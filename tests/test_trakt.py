from __future__ import annotations

import asyncio
import json
import time

import httpx

from whatson import db
from whatson.trakt import Trakt


def connected(handler) -> Trakt:
    t = Trakt(db.connect(":memory:"), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    for k, v in {"client_id": "id", "client_secret": "s3cret", "access": "old", "refresh": "r1",
                 "expires": str(int(time.time()) + 600)}.items():
        t._set(k, v)
    return t


def test_refresh_sends_localhost_first_and_keeps_older_apps_working():
    sent = []

    def handler(req):
        uri = json.loads(req.content)["redirect_uri"]
        sent.append(uri)
        if uri != "urn:ietf:wg:oauth:2.0:oob":  # an app registered before Trakt required localhost
            return httpx.Response(401)
        return httpx.Response(200, json={"access_token": "new", "refresh_token": "r2", "created_at": int(time.time()),
                                         "expires_in": 86400 * 7})

    t = connected(handler)
    asyncio.run(t._refresh_if_needed())
    assert sent == ["http://localhost", "urn:ietf:wg:oauth:2.0:oob"]
    assert t._m("access") == "new" and t.connected


def test_refresh_stops_at_localhost_when_it_works():
    sent = []

    def handler(req):
        sent.append(json.loads(req.content)["redirect_uri"])
        return httpx.Response(200, json={"access_token": "new", "refresh_token": "r2", "created_at": int(time.time()),
                                         "expires_in": 86400 * 7})

    t = connected(handler)
    asyncio.run(t._refresh_if_needed())
    assert sent == ["http://localhost"]


def test_refresh_rejected_for_both_signs_out():
    t = connected(lambda req: httpx.Response(401))
    asyncio.run(t._refresh_if_needed())
    assert not t.connected


def test_sign_in_without_a_secret_uses_pkce():
    import base64
    import hashlib
    seen = {}

    def handler(req):
        body = json.loads(req.content)
        seen[req.url.path] = body
        if req.url.path == "/oauth/device/code":
            return httpx.Response(200, json={"device_code": "d", "user_code": "ABCD", "verification_url": "https://trakt.tv/activate",
                                             "expires_in": 600, "interval": 5})
        if req.url.path == "/oauth/device/token":
            return httpx.Response(200, json={"access_token": "a", "refresh_token": "r", "created_at": int(time.time()),
                                             "expires_in": 86400 * 7})
        return httpx.Response(200, json={"user": {"username": "viewer"}})

    t = Trakt(db.connect(":memory:"), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    t.save_app("new-app-id", "")
    assert t.configured
    asyncio.run(t.start_device())
    assert asyncio.run(t.poll_device()) == "connected"
    code, token = seen["/oauth/device/code"], seen["/oauth/device/token"]
    assert code["code_challenge_method"] == "S256"
    digest = base64.urlsafe_b64encode(hashlib.sha256(token["code_verifier"].encode()).digest()).rstrip(b"=").decode()
    assert code["code_challenge"] == digest
    assert "client_secret" not in token


def test_older_app_still_sends_its_secret_and_a_new_app_drops_it():
    sent = []

    def handler(req):
        sent.append(json.loads(req.content))
        return httpx.Response(200, json={"access_token": "new", "refresh_token": "r2", "created_at": int(time.time()),
                                         "expires_in": 86400 * 7})

    t = connected(handler)
    asyncio.run(t._refresh_if_needed())
    assert sent[-1]["client_secret"] == "s3cret"
    t.save_app("another-app", "")
    assert t._m("client_secret") == "" and not t.connected
