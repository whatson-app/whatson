"""Jellyfin server: its Live TV guide and library, the clients playing on it, and remote control of
those that allow it.

Uses the server's Sessions API for what's playing, so it works for the official Jellyfin apps and for
third-party ones (Plezy, Kodi + Jellyfin add-on, Moonfin, ...); remote control needs the app to report
SupportsRemoteControl. Watched status and up next belong to one Jellyfin user (Settings → Jellyfin)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from .base import Airing, Channel, Episode, LibraryItem, Session, classify

TICKS_PER_MS = 10_000
COMMANDS = {"PlayPause", "Pause", "Unpause", "Stop", "NextTrack", "PreviousTrack", "Seek"}
PAGE = 500
SLOW = 120            # seconds: asking for cast on 500 titles takes a few seconds on a big library
ID_RE = re.compile(r"[0-9a-fA-F]{32}")
# Only exact artwork paths, so /api/thumb can't be used to reach anything else on the server.
THUMB_RE = re.compile(r"/Items/[0-9a-fA-F]{32}/Images/Primary")


class JellyfinError(Exception):
    pass


@dataclass
class JellyfinSession:
    id: str
    client: str           # app name, e.g. "Jellyfin Android TV"
    device: str           # device name the app reports
    address: str          # IP the server sees it on
    controllable: bool
    title: str = ""
    subtitle: str = ""
    kind: str = ""
    paused: bool = False
    position: int = 0     # ms
    duration: int = 0     # ms
    device_id: str = ""


def _ip(endpoint: str) -> str:
    """"192.168.1.5", "192.168.1.5:5000" or "::ffff:192.168.1.5" -> "192.168.1.5"."""
    endpoint = endpoint.removeprefix("::ffff:")
    return endpoint.rsplit(":", 1)[0] if endpoint.count(":") == 1 else endpoint


def _ts(iso: str | None) -> int:
    """Jellyfin's dates have seven decimal places and are in UTC, so only the first 19 characters count."""
    try:
        return int(datetime.fromisoformat((iso or "")[:19]).replace(tzinfo=timezone.utc).timestamp())
    except ValueError:
        return 0


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _image(item_id: str | None) -> str:
    return f"/Items/{item_id}/Images/Primary" if item_id else ""


def _poster(item: dict) -> str:
    return _image(item.get("Id")) if (item.get("ImageTags") or {}).get("Primary") else ""


def _ms(item: dict) -> int:
    return int(item.get("RunTimeTicks") or 0) // TICKS_PER_MS


def _episode_label(item: dict) -> str:
    se, ep = item.get("ParentIndexNumber"), item.get("IndexNumber")
    return (f"S{se:02d}E{ep:02d} " if isinstance(se, int) and isinstance(ep, int) else "") + (item.get("Name") or "")


def _guids(ids: dict) -> list[str]:
    """{"Imdb": "tt1", "Tmdb": "2", "TvdbSlug": "x"} -> ["imdb:tt1", "tmdb:2"], as Plex items have them."""
    wanted = {k.lower(): v for k, v in (ids or {}).items() if k.lower() in ("imdb", "tmdb", "tvdb") and v}
    return [f"{k}:{v}" for k, v in wanted.items()]


def _library_item(m: dict) -> LibraryItem:
    show = m.get("Type") == "Series"
    user = m.get("UserData") or {}
    leaves = int(m.get("RecursiveItemCount") or 0)
    return LibraryItem(
        rating_key=m["Id"], kind="show" if show else "movie", title=m.get("Name", ""), year=m.get("ProductionYear"),
        summary=m.get("Overview") or "", genres=m.get("Genres") or [],
        people=[p.get("Name", "") for p in (m.get("People") or [])[:12]], thumb=_poster(m),
        added_at=_ts(m.get("DateCreated")), duration=_ms(m), content_rating=m.get("OfficialRating") or "",
        audience_rating=m.get("CommunityRating"), watched=bool(user.get("Played")), leaf_count=leaves if show else 0,
        viewed_leaf_count=max(0, leaves - int(user.get("UnplayedItemCount") or 0)) if show else 0,
        guids=_guids(m.get("ProviderIds")))


def _airing(p: dict) -> Airing:
    title, genres = p.get("Name", ""), list(p.get("Genres") or [])
    if p.get("IsSports"):
        genres.append("Sports")
    summary = p.get("Overview") or ""
    sub = p.get("EpisodeTitle") or ""
    se, ep = p.get("ParentIndexNumber"), p.get("IndexNumber")
    if se and ep:
        sub = f"S{int(se):02d}E{int(ep):02d} {sub}".strip()
    media_type = "movie" if p.get("IsMovie") else "episode" if p.get("IsSeries") else ""
    return Airing(p.get("ChannelId", ""), title, sub, summary, classify(title, summary, media_type, genres),
                  _ts(p.get("StartDate")), _ts(p.get("EndDate")), p.get("ProductionYear"))


class Jellyfin:
    name, label = "jellyfin", "Jellyfin"

    def __init__(self, url: str, key: str, http: httpx.AsyncClient, user_id: str = ""):
        self.url, self.key, self.http, self.user_id = url.rstrip("/"), key, http, user_id

    @property
    def configured(self) -> bool:
        return bool(self.url and self.key)

    def headers(self) -> dict:
        return {"Accept": "application/json",
                "Authorization": f'MediaBrowser Client="WhatsOn", Device="WhatsOn", DeviceId="whatson", '
                                 f'Version="1", Token="{self.key}"'}

    async def _call(self, method: str, path: str, timeout: float = 10, **kw):
        try:
            r = await self.http.request(method, f"{self.url}{path}", headers=self.headers(), timeout=timeout, **kw)
        except httpx.HTTPError as exc:
            raise JellyfinError(f"No answer from {self.url} ({type(exc).__name__})") from exc
        if r.status_code in (401, 403):
            raise JellyfinError("Jellyfin refused the API key")
        if r.status_code >= 400:
            raise JellyfinError(f"Jellyfin said HTTP {r.status_code}")
        return r.json() if r.content and "json" in r.headers.get("content-type", "") else None

    def _user(self) -> dict:
        return {"userId": self.user_id} if self.user_id else {}

    async def _pages(self, path: str, **params) -> list[dict]:
        out: list[dict] = []
        while True:
            res = await self._call("GET", path, timeout=SLOW, params={**params, "StartIndex": len(out), "Limit": PAGE})
            items = (res or {}).get("Items") or []
            out += items
            if len(items) < PAGE:
                return out

    async def info(self) -> dict:
        i = await self._call("GET", "/System/Info")
        return {"name": (i or {}).get("ServerName", ""), "version": (i or {}).get("Version", ""),
                "id": (i or {}).get("Id", "")}

    async def server_id(self) -> str:
        return (await self.info())["id"]

    async def users(self) -> list[dict]:
        return [{"id": u.get("Id", ""), "name": u.get("Name", "")} for u in await self._call("GET", "/Users") or []]

    async def plezy_devices(self) -> list[dict]:
        """Plezy installs that have signed in to this server, for linking one to each TV."""
        res = await self._call("GET", "/Devices") or {}
        return [{"id": d.get("Id", ""), "name": d.get("CustomName") or d.get("Name", ""), "user": d.get("LastUserName", "")}
                for d in res.get("Items") or [] if "plezy" in (d.get("AppName") or "").lower()]

    async def load_guide(self, start: int, end: int) -> tuple[list[Channel], list[Airing]]:
        rows = await self._pages("/LiveTv/Channels", **self._user())
        if not rows:
            return [], []
        channels = []
        for c in rows:
            # Channel art is used as an address as it stands, so it's stored as WhatsOn's own proxy link.
            art = _poster(c)
            channels.append(Channel(id=c["Id"], vcn=str(c.get("ChannelNumber") or c.get("Number") or c["Id"]),
                                    title=c.get("Name", ""),
                                    thumb=f"/api/thumb?path={quote(art, safe='')}&width=120" if art else ""))
        programs = await self._pages("/LiveTv/Programs", MinEndDate=_iso(start), MaxStartDate=_iso(end),
                                     Fields="Overview,Genres", EnableImages="false", EnableUserData="false",
                                     **self._user())
        return channels, [_airing(p) for p in programs if p.get("ChannelId")]

    async def library(self) -> list[LibraryItem]:
        rows = await self._pages("/Items", Recursive="true", IncludeItemTypes="Movie,Series",
                                 Fields="Overview,Genres,People,ProviderIds,DateCreated,OfficialRating,RecursiveItemCount",
                                 **self._user())
        return [_library_item(m) for m in rows]

    async def library_episodes(self) -> list[Episode]:
        rows = await self._pages("/Items", Recursive="true", IncludeItemTypes="Episode", EnableImages="false",
                                 EnableUserData="false", **self._user())
        return [Episode(rating_key=m["Id"], show_key=m["SeriesId"], show_title=m.get("SeriesName") or "",
                        season=m.get("ParentIndexNumber"), index=m.get("IndexNumber"), title=m["Name"])
                for m in rows if m.get("Id") and m.get("SeriesId") and m.get("Name")]

    async def sessions(self) -> list[JellyfinSession]:
        out = []
        for s in await self._call("GET", "/Sessions", params={"activeWithinSeconds": 900}) or []:
            if s.get("Client") == "WhatsOn":
                continue
            item, play = s.get("NowPlayingItem") or {}, s.get("PlayState") or {}
            out.append(JellyfinSession(
                id=s.get("Id", ""), client=s.get("Client", ""), device=s.get("DeviceName", ""),
                address=_ip(s.get("RemoteEndPoint") or ""),
                controllable=bool(s.get("SupportsRemoteControl")),
                title=item.get("SeriesName") or item.get("Name", ""),
                subtitle=_episode_label(item) if item.get("SeriesName") else "", kind=(item.get("Type") or "").lower(),
                paused=bool(play.get("IsPaused")), position=int(play.get("PositionTicks") or 0) // TICKS_PER_MS,
                duration=_ms(item), device_id=s.get("DeviceId", "")))
        return out

    async def playing(self) -> list[Session]:
        """Only sessions with something playing: an app that's merely signed in is listed too, with no item."""
        out = []
        for s in await self._call("GET", "/Sessions", params={"activeWithinSeconds": 900}) or []:
            item, play = s.get("NowPlayingItem"), s.get("PlayState") or {}
            if not item or s.get("Client") == "WhatsOn":
                continue
            kind = {"TvChannel": "live", "Episode": "episode", "Movie": "movie"}.get(item.get("Type"), "")
            out.append(Session(
                player_title=s.get("DeviceName", ""), player_address=_ip(s.get("RemoteEndPoint") or ""),
                product=s.get("Client", ""), state="paused" if play.get("IsPaused") else "playing",
                title=item.get("SeriesName") or item.get("Name", ""), live=kind == "live", kind=kind,
                show=item.get("SeriesName") or "", episode=_episode_label(item) if kind == "episode" else "",
                rating_key=item.get("Id", ""), show_key=item.get("SeriesId") or "",
                thumb=_image(item.get("SeriesId") or item.get("Id")),
                offset=int(play.get("PositionTicks") or 0) // TICKS_PER_MS, duration=_ms(item),
                channel_id=item.get("Id", "") if kind == "live" else "", device_id=s.get("DeviceId", "")))
        return out

    def valid_id(self, item_id: str) -> bool:
        return bool(ID_RE.fullmatch(item_id))

    async def item(self, item_id: str) -> dict | None:
        res = await self._call("GET", "/Items", params={"ids": item_id, "Fields": "Overview,Genres,People,Studios",
                                                        **self._user()}) or {}
        items = res.get("Items") or []
        if not items:
            return None
        m, user = items[0], items[0].get("UserData") or {}
        show = m.get("Type") == "Series"
        offset = int(user.get("PlaybackPositionTicks") or 0) // TICKS_PER_MS
        out = {"rating_key": item_id, "kind": "show" if show else "movie", "title": m.get("Name"),
               "year": m.get("ProductionYear"), "summary": m.get("Overview") or "", "duration": _ms(m),
               "content_rating": m.get("OfficialRating") or "", "audience_rating": m.get("CommunityRating"),
               "thumb": _poster(m), "art": "", "genres": m.get("Genres") or [],
               "cast": [p.get("Name") for p in m.get("People") or [] if p.get("Type") == "Actor"][:8],
               "studio": ((m.get("Studios") or [{}])[0]).get("Name", ""), "view_offset": offset or None,
               "watched": bool(user.get("Played"))}
        if show:
            res = await self._call("GET", f"/Shows/{item_id}/Seasons", params={"Fields": "ChildCount", **self._user()}) or {}
            out["seasons"] = []
            for s in res.get("Items") or []:
                count = int(s.get("ChildCount") or 0)
                out["seasons"].append({
                    "rating_key": s["Id"], "index": s.get("IndexNumber"), "title": s.get("Name"), "thumb": _poster(s),
                    "episodes": count,
                    "watched": max(0, count - int((s.get("UserData") or {}).get("UnplayedItemCount") or 0))})
        return out

    async def episodes(self, season_id: str) -> list[dict]:
        res = await self._call("GET", "/Items", params={"ParentId": season_id, "IncludeItemTypes": "Episode",
                                                        "Fields": "Overview", **self._user()}) or {}
        rows = sorted(res.get("Items") or [], key=lambda e: e.get("IndexNumber") or 0)
        return [{"rating_key": e["Id"], "index": e.get("IndexNumber"), "title": e.get("Name"),
                 "summary": e.get("Overview") or "", "duration": _ms(e), "thumb": _poster(e),
                 "watched": bool((e.get("UserData") or {}).get("Played")),
                 "view_offset": int((e.get("UserData") or {}).get("PlaybackPositionTicks") or 0) // TICKS_PER_MS or None,
                 "aired": (e.get("PremiereDate") or "")[:10] or None} for e in rows]

    async def up_next(self) -> list[dict]:
        """Things in progress first, then the next episode of each show, one card per title."""
        if not self.user_id:
            return []
        started = await self._call("GET", "/UserItems/Resume", params={"mediaTypes": "Video", "Limit": 12, **self._user()}) or {}
        following = await self._call("GET", "/Shows/NextUp", params={"Limit": 12, **self._user()}) or {}
        out: dict[str, dict] = {}
        for m in (started.get("Items") or []) + (following.get("Items") or []):
            ep = m.get("Type") == "Episode"
            key = (m.get("SeriesId") if ep else m.get("Id")) or ""
            if key and key not in out:
                out[key] = {"type": "library", "kind": "show" if ep else "movie", "rating_key": key, "play_key": m.get("Id"),
                            "title": m.get("SeriesName") if ep else m.get("Name"), "thumb": _image(key),
                            "label": _episode_label(m) if ep else "Continue watching", "reason": "Up next in Jellyfin"}
        return list(out.values())[:12]

    async def thumb(self, path: str, width: int) -> httpx.Response | None:
        if not THUMB_RE.fullmatch(path):
            return None
        try:
            return await self.http.get(f"{self.url}{path}", params={"maxWidth": width}, headers=self.headers(), timeout=30)
        except httpx.HTTPError as exc:
            raise JellyfinError(f"No answer from {self.url} ({type(exc).__name__})") from exc

    async def command(self, session_id: str, command: str, position_ms: int | None = None) -> None:
        if command not in COMMANDS:
            raise JellyfinError(f"Unknown command {command}")
        params = {"seekPositionTicks": max(0, position_ms) * TICKS_PER_MS} if command == "Seek" and position_ms is not None else {}
        await self._call("POST", f"/Sessions/{session_id}/Playing/{command}", params=params)
