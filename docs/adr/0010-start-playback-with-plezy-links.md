# 0010. Start playback by sending Plezy an app link

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

The remote protocol can press keys and open app links, but has no "play this" command. Something on the TV has to accept
a link and play it. Per the README, the official Plex Android TV app stopped accepting remote play commands after its 2026
redesign. Plezy accepts links for Live TV and library titles, from Plex or Jellyfin.

## Decision

Everything WhatsOn starts on a TV goes through Plezy links, built in `whatson/tune.py`:

- Live TV: `plezy://live?channel=<number>&start=live&server=<server id>`
- Library: `plezy://play?server=<server id>&id=<item id>`
- Opening the app: `plezy://open`

`server` is included because Plezy otherwise pools the channels of every server it's signed in to. `start=live` skips
its "watch from the beginning?" prompt.

## Consequences

- **Plezy is a hard requirement for starting anything**, stated at the top of the README. Without it, WhatsOn can search
  and act as a remote.
- A link replaces whatever is playing, which is why the busy check exists (ADR 0011).
- A link can't report failure. For Jellyfin, where Plezy may not be signed in, the tune response carries `confirm` and the
  front end says so after about 25 seconds.
- Plezy quirks leak in. Its player ignores `MEDIA_STOP` and leaves on `BACK`, but `BACK` also walks its menus, so
  `_stop_key` in `whatson/routes.py` sends `BACK` only while the server reports something playing on that TV.
- WhatsOn depends on an outside app's link format, which it doesn't control.

## Alternatives

The official Plex app no longer works this way. Jellyfin apps are controlled from the Remote tab only, through the
Jellyfin server, and WhatsOn doesn't start titles in them.

## Where it lives

`whatson/tune.py`, `/api/tune` in `whatson/app.py`, the README's "Which apps can play".
