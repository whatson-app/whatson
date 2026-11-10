"""Finding an episode by its own title (ADR 0030): the Plex and Jellyfin episode lists, storing them, and search."""

import asyncio

import httpx

from whatson import db, search
from whatson.ingest import Refresher, write_episodes, write_library
from whatson.sources.base import Episode, LibraryItem
from whatson.sources.jellyfin import Jellyfin
from whatson.sources.plex import PlexClient

SHOW_ID, EP1, EP2 = "b" * 32, "d" * 32, "e" * 32


def run(coro):
    return asyncio.run(coro)


def library_db(rating: str = "TV-Y7") -> "db.sqlite3.Connection":
    conn = db.connect(":memory:")
    write_library(conn, [
        LibraryItem("10", "show", "Critter Crew", 2011, "Two brothers meet animals", ["Kids"], content_rating=rating,
                    thumb="/library/metadata/10/thumb/1"),
        LibraryItem("20", "movie", "Pond Life", 2001, "A documentary", ["Documentary"])])
    write_episodes(conn, [
        Episode("101", "10", "Critter Crew", 7, 15, "Goose, Goose, Heron!"),
        Episode("102", "10", "Critter Crew", 7, 16, "Shapes of the Armadillo"),
        Episode("901", "99", "Gone Show", 1, 1, "Goose, Goose, Heron!")])   # its show left the library
    return conn


def test_an_episode_is_found_by_its_own_title():
    res = search.run(library_db(), search.basic_filters("Goose Goose Heron"))
    assert res["library"] == []   # no show or movie has those words
    [ep] = res["episodes"]
    assert ep == {"type": "episode", "rating_key": "101", "show_key": "10", "show_title": "Critter Crew", "season": 7,
                  "index": 15, "title": "Goose, Goose, Heron!", "label": "S07E15 Goose, Goose, Heron!",
                  "thumb": "/library/metadata/10/thumb/1", "year": 2011}


def test_episodes_follow_the_search_filters():
    conn = library_db()
    for f in (search.Filters(text="heron", kinds=["movie"]), search.Filters(text="heron", on_now=True),
              search.Filters(text="heron", scope="guide"), search.Filters(text="heron", genres=["Horror"]),
              search.Filters(text="")):
        assert search.run(conn, f)["episodes"] == [], f
    assert search.run(conn, search.Filters(text="heron", kinds=["episode"]))["episodes"]
    assert search.run(conn, search.Filters(text="heron", audience="kids"))["episodes"]
    assert not search.run(library_db(rating="TV-MA"), search.Filters(text="heron", audience="kids"))["episodes"]


def test_an_episode_needs_every_word():
    # One shared word isn't enough: "goose" alone matches, "goose armadillo" matches nothing.
    conn = library_db()
    assert [e["title"] for e in search.run(conn, search.Filters(text="goose"))["episodes"]] == ["Goose, Goose, Heron!"]
    assert search.run(conn, search.Filters(text="goose armadillo"))["episodes"] == []


def test_typed_episode_matches_are_not_repeated_in_the_ai_part():
    conn = library_db()
    out = search.run(conn, search.Filters(text="heron"))
    typed = search.split_typed(search.run(conn, search.basic_filters("goose goose heron")), out)
    assert [e["rating_key"] for e in typed["episodes"]] == ["101"] and out["episodes"] == []


def test_switching_server_forgets_the_episodes():
    conn = library_db()
    db.clear_server_data(conn)
    assert conn.execute("SELECT count(*) FROM episodes").fetchone()[0] == 0
    assert search.run(conn, search.Filters(text="heron"))["episodes"] == []


def test_plex_lists_episodes_of_show_sections_page_by_page(monkeypatch):
    monkeypatch.setattr("whatson.sources.plex.PAGE", 2)
    seen = []
    eps = [{"ratingKey": 101, "grandparentRatingKey": 10, "grandparentTitle": "Critter Crew", "parentIndex": 7,
            "index": 15, "title": "Goose, Goose, Heron!"},
           {"ratingKey": 102, "grandparentRatingKey": 10, "grandparentTitle": "Critter Crew", "title": "Special"},
           {"ratingKey": 103, "grandparentRatingKey": 10, "title": ""}]   # no title: nothing to search for

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.path == "/library/sections":
            return httpx.Response(200, json={"MediaContainer": {"Directory": [
                {"key": "1", "type": "movie", "title": "Movies"}, {"key": "2", "type": "show", "title": "TV Shows"}]}})
        start = int(req.headers["X-Plex-Container-Start"])
        return httpx.Response(200, json={"MediaContainer": {"totalSize": 3, "Metadata": eps[start:start + 2]}})

    plex = PlexClient("http://plex.example.com:32400", "t", http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    out = run(plex.library_episodes())
    assert out == [Episode("101", "10", "Critter Crew", 7, 15, "Goose, Goose, Heron!"),
                   Episode("102", "10", "Critter Crew", None, None, "Special")]
    lists = [r for r in seen if r.url.path != "/library/sections"]
    assert [r.url.path for r in lists] == ["/library/sections/2/all"] * 2   # the movie section isn't asked
    assert lists[0].url.params["type"] == "4" and "summary" in lists[0].url.params["excludeFields"]


def test_jellyfin_lists_episodes_for_its_user():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json={"Items": [
            {"Id": EP1, "SeriesId": SHOW_ID, "SeriesName": "Critter Crew", "ParentIndexNumber": 7, "IndexNumber": 15,
             "Name": "Goose, Goose, Heron!"},
            {"Id": EP2, "Name": "No show"}]})

    jf = Jellyfin("http://jf.example.com:8096", "k3y", httpx.AsyncClient(transport=httpx.MockTransport(handler)), "u1")
    assert run(jf.library_episodes()) == [Episode(EP1, SHOW_ID, "Critter Crew", 7, 15, "Goose, Goose, Heron!")]
    assert seen[0].url.params["IncludeItemTypes"] == "Episode" and seen[0].url.params["userId"] == "u1"


class FakeSource:
    name, label, configured = "plex", "Plex", True

    def __init__(self, episodes):
        self.episodes = episodes

    async def library(self):
        return [LibraryItem("10", "show", "Critter Crew", 2011, "")]

    async def library_episodes(self):
        if isinstance(self.episodes, Exception):
            raise self.episodes
        return self.episodes


def test_a_library_refresh_stores_the_episodes():
    conn = db.connect(":memory:")
    refresher = Refresher(object(), conn, FakeSource([Episode("101", "10", "Critter Crew", 7, 15, "Goose, Goose, Heron!")]))
    run(refresher.refresh_library())
    assert [e["label"] for e in search.run(conn, search.Filters(text="heron"))["episodes"]] == ["S07E15 Goose, Goose, Heron!"]


def test_episodes_failing_to_load_keeps_the_library_and_the_old_episodes():
    conn = library_db()
    run(Refresher(object(), conn, FakeSource(httpx.ConnectError("down"))).refresh_library())
    assert conn.execute("SELECT count(*) FROM library").fetchone()[0] == 1   # the new library was written
    assert search.run(conn, search.Filters(text="heron"))["episodes"]
