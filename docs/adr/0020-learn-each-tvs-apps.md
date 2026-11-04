# 0020. Learn each TV's apps, and open them by link

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

The Remote tab has a row of apps. A TV can't list its installed apps over the remote protocol. Google TV also stopped
letting other apps open apps by package name in an August 2026 Play Store update, though older Android TV devices may
still allow it.

## Decision

- **Build each TV's row from what's seen.** Apps WhatsOn has seen in front on that TV, plus the ones the person ticks,
  stored in `tv_apps`. A TV with nothing recorded shows a short default list.
- **Open by link where one is known,** and by package name otherwise. Report whether the app really came to the front.
- Parts of the TV itself, like its Settings app, go in `SYSTEM`, so they're named when in front but left off the row.

## Consequences

- The row starts generic and improves with use.
- Apps with no link (Jellyfin, Kodi) may not open on Google TV. The README says so, and the response's `by_link` lets the
  screen explain it.
- A new link has to be tried on a real TV before it's added to `CATALOG`.
- Links to streaming sites are on the allowed hosts list, marked as links WhatsOn never calls itself.

## Alternatives

Package names alone no longer work on Google TV. Reading installed apps through ADB is ruled out by ADR 0009.

## Where it lives

`whatson/apps.py`, `whatson/remote_routes.py`, `whatson/static/js/remote.js`, `tests/test_remote.py`.
