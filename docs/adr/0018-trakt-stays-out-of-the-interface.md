# 0018. Trakt stays in the code but out of the interface

- **Status:** Superseded by ADR 0027
- **Date:** 2026-11-03

## Context

Trakt can feed suggestions with ratings, a watchlist and a calendar. A shared client secret can't ship in open source, so
each self-hoster would have to register their own Trakt API app.

## Decision

Keep `whatson/trakt.py`, its routes and its use in `whatson/suggest.py`, but show **no interface** for it for now. Don't
wire it back in without being asked. The reason for holding it back isn't on record.

Suggestions fill from rules alone when there's no Trakt data.

## Consequences

- Code with no way to reach it from the app has to be kept working, along with its routes and tests.
- The sync task still starts with the app, and returns straight away when Trakt isn't connected.
- `api.trakt.tv` stays on the allowed hosts list, though no one using the interface can connect to it.
- `tests/test_guards.py` fails if the front end calls `/api/trakt`.

## Alternatives

**Inferred:** removing it, which would lose working code if it comes back. Not on record as having been weighed.

## Where it lives

`whatson/trakt.py`, `whatson/routes.py`, `whatson/suggest.py`, `tests/test_guards.py`.
