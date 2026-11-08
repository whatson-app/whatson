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
