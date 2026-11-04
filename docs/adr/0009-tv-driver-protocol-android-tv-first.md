# 0009. A TV driver protocol, with Android TV's remote protocol first

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

WhatsOn has to control TVs from a server, and should support more kinds later. **Inferred:** asking people to turn on
developer mode or ADB on each TV would be a big hurdle.

## Decision

TV control sits behind the `TVDriver` protocol in `whatson/devices/base.py`: discovery, pairing, status, keys, typing and
opening links. Drivers register by kind in `state.drivers`.

The first driver uses the Android TV Remote protocol v2, the one the Google TV phone remote uses, through
`androidtvremote2`. Pairing is a one-time code shown on the TV, with no ADB or developer mode.

- One client certificate for the whole install, kept in the data folder. Each TV pairs with it once.
- Remote tab connections stay open for 120 seconds after the last key press, because a new one costs a TLS handshake of
  about a second, too slow for a d-pad.
- `enable_ime` is on because it's what makes the TV report its foreground app, which the busy check needs (ADR 0011).

## Consequences

- Only Google TV and Android TV work today. `PLANNED_KINDS` lists others as coming later.
- The container needs to reach TVs directly on ports 6466 and 6467, hence host networking (ADR 0023).
- The protocol can't list installed apps (ADR 0020) or start playback on its own terms (ADR 0010).
- `androidtvremote2` is pinned below 0.4, so moving to a newer version is a deliberate step.

## Alternatives

**ADB.** The driver and the README state that no ADB or developer mode is needed. Whether it was tried isn't on record.

## Where it lives

`whatson/devices/`, `state.drivers` in `whatson/app.py`, `tests/test_remote.py`, CONTRIBUTING's "A TV type".
