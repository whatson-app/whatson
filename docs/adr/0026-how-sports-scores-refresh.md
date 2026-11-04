# 0026. Sports scores refresh by polling, on two timers

- **Status:** Proposed
- **Date:** 2026-11-03

## Context

This records how WhatsOn already works, so accepting it changes no code.

Scores come from ESPN's public scoreboard feed, which is unofficial and undocumented (ADR 0014). Someone with the Sports
page open should see scores change without reloading, but the browser must never call an outside service directly.

## Decision

The server polls ESPN and saves scores in its database, and the browser polls the server. Nothing pushes to the browser.

| Who | What | How often | Where |
|---|---|---|---|
| Browser | Sports page (For you and league pages) re-reads the server | Every 20 s | `whatson/static/js/sports.js` |
| Browser | Now playing bar re-reads the TV's state, including its score | Every 10 s while the page is visible | `whatson/static/js/player.js` |
| Server | Fetches from ESPN while a followed team or league is live | Every 30 s | `run_forever` in `whatson/ingest.py` |
| Server | Fetches from ESPN the rest of the time | Every 5 min (`SPORTS_REFRESH_MINUTES`) | `run_forever` in `whatson/ingest.py` |
| Server | A followed team's last and next game | Cached for 10 min | `sports_for_you` in `whatson/routes.py` |

The server loop wakes every 15 seconds, so the 30-second fetch really happens every 30 to 45 seconds.

Airings keep a `game_id` and join to the `games` table, so search and the guide show scores as fresh as the table when
they load, with no guide refresh needed.

**Inferred:** polling needs no new connection type or dependency, and ESPN's load doesn't grow with the number of open
browsers.

## Consequences

How fresh a score is depends mostly on the server's timer, not the page's:

- **A followed game that's live** shows a new score up to about 65 seconds after ESPN has it.
- **Any other live game** can be about 5 minutes behind, even though the page re-reads every 20 seconds. That includes
  "Worth switching to" and the folded games, unless a followed game happens to be live at the same time.
- **A followed game that has just started** can also take up to 5 minutes to speed up, because the 30-second rate starts
  only once the saved game shows as live.
- **Search results and the guide** don't re-read on their own. They're current as of when they loaded.

Known limits in the page's polling:

- **One failed re-read stops the updates** until the page is reopened. In `sports.js` the next timer is only set after a
  re-read succeeds, so a brief network or server error ends the cycle with no message.
- **The Sports page keeps polling in a hidden tab,** unlike the Now playing bar.

## Alternatives

**Inferred,** as none are on record:

- **Push with WebSockets or server-sent events:** it would save at most the page's 20 seconds, because ESPN still has to be
  polled.
- **The browser calling ESPN directly:** not allowed.
- **Always fetching every 30 seconds:** more calls to an unofficial feed for games nobody has said they care about.

## Where it lives

`whatson/ingest.py`, `whatson/routes.py`, `whatson/sources/espn.py`, `whatson/static/js/sports.js`,
`whatson/static/js/player.js`, `SPORTS_REFRESH_MINUTES` in `whatson/config.py`. Related: ADR 0004, ADR 0005, ADR 0014.
