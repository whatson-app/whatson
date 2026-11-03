import asyncio
import base64
import json
import socket

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from whatson import db, plex_auth, safe_http


def unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def test_saved_connection_wins_over_env_and_forget_falls_back(monkeypatch):
    monkeypatch.setenv("PLEX_URL", "http://10.0.0.2:32400/")
    monkeypatch.setenv("PLEX_TOKEN", "env-token")
    conn = db.connect(":memory:")
    pc = plex_auth.load(conn)
    assert (pc.source, pc.url, pc.token) == ("env", "http://10.0.0.2:32400", "env-token")
    plex_auth.save_server(conn, "signin", "https://10-0-0-3.abc.plex.direct:32400/", "server-token", "Home", "mid")
    db.set_meta(conn, "plex.jwt", "secret-jwt")
    pc = plex_auth.load(conn)
    assert (pc.source, pc.url, pc.token, pc.server_name) == ("signin", "https://10-0-0-3.abc.plex.direct:32400",
                                                             "server-token", "Home")
    pub = json.dumps(plex_auth.public(conn, pc))
    assert "server-token" not in pub and "secret-jwt" not in pub and "env-token" not in pub
    plex_auth.forget(conn)
    assert plex_auth.load(conn).source == "env"
    monkeypatch.delenv("PLEX_TOKEN")
    assert not plex_auth.load(conn).configured


def test_device_jwt_is_signed_by_the_install_key():
    conn = db.connect(":memory:")
    key = plex_auth.jwk(conn)
    assert key["kty"] == "OKP" and key["crv"] == "Ed25519" and key["kid"]
    assert plex_auth.client_id(conn) == plex_auth.client_id(conn)  # stable per install
    head, body, sig = plex_auth.device_jwt(conn, nonce="n-1").split(".")
    Ed25519PublicKey.from_public_bytes(unb64(key["x"])).verify(unb64(sig), f"{head}.{body}".encode())
    h, b = json.loads(unb64(head)), json.loads(unb64(body))
    assert h == {"kid": key["kid"], "alg": "EdDSA", "typ": "JWT"}
    assert b["aud"] == "plex.tv" and b["iss"] == plex_auth.client_id(conn) and b["nonce"] == "n-1"
    assert b["exp"] > b["iat"]


def test_plex_tv_flow():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        p = req.url.path
        if p == "/api/v2/pins" and req.method == "POST":
            return httpx.Response(201, json={"id": 7, "code": "abc", "expiresIn": 1800})
        if p == "/api/v2/pins/7":
            return httpx.Response(200, json={"authToken": "jwt-1"})
        if p == "/api/v2/resources":
            return httpx.Response(200, json=[
                {"clientIdentifier": "tv1", "provides": "player", "connections": []},
                {"clientIdentifier": "srv", "name": "Home", "provides": "server", "owned": True, "presence": True,
                 "connections": [{"uri": "https://relay", "relay": True, "local": False},
                                 {"uri": "https://remote", "local": False},
                                 {"uri": "https://local", "local": True}]}])
        if p == "/api/v2/devices":
            return httpx.Response(200, json=[{"clientIdentifier": "srv", "token": "legacy-srv"}])
        if p == "/api/v2/auth/nonce":
            return httpx.Response(200, json={"nonce": "n-2"})
        if p == "/api/v2/auth/token":
            return httpx.Response(200, json={"auth_token": "jwt-2"})
        return httpx.Response(404)

    async def run():
        conn = db.connect(":memory:")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            tv = plex_auth.PlexTV(conn, http)
            pin = await tv.start_pin("http://192.168.1.10:8430/static/signed-in.html")
            assert pin["id"] == 7 and pin["auth_url"].startswith("https://app.plex.tv/auth#?clientID=whatson-")
            assert "code=abc" in pin["auth_url"] and "forwardUrl=" in pin["auth_url"]
            body = json.loads(seen[0].content)
            assert body["strong"] is True and body["jwk"]["crv"] == "Ed25519"
            assert await tv.check_pin(7) == "jwt-1"
            assert "deviceJWT" in seen[-1].url.params
            servers = await tv.servers("jwt-1")
            assert [s["id"] for s in servers] == ["srv"]
            assert servers[0]["connections"] == ["https://local", "https://remote"]  # local first, no relay
            assert await tv.server_token("jwt-1", "srv") == "legacy-srv"
            with pytest.raises(plex_auth.PlexAuthError):
                await tv.server_token("jwt-1", "other")
            assert await tv.renew() == "jwt-2"
            assert json.loads(seen[-1].content)["jwt"].count(".") == 2

    asyncio.run(run())


def test_pinned_transport_rechecks_every_request(monkeypatch):
    answers = iter(["192.168.1.5", "169.254.169.254"])
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, **kw: [(0, 0, 0, "", (next(answers), port))])
    monkeypatch.setattr(safe_http, "CACHE_SECONDS", 0)
    sent = []

    async def fake_send(self, request):
        sent.append(request)
        return httpx.Response(200, request=request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_send)

    async def run():
        async with safe_http.client() as http:
            r = await http.get("https://radarr.example.lan:7878/api/v3/system/status")
            assert r.status_code == 200
            # A second lookup now points at a metadata address: refused at request time.
            with pytest.raises(httpx.ConnectError, match="isn't allowed"):
                await http.get("https://radarr.example.lan:7878/api/v3/system/status")

    asyncio.run(run())
    req = sent[0]
    assert req.url.host == "192.168.1.5" and req.headers["host"] == "radarr.example.lan:7878"
    assert req.extensions["sni_hostname"] == "radarr.example.lan"
    assert len(sent) == 1


def test_pinned_transport_leaves_ip_literals_alone(monkeypatch):
    sent = []

    async def fake_send(self, request):
        sent.append(request)
        return httpx.Response(200, request=request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_send)

    async def run():
        async with safe_http.client() as http:
            await http.get("http://127.0.0.1:32400/identity")
            with pytest.raises(httpx.ConnectError):
                await http.get("http://169.254.169.254/latest/meta-data/")

    asyncio.run(run())
    assert [str(r.url) for r in sent] == ["http://127.0.0.1:32400/identity"]
    assert "sni_hostname" not in sent[0].extensions
