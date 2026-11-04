# 0008. Check typed addresses when saved and on every request

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

People type addresses into Settings, and WhatsOn then calls them with saved keys. Home servers live on private
addresses, so the usual rule of refusing private ranges would break the app. Cloud metadata endpoints, redirects and
names that later resolve somewhere else are still real risks.

## Decision

Two HTTP clients, for two kinds of destination:

- **`safe_http` clients** for anything typed in Settings. That's `state.lan_http`, plus the Plex client's own and the AI
  client's own, which use the same transport. `check_base_url` runs when an address is saved. `PinnedTransport` checks again
  on every request, connects to the exact IP it checked and keeps the name for TLS. Redirects aren't followed.
- **`state.http`** only for fixed public hosts: ESPN, Trakt and plex.tv.

The rules allow http and https only, and LAN and loopback addresses. They refuse link-local, multicast, unspecified,
reserved and known cloud metadata addresses, and IPv6 forms that wrap an IPv4 address. Every address a name resolves to
must pass.

TVs are stricter: pairing takes only a private IP address (`_lan_host` in `whatson/app.py`).

## Consequences

- A name that changes to a refused address after being saved stops working instead of leaking a key.
- Lookup results are cached for 60 seconds per name, so that's how long a change can take to be noticed.
- A new typed address must use `lan_http`. `tests/test_guards.py` has an allowlist of `state.http` uses and checks the LAN
  client doesn't follow redirects.
- A server that relies on redirects has to be entered by its final address.
- The leftover Seerr setting only checks the address's prefix. WhatsOn never calls it (ADR 0017).

## Alternatives

Refusing private addresses, as most server-side request filters do, isn't possible here: those are the addresses people
are meant to enter.

## Where it lives

`whatson/safe_http.py`, `whatson/state.py`, `_no_redirects` in `whatson/ai.py`, `tests/test_guards.py`.
