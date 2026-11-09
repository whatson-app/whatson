from __future__ import annotations

import time

from whatson.ingest import link_games, sort_kinds
from whatson.sources.base import Airing, Channel
from whatson.sources.espn import Game

NOW = int(time.time())
H = 3600
CH = {c.id: c for c in [Channel("1", "1", "Channel One"), Channel("2", "2", "Film Box"),
                        Channel("3", "3", "Lakemont News"), Channel("4", "4", "NBC 5 KDEM", "KDEM")]}


def movie(ch, title, begins, mins, desc="", year=None):
    return Airing(ch, title, "", desc, "movie", begins, begins + mins * 60, year)


def kinds(airings):
    return [a.kind for a in sort_kinds(airings, CH)]


def test_titles_with_different_descriptions_are_shows():
    assert kinds([movie("1", "Harbor Cops", NOW, 90, "The team chases a lead."),
                  movie("1", "Harbor Cops", NOW + 2 * H, 90, "A witness goes missing.")]) == ["episode", "episode"]


def test_a_title_at_the_same_time_on_another_day_is_a_show():
    assert kinds([movie("1", "Morning Lakemont", NOW, 120, "Daily talk."),
                  movie("1", "Morning Lakemont", NOW + 24 * H + 600, 120, "Daily talk.")]) == ["episode", "episode"]


def test_long_one_off_listing_stays_a_movie_and_short_one_is_a_show():
    assert kinds([movie("2", "The Long Voyage", NOW, 125, "Sailors cross an ocean."),
                  movie("2", "Quick Bites", NOW + 3 * H, 30, "Snacks.")]) == ["movie", "episode"]


def test_placeholders_live_and_news_channels_are_other():
    assert kinds([movie("4", "NBC 5 KDEM", NOW, 240), movie("1", "Live: Morning Desk", NOW, 120),
                  movie("3", "Evening Report", NOW, 120, "Headlines.")]) == ["other", "other", "other"]


def test_listings_with_a_year_or_already_sports_are_left_alone():
    sports = Airing("1", "College Football", "", "", "sports", NOW, NOW + 3 * H)
    assert kinds([movie("1", "Short Film", NOW, 20, year=1999), sports]) == ["movie", "sports"]


def game(**kw) -> Game:
    base = dict(id="football/nfl:1", league="football/nfl", name="Comets at Otters", short_name="COM @ OTT",
                starts=NOW - H, state="in", detail="2nd", home="Otters", away="Comets", home_score="7",
                away_score="3", networks=["NBC"], terms=["Otters", "Comets"])
    base.update(kw)
    return Game(**base)


def test_placeholder_on_the_games_network_links_to_the_game():
    airings = [movie("4", "NBC 5 KDEM", NOW - 2 * H, 240), movie("1", "Channel One", NOW - 2 * H, 240)]
    assert list(link_games(sort_kinds(airings, CH), CH, [game()])) == [0]


def test_a_replay_that_names_the_teams_does_not_link():
    replay = Airing("1", "Comets @ Otters - NFL", "", "", "sports", NOW + 2 * H, NOW + 5 * H)
    live = Airing("1", "Comets @ Otters - NFL", "", "", "sports", NOW - H - 600, NOW + 2 * H)
    assert list(link_games([replay, live], CH, [game(networks=[])])) == [1]


def test_linked_placeholder_is_stored_as_sports():
    from whatson import db
    from whatson.ingest import write_games, write_guide
    conn = db.connect(":memory:")
    g = game()
    write_games(conn, [g])
    write_guide(conn, list(CH.values()), sort_kinds([movie("4", "NBC 5 KDEM", NOW - 2 * H, 240)], CH), [g])
    assert tuple(conn.execute("SELECT kind, game_id FROM airings").fetchone()) == ("sports", "football/nfl:1")
