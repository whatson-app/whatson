# API

The HTTP API exists for WhatsOn's own front end, and it isn't a stable public interface. While the app runs, FastAPI also
serves generated schemas at `/docs` and `/openapi.json`.

## Conventions

- **`X-WhatsOn: 1` is required** on everything but GET, HEAD and OPTIONS. Without it you get 403. See
  [ADR 0006](adr/0006-header-and-host-checks.md).
- **The `Host` must be known:** an IP address, `localhost`, or a name in `ALLOWED_HOSTS`.
- **There's no login.** See [ADR 0002](adr/0002-self-hosted-home-network-no-login.md).
- **No response contains a saved key.** Settings responses say whether one is saved, and may show a short hint.
- **Errors** come back as `{"detail": "text"}` or `{"detail": {"code": "...", "message": "..."}}`. `message` is written for
  people, and `code` is what the front end acts on.

| Code | Status | Meaning |
|---|---|---|
| `busy` | 409 | Something is on that TV. Ask, then send again with `force` |
| `not_paired` | 409 | The TV no longer accepts this install. Pair again |
| `unreachable` | 502 or 409 | Couldn't reach the TV |
| `wrong_code`, `cancelled`, `expired`, `failed` | 409 | Pairing didn't finish. `restarted` means a new code is showing |
| `bad_format` | 400 | A pairing code must be 6 characters, 0-9 and A-F |
| `plex_not_connected` | 503 | No Plex server is set up |
| `jellyfin_error` | 502 | The Jellyfin server failed or refused |

## App

| Route | What it does |
|---|---|
| `GET /` | The page |
| `GET /health` | Answers `{"ok": true}` |
| `GET /api/status` | Version, counts, whether AI and a server are on, and last refresh times |
| `GET /api/thumb` | Artwork from the current server, with the token kept on the server |

## Search and suggestions

| Route | What it does |
|---|---|
| `GET /api/search` | Search. `q`, `scope`, `ai`, `on_now`, `kind`, or `filters` to replay edited chips. `device` shows watched status for that TV's Plex user |
| `GET /api/answer` | One line answering `q` from the matches only. Empty when AI is off |
| `GET /api/suggest/live` | Your shows on tonight, and picks for Live TV |
| `GET /api/suggest/library` | Up next, picks, and watchlist titles you don't have. `device` reads as that TV's Plex user |

## Live TV

| Route | What it does |
|---|---|
| `GET /api/guide` | The guide grid |
| `GET /api/airing/{airing_id}` | One listing's details |
| `POST /api/favorites/channels/{channel_id}` | Add a favorite channel |
| `DELETE /api/favorites/channels/{channel_id}` | Remove a favorite channel |

## Library

| Route | What it does |
|---|---|
| `GET /api/library` | Poster grid, with sort, genre and unwatched options. `device` shows watched status for that TV's Plex user |
| `GET /api/library/genres` | Genres in the library |
| `GET /api/library/item/{rating_key}` | A movie or show, with seasons. `device` reads as that TV's Plex user, and `hidden_from` names them if Plex hides the title from them |
| `GET /api/library/season/{rating_key}` | A season's episodes. `device` reads as that TV's Plex user |

## Sports

| Route | What it does |
|---|---|
| `GET /api/sports` | Games on the board now |
| `GET /api/sports/leagues` | Leagues that can be followed |
| `GET /api/sports/teams` | Teams in a league |
| `GET /api/sports/foryou` | Followed teams and leagues, with scores and close games |
| `GET /api/sports/league` | One league's page |
| `GET /api/sports/recap` | "Catch me up" on a game |
| `GET /api/follows` | What's followed |
| `POST /api/follows` | Follow a league or team |
| `DELETE /api/follows` | Stop following |

## TVs and tuning

| Route | What it does |
|---|---|
| `GET /api/tv-types` | TV kinds, working and planned |
| `GET /api/discover` | TVs announcing themselves on the network |
| `POST /api/pair/start` | Start pairing. The TV shows a code |
| `POST /api/pair/finish` | Finish pairing with the code |
| `GET /api/devices` | Saved TVs |
| `PATCH /api/devices/{device_id}` | Rename a TV |
| `DELETE /api/devices/{device_id}` | Remove a TV |
| `POST /api/devices/{device_id}/test` | Open Plezy and confirm it came to the front. Checks whether the TV is busy first |
| `GET /api/devices/{device_id}/status` | Whether the TV is reachable, on and busy |
| `GET /api/devices/{device_id}/now` | What the TV is showing. Cached for 8 seconds |
| `POST /api/devices/{device_id}/key` | Now-playing bar's play/pause, stop, back and home |
| `PUT /api/devices/{device_id}/jellyfin` | Link a TV to the Plezy device Jellyfin reports |
| `PUT /api/devices/{device_id}/plex-user` | Choose which Plex Home user watches on a TV, or nobody |
| `POST /api/tune` | Tune a channel or play a title. Checks whether the TV is busy unless `force` is set |

## Remote tab

| Route | What it does |
|---|---|
| `GET /api/remote/{device_id}` | Live status, volume, the app list and controllable Jellyfin apps |
| `POST /api/remote/{device_id}/key` | Press a key. Short press or long hold |
| `POST /api/remote/{device_id}/text` | Type into the field in focus on the TV |
| `POST /api/remote/{device_id}/launch` | Open an app, and report whether it came to the front |
| `PUT /api/remote/{device_id}/apps` | Show or hide an app on this TV's row |
| `POST /api/remote/{device_id}/control` | Pause, seek or skip a Jellyfin app through the server |

## Getting titles (Radarr and Sonarr)

| Route | What it does |
|---|---|
| `GET /api/get/lookup` | Titles matching a search |
| `GET /api/get/item` | One title, with options for the Add sheet |
| `POST /api/get/add` | Add a title. Refused when adding is off |
| `POST /api/get/search` | Start a search for a title. Refused when adding is off |
| `GET /api/get/downloads` | The download queue, plus titles added here in the last 30 days |

## Settings

| Route | What it does |
|---|---|
| `GET /api/settings/source` | Which server is in use |
| `PUT /api/settings/source` | Switch server. Clears the old server's data |
| `GET /api/settings/plex` | Plex connection |
| `DELETE /api/settings/plex` | Forget the Plex connection |
| `POST /api/settings/plex/signin` | Start Sign in with Plex |
| `GET /api/settings/plex/signin/{pin_id}` | Check on a sign-in |
| `POST /api/settings/plex/server` | Choose a server after signing in |
| `PUT /api/settings/plex/manual` | Use an address and a pasted token |
| `GET /api/settings/plex/users` | Plex Home users to choose from. Empty while Plex isn't the server in use |
| `GET /api/settings/jellyfin` | Jellyfin connection |
| `PUT /api/settings/jellyfin` | Connect to Jellyfin |
| `DELETE /api/settings/jellyfin` | Forget the Jellyfin connection |
| `GET /api/settings/jellyfin/users` | Users to choose from |
| `PUT /api/settings/jellyfin/user` | Choose whose watched status and up next to show |
| `GET /api/settings/jellyfin/devices` | Devices for linking TVs |
| `GET /api/settings/ai` | AI settings |
| `PUT /api/settings/ai` | Save AI settings |
| `POST /api/settings/ai/test` | Try a question against the saved AI settings |
| `POST /api/settings/ai/models` | Models for the dropdown |
| `GET /api/settings/downloads` | Radarr and Sonarr settings |
| `PUT /api/settings/downloads` | Turn adding on or off |
| `PUT /api/settings/downloads/{kind}` | Save settings for `movie` (Radarr) or `show` (Sonarr) |
| `POST /api/settings/downloads/{kind}/test` | Try the connection and read its options |

## No interface yet

These routes work, but nothing in the front end calls them. See [ADR 0018](adr/0018-trakt-stays-out-of-the-interface.md) and
[ADR 0017](adr/0017-radarr-sonarr-add-and-search-only.md).

| Route | What it does |
|---|---|
| `GET /api/trakt` | Trakt connection |
| `PUT /api/trakt/app` | Save a Trakt app's client id and secret |
| `POST /api/trakt/connect` | Start device-code sign-in |
| `POST /api/trakt/poll` | Check on a sign-in |
| `POST /api/trakt/disconnect` | Forget the Trakt connection |
| `POST /api/trakt/sync` | Sync now |
| `PUT /api/settings/seerr` | Leftover: saves an address that WhatsOn never calls |
