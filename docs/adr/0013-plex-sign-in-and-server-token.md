# 0013. Plex sign-in with JWTs, and the server token for the server

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

**Inferred:** digging a token out of Plex Web's XML view is a poor first step. WhatsOn never sees a Plex password. Plex offers a newer JWT sign-in, but Plex Media Server didn't accept those tokens when tested on 2026-10-31
(401/403).

## Decision

Offer three ways to connect, preferred in this order: **Sign in with Plex**, **a pasted token**, and **`PLEX_URL` and
`PLEX_TOKEN`** for headless setups, used only when nothing is saved.

Sign-in uses Plex's JWT flow. WhatsOn has its own Ed25519 key, the person approves a PIN on plex.tv, and plex.tv issues a
7-day JWT that WhatsOn renews with the key. Server calls use the server token from plex.tv's device list, fetched again
after each renewal. Renewal runs after 2 days, so failures have time to clear.

## Consequences

- No password ever reaches WhatsOn, and it appears under Plex's Authorized Devices.
- Two kinds of credential to keep in step, and a renewal loop to run.
- If Plex Media Server starts accepting JWTs, the server token step could go. That would be a new ADR.
- An owner's token can do everything on the server. WhatsOn only reads, but nothing on Plex's side limits it to that. The
  README says so.
- A pasted token always needs its address typed alongside it, in line with ADR 0007.

## Alternatives

Using the JWT directly against the server was tried and failed, as above. A token-only setup remains available for when
the sign-in pop-up can't work.

## Where it lives

`whatson/plex_auth.py`, `whatson/plex_routes.py`, `tests/test_plex_auth.py`.
