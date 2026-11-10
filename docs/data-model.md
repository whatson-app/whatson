# Data model

Everything is in one SQLite file, `whatson.db`, in the data folder, in WAL mode. The schema is `SCHEMA` in `whatson/db.py`.
For why it works this way, see [ADR 0005](adr/0005-local-sqlite-copy-rebuilt-on-refresh.md).

The database holds saved keys, so its files are set to mode 600. Protect the data folder like a password file.

## Rebuilt on each refresh

Safe to lose: the next refresh fills them again. Switching server clears all of these except `games`.

| Table | What it holds |
|---|---|
| `channels` | Channels from the server. `id` is the server's, and `vcn` is the number shown to people and used to tune |
| `airings` | Listings. `kind` is movie, episode, sports or other, and `game_id` is set when linked to a game |
| `airings_fts` | Search index over airings. `extra` holds the linked game's team names, which is how a team finds its channel |
| `library` | Movies and shows. `rating_key` is the server's item id, whichever server that is |
| `library_fts` | Search index over the library |
| `episodes` | Every library episode's title, season and number. `show_key` is its show's `rating_key` ([ADR 0030](adr/0030-search-episode-titles.md)) |
| `episodes_fts` | Search index over episode titles |
| `games` | Games from ESPN, with teams, scores and networks. `state` is pre, in or post |
| `user_watched` | Watched status for Plex Home users other than the owner, refreshed as often as the library |

## Long-lived

These hold what people set up. A new column needs an `ALTER TABLE` in `connect()`, or existing installs break.

| Table | What it holds |
|---|---|
| `devices` | Paired TVs: name, kind, address, how to recognise them in a server's sessions, and which Plex Home user watches there |
| `fav_channels` | Favorite channels. Cleared when switching server, because the ids differ |
| `follows` | Followed leagues and teams, shared by the household |
| `arr_adds` | Titles added to Radarr or Sonarr from WhatsOn, for the Downloads view |
| `tv_apps` | Apps seen on, or ticked for, each TV |
| `plex_user_tokens` | Each chosen Plex Home user's server token, and the only address it goes to. Secret. Cleared when Plex is disconnected |
| `meta` | Settings and saved keys, as key-value text |

## Changing columns

- **`library` or `games`:** add the column to `SCHEMA`, and name it in `want` in `connect()`. On an existing install, the
  missing column makes the table drop and rebuild.
- **`channels` or `airings`:** these aren't in `want` yet, so `CREATE TABLE IF NOT EXISTS` would leave an existing table as it
  is. Add an entry to `want` and to `REBUILT`, and for `airings` include `airings_fts` with it.
- **Long-lived tables:** add it to `SCHEMA` and to the `ALTER TABLE` list in `connect()`.

## Saved settings in `meta`

`{...}` stands for part of the key. **Secret** means it's never sent to the browser.

| Key | What it holds | Secret |
|---|---|---|
| `source` | `plex` or `jellyfin` | |
| `machine_id` | The current server's id, used in Plezy links | |
| `guide_refreshed` | Time of the last guide refresh | |
| `library_refreshed` | Time of the last library refresh | |
| `plex.source` | `signin` or `token` | |
| `plex.url` | Server address | |
| `plex.server_id` | Server id | |
| `plex.server_name` | Server name | |
| `plex.server_token` | Token used to call the server | Yes |
| `plex.account` | Account name from sign-in | |
| `plex.client_id` | This install's id on plex.tv | |
| `plex.key` | This install's Ed25519 private key | Yes |
| `plex.kid` | The id plex.tv knows that key by | |
| `plex.jwt` | Sign-in token from plex.tv | Yes |
| `plex.jwt_at` | When that token was last renewed | |
| `plex.owner_uuid` | Which Plex Home user is the owner | |
| `jellyfin.url` | Server address, and the only address `jellyfin.key` goes to | |
| `jellyfin.key` | API key | Yes |
| `jellyfin.name` | Server name | |
| `jellyfin.server_id` | Server id | |
| `jellyfin.user_id` | Whose watched status and up next to show | |
| `jellyfin.user_name` | That user's name | |
| `arr.allow_add` | Whether adding titles is on | |
| `arr.{kind}` | Settings for `movie` (Radarr) or `show` (Sonarr), as JSON | |
| `arr.{kind}.key` | API key | Yes |
| `arr.{kind}.key_base` | The only address that key goes to | |
| `ai.provider` | AI provider, or `none` | |
| `ai.model` | Model name | |
| `ai.base_url` | Address of an OpenAI-compatible server | |
| `ai.key.{provider}` | API key | Yes |
| `ai.key_base.{provider}` | The only address that key goes to | |
| `trakt.{name}` | Trakt app, tokens and cached data. The client secret and tokens are secret | Partly |
| `seerr_url` | Only on older installs. Nothing reads or writes it now | |

## Other files in the data folder

`androidtv/cert.pem` and `androidtv/key.pem` are the client certificate every TV pairs with. Losing them means pairing every
TV again.

## Memory only

Lost on restart, and the reason WhatsOn must run as one process
([ADR 0003](adr/0003-single-fastapi-process.md)): the route cache in `whatson/routes.py`, `state.last_tune`, Plex sign-ins in
progress, Trakt's pending device sign-in, the AI ranking cache, TV pairing attempts and held TV connections.
