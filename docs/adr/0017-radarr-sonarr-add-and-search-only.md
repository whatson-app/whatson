# 0017. Radarr and Sonarr: add and search only, with no Seerr mode

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

Searching for a title you don't have leads naturally to getting it. Radarr and Sonarr can also delete files and change
settings, and WhatsOn has no login (ADR 0002), so anyone on the network can use whatever it exposes.

## Decision

WhatsOn looks titles up, adds them and starts searches. It **never edits or deletes** anything in Radarr or Sonarr.

- All calls stay in `whatson/arr.py`. It sends only GET and POST, and POSTs only to add a title or to run
  `MoviesSearch` or `SeriesSearch`.
- A switch in Settings turns adding off. While it's on, anyone who can open WhatsOn can add.
- When adding, WhatsOn reads the title from Radarr or Sonarr again instead of trusting what the browser sent.
- Titles added from WhatsOn are remembered in `arr_adds`, so Downloads can follow them until they reach the library.

**A Seerr add mode was decided against.** The reason isn't on record.

## Consequences

- The worst someone on the network can do here is start downloads, and that can be turned off.
- Fixing a wrong add or removing a title happens in Radarr or Sonarr.
- `tests/test_guards.py` reads `whatson/arr.py` and fails on any new method, POST target or command.
- A leftover remains: `PUT /api/settings/seerr` saves an address, and `/api/trakt` and `/api/suggest/library` return it.
  Nothing in the front end uses it and WhatsOn never calls that address. Removing it is a separate change.

## Alternatives

**Letting WhatsOn manage titles fully.** **Inferred:** it conflicts with having no login. **Seerr**, as above.

## Where it lives

`whatson/arr.py`, `whatson/arr_routes.py`, `whatson/static/js/get.js`, `tests/test_arr.py`, `tests/test_guards.py`.
