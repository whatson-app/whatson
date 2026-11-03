"""TV apps the Remote tab knows how to show and open, and which ones each TV has.

A TV can't list its installed apps over the remote protocol, so each TV's list is built from apps
WhatsOn has seen in front on it, plus the ones the person ticks. Apps open by link where one is known;
otherwise by package name, which Google TV refuses (Aug 2026 Play Store update) but older Android TV
devices such as the Shield may still accept."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class App:
    id: str
    name: str
    package: str
    link: str = ""       # deep link that opens the app; "" = only the package route
    color: str = "#22262e"
    badge: str = ""


CATALOG = [
    App("plezy", "Plezy", "com.edde746.plezy", "plezy://open", "#e5a00d", "Pz"),
    App("plex", "Plex", "com.plexapp.android", "plex://", "#282a2d", "P"),
    App("youtube", "YouTube", "com.google.android.youtube.tv", "https://www.youtube.com", "#ff0000", "▶"),
    App("netflix", "Netflix", "com.netflix.ninja", "https://www.netflix.com/title", "#000000", "N"),
    App("prime", "Prime Video", "com.amazon.amazonvideo.livingroom", "https://app.primevideo.com", "#00a8e1", "pv"),
    App("disney", "Disney+", "com.disney.disneyplus", "https://www.disneyplus.com", "#113ccf", "D+"),
    App("max", "Max", "com.wbd.stream", "https://play.max.com", "#002be7", "M"),
    App("hulu", "Hulu", "com.hulu.livingroomplus", "https://www.hulu.com", "#1ce783", "h"),
    App("paramount", "Paramount+", "com.cbs.ott", "https://www.paramountplus.com", "#0064ff", "P+"),
    App("peacock", "Peacock", "com.peacocktv.peacockandroid", "https://www.peacocktv.com", "#111111", "Pk"),
    App("appletv", "Apple TV", "com.apple.atve.androidtv.appletv", "https://tv.apple.com", "#111111", "tv"),
    App("youtubetv", "YouTube TV", "com.google.android.apps.youtube.unplugged", "https://tv.youtube.com", "#ff0000", "YT"),
    App("spotify", "Spotify", "com.spotify.tv.android", "spotify://", "#1db954", "S"),
    App("jellyfin", "Jellyfin", "org.jellyfin.androidtv", "", "#00a4dc", "J"),
    App("kodi", "Kodi", "org.xbmc.kodi", "", "#17b2e7", "K"),
    App("pbskids", "PBS Kids", "org.pbskids.video", "", "#2638c4", "PK"),
]
# Parts of the TV itself: named when they're in front, but not apps to put on the row.
SYSTEM = {"com.android.tv.settings": "Settings", "com.google.android.katniss": "Google Assistant",
          "com.android.systemui": "System", "com.google.android.apps.tv.dreamx": "Screensaver"}
BY_PACKAGE = {a.package: a for a in CATALOG}
BY_ID = {a.id: a for a in CATALOG}
DEFAULT = ("plezy", "plex", "youtube")   # shown until a TV has seen or ticked anything


def name_of(package: str) -> str:
    a = BY_PACKAGE.get(package)
    if a or not package:
        return a.name if a else package
    return SYSTEM.get(package) or _unknown(package).name


def _unknown(package: str) -> App:
    # A package WhatsOn saw on the TV but doesn't know: name it from the last dotted part.
    tail = package.rsplit(".", 1)[-1] or package
    return App(package, tail[:1].upper() + tail[1:], package, "", "#22262e", tail[:2].upper())


def note_seen(conn: sqlite3.Connection, device_id: int, package: str, idle: set[str]) -> None:
    if not package or package in idle or package in SYSTEM:
        return
    conn.execute("""INSERT INTO tv_apps (device_id, package, seen_at) VALUES (?, ?, ?)
                    ON CONFLICT (device_id, package) DO UPDATE SET seen_at = excluded.seen_at""",
                 (device_id, package, int(time.time())))


def set_picked(conn: sqlite3.Connection, device_id: int, package: str, picked: bool) -> None:
    conn.execute("""INSERT INTO tv_apps (device_id, package, picked) VALUES (?, ?, ?)
                    ON CONFLICT (device_id, package) DO UPDATE SET picked = excluded.picked""",
                 (device_id, package, int(picked)))


def for_tv(conn: sqlite3.Connection, device_id: int) -> list[dict]:
    """Every app worth listing for this TV: catalogue entries plus anything seen there.
    `shown` = on the Apps row (ticked, or seen and not unticked)."""
    rows = {r["package"]: r for r in conn.execute("SELECT * FROM tv_apps WHERE device_id = ?", (device_id,))}
    anything = any(r["seen_at"] or r["picked"] is not None for r in rows.values())
    out = []
    for a in CATALOG + [_unknown(p) for p in rows if p not in BY_PACKAGE and p not in SYSTEM]:
        r = rows.get(a.package)
        seen = r["seen_at"] if r else 0
        picked = r["picked"] if r else None
        shown = bool(picked) if picked is not None else bool(seen) or (not anything and a.id in DEFAULT)
        out.append({**asdict(a), "seen_at": seen or 0, "shown": shown, "by_link": bool(a.link)})
    # Shown first (Plezy leads), then most recently seen, then catalogue order.
    order = {a["id"]: i for i, a in enumerate(out)}
    out.sort(key=lambda a: (not a["shown"], a["id"] != "plezy", -a["seen_at"], order[a["id"]]))
    return out
