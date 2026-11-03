"""Trakt: device-code sign-in plus a periodic sync of the bits suggestions use (watchlist, ratings,
watch progress, calendar, recommendations). Each self-hoster registers their own free Trakt API app
(trakt.tv/oauth/applications) and pastes its client id and secret into Settings; a shared secret
can't ship in open source.

Everything is cached in the meta table, so suggestions never wait on Trakt."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from datetime import date

import httpx

from . import db

log = logging.getLogger(__name__)
API = "https://api.trakt.tv"
OOB = "urn:ietf:wg:oauth:2.0:oob"
SYNC_EVERY = 30 * 60


def norm_title(title: str) -> str:
    """Loose title key for matching guide listings (which carry no ids) to Trakt titles."""
    t = re.sub(r"\(\d{4}\)", "", title.lower())
    t = re.sub(r"^(the|a|an)\s+", "", t.strip())
    return re.sub(r"[^a-z0-9]+", "", t)


def guid_keys(ids: dict) -> set[str]:
    """Trakt ids -> the same "imdb:tt..", "tmdb:..", "tvdb:.." strings stored in library.guids."""
    return {f"{k}:{ids[k]}" for k in ("imdb", "tmdb", "tvdb") if ids.get(k)}


class TraktError(Exception):
    pass


class Trakt:
    def __init__(self, conn: sqlite3.Connection, http: httpx.AsyncClient | None = None):
        self.conn = conn
        self.http = http or httpx.AsyncClient(timeout=20)
        self.device: dict | None = None  # pending device-code sign-in

    # --- settings and tokens -------------------------------------------------------------------

    def _m(self, key: str, default: str = "") -> str:
        return db.get_meta(self.conn, f"trakt.{key}", default)

    def _set(self, key: str, value: str) -> None:
        db.set_meta(self.conn, f"trakt.{key}", value)

    @property
    def client_id(self) -> str:
        return self._m("client_id")

    @property
    def configured(self) -> bool:
        return bool(self._m("client_id") and self._m("client_secret"))

    @property
    def connected(self) -> bool:
        return bool(self._m("access"))

    def public(self) -> dict:
        return {"configured": self.configured, "connected": self.connected, "user": self._m("user"),
                "client_id_hint": f"…{self.client_id[-4:]}" if self.client_id else "",
                "synced_at": int(self._m("synced_at", "0") or 0),
                "pending": bool(self.device)}

    def save_app(self, client_id: str, client_secret: str) -> None:
        if client_id.strip():
            if client_id.strip() != self.client_id:
                self.disconnect()  # tokens belong to the old app
            self._set("client_id", client_id.strip())
        if client_secret.strip():
            self._set("client_secret", client_secret.strip())

    def disconnect(self) -> None:
        for k in ("access", "refresh", "expires", "user", "cache", "synced_at"):
            self.conn.execute("DELETE FROM meta WHERE key = ?", (f"trakt.{k}",))
        self.device = None

    def _headers(self, auth: bool = True) -> dict:
        h = {"trakt-api-version": "2", "trakt-api-key": self.client_id, "Content-Type": "application/json",
             "User-Agent": "WhatsOn"}
        if auth and self._m("access"):
            h["Authorization"] = f"Bearer {self._m('access')}"
        return h

    def _store_tokens(self, tok: dict) -> None:
        self._set("access", tok["access_token"])
        self._set("refresh", tok.get("refresh_token", ""))
        self._set("expires", str(int(tok.get("created_at", time.time())) + int(tok.get("expires_in", 0))))

    # --- device-code sign-in -------------------------------------------------------------------

    async def start_device(self) -> dict:
        if not self.configured:
            raise TraktError("Add your Trakt app's client id and secret first.")
        r = await self.http.post(f"{API}/oauth/device/code", json={"client_id": self.client_id},
                                 headers=self._headers(auth=False))
        if r.status_code != 200:
            raise TraktError(f"Trakt didn't accept the client id ({r.status_code}).")
        d = r.json()
        self.device = {**d, "started": time.time()}
        return {"user_code": d["user_code"], "verification_url": d["verification_url"],
                "expires_in": d["expires_in"], "interval": d["interval"]}

    async def poll_device(self) -> str:
        """One poll: 'connected' | 'pending' | 'expired' | 'denied' | 'idle'."""
        if not self.device:
            return "connected" if self.connected else "idle"
        if time.time() - self.device["started"] > self.device["expires_in"]:
            self.device = None
            return "expired"
        r = await self.http.post(f"{API}/oauth/device/token", headers=self._headers(auth=False), json={
            "code": self.device["device_code"], "client_id": self.client_id,
            "client_secret": self._m("client_secret")})
        if r.status_code == 200:
            self._store_tokens(r.json())
            self.device = None
            try:
                me = await self._get("/users/settings")
                self._set("user", me.get("user", {}).get("username", ""))
            except Exception:
                pass
            return "connected"
        if r.status_code in (400, 429):
            return "pending"
        self.device = None
        return {410: "expired", 418: "denied"}.get(r.status_code, "expired")

    async def _refresh_if_needed(self) -> None:
        if not self.connected or time.time() < int(self._m("expires", "0") or 0) - 86400:
            return
        r = await self.http.post(f"{API}/oauth/token", headers=self._headers(auth=False), json={
            "refresh_token": self._m("refresh"), "client_id": self.client_id,
            "client_secret": self._m("client_secret"), "redirect_uri": OOB, "grant_type": "refresh_token"})
        if r.status_code == 200:
            self._store_tokens(r.json())
        elif r.status_code in (400, 401):
            log.warning("Trakt refresh token rejected; sign in again")
            self.disconnect()

    async def _get(self, path: str, params: dict | None = None):
        r = await self.http.get(f"{API}{path}", params=params, headers=self._headers())
        if r.status_code == 401:
            raise TraktError("Trakt sign-in expired")
        r.raise_for_status()
        return r.json()

    # --- sync ------------------------------------------------------------------------------------

    def cache(self) -> dict:
        raw = self._m("cache")
        return json.loads(raw) if raw else {}

    async def sync(self, force: bool = False) -> bool:
        if not self.connected:
            return False
        if not force and time.time() - int(self._m("synced_at", "0") or 0) < SYNC_EVERY:
            return False
        await self._refresh_if_needed()
        if not self.connected:
            return False

        def slim(item: dict, kind: str) -> dict:
            m = item.get(kind) or {}
            return {"title": m.get("title", ""), "year": m.get("year"), "ids": m.get("ids", {})}

        c: dict = {"watchlist": [], "ratings": [], "up_next": [], "calendar": [], "recommended": [],
                   "watched_shows": []}
        for kind in ("movie", "show"):
            for it in await self._get(f"/sync/watchlist/{kind}s"):
                c["watchlist"].append({"kind": kind, **slim(it, kind)})
            for it in await self._get(f"/sync/ratings/{kind}s"):
                c["ratings"].append({"kind": kind, "rating": it.get("rating"), **slim(it, kind)})
            for it in await self._get(f"/recommendations/{kind}s", {"limit": 30}):
                c["recommended"].append({"kind": kind, "title": it.get("title", ""), "year": it.get("year"),
                                         "ids": it.get("ids", {})})
        watched = await self._get("/sync/watched/shows", {"extended": "noseasons"})
        watched.sort(key=lambda w: w.get("last_watched_at", ""), reverse=True)
        for w in watched[:25]:
            show = slim(w, "show")
            c["watched_shows"].append({**show, "last_watched_at": w.get("last_watched_at", "")})
            try:
                prog = await self._get(f"/shows/{show['ids'].get('trakt')}/progress/watched")
            except httpx.HTTPError:
                continue
            nxt = prog.get("next_episode")
            if nxt and not prog.get("completed") == prog.get("aired"):
                c["up_next"].append({**show, "season": nxt.get("season"), "number": nxt.get("number"),
                                     "episode_title": nxt.get("title", ""),
                                     "last_watched_at": w.get("last_watched_at", "")})
        for it in await self._get(f"/calendars/my/shows/{date.today().isoformat()}/2"):
            ep = it.get("episode", {})
            c["calendar"].append({**slim(it, "show"), "first_aired": it.get("first_aired", ""),
                                  "season": ep.get("season"), "number": ep.get("number"),
                                  "episode_title": ep.get("title", "")})
        self._set("cache", json.dumps(c))
        self._set("synced_at", str(int(time.time())))
        log.info("trakt: %d watchlist, %d ratings, %d up next, %d calendar", len(c["watchlist"]),
                 len(c["ratings"]), len(c["up_next"]), len(c["calendar"]))
        return True
