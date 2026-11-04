# whatson/: the app

Local rules for the server and front end. The top-level `AGENTS.md` comes first, including its rules on ADRs and docs.
`docs/architecture.md` and `docs/frontend.md` describe what's here.

**Server**

- A saved key follows `_key_for` in `whatson/remote_routes.py`: reused only for the address it was saved with.
- Addresses typed in Settings go through `check_base_url` when saved and `state.lan_http` when called. `state.http` is
  only for ESPN, Trakt and plex.tv.
- Media servers implement `whatson/sources/base.py`. Don't reach for Plex or Jellyfin directly in shared code.
- Anything that starts playback on a TV calls `tune.check_busy` first, unless the person already said to take over.
- Radarr and Sonarr calls stay in `whatson/arr.py`: looking up, adding and searching. Never `PUT` or `DELETE`.

**Front end** (`whatson/static/`)

- Plain JavaScript modules, no framework and no build step.
- Put `esc()` around anything from outside when building HTML. Call the server through `api()` in
  `whatson/static/js/core.js`.
- Colours come from the tokens in `whatson/static/style.css`. Icons are inline SVG, not emoji.
- Check screens at phone width and in light and dark mode. Say so if you couldn't.
- Nothing loads from a CDN, and the browser never calls an outside service directly.
