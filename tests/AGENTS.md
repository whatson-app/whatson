# tests/: pytest

Local rules for tests. The top-level `AGENTS.md` comes first.

- **Offline and made up.** No network, no real TV, no real data. Addresses are `192.0.2.x`, or the stand-ins listed in
  `scripts/check_public.py` when a test needs a LAN address. Names are invented. Never paste a real log or response.
- **Reuse what's here.** Fake HTTP with `httpx.MockTransport` and the TV connection as `tests/test_remote.py` does.
  Storage is `db.connect(":memory:")`.
- **Test the behaviour, not the implementation.** One test per behaviour, named for it.
- **A bug fix starts with a failing test** that reproduces it.
- **`tests/test_guards.py` is not yours to change.** It encodes the rules in `AGENTS.md`. If it fails, the change is
  wrong; if the rule itself must change, say so in an issue first. Don't loosen an assertion, add a skip or widen an
  allowlist to get past it.
- **`tests/test_docs.py` keeps the docs true to the code.** If it fails, fix the docs. A new test file goes in
  `docs/testing.md`.
- Run one file with `python -m pytest -q tests/test_x.py`; everything with `python scripts/check.py`.
