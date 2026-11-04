# 0004. Plain JavaScript modules, no build step and nothing from the web

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

The front end is one page with a handful of sections, served by the app itself. **Inferred:** contributors should be able
to change it and reload, and a page on a home network shouldn't depend on scripts from outside hosts.

## Decision

The front end is plain JavaScript modules in `whatson/static/js/`, with one module per section and a small hash router in
`main.js`. There's no framework, no `package.json` and no build step. No script or stylesheet loads from a CDN, and API
calls go to the server with `api()`. Library artwork goes through `/api/thumb`.

The server sends the page and scripts with `Cache-Control: no-cache`, so an update shows on the next load.

## Consequences

- Reloading the page picks up a change, and there's no toolchain to keep up to date.
- Screens build HTML as strings, so `esc()` around anything from outside is a rule that needs review as well as tests.
- There are no browser tests. `tests/test_progress_ui.py` and `tests/test_settings_layout.py` only check that wiring is
  in place, so how a screen looks still has to be checked by a person.
- `tests/test_guards.py` refuses `package.json`, outside addresses written into the scripts and pages, and running text as
  code.
- **Known gap:** `AGENTS.md` says the browser never calls an outside service directly, but some images do. Team logos come
  straight from the addresses ESPN gives, and Radarr and Sonarr posters and some channel art load from wherever their URLs
  point. The guard can't see these, because the URLs arrive as data.

## Alternatives

**Inferred:** a framework with a bundler. No record of it being weighed; `AGENTS.md` says only that the absence of a
build step is on purpose.

## Where it lives

`whatson/static/`, `whatson/AGENTS.md`, [frontend.md](../frontend.md). See also ADR 0024.
