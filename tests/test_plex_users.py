import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from whatson import db, devices, plex_auth, plex_users, tune
from whatson.app import app
from whatson.devices.base import TVStatus
from whatson.sources.plex import PlexClient
from whatson.state import state

SERVER = "http://192.0.2.8:32400"
OWNER_TOKEN, SWITCH_TOKEN, USER_TOKEN = "owner-token-123456", "switch-token-123456", "user-token-123456"
OWNER, KID, PINNED = "owner-uuid", "kid-uuid", "pinned-uuid"
HOME = {"users": [
    {"uuid": OWNER, "title": "Sam", "email": "sam@example.com", "restricted": False, "protected": False},
    {"uuid": KID, "title": "Robin", "restricted": True, "protected": False},
    {"uuid": PINNED, "title": "Alex", "restricted": False, "protected": True}]}


def movie(key: str, viewed: bool) -> dict:
    return {"ratingKey": key, "title": f"Movie {key}", "viewCount": 1 if viewed else 0}


class FakePlex:
    """plex.tv and a Plex server. Each token sees its own data, and the server refuses the plex.tv-only token."""

    def __init__(self):
        self.seen: list[httpx.Request] = []
        self.switches = 0
        self.user_tokens = [USER_TOKEN]
        self.hidden: set[str] = set()

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.seen.append(req)
        path, token = req.url.path, req.headers.get("x-plex-token")
        if req.url.host == "clients.plex.tv":
            if path == "/api/v2/user":
                return httpx.Response(200, json={"uuid": OWNER})
            if path == "/api/v2/home/users":
                return httpx.Response(200, json=HOME)
            if path == f"/api/v2/home/users/{KID}/switch":
                self.switches += 1
                return httpx.Response(201, json={"authToken": SWITCH_TOKEN})
            if path == "/api/v2/resources":
                assert token == SWITCH_TOKEN
                return httpx.Response(200, json=[{"clientIdentifier": "other", "accessToken": "wrong"},
                                                 {"clientIdentifier": "machine-1", "accessToken": self.user_tokens[-1]}])
            return httpx.Response(404)
        if token not in (OWNER_TOKEN, self.user_tokens[-1]):
            return httpx.Response(401)
        as_user = token != OWNER_TOKEN
        if path == "/identity":
            return httpx.Response(200, json={"MediaContainer": {"machineIdentifier": "machine-1"}})
        if path == "/status/sessions":
            return httpx.Response(403 if as_user else 200, json={"MediaContainer": {}})
        if path == "/library/onDeck":
            return httpx.Response(200, json={"MediaContainer": {"Metadata": [movie("2" if as_user else "1", False)]}})
        if path == "/library/sections":
            return httpx.Response(200, json={"MediaContainer": {"Directory": [{"key": "1", "type": "movie", "title": "Movies"}]}})
        if path == "/library/sections/1/all":
            items = [movie("1", False), movie("2", True)] if as_user else [movie("1", True), movie("2", False)]
            return httpx.Response(200, json={"MediaContainer": {"Metadata": items, "totalSize": 2}})
        if path.startswith("/library/metadata/"):
            key = path.rsplit("/", 1)[1]
            if as_user and key in self.hidden:
                return httpx.Response(404)
            m = movie(key, as_user)
            return httpx.Response(200, json={"MediaContainer": {"Metadata": [{**m, "type": "movie", "Genre": [], "Role": []}]}})
        return httpx.Response(404)


class FakeTV:
    label = "Fake"

    def __init__(self):
        self.links: list[str] = []

    async def status(self, host):
        return TVStatus(reachable=True, is_on=True, current_app="")

    async def open_link(self, host, link):
        self.links.append(link)


@pytest.fixture
def home(monkeypatch):
    fake = FakePlex()
    http = httpx.AsyncClient(transport=httpx.MockTransport(fake))
    conn = db.connect(":memory:")
    plex_auth.save_server(conn, "token", SERVER, OWNER_TOKEN, server_id="machine-1")
    db.set_meta(conn, "machine_id", "machine-1")
    conn.executemany("INSERT INTO library (rating_key, kind, title, watched) VALUES (?, 'movie', ?, ?)",
                     [("1", "Movie 1", 1), ("2", "Movie 2", 0)])
    plex = PlexClient(SERVER, OWNER_TOKEN, "WhatsOn", http=http)
    tv = FakeTV()

    class Settings:
        client_name = "WhatsOn"

    for name, value in (("conn", conn), ("plex", plex), ("source", plex), ("http", http), ("settings", Settings),
                        ("drivers", {"androidtv": tv})):
        monkeypatch.setattr(state, name, value, raising=False)
    fake.tv = tv
    fake.device = devices.add_device(conn, "Den TV", "192.0.2.20")
    fake.client = TestClient(app, base_url="http://localhost", headers={"X-WhatsOn": "1"})
    return fake


def choose(home, user):
    res = home.client.put(f"/api/devices/{home.device}/plex-user", json={"user": user})
    assert res.status_code == 200, res.text
    return res


def load_watched(home):
    asyncio.run(plex_users.refresh_watched(KID))


def test_links_name_the_profile_only_when_given():
    assert tune.open_link() == "plezy://open"
    assert tune.open_link("u1") == "plezy://open?profile=u1"
    assert tune.play_link("abc", "55", "u1") == "plezy://play?server=abc&id=55&profile=u1"
    assert tune.live_link("706", "abc", "u1") == "plezy://live?channel=706&start=live&server=abc&profile=u1"


def test_the_list_of_users_has_no_emails_or_tokens(home):
    res = home.client.get("/api/settings/plex/users")
    assert [(u["name"], u["owner"], u["restricted"], u["protected"]) for u in res.json()] == [
        ("Sam", True, False, False), ("Robin", False, True, False), ("Alex", False, False, True)]
    assert "example.com" not in res.text and OWNER_TOKEN not in res.text


def test_an_account_with_no_plex_home_lists_nobody(home, monkeypatch):
    async def refused(self, token):
        raise plex_auth.PlexAuthError("plex.tv refused the sign-in; sign in again")
    monkeypatch.setattr(plex_auth.PlexTV, "home_users", refused)
    assert home.client.get("/api/settings/plex/users").json() == []


def test_choosing_a_user_saves_the_server_token_not_the_plex_tv_one(home):
    res = choose(home, KID)
    assert res.json()["plex_user_name"] == "Robin"
    assert plex_auth.saved_user_token(state.conn, KID, SERVER) == USER_TOKEN
    assert SWITCH_TOKEN not in state.conn.execute("SELECT group_concat(token) FROM plex_user_tokens").fetchone()[0]


def test_tokens_never_reach_the_browser(home):
    choose(home, KID)
    for path in ("/api/devices", f"/api/library?device={home.device}", f"/api/library/item/1?device={home.device}",
                 "/api/settings/plex", "/api/settings/plex/users"):
        text = home.client.get(path).text
        assert USER_TOKEN not in text and SWITCH_TOKEN not in text and OWNER_TOKEN not in text, path


def test_a_user_token_only_goes_to_the_address_it_was_saved_with(home):
    choose(home, KID)
    assert plex_auth.saved_user_token(state.conn, KID, "http://192.0.2.66:32400") == ""


def test_a_new_server_address_gets_a_new_token(home):
    choose(home, KID)
    switches = home.switches
    home.seen.clear()
    state.plex.configure("http://192.0.2.9:32400", OWNER_TOKEN)
    plex_auth.save_server(state.conn, "token", "http://192.0.2.9:32400", OWNER_TOKEN, server_id="machine-1")
    home.client.get(f"/api/library/item/1?device={home.device}")
    assert home.switches == switches + 1
    assert not [r for r in home.seen if r.url.host == "192.0.2.8"], "a saved token went to the old address"


def test_forgetting_plex_clears_users_and_their_tokens(home):
    choose(home, KID)
    load_watched(home)
    plex_auth.forget(state.conn)
    assert devices.get_device(state.conn, home.device)["plex_user"] == ""
    assert state.conn.execute("SELECT count(*) FROM plex_user_tokens").fetchone()[0] == 0
    assert state.conn.execute("SELECT count(*) FROM user_watched").fetchone()[0] == 0


def test_unknown_and_pin_protected_users_are_refused(home):
    res = home.client.put(f"/api/devices/{home.device}/plex-user", json={"user": "someone-else"})
    assert res.status_code == 400
    res = home.client.put(f"/api/devices/{home.device}/plex-user", json={"user": PINNED})
    assert res.status_code == 400 and "PIN" in res.json()["detail"]
    assert devices.get_device(state.conn, home.device)["plex_user"] == ""


def test_tuning_tells_plezy_who_to_play_as(home):
    choose(home, KID)
    res = home.client.post("/api/tune", json={"device_id": home.device, "rating_key": "2"})
    assert res.json()["confirm"] and res.json()["profile_user"] == "Robin"
    assert home.tv.links[-1] == f"plezy://play?server=machine-1&id=2&profile={KID}"
    home.client.post("/api/tune", json={"device_id": home.device, "channel": "7"})
    assert home.tv.links[-1] == f"plezy://live?channel=7&start=live&server=machine-1&profile={KID}"


def test_the_owner_is_named_in_links_too_so_plezy_switches_back(home):
    choose(home, OWNER)
    home.client.post("/api/tune", json={"device_id": home.device, "rating_key": "2"})
    assert home.tv.links[-1].endswith(f"&profile={OWNER}")


def test_a_tv_with_no_user_sends_no_profile(home):
    res = home.client.post("/api/tune", json={"device_id": home.device, "rating_key": "2"})
    assert home.tv.links[-1] == "plezy://play?server=machine-1&id=2" and not res.json()["confirm"]


def test_no_profile_while_another_server_is_in_use(home, monkeypatch):
    choose(home, KID)
    monkeypatch.setattr(state, "source", object())
    assert plex_users.profile_for(devices.get_device(state.conn, home.device)) == ""
    assert plex_users.viewer(home.device) == ""


def test_the_busy_check_stays_on_the_owners_token(home):
    choose(home, KID)
    home.seen.clear()
    res = home.client.post("/api/tune", json={"device_id": home.device, "rating_key": "2"})
    assert res.status_code == 200
    sessions = [r for r in home.seen if r.url.path == "/status/sessions"]
    assert sessions and all(r.headers["x-plex-token"] == OWNER_TOKEN for r in sessions)


def test_library_watched_status_follows_the_tv(home):
    choose(home, KID)
    load_watched(home)
    other = devices.add_device(state.conn, "Hall TV", "192.0.2.21")
    watched = lambda d: {i["rating_key"]: i["watched"] for i in home.client.get(f"/api/library?device={d}").json()["items"]}
    assert watched(home.device) == {"1": False, "2": True}
    assert watched(other) == {"1": True, "2": False}
    assert watched(0) == {"1": True, "2": False}


def test_the_unwatched_filter_follows_the_tv(home):
    choose(home, KID)
    load_watched(home)
    keys = lambda d: [i["rating_key"] for i in home.client.get(f"/api/library?unwatched=true&device={d}").json()["items"]]
    assert keys(home.device) == ["1"]
    assert keys(0) == ["2"]


def test_search_results_show_the_tvs_user(home):
    choose(home, KID)
    load_watched(home)
    state.conn.execute("INSERT INTO library_fts (rowid, title, summary, genres, people) "
                       "SELECT rowid, title, summary, genres, people FROM library")
    state.interpreter = None
    res = home.client.get(f"/api/search?q=movie&ai=false&device={home.device}").json()
    assert {i["rating_key"]: i["watched"] for i in res["library"]} == {"1": False, "2": True}


def test_up_next_and_picks_follow_the_tv(home, monkeypatch):
    class Trakt:
        connected = False

        def cache(self):
            return {}

    class Off:
        enabled = False

    monkeypatch.setattr(state, "trakt", Trakt(), raising=False)
    monkeypatch.setattr(state, "interpreter", Off(), raising=False)
    state.conn.execute("UPDATE library SET audience_rating = 8, watched = 0")
    choose(home, KID)
    load_watched(home)
    res = home.client.get(f"/api/suggest/library?device={home.device}").json()
    assert [u["rating_key"] for u in res["up_next"]] == ["2"]
    assert [p["rating_key"] for p in res["picks"]] == ["1"]
    assert [u["rating_key"] for u in home.client.get("/api/suggest/library").json()["up_next"]] == ["1"]


def test_a_title_opens_as_the_tvs_user(home):
    choose(home, KID)
    assert home.client.get(f"/api/library/item/5?device={home.device}").json()["watched"] is True
    assert home.client.get("/api/library/item/5").json()["watched"] is False


def test_a_title_plex_hides_from_the_user_still_opens_and_says_so(home):
    choose(home, KID)
    home.hidden.add("5")
    out = home.client.get(f"/api/library/item/5?device={home.device}").json()
    assert out["hidden_from"] == "Robin" and out["title"] == "Movie 5"


def test_a_refused_token_is_replaced_once(home):
    choose(home, KID)
    switches = home.switches
    home.user_tokens.append("user-token-new-123456")
    assert home.client.get(f"/api/library/item/5?device={home.device}").json()["watched"] is True
    assert home.switches == switches + 1
    assert plex_auth.saved_user_token(state.conn, KID, SERVER) == "user-token-new-123456"


def test_a_plex_tv_failure_falls_back_to_the_owners_view(home, monkeypatch):
    choose(home, KID)
    state.conn.execute("DELETE FROM plex_user_tokens")

    async def down(self, *a):
        raise plex_auth.PlexAuthError("Couldn't reach plex.tv")
    monkeypatch.setattr(plex_auth.PlexTV, "user_server_token", down)
    out = home.client.get(f"/api/library/item/5?device={home.device}").json()
    assert out["watched"] is False and "hidden_from" not in out


def test_refresh_skips_the_owner_and_users_no_longer_on_a_tv(home):
    choose(home, KID)
    load_watched(home)
    assert state.conn.execute("SELECT count(*) FROM user_watched").fetchone()[0] == 2
    choose(home, OWNER)
    asyncio.run(plex_users.refresh_all())
    assert state.conn.execute("SELECT count(*) FROM user_watched").fetchone()[0] == 0


