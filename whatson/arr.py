"""Radarr (movies) and Sonarr (shows): look titles up, add them, and follow them until they reach Plex.

Settings live in the meta table, edited from the Downloads tab. RADARR_URL/RADARR_KEY and
SONARR_URL/SONARR_KEY in the environment are the fallback. As with the AI keys, a saved key only
goes to the address it was saved with, and keys never go back to the browser.

Everything here stays additive: WhatsOn adds and searches, it never edits or deletes in Radarr/Sonarr."""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field

import httpx

from . import db

KINDS = ("movie", "show")
APP = {"movie": "radarr", "show": "sonarr"}
LABEL = {"movie": "Radarr", "show": "Sonarr"}
MONITOR = ("all", "future", "missing", "existing", "firstSeason", "lastSeason", "pilot")
AVAILABILITY = ("announced", "inCinemas", "released")
PREFS = {"url": "", "root": "", "profile": 0, "anime_root": "", "anime_profile": 0, "anime_tags": [],
         "monitor": "all", "min_availability": "released"}


class ArrError(Exception):
    pass


class ArrNotFound(ArrError):
    pass


@dataclass
class ArrConfig:
    kind: str
    url: str
    key: str = ""
    key_source: str = ""  # saved | env | ""
    prefs: dict = field(default_factory=dict)

    @property
    def configured(self) -> bool:
        return bool(self.url and self.key)


def _env(kind: str, name: str) -> str:
    return os.environ.get(f"{APP[kind].upper()}_{name}", "").strip().rstrip("/")


def load(conn: sqlite3.Connection, kind: str) -> ArrConfig:
    try:
        saved = json.loads(db.get_meta(conn, f"arr.{kind}") or "{}")
    except ValueError:
        saved = {}
    prefs = {**PREFS, **{k: v for k, v in saved.items() if k in PREFS}}
    env_url = _env(kind, "URL")
    url = prefs["url"] or env_url
    prefs["url"] = url
    key, source = "", ""
    saved_key = db.get_meta(conn, f"arr.{kind}.key")
    if saved_key and db.get_meta(conn, f"arr.{kind}.key_base") == url:
        key, source = saved_key, "saved"
    elif url and url == env_url and os.environ.get(f"{APP[kind].upper()}_KEY", "").strip():
        key, source = os.environ[f"{APP[kind].upper()}_KEY"].strip(), "env"
    return ArrConfig(kind, url, key, source, prefs)


def clean_prefs(kind: str, body: dict) -> dict:
    """Validate what the Settings form sends; unknown fields are dropped."""
    p = {**PREFS}
    p["url"] = str(body.get("url") or "").strip().rstrip("/")
    for k in ("root", "anime_root"):
        p[k] = str(body.get(k) or "").strip()[:500]
    for k in ("profile", "anime_profile"):
        try:
            p[k] = max(0, int(body.get(k) or 0))
        except (TypeError, ValueError):
            raise ValueError(f"{k} must be a number") from None
    tags = body.get("anime_tags") or []
    if not isinstance(tags, list) or not all(isinstance(t, int) and t >= 0 for t in tags):
        raise ValueError("anime_tags must be a list of tag ids")
    p["anime_tags"] = tags[:20]
    if kind == "show":
        p["monitor"] = body.get("monitor") or "all"
        if p["monitor"] not in MONITOR:
            raise ValueError(f"monitor must be one of {', '.join(MONITOR)}")
    else:
        p["min_availability"] = body.get("min_availability") or "released"
        if p["min_availability"] not in AVAILABILITY:
            raise ValueError(f"min_availability must be one of {', '.join(AVAILABILITY)}")
    return p


def save(conn: sqlite3.Connection, kind: str, prefs: dict, key: str = "", clear_key: bool = False) -> None:
    """prefs come from clean_prefs; the caller has already checked the URL."""
    db.set_meta(conn, f"arr.{kind}", json.dumps(prefs))
    if clear_key:
        conn.execute("DELETE FROM meta WHERE key IN (?, ?)", (f"arr.{kind}.key", f"arr.{kind}.key_base"))
    elif key.strip():
        db.set_meta(conn, f"arr.{kind}.key", key.strip())
        db.set_meta(conn, f"arr.{kind}.key_base", prefs["url"])


def allow_add(conn: sqlite3.Connection) -> bool:
    return db.get_meta(conn, "arr.allow_add", "1") == "1"


def public(cfg: ArrConfig) -> dict:
    k = cfg.key
    return {**cfg.prefs, "configured": cfg.configured, "label": LABEL[cfg.kind],
            "key": {"set": bool(k), "hint": f"…{k[-4:]}" if len(k) > 8 else ("set" if k else ""),
                    "source": cfg.key_source}}


# --- Turning Radarr/Sonarr records into cards ---------------------------------------------------

def _poster(raw: dict) -> str:
    url = raw.get("remotePoster") or next(
        (i.get("remoteUrl", "") for i in raw.get("images", []) if i.get("coverType") == "poster"), "")
    # TMDB serves smaller sizes from the same path; the original is several MB.
    return url.replace("/t/p/original/", "/t/p/w342/") if url.startswith("https://image.tmdb.org/") else url


def _rating(raw: dict) -> float | None:
    r = raw.get("ratings") or {}
    if "value" in r:  # Sonarr: one rating
        return r["value"] or None
    for src in ("imdb", "tmdb"):  # Radarr: one per source
        v = (r.get(src) or {}).get("value")
        if v:
            return round(float(v), 1)
    return None


def is_anime(raw: dict) -> bool:
    genres = {g.lower() for g in raw.get("genres", [])}
    lang = ((raw.get("originalLanguage") or {}).get("name") or "").lower()
    return raw.get("seriesType") == "anime" or "anime" in genres or ("animation" in genres and lang == "japanese")


def card(kind: str, raw: dict) -> dict:
    stats = raw.get("statistics") or {}
    if kind == "movie":
        has_file = bool(raw.get("hasFile") or raw.get("movieFileId"))
    else:
        has_file = bool(stats.get("episodeFileCount"))
    return {
        "type": "get", "kind": kind, "id": raw.get("tmdbId") if kind == "movie" else raw.get("tvdbId"),
        "tmdb": raw.get("tmdbId") or None, "tvdb": raw.get("tvdbId") or None, "imdb": raw.get("imdbId") or None,
        "title": raw.get("title", ""), "year": raw.get("year") or None, "overview": (raw.get("overview") or "")[:600],
        "poster": _poster(raw), "rating": _rating(raw), "genres": raw.get("genres", [])[:4],
        "network": raw.get("network") or raw.get("studio") or "", "runtime": raw.get("runtime") or None,
        "status": raw.get("status", ""), "available": raw.get("isAvailable"),
        "seasons": len([s for s in raw.get("seasons", []) if s.get("seasonNumber")]) or None,
        "arr_id": raw.get("id") or None, "has_file": has_file, "anime": is_anime(raw),
        "episodes": [stats.get("episodeFileCount", 0), stats.get("episodeCount", 0)] if kind == "show" else None,
    }


def queue_progress(records: list[dict], kind: str) -> dict[int, dict]:
    """Queue rows grouped per movie/series: overall progress, time left, and whether it's importing."""
    out: dict[int, dict] = {}
    key = "movieId" if kind == "movie" else "seriesId"
    for r in records:
        arr_id = r.get(key)
        if not arr_id:
            continue
        q = out.setdefault(arr_id, {"size": 0, "left": 0, "count": 0, "timeleft": "", "importing": True,
                                    "warning": "", "raw": r})
        q["size"] += r.get("size") or 0
        q["left"] += r.get("sizeleft") or 0
        q["count"] += 1
        q["timeleft"] = max(q["timeleft"], r.get("timeleft") or "")
        q["importing"] &= r.get("status") == "completed"
        if r.get("trackedDownloadStatus") == "warning" or r.get("trackedDownloadState") == "importBlocked":
            q["warning"] = "Needs attention in " + LABEL[kind]
    for q in out.values():
        q["progress"] = round(1 - q["left"] / q["size"], 3) if q["size"] else 0.0
    return out


def set_state(c: dict, queue: dict[int, dict], plex_key: str | None) -> dict:
    """One of: in_plex, not_added, downloading, importing, imported, not_released, missing."""
    q = queue.get(c["arr_id"]) if c["arr_id"] else None
    if plex_key:
        c["state"], c["rating_key"] = "in_plex", plex_key
    elif not c["arr_id"]:
        c["state"] = "not_added"
    elif q:
        c["state"] = "importing" if q["importing"] else "downloading"
        c["progress"], c["timeleft"], c["warning"] = q["progress"], q["timeleft"], q["warning"]
        if c["kind"] == "show":
            c["queued_episodes"] = q["count"]
    elif c["has_file"] and c["kind"] == "movie":
        c["state"] = "imported"
    elif c["kind"] == "movie" and c["status"] in ("announced", "inCinemas", "tba") and not c["available"]:
        c["state"] = "not_released"
    elif c["kind"] == "show" and c["status"] == "upcoming":
        c["state"] = "not_released"
    elif c["kind"] == "show" and c["has_file"]:
        c["state"] = "imported"  # some episodes are in; Plex picks them up on its next scan
    else:
        c["state"] = "missing"
    return c


def pick(prefs: dict, options: dict, anime: bool, root: str = "", profile: int = 0) -> tuple[str, int, list[int]]:
    """Root folder, quality profile and tags for an add. An explicit choice must be one the app has;
    otherwise the saved defaults (the anime set when anime), falling back to the app's first ones."""
    roots = [r["path"] for r in options["roots"]]
    profiles = [p["id"] for p in options["profiles"]]
    tag_ids = {t["id"] for t in options["tags"]}
    if root and root not in roots:
        raise ArrError("That folder isn't one of the app's root folders")
    if profile and profile not in profiles:
        raise ArrError("That quality profile doesn't exist")
    root = root or (anime and prefs["anime_root"]) or prefs["root"]
    profile = profile or (anime and prefs["anime_profile"]) or prefs["profile"]
    if root not in roots:
        root = roots[0] if roots else ""
    if profile not in profiles:
        profile = profiles[0] if profiles else 0
    if not root or not profile:
        raise ArrError("Set up a root folder and quality profile in the app first")
    tags = [t for t in (prefs["anime_tags"] if anime else []) if t in tag_ids]
    return root, profile, tags


def guess_anime(options: dict) -> dict:
    """Suggested anime defaults for Settings: a folder, profile and tag with "anime" in the name."""
    has = lambda s: "anime" in str(s).lower()
    return {"anime_root": next((r["path"] for r in options["roots"] if has(r["path"])), ""),
            "anime_profile": next((p["id"] for p in options["profiles"] if has(p["name"])), 0),
            "anime_tags": [t["id"] for t in options["tags"] if has(t["label"])][:1]}


# --- The HTTP client ----------------------------------------------------------------------------

class Arr:
    def __init__(self, cfg: ArrConfig, http: httpx.AsyncClient):
        self.kind = cfg.kind
        self.label = LABEL[cfg.kind]
        self.base = f"{cfg.url}/api/v3"
        self.cfg = cfg
        self._http = http
        self._headers = {"X-Api-Key": cfg.key}

    async def _req(self, method: str, path: str, **kw):
        try:
            # No redirects: the key must not follow a 30x somewhere else.
            r = await self._http.request(method, self.base + path, headers=self._headers, timeout=20,
                                         follow_redirects=False, **kw)
        except httpx.HTTPError as exc:
            raise ArrError(f"{self.label} didn't answer ({type(exc).__name__})") from exc
        if r.status_code == 401:
            raise ArrError(f"{self.label} refused the API key")
        if r.status_code == 404:
            raise ArrNotFound(f"{self.label}: not found")
        if r.status_code >= 400:
            try:
                body = r.json()
                msg = body[0].get("errorMessage") if isinstance(body, list) and body else body.get("message")
            except ValueError:
                msg = ""
            raise ArrError(f"{self.label}: {msg or f'HTTP {r.status_code}'}")
        if r.status_code >= 300:
            raise ArrError(f"{self.label} redirected; check the address")
        return r.json() if r.content else None

    async def version(self) -> str:
        return (await self._req("GET", "/system/status")).get("version", "")

    async def options(self) -> dict:
        roots = await self._req("GET", "/rootfolder")
        profiles = await self._req("GET", "/qualityprofile")
        tags = await self._req("GET", "/tag")
        return {"roots": [{"id": r["id"], "path": r["path"], "free": r.get("freeSpace")} for r in roots],
                "profiles": [{"id": p["id"], "name": p["name"]} for p in profiles],
                "tags": [{"id": t["id"], "label": t["label"]} for t in tags]}

    async def lookup(self, term: str) -> list[dict]:
        path = "/movie/lookup" if self.kind == "movie" else "/series/lookup"
        return (await self._req("GET", path, params={"term": term})) or []

    async def lookup_id(self, ext_id: int) -> dict | None:
        if self.kind == "movie":
            raw = await self._req("GET", "/movie/lookup/tmdb", params={"tmdbId": ext_id})
            return raw if raw and raw.get("tmdbId") else None
        found = await self._req("GET", "/series/lookup", params={"term": f"tvdb:{ext_id}"})
        return next((s for s in found or [] if s.get("tvdbId") == ext_id), None)

    async def get(self, arr_id: int) -> dict:
        return await self._req("GET", f"/{'movie' if self.kind == 'movie' else 'series'}/{arr_id}")

    async def queue(self) -> list[dict]:
        extra = {"includeMovie": "true"} if self.kind == "movie" else {"includeSeries": "true", "includeEpisode": "true"}
        return ((await self._req("GET", "/queue", params={"pageSize": 200, **extra})) or {}).get("records", [])

    def add_body(self, raw: dict, root: str, profile: int, tags: list[int], anime: bool,
                 search: bool, monitor: str = "") -> dict:
        """The lookup record plus our choices, which is what Radarr's and Sonarr's own UIs post."""
        body = {k: v for k, v in raw.items() if k != "id"}
        body.update(rootFolderPath=root, qualityProfileId=profile, monitored=True,
                    tags=sorted(set(raw.get("tags") or []) | set(tags)))
        if self.kind == "movie":
            body.update(minimumAvailability=self.cfg.prefs["min_availability"],
                        addOptions={"searchForMovie": search})
        else:
            series_type = "anime" if anime else ("daily" if raw.get("seriesType") == "daily" else "standard")
            body.update(seriesType=series_type, seasonFolder=True,
                        addOptions={"monitor": monitor or self.cfg.prefs["monitor"],
                                    "searchForMissingEpisodes": search, "searchForCutoffUnmetEpisodes": False})
        return body

    async def add(self, body: dict) -> dict:
        return await self._req("POST", "/movie" if self.kind == "movie" else "/series", json=body)

    async def search(self, arr_id: int) -> None:
        cmd = {"name": "MoviesSearch", "movieIds": [arr_id]} if self.kind == "movie" \
            else {"name": "SeriesSearch", "seriesId": arr_id}
        await self._req("POST", "/command", json=cmd)
