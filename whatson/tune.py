"""Turning a search result into something playing on a TV: Plezy app links plus a check that
the TV is not already in use (a link replaces whatever is playing)."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

from .devices.base import TVDriver, TVStatus
from .sources.plex import PlexClient

# Home screens and screensavers: a TV showing one of these is free to take over.
IDLE_APPS = {
    "com.google.android.apps.tv.launcherx", "com.google.android.tvlauncher",
    "com.google.android.leanbacklauncher", "com.spocky.projengmenu", "com.gathin.tvhome",
    "com.google.android.backdrop", "com.android.systemui", "com.google.android.apps.tv.dreamx",
    "com.amazon.tv.launcher", "com.neilturner.aerialviews", "",
}
PLEZY = "com.edde746.plezy"


def live_link(channel: str, server: str = "") -> str:
    # start=live skips Plezy's "watch from the beginning?" prompt on channels already streaming.
    params = {"channel": channel, "start": "live"}
    if server:
        params["server"] = server
    return "plezy://live?" + urlencode(params)


def open_link() -> str:
    return "plezy://open"


def play_link(server: str, rating_key: str) -> str:
    return "plezy://play?" + urlencode({"server": server, "id": rating_key})


@dataclass
class Availability:
    busy: bool
    reason: str = ""
    status: TVStatus | None = None


async def check_busy(driver: TVDriver, plex: PlexClient, device: dict) -> Availability:
    status = await driver.status(device["host"])
    if not status.reachable or status.error:
        return Availability(busy=False, reason=status.error, status=status)
    player = (device.get("plex_player") or device["name"]).lower()
    for s in (await plex.sessions() if plex.configured else []):
        if s.state in ("playing", "buffering") and (
                s.player_title.lower() == player or s.player_address == device["host"]):
            what = "Live TV" if s.live else s.title
            return Availability(busy=True, status=status,
                                reason=f"{device['name']} is playing {what} in {s.product}.")
    if status.is_on and status.current_app not in IDLE_APPS and status.current_app != PLEZY:
        return Availability(busy=True, status=status,
                            reason=f"{device['name']} has {status.current_app} open.")
    return Availability(busy=False, status=status)
