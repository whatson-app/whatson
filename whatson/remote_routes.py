"""API for the Remote tab: keys, typing, volume, opening apps, each TV's app list, and direct control
of Jellyfin apps through the Jellyfin server (Settings → Jellyfin)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import apps, db, devices, source_routes, tune
from .arr_routes import _check_url
from .devices.androidtv import NotPaired
from .source_routes import jellyfin
from .sources.jellyfin import Jellyfin, JellyfinError, JellyfinSession
from .state import state

router = APIRouter(prefix="/api")

KEYS = {
    "DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT", "DPAD_CENTER", "BACK", "HOME", "MENU",
    "MEDIA_PLAY_PAUSE", "MEDIA_STOP", "MEDIA_NEXT", "MEDIA_PREVIOUS", "MEDIA_REWIND", "MEDIA_FAST_FORWARD",
    "VOLUME_UP", "VOLUME_DOWN", "VOLUME_MUTE", "POWER", "CHANNEL_UP", "CHANNEL_DOWN", "TV_INPUT",
    "DEL", "ENTER", "SEARCH", "INFO", "GUIDE", "CAPTIONS", "SETTINGS",
}
DIRECTIONS = {"SHORT", "START_LONG", "END_LONG"}


def _tv(device_id: int) -> tuple[dict, object]:
    d = devices.get_device(state.conn, device_id)
    if not d:
        raise HTTPException(404, "No such TV")
    drv = state.drivers.get(d["kind"])
    if not drv:
        raise HTTPException(400, f"{d['kind']} TVs aren't supported yet")
    return d, drv


async def _do(device_id: int, d: dict, coro):
    try:
        return await coro
    except NotPaired as exc:
        devices.mark_paired(state.conn, device_id, False)
        raise HTTPException(409, {"code": "not_paired", "message": str(exc)}) from exc
    except (OSError, asyncio.TimeoutError, ConnectionError) as exc:
        raise HTTPException(502, f"Couldn't reach {d['name']} ({type(exc).__name__})") from exc
    except Exception as exc:
        if type(exc).__name__ in ("CannotConnect", "ConnectionClosed"):
            raise HTTPException(502, f"Couldn't reach {d['name']}") from exc
        raise


# --- Jellyfin connection -------------------------------------------------------------------------

def _jf_public() -> dict:
    return {"url": db.get_meta(state.conn, "jellyfin.url"), "configured": jellyfin() is not None,
            "server_name": db.get_meta(state.conn, "jellyfin.name"),
            "user_id": db.get_meta(state.conn, "jellyfin.user_id")}


def _forget_server_links() -> None:
    """A user and TV links belong to one server."""
    for k in ("user_id", "user_name"):
        db.set_meta(state.conn, f"jellyfin.{k}", "")
    state.conn.execute("UPDATE devices SET jellyfin_device = ''")


def _key_for(url: str, typed: str) -> str:
    """The typed key, else the saved one, but only for the address it was saved with: a saved key
    must never be sent to a server someone has just typed in."""
    if typed.strip():
        return typed.strip()
    return db.get_meta(state.conn, "jellyfin.key") if url == db.get_meta(state.conn, "jellyfin.url") else ""


class JellyfinIn(BaseModel):
    url: str
    key: str = ""


@router.get("/settings/jellyfin")
async def jellyfin_settings():
    return _jf_public()


@router.put("/settings/jellyfin")
async def save_jellyfin(body: JellyfinIn):
    url = body.url.strip().rstrip("/")
    key = _key_for(url, body.key)
    if not url or not key:
        raise HTTPException(400, "Enter the server address and an API key")
    await _check_url(url)
    try:
        info = await Jellyfin(url, key, state.lan_http).info()
    except JellyfinError as exc:
        raise HTTPException(400, str(exc)) from exc
    different = info["id"] != db.get_meta(state.conn, "jellyfin.server_id")
    if different:
        _forget_server_links()
    db.set_meta(state.conn, "jellyfin.url", url)
    db.set_meta(state.conn, "jellyfin.key", key)
    db.set_meta(state.conn, "jellyfin.name", info["name"])
    db.set_meta(state.conn, "jellyfin.server_id", info["id"])
    if source_routes.chosen() == "jellyfin":
        # Without a user the new server can't be the source yet, so go back to Plex until one is chosen.
        if different:
            source_routes.switch("plex")
        else:
            source_routes.apply()
    return _jf_public()


@router.delete("/settings/jellyfin")
async def forget_jellyfin():
    was_source = source_routes.chosen() == "jellyfin"
    for k in ("url", "key", "name", "server_id"):
        db.set_meta(state.conn, f"jellyfin.{k}", "")
    _forget_server_links()
    if was_source:
        source_routes.switch("plex")
    return _jf_public()


async def _jf_call(call):
    try:
        return await call
    except JellyfinError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.get("/settings/jellyfin/users")
async def jellyfin_users():
    jf = jellyfin()
    if not jf:
        raise HTTPException(400, "Connect your Jellyfin server first")
    return await _jf_call(jf.users())


class JellyfinUserIn(BaseModel):
    user_id: str


@router.put("/settings/jellyfin/user")
async def set_jellyfin_user(body: JellyfinUserIn):
    jf = jellyfin()
    if not jf:
        raise HTTPException(400, "Connect your Jellyfin server first")
    user = next((u for u in await _jf_call(jf.users()) if u["id"] == body.user_id), None)
    if not user:
        raise HTTPException(400, "That user isn't on this server")
    db.set_meta(state.conn, "jellyfin.user_id", user["id"])
    db.set_meta(state.conn, "jellyfin.user_name", user["name"])
    if source_routes.chosen() == "jellyfin":
        source_routes.apply()   # watched status and up next are per user
    return _jf_public()


@router.get("/settings/jellyfin/devices")
async def jellyfin_devices():
    """Plezy installs signed in to this server, to link to TVs. Empty until Plezy has signed in on one."""
    jf = jellyfin()
    return await _jf_call(jf.plezy_devices()) if jf else []


class TVLinkIn(BaseModel):
    device: str = Field(default="", max_length=100)


@router.put("/devices/{device_id}/jellyfin")
async def link_jellyfin_device(device_id: int, body: TVLinkIn):
    """Which Plezy on Jellyfin is this TV. Needed when the names differ, since the server may not see the TV's address."""
    _tv(device_id)
    state.conn.execute("UPDATE devices SET jellyfin_device = ? WHERE id = ?", (body.device, device_id))
    return devices.get_device(state.conn, device_id)


async def _jf_sessions(d: dict) -> list[JellyfinSession]:
    jf = jellyfin()
    if not jf:
        return []
    try:
        found = await jf.sessions()
    except JellyfinError:
        return []
    return [s for s in found if tune.is_on_tv(d, s.address, s.device, s.device_id)]


# --- Remote --------------------------------------------------------------------------------------

@router.get("/remote/{device_id}")
async def remote_state(device_id: int):
    """What the Remote tab needs: power, app in front, volume, this TV's apps, controllable apps."""
    d, drv = _tv(device_id)
    st = await drv.live(d["host"])
    if st.current_app:
        apps.note_seen(state.conn, device_id, st.current_app, tune.IDLE_APPS)
    jf = await _jf_sessions(d)
    return {
        "reachable": st.reachable, "paired": not (st.reachable and st.error), "error": st.error,
        "is_on": st.is_on, "current_app": st.current_app,
        "app_name": "Home screen" if st.current_app in tune.IDLE_APPS else apps.name_of(st.current_app),
        "volume": st.volume, "apps": apps.for_tv(state.conn, device_id),
        "controls": [{"id": f"jellyfin:{s.id}", "label": s.client or "Jellyfin", "controllable": s.controllable,
                      "title": s.title, "subtitle": s.subtitle, "paused": s.paused,
                      "position": s.position, "duration": s.duration} for s in jf],
    }


class KeyIn(BaseModel):
    key: str
    direction: str = "SHORT"


@router.post("/remote/{device_id}/key")
async def remote_key(device_id: int, body: KeyIn):
    key, direction = body.key.upper().removeprefix("KEYCODE_"), body.direction.upper()
    if key not in KEYS or direction not in DIRECTIONS:
        raise HTTPException(400, "Unknown key")
    d, drv = _tv(device_id)
    await _do(device_id, d, drv.send_key(d["host"], key, direction))
    return {"ok": True}


class TextIn(BaseModel):
    text: str = Field(max_length=200)


@router.post("/remote/{device_id}/text")
async def remote_text(device_id: int, body: TextIn):
    if not body.text:
        raise HTTPException(400, "Nothing to type")
    d, drv = _tv(device_id)
    await _do(device_id, d, drv.send_text(d["host"], body.text))
    return {"ok": True}


class LaunchIn(BaseModel):
    app: str      # catalogue id, or a package name seen on this TV


@router.post("/remote/{device_id}/launch")
async def remote_launch(device_id: int, body: LaunchIn):
    """Open an app, then report whether it actually came to the front."""
    d, drv = _tv(device_id)
    a = apps.BY_ID.get(body.app)
    if not a:
        known = {r["package"] for r in state.conn.execute("SELECT package FROM tv_apps WHERE device_id = ?", (device_id,))}
        if body.app not in known:
            raise HTTPException(400, "Unknown app")
        a = apps.App(body.app, apps.name_of(body.app), body.app)
    await _do(device_id, d, drv.open_link(d["host"], a.link or a.package))
    opened = False
    for _ in range(10):   # cold starts can take a few seconds
        await asyncio.sleep(0.6)
        st = await drv.live(d["host"])
        if st.current_app == a.package:
            opened = True
            break
    if opened:
        apps.note_seen(state.conn, device_id, a.package, tune.IDLE_APPS)
    return {"opened": opened, "name": a.name, "by_link": bool(a.link)}


class PickIn(BaseModel):
    package: str
    shown: bool


@router.put("/remote/{device_id}/apps")
async def remote_pick(device_id: int, body: PickIn):
    _tv(device_id)
    if body.package not in apps.BY_PACKAGE and not state.conn.execute(
            "SELECT 1 FROM tv_apps WHERE device_id = ? AND package = ?", (device_id, body.package)).fetchone():
        raise HTTPException(400, "Unknown app")
    apps.set_picked(state.conn, device_id, body.package, body.shown)
    return apps.for_tv(state.conn, device_id)


class ControlIn(BaseModel):
    target: str           # "jellyfin:<session id>"
    command: str          # PlayPause, Stop, NextTrack, PreviousTrack, Seek
    position: int | None = None   # ms, for Seek
    delta: int | None = None      # ms, relative Seek (e.g. -10000)


@router.post("/remote/{device_id}/control")
async def remote_control(device_id: int, body: ControlIn):
    d, _ = _tv(device_id)
    kind, _, sid = body.target.partition(":")
    jf = jellyfin()
    if kind != "jellyfin" or not jf:
        raise HTTPException(400, "Nothing to control")
    session = next((s for s in await _jf_sessions(d) if s.id == sid), None)
    if not session:
        raise HTTPException(404, "That app isn't playing on this TV any more")
    if not session.controllable:
        raise HTTPException(409, f"{session.client} doesn't allow remote control")
    position = body.position
    if body.command == "Seek" and body.delta is not None:
        position = max(0, session.position + body.delta)
    try:
        await jf.command(sid, body.command, position)
    except JellyfinError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"ok": True}
