import asyncio
import time
from datetime import datetime, timezone

from whatson import db, suggest
from whatson.ingest import write_games, write_guide, write_library
from whatson.sources.espn import Game
from whatson.sources.plex import Airing, Channel, LibraryItem
from whatson.trakt import guid_keys, norm_title

NOW = int(time.time())


def iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


def make():
    conn = db.connect(":memory:")
    channels = [Channel("4", "4", "CBS 2"), Channel("101", "101", "AMC")]
    airings = [Airing("4", "Tracker", "S03E05", "", "episode", NOW + 1800, NOW + 5400),
               Airing("101", "Halloween", "", "", "movie", NOW - 600, NOW + 6000, 1978)]
    write_guide(conn, channels, airings, [])
    write_library(conn, [
        LibraryItem("55", "movie", "Knives Out", 2019, "", ["Mystery"], [], added_at=NOW, duration=7800000,
                    audience_rating=7.9, guids=["imdb:tt8946378", "tmdb:546554"]),
        LibraryItem("77", "show", "Slow Horses", 2022, "", ["Drama"], [], guids=["tvdb:401000"]),
    ])
    return conn


def test_norm_title_and_guid_keys():
    assert norm_title("The Office (US)") == norm_title("office (us)") == "officeus"
    assert norm_title("Halloween (1978)") == "halloween"
    assert guid_keys({"imdb": "tt1", "tmdb": 5, "trakt": 9}) == {"imdb:tt1", "tmdb:5"}


def test_your_shows_from_trakt_calendar_and_watchlist():
    cache = {"calendar": [{"title": "Tracker", "first_aired": iso(NOW + 1800), "season": 3, "number": 5, "ids": {}}],
             "watchlist": [{"kind": "movie", "title": "Halloween", "year": 1978, "ids": {}}]}
    shows = suggest.live_shows(make(), cache, NOW)
    reasons = {s["title"]: s["reason"] for s in shows}
    assert reasons == {"Tracker": "New episode S03E05", "Halloween": "On your watchlist"}
    assert shows[0]["title"] == "Halloween"  # on now sorts first


def test_up_next_and_missing_match_library_by_ids():
    conn = make()
    cache = {"up_next": [{"title": "Slow Horses", "year": 2022, "ids": {"tvdb": 401000}, "season": 4, "number": 3}],
             "watchlist": [{"kind": "movie", "title": "Knives Out", "year": 2019, "ids": {"imdb": "tt8946378"}},
                           {"kind": "movie", "title": "Conclave", "year": 2024, "ids": {"tmdb": 974576}}]}
    up = suggest.library_up_next(conn, cache)
    assert up[0]["rating_key"] == "77" and up[0]["label"].startswith("S04E03")
    assert [m["title"] for m in suggest.watchlist_missing(conn, cache)] == ["Conclave"]
    pool = suggest.library_candidates(conn, cache)
    assert pool[0]["rating_key"] == "55" and pool[0]["reason"] == "On your watchlist"


def test_worth_switching_close_late_games_only():
    conn = db.connect(":memory:")
    base = dict(league="football/nfl", name="", short_name="", starts=NOW, home="A", away="B", networks=[], terms=[])
    write_games(conn, [
        Game(id="1", state="in", detail="2:10 - 4th", home_score="21", away_score="17", **base),
        Game(id="2", state="in", detail="2:10 - 4th", home_score="35", away_score="7", **base),
        Game(id="3", state="in", detail="8:00 - 2nd", home_score="7", away_score="7", **base),
    ])
    assert [w["id"] for w in suggest.worth_switching(conn)] == ["1"]


def test_game_signal_names_the_team_you_follow():
    conn = db.connect(":memory:")
    base = dict(league="football/nfl", name="", short_name="", starts=NOW, state="in", detail="2:10 - 4th",
                home_score="21", away_score="17", networks=[], terms=[])
    write_games(conn, [Game(id="1", home="Otters", away="Comets", home_id="9", away_id="3", **base),
                       Game(id="2", home="Foxes", away="Pilots", home_id="8", away_id="16", **base)])
    write_guide(conn, [Channel("4", "4", "Channel A"), Channel("5", "5", "Channel B")],
                [Airing("4", "NFL", "", "", "sports", NOW - 600, NOW + 6000),
                 Airing("5", "NFL", "", "", "sports", NOW - 600, NOW + 6000)], [])
    conn.execute("UPDATE airings SET game_id = '1' WHERE channel_id = '4'")
    conn.execute("UPDATE airings SET game_id = '2' WHERE channel_id = '5'")
    conn.execute("INSERT INTO follows VALUES ('team', 'football/nfl', '3', 'Riverton Comets', 'RIV', '')")
    reasons = {c["channel"]["title"]: c["reason"] for c in suggest.live_candidates(conn, {}, NOW)}
    assert reasons["Channel A"] == "You follow Comets: Comets at Otters, 2:10 - 4th"
    assert reasons["Channel B"] == "Pilots at Foxes, 2:10 - 4th"  # same league, but not your team


class FakeAI:
    enabled = True

    def __init__(self, picks):
        self.picks = picks

    async def rank(self, candidates, want, context=""):
        return self.picks


def test_row_is_only_labelled_ai_when_ai_really_ranked_it():
    pool = [{"id": "l1", "type": "library", "title": "Knives Out", "reason": "On your watchlist"}]
    suggest._rank_cache.clear()
    failed = asyncio.run(suggest.ai_rank(FakeAI([]), "t", pool, 4))
    assert failed[0]["reason"] == "On your watchlist" and not suggest.ai_ranked(failed)
    ranked = asyncio.run(suggest.ai_rank(FakeAI([{"id": "l1", "reason": "Fits your taste"}]), "t", pool, 4))
    assert ranked[0]["reason"] == "Fits your taste" and suggest.ai_ranked(ranked)


def test_one_card_per_game_and_none_for_games_already_over():
    conn = db.connect(":memory:")
    base = dict(league="football/nfl", name="", short_name="", networks=[], terms=[], home_score="7", away_score="3")
    write_games(conn, [Game(id="live", home="Otters", away="Comets", starts=NOW - 7200, state="in", detail="3rd", **base),
                       Game(id="over", home="Foxes", away="Pilots", starts=NOW - 9000, state="post", detail="Final", **base)])
    write_guide(conn, [Channel("1", "1", "Channel A"), Channel("2", "2", "Channel B")],
                [Airing("1", "NFL", "", "", "sports", NOW - 7200, NOW + 3600),        # the live broadcast
                 Airing("2", "Comets at Otters", "", "", "sports", NOW + 1800, NOW + 9000),  # a replay later
                 Airing("2", "Pilots at Foxes", "", "", "sports", NOW - 9000, NOW + 600)], [])  # finished game
    conn.execute("UPDATE airings SET game_id = 'live' WHERE title IN ('NFL', 'Comets at Otters')")
    conn.execute("UPDATE airings SET game_id = 'over' WHERE title = 'Pilots at Foxes'")
    conn.execute("INSERT INTO follows VALUES ('league', 'football/nfl', '', '', '', '')")
    picks = suggest.live_candidates(conn, {}, NOW)
    assert [(p["title"], p["channel"]["title"]) for p in picks] == [("NFL", "Channel A")]


def test_a_game_pick_is_named_for_the_game_not_the_channel():
    conn = db.connect(":memory:")
    base = dict(league="football/nfl", name="", short_name="", starts=NOW, state="in", detail="2nd",
                home_score="7", away_score="3", networks=[], terms=[])
    write_games(conn, [Game(id="1", home="Otters", away="Comets", home_id="9", away_id="3", **base)])
    write_guide(conn, [Channel("4", "4", "Channel A")], [Airing("4", "Channel A", "", "", "other", NOW - 600, NOW + 6000)], [])
    conn.execute("UPDATE airings SET game_id = '1'")
    conn.execute("INSERT INTO follows VALUES ('league', 'football/nfl', '', '', '', '')")
    [pick] = suggest.live_candidates(conn, {}, NOW)
    assert pick["game"]["away"] == "Comets" and pick["game"]["home"] == "Otters"

    class Ranker:
        enabled = True
        seen = []

        async def rank(self, candidates, want, context=""):
            Ranker.seen = candidates
            return []

    suggest._rank_cache.clear()
    asyncio.run(suggest.ai_rank(Ranker(), "t", [pick], 4))
    assert Ranker.seen[0]["text"].startswith("Comets at Otters")
