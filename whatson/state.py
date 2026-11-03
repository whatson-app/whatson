"""Process-wide objects shared by the API routes."""

from __future__ import annotations

import sqlite3

from . import config


class State:
    settings: config.Settings
    conn: sqlite3.Connection
    plex = None          # sources.plex.PlexClient
    source = None        # sources.base.Source: the server the guide and library come from now
    refresher = None     # ingest.Refresher
    interpreter = None   # ai.Interpreter
    trakt = None         # trakt.Trakt
    http = None          # shared httpx.AsyncClient for fixed public hosts (ESPN, Trakt, plex.tv)
    lan_http = None      # safe_http.client() for addresses typed in Settings (Radarr, Sonarr)
    drivers: dict = {}
    # device id -> (channel id, time) of the last channel WhatsOn tuned there. Plex's Live TV sessions
    # don't say which channel they're on (Jellyfin's do), so now-playing uses this (checked against the title).
    last_tune: dict = {}


state = State()
