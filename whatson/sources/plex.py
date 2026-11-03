"""Plex Media Server client: Live TV guide, library and active sessions.

The guide comes from Plex's own EPG provider (`/<epgIdentifier>/grid`), so this works for
any Plex Live TV setup, whatever feeds it (HDHomeRun, Dispatcharr, Plex's cloud guide).
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from .base import Airing, Channel, LibraryItem, Session, classify

PAGE = 2000
# Only exact Plex artwork paths, so /api/thumb can't be used to reach anything else on the server.
THUMB_RE = re.compile(r"/library/metadata/\d+/(thumb|art)/\d+")


def _list(container: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = container.get(key) or []
    return value if isinstance(value, list) else [value]


class PlexNotConnected(Exception):
    """No Plex server is set up yet (Settings → Plex)."""


class PlexClient:
    name, label = "plex", "Plex"

    def __init__(self, url: str, token: str, client_name: str = "WhatsOn",
                 http: httpx.AsyncClient | None = None, client_id: str = ""):
        self._http = http or httpx.AsyncClient(timeout=60)
        self._name, self._client_id = client_name, client_id or f"{client_name.lower()}-server"
        self.configure(url, token)

    def configure(self, url: str, token: str) -> None:
        """Point at a (new) server; called again when the sign-in changes."""
        self.url = url.rstrip("/")
        self._headers = {
            "X-Plex-Token": token,
            "X-Plex-Client-Identifier": self._client_id,
            "X-Plex-Product": self._name,
            "Accept": "application/json",
        }

    @property
    def configured(self) -> bool:
        return bool(self.url and self._headers["X-Plex-Token"])

    async def get_raw(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        if not self.configured:
            raise PlexNotConnected("Plex isn't connected yet (Settings → Plex)")
        return await self._http.get(f"{self.url}{path}", params=params, headers=self._headers)

    async def _get(self, path: str, params: dict[str, Any] | None = None,
                   headers: dict[str, str] | None = None) -> dict[str, Any]:
        if not self.configured:
            raise PlexNotConnected("Plex isn't connected yet (Settings → Plex)")
        r = await self._http.get(f"{self.url}{path}", params=params,
                                 headers={**self._headers, **(headers or {})})
        r.raise_for_status()
        return r.json().get("MediaContainer", {})

    async def close(self) -> None:
        await self._http.aclose()

    async def machine_identifier(self) -> str:
        return (await self._get("/identity"))["machineIdentifier"]

    server_id = machine_identifier

    async def load_guide(self, start: int, end: int) -> tuple[list[Channel], list[Airing]]:
        channels: list[Channel] = []
        airings: list[Airing] = []
        for epg in await self.epg_identifiers():
            channels += await self.channels(epg)
            airings += await self.guide(epg, start, end)
        return channels, airings

    async def epg_identifiers(self) -> list[str]:
        dvrs = _list(await self._get("/livetv/dvrs"), "Dvr")
        return [d["epgIdentifier"] for d in dvrs if d.get("epgIdentifier")]

    async def channels(self, epg: str) -> list[Channel]:
        mc = await self._get(f"/{epg}/lineups/dvr/channels")
        rows = _list(mc, "Channel")
        for lineup in _list(mc, "Lineup"):
            rows += _list(lineup, "Channel")
        out = []
        for c in rows:
            ident = str(c.get("identifier") or c.get("id") or c.get("vcn") or "")
            if not ident:
                continue
            out.append(Channel(id=ident, vcn=str(c.get("vcn") or ident),
                               title=c.get("title") or c.get("callSign") or ident,
                               callsign=c.get("callSign") or "", thumb=c.get("thumb") or ""))
        return out

    async def guide(self, epg: str, start: int, end: int) -> list[Airing]:
        # httpx would encode the comparison operator, so build that part of the query by hand.
        query = f"type=1,4&beginsAt%3C={end}&endsAt%3E={start}"
        out: list[Airing] = []
        offset = 0
        while True:
            mc = await self._get(f"/{epg}/grid?{query}", headers={
                "X-Plex-Container-Start": str(offset), "X-Plex-Container-Size": str(PAGE)})
            items = _list(mc, "Metadata")
            for item in items:
                out.extend(self._airings(item, start, end))
            offset += len(items)
            total = int(mc.get("totalSize") or mc.get("size") or 0)
            if not items or len(items) < PAGE or offset >= total:
                return out

    @staticmethod
    def _airings(item: dict[str, Any], start: int, end: int) -> list[Airing]:
        plex_type = item.get("type", "")
        genres = [g.get("tag", "") for g in _list(item, "Genre")]
        if plex_type == "episode":
            title = item.get("grandparentTitle") or item.get("title", "")
            sub = item.get("title", "") if item.get("title") != title else ""
            s, e = item.get("parentIndex"), item.get("index")
            if s and e and int(s) > 0:
                sub = f"S{int(s):02d}E{int(e):02d} {sub}".strip()
        else:
            title, sub = item.get("title", ""), ""
        summary = item.get("summary", "") or ""
        kind = classify(title, summary, plex_type, genres)
        out = []
        for m in _list(item, "Media"):
            b, e = int(m.get("beginsAt") or 0), int(m.get("endsAt") or 0)
            ch = str(m.get("channelIdentifier") or m.get("channelVcn") or "")
            if ch and b < end and e > start:
                out.append(Airing(ch, title, sub, summary, kind, b, e, item.get("year")))
        return out

    async def library(self) -> list[LibraryItem]:
        out: list[LibraryItem] = []
        for sec in _list(await self._get("/library/sections"), "Directory"):
            if sec.get("type") not in ("movie", "show"):
                continue
            offset = 0
            while True:
                mc = await self._get(f"/library/sections/{sec['key']}/all?includeGuids=1", headers={
                    "X-Plex-Container-Start": str(offset), "X-Plex-Container-Size": str(PAGE)})
                items = _list(mc, "Metadata")
                for m in items:
                    leaves, viewed = int(m.get("leafCount") or 0), int(m.get("viewedLeafCount") or 0)
                    out.append(LibraryItem(
                        rating_key=str(m["ratingKey"]), kind=sec["type"], title=m.get("title", ""),
                        year=m.get("year"), summary=m.get("summary", "") or "",
                        genres=[g.get("tag", "") for g in _list(m, "Genre")],
                        people=[p.get("tag", "") for p in _list(m, "Role") + _list(m, "Director")],
                        thumb=m.get("thumb", "") or "", section=sec.get("title", ""),
                        added_at=int(m.get("addedAt") or 0), duration=int(m.get("duration") or 0),
                        content_rating=m.get("contentRating", "") or "",
                        audience_rating=m.get("audienceRating"),
                        watched=bool(m.get("viewCount")) if sec["type"] == "movie" else (leaves > 0 and viewed >= leaves),
                        leaf_count=leaves, viewed_leaf_count=viewed,
                        guids=[g["id"].replace("://", ":") for g in _list(m, "Guid") if g.get("id")]))
                offset += len(items)
                if not items or offset >= int(mc.get("totalSize") or mc.get("size") or 0):
                    break
        return out

    async def sessions(self) -> list[Session]:
        out = []
        for m in _list(await self._get("/status/sessions"), "Metadata"):
            p = m.get("Player") or {}
            live = bool(m.get("live"))
            kind = "live" if live else m.get("type", "")
            episode = ""
            if kind == "episode":
                s_, e_ = m.get("parentIndex"), m.get("index")
                episode = (f"S{int(s_):02d}E{int(e_):02d} " if s_ and e_ else "") + (m.get("title") or "")
            out.append(Session(player_title=p.get("title", ""), player_address=p.get("address", ""),
                               product=p.get("product", ""), state=p.get("state", ""),
                               title=m.get("grandparentTitle") or m.get("title", ""), live=live,
                               kind=kind, show=m.get("grandparentTitle", "") or "", episode=episode,
                               rating_key=str(m.get("ratingKey", "")), show_key=str(m.get("grandparentRatingKey", "") or ""),
                               thumb=m.get("grandparentThumb") or m.get("thumb") or "",
                               offset=int(m.get("viewOffset") or 0), duration=int(m.get("duration") or 0),
                               key=m.get("key", "")))
        return out

    playing = sessions

    def valid_id(self, item_id: str) -> bool:
        return item_id.isdigit()

    async def item(self, item_id: str) -> dict | None:
        m = await self.metadata(item_id)
        if not m:
            return None
        out = {"rating_key": item_id, "kind": m.get("type"), "title": m.get("title"), "year": m.get("year"),
               "summary": m.get("summary", ""), "duration": m.get("duration"), "content_rating": m.get("contentRating", ""),
               "audience_rating": m.get("audienceRating"), "thumb": m.get("thumb", ""), "art": m.get("art", ""),
               "genres": [g.get("tag") for g in m.get("Genre", [])], "cast": [r.get("tag") for r in m.get("Role", [])][:8],
               "studio": m.get("studio", ""), "view_offset": m.get("viewOffset"), "watched": bool(m.get("viewCount"))}
        if m.get("type") == "show":
            out["seasons"] = [{"rating_key": str(s["ratingKey"]), "index": s.get("index"), "title": s.get("title"),
                               "thumb": s.get("thumb", ""), "episodes": s.get("leafCount"),
                               "watched": s.get("viewedLeafCount")} for s in await self.children(item_id)]
        return out

    async def episodes(self, season_id: str) -> list[dict]:
        return [{"rating_key": str(e["ratingKey"]), "index": e.get("index"), "title": e.get("title"),
                 "summary": e.get("summary", ""), "duration": e.get("duration"), "thumb": e.get("thumb", ""),
                 "watched": bool(e.get("viewCount")), "view_offset": e.get("viewOffset"),
                 "aired": e.get("originallyAvailableAt")} for e in await self.children(season_id)]

    async def up_next(self) -> list[dict]:
        out = []
        for m in (await self.on_deck())[:12]:
            ep = m.get("type") == "episode"
            out.append({"type": "library", "kind": "show" if ep else "movie",
                        "rating_key": str(m.get("grandparentRatingKey") or m.get("ratingKey")),
                        "play_key": str(m.get("ratingKey")),
                        "title": m.get("grandparentTitle") if ep else m.get("title"),
                        "thumb": m.get("grandparentThumb") if ep else m.get("thumb", ""),
                        "label": (f"S{int(m.get('parentIndex') or 0):02d}E{int(m.get('index') or 0):02d} {m.get('title', '')}"
                                  if ep else "Continue watching"), "reason": "On deck in Plex"})
        return out

    async def thumb(self, path: str, width: int) -> httpx.Response | None:
        if not THUMB_RE.fullmatch(path):
            return None
        return await self.get_raw("/photo/:/transcode",
                                  {"url": path, "width": width, "height": int(width * 1.5), "minSize": 1})

    async def metadata(self, rating_key: str) -> dict:
        items = _list(await self._get(f"/library/metadata/{rating_key}"), "Metadata")
        return items[0] if items else {}

    async def children(self, rating_key: str) -> list[dict]:
        return _list(await self._get(f"/library/metadata/{rating_key}/children"), "Metadata")

    async def on_deck(self) -> list[dict]:
        return _list(await self._get("/library/onDeck"), "Metadata")
