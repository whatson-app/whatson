"""Turning a search result into something playing on a TV: Plezy app links plus a check that
the TV is not already in use (a link replaces whatever is playing)."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

from .devices.base import TVDriver, TVStatus
from .sources.base import Session, Source

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


def is_on_tv(device: dict, address: str, player: str, device_id: str = "") -> bool:
    """Whether something a server reports is on this TV. A linked Jellyfin device decides it outright,
    because a server behind a proxy sees the proxy's address and an app's name can be anything."""
    linked = device.get("jellyfin_device")
    if linked and device_id:
        return device_id == linked
    return address == device["host"] or player.lower() in {device["name"].lower(), (device.get("plex_player") or "").lower()} - {""}


def on_tv(s: Session, device: dict) -> bool:
    return is_on_tv(device, s.player_address, s.player_title, s.device_id)


async def check_busy(driver: TVDriver, source: Source, device: dict) -> Availability:
    status = await driver.status(device["host"])
    if not status.reachable or status.error:
        return Availability(busy=False, reason=status.error, status=status)
    for s in (await source.playing() if source.configured else []):
        if s.state in ("playing", "buffering") and on_tv(s, device):
            what = "Live TV" if s.live else s.title
            return Availability(busy=True, status=status,
                                reason=f"{device['name']} is playing {what} in {s.product}.")
    if status.is_on and status.current_app not in IDLE_APPS and status.current_app != PLEZY:
        return Availability(busy=True, status=status,
                            reason=f"{device['name']} has {status.current_app} open.")
    return Availability(busy=False, status=status)
