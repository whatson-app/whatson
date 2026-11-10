"""HTTP API and web UI.

Decisions: ADR 0002, 0003, 0006."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__, ai_settings, config, db, devices, plex_auth, plex_users, safe_http, search, source_routes, tune
from .ai import Interpreter
from .devices.androidtv import AndroidTVDriver, NotPaired
from .devices.base import PairingError, WrongCode
from .ingest import Refresher
from .sources.jellyfin import JellyfinError
from .sources.plex import PlexClient, PlexNotConnected
from .routes import _cache as route_cache, router as api_router
from .arr_routes import router as arr_router
from .plex_routes import renew_loop, router as plex_router
from .remote_routes import router as remote_router
from .state import state
from .trakt import Trakt

log = logging.getLogger("whatson")
STATIC = Path(__file__).parent / "static"




@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    s = state.settings = config.load()
    state.conn = db.connect(s.db_path)
    pc = plex_auth.load(state.conn)
    state.plex = PlexClient(pc.url, pc.token, s.client_name, http=safe_http.client(timeout=60),
                            client_id=plex_auth.client_id(state.conn))
    state.interpreter = ai_settings.interpreter(ai_settings.load(state.conn))
    state.drivers = {"androidtv": AndroidTVDriver(s.cert_dir, s.client_name)}
    state.http = httpx.AsyncClient(timeout=20)
    state.lan_http = safe_http.client(timeout=20)
    state.source = source_routes.current()
    if not state.source.configured:
        log.warning("No server yet: open WhatsOn → Settings → Server to connect Plex or Jellyfin")
    state.refresher = Refresher(s, state.conn, state.source)
    state.trakt = Trakt(state.conn, state.http)
    tasks = [asyncio.create_task(state.refresher.run_forever()), asyncio.create_task(_trakt_loop()),
             asyncio.create_task(renew_loop()), asyncio.create_task(_drop_idle_loop()),
             asyncio.create_task(_plex_users_loop())]
    yield
    for t in tasks:
        t.cancel()
    await state.plex.close()
    await state.http.aclose()
    await state.lan_http.aclose()


async def _drop_idle_loop():
    """Close Remote-tab connections to TVs nobody has pressed a key on for a while."""
    while True:
        await asyncio.sleep(30)
        for drv in state.drivers.values():
            drv.drop_idle()


async def _plex_users_loop():
    """Each TV's Plex user's watched status, as often as the library itself."""
    while True:
        try:
            await plex_users.refresh_all()
        except Exception:
            log.exception("Refreshing Plex users' watched status failed")
        await asyncio.sleep(state.settings.library_refresh_minutes * 60)


async def _trakt_loop():
    while True:
        try:
            await state.trakt.sync()
        except Exception:
            log.exception("Trakt sync failed")
        await asyncio.sleep(300)


app = FastAPI(title="WhatsOn", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
app.include_router(api_router)
app.include_router(arr_router)
app.include_router(plex_router)
app.include_router(plex_users.router)
app.include_router(remote_router)
app.include_router(source_routes.router)


@app.exception_handler(PlexNotConnected)
async def plex_not_connected(request: Request, exc: PlexNotConnected):
    return JSONResponse({"detail": {"code": "plex_not_connected", "message": str(exc)}}, status_code=503)


@app.exception_handler(JellyfinError)
async def jellyfin_failed(request: Request, exc: JellyfinError):
    return JSONResponse({"detail": {"code": "jellyfin_error", "message": str(exc)}}, status_code=502)

ALLOWED_HOSTS = {h.strip().lower() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()}


def host_allowed(host_header: str) -> bool:
    """IP literals and localhost always; named hosts only when listed in ALLOWED_HOSTS.
    Refusing unknown names defeats DNS rebinding, which needs an attacker-controlled name."""
    host = host_header.rsplit(":", 1)[0].strip("[]").lower() if host_header.count(":") <= 1 \
        else host_header.split("]")[0].strip("[").lower()
    if host in ("localhost", "") or host in ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
        return True
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


@app.middleware("http")
async def guard(request: Request, call_next):
    if not host_allowed(request.headers.get("host", "")):
        return JSONResponse({"detail": "Host not allowed; add it to ALLOWED_HOSTS"}, status_code=403)
    # State-changing calls need a custom header. Browsers only send one cross-site after a CORS
    # preflight, which this app never approves, so other sites can't pair or tune your TVs.
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-whatson") != "1":
        return JSONResponse({"detail": "Missing X-WhatsOn header"}, status_code=403)
    response = await call_next(request)
    # Revalidate the page and its scripts on every load (cheap ETag checks), so an update shows at once.
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/api/status")
async def status():
    c = state.conn
    count = lambda t: c.execute(f"SELECT count(*) FROM {t}").fetchone()[0]  # noqa: E731
    return {"version": __version__, "channels": count("channels"), "airings": count("airings"), "library": count("library"),
            "games": count("games"), "ai": state.interpreter.enabled, "connected": state.source.configured,
            "source": state.source.name, "ai_provider": state.interpreter.provider if state.interpreter.enabled else None,
            "guide_refreshed": int(db.get_meta(c, "guide_refreshed", "0")),
            "library_refreshed": int(db.get_meta(c, "library_refreshed", "0"))}


@app.get("/api/search")
async def do_search(q: str = "", scope: str = "all", ai: bool = True, on_now: bool = False,
                    kind: str = "", filters: str = "", device: int = 0):
    """Search one section. `filters` (JSON) replays edited chips without asking the AI again. When AI read `q`,
    or chips from an AI reading are replayed with `q`, matches for the words as typed come back first in `typed`."""
    note = ""
    if filters:
        try:
            f = search.parse_filters(filters)
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, "Bad filters") from exc
    elif q and ai and state.interpreter.enabled:
        f, note = await state.interpreter.interpret(q)
    else:
        f = search.basic_filters(q)

    def scoped(f: search.Filters) -> search.Filters:
        if scope != "all":
            f.scope = scope
        if kind in ("movie", "show") and f.scope == "library":
            f.kinds = [kind]
        f.on_now = f.on_now or on_now
        return f

    f = scoped(f)
    out = search.run(state.conn, f)
    typed = None
    if q and (filters or note):
        typed = search.split_typed(search.run(state.conn, scoped(search.basic_filters(q))), out)
        if typed:
            typed["text"] = q
    if user := plex_users.viewer(device):
        plex_users.apply_watched(user, out["library"])
        if typed:
            plex_users.apply_watched(user, typed["library"])
    out["typed"] = typed
    out["note"] = note
    out["ai"] = bool(note)
    out["filters"] = search.filters_dict(f)
    return out


@app.get("/api/sports")
async def sports(hours: int = 4):
    return {"games": search.sports_board(state.conn, hours=hours), "now": int(time.time())}


@app.get("/api/thumb")
async def thumb(path: str, width: int = Query(300, ge=50, le=1000)):
    """Proxy library artwork so the server's token never reaches the browser. Each source accepts only
    its exact artwork paths, so this can't be used to reach anything else on the server."""
    r = await state.source.thumb(path, width)
    if r is None or r.status_code != 200:
        raise HTTPException(404)
    return Response(r.content, media_type=r.headers.get("content-type", "image/jpeg"),
                    headers={"Cache-Control": "max-age=86400"})


class AISettingsIn(BaseModel):
    provider: str
    model: str = ""
    base_url: str = ""
    keys: dict[str, str] = {}
    clear_keys: list[str] = []


class AITestIn(BaseModel):
    query: str = "is the lakers game on tonight?"


class PairStartIn(BaseModel):
    host: str
    kind: str = "androidtv"


class PairFinishIn(BaseModel):
    host: str
    code: str
    name: str = ""
    kind: str = "androidtv"


class DevicePatch(BaseModel):
    name: str


class TestIn(BaseModel):
    force: bool = False


class TuneIn(BaseModel):
    device_id: int
    channel: str | None = None
    rating_key: str | None = None
    force: bool = False


# --- AI settings -------------------------------------------------------------------------------

@app.get("/api/settings/ai")
async def get_ai_settings():
    return ai_settings.public(ai_settings.load(state.conn), state.interpreter.enabled)


@app.put("/api/settings/ai")
async def put_ai_settings(body: AISettingsIn):
    try:
        # The URL check does a DNS lookup: keep it off the event loop and bounded.
        await asyncio.wait_for(asyncio.to_thread(ai_settings.check_base_url,
                                                 body.base_url.strip() if body.provider == "openai" else ""), 5)
        ai_settings.save(state.conn, body.provider, body.model, body.base_url, body.keys, body.clear_keys,
                         checked=True)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    cfg = ai_settings.load(state.conn)
    state.interpreter = await asyncio.to_thread(ai_settings.interpreter, cfg)
    return ai_settings.public(cfg, state.interpreter.enabled)


@app.post("/api/settings/ai/test")
async def test_ai(body: AITestIn):
    if not state.interpreter.enabled:
        return {"ok": False, "error": "AI search is off: choose a provider and save a key (and a model for "
                                      "OpenAI/OpenRouter)."}
    started = time.monotonic()
    try:
        f, note = await state.interpreter.interpret(body.query, raise_errors=True)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:400]}
    return {"ok": True, "ms": int((time.monotonic() - started) * 1000), "note": note,
            "filters": {"text": f.text, "scope": f.scope, "on_now": f.on_now, "kinds": f.kinds,
                        "genres": f.genres, "within_minutes": f.within_minutes}}


# --- TVs and the pairing wizard ----------------------------------------------------------------

PLANNED_KINDS = [("roku", "Roku"), ("firetv", "Fire TV"), ("appletv", "Apple TV")]


def _device(device_id: int) -> dict:
    d = devices.get_device(state.conn, device_id)
    if not d:
        raise HTTPException(404, "No such TV")
    return d


def _driver_for(kind: str):
    drv = state.drivers.get(kind)
    if not drv:
        raise HTTPException(400, f"{kind} TVs aren't supported yet")
    return drv


def _driver(d: dict):
    return _driver_for(d["kind"])


def _lan_host(host: str) -> str:
    host = host.strip()
    try:
        if ipaddress.ip_address(host).is_private:
            return host
    except ValueError:
        pass
    raise HTTPException(400, "Use the TV's IP address on your home network, e.g. 192.168.1.50")


def _pairing_error(exc: PairingError, **extra) -> HTTPException:
    return HTTPException(409, {"code": exc.code, "message": str(exc), **extra})


@app.get("/api/tv-types")
async def tv_types():
    return [{"kind": k, "label": d.label, "available": True} for k, d in state.drivers.items()] + \
           [{"kind": k, "label": label, "available": False} for k, label in PLANNED_KINDS]


@app.get("/api/discover")
async def discover(kind: str = "androidtv"):
    found = await _driver_for(kind).discover()
    known = {d["host"]: d for d in devices.list_devices(state.conn)}
    return [{"name": f.name, "host": f.host, "mac": f.mac, "model": f.model,
             "device_id": known[f.host]["id"] if f.host in known else None,
             "paired": bool(known[f.host]["paired"]) if f.host in known else False} for f in found]


@app.post("/api/pair/start")
async def pair_start(body: PairStartIn):
    host, drv = _lan_host(body.host), _driver_for(body.kind)
    try:
        info = await drv.probe(host)
        await drv.start_pairing(host)
    except PairingError as exc:
        raise _pairing_error(exc) from exc
    return {"host": host, "name": info.name, "mac": info.mac}


@app.post("/api/pair/finish")
async def pair_finish(body: PairFinishIn):
    host, drv = _lan_host(body.host), _driver_for(body.kind)
    code = body.code.strip().upper()
    if len(code) != 6 or any(c not in "0123456789ABCDEF" for c in code):
        raise HTTPException(400, {"code": "bad_format", "message": "The code is 6 letters and numbers (0-9, A-F)."})
    try:
        await drv.finish_pairing(host, code)
    except WrongCode as exc:
        # A wrong code ends the TV's pairing screen; open a fresh one so the person can just retry.
        try:
            await drv.start_pairing(host)
        except PairingError as again:
            raise _pairing_error(again) from exc
        raise _pairing_error(exc, restarted=True) from exc
    except PairingError as exc:
        raise _pairing_error(exc) from exc
    name = body.name.strip() or host
    device_id = devices.add_device(state.conn, name, host, body.kind)
    devices.mark_paired(state.conn, device_id)
    return {"id": device_id, "name": name}


@app.get("/api/devices")
async def list_tvs():
    return devices.list_devices(state.conn)


@app.patch("/api/devices/{device_id}")
async def rename_tv(device_id: int, body: DevicePatch):
    _device(device_id)
    if not body.name.strip():
        raise HTTPException(400, "Name can't be empty")
    devices.rename_device(state.conn, device_id, body.name.strip())
    return devices.get_device(state.conn, device_id)


@app.delete("/api/devices/{device_id}")
async def remove_tv(device_id: int):
    devices.remove_device(state.conn, device_id)
    return {"ok": True}


@app.post("/api/devices/{device_id}/test")
async def test_tv(device_id: int, body: TestIn):
    """Open Plezy on the TV and confirm it came to the front: proves pairing works and Plezy is installed."""
    d = _device(device_id)
    drv = _driver(d)
    if not body.force:
        avail = await tune.check_busy(drv, state.source, d)
        if avail.busy:
            raise HTTPException(409, {"code": "busy", "message": avail.reason})
    try:
        await drv.open_link(d["host"], tune.open_link(plex_users.profile_for(d)))
    except NotPaired as exc:
        devices.mark_paired(state.conn, device_id, False)
        raise HTTPException(409, {"code": "not_paired", "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(502, {"code": "unreachable", "message": f"Couldn't reach {d['name']}: {exc}"}) from exc
    st = None
    for _ in range(4):  # Plezy can take a few seconds to come forward on a cold start
        await asyncio.sleep(2)
        st = await drv.status(d["host"])
        if st.current_app == tune.PLEZY:
            break
    return {"plezy": bool(st and st.current_app == tune.PLEZY), "current_app": st.current_app if st else ""}


@app.get("/api/devices/{device_id}/status")
async def tv_status(device_id: int):
    d = _device(device_id)
    avail = await tune.check_busy(_driver(d), state.source, d)
    st = avail.status
    return {"busy": avail.busy, "reason": avail.reason, "reachable": st.reachable if st else False,
            "is_on": st.is_on if st else None, "current_app": st.current_app if st else ""}


@app.post("/api/tune")
async def do_tune(body: TuneIn):
    d = _device(body.device_id)
    drv = _driver(d)
    server = db.get_meta(state.conn, "machine_id")
    profile = plex_users.profile_for(d)
    if body.channel:
        # Plezy pools the channels of every server it's signed in to unless told which one.
        link = tune.live_link(body.channel, server, profile)
    elif body.rating_key:
        link = tune.play_link(server, body.rating_key, profile)
    else:
        raise HTTPException(400, "Give a channel or a rating_key")
    if not body.force:
        avail = await tune.check_busy(drv, state.source, d)
        if avail.busy:
            raise HTTPException(409, {"code": "busy", "message": avail.reason})
    try:
        await drv.open_link(d["host"], link)
    except NotPaired as exc:
        devices.mark_paired(state.conn, d["id"], False)
        raise HTTPException(409, {"code": "not_paired", "message": str(exc), "device_id": d["id"]}) from exc
    except Exception as exc:
        raise HTTPException(502, {"code": "unreachable", "message": f"Couldn't reach {d['name']}: {exc}"}) from exc
    if body.channel:
        row = state.conn.execute("SELECT id FROM channels WHERE vcn = ? OR id = ?",
                                 (body.channel, body.channel)).fetchone()
        if row:
            state.last_tune[d["id"]] = (row["id"], time.time())
    route_cache.pop(f"now:{d['id']}", None)
    # Plezy can only play from Jellyfin once it's signed in there, and a profile it doesn't have starts
    # nothing. A link can't report either failure, so the page checks that something started.
    return {"ok": True, "link": link, "device": d["name"], "confirm": state.source.name == "jellyfin" or bool(profile),
            "profile_user": d["plex_user_name"] if profile else ""}
