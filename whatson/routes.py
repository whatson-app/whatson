"""API for the sectioned UI: now playing, Live TV guide, Library, Sports, Trakt and suggestions."""

from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import ai, ai_settings, apps, arr, devices, plex_users, search, suggest, tune
from .sources import espn
from .state import state
from .trakt import TraktError

router = APIRouter(prefix="/api")
_cache: dict[str, tuple[float, object]] = {}


def cached(key: str, ttl: float):
    hit = _cache.get(key)
    return hit[1] if hit and time.time() - hit[0] < ttl else None


def remember(key: str, value):
    _cache[key] = (time.time(), value)
    return value


def _device(device_id: int) -> dict:
    d = devices.get_device(state.conn, device_id)
    if not d:
        raise HTTPException(404, "No such TV")
    return d


# --- AI: model list and one-line answers -------------------------------------------------------

class ModelsIn(BaseModel):
    provider: str
    base_url: str = ""
    key: str = ""


@router.post("/settings/ai/models")
async def ai_models(body: ModelsIn):
    """Models for the dropdown. Uses the key typed in the form, else the saved key, but only when
    the saved key belongs to this same server URL. The typed key isn't stored."""
    base_url = body.base_url.strip() if body.provider == "openai" else ""
    try:
        await asyncio.wait_for(asyncio.to_thread(ai_settings.check_base_url, base_url), 5)
    except asyncio.TimeoutError as exc:
        raise HTTPException(400, "Looking up that server took too long") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    key = body.key.strip()
    if not key:
        cfg = ai_settings.load(state.conn)
        if cfg.base_url == base_url:
            key = cfg.keys.get(body.provider, ("", ""))[0]
    if body.provider in ("anthropic", "openai") and not key and ai.key_required(body.provider, base_url):
        raise HTTPException(400, "Paste the API key first, so the model list can be fetched.")
    try:
        models = await ai.list_models(body.provider, base_url, key)
    except Exception as exc:
        raise HTTPException(502, f"Couldn't list models ({_brief(exc)}). Check the key and server URL.") from exc
    return {"models": models}


def _brief(exc: Exception) -> str:
    """A short, safe description of a provider error: the status code or error type, never its body."""
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    return f"HTTP {status}" if status else type(exc).__name__


@router.get("/answer")
async def answer(q: str, filters: str, scope: str = "all"):
    """One line answering the question from the matches only (AI); empty when AI is off."""
    if not state.interpreter.enabled:
        return {"answer": ""}
    try:
        f = search.parse_filters(filters)
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, "Bad filters") from exc
    if scope != "all":
        f.scope = scope
    res = search.run(state.conn, f)
    lines = []
    for g in res["games"][:5]:
        ch = g["channels"][0]["title"] if g["channels"] else ", ".join(g["networks"]) or "no channel"
        lines.append(f"Game: {g['away']} at {g['home']} ({g['league']}), {g['detail']}, on {ch}")
    for a in res["guide"][:8]:
        when = "on now" if a["on_now"] else time.strftime("%a %I:%M %p", time.localtime(a["begins"]))
        lines.append(f"Live TV: {a['title']} {a['subtitle']} | {when} | {a['channels'][0]['vcn']} "
                     f"{a['channels'][0]['title']} | {round((a['ends'] - a['begins']) / 60)} min")
    for li in res["library"][:8]:
        lines.append(f"Library {li['kind']}: {li['title']} ({li['year']}) | {round((li['duration'] or 0) / 60000)} min"
                     f" | {li['genres']} | {li['content_rating']}{' | watched' if li['watched'] else ''}")
    return {"answer": await state.interpreter.answer(q, lines)}


# --- Now playing --------------------------------------------------------------------------------

@router.get("/devices/{device_id}/now")
async def now_playing(device_id: int):
    """What the TV is showing. Cached a few seconds per TV so many open pages don't each query it."""
    key = f"now:{device_id}"
    if (hit := cached(key, 8)) is not None:
        return hit
    d = _device(device_id)
    sessions = [s for s in await state.source.playing() if tune.on_tv(s, d)]
    if sessions:
        s = sessions[0]
        out = {"state": s.state, "kind": s.kind, "app": s.product, "title": s.title, "subtitle": s.episode,
               "thumb": s.thumb, "offset": s.offset, "duration": s.duration, "rating_key": s.rating_key,
               "show_key": s.show_key}
        if s.live:
            channel = s.channel_id or _live_channel(device_id, s.title)
            row = state.conn.execute(
                """SELECT a.id AS aid, a.title, a.subtitle, a.summary, a.begins, a.ends, c.vcn, c.title AS ch,
                          c.thumb AS ch_thumb, g.id AS gid, g.league, g.away, g.home, g.away_score, g.home_score,
                          g.away_logo, g.home_logo, g.detail, g.state AS gstate
                   FROM channels c LEFT JOIN airings a ON a.channel_id = c.id AND a.begins <= ? AND a.ends > ?
                   LEFT JOIN games g ON g.id = a.game_id WHERE c.id = ?""",
                (int(time.time()), int(time.time()), channel)).fetchone() if channel else None
            if row:
                out.update(title=row["title"] or row["ch"], subtitle="", summary=row["summary"] or "",
                           airing_id=row["aid"], channel={"vcn": row["vcn"], "title": row["ch"],
                                                          "thumb": row["ch_thumb"], "id": channel})
                if row["begins"]:
                    out.update(offset=(int(time.time()) - row["begins"]) * 1000,
                               duration=(row["ends"] - row["begins"]) * 1000)
                if row["away"]:
                    out["game"] = {"id": row["gid"], "league": espn.league_label(row["league"]),
                                   "away": row["away"], "home": row["home"], "away_score": row["away_score"],
                                   "home_score": row["home_score"], "away_logo": row["away_logo"],
                                   "home_logo": row["home_logo"], "detail": row["detail"], "state": row["gstate"],
                                   "espn_url": espn.game_url(row["gid"])}
        return remember(key, out)
    drv = state.drivers.get(d["kind"])
    st = await drv.status(d["host"])
    if st.error and st.reachable:
        out = {"state": "not_paired", "kind": "none", "title": "Not paired"}
    elif not st.reachable:
        out = {"state": "unreachable", "kind": "none", "title": "Can't reach the TV"}
    elif st.is_on is False:
        out = {"state": "off", "kind": "none", "title": "Off"}
    elif st.current_app in suggest_idle_apps():
        out = {"state": "idle", "kind": "none", "title": "Home screen"}
    else:
        out = {"state": "app", "kind": "app", "title": apps.name_of(st.current_app) or "An app",
               "app": st.current_app}
    if st.current_app:
        apps.note_seen(state.conn, device_id, st.current_app, suggest_idle_apps())
    return remember(key, out)


def _live_channel(device_id: int, title: str) -> str:
    """Best guess at the channel a Live TV session is on: the channel WhatsOn last tuned on this TV
    if it's showing this title now, else the only channel showing this title now."""
    now = int(time.time())
    on_now = [r["channel_id"] for r in state.conn.execute(
        "SELECT channel_id FROM airings WHERE title = ? AND begins <= ? AND ends > ?", (title, now, now))]
    last = state.last_tune.get(device_id)
    if last and (last[0] in on_now or not on_now):
        return last[0]
    return on_now[0] if len(set(on_now)) == 1 else ""


def suggest_idle_apps():
    from .tune import IDLE_APPS
    return IDLE_APPS


class KeyIn(BaseModel):
    key: str


async def _stop_key(device_id: int, d: dict) -> str:
    """Plezy's video player ignores MEDIA_STOP and only leaves on BACK. BACK also walks through Plezy's
    menus, so it's sent only while the server still reports something playing on this TV."""
    st = await state.drivers[d["kind"]].status(d["host"])
    if st.current_app != tune.PLEZY:
        return "MEDIA_STOP"
    _cache.pop(f"now:{device_id}", None)
    return "MEDIA_STOP" if (await now_playing(device_id))["state"] == "app" else "BACK"


# The now-playing bar and card. In Plezy, MEDIA_REWIND skips back by its small seek time (10 s unless changed), or a
# chapter when the item has chapters.
NOW_KEYS = {"play_pause": "MEDIA_PLAY_PAUSE", "stop": "MEDIA_STOP", "back": "BACK", "home": "HOME",
            "rewind": "MEDIA_REWIND", "volume_up": "VOLUME_UP", "volume_down": "VOLUME_DOWN", "volume_mute": "VOLUME_MUTE"}


@router.post("/devices/{device_id}/key")
async def press_key(device_id: int, body: KeyIn):
    keys = NOW_KEYS
    if body.key not in keys:
        raise HTTPException(400, f"Keys: {', '.join(keys)}")
    d = _device(device_id)
    key = keys[body.key]
    try:
        if body.key == "stop":
            key = await _stop_key(device_id, d)
        await state.drivers[d["kind"]].send_key(d["host"], key)
    except Exception as exc:
        raise HTTPException(502, f"Couldn't reach {d['name']}: {exc}") from exc
    _cache.pop(f"now:{device_id}", None)
    return {"ok": True}


# --- Live TV guide ------------------------------------------------------------------------------

@router.get("/guide")
async def guide(hours: float = 4, view: str = "all", start: int = 0):
    """Channels with their airings in a window starting at the last half hour (or `start`).
    view: all | favorites | sports | movie | episode."""
    now = int(time.time())
    begin = start or now - now % 1800
    end = begin + int(min(max(hours, 1), 24) * 3600)
    favs = {r["channel_id"] for r in state.conn.execute("SELECT channel_id FROM fav_channels")}
    rows = state.conn.execute(
        """SELECT a.id, a.channel_id, a.title, a.subtitle, a.kind, a.begins, a.ends, a.game_id,
                  g.away, g.home, g.away_score, g.home_score, g.detail, g.state AS gstate
           FROM airings a LEFT JOIN games g ON g.id = a.game_id
           WHERE a.ends > ? AND a.begins < ? ORDER BY a.begins""", (begin, end)).fetchall()
    by_ch: dict[str, list] = {}
    for r in rows:
        a = {"id": r["id"], "title": r["title"], "subtitle": r["subtitle"], "kind": r["kind"],
             "begins": r["begins"], "ends": r["ends"]}
        if r["away"]:
            a["game"] = {"away": r["away"], "home": r["home"], "away_score": r["away_score"],
                         "home_score": r["home_score"], "detail": r["detail"], "state": r["gstate"]}
        by_ch.setdefault(r["channel_id"], []).append(a)
    chans = []
    for c in state.conn.execute("SELECT * FROM channels"):
        airs = by_ch.get(c["id"], [])
        if view == "favorites" and c["id"] not in favs:
            continue
        if view in ("sports", "movie", "episode") and not any(a["kind"] == view for a in airs):
            continue
        chans.append({"id": c["id"], "vcn": c["vcn"], "title": c["title"], "thumb": c["thumb"],
                      "fav": c["id"] in favs, "airings": airs})
    chans.sort(key=lambda c: (not c["fav"], int(c["vcn"]) if c["vcn"].isdigit() else 99999))
    return {"start": begin, "end": end, "now": now, "channels": chans}


@router.get("/airing/{airing_id}")
async def airing(airing_id: int):
    r = state.conn.execute(
        """SELECT a.*, c.vcn, c.title AS ch, c.thumb AS ch_thumb FROM airings a JOIN channels c ON c.id = a.channel_id
           WHERE a.id = ?""", (airing_id,)).fetchone()
    if not r:
        raise HTTPException(404, "That listing is no longer in the guide")
    later = state.conn.execute(
        """SELECT a.begins, a.ends, c.vcn, c.title AS ch FROM airings a JOIN channels c ON c.id = a.channel_id
           WHERE a.title = ? AND a.subtitle = ? AND a.id != ? AND a.ends > ? ORDER BY a.begins LIMIT 6""",
        (r["title"], r["subtitle"], airing_id, int(time.time()))).fetchall()
    return {"id": r["id"], "title": r["title"], "subtitle": r["subtitle"], "summary": r["summary"], "kind": r["kind"],
            "begins": r["begins"], "ends": r["ends"], "year": r["year"],
            "channel": {"id": r["channel_id"], "vcn": r["vcn"], "title": r["ch"], "thumb": r["ch_thumb"]},
            "also": [dict(x) for x in later]}


@router.post("/favorites/channels/{channel_id}")
async def fav_add(channel_id: str):
    state.conn.execute("INSERT OR IGNORE INTO fav_channels VALUES (?)", (channel_id,))
    return {"ok": True}


@router.delete("/favorites/channels/{channel_id}")
async def fav_remove(channel_id: str):
    state.conn.execute("DELETE FROM fav_channels WHERE channel_id = ?", (channel_id,))
    return {"ok": True}


# --- Library ----------------------------------------------------------------------------------

SORTS = {"added": "added_at DESC", "title": "title COLLATE NOCASE", "year": "year DESC, title",
         "rating": "audience_rating DESC NULLS LAST, title"}


@router.get("/library")
async def library(kind: str = "movie", sort: str = "added", genre: str = "", q: str = "",
                  unwatched: bool = False, offset: int = 0, limit: int = 60, device: int = 0):
    if kind not in ("movie", "show"):
        raise HTTPException(400, "kind is movie or show")
    user = plex_users.viewer(device)
    where, args = ["l.kind = ?"], [kind]
    if genre:
        where.append("(', ' || l.genres || ', ') LIKE ?")
        args.append(f"%, {genre}, %")
    if unwatched and user:
        where.append("l.rating_key NOT IN (SELECT rating_key FROM user_watched WHERE user = ? AND watched = 1)")
        args.append(user)
    elif unwatched:
        where.append("l.watched = 0")
    src = "library l"
    order = "l." + SORTS.get(sort, SORTS["added"]).replace(", title", ", l.title")
    fq = search.fts_query(q)
    if fq:
        src = "library_fts JOIN library l ON l.rowid = library_fts.rowid"
        where.insert(0, "library_fts MATCH ?")
        args.insert(0, fq)
        if sort == "added" and q:
            order = "bm25(library_fts, 10.0, 1.0, 2.0, 3.0)"
    total = state.conn.execute(f"SELECT count(*) FROM {src} WHERE {' AND '.join(where)}", args).fetchone()[0]
    rows = state.conn.execute(f"SELECT l.* FROM {src} WHERE {' AND '.join(where)} ORDER BY {order} LIMIT ? OFFSET ?",
                              args + [min(limit, 200), offset]).fetchall()
    items = [search.library_item(r) for r in rows]
    return {"total": total, "items": plex_users.apply_watched(user, items) if user else items}


@router.get("/library/genres")
async def library_genres(kind: str = "movie"):
    counts: dict[str, int] = {}
    for r in state.conn.execute("SELECT genres FROM library WHERE kind = ?", (kind,)):
        for g in filter(None, (x.strip() for x in r["genres"].split(","))):
            counts[g] = counts.get(g, 0) + 1
    return [{"name": g, "count": n} for g, n in sorted(counts.items(), key=lambda x: -x[1])]


@router.get("/library/item/{rating_key}")
async def library_detail(rating_key: str, device: int = 0):
    if not state.source.valid_id(rating_key):
        raise HTTPException(400, "Bad id")
    out = await plex_users.item_as(device, rating_key)
    if not out:
        raise HTTPException(404, "Not in the library")
    return out


@router.get("/library/season/{rating_key}")
async def library_season(rating_key: str, device: int = 0):
    if not state.source.valid_id(rating_key):
        raise HTTPException(400, "Bad id")
    return await plex_users.episodes_as(device, rating_key)


# --- Sports -----------------------------------------------------------------------------------

def _followed() -> tuple[set[str], dict[str, dict]]:
    leagues, teams = set(), {}
    for r in state.conn.execute("SELECT * FROM follows"):
        if r["kind"] == "league":
            leagues.add(r["league"])
        else:
            teams[f"{r['league']}:{r['team_id']}"] = dict(r)
    return leagues, teams


@router.get("/sports/leagues")
async def sports_leagues():
    leagues, _ = _followed()
    known = list(dict.fromkeys([*state.settings.espn_leagues, *espn.LEAGUE_LABELS, *leagues]))
    return [{"league": lg, "label": espn.league_label(lg), "followed": lg in leagues} for lg in known]


@router.get("/sports/teams")
async def sports_teams(league: str):
    teams = cached(f"teams:{league}", 86400)
    if teams is None:
        try:
            teams = remember(f"teams:{league}", await espn.fetch_teams(league, state.http))
        except Exception as exc:
            raise HTTPException(502, f"Couldn't load teams: {exc}") from exc
    _, followed = _followed()
    return [{**t, "followed": f"{league}:{t['id']}" in followed} for t in teams]


class FollowIn(BaseModel):
    kind: str
    league: str
    team_id: str = ""
    name: str = ""
    abbr: str = ""
    logo: str = ""


@router.post("/follows")
async def follow(body: FollowIn):
    if body.kind not in ("league", "team"):
        raise HTTPException(400, "kind is league or team")
    state.conn.execute("INSERT OR REPLACE INTO follows VALUES (?, ?, ?, ?, ?, ?)",
                       (body.kind, body.league, body.team_id if body.kind == "team" else "", body.name, body.abbr, body.logo))
    if body.kind == "league" and body.league not in state.settings.espn_leagues:
        asyncio.create_task(state.refresher.refresh_games())
    return {"ok": True}


@router.delete("/follows")
async def unfollow(kind: str, league: str, team_id: str = ""):
    state.conn.execute("DELETE FROM follows WHERE kind = ? AND league = ? AND team_id = ?", (kind, league, team_id))
    return {"ok": True}


@router.get("/follows")
async def follows():
    return [dict(r) for r in state.conn.execute("SELECT * FROM follows ORDER BY kind, name")]


def _game_cards(where: str, args: list, hours: int = 24) -> list[dict]:
    return search._games(state.conn, int(time.time()), hours, where, args)


def _schedule_card(g: espn.Game | None) -> dict | None:
    if not g:
        return None
    rows = _game_cards("g.id = ?", [g.id])
    if rows:
        return rows[0]
    return {"id": g.id, "league": espn.league_label(g.league), "name": g.name, "short": g.short_name, "starts": g.starts,
            "state": g.state, "detail": g.detail, "home": g.home, "away": g.away, "home_score": g.home_score,
            "away_score": g.away_score, "networks": g.networks, "channels": [], "home_logo": g.home_logo,
            "away_logo": g.away_logo}


@router.get("/sports/foryou")
async def sports_for_you():
    leagues, teams = _followed()
    now = int(time.time())
    team_rows = []
    schools = set()
    for t in teams.values():
        # A school's games in any college sport, not just the league it was followed in, so a school
        # followed in two college leagues gets one row.
        lgs = espn.team_leagues(t["league"])
        if (lgs, t["team_id"]) in schools:
            continue
        schools.add((lgs, t["team_id"]))
        same_team = f"g.league IN ({','.join('?' * len(lgs))}) AND (g.home_id = ? OR g.away_id = ?)"
        team_args = [*lgs, t["team_id"], t["team_id"]]
        live = _game_cards(f"g.state = 'in' AND {same_team}", team_args)
        sched = cached(f"sched:{t['league']}:{t['team_id']}", 600)
        if sched is None:
            try:
                sched = remember(f"sched:{t['league']}:{t['team_id']}",
                                 await espn.fetch_schedule(t["league"], t["team_id"], state.http))
            except Exception:
                sched = {"last": None, "next": None}
        nxt = _schedule_card(sched["next"])
        if len(lgs) > 1:   # an earlier game in the school's other sports beats the followed league's next one
            soon = _game_cards(f"g.state = 'pre' AND {same_team}", team_args)
            if soon and (not nxt or soon[0]["starts"] < nxt["starts"]):
                nxt = soon[0]
        team_rows.append({"team": {"id": t["team_id"], "name": t["name"], "abbr": t["abbr"], "logo": t["logo"],
                                   "league": "College" if len(lgs) > 1 else espn.league_label(t["league"])},
                          "live": live[0] if live else None,
                          "last": None if live else _schedule_card(sched["last"]),
                          "next": None if live else nxt})
    team_rows.sort(key=lambda r: (r["live"] is None, (r["next"] or {}).get("starts", 1 << 40)))
    league_games = []
    if leagues:
        marks = ",".join("?" * len(leagues))
        league_games = _game_cards(f"g.league IN ({marks}) AND (g.state = 'in' OR (g.state = 'pre' AND g.starts < ?))",
                                   [*leagues, now + 4 * 3600], 4)
    worth = {w["id"]: w for w in suggest.worth_switching(state.conn)}
    worth_cards = [{**c, "reason": worth[c["id"]]["reason"]}
                   for c in _game_cards("g.state = 'in'", [], 4) if c["id"] in worth]
    shown = {c["id"] for c in league_games} | {c["id"] for c in worth_cards}
    for r in team_rows:
        for k in ("live", "last", "next"):
            if r[k]:
                shown.add(r[k]["id"])
    others = [c for c in search.sports_board(state.conn, now) if c["id"] not in shown]
    return {"teams": team_rows, "leagues": league_games, "worth": worth_cards, "others": others,
            "followed_leagues": [{"league": lg, "label": espn.league_label(lg)} for lg in sorted(leagues)]}


@router.get("/sports/league")
async def sports_league(league: str):
    return _game_cards("g.league = ?", [league], 36)


@router.get("/sports/recap")
async def sports_recap(game_id: str):
    league, _, event = game_id.rpartition(":")
    if not league or not event.isdigit():
        raise HTTPException(400, "Bad game id")
    if (hit := cached(f"recap:{game_id}", 60)) is not None:
        return hit
    try:
        facts, plays = await espn.fetch_recap_facts(league, event, state.http)
    except Exception as exc:
        raise HTTPException(502, f"Couldn't load the game: {exc}") from exc
    text = await state.interpreter.recap(facts) if state.interpreter.enabled else ""
    return remember(f"recap:{game_id}", {"recap": text, "plays": plays, "ai": bool(text)})


# --- Trakt settings ---------------------------------------------------------------------------

class TraktAppIn(BaseModel):
    client_id: str = ""
    client_secret: str = ""


@router.get("/trakt")
async def trakt_status():
    return state.trakt.public()


@router.put("/trakt/app")
async def trakt_app(body: TraktAppIn):
    state.trakt.save_app(body.client_id, body.client_secret)
    return state.trakt.public()


@router.post("/trakt/connect")
async def trakt_connect():
    try:
        return await state.trakt.start_device()
    except TraktError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/trakt/poll")
async def trakt_poll():
    status = await state.trakt.poll_device()
    if status == "connected":
        asyncio.create_task(state.trakt.sync(force=True))
    return {"status": status, **state.trakt.public()}


@router.post("/trakt/disconnect")
async def trakt_disconnect():
    state.trakt.disconnect()
    return state.trakt.public()


@router.post("/trakt/sync")
async def trakt_sync():
    try:
        await state.trakt.sync(force=True)
    except Exception as exc:
        raise HTTPException(502, f"Trakt sync failed: {exc}") from exc
    return state.trakt.public()


# --- Suggestions ----------------------------------------------------------------------------------

@router.get("/suggest/live")
async def suggest_live():
    cache = state.trakt.cache()
    shows = suggest.live_shows(state.conn, cache)
    picks = await suggest.ai_rank(state.interpreter, "live", suggest.live_candidates(state.conn, cache), 6,
                                  suggest.taste_context(cache))
    return {"your_shows": shows, "picks": picks, "ai": suggest.ai_ranked(picks), "trakt": state.trakt.connected}


@router.get("/suggest/library")
async def suggest_library(device: int = 0):
    cache = state.trakt.cache()
    user = plex_users.viewer(device)
    pool = suggest.library_candidates(state.conn, cache)
    if user:  # Trakt follows one account, so a TV's own user skips it
        source = state.source.name
        up_next = await plex_users.up_next_as(user)
        seen = plex_users.watched_keys(user)
        pool = [c for c in pool if c["rating_key"] not in seen]
    else:
        up_next = suggest.library_up_next(state.conn, cache)
        source = "trakt"
        if not up_next:
            source = state.source.name
            up_next = await state.source.up_next()
    picks = await suggest.ai_rank(state.interpreter, "library", pool, 4, suggest.taste_context(cache))
    return {"up_next": up_next, "up_next_source": source, "source_label": state.source.label, "picks": picks,
            "missing": suggest.watchlist_missing(state.conn, cache),
            "get": {k: arr.load(state.conn, k).configured for k in arr.KINDS},
            "ai": suggest.ai_ranked(picks), "trakt": state.trakt.connected}
