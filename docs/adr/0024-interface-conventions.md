# 0024. Interface conventions: tokens, both themes, phone width, plain words

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

**Inferred:** people often use WhatsOn from a phone, in a dark room, and aren't always the person who set it up. With no
framework (ADR 0004), consistency has to come from conventions.

## Decision

- **Colours come from the tokens** in `whatson/static/style.css`. Each theme redefines the same tokens. A theme picker
  forces light or dark, and otherwise it follows the device.
- **Every screen works at phone width and in both modes.** Live TV's guide grid becomes a now/next list on a phone.
- **Icons are inline SVG,** not emoji.
- **Words are plain and short.** "Couldn't reach the TV", not "Connection error 502". Errors say what to do next.
- **Show that things are working.** Search shows a spinner and what it's waiting for, and AI gets a placeholder where its
  answer will appear.

## Consequences

- A theme is one set of token values.
- Each screen change has to be checked in four combinations, by a person, since there are no browser tests. The pull
  request template asks.
- `tests/test_guards.py` caps hard-coded colours in scripts and pages. The allowed few are the browser's theme-color, which
  can't read a token. App badge colours in `whatson/apps.py` are data, outside this rule.

## Alternatives

None on record.

## Where it lives

`whatson/static/style.css`, `whatson/static/js/core.js`, `AGENTS.md`, [frontend.md](../frontend.md).
