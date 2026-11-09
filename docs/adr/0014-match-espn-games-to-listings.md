# 0014. Match ESPN games to guide listings by network and kickoff

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

Guide listings rarely name the teams, so a team name can't find the game. This is the problem WhatsOn exists to solve.
ESPN's public scoreboard feed has teams, start times, scores and TV networks. It's unofficial and undocumented, and may
change without notice.

## Decision

Use ESPN's scoreboard feed for games and scores, and link a game to a sports listing in `link_games`
(`whatson/ingest.py`) when either:

- The channel carries one of the game's networks, and kickoff falls from 45 minutes before the listing up to its end.
  Not when the listing names a different sport, because a network's name can be part of another channel's name
  ("Fox Soccer Plus" for a game on Fox). Added 2026-11-08.
- The channel or listing names both teams, and kickoff falls from 3 hours before the listing up to its end. This handles
  event channels, which name the teams all day.

[ADR 0028](0028-sort-bare-guide-listings.md) (2026-11-08) narrows the second rule to 45 minutes, so a replay doesn't
link, and lets the first rule link placeholder listings that only repeat the channel's name.

A linked airing stores `game_id` and gets the teams' names in its search index. Games refresh first, so the guide can link
them, every few minutes, and every 30 seconds while a followed team or league is playing.

## Consequences

- A team name finds the right channel, even when the listing says only the sport.
- If ESPN changes or drops the feed, games and scores go, and the guide and library still work. An empty result doesn't
  overwrite the last good games.
- Network names need an alias table (`NETWORK_ALIASES`), and matching can miss or mislink. `tests/test_core.py` pins the
  known cases.
- College feeds need a `GROUPS` entry, or they only list ranked and featured games.
- The README tells people the feed is unofficial.

## Alternatives

**Inferred:** a paid sports data API would cost self-hosters a key and a bill, and is a new outside service. Not on
record as having been weighed.

## Where it lives

`whatson/sources/espn.py`, `whatson/ingest.py`, `tests/test_core.py`.
