import time

from whatson import db, search, tune
from whatson.ingest import link_games, write_games, write_guide, write_library
from whatson.sources import espn
from whatson.sources.espn import Game, network_matches
from whatson.sources.plex import Airing, Channel, LibraryItem, classify

NOW = int(time.time())


def game(**kw) -> Game:
    base = dict(id="football/college-football:1", league="football/college-football",
                name="Illinois Fighting Illini at Maryland Terrapins", short_name="ILL @ MD",
                starts=NOW - 3600, state="in", detail="5:12 - 4th", home="Maryland", away="Illinois",
                home_score="17", away_score="20", networks=["FS1"],
                terms=["Illinois Fighting Illini", "Illinois", "Fighting Illini", "ILL", "Maryland"])
    base.update(kw)
    return Game(**base)


def test_network_matching():
    assert network_matches("FS1", "FOX SPORTS 1")
    assert not network_matches("FOX", "FOX SPORTS 1")
    assert network_matches("FOX", "FOX 32 WFLD Chicago")
    assert network_matches("FOX", "8 FOX 32 WFLD Chicago")
    assert network_matches("BTN", "BIG TEN NETWORK")
    assert network_matches("ESPN2", "ESPN 2")
    assert not network_matches("ESPN", "ESPNU")
    assert network_matches("ABC", "ABC 7 WLS Chicago")


def test_classify():
    assert classify("Live: College Football", "", "movie", []) == "sports"
    assert classify("Halloween", "Michael Myers returns", "movie", []) == "movie"
    assert classify("Bluey", "", "episode", []) == "episode"


def test_link_games_by_network_and_time():
    channels = {"706": Channel("706", "706", "FOX SPORTS 1"), "7": Channel("7", "7", "FOX 6 WITI")}
    airings = [Airing("706", "Live: College Football", "", "", "sports", NOW - 4000, NOW + 3000),
               Airing("7", "Live: College Football", "", "", "sports", NOW - 4000, NOW + 3000)]
    links = link_games(airings, channels, [game()])
    assert list(links) == [0]


def test_link_games_by_team_names_in_channel():
    channels = {"1045": Channel("1045", "1045", "NCAAF 01: Illinois at Maryland 11am")}
    airings = [Airing("1045", "NCAAF 01: Illinois at Maryland 11am", "", "filler", "sports", NOW - 9000, NOW + 9000)]
    assert 0 in link_games(airings, channels, [game(networks=[])])


def make_db():
    conn = db.connect(":memory:")
    g = game()
    channels = [Channel("706", "706", "FOX SPORTS 1"), Channel("1050", "1050", "NCAAF 06: FS1"),
                Channel("101", "101", "AMC")]
    airings = [Airing("706", "Live: College Football", "", "From Maryland", "sports", NOW - 4000, NOW + 3000),
               Airing("101", "Halloween", "", "Michael Myers", "movie", NOW + 600, NOW + 7800, 1978)]
    write_games(conn, [g])
    write_guide(conn, channels, airings, [g])
    write_library(conn, [LibraryItem("55", "movie", "Halloween", 1978, "Slasher classic", ["Horror"], ["Jamie Lee Curtis"])])
    return conn


def test_team_search_finds_channel():
    conn = make_db()
    res = search.search_guide(conn, search.basic_filters("illini game"), NOW)
    assert res and res[0]["channels"][0]["vcn"] == "706"
    assert res[0]["game"]["away_score"] == "20" and res[0]["on_now"]


def test_library_and_people_search():
    conn = make_db()
    out = search.run(conn, search.Filters(text="jamie lee curtis"))
    assert out["library"][0]["rating_key"] == "55"
    assert search.run(conn, search.Filters(text="halloween"))["guide"][0]["channels"][0]["vcn"] == "101"


def test_finished_game_still_found():
    conn = make_db()
    write_games(conn, [game(state="post", detail="Final")])
    games = search.run(conn, search.basic_filters("is the illini game on"))["games"]
    assert games and games[0]["detail"] == "Final" and games[0]["away_score"] == "20"


def test_filter_words_not_searched():
    f = search.basic_filters("sports on now")
    assert f.kinds == ["sports"] and f.on_now and search.fts_query(f.text) == ""


def test_sports_board():
    board = search.sports_board(make_db(), NOW)
    assert board[0]["channels"][0]["vcn"] == "706"


def test_ai_settings_saved_beat_env_and_never_leak(monkeypatch):
    from whatson import ai_settings
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-1234567890")
    conn = db.connect(":memory:")
    cfg = ai_settings.load(conn)
    assert cfg.provider == "openai" and cfg.key() == "sk-env-1234567890"
    ai_settings.save(conn, "anthropic", "", "", {"anthropic": "sk-ant-secret-abcd"}, [])
    cfg = ai_settings.load(conn)
    assert cfg.provider == "anthropic" and cfg.key() == "sk-ant-secret-abcd"
    pub = ai_settings.public(cfg, True)
    assert "secret" not in str(pub) and pub["keys"]["anthropic"]["hint"] == "…abcd"
    assert pub["keys"]["openai"]["source"] == "env"
    ai_settings.save(conn, "anthropic", "", "", {}, ["anthropic"])
    assert ai_settings.load(conn).key() == ""


def test_saved_key_never_follows_a_changed_base_url(monkeypatch):
    import pytest
    from whatson import ai_settings
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-1234567890")
    conn = db.connect(":memory:")
    ai_settings.save(conn, "openai", "m", "", {"openai": "sk-saved-1234567890"}, [])
    assert ai_settings.load(conn).key() == "sk-saved-1234567890"
    # Someone repoints the base URL without supplying a key: neither saved nor .env key goes there.
    ai_settings.save(conn, "openai", "m", "http://203.0.113.9/v1", {}, [])
    assert ai_settings.load(conn).key() == ""
    # Re-entering the key for the new URL binds it there.
    ai_settings.save(conn, "openai", "m", "http://192.168.1.20:1234/v1", {"openai": "sk-local-123456789"}, [])
    assert ai_settings.load(conn).key() == "sk-local-123456789"
    with pytest.raises(ValueError):
        ai_settings.save(conn, "openai", "m", "file:///etc/passwd", {}, [])


def test_interpreter_off_without_key_or_model():
    from whatson.ai import Interpreter
    assert not Interpreter("anthropic", api_key="").enabled
    assert not Interpreter("openrouter", api_key="k", model="").enabled
    assert Interpreter("anthropic", api_key="k").enabled


def test_local_server_needs_no_key_and_has_a_time_limit():
    from whatson.ai import Interpreter
    lm = Interpreter("openai", model="qwen3-8b", base_url="http://192.168.1.20:1234/v1", timeout=12)
    assert lm.enabled and lm._client.timeout == 12 and lm._client.max_retries == 0
    assert not Interpreter("openai", model="gpt-x").enabled         # real OpenAI still needs a key
    assert not Interpreter("openrouter", model="a/b", base_url="http://x").enabled


def test_custom_url_only_kept_for_openai():
    from whatson import ai_settings
    conn = db.connect(":memory:")
    ai_settings.save(conn, "anthropic", "", "http://leftover:1234/v1", {"anthropic": "sk-ant-123456789"}, [])
    cfg = ai_settings.load(conn)
    assert cfg.base_url == "" and cfg.key() == "sk-ant-123456789"


def test_host_guard():
    from whatson.app import host_allowed
    assert host_allowed("192.168.1.10:8430") and host_allowed("localhost:8431") and host_allowed("[::1]:8430")
    assert not host_allowed("evil.example.com") and not host_allowed("rebind.attacker.net:8430")


def test_links():
    assert tune.live_link("706") == "plezy://live?channel=706&start=live"
    assert tune.live_link("706", "abc") == "plezy://live?channel=706&start=live&server=abc"
    assert tune.play_link("abc", "55") == "plezy://play?server=abc&id=55"
    assert search.fts_query("what's on: the Illini game") == '"illini"*'


def test_replayed_filters_are_validated():
    import pytest
    f = search.parse_filters('{"text": "bears", "kinds": ["sports"], "max_minutes": 120, "on_now": true}')
    assert f.text == "bears" and f.kinds == ["sports"] and f.max_minutes == 120 and f.on_now
    for bad in ('{"max_minutes": "' + "9" * 5000 + '"}', '{"max_minutes": 10000000}', '{"kinds": ["x"]}',
                '{"text": ' + '"' + "a" * 300 + '"}', '{"scope": "everything"}', '[1, 2]', '{"max_minutes": true}'):
        with pytest.raises(ValueError):
            search.parse_filters(bad)


def test_ai_server_url_check():
    import pytest
    from whatson.ai_settings import check_base_url
    for ok in ("", "http://192.168.1.20:1234/v1", "http://localhost:11434/v1", "http://127.0.0.1:1234/v1"):
        check_base_url(ok)
    for bad in ("file:///etc/passwd", "http://169.254.169.254/latest", "http://metadata.google.internal/", "ftp://x",
                "http://2852039166/latest", "http://[::ffff:169.254.169.254]/", "http://METADATA./",
                "http://no-such-host.invalid/v1", "http://100.100.100.200/", "http://[fd00:ec2::254]/",
                "http://[2002:a9fe:a9fe::1]/", "http://[64:ff9b::a9fe:a9fe]/", "http://[2001:0:4136:e378:8000:63bf:5601:5601]/"):
        with pytest.raises(ValueError):
            check_base_url(bad)


def search_db():
    conn = db.connect(":memory:")
    channels = [Channel("1", "1", "DISNEY JR"), Channel("2", "2", "ESPN"), Channel("3", "3", "DISNEY CHANNEL"),
                Channel("4", "4", "AMC"), Channel("5", "5", "STARZ KIDS & FAMILY")]
    airings = [Airing("1", "Bluey", "S01E22 The Pool", "", "episode", NOW - 600, NOW + 900),
               Airing("2", "Live Tennis", "", "", "sports", NOW - 600, NOW + 3600),
               Airing("3", "Big City Greens", "", "Cricket goes to the city", "episode", NOW, NOW + 1800),
               Airing("4", "PGA Tour Golf", "", "Bay Hill", "sports", NOW, NOW + 7200),
               Airing("5", "Let Us In", "", "Horror", "movie", NOW, NOW + 5400)]
    write_guide(conn, channels, airings, [])
    write_library(conn, [LibraryItem("1", "movie", "Groundhog Day", 1993, "Comedy loop", ["Comedy"]),
                         LibraryItem("2", "movie", "Superbad", 2007, "Teen comedy", ["Comedy"]),
                         LibraryItem("3", "movie", "Heat", 1995, "Crime", ["Crime"])])
    return conn


def test_decade_becomes_a_year_filter():
    f = search.take_decade(search.Filters(text="90s", kinds=["movie"], genres=["comedy"]))
    assert (f.text, f.year_from, f.year_to) == ("", 1990, 1999)
    assert [i["title"] for i in search.run(search_db(), f)["library"]] == ["Groundhog Day"]
    assert search.take_decade(search.Filters(text="1980s horror")).year_from == 1980
    assert search.basic_filters("comedies from the 2000s").year_to == 2009
    assert search.parse_filters('{"year_from": 1990, "year_to": 1999}').year_to == 1999


def test_kids_on_live_tv_goes_by_channel_and_skips_sports():
    f = search.Filters(scope="guide", audience="kids")
    titles = {i["title"] for i in search.search_guide(search_db(), f, NOW)}
    assert titles == {"Bluey", "Big City Greens"}
    cartoons = search.Filters(scope="guide", on_now=True, genres=["animation"])
    assert {i["title"] for i in search.search_guide(search_db(), cartoons, NOW)} == {"Bluey", "Big City Greens"}
    family = {i["title"] for i in search.search_guide(search_db(), search.Filters(audience="family"), NOW)}
    assert "Let Us In" in family


def test_any_word_fallback_needs_most_words():
    titles = [i["title"] for i in search.search_guide(search_db(), search.Filters(text="green bay packers"), NOW)]
    assert titles == []
    # Two of three words is still a match.
    assert [i["title"] for i in search.search_guide(search_db(), search.Filters(text="big city ducks"), NOW)] == ["Big City Greens"]


def test_following_a_school_covers_its_other_college_sports_but_pro_ids_stay_in_their_league():
    rows = [{"league": "football/college-football", "team_id": "356"}, {"league": "hockey/nhl", "team_id": "4"}]
    keys = espn.followed_team_keys(rows)
    assert espn.is_followed_game(keys, "basketball/mens-college-basketball", "356", "161")   # Illini hoops
    assert espn.is_followed_game(keys, "hockey/nhl", "1", "4")
    assert not espn.is_followed_game(keys, "basketball/nba", "4", "9")                     # a different team 4
