"""What a media server gives WhatsOn, whichever one it is: channels, listings, library items, what's
playing, and the calls the routes need. WhatsOn reads one server at a time (Settings → Server).

Decisions: ADR 0012."""

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
class Episode:
    """One episode of a show in the library, kept so search can find an episode by its own title (ADR 0030)."""
    rating_key: str
    show_key: str                  # the show's rating_key in the library
    show_title: str
    season: int | None
    index: int | None
    title: str


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
    def configured(self) -> bool:
        """Whether enough is saved to call the server. Background refresh and the busy check skip an unconfigured
        source; other calls on one may raise."""

    async def server_id(self) -> str:
        """The id Plezy knows this server by; it goes into live and play links."""

    async def load_guide(self, start: int, end: int) -> tuple[list[Channel], list[Airing]]:
        """Channels, and listings overlapping this window (epoch seconds). Empty when the server has no Live TV."""

    async def library(self) -> list[LibraryItem]:
        """Every movie and show. Called on a slow timer; the result replaces the local copy."""

    async def library_episodes(self) -> list[Episode]:
        """Every episode's title, season and number, for search. Called right after library(); the result replaces
        the local copy. Keep each request light: this can be tens of thousands of episodes."""

    async def playing(self) -> list[Session]:
        """What's playing now. The busy check relies on this, so it must say which TV each session is on."""

    def valid_id(self, item_id: str) -> bool:
        """Whether this looks like one of the server's ids. The library routes check this before calling the server."""

    async def item(self, item_id: str) -> dict | None:
        """A movie or show's details for its page, with seasons for a show. None when the server returns nothing."""

    async def episodes(self, season_id: str) -> list[dict]:
        """A season's episodes."""

    async def up_next(self) -> list[dict]:
        """What to carry on watching, as library cards."""

    async def thumb(self, path: str, width: int) -> httpx.Response | None:
        """Fetch artwork for /api/thumb. Must accept only exact artwork paths and return None for anything else, so
        the proxy can't reach the rest of the server with its token."""
