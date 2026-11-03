import asyncio
import json

import httpx
import pytest
from androidtvremote2 import ConnectionClosed

from whatson import apps, db, remote_routes
from whatson.devices.androidtv import AndroidTVDriver
from whatson.sources.jellyfin import Jellyfin, JellyfinError


def test_app_list_defaults_then_learns_from_seen_and_ticks():
    conn = db.connect(":memory:")
    shown = lambda: [a["id"] for a in apps.for_tv(conn, 1) if a["shown"]]
    assert shown() == ["plezy", "plex", "youtube"]   # nothing known yet
    apps.note_seen(conn, 1, "com.netflix.ninja", idle={"com.google.android.tvlauncher"})
    apps.note_seen(conn, 1, "com.google.android.tvlauncher", idle={"com.google.android.tvlauncher"})
    assert shown() == ["netflix"]                      # once something is known, defaults step aside
    apps.set_picked(conn, 1, "com.edde746.plezy", True)
    apps.set_picked(conn, 1, "com.netflix.ninja", False)
    assert shown() == ["plezy"]
    apps.note_seen(conn, 1, "tv.example.newapp", idle=set())
    unknown = next(a for a in apps.for_tv(conn, 1) if a["package"] == "tv.example.newapp")
    assert unknown["shown"] and unknown["name"] == "Newapp" and not unknown["by_link"]
    assert apps.for_tv(conn, 2)[0]["id"] == "plezy"   # other TVs unaffected
    conn.execute("INSERT INTO tv_apps (device_id, package, seen_at) VALUES (1, 'com.android.tv.settings', 1)")
    apps.note_seen(conn, 1, "com.google.android.katniss", idle=set())
    assert not {"com.android.tv.settings", "com.google.android.katniss"} & {a["package"] for a in apps.for_tv(conn, 1)}
    assert apps.name_of("com.android.tv.settings") == "Settings" and apps.name_of("tv.example.newapp") == "Newapp"


def test_jellyfin_sessions_and_commands():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.path == "/Sessions":
            return httpx.Response(200, json=[
                {"Id": "s1", "Client": "Jellyfin Android TV", "DeviceName": "Living Room TV",
                 "RemoteEndPoint": "::ffff:192.0.2.43", "SupportsRemoteControl": True,
                 "NowPlayingItem": {"Name": "The Pool", "SeriesName": "Bluey", "ParentIndexNumber": 1,
                                    "IndexNumber": 22, "Type": "Episode", "RunTimeTicks": 4_380_000_000},
                 "PlayState": {"PositionTicks": 2_200_000_000, "IsPaused": True}},
                {"Id": "me", "Client": "WhatsOn"}])
        if req.url.path.startswith("/Sessions/s1/Playing/"):
            return httpx.Response(204)
        if req.url.path == "/System/Info":
            return httpx.Response(401)
        return httpx.Response(404)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            jf = Jellyfin("http://jf.lan:8096/", "k3y", http)
            [s] = await jf.sessions()
            assert (s.address, s.controllable, s.title, s.subtitle, s.paused) == (
                "192.0.2.43", True, "Bluey", "S01E22 The Pool", True)
            assert (s.position, s.duration) == (220_000, 438_000)
            assert 'Token="k3y"' in seen[0].headers["authorization"]
            await jf.command("s1", "Seek", 230_000)
            assert seen[-1].method == "POST" and seen[-1].url.params["seekPositionTicks"] == "2300000000"
            with pytest.raises(JellyfinError):
                await jf.command("s1", "Shutdown")
            with pytest.raises(JellyfinError, match="refused"):
                await jf.info()

    asyncio.run(run())


class FakeRemote:
    def __init__(self, fail_first=False):
        self.sent, self.fail_first, self.disconnected = [], fail_first, False

    def send_key_command(self, key, direction):
        if self.fail_first:
            self.fail_first = False
            raise ConnectionClosed("gone")
        self.sent.append((key, direction))

    def disconnect(self):
        self.disconnected = True


def test_held_connection_is_reused_and_reopened_when_dropped(tmp_path, monkeypatch):
    drv = AndroidTVDriver(tmp_path, "WhatsOn")
    made = [FakeRemote(fail_first=True), FakeRemote()]
    opened = []

    async def connected(host):
        opened.append(host)
        return made[len(opened) - 1]

    monkeypatch.setattr(drv, "_connected", connected)
    monkeypatch.setattr(AndroidTVDriver, "_alive", staticmethod(lambda r: not r.disconnected))

    async def run():
        await drv.send_key("10.0.0.5", "DPAD_UP")        # first connection drops: reconnect once
        await drv.send_key("10.0.0.5", "VOLUME_UP", "START_LONG")
    asyncio.run(run())
    assert opened == ["10.0.0.5", "10.0.0.5"] and made[0].disconnected
    assert made[1].sent == [("DPAD_UP", "SHORT"), ("VOLUME_UP", "START_LONG")]
    drv.drop_idle(max_idle=-1)
    assert made[1].disconnected and not drv._held


def test_saved_jellyfin_key_only_goes_to_the_address_it_was_saved_with(monkeypatch):
    conn = db.connect(":memory:")
    monkeypatch.setattr(remote_routes.state, "conn", conn, raising=False)
    db.set_meta(conn, "jellyfin.url", "http://jf.lan:8096")
    db.set_meta(conn, "jellyfin.key", "s3cret")
    assert remote_routes._key_for("http://jf.lan:8096", "") == "s3cret"
    assert remote_routes._key_for("http://elsewhere.lan:8096", "") == ""
    assert remote_routes._key_for("http://elsewhere.lan:8096", " typed ") == "typed"
