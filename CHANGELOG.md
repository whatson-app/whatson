# Changelog

What changed in each version of WhatsOn, newest first.

## Unreleased

## 0.2.7 - 2026-11-10

### Changed
- **Search shows what you typed, then what the AI made of it.** With AI on, matches for your words exactly as typed now
  come first, under "Matches for", and the AI's reading follows under "More from the AI's reading". Before, only the AI's
  reading was searched, so a search for an episode like "Duck Duck Loon" could turn into a search for an Oregon Ducks game
  and never show the episode.

## 0.2.6 - 2026-11-08

### Fixed
- **The now-playing card's remote no longer stalls the TV picture.** The first press after two quiet minutes had to
  open a new connection to the TV, which could freeze live video in Plezy for a moment. The card now opens that
  connection as soon as it appears and keeps it open while it's showing, as the Remote tab does.

## 0.2.5 - 2026-11-08

### Added
- **Tap the now-playing bar for a card about what's on.** For a game: the live score, "Catch me up", the latest plays
  and a link to the game on ESPN, credited to ESPN. For other live TV: the listing's time, channel and description. For
  a movie or episode: poster, time left and a link to its page.
- **A small remote on that card:** back 10 seconds, play/pause, back to live (live TV), volume down, mute and up, and a
  link to the full remote.

### Changed
- Live TV no longer has a separate "Your shows on tonight" row. With Trakt connected, those shows are still among the
  candidates for "On now, picked for you".
- **Settings has more room.** Each TV is its own box with its buttons on one line; your Trakt account and last sync
  stack instead of squeezing side by side; followed teams are one per row with the league on the right; the Downloads
  test result sits under its button; opened sections get a divider; and on phones the dialog uses more of the screen.

### Fixed
- A game on ESPN no longer also shows on ESPN 2, ESPNU, ESPNews or ESPN8 The Ocho, and a game on FOX no longer shows on
  FOX Weather, LiveNOW from FOX or Fox Soccer Plus.
- Games ESPN lists on "NFL Net" or "NHL Net" now match NFL Network and NHL Network channels.
- Tapping the now-playing bar during a movie or episode no longer starts it again on the TV.
- A game in "On now, picked for you" is named for the game ("Comets at Otters"), not the channel's placeholder listing,
  on the card and in what the AI ranks.
- **A held Remote key can't get stuck repeating.** If the Remote screen refreshed while a key was held, the key kept
  repeating after you let go, until the page was closed. Volume Down could run for minutes and turn a soundbar all the
  way down. A refresh, switching tabs or leaving the window now ends the hold, and a hold stops after about 8 seconds.

## 0.2.4 - 2026-11-08

### Fixed
- **Movies and Shows views work on bare guides.** Plex calls every listing from an XMLTV guide a movie, so news, reality
  shows and cartoons all showed under Movies and Shows was empty. Listings are now sorted from the guide itself: a title
  with different descriptions, or on at the same time on another day, or under 80 minutes is a show; placeholders,
  "Live" titles and news or shopping channels are neither. ADR 0028.
- **A game on a channel with no guide data shows on that channel.** A placeholder block (just the channel's name) on the
  game's network now links to the game, so it appears there, under Sports and in "On now, picked for you". A replay that
  names both teams but starts well after kickoff no longer counts as the game.
- "NBC News Now", "FOX News" and similar channels no longer count as carrying a game on that broadcast network.

## 0.2.3 - 2026-11-08

### Added
- **Trakt is back**, in ⚙ → More → Trakt: connect with your own free Trakt app for "Your shows on tonight", "Up next"
  from Trakt, a row of watchlist titles you don't own (with "Get it" when Radarr or Sonarr is connected) and suggestions
  that use your ratings and viewing. ADR 0027 replaces ADR 0018. Register the Trakt app with the redirect URI
  `http://localhost`. New Trakt apps have no client secret, so sign-in uses PKCE; older apps with a secret and
  `urn:ietf:wg:oauth:2.0:oob` keep working.
- **How AI works** in the README: what each AI feature is sent, what's checked and what isn't.

### Fixed
- "On now, picked for you" shows each game once, on the channel airing it now, and leaves out games that are already over
  and later replays. A sports listing for another sport, such as soccer on Fox Soccer Plus, is no longer matched to a
  game on Fox.
- Suggestion rows only show the AI badge when AI really ranked them, not whenever AI is set up. Sports picks now tell
  the AI which followed team is playing, as its prompt said they would.

## 0.2.2 - 2026-11-03

### Added
- **A Plex Home user for each TV:** choose who watches on each TV in ⚙ → TVs. Picking that TV shows their Up Next and
  watched status, and anything you start plays as them in Plezy.
- **Documentation** in `docs/`: architecture, API, data model, configuration, integrations, front end and testing, plus
  decision records (ADRs) for WhatsOn's design. Contributors now write and review ADRs as part of their changes.

### Fixed
- Game cards show the league's name, such as "College football", not `COLLEGE-FOOTBALL`.

### Removed
- The unused Seerr address setting: `PUT /api/settings/seerr`, and `seerr_url` in `GET /api/trakt` and
  `GET /api/suggest/library`. The Settings screen never offered it, and WhatsOn never called that address.

## 0.2.1 - 2026-11-03

### Changed
- **Settings has four tabs:** Server (Plex and Jellyfin together), TVs, Sports and More (AI search, Downloads,
  Appearance).

### Added
- **Search shows that it's working,** with a spinning circle and a line saying what it's waiting for.
- **AI shows that it's working,** with a placeholder where its answer, picks or game recap will appear.
- The bottom of Settings shows the version you're running, with a link to WhatsOn on GitHub.

### Changed
- The sample question in Settings → AI search now asks about a different team.

### Fixed
- The theme picker's section no longer has a stray sideways scrollbar.

## 0.2.0 - 2026-11-03

### Added
- **Jellyfin as a source:** the guide and library can come from a Jellyfin server instead of Plex. Choose in
  Settings → Source. WhatsOn uses one server at a time.
- **Theme picker** in Settings, and a new app icon.
- **Unraid Docker template,** so WhatsOn shows as an ordinary Unraid app. See the README.

### Fixed
- **The Stop button** on the now-playing bar now stops Plezy.

## 0.1.1 - 2026-11-03

### Added
- Images for arm64 as well as amd64, so a 64-bit Raspberry Pi works.

## 0.1.0 - 2026-11-03

First published image.
