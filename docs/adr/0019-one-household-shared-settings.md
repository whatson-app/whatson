# 0019. One household, with shared settings

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

With no login (ADR 0002), WhatsOn can't tell people apart.

## Decision

An install serves one household. Follows, favorite channels, TVs and settings are shared on the server. Jellyfin's
watched status and up next come from one chosen user.

Only conveniences for a single device stay in the browser's local storage: the selected TV, the theme, the last section
and the library sort.

## Consequences

- No profiles to set up, and a followed team shows for everyone.
- Up next and watched status reflect one person on Jellyfin, or the account behind the Plex token.
- Each phone remembers its own TV.
- Per-person features would need a way to identify people, which means reopening ADR 0002.

## Alternatives

None on record.

## Where it lives

`whatson/db.py`, `store` in `whatson/static/js/core.js`, `whatson/remote_routes.py`.
