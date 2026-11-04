# 0012. A source protocol, and one media server at a time

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

WhatsOn started on Plex and gained Jellyfin in 0.2.0. Channels, items and sessions have different ids on each server, and
Plezy needs to know which server to play from.

## Decision

Media servers implement the `Source` protocol in `whatson/sources/base.py`. Shared code talks to `state.source` and doesn't
reach for Plex or Jellyfin directly.

WhatsOn reads **one server at a time and doesn't merge them**. Switching in Settings clears everything tied to the old
server's ids, including favorite channels, and reloads. A guide or library still loading from the old server when the
switch happens is thrown away rather than written over the new one.

## Consequences

- Search, suggestions and tuning work the same on either server.
- Switching servers loses favorite channels. The README says so.
- The busy check only sees the server in use (ADR 0011).
- Some names keep their Plex origin: `rating_key` holds any server's item id.
- Direct control of Jellyfin apps on the Remote tab is Jellyfin-only and sits outside `Source`. It's a server feature with
  no Plex equivalent in WhatsOn.
- Sources differ in what they provide. Plex's Live TV sessions don't say which channel they're on, so now-playing falls
  back on the last channel tuned (`state.last_tune`). Jellyfin's do.

## Alternatives

**Merging both servers** was left out: the docs state "doesn't merge" as a limit. **Inferred:** because of duplicate
titles and channels and the different ids; the reason isn't on record.

## Where it lives

`whatson/sources/base.py`, `whatson/source_routes.py`, `clear_server_data` in `whatson/db.py`, `tests/test_sources.py`.
