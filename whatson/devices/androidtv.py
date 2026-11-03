"""Android TV / Google TV over the Android TV Remote protocol v2 (the protocol the Google TV
phone remote uses). No ADB or developer mode: pairing is a one-time code shown on the TV."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from androidtvremote2 import AndroidTVRemote, CannotConnect, ConnectionClosed, InvalidAuth
from zeroconf import ServiceStateChange
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

from .base import (FoundTV, PairingCancelled, PairingExpired, TVStatus, Unreachable, WrongCode)

CONNECT_TIMEOUT = 8
HOLD_SECONDS = 120         # keep a TV's connection open this long after the last remote press
PAIRING_TTL = 300          # forget a pairing attempt nobody finished after 5 minutes
MDNS_TYPE = "_androidtvremote2._tcp.local."


class NotPaired(Exception):
    pass


class AndroidTVDriver:
    kind = "androidtv"
    label = "Google TV / Android TV"

    def __init__(self, cert_dir: Path, client_name: str):
        cert_dir.mkdir(parents=True, exist_ok=True)
        # One client certificate for the whole app; each TV pairs with it once.
        self.certfile = str(cert_dir / "cert.pem")
        self.keyfile = str(cert_dir / "key.pem")
        self.client_name = client_name
        self._pairing: dict[str, tuple[AndroidTVRemote, float]] = {}
        # Connections kept open for the Remote tab: host -> [remote, last used]. Opening one costs a
        # TLS handshake (about a second), far too slow per d-pad press.
        self._held: dict[str, list] = {}
        self._held_locks: dict[str, asyncio.Lock] = {}

    def _remote(self, host: str) -> AndroidTVRemote:
        # enable_ime is what makes the TV report its foreground app (used by the busy check).
        return AndroidTVRemote(self.client_name, self.certfile, self.keyfile, host,
                               enable_ime=True, enable_voice=False)

    async def discover(self, seconds: float = 3.0) -> list[FoundTV]:
        azc = AsyncZeroconf()
        names: set[str] = set()

        def on_change(zeroconf, service_type, name, state_change):
            if state_change is ServiceStateChange.Added:
                names.add(name)

        browser = AsyncServiceBrowser(azc.zeroconf, [MDNS_TYPE], handlers=[on_change])
        try:
            await asyncio.sleep(seconds)
            found = []
            for name in sorted(names):
                # Announcements come from anything on the network: one malformed entry is skipped,
                # never allowed to break the scan.
                try:
                    info = AsyncServiceInfo(MDNS_TYPE, name)
                    if not await info.async_request(azc.zeroconf, 2000):
                        continue
                    v4 = [a for a in info.parsed_addresses() if ":" not in a]
                    if not v4:
                        continue
                    bt = (info.properties or {}).get(b"bt") or b""
                    found.append(FoundTV(name=name.removesuffix("." + MDNS_TYPE)[:100], host=v4[0],
                                         mac=bt.decode("utf-8", errors="replace")[:32]))
                except Exception:
                    continue
            return found
        finally:
            await browser.async_cancel()
            await azc.async_close()

    async def probe(self, host: str) -> FoundTV:
        remote = self._remote(host)
        try:
            await remote.async_generate_cert_if_missing()
            name, mac = await asyncio.wait_for(remote.async_get_name_and_mac(), CONNECT_TIMEOUT)
        except (CannotConnect, asyncio.TimeoutError, OSError) as exc:
            raise Unreachable(f"No Google TV answered at {host}. Is it on and on this network?") from exc
        return FoundTV(name=name, host=host, mac=mac)

    def _expire(self) -> None:
        now = time.monotonic()
        for host, (remote, started) in list(self._pairing.items()):
            if now - started > PAIRING_TTL:
                remote.disconnect()
                del self._pairing[host]

    async def start_pairing(self, host: str) -> None:
        self._expire()
        old = self._pairing.pop(host, None)
        if old:
            old[0].disconnect()
        remote = self._remote(host)
        await remote.async_generate_cert_if_missing()
        try:
            await asyncio.wait_for(remote.async_start_pairing(), CONNECT_TIMEOUT)
        except (CannotConnect, ConnectionClosed, asyncio.TimeoutError, OSError) as exc:
            remote.disconnect()
            raise Unreachable(f"Couldn't start pairing with {host}. Is the TV on?") from exc
        self._pairing[host] = (remote, time.monotonic())

    async def finish_pairing(self, host: str, code: str) -> None:
        self._expire()
        entry = self._pairing.pop(host, None)
        if not entry:
            raise PairingExpired("That pairing attempt timed out. Start again for a new code.")
        remote = entry[0]
        try:
            await remote.async_finish_pairing(code.strip().upper())
        except InvalidAuth as exc:
            raise WrongCode("That code didn't match the one on the TV.") from exc
        except ConnectionClosed as exc:
            raise PairingCancelled("The TV closed the pairing screen (cancelled or timed out).") from exc
        finally:
            remote.disconnect()

    async def _connected(self, host: str) -> AndroidTVRemote:
        remote = self._remote(host)
        try:
            await asyncio.wait_for(remote.async_connect(), CONNECT_TIMEOUT)
        except InvalidAuth as exc:
            remote.disconnect()
            raise NotPaired("This TV is not paired (or the pairing was removed on the TV).") from exc
        except Exception:
            remote.disconnect()
            raise
        return remote

    async def status(self, host: str) -> TVStatus:
        entry = self._held.get(host)
        if entry and self._alive(entry[0]):
            return TVStatus(reachable=True, is_on=entry[0].is_on, current_app=entry[0].current_app or "",
                            volume=dict(entry[0].volume_info) if entry[0].volume_info else None)
        try:
            remote = await self._connected(host)
        except NotPaired as exc:
            return TVStatus(reachable=True, error=str(exc))
        except (CannotConnect, ConnectionClosed, asyncio.TimeoutError, OSError) as exc:
            return TVStatus(reachable=False, error=f"Cannot reach the TV ({type(exc).__name__}).")
        try:
            # current_app arrives a moment after connect; give it up to 3 s.
            for _ in range(30):
                if remote.current_app:
                    break
                await asyncio.sleep(0.1)
            return TVStatus(reachable=True, is_on=remote.is_on, current_app=remote.current_app or "")
        finally:
            remote.disconnect()

    @staticmethod
    def _alive(remote: AndroidTVRemote) -> bool:
        proto = remote._remote_message_protocol
        return bool(proto and proto.transport and not proto.transport.is_closing())

    async def _held_remote(self, host: str) -> AndroidTVRemote:
        """An open connection to the TV, reused across presses and dropped after HOLD_SECONDS idle."""
        self.drop_idle()
        async with self._held_locks.setdefault(host, asyncio.Lock()):
            entry = self._held.get(host)
            if entry and self._alive(entry[0]):
                entry[1] = time.monotonic()
                return entry[0]
            if entry:
                entry[0].disconnect()
            remote = await self._connected(host)
            self._held[host] = [remote, time.monotonic()]
            return remote

    def drop_idle(self, max_idle: float = HOLD_SECONDS) -> None:
        now = time.monotonic()
        for host, (remote, used) in list(self._held.items()):
            if now - used > max_idle or not self._alive(remote):
                remote.disconnect()
                del self._held[host]

    async def _send(self, host: str, fn) -> None:
        """Run fn(remote) on the held connection; if the TV dropped it meanwhile, reconnect once."""
        for attempt in (1, 2):
            remote = await self._held_remote(host)
            try:
                fn(remote)
                return
            except ConnectionClosed:
                remote.disconnect()
                self._held.pop(host, None)
                if attempt == 2:
                    raise

    async def send_key(self, host: str, key: str, direction: str = "SHORT") -> None:
        """Press a remote key, e.g. DPAD_UP or MEDIA_PLAY_PAUSE. direction: SHORT, START_LONG, END_LONG."""
        await self._send(host, lambda r: r.send_key_command(key, direction))

    async def send_text(self, host: str, text: str) -> None:
        await self._send(host, lambda r: r.send_text(text))

    async def open_link(self, host: str, link: str) -> None:
        await self._send(host, lambda r: r.send_launch_app_command(link))
        await asyncio.sleep(0.3)  # let the message flush before anyone checks the result

    async def live(self, host: str) -> TVStatus:
        """State from the held connection (the TV pushes changes), opening one if needed."""
        try:
            remote = await self._held_remote(host)
        except NotPaired as exc:
            return TVStatus(reachable=True, error=str(exc))
        except (CannotConnect, ConnectionClosed, asyncio.TimeoutError, OSError) as exc:
            return TVStatus(reachable=False, error=f"Cannot reach the TV ({type(exc).__name__}).")
        for _ in range(30):
            if remote.current_app:
                break
            await asyncio.sleep(0.1)
        return TVStatus(reachable=True, is_on=remote.is_on, current_app=remote.current_app or "",
                        volume=dict(remote.volume_info) if remote.volume_info else None)
