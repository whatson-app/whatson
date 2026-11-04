# 0011. Ask before interrupting a TV

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

A link replaces whatever is playing (ADR 0010), and the person tapping Play on a phone may be in a different room from
the person watching.

## Decision

Before starting anything, `tune.check_busy` looks at two things:

1. Whether the media server reports something playing or buffering on this TV.
2. Whether the TV has an app in front that isn't a home screen, a screensaver or Plezy (`IDLE_APPS`).

If so, the API answers 409 with code `busy` and a plain sentence saying what's on, and the front end asks. The request
is sent again with `force` only after the person agrees.

A TV that can't be reached doesn't count as busy.

## Consequences

- Takes a moment longer than sending the link straight away.
- It only sees the server in use, so Plezy playing from the other server isn't noticed. The README says so.
- Plezy in front with nothing reported by the server counts as free, so Plezy's own menus don't trigger a prompt.
- The Remote tab's app row is exempt, because a person pressed a button for that app on that TV. `tests/test_guards.py`
  fails any other caller of `open_link` that doesn't call `check_busy`.

## Alternatives

None on record. `AGENTS.md` lists this among the rules that can't be broken.

## Where it lives

`check_busy` in `whatson/tune.py`, `whatson/app.py`, `whatson/static/js/player.js`, `tests/test_guards.py`.
