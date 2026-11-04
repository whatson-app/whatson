# 0006. Stop other web pages with a required header and a host check

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

With no login (ADR 0002), the network boundary isn't enough. Any web page open in a browser on the home network could
otherwise send requests to WhatsOn and pair or tune TVs, directly or through DNS rebinding.

## Decision

Middleware in `whatson/app.py` applies two checks to every request:

- **`X-WhatsOn: 1` on anything that changes something** (every method but GET, HEAD and OPTIONS). Browsers only send a
  custom header cross-site after a CORS preflight, and this app never approves one. The front end's `api()` sends it.
- **A known `Host`.** IP literals and `localhost` always pass. Names pass only when listed in `ALLOWED_HOSTS`. Rebinding
  needs a name the attacker controls, so refusing unknown names defeats it.

No route is exempt. GET routes must not change anything people set up. The one exception on record is noting which app a
TV has in front, which `GET /api/devices/{device_id}/now` and `GET /api/remote/{device_id}` save to `tv_apps`.

## Consequences

- People using a DNS name or reverse proxy have to set `ALLOWED_HOSTS`. Setting it to `*` turns the host check off.
- Scripts calling the API must send the header too.
- `tests/test_guards.py` tries every changing route without the header, so a new route is covered automatically. CI also
  tries `POST /api/tune` against the built image.

## Alternatives

**Inferred:** CSRF tokens need a session to attach to, and there isn't one. Not on record as having been weighed.

## Where it lives

`guard` and `host_allowed` in `whatson/app.py`, `api()` in `whatson/static/js/core.js`, `tests/test_guards.py`.
