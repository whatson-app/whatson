"""Settings → Plex: Sign in with Plex (pick a server), paste a token, or use PLEX_URL/PLEX_TOKEN."""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from . import db, plex_auth
from .plex_auth import PlexAuthError, PlexTV
from .state import state

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings/plex")

# Sign-ins in progress: pin id -> {"started", "jwt", "servers"}. Memory only, since they're short-lived.
_pending: dict[int, dict] = {}


def _tv() -> PlexTV:
    return PlexTV(state.conn, state.http, state.settings.client_name)


def apply() -> None:
    """Point the Plex client at whatever is saved now, and reload the guide and library."""
    pc = plex_auth.load(state.conn)
    state.plex.configure(pc.url, pc.token)
    if state.source is state.plex:
        state.refresher.kick()


async def _check(url: str) -> None:
    from .arr_routes import _check_url  # same 400 errors as the other address fields
    await _check_url(url)


@router.get("")
async def plex_settings():
    return plex_auth.public(state.conn, plex_auth.load(state.conn))


@router.post("/signin")
async def signin_start(request: Request):
    for pid in [p for p, v in _pending.items() if time.time() - v["started"] > 1800]:
        del _pending[pid]
    forward = str(request.base_url).rstrip("/") + "/static/signed-in.html"
    try:
        pin = await _tv().start_pin(forward)
    except PlexAuthError as exc:
        raise HTTPException(502, str(exc)) from exc
    _pending[pin["id"]] = {"started": time.time(), "jwt": "", "servers": []}
    return {"pin_id": pin["id"], "auth_url": pin["auth_url"]}


@router.get("/signin/{pin_id}")
async def signin_poll(pin_id: int):
    """Pending until the person approves on plex.tv; then the servers they can pick from."""
    p = _pending.get(pin_id)
    if not p:
        raise HTTPException(404, "That sign-in expired; start again")
    tv = _tv()
    try:
        if not p["jwt"]:
            jwt = await tv.check_pin(pin_id)
            if not jwt:
                return {"status": "pending"}
            p["jwt"], p["account"] = jwt, await tv.account(jwt)
            p["servers"] = await tv.servers(jwt)
    except PlexAuthError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"status": "signed_in", "account": p["account"],
            "servers": [{k: s[k] for k in ("id", "name", "owned", "presence")} for s in p["servers"]]}


class ServerIn(BaseModel):
    pin_id: int
    server_id: str


@router.post("/server")
async def signin_pick(body: ServerIn):
    p = _pending.get(body.pin_id)
    server = next((s for s in (p or {}).get("servers", []) if s["id"] == body.server_id), None)
    if not p or not p["jwt"] or not server:
        raise HTTPException(404, "That sign-in expired; start again")
    tv = _tv()
    try:
        token = await tv.server_token(p["jwt"], server["id"])
    except PlexAuthError as exc:
        raise HTTPException(502, str(exc)) from exc
    errors = []
    for url in server["connections"]:
        try:
            await _check(url)
            await plex_auth.reachable(state.lan_http, url, token, server["id"])
        except (PlexAuthError, HTTPException) as exc:
            errors.append(str(getattr(exc, "detail", exc)))
            continue
        plex_auth.save_server(state.conn, "signin", url, token, server["name"], server["id"])
        db.set_meta(state.conn, "plex.jwt", p["jwt"])
        db.set_meta(state.conn, "plex.jwt_at", str(int(time.time())))
        db.set_meta(state.conn, "plex.account", p.get("account", ""))
        del _pending[body.pin_id]
        apply()
        return plex_auth.public(state.conn, plex_auth.load(state.conn))
    raise HTTPException(502, f"Couldn't reach {server['name']} from WhatsOn. Tried {len(server['connections'])} "
                             f"address(es): {'; '.join(dict.fromkeys(errors))[:300]}")


class ManualIn(BaseModel):
    url: str
    token: str


@router.put("/manual")
async def manual(body: ManualIn):
    """A pasted token (Plex Web → Get Info → View XML → X-Plex-Token) plus the server's address."""
    url, token = body.url.strip().rstrip("/"), body.token.strip()
    if not url or not token:
        raise HTTPException(400, "Enter the server address and the token")
    await _check(url)
    try:
        mid = await plex_auth.reachable(state.lan_http, url, token)
    except PlexAuthError as exc:
        raise HTTPException(400, str(exc)) from exc
    plex_auth.forget(state.conn)
    plex_auth.save_server(state.conn, "token", url, token, server_id=mid)
    apply()
    return plex_auth.public(state.conn, plex_auth.load(state.conn))


@router.delete("")
async def disconnect():
    """Forget the sign-in or pasted token. PLEX_URL/PLEX_TOKEN take over again if they're set."""
    plex_auth.forget(state.conn)
    apply()
    return plex_auth.public(state.conn, plex_auth.load(state.conn))


async def renew_once() -> None:
    conn = state.conn
    if db.get_meta(conn, "plex.source") != "signin":
        return
    if time.time() - int(db.get_meta(conn, "plex.jwt_at", "0") or 0) < plex_auth.RENEW_AFTER:
        return
    tv = _tv()
    jwt = await tv.renew()
    db.set_meta(conn, "plex.jwt", jwt)
    db.set_meta(conn, "plex.jwt_at", str(int(time.time())))
    # The server token can change too; keep the one plex.tv hands out now.
    token = await tv.server_token(jwt, db.get_meta(conn, "plex.server_id"))
    if token != db.get_meta(conn, "plex.server_token"):
        db.set_meta(conn, "plex.server_token", token)
        state.plex.configure(db.get_meta(conn, "plex.url"), token)
    log.info("Plex sign-in renewed")


async def renew_loop() -> None:
    while True:
        try:
            await renew_once()
        except Exception as exc:
            log.warning("Renewing the Plex sign-in failed (%s); trying again in an hour", exc)
        await asyncio.sleep(3600)
