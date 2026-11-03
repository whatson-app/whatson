import asyncio
import json

import httpx
import pytest

from whatson import arr, db

RADARR_LOOKUP = {
    "title": "Dune: Part Three", "year": 2026, "tmdbId": 1170608, "imdbId": "tt31378509", "status": "announced",
    "isAvailable": False, "genres": ["Science Fiction"], "originalLanguage": {"id": 1, "name": "English"},
    "remotePoster": "https://image.tmdb.org/t/p/original/abc.jpg", "ratings": {"tmdb": {"value": 7.84}},
    "studio": "Legendary", "images": [], "tags": [],
}
SONARR_LOOKUP = {
    "title": "Frieren", "year": 2023, "tvdbId": 424536, "tmdbId": 209867, "status": "continuing", "seriesType": "standard",
    "genres": ["Animation", "Fantasy"], "originalLanguage": {"name": "Japanese"}, "ratings": {"value": 9.1},
    "network": "Nippon TV", "seasons": [{"seasonNumber": 0}, {"seasonNumber": 1}, {"seasonNumber": 2}],
    "images": [{"coverType": "poster", "remoteUrl": "https://artworks.thetvdb.com/p.jpg"}],
}
OPTIONS = {"roots": [{"id": 1, "path": "/data/Movies"}, {"id": 4, "path": "/data/Anime/Movies"}],
           "profiles": [{"id": 1, "name": "Any"}, {"id": 5, "name": "Ultra-HD"}, {"id": 7, "name": "Anime"}],
           "tags": [{"id": 2, "label": "anime"}, {"id": 3, "label": "kids"}]}


def test_cards_from_both_apps():
    m = arr.card("movie", RADARR_LOOKUP)
    assert m["id"] == 1170608 and m["poster"] == "https://image.tmdb.org/t/p/w342/abc.jpg"
    assert m["rating"] == 7.8 and m["arr_id"] is None and not m["anime"] and m["network"] == "Legendary"
    s = arr.card("show", SONARR_LOOKUP)
    assert s["id"] == 424536 and s["seasons"] == 2 and s["rating"] == 9.1 and s["anime"]
    assert s["poster"] == "https://artworks.thetvdb.com/p.jpg"


def test_states():
    m = arr.card("movie", RADARR_LOOKUP)
    assert arr.set_state(dict(m), {}, None)["state"] == "not_added"
    assert arr.set_state(dict(m), {}, "55") == {**m, "state": "in_plex", "rating_key": "55"}
    added = arr.card("movie", {**RADARR_LOOKUP, "id": 9})
    assert arr.set_state(dict(added), {}, None)["state"] == "not_released"
    out = arr.card("movie", {**RADARR_LOOKUP, "id": 9, "status": "released", "isAvailable": True})
    assert arr.set_state(dict(out), {}, None)["state"] == "missing"
    assert arr.set_state(arr.card("movie", {**RADARR_LOOKUP, "id": 9, "movieFileId": 3}), {}, None)["state"] == "imported"
    q = arr.queue_progress([{"movieId": 9, "size": 1000, "sizeleft": 250, "status": "downloading", "timeleft": "00:05:00"}], "movie")
    c = arr.set_state(dict(out), q, None)
    assert c["state"] == "downloading" and c["progress"] == 0.75 and c["timeleft"] == "00:05:00"
    q = arr.queue_progress([{"movieId": 9, "size": 10, "sizeleft": 0, "status": "completed",
                             "trackedDownloadState": "importBlocked"}], "movie")
    c = arr.set_state(dict(out), q, None)
    assert c["state"] == "importing" and c["warning"]


def test_show_queue_groups_episodes():
    q = arr.queue_progress([{"seriesId": 4, "size": 100, "sizeleft": 100, "status": "downloading"},
                            {"seriesId": 4, "size": 100, "sizeleft": 0, "status": "completed"}], "show")
    assert q[4]["count"] == 2 and q[4]["progress"] == 0.5 and not q[4]["importing"]


def test_pick_root_profile_tags():
    prefs = {**arr.PREFS, "root": "/data/Movies", "profile": 5, "anime_root": "/data/Anime/Movies",
             "anime_profile": 7, "anime_tags": [2, 99]}
    assert arr.pick(prefs, OPTIONS, False) == ("/data/Movies", 5, [])
    assert arr.pick(prefs, OPTIONS, True) == ("/data/Anime/Movies", 7, [2])  # unknown tag 99 dropped
    assert arr.pick(prefs, OPTIONS, False, "/data/Anime/Movies", 1) == ("/data/Anime/Movies", 1, [])
    # Nothing saved yet: the app's first folder and profile.
    assert arr.pick(arr.PREFS, OPTIONS, True) == ("/data/Movies", 1, [])
    with pytest.raises(arr.ArrError):
        arr.pick(prefs, OPTIONS, False, "/etc", 0)
    with pytest.raises(arr.ArrError):
        arr.pick(prefs, OPTIONS, False, "", 42)
    assert arr.guess_anime(OPTIONS) == {"anime_root": "/data/Anime/Movies", "anime_profile": 7, "anime_tags": [2]}


def test_keys_stay_with_their_address(monkeypatch):
    monkeypatch.setenv("RADARR_URL", "http://192.168.1.10:7878/")
    monkeypatch.setenv("RADARR_KEY", "env-key-123456789")
    conn = db.connect(":memory:")
    cfg = arr.load(conn, "movie")
    assert cfg.configured and cfg.key_source == "env" and cfg.url == "http://192.168.1.10:7878"
    # Pointing it somewhere else without a key: neither the env key nor any saved key goes there.
    arr.save(conn, "movie", arr.clean_prefs("movie", {"url": "http://10.0.0.9:7878"}))
    assert arr.load(conn, "movie").key == ""
    arr.save(conn, "movie", arr.clean_prefs("movie", {"url": "http://10.0.0.9:7878"}), key="saved-key-123456789")
    cfg = arr.load(conn, "movie")
    assert cfg.key == "saved-key-123456789" and cfg.key_source == "saved"
    pub = arr.public(cfg)
    assert "saved-key" not in json.dumps(pub) and pub["key"]["hint"] == "…6789"
    arr.save(conn, "movie", arr.clean_prefs("movie", {"url": "http://10.0.0.9:7878"}), clear_key=True)
    assert arr.load(conn, "movie").key == ""


def test_settings_validation():
    p = arr.clean_prefs("show", {"url": " http://x:8989/ ", "profile": "2", "monitor": "future", "evil": 1})
    assert p["url"] == "http://x:8989" and p["profile"] == 2 and p["monitor"] == "future" and "evil" not in p
    for bad in ({"monitor": "everything"}, {"profile": "x"}, {"anime_tags": ["1"]}):
        with pytest.raises(ValueError):
            arr.clean_prefs("show", bad)
    with pytest.raises(ValueError):
        arr.clean_prefs("movie", {"min_availability": "whenever"})


def test_add_bodies():
    movie = arr.Arr(arr.ArrConfig("movie", "http://r", "k", prefs={**arr.PREFS}), None)
    b = movie.add_body({**RADARR_LOOKUP, "id": 0}, "/data/Movies", 5, [], False, True)
    assert b["rootFolderPath"] == "/data/Movies" and b["qualityProfileId"] == 5 and b["monitored"]
    assert b["addOptions"] == {"searchForMovie": True} and b["minimumAvailability"] == "released" and "id" not in b
    show = arr.Arr(arr.ArrConfig("show", "http://s", "k", prefs={**arr.PREFS, "monitor": "all"}), None)
    b = show.add_body(SONARR_LOOKUP, "/data/Anime/Shows", 2, [7], True, False, "future")
    assert b["seriesType"] == "anime" and b["tags"] == [7] and b["seasonFolder"]
    assert b["addOptions"] == {"monitor": "future", "searchForMissingEpisodes": False, "searchForCutoffUnmetEpisodes": False}
    assert show.add_body(SONARR_LOOKUP, "/data/TV", 1, [], False, True)["addOptions"]["monitor"] == "all"


def test_client_sends_key_and_refuses_redirects():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.path == "/api/v3/system/status":
            return httpx.Response(302, headers={"Location": "http://evil/"})
        if req.url.path == "/api/v3/movie/7":
            return httpx.Response(404, json={"message": "NotFound"})
        if req.url.path == "/api/v3/tag":
            return httpx.Response(401)
        return httpx.Response(201, json={**RADARR_LOOKUP, "id": 77})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            c = arr.Arr(arr.ArrConfig("movie", "http://radarr:7878", "secret", prefs={**arr.PREFS}), http)
            added = await c.add({"tmdbId": 1})
            assert added["id"] == 77
            with pytest.raises(arr.ArrError, match="redirected"):
                await c.version()
            with pytest.raises(arr.ArrNotFound):
                await c.get(7)
            with pytest.raises(arr.ArrError, match="refused the API key"):
                await c._req("GET", "/tag")

    asyncio.run(run())
    assert seen[0].headers["X-Api-Key"] == "secret" and seen[0].method == "POST"
    assert str(seen[0].url) == "http://radarr:7878/api/v3/movie"
    assert len([r for r in seen if r.url.host == "evil"]) == 0
