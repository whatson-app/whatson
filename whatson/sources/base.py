"""What a media server gives WhatsOn, whichever one it is: channels, listings, library items, what's
playing, and the calls the routes need. WhatsOn reads one server at a time (Settings → Source)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

import httpx

SPORTS_RE = re.compile(
    r"\b(football|basketball|baseball|hockey|soccer|NFL|NBA|WNBA|MLB|NHL|MLS|NCAA[FBM]?|"
    r"college (?:football|basketball)|premier league|la liga|bundesliga|serie a|"
    r"champions league|EFL|UFC|boxing|wrestling|golf|PGA|tennis|NASCAR|formula 1|F1|"
    r"rugby|cricket|volleyball|softball|lacrosse|world series|stanley cup|super bowl|"
    r"march madness|playoffs?|grand prix|olympics|racing|darts|snooker)\b",
    re.I,
)


@dataclass
class Channel:
    id: str
    vcn: str
    title: str
    callsign: str = ""
    thumb: str = ""


@dataclass
class Airing:
    channel_id: str
    title: str
    subtitle: str
    summary: str
    kind: str
    begins: int
    ends: int
    year: int | None = None


@dataclass
class LibraryItem:
    rating_key: str
    kind: str
    title: str
    year: int | None
    summary: str
    genres: list[str] = field(default_factory=list)
    people: list[str] = field(default_factory=list)
    thumb: str = ""
    section: str = ""
    added_at: int = 0
    duration: int = 0
    content_rating: str = ""
    audience_rating: float | None = None
    watched: bool = False
    leaf_count: int = 0
    viewed_leaf_count: int = 0
    guids: list[str] = field(default_factory=list)


@dataclass
class Session:
    player_title: str
    player_address: str
    product: str
    state: str
    title: str
    live: bool
    kind: str = ""                 # movie | episode | live
    show: str = ""
    episode: str = ""              # "S02E05 Blue Mountains"
    rating_key: str = ""
    show_key: str = ""
    thumb: str = ""
    offset: int = 0                # ms
    duration: int = 0              # ms
    key: str = ""
    channel_id: str = ""           # Live TV, when the server says which channel
    device_id: str = ""            # the server's id for this app on this TV, when it has one


def classify(title: str, summary: str, media_type: str, genres: list[str]) -> str:
    text = f"{title} {summary} {' '.join(genres)}"
    if any(g.lower() == "sports" for g in genres) or SPORTS_RE.search(text):
        return "sports"
    if media_type == "episode":
        return "episode"
    if media_type == "movie":
        # Plex labels many XMLTV airings "movie"; only call it a film if it looks like one.
        return "movie" if not title.lower().startswith("live:") else "other"
    return "other"


class Source(Protocol):
    name: str                      # "plex" | "jellyfin"
    label: str                     # as people see it

    @property
    def configured(self) -> bool: ...
    async def server_id(self) -> str: ...
    async def load_guide(self, start: int, end: int) -> tuple[list[Channel], list[Airing]]: ...
    async def library(self) -> list[LibraryItem]: ...
    async def playing(self) -> list[Session]: ...
    def valid_id(self, item_id: str) -> bool: ...
    async def item(self, item_id: str) -> dict | None: ...
    async def episodes(self, season_id: str) -> list[dict]: ...
    async def up_next(self) -> list[dict]: ...
    async def thumb(self, path: str, width: int) -> httpx.Response | None: ...
