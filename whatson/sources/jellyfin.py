"""Jellyfin server: the clients playing on it and remote control of those that allow it.

Uses the server's Sessions API, so it works for the official Jellyfin apps and for third-party ones
(Kodi + Jellyfin add-on, Moonfin, ...) as long as the app reports SupportsRemoteControl."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

TICKS_PER_MS = 10_000
COMMANDS = {"PlayPause", "Pause", "Unpause", "Stop", "NextTrack", "PreviousTrack", "Seek"}


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


def _ip(endpoint: str) -> str:
    """"192.168.1.5", "192.168.1.5:5000" or "::ffff:192.168.1.5" -> "192.168.1.5"."""
    endpoint = endpoint.removeprefix("::ffff:")
    return endpoint.rsplit(":", 1)[0] if endpoint.count(":") == 1 else endpoint


class Jellyfin:
    def __init__(self, url: str, key: str, http: httpx.AsyncClient):
        self.url, self.key, self.http = url.rstrip("/"), key, http

    def headers(self) -> dict:
        return {"Accept": "application/json",
                "Authorization": f'MediaBrowser Client="WhatsOn", Device="WhatsOn", DeviceId="whatson", '
                                 f'Version="1", Token="{self.key}"'}

    async def _call(self, method: str, path: str, **kw):
        try:
            r = await self.http.request(method, f"{self.url}{path}", headers=self.headers(), timeout=10, **kw)
        except httpx.HTTPError as exc:
            raise JellyfinError(f"No answer from {self.url} ({type(exc).__name__})") from exc
        if r.status_code in (401, 403):
            raise JellyfinError("Jellyfin refused the API key")
        if r.status_code >= 400:
            raise JellyfinError(f"Jellyfin said HTTP {r.status_code}")
        return r.json() if r.content and "json" in r.headers.get("content-type", "") else None

    async def info(self) -> dict:
        i = await self._call("GET", "/System/Info")
        return {"name": (i or {}).get("ServerName", ""), "version": (i or {}).get("Version", "")}

    async def sessions(self) -> list[JellyfinSession]:
        out = []
        for s in await self._call("GET", "/Sessions", params={"activeWithinSeconds": 900}) or []:
            if s.get("Client") == "WhatsOn":
                continue
            item, play = s.get("NowPlayingItem") or {}, s.get("PlayState") or {}
            sub = ""
            if item.get("SeriesName"):
                se, ep = item.get("ParentIndexNumber"), item.get("IndexNumber")
                sub = (f"S{se:02d}E{ep:02d} " if isinstance(se, int) and isinstance(ep, int) else "") + item.get("Name", "")
            out.append(JellyfinSession(
                id=s.get("Id", ""), client=s.get("Client", ""), device=s.get("DeviceName", ""),
                address=_ip(s.get("RemoteEndPoint") or ""),
                controllable=bool(s.get("SupportsRemoteControl")),
                title=item.get("SeriesName") or item.get("Name", ""), subtitle=sub, kind=(item.get("Type") or "").lower(),
                paused=bool(play.get("IsPaused")), position=int(play.get("PositionTicks") or 0) // TICKS_PER_MS,
                duration=int(item.get("RunTimeTicks") or 0) // TICKS_PER_MS))
        return out

    async def command(self, session_id: str, command: str, position_ms: int | None = None) -> None:
        if command not in COMMANDS:
            raise JellyfinError(f"Unknown command {command}")
        params = {"seekPositionTicks": max(0, position_ms) * TICKS_PER_MS} if command == "Seek" and position_ms is not None else {}
        await self._call("POST", f"/Sessions/{session_id}/Playing/{command}", params=params)
