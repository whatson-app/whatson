"""A Plex Home user for each TV (ADR 0025). Choosing a TV makes watched status and Up Next follow its user,
and links tell Plezy to play as that user.

The owner's token keeps the guide, the library list and the busy check. A user's token only reads that
user's own data: it's refused on /status/sessions."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import db, devices, plex_auth
from .plex_auth import PlexAuthError, PlexTV
from .sources.plex import PlexClient
from .state import state

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

OWNER = "plex.owner_uuid"


def _tv() -> PlexTV:
    return PlexTV(state.conn, state.http, state.settings.client_name)


def profile_for(d: dict) -> str:
    """What to name in this TV's links. Plezy's profiles here are Plex's, so only while Plex is the source."""
    return d.get("plex_user", "") if state.source is state.plex else ""


def viewer(device_id: int) -> str:
    """The Home user to read as for this TV: empty for no TV, no user, or the owner, whose token is in use already."""
    d = devices.get_device(state.conn, device_id) if device_id else None
    user = profile_for(d) if d else ""
    return "" if user == db.get_meta(state.conn, OWNER) else user


async def _token(user: str, fresh: bool = False) -> str:
    pc = plex_auth.load(state.conn)
    token = "" if fresh else plex_auth.saved_user_token(state.conn, user, pc.url)
    if not token:
        server_id = await state.plex.machine_identifier()
        token = await _tv().user_server_token(pc.token, user, server_id)
        plex_auth.save_user_token(state.conn, user, pc.url, token)
    return token


async def read_as(user: str, read: Callable[[PlexClient], Awaitable[Any]]) -> Any:
    """Read as a Home user. Plex gives no expiry date for these tokens, so a refused one is replaced once."""
    try:
        return await read(state.plex.as_user(await _token(user)))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 401:
            raise
    return await read(state.plex.as_user(await _token(user, fresh=True)))


async def item_as(device_id: int, item_id: str) -> dict | None:
    """A title as this TV's user sees it. The library is listed with the owner's token, so it can include
    titles Plex hides from a restricted user: those come from the owner's view, marked as hidden."""
    user = viewer(device_id)
    if not user:
        return await state.source.item(item_id)
    hidden = False
    try:
        out = await read_as(user, lambda s: s.item(item_id))
        hidden = out is None
    except httpx.HTTPStatusError as exc:
        out, hidden = None, exc.response.status_code in (401, 403, 404)
    except (PlexAuthError, httpx.HTTPError) as exc:
        log.warning("Couldn't read a title as this TV's Plex user: %s", type(exc).__name__)
        out = None
    if out is not None:
        return out
    out = await state.source.item(item_id)
    if out and hidden:
        out["hidden_from"] = devices.get_device(state.conn, device_id)["plex_user_name"]
    return out


async def episodes_as(device_id: int, season_id: str) -> list[dict]:
    user = viewer(device_id)
    if user:
        try:
            return await read_as(user, lambda s: s.episodes(season_id))
        except (PlexAuthError, httpx.HTTPError) as exc:
            log.warning("Couldn't read episodes as this TV's Plex user: %s", type(exc).__name__)
    return await state.source.episodes(season_id)


async def up_next_as(user: str) -> list[dict]:
    try:
        return await read_as(user, lambda s: s.up_next())
    except (PlexAuthError, httpx.HTTPError) as exc:
        log.warning("Couldn't read Up Next for this TV's Plex user: %s", type(exc).__name__)
        return []


# --- Watched status, saved per user because the library list is the owner's -----------------------------

def watched_keys(user: str) -> set[str]:
    return {r["rating_key"] for r in state.conn.execute(
        "SELECT rating_key FROM user_watched WHERE user = ? AND watched = 1", (user,))}


def apply_watched(user: str, items: list[dict]) -> list[dict]:
    """Replace the owner's watched status on these library items with this user's."""
    rows = {r["rating_key"]: r for r in state.conn.execute(
        "SELECT rating_key, watched, viewed_leaf_count FROM user_watched WHERE user = ?", (user,))}
    for it in items:
        r = rows.get(it["rating_key"])
        it["watched"] = bool(r and r["watched"])
        if "viewed_leaf_count" in it:
            it["viewed_leaf_count"] = r["viewed_leaf_count"] if r else 0
    return items


async def refresh_watched(user: str) -> None:
    items = await read_as(user, lambda s: s.library())
    conn = state.conn
    conn.execute("BEGIN")
    try:
        conn.execute("DELETE FROM user_watched WHERE user = ?", (user,))
        conn.executemany("INSERT INTO user_watched (user, rating_key, watched, viewed_leaf_count) VALUES (?, ?, ?, ?)",
                         [(user, it.rating_key, int(it.watched), it.viewed_leaf_count) for it in items])
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    log.info("watched status: %d items for one Plex user", len(items))


async def _refresh_quietly(user: str) -> None:
    try:
        await refresh_watched(user)
    except (PlexAuthError, httpx.HTTPError) as exc:
        log.warning("Couldn't load a Plex user's watched status: %s", type(exc).__name__)


async def refresh_all() -> None:
    """Only users on a TV, and only while Plex is the source."""
    if state.source is not state.plex or not state.plex.configured:
        return
    owner = db.get_meta(state.conn, OWNER)
    users = {r["plex_user"] for r in state.conn.execute("SELECT plex_user FROM devices WHERE plex_user != ''")} - {owner}
    marks = ",".join("?" * len(users))
    state.conn.execute(f"DELETE FROM user_watched WHERE user NOT IN ({marks})", tuple(users))
    for user in users:
        await _refresh_quietly(user)


# --- Settings → TVs -------------------------------------------------------------------------------------

async def _home_users() -> list[dict]:
    users = await _tv().home_users(plex_auth.load(state.conn).token)
    db.set_meta(state.conn, OWNER, next((u["uuid"] for u in users if u["owner"]), ""))
    return users


@router.get("/settings/plex/users")
async def plex_users():
    """Empty while Plex isn't the source, or for an account with no Plex Home, such as a friend's shared server."""
    if state.source is not state.plex or not state.plex.configured:
        return []
    try:
        return await _home_users()
    except PlexAuthError as exc:
        log.info("No Plex Home users to list: %s", exc)
        return []


class PlexUserIn(BaseModel):
    user: str = Field(default="", max_length=100)


@router.put("/devices/{device_id}/plex-user")
async def set_plex_user(device_id: int, body: PlexUserIn):
    if not devices.get_device(state.conn, device_id):
        raise HTTPException(404, "No such TV")
    name = ""
    if body.user:
        if state.source is not state.plex:
            raise HTTPException(400, "This only works while Plex is the server in use.")
        try:
            users = await _home_users()
        except PlexAuthError as exc:
            raise HTTPException(502, f"Couldn't get your Plex Home users. Try again in a moment. ({exc})") from exc
        user = next((u for u in users if u["uuid"] == body.user), None)
        if not user:
            raise HTTPException(400, "That user isn't in this Plex Home.")
        if user["protected"]:
            raise HTTPException(400, f"{user['name']} has a Plex PIN, and WhatsOn can't use PIN-protected users. "
                                     "Remove the PIN in Plex to choose them here.")
        name = user["name"]
        if not user["owner"]:
            try:
                await _token(user["uuid"], fresh=True)
            except (PlexAuthError, httpx.HTTPError) as exc:
                raise HTTPException(502, f"Couldn't set up {name}. Try again in a moment.") from exc
            asyncio.create_task(_refresh_quietly(user["uuid"]))
    state.conn.execute("UPDATE devices SET plex_user = ?, plex_user_name = ? WHERE id = ?", (body.user, name, device_id))
    return devices.get_device(state.conn, device_id)
