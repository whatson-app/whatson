"""API for finding and adding movies and shows through Radarr and Sonarr: the Downloads settings tab,
the "Get it" row under library searches, the Add sheet, and the Downloads view."""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import ai_settings, arr, db, suggest
from .arr import KINDS, LABEL, Arr, ArrConfig, ArrError
from .routes import _cache, cached, remember
from .state import state

router = APIRouter(prefix="/api")

ORDER = {"downloading": 0, "importing": 1, "not_released": 2, "missing": 3, "imported": 4, "in_plex": 5}


def _kind(kind: str) -> str:
    if kind not in KINDS:
        raise HTTPException(400, "kind is movie or show")
    return kind


def _client(kind: str) -> Arr:
    cfg = arr.load(state.conn, _kind(kind))
    if not cfg.configured:
        raise HTTPException(409, f"{LABEL[kind]} isn't set up yet (Settings → More → Downloads)")
    return Arr(cfg, state.lan_http)


async def _check_url(url: str) -> None:
    try:
        await asyncio.wait_for(asyncio.to_thread(ai_settings.check_base_url, url), 5)
    except asyncio.TimeoutError as exc:
        raise HTTPException(400, "Looking up that server took too long") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _forget(prefix: str) -> None:
    for k in [k for k in _cache if k.startswith(prefix)]:
        del _cache[k]


def _plex_key(c: dict) -> str | None:
    ids = {k: c[k] for k in ("tmdb", "tvdb", "imdb") if c.get(k)}
    row = suggest.match_library(state.conn, c["kind"], {"ids": ids, "title": c["title"], "year": c["year"]})
    return row["rating_key"] if row else None


async def _queue(client: Arr) -> list[dict]:
    key = f"arrq:{client.kind}"
    if (hit := cached(key, 10)) is not None:
        return hit
    return remember(key, await client.queue())


async def _options(client: Arr) -> dict:
    key = f"arro:{client.kind}"
    if (hit := cached(key, 300)) is not None:
        return hit
    return remember(key, await client.options())


def _configured() -> dict:
    return {k: arr.load(state.conn, k).configured for k in KINDS}


# --- Settings ------------------------------------------------------------------------------------

@router.get("/settings/downloads")
async def downloads_settings():
    return {"allow_add": arr.allow_add(state.conn), "monitor_options": arr.MONITOR,
            "availability_options": arr.AVAILABILITY,
            **{k: arr.public(arr.load(state.conn, k)) for k in KINDS}}


class AllowIn(BaseModel):
    allow_add: bool


@router.put("/settings/downloads")
async def downloads_allow(body: AllowIn):
    db.set_meta(state.conn, "arr.allow_add", "1" if body.allow_add else "0")
    return await downloads_settings()


class ArrSettingsIn(BaseModel):
    url: str = ""
    key: str = ""
    clear_key: bool = False
    root: str = ""
    profile: int = 0
    anime_root: str = ""
    anime_profile: int = 0
    anime_tags: list[int] = []
    monitor: str = "all"
    min_availability: str = "released"


@router.put("/settings/downloads/{kind}")
async def downloads_save(kind: str, body: ArrSettingsIn):
    try:
        prefs = arr.clean_prefs(_kind(kind), body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if prefs["url"]:
        await _check_url(prefs["url"])
    arr.save(state.conn, kind, prefs, body.key, body.clear_key)
    _forget("arr")
    _forget(f"lookup:{kind}:")
    return arr.public(arr.load(state.conn, kind))


class ArrTestIn(BaseModel):
    url: str
    key: str = ""


@router.post("/settings/downloads/{kind}/test")
async def downloads_test(kind: str, body: ArrTestIn):
    """Check an address and key before saving, and return the app's folders, profiles and tags for
    the dropdowns. The typed key is used if given, else the saved key for this same address."""
    url = body.url.strip().rstrip("/")
    if not url:
        raise HTTPException(400, "Enter the address first")
    await _check_url(url)
    saved = arr.load(state.conn, _kind(kind))
    key = body.key.strip() or (saved.key if saved.url == url else "")
    if not key:
        raise HTTPException(400, f"Paste {LABEL[kind]}'s API key (Settings → General in {LABEL[kind]})")
    client = Arr(ArrConfig(kind, url, key, prefs=saved.prefs), state.lan_http)
    try:
        version = await client.version()
        options = await client.options()
    except ArrError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"version": version, "options": options, "suggested": arr.guess_anime(options)}


# --- Finding and adding --------------------------------------------------------------------------

async def _lookup_kind(kind: str, q: str) -> list[dict]:
    client = _client(kind)
    key = f"lookup:{kind}:{q.lower()}"
    cards = cached(key, 600)
    if cards is None:
        cards = remember(key, [arr.card(kind, raw) for raw in (await client.lookup(q))[:10]])
    queue = arr.queue_progress(await _queue(client), kind) if any(c["arr_id"] for c in cards) else {}
    return [arr.set_state(dict(c), queue, _plex_key(c)) for c in cards]


@router.get("/get/lookup")
async def get_lookup(q: str, kind: str = "all"):
    q = q.strip()
    if not 2 <= len(q) <= 100:
        raise HTTPException(400, "Search for 2 to 100 characters")
    configured = _configured()
    kinds = [k for k in KINDS if configured[k] and kind in ("all", k)]
    out = {"configured": configured, "allow_add": arr.allow_add(state.conn), "errors": {},
           "movie": [], "show": []}
    results = await asyncio.gather(*(_lookup_kind(k, q) for k in kinds), return_exceptions=True)
    for k, res in zip(kinds, results):
        if isinstance(res, Exception):
            out["errors"][k] = str(res.detail if isinstance(res, HTTPException) else res)
        else:
            out[k] = res
    return out


@router.get("/get/item")
async def get_item(kind: str, id: int):
    """One title for the Add sheet: its state now, and the folders and profiles to choose from."""
    client = _client(kind)
    try:
        raw = await client.lookup_id(id)
        if not raw:
            raise HTTPException(404, f"{LABEL[kind]} doesn't know that title")
        if raw.get("id"):
            raw = await client.get(raw["id"])  # the library record has file and episode counts
        c = arr.card(kind, raw)
        queue = arr.queue_progress(await _queue(client), kind) if c["arr_id"] else {}
        options = await _options(client)
    except ArrError as exc:
        raise HTTPException(502, str(exc)) from exc
    prefs = client.cfg.prefs
    defaults = {}
    for anime in (False, True):
        try:
            root, profile, _ = arr.pick(prefs, options, anime)
        except ArrError:
            root, profile = "", 0
        defaults["anime" if anime else "normal"] = {"root": root, "profile": profile}
    return {"item": arr.set_state(c, queue, _plex_key(c)), "options": options, "defaults": defaults,
            "monitor": prefs.get("monitor", "all"), "allow_add": arr.allow_add(state.conn), "label": LABEL[kind]}


class AddIn(BaseModel):
    kind: str
    id: int
    anime: bool = False
    root: str = ""
    profile: int = 0
    monitor: str = ""
    search: bool = True


@router.post("/get/add")
async def get_add(body: AddIn):
    if not arr.allow_add(state.conn):
        raise HTTPException(403, "Adding is turned off in Settings → More → Downloads")
    if body.monitor and body.monitor not in arr.MONITOR:
        raise HTTPException(400, "Unknown monitor option")
    client = _client(body.kind)
    try:
        # Re-read the title from Radarr/Sonarr rather than trusting what the browser sends.
        raw = await client.lookup_id(body.id)
        if not raw:
            raise HTTPException(404, f"{client.label} doesn't know that title")
        if raw.get("id"):
            raise HTTPException(409, f"Already in {client.label}")
        root, profile, tags = arr.pick(client.cfg.prefs, await _options(client), body.anime, body.root, body.profile)
        added = await client.add(client.add_body(raw, root, profile, tags, body.anime, body.search, body.monitor))
    except ArrError as exc:
        raise HTTPException(502, str(exc)) from exc
    c = arr.card(body.kind, added)
    db_row = (body.kind, c["arr_id"], c["title"], c["year"], c["poster"], int(time.time()))
    state.conn.execute("INSERT OR REPLACE INTO arr_adds VALUES (?, ?, ?, ?, ?, ?)", db_row)
    _forget(f"lookup:{body.kind}:")
    _forget(f"arrq:{body.kind}")
    return arr.set_state(c, {}, None)


class SearchIn(BaseModel):
    kind: str
    arr_id: int


@router.post("/get/search")
async def get_search(body: SearchIn):
    if not arr.allow_add(state.conn):
        raise HTTPException(403, "Adding is turned off in Settings → More → Downloads")
    client = _client(body.kind)
    try:
        await client.search(body.arr_id)
    except ArrError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"ok": True, "message": f"{client.label} is searching for it"}


async def _downloads_kind(kind: str) -> list[dict]:
    client = _client(kind)
    records = await _queue(client)
    queue = arr.queue_progress(records, kind)
    items: dict[int, dict] = {}
    for arr_id, q in queue.items():
        raw = q["raw"].get("movie" if kind == "movie" else "series")
        if raw:
            c = arr.card(kind, raw)
            if kind == "show":
                eps = [r.get("episode") or {} for r in records if r.get("seriesId") == arr_id]
                c["episode_labels"] = sorted(f"S{e.get('seasonNumber', 0):02d}E{e.get('episodeNumber', 0):02d}"
                                             for e in eps if e)[:6]
            items[arr_id] = arr.set_state(c, queue, None)
    since = int(time.time()) - 30 * 86400
    recent = [r for r in state.conn.execute(
        "SELECT * FROM arr_adds WHERE kind = ? AND added_at > ? ORDER BY added_at DESC LIMIT 20", (kind, since))
        if r["arr_id"] not in items]
    fetched = await asyncio.gather(*(client.get(r["arr_id"]) for r in recent), return_exceptions=True)
    for r, raw in zip(recent, fetched):
        if isinstance(raw, arr.ArrNotFound):
            state.conn.execute("DELETE FROM arr_adds WHERE kind = ? AND arr_id = ?", (kind, r["arr_id"]))
            continue  # removed in Radarr/Sonarr
        if isinstance(raw, Exception):
            continue
        c = arr.card(kind, raw)
        items[r["arr_id"]] = arr.set_state(c, queue, _plex_key(c))
    mine = {r["arr_id"] for r in state.conn.execute("SELECT arr_id FROM arr_adds WHERE kind = ?", (kind,))}
    for c in items.values():
        c["added_here"] = c["arr_id"] in mine
    return list(items.values())


@router.get("/get/downloads")
async def get_downloads():
    configured = _configured()
    kinds = [k for k in KINDS if configured[k]]
    out = {"configured": configured, "items": [], "errors": {}}
    results = await asyncio.gather(*(_downloads_kind(k) for k in kinds), return_exceptions=True)
    for k, res in zip(kinds, results):
        if isinstance(res, Exception):
            out["errors"][k] = str(res.detail if isinstance(res, HTTPException) else res)
        else:
            out["items"] += res
    out["items"].sort(key=lambda c: (ORDER.get(c["state"], 9), -(c.get("progress") or 0)))
    return out
