# Testing

```bash
python scripts/check.py            # every check, the same as CI
python scripts/check.py --quick    # skips the full test suite while you work
python -m pytest -q tests/test_remote.py
```

`scripts/check.py` runs the guard tests, all tests, the docs tests, the privacy check, and a syntax check of the front-end
scripts when Node.js is installed. CI also runs gitleaks over the whole history, and builds and starts the Docker image.

## Test files

| File | What it covers |
|---|---|
| `tests/test_guards.py` | The rules in `AGENTS.md` that a test can check. See [ADR 0021](adr/0021-rules-enforced-by-guard-tests.md) |
| `tests/test_docs.py` | ADR format and index, links and paths, and that the reference docs cover the code |
| `tests/test_core.py` | Linking games to listings, and search |
| `tests/test_sources.py` | Plex and Jellyfin clients, and switching server |
| `tests/test_remote.py` | Remote tab, TV driver and app lists. The model for faking a TV |
| `tests/test_arr.py` | Radarr and Sonarr |
| `tests/test_plex_auth.py` | Plex sign-in and tokens |
| `tests/test_suggest.py` | Suggestion rows |
| `tests/test_settings_layout.py` | Settings tabs and links into them |
| `tests/test_progress_ui.py` | Wiring for search and AI progress |
| `tests/test_release.py` | Release notes and version checks |
| `tests/test_unraid.py` | The Unraid template matches how the app runs |
| `tests/test_version.py` | The status route reports the version |
| `tests/test_seerr_removed.py` | The old Seerr address can't be saved and is never returned |

## How tests are written

- **Offline and made up.** No network, no real TV and no real data. See `tests/AGENTS.md`.
- **HTTP** is faked with `httpx.MockTransport`, and **the TV connection** as `tests/test_remote.py` does it.
- **Storage** is `db.connect(":memory:")`.
- **A bug fix starts with a failing test.** Every behaviour change has a test that fails without it.

## What tests can't tell you

- **Whether anything works on a real TV.** Nothing here touches hardware. Say so in the pull request if you didn't try it.
- **How a screen looks.** There are no browser tests, so check phone width and both themes by hand.
- **How a real server responds.** Fakes reflect what we believe about Plex, Jellyfin, Plezy and ESPN.
- **Whether a change needed an ADR.** That's for the pull request template and the reviewer.
