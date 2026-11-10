# 0030. Search finds episodes by their own titles

- **Status:** Proposed
- **Date:** 2026-11-10

## Context

The local copy of the library held movies and shows only, so search matched a show's name, summary, genres and cast, never
an episode's title. A search for an episode such as "Duck, Duck, Loon!" found nothing even when the server had it, and the
person had to know which show it belonged to. ADR 0029 makes sure the words as typed are searched for; without episode
titles in the local copy there was still nothing for them to match. The live guide can't fill the gap either: guides fed
from XMLTV through Plex arrive with no episode titles at all.

## Decision

WhatsOn keeps every library episode's title, season and number, and search matches episodes by their title.

- `Source` gains `library_episodes()`, called right after `library()` on the same timer. Plex lists each TV section with
  `type=4`, leaving out summaries, artwork and media details. Jellyfin lists items of type `Episode` for the configured user.
- They're stored in `episodes` and indexed by title in `episodes_fts`, rebuilt on each library refresh and cleared when
  switching server. If they fail to load, the library is still written and the previous episodes stay.
- `search.run` returns them in `episodes` for text searches over the library: every word must be in the title, the show
  must be in the library, at most 20 come back, and the show's genres, rating and year stand in for the episode's.
- The results page shows them in an "Episodes" row, each with Play and Open the show. `/api/answer` sees them too.

## Consequences

- An episode can be found and played by its name alone.
- A library refresh reads every episode, which is tens of thousands of items on a big library. On a test library of about
  44,000 episodes that's 23 pages and roughly 80 MB from Plex, about 15 seconds, every `LIBRARY_REFRESH_MINUTES` (6 hours
  by default). The local database grows by a few megabytes.
- Episodes don't carry watched status, so they show no tick, and they don't take part in suggestions or Trakt matching.
- Episode summaries aren't searched, so describing an episode ("the one with the loon") still won't find it.
- Every source must implement one more method.

## Alternatives

- **Ask the server's own search when a search runs.** No extra storage, but it's a network call on every search, Plex's
  search missed this exact episode in testing, and search would stop working while the server is unreachable.
- **Store episodes as `library` rows of kind `episode`.** One table, but suggestions, Trakt matching, the Library tab and
  watched status all read `library` and assume movies and shows.
- **Also index episode summaries.** Finds more, but one shared word in a summary would bring back pages of unrelated
  episodes. Left for later.

## Where it lives

`library_episodes` in `whatson/sources/base.py`, `whatson/sources/plex.py` and `whatson/sources/jellyfin.py`;
`write_episodes` and `Refresher.refresh_library` in `whatson/ingest.py`; `episodes` and `episodes_fts` in `whatson/db.py`;
`search_episodes` in `whatson/search.py`; `episodeCard` in `whatson/static/js/cards.js` and `whatson/static/js/results.js`;
`tests/test_episodes.py`. Builds on ADR 0005, ADR 0012 and ADR 0029.
