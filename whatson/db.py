"""SQLite storage. Guide, library and games are rebuilt wholesale on each refresh;
devices are the only long-lived rows."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
    id        TEXT PRIMARY KEY,     -- the server's channel id
    vcn       TEXT NOT NULL,        -- channel number shown to people and used to tune
    title     TEXT NOT NULL,
    callsign  TEXT NOT NULL DEFAULT '',
    thumb     TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS airings (
    id         INTEGER PRIMARY KEY,
    channel_id TEXT NOT NULL,
    title      TEXT NOT NULL,
    subtitle   TEXT NOT NULL DEFAULT '',
    summary    TEXT NOT NULL DEFAULT '',
    kind       TEXT NOT NULL DEFAULT '',   -- movie | episode | sports | other
    begins     INTEGER NOT NULL,
    ends       INTEGER NOT NULL,
    year       INTEGER,
    game_id    TEXT                         -- set when matched to an ESPN game
);
CREATE INDEX IF NOT EXISTS airings_time ON airings (begins, ends);

CREATE VIRTUAL TABLE IF NOT EXISTS airings_fts USING fts5 (
    title, subtitle, summary, channel, extra, tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TABLE IF NOT EXISTS library (
    rating_key TEXT PRIMARY KEY,
    kind       TEXT NOT NULL,           -- movie | show
    title      TEXT NOT NULL,
    year       INTEGER,
    summary    TEXT NOT NULL DEFAULT '',
    genres     TEXT NOT NULL DEFAULT '',
    people     TEXT NOT NULL DEFAULT '',
    thumb      TEXT NOT NULL DEFAULT '',
    section    TEXT NOT NULL DEFAULT '',
    added_at   INTEGER NOT NULL DEFAULT 0,
    duration   INTEGER NOT NULL DEFAULT 0,     -- ms; per episode for shows
    content_rating TEXT NOT NULL DEFAULT '',
    audience_rating REAL,
    watched    INTEGER NOT NULL DEFAULT 0,     -- movie seen / show fully seen
    leaf_count INTEGER NOT NULL DEFAULT 0,
    viewed_leaf_count INTEGER NOT NULL DEFAULT 0,
    guids      TEXT NOT NULL DEFAULT ''        -- "imdb:tt0115082 tmdb:155 tvdb:72389", for Trakt matching
);
CREATE INDEX IF NOT EXISTS library_kind ON library (kind, added_at);

CREATE VIRTUAL TABLE IF NOT EXISTS library_fts USING fts5 (
    title, summary, genres, people, tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TABLE IF NOT EXISTS games (
    id         TEXT PRIMARY KEY,
    league     TEXT NOT NULL,
    name       TEXT NOT NULL,
    short_name TEXT NOT NULL,
    starts     INTEGER NOT NULL,
    state      TEXT NOT NULL,           -- pre | in | post
    detail     TEXT NOT NULL DEFAULT '',
    home       TEXT NOT NULL,
    away       TEXT NOT NULL,
    home_score TEXT NOT NULL DEFAULT '',
    away_score TEXT NOT NULL DEFAULT '',
    networks   TEXT NOT NULL DEFAULT '', -- comma-separated broadcast names
    terms      TEXT NOT NULL DEFAULT '', -- every team name/abbreviation, for search
    home_id    TEXT NOT NULL DEFAULT '',
    away_id    TEXT NOT NULL DEFAULT '',
    home_logo  TEXT NOT NULL DEFAULT '',
    away_logo  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS fav_channels (
    channel_id TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS follows (          -- favorite leagues and teams (shared by the household)
    kind    TEXT NOT NULL,                    -- league | team
    league  TEXT NOT NULL,                    -- ESPN path, e.g. football/nfl
    team_id TEXT NOT NULL DEFAULT '',
    name    TEXT NOT NULL DEFAULT '',
    abbr    TEXT NOT NULL DEFAULT '',
    logo    TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (kind, league, team_id)
);

CREATE TABLE IF NOT EXISTS devices (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL,          -- androidtv (phase 2: roku, firetv, ...)
    host        TEXT NOT NULL UNIQUE,
    plex_player TEXT NOT NULL DEFAULT '', -- Plex/Plezy player name, for the busy check
    paired      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS arr_adds (         -- titles added to Radarr/Sonarr from WhatsOn, for Downloads
    kind     TEXT NOT NULL,                   -- movie | show
    arr_id   INTEGER NOT NULL,                -- the id inside Radarr/Sonarr
    title    TEXT NOT NULL,
    year     INTEGER,
    poster   TEXT NOT NULL DEFAULT '',
    added_at INTEGER NOT NULL,
    PRIMARY KEY (kind, arr_id)
);

CREATE TABLE IF NOT EXISTS tv_apps (          -- apps seen on (or ticked for) each TV, for the Remote tab
    device_id INTEGER NOT NULL,
    package   TEXT NOT NULL,
    seen_at   INTEGER NOT NULL DEFAULT 0,      -- last time it was in front; 0 = never seen
    picked    INTEGER,                        -- 1 shown, 0 hidden, NULL = shown if seen
    PRIMARY KEY (device_id, package)
);

CREATE TABLE IF NOT EXISTS plex_user_tokens ( -- a Plex Home user's server token, and the address it's for
    uuid  TEXT PRIMARY KEY,
    url   TEXT NOT NULL,
    token TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_watched (     -- watched status for Plex Home users other than the owner
    user       TEXT NOT NULL,
    rating_key TEXT NOT NULL,
    watched    INTEGER NOT NULL DEFAULT 0,
    viewed_leaf_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user, rating_key)
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


# Tables rebuilt wholesale on every refresh: when their columns change, drop and recreate them
# (the next refresh refills them) instead of writing migrations.
REBUILT = {"library": ("library", "library_fts"), "games": ("games",)}


def connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    want = {"library": "guids", "games": "home_logo"}
    for table, col in want.items():
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if cols and col not in cols:
            for t in REBUILT[table]:
                conn.execute(f"DROP TABLE IF EXISTS {t}")
    conn.executescript(SCHEMA)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(devices)")}
    for col, ddl in (("model", "TEXT NOT NULL DEFAULT ''"), ("mac", "TEXT NOT NULL DEFAULT ''"),
                     ("jellyfin_device", "TEXT NOT NULL DEFAULT ''"), ("plex_user", "TEXT NOT NULL DEFAULT ''"),
                     ("plex_user_name", "TEXT NOT NULL DEFAULT ''")):
        if col not in cols:
            conn.execute(f"ALTER TABLE devices ADD COLUMN {col} {ddl}")
    if str(path) != ":memory:":
        # The file holds AI API keys once they're saved from the UI.
        for suffix in ("", "-wal", "-shm"):
            p = Path(f"{path}{suffix}")
            if p.exists():
                p.chmod(0o600)
    return conn


def clear_server_data(conn: sqlite3.Connection) -> None:
    """Everything tied to one server's ids, for when WhatsOn moves to another. Favorite channels go too:
    the other server's channels have different ids."""
    for table in ("channels", "airings", "airings_fts", "library", "library_fts", "fav_channels", "user_watched"):
        conn.execute(f"DELETE FROM {table}")
    for key in ("machine_id", "guide_refreshed", "library_refreshed"):
        conn.execute("DELETE FROM meta WHERE key = ?", (key,))


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT INTO meta (key, value) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


def get_meta(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default
