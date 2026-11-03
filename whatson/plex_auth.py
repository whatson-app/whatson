"""Connecting WhatsOn to a Plex server: Sign in with Plex, a pasted token, or PLEX_URL/PLEX_TOKEN.

Sign-in uses Plex's JWT flow (developer.plex.tv/pms, "Authenticating with Plex"): WhatsOn has its own
Ed25519 key, the person approves a PIN on plex.tv, and plex.tv issues a 7-day JWT that WhatsOn renews
with the key. Plex Media Server itself doesn't accept JWTs yet (tested 2026-10-31: 401/403), so server
calls use the server token from plex.tv's `/api/v2/devices` list, fetched again after each renewal.

Everything is kept in the meta table under `plex.*`. Tokens and the key never go to the browser."""

from __future__ import annotations

import base64
import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from . import db

PLEX_TV = "https://clients.plex.tv"
AUTH_APP = "https://app.plex.tv/auth#?"
RENEW_AFTER = 2 * 86400  # tokens last 7 days; renew well before that
SECRET_KEYS = ("plex.jwt", "plex.key", "plex.server_token")


class PlexAuthError(Exception):
    pass


@dataclass
class PlexConn:
    source: str        # "signin" | "token" | "env" | ""
    url: str
    token: str
    server_name: str = ""
    account: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.url and self.token)


def client_id(conn: sqlite3.Connection) -> str:
    """This install's own id on plex.tv (each install is its own device there)."""
    cid = db.get_meta(conn, "plex.client_id")
    if not cid:
        cid = f"whatson-{uuid.uuid4()}"
        db.set_meta(conn, "plex.client_id", cid)
    return cid


def load(conn: sqlite3.Connection) -> PlexConn:
    source = db.get_meta(conn, "plex.source")
    if source in ("signin", "token"):
        return PlexConn(source, db.get_meta(conn, "plex.url"), db.get_meta(conn, "plex.server_token"),
                        db.get_meta(conn, "plex.server_name"), db.get_meta(conn, "plex.account"))
    url, token = os.environ.get("PLEX_URL", "").strip().rstrip("/"), os.environ.get("PLEX_TOKEN", "").strip()
    return PlexConn("env" if url and token else "", url, token)


def public(conn: sqlite3.Connection, pc: PlexConn) -> dict:
    return {"source": pc.source, "configured": pc.configured, "url": pc.url, "server_name": pc.server_name,
            "account": pc.account, "env_available": bool(os.environ.get("PLEX_URL") and os.environ.get("PLEX_TOKEN")),
            "renewed_at": int(db.get_meta(conn, "plex.jwt_at", "0") or 0)}


def forget(conn: sqlite3.Connection) -> None:
    for k in ("source", "url", "server_token", "server_name", "server_id", "account", "jwt", "jwt_at"):
        db.set_meta(conn, f"plex.{k}", "")


def save_server(conn: sqlite3.Connection, source: str, url: str, token: str, name: str = "", server_id: str = "") -> None:
    db.set_meta(conn, "plex.url", url.rstrip("/"))
    db.set_meta(conn, "plex.server_token", token)
    db.set_meta(conn, "plex.server_name", name)
    db.set_meta(conn, "plex.server_id", server_id)
    db.set_meta(conn, "plex.source", source)


# --- The device key and its JWTs -------------------------------------------------------------------

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _key(conn: sqlite3.Connection) -> Ed25519PrivateKey:
    raw = db.get_meta(conn, "plex.key")
    if raw:
        return Ed25519PrivateKey.from_private_bytes(base64.b64decode(raw))
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    db.set_meta(conn, "plex.key", base64.b64encode(raw).decode())
    db.set_meta(conn, "plex.kid", str(uuid.uuid4()))
    return key


def jwk(conn: sqlite3.Connection) -> dict:
    pub = _key(conn).public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return {"kty": "OKP", "crv": "Ed25519", "x": _b64(pub), "kid": db.get_meta(conn, "plex.kid"), "alg": "EdDSA"}


def device_jwt(conn: sqlite3.Connection, nonce: str = "") -> str:
    key = _key(conn)
    now = int(time.time())
    head = {"kid": db.get_meta(conn, "plex.kid"), "alg": "EdDSA", "typ": "JWT"}
    body = {"aud": "plex.tv", "iss": client_id(conn), "iat": now, "exp": now + 300,
            "scope": "username,friendly_name"}
    if nonce:
        body["nonce"] = nonce
    msg = f"{_b64(json.dumps(head).encode())}.{_b64(json.dumps(body).encode())}"
    return f"{msg}.{_b64(key.sign(msg.encode()))}"


# --- plex.tv ---------------------------------------------------------------------------------------

class PlexTV:
    def __init__(self, conn: sqlite3.Connection, http: httpx.AsyncClient, product: str = "WhatsOn"):
        self.conn, self.http, self.product = conn, http, product

    def headers(self, token: str = "") -> dict:
        h = {"Accept": "application/json", "X-Plex-Product": self.product,
             "X-Plex-Client-Identifier": client_id(self.conn)}
        if token:
            h["X-Plex-Token"] = token
        return h

    async def _call(self, method: str, path: str, token: str = "", **kw):
        try:
            r = await self.http.request(method, f"{PLEX_TV}{path}", headers=self.headers(token), timeout=20, **kw)
        except httpx.HTTPError as exc:
            raise PlexAuthError(f"Couldn't reach plex.tv ({type(exc).__name__})") from exc
        if r.status_code == 401:
            raise PlexAuthError("plex.tv refused the sign-in; sign in again")
        if r.status_code >= 400:
            raise PlexAuthError(f"plex.tv said HTTP {r.status_code}")
        return r.json() if r.content else None

    async def start_pin(self, forward_url: str = "") -> dict:
        pin = await self._call("POST", "/api/v2/pins", json={"jwk": jwk(self.conn), "strong": True})
        q = httpx.QueryParams({"clientID": client_id(self.conn), "code": pin["code"],
                               "context[device][product]": self.product, **({"forwardUrl": forward_url} if forward_url else {})})
        return {"id": pin["id"], "auth_url": AUTH_APP + str(q), "expires_in": pin.get("expiresIn", 1800)}

    async def check_pin(self, pin_id: int) -> str | None:
        pin = await self._call("GET", f"/api/v2/pins/{pin_id}", params={"deviceJWT": device_jwt(self.conn)})
        return pin.get("authToken") or None

    async def renew(self) -> str:
        nonce = (await self._call("GET", "/api/v2/auth/nonce"))["nonce"]
        out = await self._call("POST", "/api/v2/auth/token", json={"jwt": device_jwt(self.conn, nonce)})
        return out["auth_token"]

    async def account(self, jwt: str) -> str:
        u = await self._call("GET", "/api/v2/user", token=jwt)
        return u.get("friendlyName") or u.get("username") or ""

    async def servers(self, jwt: str) -> list[dict]:
        """Servers this account can use, with the connections to try (local first, relays last)."""
        res = await self._call("GET", "/api/v2/resources", token=jwt, params={"includeHttps": 1})
        out = []
        for d in res or []:
            if "server" not in (d.get("provides") or ""):
                continue
            conns = sorted(d.get("connections") or [], key=lambda c: (bool(c.get("relay")), not c.get("local")))
            out.append({"id": d["clientIdentifier"], "name": d.get("name") or "Plex server",
                        "owned": bool(d.get("owned")), "presence": bool(d.get("presence")),
                        "connections": [c["uri"] for c in conns if c.get("uri") and not c.get("relay")]})
        return out

    async def server_token(self, jwt: str, server_id: str) -> str:
        """The token Plex Media Server accepts for this account (it doesn't take the JWT)."""
        for d in await self._call("GET", "/api/v2/devices", token=jwt) or []:
            if d.get("clientIdentifier") == server_id and d.get("token"):
                return d["token"]
        raise PlexAuthError("plex.tv didn't give a token for that server")


async def reachable(http: httpx.AsyncClient, url: str, token: str, server_id: str = "") -> str:
    """Check a Plex server answers with this token. Returns its machine id; raises PlexAuthError."""
    try:
        r = await http.get(f"{url.rstrip('/')}/identity", headers={"Accept": "application/json"}, timeout=6)
        r.raise_for_status()
        mid = r.json()["MediaContainer"]["machineIdentifier"]
        if server_id and mid != server_id:
            raise PlexAuthError("That address is a different Plex server")
        r = await http.get(f"{url.rstrip('/')}/library/sections",
                           headers={"Accept": "application/json", "X-Plex-Token": token}, timeout=10)
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise PlexAuthError(f"No answer from {url} ({type(exc).__name__})") from exc
    if r.status_code in (401, 403):
        raise PlexAuthError("The Plex server refused the token")
    if r.status_code >= 400:
        raise PlexAuthError(f"The Plex server said HTTP {r.status_code}")
    return mid
