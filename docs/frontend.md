# Front end

Plain JavaScript modules in `whatson/static/`, with no framework and no build step. Reload the page to see a change. See
[ADR 0004](adr/0004-plain-javascript-no-build-step.md) and [ADR 0024](adr/0024-interface-conventions.md).

## Files

| File | What it does |
|---|---|
| `whatson/static/index.html` | The page shell. Applies the saved theme before first paint |
| `whatson/static/style.css` | All styles, and the colour tokens for each theme |
| `whatson/static/signed-in.html` | The page Plex's sign-in returns to |
| `whatson/static/icon-512.png` | App icon |
| `whatson/static/js/main.js` | Router, the search bar, and global click wiring |
| `whatson/static/js/core.js` | Shared helpers: `$`, `esc()`, `api()`, `store`, toasts, dialogs, formatting, placeholders |
| `whatson/static/js/cards.js` | Card renderers shared by the sections |
| `whatson/static/js/search.js` | The search box, filter chips and AI answer |
| `whatson/static/js/results.js` | The search results page |
| `whatson/static/js/player.js` | The TV picker, tuning, the now-playing bar, and the card it opens (listing, or a game's score and ESPN plays) |
| `whatson/static/js/live.js` | Live TV: suggestion rows, guide grid or now/next list, favorites |
| `whatson/static/js/library.js` | Library: poster grids, show pages, up next |
| `whatson/static/js/sports.js` | Sports: followed teams, close games, league pages, recaps |
| `whatson/static/js/remote.js` | Remote tab |
| `whatson/static/js/get.js` | Getting titles: the Get it row, Add sheet, Downloads view and settings |
| `whatson/static/js/settings.js` | Settings: Server, TVs (with the pairing wizard), Sports, More |

## Routes

Hash routes, handled in `main.js`. The last section used is remembered.

| Route | Screen |
|---|---|
| `#/live[/view]` | Live TV |
| `#/library[/movie, /show or /downloads]` | Library |
| `#/library/show/<id>` | A show's page |
| `#/sports[/league]` | Sports |
| `#/remote` | Remote |
| `#/search` | Search results |

## Clicks

Cards carry `data-*` attributes, and `main.js` handles the clicks in one place: `data-channel` tunes a channel,
`data-rating-key` plays from the library, `data-recap` opens a recap, `data-airing` opens listing details, `data-show` opens a
show page, `data-movie` opens movie details, and `data-get` opens the Add sheet.

## Rules

- **`esc()`** around anything from outside when building HTML. Guide data and titles aren't trusted.
- **`api()`** for every server call. It sends `X-WhatsOn` and turns errors into thrown `Error`s with `status`, `code` and `data`.
- **Colours from tokens** in `style.css`. Icons are inline SVG, not emoji.
- **Check every screen** at phone width and in light and dark mode. There are no browser tests.
- **Nothing from the web:** no CDNs, and no outside calls from the browser. Some images are a known gap: see
  [ADR 0004](adr/0004-plain-javascript-no-build-step.md).
- **Plain, short words,** and errors that say what to do next.
- **Show waiting.** `working()` for a spinner and a line, `aiPlaceholder()` where AI's output will appear. Only claim AI is
  working when `ai.on` is set.

## Themes

`:root` holds the light tokens. A `prefers-color-scheme: dark` block redefines them unless `data-theme="light"` is set, and
`:root[data-theme="dark"]` redefines them when dark is forced. `applyTheme` in `core.js` sets the attribute and the browser's
theme colour.

## Browser storage

`store` wraps `localStorage` and copes with private mode. It only holds conveniences for one device: `theme`, `section`, `tv` and
library sort settings. Everything shared lives on the server.
