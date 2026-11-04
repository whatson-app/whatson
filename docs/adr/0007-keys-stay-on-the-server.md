# 0007. Keys stay on the server and only go to the address they were saved with

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

WhatsOn holds keys to Plex, Jellyfin, Radarr, Sonarr and AI providers, several of which give full control of those
services. With no login (ADR 0002), anyone on the network can open Settings, so Settings can't be allowed to reveal a key
or be tricked into sending one elsewhere.

## Decision

- **Keys never reach the browser.** Responses may say a key is saved and show a short hint, never the key.
- **Artwork goes through `/api/thumb`**, so the Plex token stays out of the page. Each source accepts only its exact
  artwork paths, so the proxy can't reach anything else on the server.
- **A saved key is reused only for the address it was saved with.** If the address changes, the key has to be typed
  again. Each saved key stores its address alongside it. A key from `.env` goes only to the address set beside it or, for
  AI, to the provider's own default address.
- **Keys are stored in plain text in the SQLite file**, set to mode 600. The README tells people to protect the data folder
  like a password file.

## Consequences

- Changing a server's address means typing its key again. That's deliberate.
- Every new saved key needs the same check and a test for it. `_key_for` in `whatson/remote_routes.py` is the model.
- Anyone with the data folder has every key.

## Alternatives

**Inferred:** encrypting keys at rest. The app would have to keep the decryption key beside them to start unattended, so
it would add little. Not on record as having been weighed.

## Where it lives

`whatson/remote_routes.py`, `whatson/arr.py`, `whatson/ai_settings.py`, `whatson/plex_auth.py`, `tests/test_guards.py`.
See also ADR 0008.
