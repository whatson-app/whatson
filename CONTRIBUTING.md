# Contributing

Issues and pull requests are welcome. Roku, Fire TV and other TV drivers are the most useful addition,
since only Google TV / Android TV works today.

## Before you start

- **Small fixes:** go ahead and open a pull request.
- **Anything bigger:** open an issue first, so nobody spends time on something that won't be merged.
- **Security problems:** see [SECURITY.md](SECURITY.md), and please don't open a public issue.
- **Not planned:** a login and a Seerr add mode. Trakt is out of the interface for now.

## Using AI

AI-assisted contributions are welcome, on these terms:

- **You're responsible for what you submit.** Read the whole diff and be able to explain it. If you can't
  answer questions about it, it isn't ready.
- **Say that AI was used,** in the pull request template.
- **Test it yourself.** Run `scripts/check.py`, and report what you actually ran, including what you didn't test.
- **Keep it to the issue.** Assistants like to tidy up along the way. Revert anything the issue didn't ask for.
- **No invented behaviour.** If the assistant "knows" how a TV, app or server responds and you can't find it in the
  code or its docs, try it or leave it out.
- **No real data in the prompt that ends up in the repo.** Assistants copy what you show them. Give them made-up
  names and addresses, not your home's.

Pull requests that look unreviewed may be closed without detailed feedback. That includes text that
doesn't match the diff, or claims of testing that didn't happen.

If you use a coding agent, point it at [AGENTS.md](AGENTS.md), which has the full rules. Many tools read it
automatically. Claude Code reads it through `CLAUDE.md`, and `whatson/` and `tests/` each have their own short pair.
Those rules, especially the security ones, apply to people too.

## Set up

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev,anthropic,openai]"
DATA_DIR=./data .venv/bin/uvicorn whatson.app:app --reload --port 8430
```

Open `http://localhost:8430`, then connect a server in ⚙ → Source. The front end is plain JavaScript modules
with no build step, so reloading the page picks up changes.

## Checks

Run this before you open a pull request. CI runs the same command:

```bash
.venv/bin/python scripts/check.py            # tests, guard tests, privacy check, JS syntax
.venv/bin/python scripts/check.py --quick    # the same without the full test suite, while you work
```

`tests/test_guards.py` turns the rules in [AGENTS.md](AGENTS.md) into tests. If one fails, the message names the
rule. Don't change the guard test to get past it; if you think a rule should change, open an issue.

Put your own private values in `.private-denylist`, one per line: your server's address, your TV and room names, your
Plex server id. The file is git-ignored, and `scripts/check_public.py` will then refuse them too. CI also scans the
whole history for secrets with gitleaks.

## Where things are

| Path | What it does |
|---|---|
| `whatson/app.py` | Start-up, request checks, TV pairing and search routes |
| `whatson/routes.py` | Most of the API: guide, library, sports, suggestions |
| `whatson/remote_routes.py`, `arr_routes.py`, `plex_routes.py`, `source_routes.py` | Remote tab and Jellyfin, Radarr/Sonarr, Plex sign-in, choosing the server |
| `whatson/search.py`, `ai.py`, `suggest.py` | Search filters and queries, AI reading of questions, suggestion rows |
| `whatson/ingest.py`, `db.py` | Background refresh, SQLite storage |
| `whatson/sources/` | Plex, ESPN and Jellyfin clients; `base.py` is what a media server has to provide |
| `whatson/devices/` | TV drivers |
| `whatson/apps.py` | Apps the Remote tab knows about |
| `whatson/safe_http.py` | The rules for addresses people type in Settings |
| `whatson/static/` | Front end: `index.html`, `style.css`, one module per section in `js/` |

## Common additions

### A TV type

1. Implement the `TVDriver` protocol in `whatson/devices/base.py`. `whatson/devices/androidtv.py` is the
   working example. That covers discovery, pairing, status, keys, typing and opening links.
2. Register it in `state.drivers` in `whatson/app.py`. `PLANNED_KINDS` there lists types shown as coming later.
3. Add tests with a fake TV connection, and say which real TVs you tried it on.

Keep the check for something already playing. Before taking over a TV, WhatsOn asks first.

### An app on the Remote tab

Add an `App` to `CATALOG` in `whatson/apps.py`, with its package name and, if it has one, a link that opens
it. Try the link on a real TV: Google TV refuses to open apps by package name alone. Parts of the TV itself,
like its Settings app, go in `SYSTEM` so they stay off the app row.

### A sports league

Add its ESPN path to `DEFAULT_LEAGUES` in `whatson/config.py` and its name to `LEAGUE_LABELS` in
`whatson/sources/espn.py`. A college league also needs a `GROUPS` entry and a place in `COLLEGE_LEAGUES`.

### A setting that saves a key

Follow the Jellyfin code in `whatson/remote_routes.py`. Check the address with `_check_url`, call it through
`state.lan_http`, never return the key, and only reuse a saved key for the address it was saved with. Add a
test for that last rule.

### A database column

Add it to `SCHEMA` in `whatson/db.py`. Guide, library and games are rebuilt on each refresh, so those tables
are dropped and recreated when the column named in `want` is missing. Long-lived tables like `devices` need
an `ALTER TABLE` in `connect()`, or existing installs will break.

### A screen or section

Add a module in `whatson/static/js/` and route it in `main.js`. Build HTML with `esc()` around anything from
outside, call the server through `api()`, and check it at phone width and in light and dark mode.

## Pull requests

- Keep each one to a single change, and fill in the template.
- Every behaviour change or bug fix needs a test that fails without it. Tests don't use the network or real TVs.
- Add a line to `CHANGELOG.md` under **Unreleased** for anything a user would notice.
- All checks must pass; CI runs `scripts/check.py`, the privacy checks and a Docker build that starts the image.
- A maintainer reviews every pull request. Anything that handles keys, calls addresses people type, changes the
  request checks, takes over a TV or talks to Radarr or Sonarr gets a closer look (see `.github/CODEOWNERS`).
- Match the style of the file you're in. There's no linter, so please don't reformat code.
- Never include keys, tokens or details of your home in code, tests, logs or screenshots.
- `whatson/trakt.py` and its routes are present but have no interface for now.

Maintainers handle versions, tags and releases. By contributing, you agree your work is released under the
[MIT License](LICENSE).

## Conduct

Be kind and assume good faith. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
