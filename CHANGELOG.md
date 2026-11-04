# Changelog

What changed in each version of WhatsOn, newest first.

## Unreleased

### Added
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
