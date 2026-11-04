"""Settings → Server: which server the guide and library come from. One at a time; they aren't merged.

Decisions: ADR 0012."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import db
from .sources.base import Source
from .sources.jellyfin import Jellyfin
from .state import state

router = APIRouter(prefix="/api/settings/source")


def jellyfin() -> Jellyfin | None:
    url, key = db.get_meta(state.conn, "jellyfin.url"), db.get_meta(state.conn, "jellyfin.key")
    return Jellyfin(url, key, state.lan_http, db.get_meta(state.conn, "jellyfin.user_id")) if url and key else None


def chosen() -> str:
    return "jellyfin" if db.get_meta(state.conn, "source") == "jellyfin" else "plex"


def current() -> Source:
    return (jellyfin() if chosen() == "jellyfin" else None) or state.plex


def apply() -> None:
    """Use whatever is saved now, and reload the guide and library from it."""
    state.source = current()
    state.refresher.use(state.source)


def switch(name: str) -> None:
    if name != chosen():
        db.clear_server_data(state.conn)
        state.last_tune.clear()
    db.set_meta(state.conn, "source", name)
    apply()


def public() -> dict:
    jf = jellyfin()
    return {"source": state.source.name, "label": state.source.label, "connected": state.source.configured,
            "plex": state.plex.configured, "jellyfin": jf is not None,
            "jellyfin_user": db.get_meta(state.conn, "jellyfin.user_name")}


@router.get("")
async def source_settings():
    return public()


class SourceIn(BaseModel):
    source: str


@router.put("")
async def set_source(body: SourceIn):
    if body.source not in ("plex", "jellyfin"):
        raise HTTPException(400, "The source is plex or jellyfin")
    if body.source == "jellyfin":
        if not jellyfin():
            raise HTTPException(400, "Connect your Jellyfin server first (Settings → Server → Jellyfin).")
        if not db.get_meta(state.conn, "jellyfin.user_id"):
            raise HTTPException(400, "Choose a Jellyfin user first (Settings → Server → Jellyfin), for watched status and up next.")
    switch(body.source)
    return public()
