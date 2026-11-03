"""What every TV driver provides. Phase 1 ships Android TV / Google TV; Roku, Fire TV and
others plug in here later."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class TVStatus:
    reachable: bool
    is_on: bool | None = None
    current_app: str = ""
    error: str = ""
    volume: dict | None = None     # {"level", "max", "muted"} when the TV reports it


@dataclass
class FoundTV:
    name: str
    host: str
    model: str = ""
    mac: str = ""


class PairingError(Exception):
    """Pairing failed in a way the wizard explains to the person. `code` is stable for the UI."""

    code = "failed"


class WrongCode(PairingError):
    code = "wrong_code"


class PairingCancelled(PairingError):
    code = "cancelled"


class Unreachable(PairingError):
    code = "unreachable"


class PairingExpired(PairingError):
    code = "expired"


class TVDriver(Protocol):
    kind: str
    label: str

    async def discover(self, seconds: float = 3.0) -> list[FoundTV]:
        """TVs of this kind announcing themselves on the local network."""

    async def probe(self, host: str) -> FoundTV:
        """Check a TV answers at host and read its name; raises Unreachable."""

    async def start_pairing(self, host: str) -> None:
        """Begin pairing; the TV shows a code."""

    async def finish_pairing(self, host: str, code: str) -> None:
        """Complete pairing with the code shown on the TV; raises a PairingError subclass."""

    async def status(self, host: str) -> TVStatus:
        ...

    async def send_key(self, host: str, key: str, direction: str = "SHORT") -> None:
        """Press a remote key (DPAD_UP, MEDIA_PLAY_PAUSE, VOLUME_UP, ...); START_LONG/END_LONG hold it."""

    async def send_text(self, host: str, text: str) -> None:
        """Type text into whatever field has focus on the TV."""

    async def live(self, host: str) -> TVStatus:
        """Like status(), over a connection kept open for the Remote tab; includes volume."""

    async def open_link(self, host: str, link: str) -> None:
        """Open an app link (for example plezy://live?channel=706) on the TV."""
