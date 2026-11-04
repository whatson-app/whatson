"""Suggestion rows. Rules and Trakt choose the candidates; AI (when on) only re-orders them and writes
a short "because" line. With AI off every row still fills, in rule order, with rule reasons.

Decisions: ADR 0016, 0018."""

from __future__ import annotations

import re
import sqlite3
import time
from datetime import datetime

from .ai import Interpreter
from .sources import espn
from .trakt import guid_keys, norm_title

RANK_TTL = 15 * 60
_rank_cache: dict[str, tuple[float, list[dict]]] = {}


def _ts(iso: str) -> int:
    try:
        return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())
    except (ValueError, AttributeError):
        return 0


def _airings(conn: sqlite3.Connection, start: int, end: int) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT a.*, c.vcn, c.title AS ch_title, c.thumb AS ch_thumb,
                  EXISTS (SELECT 1 FROM fav_channels f WHERE f.channel_id = a.channel_id) AS fav
           FROM airings a JOIN channels c ON c.id = a.channel_id
           WHERE a.ends > ? AND a.begins < ? ORDER BY a.begins""", (start, end)).fetchall()


def _airing(r: sqlite3.Row, now: int, reason: str, source: str) -> dict:
    return {"type": "airing", "id": f"a{r['id']}", "title": r["title"], "subtitle": r["subtitle"],
            "begins": r["begins"], "ends": r["ends"], "on_now": r["begins"] <= now < r["ends"],
            "channel": {"vcn": r["vcn"], "title": r["ch_title"], "thumb": r["ch_thumb"]},
            "reason": reason, "source": source, "kind": r["kind"]}


def _rating_index(cache: dict) -> dict[str, int]:
    return {norm_title(x["title"]): x["rating"] for x in cache.get("ratings", []) if x.get("rating")}


def live_shows(conn: sqlite3.Connection, cache: dict, now: int | None = None) -> list[dict]:
    """'Your shows on tonight': new episodes from the Trakt calendar, shows you watch, and watchlist
    or highly rated movies, found in the next six hours of the guide by title."""
    now = now or int(time.time())
    rows = _airings(conn, now - 1800, now + 6 * 3600)
    by_title: dict[str, list[sqlite3.Row]] = {}
    for r in rows:
        by_title.setdefault(norm_title(r["title"]), []).append(r)
    out: dict[tuple, dict] = {}

    def add(r: sqlite3.Row, reason: str):
        key = (norm_title(r["title"]), r["begins"])
        if key not in out and r["ends"] > now:
            out[key] = _airing(r, now, reason, "trakt")

    for ep in cache.get("calendar", []):
        aired = _ts(ep.get("first_aired", ""))
        matches = by_title.get(norm_title(ep["title"]), [])
        near = [r for r in matches if abs(r["begins"] - aired) <= 45 * 60] or matches[:1]
        for r in near[:1]:
            add(r, f"New episode S{ep.get('season', 0):02d}E{ep.get('number', 0):02d}")
    recent = now - 60 * 86400
    for show in cache.get("watched_shows", []):
        if _ts(show.get("last_watched_at", "")) >= recent:
            for r in by_title.get(norm_title(show["title"]), [])[:1]:
                add(r, "You watch this")
    ratings = _rating_index(cache)
    for item in cache.get("watchlist", []):
        if item["kind"] == "movie":
            for r in by_title.get(norm_title(item["title"]), [])[:1]:
                add(r, "On your watchlist")
    for title, rating in ratings.items():
        if rating >= 8:
            for r in by_title.get(title, [])[:1]:
                add(r, f"You rated it {rating}")
    return sorted(out.values(), key=lambda x: (not x["on_now"], x["begins"]))[:12]


def live_candidates(conn: sqlite3.Connection, cache: dict, now: int | None = None) -> list[dict]:
    """Pool for 'On now, picked for you': things on now or within the hour on favorite channels,
    your Trakt matches, Trakt recommendations in the guide, and live games in followed leagues."""
    now = now or int(time.time())
    rows = _airings(conn, now, now + 3600)
    followed = {r["league"] for r in conn.execute("SELECT DISTINCT league FROM follows")}
    teams = espn.followed_team_keys(conn.execute("SELECT league, team_id FROM follows WHERE kind = 'team'"))
    recs = {norm_title(x["title"]) for x in cache.get("recommended", [])}
    pool: dict[str, dict] = {}
    for s in live_shows(conn, cache, now):
        if s["begins"] <= now + 3600:
            pool[s["id"]] = s
    games = {g["id"]: g for g in conn.execute("SELECT * FROM games")}
    for r in rows:
        aid = f"a{r['id']}"
        if aid in pool:
            continue
        g = games.get(r["game_id"]) if r["game_id"] else None
        if g and (g["state"] == "in" or g["starts"] <= now + 3600) and (
                g["league"] in followed or espn.is_followed_game(teams, g["league"], g["home_id"], g["away_id"])):
            pool[aid] = _airing(r, now, f"{g['away']} at {g['home']}, {g['detail']}", "sports")
        elif norm_title(r["title"]) in recs:
            pool[aid] = _airing(r, now, "Trakt recommends it", "trakt")
        elif r["fav"] and r["begins"] <= now:
            pool[aid] = _airing(r, now, "On one of your favorite channels", "favorite")
    return list(pool.values())


def library_up_next(conn: sqlite3.Connection, cache: dict) -> list[dict]:
    """Trakt progress matched to shows you own (Plezy's show link plays the next episode)."""
    out = []
    for item in cache.get("up_next", []):
        row = match_library(conn, "show", item)
        if row:
            out.append({"type": "library", "rating_key": row["rating_key"], "kind": "show", "title": row["title"],
                        "thumb": row["thumb"], "year": row["year"],
                        "label": f"S{item.get('season', 0):02d}E{item.get('number', 0):02d} {item.get('episode_title') or ''}".strip(),
                        "reason": "Up next on Trakt"})
    return out[:12]


def match_library(conn: sqlite3.Connection, kind: str, item: dict) -> sqlite3.Row | None:
    for key in guid_keys(item.get("ids", {})):
        row = conn.execute("SELECT * FROM library WHERE kind = ? AND (' ' || guids || ' ') LIKE ?",
                           (kind, f"% {key} %")).fetchone()
        if row:
            return row
    for row in conn.execute("SELECT * FROM library WHERE kind = ? AND title LIKE ?", (kind, item["title"])):
        if not item.get("year") or not row["year"] or abs(row["year"] - item["year"]) <= 1:
            return row
    return None


def watchlist_missing(conn: sqlite3.Connection, cache: dict) -> list[dict]:
    out = []
    for item in cache.get("watchlist", []):
        if not match_library(conn, item["kind"], item):
            out.append({"type": "missing", "kind": item["kind"], "title": item["title"], "year": item.get("year"),
                        "tmdb": item.get("ids", {}).get("tmdb"), "tvdb": item.get("ids", {}).get("tvdb"),
                        "reason": "On your Trakt watchlist"})
    return out[:20]


def library_candidates(conn: sqlite3.Connection, cache: dict) -> list[dict]:
    """Pool for 'Tonight's pick': unwatched movies you own that are on your watchlist or recommended,
    plus well-rated unwatched recent additions."""
    pool: dict[str, dict] = {}

    def add(row: sqlite3.Row, reason: str):
        if row and not row["watched"] and row["rating_key"] not in pool:
            pool[row["rating_key"]] = {"type": "library", "rating_key": row["rating_key"], "kind": row["kind"],
                                       "title": row["title"], "year": row["year"], "thumb": row["thumb"],
                                       "duration": row["duration"], "genres": row["genres"],
                                       "summary": row["summary"], "reason": reason,
                                       "id": f"l{row['rating_key']}"}

    for item in cache.get("watchlist", []):
        if item["kind"] == "movie":
            add(match_library(conn, "movie", item), "On your watchlist")
    for item in cache.get("recommended", []):
        if item["kind"] == "movie":
            add(match_library(conn, "movie", item), "Trakt recommends it")
    for row in conn.execute("""SELECT * FROM library WHERE kind = 'movie' AND watched = 0 AND audience_rating >= 7
                               ORDER BY added_at DESC LIMIT 25"""):
        add(row, f"Rated {row['audience_rating']:.1f} by audiences")
    return list(pool.values())


LATE = re.compile(r"\b(4th|OT|2nd half|3rd|8th|9th|extra|stoppage|9\d')", re.I)


def worth_switching(conn: sqlite3.Connection, now: int | None = None) -> list[dict]:
    """Close games late, from the score alone (no AI): football within 8, basketball within 6,
    everything else within 1, in the last period."""
    followed = {r["league"] for r in conn.execute("SELECT DISTINCT league FROM follows")}
    out = []
    for g in conn.execute("SELECT * FROM games WHERE state = 'in'"):
        try:
            diff = abs(int(g["home_score"] or 0) - int(g["away_score"] or 0))
        except ValueError:
            continue
        sport = g["league"].split("/")[0]
        limit = {"football": 8, "basketball": 6}.get(sport, 1)
        if diff <= limit and LATE.search(g["detail"] or ""):
            out.append({"id": g["id"], "reason": "Tied late" if diff == 0 else "Close game late",
                        "followed": g["league"] in followed})
    return sorted(out, key=lambda x: not x["followed"])


async def ai_rank(interpreter: Interpreter, key: str, candidates: list[dict], want: int,
                  context: str = "") -> list[dict]:
    """Candidates re-ordered by AI with its reasons, cached per key for 15 minutes. Falls back to the
    candidates' own order and rule reasons when AI is off or fails."""
    if not interpreter.enabled or not candidates:
        return candidates[:want]
    hit = _rank_cache.get(key)
    by_id = {c["id"]: c for c in candidates}
    if hit and time.time() - hit[0] < RANK_TTL and all(p["id"] in by_id for p in hit[1]):
        picks = hit[1]
    else:
        lines = []
        for c in candidates:
            when = "on now" if c.get("on_now") else (
                datetime.fromtimestamp(c["begins"]).strftime("%I:%M %p").lstrip("0") if c.get("begins") else "")
            if c.get("type") == "airing":
                lines.append({"id": c["id"], "text": f"{c['title']} {c.get('subtitle') or ''} | {when} on "
                                                     f"{c['channel']['title']} | {c['kind']} | signal: {c['reason']}"})
            else:
                mins = round((c.get("duration") or 0) / 60000)
                lines.append({"id": c["id"], "text": f"{c['title']} ({c.get('year') or ''}) | {mins} min | "
                                                     f"{c.get('genres', '')} | signal: {c['reason']}"})
        picks = await interpreter.rank(lines, want, context)
        if not picks:
            return candidates[:want]
        _rank_cache[key] = (time.time(), picks)
    return [{**by_id[p["id"]], "reason": p["reason"], "ai": True} for p in picks if p["id"] in by_id]


def taste_context(cache: dict) -> str:
    top = sorted((r for r in cache.get("ratings", []) if (r.get("rating") or 0) >= 8),
                 key=lambda r: -r["rating"])[:15]
    recent = [s["title"] for s in cache.get("watched_shows", [])[:10]]
    parts = []
    if top:
        parts.append("Rated highly: " + ", ".join(f"{r['title']} ({r['rating']})" for r in top))
    if recent:
        parts.append("Recently watching: " + ", ".join(recent))
    return "\n".join(parts)
