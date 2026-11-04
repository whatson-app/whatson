"""Connections to addresses people type in Settings (AI server, Radarr, Sonarr, Plex).

The rules: http(s) only, LAN and loopback allowed, never link-local or cloud-metadata addresses.
`check_base_url` applies them when an address is saved. `PinnedTransport` applies them again on every
request and then connects to the exact IP it checked, so a name that later resolves somewhere else
(DNS rebinding) can't slip past the check made at save time.

Decisions: ADR 0008."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from urllib.parse import urlparse

import httpx

# Cloud metadata endpoints outside the link-local range (AWS IPv6, Alibaba).
METADATA_NETS = (ipaddress.ip_network("fd00:ec2::254/128"), ipaddress.ip_network("100.100.100.200/32"))
WRAPPING_NETS = (ipaddress.ip_network("64:ff9b::/96"), ipaddress.ip_network("64:ff9b:1::/48"))
CACHE_SECONDS = 60


def allowed_ips(host: str, port: int) -> list[str]:
    """Every address `host` resolves to, if all of them are allowed. Raises ValueError otherwise."""
    host = host.rstrip(".").lower()
    if host in ("metadata", "metadata.google.internal"):
        raise ValueError("That address isn't allowed")
    # Check every address the name resolves to (this also catches numeric forms like 2852039166).
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError) as exc:
        raise ValueError(f"Can't find a server called {host}") from exc
    out = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if getattr(ip, "ipv4_mapped", None):
            ip = ip.ipv4_mapped
        if not ip.is_loopback:  # loopback = a server on the same box, which is fine
            # IPv6 forms that wrap an IPv4 address (6to4, Teredo, NAT64) could hide a metadata
            # address; a home server never needs them, so refuse them outright.
            if ip.version == 6 and (ip.sixtofour or ip.teredo or any(ip in net for net in WRAPPING_NETS)):
                raise ValueError("That address isn't allowed")
            if (ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved
                    or any(ip in net for net in METADATA_NETS)):
                raise ValueError("That address isn't allowed")
        out.append(str(ip))
    return list(dict.fromkeys(out))


def check_base_url(base_url: str) -> None:
    if not base_url:
        return
    u = urlparse(base_url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("The address must start with http:// or https:// and name a server")
    allowed_ips(u.hostname, u.port or (443 if u.scheme == "https" else 80))


class PinnedTransport(httpx.AsyncHTTPTransport):
    """Checks the address on every request and connects to the checked IP. HTTPS still verifies the
    certificate against the name (sent as SNI), so plex.direct and other real certificates work."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self._cache: dict[tuple[str, int], tuple[str, float]] = {}

    async def _ip(self, host: str, port: int) -> str:
        hit = self._cache.get((host, port))
        if hit and hit[1] > time.monotonic():
            return hit[0]
        try:
            ips = await asyncio.wait_for(asyncio.to_thread(allowed_ips, host, port), 5)
        except asyncio.TimeoutError as exc:
            raise ValueError(f"Looking up {host} took too long") from exc
        self._cache[(host, port)] = (ips[0], time.monotonic() + CACHE_SECONDS)
        return ips[0]

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        if url.scheme not in ("http", "https"):
            raise httpx.UnsupportedProtocol(f"{url.scheme} isn't allowed", request=request)
        host = url.host
        try:
            ip = await self._ip(host, url.port or (443 if url.scheme == "https" else 80))
        except ValueError as exc:
            raise httpx.ConnectError(str(exc), request=request) from exc
        if ip != host:
            # The Host header was set when the request was built, so the server still sees the name.
            request.url = url.copy_with(host=ip)
            if url.scheme == "https":
                request.extensions = {**request.extensions, "sni_hostname": host}
        return await super().handle_async_request(request)


def client(**kw) -> httpx.AsyncClient:
    """An httpx client for user-typed addresses: pinned, and never following redirects."""
    return httpx.AsyncClient(transport=PinnedTransport(), follow_redirects=False, **kw)
