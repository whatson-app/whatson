# 0028. Sort bare guide listings from patterns across the guide

- **Status:** Proposed
- **Date:** 2026-11-08

## Context

Plex labels every listing from an XMLTV guide `type: movie`, with no genres, year or episode numbers, and some XMLTV
sources carry no categories at all. On a real guide, that put 817 of 965 listings in the next three hours under Movies
and none under Shows. News, reality shows and cartoons were all "movies", so the Movies and Shows views were useless.

About a third of the listings were placeholders: one block repeating the channel's name, as guides do for channels they
have no data for. Broadcast networks are often like this. [ADR 0014](0014-match-espn-games-to-listings.md) only linked
games to listings classed as sports, so a game airing on such a network was never linked. The game showed only on a
replay elsewhere that named both teams, and wasn't suggested.

## Decision

After the guide loads, `sort_kinds` (`whatson/ingest.py`) re-sorts listings the server called a movie without a year:

- A placeholder (the title is the channel's name or call sign), a title starting "Live", or a listing on a news,
  business, weather or shopping channel is **other**.
- A title with two or more different descriptions in the guide, or that starts within 30 minutes of the same time on
  another day on the same channel, or that runs under 80 minutes, is a **show**.
- Anything else stays a **movie**.

Sports, and listings with a year, are left as the server sent them.

`link_games` also links a **placeholder** listing to a game when its channel carries the game's network and kickoff
falls in the listing, as for sports listings. A listing linked to a game is stored as sports.

A listing that names both teams links only if it starts no later than 45 minutes after kickoff. One starting later is a
replay, not the game.

## Consequences

- Movies, Shows and Sports work on guides that carry no categories, and a game on a network with no guide data shows
  on that network, in search and in suggestions.
- It's a heuristic. A film shown at the same time on two days counts as a show, and a long one-off programme on a
  general channel can still count as a film.
- A replay of a game no longer carries the game's score or appears in team search.
- The rules are tuned on one real guide. Different guides may need the thresholds or the channel words adjusted.

## Alternatives

Reading the XMLTV feed directly for categories: the feed this was tuned on has none either. Matching titles against a
film database: a new outside service and dependency for every listing. Leaving the kinds alone: the views stay useless.

## Where it lives

`whatson/ingest.py` (`sort_kinds`, `is_placeholder`, `link_games`), `tests/test_guide_kinds.py`. Amends
[ADR 0014](0014-match-espn-games-to-listings.md).
