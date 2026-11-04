"""Search over the guide and the library. Works on its own; the AI layer (ai.py) only turns a
free-form question into the same Filters."""

from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass, field

STOPWORDS = {
    "a", "an", "the", "is", "are", "on", "in", "at", "of", "for", "to", "what", "whats", "what's", "where",
    "which", "who", "game", "games", "tv", "channel", "watch", "show", "me", "find", "playing",
    "now", "tonight", "today", "right", "any", "something", "there", "be", "can", "i",
}
GAME_SLOT_MIN_VCN = 1000
KIDS_RATINGS = ("G", "TV-Y", "TV-Y7", "TV-Y7-FV", "TV-G")
FAMILY_RATINGS = KIDS_RATINGS + ("PG", "TV-PG")
# Plex's Live TV guide carries no ratings or genres, so on live TV "kids" and "family" go by channel.
KIDS_CHANNEL_RE = re.compile(
    r"disney ?(jr|junior|channel)|^disney$|nick ?jr|nickelodeon|^nick$|nicktoons|nick toons|cartoon ?network|"
    r"boomerang|pbs ?kids|discovery family|baby ?tv|baby ?first|universal kids|sprout|treehouse", re.I)
# Premium "Kids & Family" channels run PG-13 films, so they count as family, not kids.
FAMILY_CHANNEL_RE = re.compile(KIDS_CHANNEL_RE.pattern + r"|kids|family|disney ?xd|teen ?nick", re.I)
# Genres that mean "kids' channels" on live TV, where listings have no genres to match.
KIDS_GENRES = {"animation", "animated", "cartoon", "cartoons", "kids", "children", "family"}
DECADE_RE = re.compile(r"\b(?:(19|20)?(\d)0)'?s\b", re.I)


@dataclass
class Filters:
    text: str = ""
    scope: str = "all"                 # all | guide | library
    on_now: bool = False
    within_minutes: int | None = None  # guide: only airings starting within this window
    max_minutes: int | None = None     # longest running time wanted
    audience: str = "any"              # any | family | kids (library content ratings)
    kinds: list[str] = field(default_factory=list)   # movie | episode | sports | show
    genres: list[str] = field(default_factory=list)
    year_from: int | None = None       # release years, inclusive
    year_to: int | None = None
    limit: int = 40


FILTER_FIELDS = ("text", "scope", "on_now", "within_minutes", "max_minutes", "audience", "kinds", "genres",
                 "year_from", "year_to")


def take_decade(f: Filters) -> Filters:
    """Move a decade written into the search text ("90s", "1980s") into the year filter. The words
    "90s" never appear in a title or summary, so leaving it as text finds nothing."""
    m = DECADE_RE.search(f.text)
    if m and not (f.year_from or f.year_to):
        century = m.group(1) or ("20" if m.group(2) in "012" else "19")
        f.year_from = int(f"{century}{m.group(2)}0")
        f.year_to = f.year_from + 9
        f.text = re.sub(r"\s+", " ", DECADE_RE.sub(" ", f.text)).strip()
    return f


def filters_dict(f: Filters) -> dict:
    return {k: getattr(f, k) for k in FILTER_FIELDS}


def parse_filters(raw: str) -> Filters:
    """Filters sent back by the browser (edited chips). Strictly typed and bounded; raises ValueError."""
    if len(raw) > 4000:
        raise ValueError("filters too long")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("filters must be an object")

    def num(key: str) -> int | None:
        v = data.get(key)
        if v is None or v == 0:
            return None
        if isinstance(v, bool) or not isinstance(v, int) or not 0 < v <= 2880:
            raise ValueError(f"{key} out of range")
        return v

    def year(key: str) -> int | None:
        v = data.get(key)
        if v is None or v == 0:
            return None
        if isinstance(v, bool) or not isinstance(v, int) or not 1880 <= v <= 2100:
            raise ValueError(f"{key} out of range")
        return v

    def words(key: str, allowed: tuple | None = None) -> list[str]:
        v = data.get(key) or []
        if not isinstance(v, list) or len(v) > 10 or not all(isinstance(x, str) and len(x) <= 40 for x in v):
            raise ValueError(f"bad {key}")
        if allowed and any(x not in allowed for x in v):
            raise ValueError(f"bad {key}")
        return v

    text = data.get("text") or ""
    if not isinstance(text, str) or len(text) > 200:
        raise ValueError("bad text")
    scope = data.get("scope") or "all"
    audience = data.get("audience") or "any"
    if scope not in ("all", "guide", "library") or audience not in ("any", "family", "kids"):
        raise ValueError("bad scope or audience")
    return Filters(text=text, scope=scope, on_now=data.get("on_now") is True, within_minutes=num("within_minutes"),
                   max_minutes=num("max_minutes"), audience=audience,
                   kinds=words("kinds", ("movie", "episode", "sports", "show")), genres=words("genres"),
                   year_from=year("year_from"), year_to=year("year_to"))


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[\w']+", text.lower()) if w not in STOPWORDS]


def enough_words(text: str, hay: str) -> bool:
    """For the any-word fallback: a result must contain all but one of the search words, each at the
    start of a word. One shared word isn't enough ("green bay packers" must not find "Big City Greens")."""
    words = _words(text)
    hay = hay.lower()
    hits = sum(1 for w in words if re.search(rf"\b{re.escape(w)}", hay))
    return hits >= max(1, len(words) - 1)


def fts_query(text: str, any_word: bool = False) -> str:
    words = _words(text)
    if not words:
        return ""
    return (" OR " if any_word else " ").join(f'"{w.replace(chr(34), "")}"*' for w in words)


def basic_filters(text: str) -> Filters:
    """Cheap keyword reading of a query, used when no AI provider is configured."""
    low = text.lower()
    f = Filters(text=text)
    if re.search(r"\b(now|right now|on now|live)\b", low):
        f.on_now = True
    if re.search(r"\btonight\b", low):
        f.within_minutes = 8 * 60
    if re.search(r"\b(movie|movies|film|films)\b", low):
        f.kinds.append("movie")
    if re.search(r"\b(sports?|game|games|match)\b", low):
        f.kinds.append("sports")
    if re.search(r"\b(kids?|children|cartoons?)\b", low):
        f.audience = "kids"
    # Words that became filters shouldn't also be searched for ("sports" would match "Sky Sports").
    f.text = re.sub(r"\b(sports?|movies?|films?|match|tonight|kids?|children|cartoons?)\b", " ", text, flags=re.I).strip()
    return take_decade(f)


def _channel_rank(vcn: str, title: str) -> tuple:
    num = int(vcn) if vcn.isdigit() else 99999
    return (num >= GAME_SLOT_MIN_VCN, "antenna" not in title.lower(), num)


def search_guide(conn: sqlite3.Connection, f: Filters, now: int | None = None) -> list[dict]:
    now = now or int(time.time())
    horizon = now + (f.within_minutes * 60 if f.within_minutes else 48 * 3600)
    where = ["a.ends > ?", "a.begins < ?"]
    args: list = [now, now + 60 if f.on_now else horizon]
    if f.kinds:
        guide_kinds = [k for k in f.kinds if k in ("movie", "episode", "sports", "other")]
        if guide_kinds:
            where.append(f"a.kind IN ({','.join('?' * len(guide_kinds))})")
            args += guide_kinds
    audience = f.audience
    for g in f.genres:
        if g.lower() in KIDS_GENRES:
            audience = audience if audience != "any" else ("family" if g.lower() == "family" else "kids")
            continue
        where.append("(a.summary LIKE ? OR a.title LIKE ?)")
        args += [f"%{g}%", f"%{g}%"]
    if f.max_minutes:
        where.append("a.ends - a.begins <= ?")
        args.append(f.max_minutes * 60)
    if f.year_from:
        where.append("a.year >= ?")
        args.append(f.year_from)
    if f.year_to:
        where.append("a.year <= ?")
        args.append(f.year_to)
    if audience in ("kids", "family"):
        pattern = KIDS_CHANNEL_RE if audience == "kids" else FAMILY_CHANNEL_RE
        ids = [r["id"] for r in conn.execute("SELECT id, title FROM channels") if pattern.search(r["title"])]
        where.append("a.kind != 'sports'")
        if ids:
            where.append(f"a.channel_id IN ({','.join('?' * len(ids))})")
            args += ids

    sql = """SELECT a.*, c.vcn, c.title AS ch_title, c.thumb AS ch_thumb, {rank} AS rank,
                    g.name AS g_name, g.short_name AS g_short, g.state AS g_state, g.detail AS g_detail,
                    g.home AS g_home, g.away AS g_away, g.home_score AS g_hs, g.away_score AS g_as,
                    g.league AS g_league
             FROM {src} JOIN channels c ON c.id = a.channel_id
             LEFT JOIN games g ON g.id = a.game_id
             WHERE {where} ORDER BY rank, a.begins LIMIT 400"""
    rows: list[sqlite3.Row] = []
    for any_word in (False, True):
        q = fts_query(f.text, any_word)
        if q:
            rows = conn.execute(sql.format(
                rank="bm25(airings_fts, 10.0, 4.0, 1.0, 2.0, 8.0)",
                src="airings_fts JOIN airings a ON a.id = airings_fts.rowid",
                where=" AND ".join(["airings_fts MATCH ?"] + where)), [q] + args).fetchall()
            if any_word:
                rows = [r for r in rows if enough_words(f.text, " ".join(str(r[k] or "") for k in (
                    "title", "subtitle", "summary", "ch_title", "g_name", "g_home", "g_away")))]
        else:
            rows = conn.execute(sql.format(rank="0", src="airings a", where=" AND ".join(where)),
                                args).fetchall()
        if rows or not q:
            break
    return _group(rows, now)[: f.limit]


def _group(rows: list[sqlite3.Row], now: int) -> list[dict]:
    groups: dict[tuple, dict] = {}
    for r in rows:
        key = ("game", r["game_id"]) if r["game_id"] else (r["title"].lower(), r["subtitle"].lower(), r["begins"])
        item = groups.get(key)
        if not item:
            item = groups[key] = {
                "type": "airing", "title": r["title"], "subtitle": r["subtitle"], "summary": r["summary"],
                "kind": r["kind"], "begins": r["begins"], "ends": r["ends"],
                "on_now": r["begins"] <= now < r["ends"], "rank": r["rank"], "channels": [], "game": None,
            }
            if r["game_id"]:
                item["game"] = {"id": r["game_id"], "name": r["g_name"], "short": r["g_short"], "state": r["g_state"],
                                "detail": r["g_detail"], "home": r["g_home"], "away": r["g_away"],
                                "home_score": r["g_hs"], "away_score": r["g_as"],
                                "league": r["g_league"].split("/")[-1]}
        if all(c["vcn"] != r["vcn"] for c in item["channels"]):
            item["channels"].append({"vcn": r["vcn"], "title": r["ch_title"], "thumb": r["ch_thumb"]})
    out = list(groups.values())
    for item in out:
        item["channels"].sort(key=lambda c: _channel_rank(c["vcn"], c["title"]))
    out.sort(key=lambda i: (not i["on_now"], i["rank"], i["begins"]))
    return out


def search_library(conn: sqlite3.Connection, f: Filters) -> list[dict]:
    kinds = [k for k in f.kinds if k in ("movie", "show")]
    if "episode" in f.kinds and "show" not in kinds:
        kinds.append("show")
    where, args = [], []
    if kinds:
        where.append(f"l.kind IN ({','.join('?' * len(kinds))})")
        args += kinds
    for g in f.genres:
        where.append("l.genres LIKE ?")
        args.append(f"%{g}%")
    if f.max_minutes:
        where.append("(l.kind = 'show' OR l.duration <= ?)")
        args.append(f.max_minutes * 60000)
    if f.year_from:
        where.append("l.year >= ?")
        args.append(f.year_from)
    if f.year_to:
        where.append("l.year <= ?")
        args.append(f.year_to)
    if f.audience in ("kids", "family"):
        allowed = KIDS_RATINGS if f.audience == "kids" else FAMILY_RATINGS
        where.append(f"l.content_rating IN ({','.join('?' * len(allowed))})")
        args += list(allowed)
    rows: list[sqlite3.Row] = []
    for any_word in (False, True):
        q = fts_query(f.text, any_word)
        if not q:
            break
        rows = conn.execute(
            "SELECT l.*, bm25(library_fts, 10.0, 1.0, 2.0, 3.0) AS rank FROM library_fts "
            "JOIN library l ON l.rowid = library_fts.rowid WHERE "
            + " AND ".join(["library_fts MATCH ?"] + where) + " ORDER BY rank LIMIT ?",
            [q] + args + [f.limit]).fetchall()
        if any_word:
            rows = [r for r in rows if enough_words(f.text, " ".join(str(r[k] or "") for k in (
                "title", "summary", "genres", "people")))]
        if rows:
            break
    if not rows and not fts_query(f.text) and where:
        rows = conn.execute("SELECT l.*, 0 AS rank FROM library l WHERE " + " AND ".join(where)
                            + " ORDER BY random() LIMIT ?", args + [f.limit]).fetchall()
    return [library_item(r) for r in rows]


def library_item(r: sqlite3.Row) -> dict:
    return {"type": "library", "rating_key": r["rating_key"], "kind": r["kind"], "title": r["title"],
            "year": r["year"], "summary": r["summary"], "genres": r["genres"], "thumb": r["thumb"],
            "section": r["section"], "duration": r["duration"], "content_rating": r["content_rating"],
            "added_at": r["added_at"], "watched": bool(r["watched"]), "leaf_count": r["leaf_count"],
            "viewed_leaf_count": r["viewed_leaf_count"]}


def sports_board(conn: sqlite3.Connection, now: int | None = None, hours: int = 4) -> list[dict]:
    """Games in progress or starting soon, each with the channels carrying it."""
    now = now or int(time.time())
    return _games(conn, now, hours, "g.state = 'in' OR (g.state = 'pre' AND g.starts < ?)",
                  [now + hours * 3600])


def search_games(conn: sqlite3.Connection, f: Filters, now: int | None = None) -> list[dict]:
    """Today's games whose teams match the query, finished ones included, so a team name answers
    with the final score after the game is over."""
    words = [w for w in re.findall(r"[\w']+", f.text.lower()) if w not in STOPWORDS and len(w) > 2]
    if not words:
        return []
    clause = " AND ".join("(lower(g.terms) LIKE ? OR lower(g.name) LIKE ?)" for _ in words)
    args = [x for w in words for x in (f"%{w}%", f"%{w}%")]
    return _games(conn, now or int(time.time()), 24, clause, args)


def _games(conn: sqlite3.Connection, now: int, hours: int, where: str, args: list) -> list[dict]:
    rows = conn.execute(
        f"""SELECT g.*, c.vcn, c.title AS ch_title, c.thumb AS ch_thumb FROM games g
            LEFT JOIN airings a ON a.game_id = g.id AND a.ends > ? AND a.begins < ?
            LEFT JOIN channels c ON c.id = a.channel_id
            WHERE {where}
            ORDER BY g.state = 'in' DESC, g.state = 'pre' DESC, g.starts""",
        [now, now + hours * 3600] + args).fetchall()
    games: dict[str, dict] = {}
    for r in rows:
        g = games.setdefault(r["id"], {
            "id": r["id"], "league": r["league"].split("/")[-1], "name": r["name"], "short": r["short_name"],
            "starts": r["starts"], "state": r["state"], "detail": r["detail"], "home": r["home"],
            "away": r["away"], "home_score": r["home_score"], "away_score": r["away_score"],
            "networks": [n for n in r["networks"].split(",") if n], "channels": [],
            "home_logo": r["home_logo"], "away_logo": r["away_logo"], "home_id": r["home_id"], "away_id": r["away_id"]})
        if r["vcn"] and all(c["vcn"] != r["vcn"] for c in g["channels"]):
            g["channels"].append({"vcn": r["vcn"], "title": r["ch_title"], "thumb": r["ch_thumb"]})
    for g in games.values():
        g["channels"].sort(key=lambda c: _channel_rank(c["vcn"], c["title"]))
    return list(games.values())


def run(conn: sqlite3.Connection, f: Filters) -> dict:
    guide = search_guide(conn, f) if f.scope in ("all", "guide") else []
    library = search_library(conn, f) if f.scope in ("all", "library") and not f.on_now else []
    games = search_games(conn, f) if f.scope in ("all", "guide") else []
    return {"games": games, "guide": guide, "library": library}
