import asyncio
import time

import httpx
import pytest
from fastapi import HTTPException

from whatson import db, remote_routes, source_routes, tune
from whatson.devices.base import TVStatus
from whatson.ingest import Refresher, write_guide, write_library
from whatson.sources.base import Channel, Airing, LibraryItem, Session
from whatson.sources.jellyfin import Jellyfin
from whatson.sources.plex import PlexClient

MOVIE_ID, SHOW_ID, SEASON_ID, EP1, EP2, CHANNEL_ID = "a" * 32, "b" * 32, "c" * 32, "d" * 32, "e" * 32, "f" * 32
TV = {"id": 1, "name": "Den TV", "host": "192.0.2.10", "plex_player": "Den TV", "jellyfin_device": ""}


def jellyfin(routes: dict, user_id: str = "u1", seen: list | None = None) -> Jellyfin:
    def handler(req: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(req)
        hit = routes.get(req.url.path)
        return httpx.Response(200, json=hit(req) if callable(hit) else hit) if hit is not None else httpx.Response(404)
    return Jellyfin("http://jf.example.com:8096", "k3y", httpx.AsyncClient(transport=httpx.MockTransport(handler)), user_id)


def run(coro):
    return asyncio.run(coro)


def test_library_items_map_to_what_the_app_expects_and_all_pages_load(monkeypatch):
    monkeypatch.setattr("whatson.sources.jellyfin.PAGE", 2)
    pages = [[{"Id": MOVIE_ID, "Type": "Movie", "Name": "Heat", "ProductionYear": 1995, "Overview": "Crime",
               "Genres": ["Crime"], "People": [{"Name": "Al Pacino", "Type": "Actor"}], "ImageTags": {"Primary": "t"},
               "DateCreated": "2021-07-05T22:25:40.0000000Z", "RunTimeTicks": 102_000_000_000, "OfficialRating": "R",
               "CommunityRating": 8.3, "ProviderIds": {"Imdb": "tt1", "Tmdb": "2", "TvdbSlug": "ignored"},
               "UserData": {"Played": True, "PlayCount": 1}},
              {"Id": SHOW_ID, "Type": "Series", "Name": "Bluey", "RecursiveItemCount": 10, "ImageTags": {},
               "UserData": {"Played": False, "UnplayedItemCount": 4}}],
             [{"Id": EP1, "Type": "Movie", "Name": "Last", "UserData": {}}]]
    seen = []
    jf = jellyfin({"/Items": lambda req: {"Items": pages[int(req.url.params["StartIndex"]) // 2]}}, seen=seen)
    movie, show, last = run(jf.library())
    assert (movie.rating_key, movie.kind, movie.year, movie.watched, movie.duration) == (MOVIE_ID, "movie", 1995, True, 10_200_000)
    assert movie.guids == ["imdb:tt1", "tmdb:2"] and movie.people == ["Al Pacino"]
    assert movie.thumb == f"/Items/{MOVIE_ID}/Images/Primary" and movie.added_at == 1625523940
    assert (show.kind, show.leaf_count, show.viewed_leaf_count, show.thumb) == ("show", 10, 6, "")
    assert last.title == "Last" and len(seen) == 2
    assert seen[0].url.params["userId"] == "u1"


def test_watched_counts_as_played_not_as_started():
    # Jellyfin raises PlayCount as soon as something starts; only Played means it was seen.
    jf = jellyfin({"/Items": {"Items": [{"Id": MOVIE_ID, "Type": "Movie", "UserData": {"Played": False, "PlayCount": 1}}]}})
    [movie] = run(jf.library())
    assert not movie.watched


def test_guide_channels_and_listings():
    jf = jellyfin({
        "/LiveTv/Channels": {"Items": [{"Id": CHANNEL_ID, "Name": "ABC 12", "ChannelNumber": "12", "ImageTags": {"Primary": "t"}},
                                       {"Id": MOVIE_ID, "Name": "No Art", "Number": "13", "ImageTags": {}}]},
        "/LiveTv/Programs": {"Items": [
            {"ChannelId": CHANNEL_ID, "Name": "Bluey", "EpisodeTitle": "The Pool", "IsSeries": True, "ParentIndexNumber": 1,
             "IndexNumber": 22, "StartDate": "2026-01-01T10:00:00.0000000Z", "EndDate": "2026-01-01T10:30:00.0000000Z"},
            {"ChannelId": CHANNEL_ID, "Name": "Heat", "IsMovie": True, "ProductionYear": 1995,
             "StartDate": "2026-01-01T11:00:00.0000000Z", "EndDate": "2026-01-01T13:00:00.0000000Z"},
            {"ChannelId": CHANNEL_ID, "Name": "The Big Match", "IsSports": True,
             "StartDate": "2026-01-01T13:00:00.0000000Z", "EndDate": "2026-01-01T15:00:00.0000000Z"},
            {"Name": "Belongs nowhere"}]}})
    channels, airings = run(jf.load_guide(0, 1))
    assert channels[0].vcn == "12" and channels[1].vcn == "13" and channels[1].thumb == ""
    # Channel art is used as an address directly, so the browser must only ever be pointed at WhatsOn.
    assert channels[0].thumb.startswith("/api/thumb?path=%2FItems%2F") and "jf.example.com" not in channels[0].thumb
    assert [(a.kind, a.subtitle) for a in airings] == [("episode", "S01E22 The Pool"), ("movie", ""), ("sports", "")]
    assert airings[0].ends - airings[0].begins == 1800 and airings[1].year == 1995


def test_no_live_tv_means_an_empty_guide():
    assert run(jellyfin({"/LiveTv/Channels": {"Items": []}}).load_guide(0, 1)) == ([], [])


def test_only_sessions_with_something_playing_count():
    sessions = [
        {"Client": "Plezy Android TV", "DeviceName": "Idle TV", "DeviceId": "d0", "RemoteEndPoint": "192.0.2.1"},
        {"Client": "WhatsOn", "NowPlayingItem": {"Id": MOVIE_ID, "Type": "Movie"}},
        {"Client": "Plezy Android TV", "DeviceName": "Den TV", "DeviceId": "d1", "RemoteEndPoint": "192.0.2.1:5000",
         "NowPlayingItem": {"Id": EP1, "Type": "Episode", "Name": "The Pool", "SeriesName": "Bluey", "SeriesId": SHOW_ID,
                            "ParentIndexNumber": 1, "IndexNumber": 22, "RunTimeTicks": 4_380_000_000},
         "PlayState": {"PositionTicks": 2_200_000_000, "IsPaused": True}},
        {"Client": "Plezy Android TV", "DeviceName": "Bedroom", "DeviceId": "d2",
         "NowPlayingItem": {"Id": CHANNEL_ID, "Type": "TvChannel", "Name": "ABC 12"}}]
    ep, live = run(jellyfin({"/Sessions": sessions}).playing())
    assert (ep.state, ep.kind, ep.title, ep.episode, ep.rating_key, ep.show_key) == ("paused", "episode", "Bluey", "S01E22 The Pool", EP1, SHOW_ID)
    assert (ep.player_address, ep.device_id, ep.offset, ep.duration) == ("192.0.2.1", "d1", 220_000, 438_000)
    assert ep.thumb == f"/Items/{SHOW_ID}/Images/Primary"
    assert (live.live, live.kind, live.channel_id, live.state) == (True, "live", CHANNEL_ID, "playing")


def test_show_page_seasons_and_episodes_in_order():
    jf = jellyfin({
        "/Items": lambda req: {"Items": [
            {"Id": SHOW_ID, "Type": "Series", "Name": "Bluey", "Overview": "Dogs", "Genres": ["Kids"], "ImageTags": {"Primary": "t"},
             "People": [{"Name": "A Writer", "Type": "Writer"}, {"Name": "An Actor", "Type": "Actor"}], "Studios": [{"Name": "ABC"}]}]}
        if "ids" in req.url.params else {"Items": [
            {"Id": EP2, "IndexNumber": 2, "Name": "Two", "UserData": {"Played": True}},
            {"Id": EP1, "IndexNumber": 1, "Name": "One", "PremiereDate": "2021-06-20T00:00:00.0000000Z",
             "UserData": {"PlaybackPositionTicks": 50_000}}]},
        f"/Shows/{SHOW_ID}/Seasons": {"Items": [{"Id": SEASON_ID, "IndexNumber": 1, "Name": "Season 1", "ChildCount": 8,
                                                 "UserData": {"UnplayedItemCount": 5}}]}})
    show = run(jf.item(SHOW_ID))
    assert (show["kind"], show["cast"], show["studio"]) == ("show", ["An Actor"], "ABC")
    assert show["seasons"] == [{"rating_key": SEASON_ID, "index": 1, "title": "Season 1", "thumb": "", "episodes": 8, "watched": 3}]
    one, two = run(jf.episodes(SEASON_ID))
    assert (one["title"], one["aired"], one["view_offset"], one["watched"]) == ("One", "2021-06-20", 5, False)
    assert (two["title"], two["aired"], two["view_offset"], two["watched"]) == ("Two", None, None, True)


def test_missing_item_is_none():
    assert run(jellyfin({"/Items": {"Items": []}}).item(MOVIE_ID)) is None


def test_up_next_is_one_card_per_title_with_in_progress_first():
    routes = {"/UserItems/Resume": {"Items": [{"Id": EP2, "Type": "Episode", "Name": "Two", "SeriesName": "Bluey", "SeriesId": SHOW_ID,
                                               "ParentIndexNumber": 1, "IndexNumber": 2},
                                              {"Id": MOVIE_ID, "Type": "Movie", "Name": "Heat"}]},
              "/Shows/NextUp": {"Items": [{"Id": EP1, "Type": "Episode", "Name": "Other", "SeriesName": "Bluey", "SeriesId": SHOW_ID}]}}
    show, movie = run(jellyfin(routes).up_next())
    assert (show["rating_key"], show["play_key"], show["kind"], show["label"]) == (SHOW_ID, EP2, "show", "S01E02 Two")
    assert (movie["rating_key"], movie["kind"], movie["label"]) == (MOVIE_ID, "movie", "Continue watching")
    assert run(jellyfin(routes, user_id="").up_next()) == []


def test_artwork_proxy_only_takes_exact_artwork_paths():
    seen = []
    jf = jellyfin({f"/Items/{MOVIE_ID}/Images/Primary": {}}, seen=seen)
    assert run(jf.thumb(f"/Items/{MOVIE_ID}/Images/Primary", 300)).status_code == 200
    assert seen[0].url.params["maxWidth"] == "300"
    plex = PlexClient("http://plex.example.com:32400", "t", http=httpx.AsyncClient(transport=httpx.MockTransport(
        lambda req: httpx.Response(200))))
    for path in ("/System/Info", "/Users", f"/Items/{MOVIE_ID}/Images/Primary/../../../System/Info", "/Sessions",
                 "http://elsewhere.example.com/x", "/library/metadata/1/thumb/1/../../secret"):
        assert run(jf.thumb(path, 300)) is None
        assert run(plex.thumb(path, 300)) is None
    assert run(plex.thumb("/library/metadata/1/thumb/2", 300)).status_code == 200
    assert len(seen) == 1


def test_ids_are_checked_per_source():
    jf, plex = jellyfin({}), PlexClient("", "")
    assert jf.valid_id("a" * 32) and not jf.valid_id("55") and not jf.valid_id("../../System/Info")
    assert plex.valid_id("55") and not plex.valid_id("a" * 32)


def test_plex_item_keeps_its_shape():
    def handler(req):
        if req.url.path.endswith("/children"):
            return httpx.Response(200, json={"MediaContainer": {"Metadata": [
                {"ratingKey": 7, "index": 1, "title": "Season 1", "leafCount": 8, "viewedLeafCount": 3}]}})
        return httpx.Response(200, json={"MediaContainer": {"Metadata": [
            {"type": "show", "title": "Bluey", "year": 2018, "Genre": [{"tag": "Kids"}], "Role": [{"tag": "An Actor"}]}]}})
    plex = PlexClient("http://plex.example.com:32400", "t", http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    show = run(plex.item("5"))
    assert (show["rating_key"], show["kind"], show["genres"], show["cast"]) == ("5", "show", ["Kids"], ["An Actor"])
    assert show["seasons"][0] == {"rating_key": "7", "index": 1, "title": "Season 1", "thumb": "", "episodes": 8, "watched": 3}


def test_a_linked_device_decides_which_tv_it_is():
    # A server behind a proxy sees the proxy's address, and the name Plezy reports can be anything.
    assert tune.is_on_tv(TV, "192.0.2.10", "Anything")
    assert tune.is_on_tv(TV, "192.0.2.1", "den tv")
    assert not tune.is_on_tv(TV, "192.0.2.1", "Kitchen")
    linked = {**TV, "jellyfin_device": "d1"}
    assert tune.is_on_tv(linked, "192.0.2.1", "Kitchen", "d1")
    assert not tune.is_on_tv(linked, "192.0.2.10", "Den TV", "d2")
    assert tune.is_on_tv(linked, "192.0.2.10", "Den TV")   # Plex sessions have no device id


class FakeDriver:
    async def status(self, host):
        return TVStatus(reachable=True, is_on=True, current_app=tune.PLEZY)


def test_busy_check_asks_the_active_source():
    busy = Session("Den TV", "192.0.2.1", "Plezy Android TV", "playing", "Heat", False)
    other = Session("Kitchen", "192.0.2.1", "Plezy Android TV", "playing", "Heat", False)

    class Fake:
        configured = True

        def __init__(self, found):
            self.found = found

        async def playing(self):
            return self.found

    assert run(tune.check_busy(FakeDriver(), Fake([busy]), TV)).busy
    assert not run(tune.check_busy(FakeDriver(), Fake([other]), TV)).busy
    assert not run(tune.check_busy(FakeDriver(), Fake([]), TV)).busy


@pytest.fixture
def app_state(monkeypatch):
    conn = db.connect(":memory:")
    s = source_routes.state
    plex = PlexClient("http://plex.example.com:32400", "t", http=httpx.AsyncClient(transport=httpx.MockTransport(
        lambda req: httpx.Response(404))))
    for name, value in (("conn", conn), ("plex", plex), ("source", plex), ("last_tune", {7: ("x", 1.0)}),
                        ("lan_http", httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(404))))):
        monkeypatch.setattr(s, name, value, raising=False)
    monkeypatch.setattr(s, "refresher", Refresher(object(), conn, plex), raising=False)
    return s


def fill(conn):
    write_guide(conn, [Channel("1", "1", "ABC")], [Airing("1", "News", "", "", "other", 1, 2)], [])
    write_library(conn, [LibraryItem("55", "movie", "Heat", 1995, "")])
    conn.execute("INSERT INTO fav_channels VALUES ('1')")
    db.set_meta(conn, "machine_id", "old-server")


def connect_jellyfin(conn, user=True):
    db.set_meta(conn, "jellyfin.url", "http://jf.example.com:8096")
    db.set_meta(conn, "jellyfin.key", "s3cret-key")
    if user:
        db.set_meta(conn, "jellyfin.user_id", "u1")
        db.set_meta(conn, "jellyfin.user_name", "sam")


def counts(conn):
    return [conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("channels", "airings", "library", "fav_channels")]


def test_switching_source_clears_the_old_servers_data(app_state):
    conn = app_state.conn
    fill(conn)
    connect_jellyfin(conn)
    run(source_routes.set_source(source_routes.SourceIn(source="jellyfin")))
    assert app_state.source.name == "jellyfin" and app_state.source.user_id == "u1"
    assert app_state.refresher.source is app_state.source
    assert counts(conn) == [0, 0, 0, 0]
    assert db.get_meta(conn, "machine_id") == "" and app_state.last_tune == {}
    assert source_routes.current().name == "jellyfin"      # survives a restart


def test_choosing_the_same_source_again_keeps_everything(app_state):
    conn = app_state.conn
    fill(conn)
    run(source_routes.set_source(source_routes.SourceIn(source="plex")))
    assert counts(conn) == [1, 1, 1, 1]


def test_jellyfin_needs_a_connection_and_a_user_first(app_state):
    conn = app_state.conn
    fill(conn)
    with pytest.raises(HTTPException, match="Connect"):
        run(source_routes.set_source(source_routes.SourceIn(source="jellyfin")))
    connect_jellyfin(conn, user=False)
    with pytest.raises(HTTPException, match="user"):
        run(source_routes.set_source(source_routes.SourceIn(source="jellyfin")))
    with pytest.raises(HTTPException):
        run(source_routes.set_source(source_routes.SourceIn(source="emby")))
    assert app_state.source is app_state.plex and counts(conn) == [1, 1, 1, 1]


def test_a_refresh_still_running_when_the_source_changes_writes_nothing(app_state):
    conn = app_state.conn
    refresher = Refresher(type("S", (), {"guide_hours": 1})(), conn, app_state.plex)
    refresher.games = []

    class Slow:
        name, label, configured = "plex", "Plex", True

        async def load_guide(self, start, end):
            refresher.use(app_state.plex)   # the switch lands while this server is answering
            return [Channel("9", "9", "Old")], []

        async def library(self):
            refresher.use(app_state.plex)
            return [LibraryItem("9", "movie", "Old", 2000, "")]

    refresher.source = Slow()
    run(refresher.refresh_guide())
    refresher.source = Slow()
    run(refresher.refresh_library())
    assert counts(conn) == [0, 0, 0, 0]


def test_keys_never_reach_the_browser(app_state):
    connect_jellyfin(app_state.conn)
    for body in (source_routes.public(), remote_routes._jf_public()):
        assert "s3cret" not in str(body)


def test_forgetting_the_jellyfin_in_use_goes_back_to_plex(app_state):
    conn = app_state.conn
    connect_jellyfin(conn)
    run(source_routes.set_source(source_routes.SourceIn(source="jellyfin")))
    conn.execute("INSERT INTO devices (name, kind, host, jellyfin_device) VALUES ('Den', 'androidtv', '192.0.2.10', 'd1')")
    fill(conn)
    run(remote_routes.forget_jellyfin())
    assert app_state.source is app_state.plex and source_routes.chosen() == "plex"
    assert counts(conn) == [0, 0, 0, 0]
    assert db.get_meta(conn, "jellyfin.user_id") == "" and db.get_meta(conn, "jellyfin.key") == ""
    assert conn.execute("SELECT jellyfin_device FROM devices").fetchone()[0] == ""


def test_plex_sign_in_only_reloads_when_plex_is_in_use(app_state):
    from whatson import plex_routes
    connect_jellyfin(app_state.conn)
    run(source_routes.set_source(source_routes.SourceIn(source="jellyfin")))
    app_state.refresher.machine_id = "jellyfin-server"
    plex_routes.apply()
    assert app_state.refresher.machine_id == "jellyfin-server"


def test_library_ingest_refills_after_a_switch(app_state):
    jf = jellyfin({"/Items": {"Items": [{"Id": MOVIE_ID, "Type": "Movie", "Name": "Heat", "UserData": {}}]}})
    refresher = Refresher(object(), app_state.conn, jf)
    run(refresher.refresh_library())
    row = app_state.conn.execute("SELECT rating_key, title FROM library").fetchone()
    assert tuple(row) == (MOVIE_ID, "Heat") and int(db.get_meta(app_state.conn, "library_refreshed")) <= time.time()
