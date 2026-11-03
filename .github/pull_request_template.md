## What this changes and why

<!-- One change per pull request. Link the issue if there is one: Fixes #123 -->

## How it was tested

- [ ] `python scripts/check.py` prints "all checks passed" (tests, guard tests, privacy, JS)
- [ ] New or changed behaviour has a test that fails without this change
- [ ] `CHANGELOG.md` (Unreleased) updated, if a user would notice
- [ ] For screen changes: checked at phone width and in light and dark mode

Tried on real hardware (TV model and app, or "not tried"):

Not tested:

## Security (tick what applies)

- [ ] Saves a key or token, or changes where one is sent
- [ ] Calls an address typed in Settings, or a new outside service
- [ ] Changes the `X-WhatsOn` or host checks, or the check for something already playing on a TV
- [ ] Changes what's sent to Radarr or Sonarr
- [ ] Changes `tests/test_guards.py` (explain why the rule itself should change)
- [ ] None of the above

## AI use

- [ ] No AI was used
- [ ] AI helped. Tool, and what it did:
- [ ] A person read the whole diff and can explain it

## Checks

- [ ] One change only, with no unrelated cleanups
- [ ] No keys, tokens or details of a real home in the code, tests, logs or screenshots
- [ ] No new dependencies, workflow changes or version bumps, or they were agreed in an issue
