"""Background refresh: pull guide, library and games, link games to airings, rebuild the indexes.

Decisions: ADR 0005, 0014."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time

from . import db
from .config import Settings
from .sources import espn
from .sources.base import Airing, Channel, LibraryItem, Source

log = logging.getLogger(__name__)
GAME_SLOT_MIN_VCN = 1000  # Dispatcharr-style per-event channels; ranked after real networks
MATCH_WINDOW = 45 * 60    # a game "airs" on a channel if kickoff is within 45 min of the listing


def link_games(airings: list[Airing], channels: dict[str, Channel],
               games: list[espn.Game]) -> dict[int, espn.Game]:
    """Return {airing index: game}. A sports airing matches a game when its channel carries
    one of the game's networks and kickoff falls inside (or just before) the listing, or when
    the channel/listing names both teams (event channels such as 'NCAAF 01: X at Y')."""
    out: dict[int, espn.Game] = {}
    for i, a in enumerate(airings):
        if a.kind != "sports":
            continue
        ch = channels.get(a.channel_id)
        ch_title = f"{ch.title} {ch.callsign}" if ch else ""
        text = f"{ch_title} {a.title} {a.subtitle}".lower()
        best, best_gap = None, None
        for g in games:
            in_window = a.begins - MATCH_WINDOW <= g.starts < a.ends
            # Event channels name the teams all day; only the listing around kickoff is the game.
            named = g.home.lower() in text and g.away.lower() in text and a.begins - 3 * 3600 <= g.starts < a.ends
            on_network = any(espn.network_matches(n, ch_title) for n in g.networks)
            if named or (in_window and on_network):
                gap = abs(g.starts - a.begins)
                if best is None or named or gap < best_gap:
                    best, best_gap = g, gap
                if named:
                    break
        if best:
            out[i] = best
    return out


def write_guide(conn: sqlite3.Connection, channels: list[Channel], airings: list[Airing],
                games: list[espn.Game]) -> None:
    by_id = {c.id: c for c in channels}
    links = link_games(airings, by_id, games)
    conn.execute("BEGIN")
    try:
        conn.execute("DELETE FROM channels")
        conn.executemany("INSERT INTO channels VALUES (?, ?, ?, ?, ?)",
                         [(c.id, c.vcn, c.title, c.callsign, c.thumb) for c in channels])
        conn.execute("DELETE FROM airings")
        conn.execute("DELETE FROM airings_fts")
        for i, a in enumerate(airings):
            game = links.get(i)
            cur = conn.execute(
                "INSERT INTO airings (channel_id, title, subtitle, summary, kind, begins, ends, year, game_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (a.channel_id, a.title, a.subtitle, a.summary, a.kind, a.begins, a.ends, a.year,
                 game.id if game else None))
            ch = by_id.get(a.channel_id)
            extra = " ".join(game.terms + [game.name, game.league.split("/")[-1]]) if game else ""
            conn.execute("INSERT INTO airings_fts (rowid, title, subtitle, summary, channel, extra) "
                         "VALUES (?, ?, ?, ?, ?, ?)",
                         (cur.lastrowid, a.title, a.subtitle, a.summary,
                          f"{ch.vcn} {ch.title} {ch.callsign}" if ch else a.channel_id, extra))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def write_games(conn: sqlite3.Connection, games: list[espn.Game]) -> None:
    conn.execute("BEGIN")
    conn.execute("DELETE FROM games")
    conn.executemany(
        "INSERT INTO games VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(g.id, g.league, g.name, g.short_name, g.starts, g.state, g.detail, g.home, g.away,
          g.home_score, g.away_score, ",".join(g.networks), " ".join(g.terms),
          g.home_id, g.away_id, g.home_logo, g.away_logo) for g in games])
    conn.execute("COMMIT")


def write_library(conn: sqlite3.Connection, items: list[LibraryItem]) -> None:
    conn.execute("BEGIN")
    try:
        conn.execute("DELETE FROM library")
        conn.execute("DELETE FROM library_fts")
        for it in items:
            cur = conn.execute(
                "INSERT INTO library (rating_key, kind, title, year, summary, genres, people, thumb, section, "
                "added_at, duration, content_rating, audience_rating, watched, leaf_count, viewed_leaf_count, guids) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (it.rating_key, it.kind, it.title, it.year, it.summary, ", ".join(it.genres),
                 ", ".join(it.people), it.thumb, it.section, it.added_at, it.duration, it.content_rating,
                 it.audience_rating, int(it.watched), it.leaf_count, it.viewed_leaf_count, " ".join(it.guids)))
            conn.execute("INSERT INTO library_fts (rowid, title, summary, genres, people) VALUES (?, ?, ?, ?, ?)",
                         (cur.lastrowid, it.title, it.summary, " ".join(it.genres), " ".join(it.people)))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


class Refresher:
    def __init__(self, settings: Settings, conn: sqlite3.Connection, source: Source):
        self.s, self.conn, self.source = settings, conn, source
        self.games: list[espn.Game] = []
        self.machine_id = ""
        self.last: dict[str, float] = {"games": 0.0, "guide": 0.0, "library": 0.0}

    async def refresh_games(self) -> None:
        followed = [r["league"] for r in self.conn.execute("SELECT DISTINCT league FROM follows")]
        leagues = tuple(dict.fromkeys([*self.s.espn_leagues, *followed]))
        games = await espn.fetch_games(leagues)
        if games:
            self.games = games
            write_games(self.conn, games)

    async def refresh_guide(self) -> None:
        source = self.source
        now = int(time.time())
        channels, airings = await source.load_guide(now - 3 * 3600, now + self.s.guide_hours * 3600)
        if source is not self.source:
            return  # switched servers while this was loading: don't write the old one's guide over the new one
        write_guide(self.conn, channels, airings, self.games)
        db.set_meta(self.conn, "guide_refreshed", str(now))
        log.info("guide: %d channels, %d airings", len(channels), len(airings))

    async def refresh_library(self) -> None:
        source = self.source
        items = await source.library()
        if source is not self.source:
            return
        write_library(self.conn, items)
        db.set_meta(self.conn, "library_refreshed", str(int(time.time())))
        log.info("library: %d items", len(items))

    def kick(self) -> None:
        """The server changed: look it up again and reload its guide and library now."""
        self.machine_id = ""
        self.last["guide"] = self.last["library"] = 0.0

    def use(self, source: Source) -> None:
        self.source = source
        self.kick()

    async def run_forever(self) -> None:
        last = self.last
        every = {"games": self.s.sports_refresh_minutes * 60, "guide": self.s.guide_refresh_minutes * 60,
                 "library": self.s.library_refresh_minutes * 60}
        jobs = {"games": self.refresh_games, "guide": self.refresh_guide, "library": self.refresh_library}
        while True:
            # Scores refresh every 30 s while a followed team or league is playing, else every few minutes.
            leagues = {r["league"] for r in self.conn.execute("SELECT league FROM follows WHERE kind = 'league'")}
            teams = espn.followed_team_keys(self.conn.execute("SELECT league, team_id FROM follows WHERE kind = 'team'"))
            live_followed = any(
                g["league"] in leagues or espn.is_followed_game(teams, g["league"], g["home_id"], g["away_id"])
                for g in self.conn.execute("SELECT league, home_id, away_id FROM games WHERE state = 'in'"))
            every["games"] = 30 if live_followed else self.s.sports_refresh_minutes * 60
            source = self.source
            if source.configured and not self.machine_id:
                try:
                    server = await source.server_id()
                    if source is self.source:
                        self.machine_id = server
                        db.set_meta(self.conn, "machine_id", server)
                except Exception:
                    log.warning("%s server isn't answering; trying again shortly", source.label)
            for name in ("games", "guide", "library"):  # games first, so the guide can link them
                if name != "games" and not self.machine_id:
                    continue  # no server connected (yet)
                if time.monotonic() - last[name] >= every[name] or not last[name]:
                    try:
                        await jobs[name]()
                        last[name] = time.monotonic()
                    except Exception:
                        log.exception("%s refresh failed; retrying in a minute", name)
                        last[name] = time.monotonic() - every[name] + 60
            # Airings keep a game_id and search joins the games table, so scores stay current
            # between guide refreshes.
            await asyncio.sleep(15)
