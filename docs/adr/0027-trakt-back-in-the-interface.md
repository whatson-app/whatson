# 0027. Trakt is back in the interface, as an optional section under More

- **Status:** Proposed
- **Date:** 2026-11-08

## Context

[ADR 0018](0018-trakt-stays-out-of-the-interface.md) kept Trakt's code but took its interface out, with no reason on
record. Without Trakt, suggestions have no taste to go on. "Tonight's pick" can only choose among recently added,
well-rated movies, and AI ranks them from title and genres alone. The maintainer asked for Trakt back.

Each self-hoster still has to register their own free Trakt API app, because a shared client secret can't ship in open
source.

## Decision

Show Trakt again as an optional section in ⚙ → More, beside AI search and Downloads: save your own Trakt app's client ID
and secret, connect with a device code, sync now, and disconnect. The rows that use it come back:

- Live TV: "Your shows on tonight".
- Library: "Up next" from Trakt, and "On your watchlist, not in your library", with "Get it" when Radarr or Sonarr is
  connected for that kind. There's no Seerr link; that setting was removed.
- Suggestions use Trakt's watchlist, recommendations, ratings and recent viewing, as `whatson/suggest.py` already did.

A TV with its own Plex Home user still skips Trakt, because Trakt follows one account
([ADR 0025](0025-a-plex-home-user-for-each-tv.md)).

## Consequences

- People who want better suggestions have a way to get them. Setting up a Trakt app is the hard part, and the section
  says how.
- With AI search on, up to 15 titles rated 8 or higher and the 10 most recently watched shows are sent to the AI
  provider with each suggestion request. The README's "How AI works" says so.
- The front end may call `/api/trakt` again, so the guard test that blocked it is gone.
- The client secret and tokens stay on the server and are never sent back to the page.

## Alternatives

Keeping it out, which leaves suggestions taste-blind. A shared Trakt app run by the project, which would mean shipping or
hosting a secret. Plex's own ratings and history as the taste source instead: possible later, and not exclusive with this.

## Where it lives

`whatson/static/index.html`, `whatson/static/js/settings.js`, `whatson/static/js/live.js`, `whatson/static/js/library.js`,
`whatson/trakt.py`, `whatson/suggest.py`, `tests/test_guards.py`. Supersedes [ADR 0018](0018-trakt-stays-out-of-the-interface.md).
