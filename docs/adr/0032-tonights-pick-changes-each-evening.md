# 0032. Tonight's pick changes each evening

- **Status:** Proposed
- **Date:** 2026-11-26

## Context

Tonight's pick on the Library → Movies page showed the same film day after day. Its pool was the watchlist, Trakt
recommendations and the 25 most recently added unwatched movies rated 7 or more. That set only changed when a movie was
added. The AI got the list in the same order every time and had no memory of earlier picks, so the same input got the
same answer.

## Decision

- **A new sample each evening.** The well-rated movies are a random 25 of all unwatched ones rated 7 or more, seeded by
  the evening's date (`suggest.pick_day`, which rolls over at 4am), not the newest 25.
- **A shuffled order.** `suggest.tonights_pool` shuffles the pool with the same seed before the AI ranks it, so the first
  entry isn't always favored.
- **Last week's picks rest.** `suggest.remember_pick` stores each evening's top pick in `meta.pick_history`. A movie
  that was the top pick in the last 7 days stays out of the pool, unless fewer than 4 others are left.
- **Held for the evening.** The AI ranking is cached for the day (keyed by day and Plex Home viewer), not for 15
  minutes, so the pick doesn't change during the evening.

## Consequences

- The pick and the row change every evening and stay put through it. AI off gives a different rule-order pick each day too.
- Only the owner's picks (TVs with no Plex Home user) are remembered. Another viewer's row still rotates with the sample
  and the shuffle.
- Watchlist and Trakt recommended movies are always in the pool. With a short list and AI off, those can still lead most
  evenings.

## Alternatives

- **Raise the AI temperature.** Varies the answer, but at random through the evening, and does nothing with AI off. Not done.
- **Tell the AI what it picked before.** Uses up prompt space and relies on the model listening. Resting a pick in the
  pool is certain. Not done.

## Where it lives

- `whatson/suggest.py`: `library_candidates`, `pick_day`, `tonights_pool`, `remember_pick`
- `whatson/routes.py`: `suggest_library`
- `tests/test_suggest.py`
