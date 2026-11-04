# Integrations

What WhatsOn uses from each outside system, what could break, and where the code is. A new outside service needs an agreed
issue and an ADR. `tests/test_guards.py` keeps a list of allowed hosts.

| System | Needed? | Used for | Code |
|---|---|---|---|
| Plex Media Server | One server is | Guide, library, sessions, artwork | `whatson/sources/plex.py` |
| plex.tv | For Sign in with Plex | Sign-in and the server token | `whatson/plex_auth.py` |
| Jellyfin | One server is | Guide, library, sessions, artwork, app control | `whatson/sources/jellyfin.py` |
| Android TV Remote v2 | For TVs | Pairing, status, keys, typing, opening links | `whatson/devices/androidtv.py` |
| Plezy | To start anything on a TV | Plays links from WhatsOn | `whatson/tune.py` |
| ESPN | No | Teams, games, scores | `whatson/sources/espn.py` |
| Radarr and Sonarr | No | Getting titles | `whatson/arr.py` |
| AI providers | No | Reading questions, answers, ranking, recaps | `whatson/ai.py` |
| Trakt | No, and has no interface | Taste signals for suggestions | `whatson/trakt.py` |

## Plex

Reads the guide from Plex's own EPG provider, so it works whatever feeds Plex's Live TV. Plex's guide has no ratings or
genres, so "kids" and "family" go by channel name on live TV. Its Live TV sessions don't say which channel they're on, so
now-playing uses the last channel WhatsOn tuned on that TV, checked against the title.

An owner's token can do everything on the server. WhatsOn only reads, and nothing on Plex's side limits it to that. See
[ADR 0013](adr/0013-plex-sign-in-and-server-token.md) for sign-in.

## Jellyfin

Uses the Sessions API, so it sees official and third-party apps. Remote control works for apps that report
`SupportsRemoteControl`. Watched status and up next belong to one chosen user. A server behind a proxy can't see a TV's
address, so a TV can be linked to its Plezy device in ⚙ → TVs.

An API key has full access to the server. WhatsOn reads, apart from the Remote tab's playback commands. Tested on Jellyfin
12.4.

## TVs

The Android TV Remote protocol needs no ADB or developer mode. See
[ADR 0009](adr/0009-tv-driver-protocol-android-tv-first.md). TVs are found by mDNS on `_androidtvremote2._tcp.local.`, or
added by address.

The protocol can't list installed apps, or tell whether a link started playing. Google TV refuses to open apps by package
name since an August 2026 Play Store update.

## Plezy

Link formats are in [ADR 0010](adr/0010-start-playback-with-plezy-links.md). Plezy has to be signed in to the same server,
and WhatsOn can't do that for it.

Plezy's video player ignores `MEDIA_STOP` and leaves on `BACK`. See `_stop_key` in `whatson/routes.py`. It can't rewind Live
TV from Jellyfin.

## ESPN

The scoreboard feed is **unofficial and undocumented**, and may change without notice. If it fails, the guide and library
keep working, and the last good games stay. College leagues need a `GROUPS` entry, or they list only ranked and featured games.
See [ADR 0014](adr/0014-match-espn-games-to-listings.md).

## Radarr and Sonarr

Only GET, plus POST to add a title or run `MoviesSearch` or `SeriesSearch`. Never edits or deletes. See
[ADR 0017](adr/0017-radarr-sonarr-add-and-search-only.md).

## AI providers

Claude through the Anthropic SDK, and OpenAI, OpenRouter and OpenAI-compatible servers through the OpenAI SDK. What's sent:
the question, the local time, the matches or candidates being considered, a game's facts for a recap, and taste signals from
Trakt if it's connected. See
[ADR 0016](adr/0016-ai-is-optional-and-never-invents.md).

## Trakt

Each self-hoster would register their own free Trakt API app, because a shared secret can't ship in open source. Out of the
interface for now. See [ADR 0018](adr/0018-trakt-stays-out-of-the-interface.md).

## Links only

`whatson/apps.py` holds links for streaming apps such as YouTube and Netflix. They're sent to a TV to open that app, and WhatsOn
never calls them itself.
