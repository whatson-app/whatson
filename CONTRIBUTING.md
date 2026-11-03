# Contributing

Issues and pull requests are welcome. Roku, Fire TV and other TV drivers are the most useful addition,
since only Google TV / Android TV works today.

## Set up

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev,anthropic,openai]"
DATA_DIR=./data .venv/bin/uvicorn whatson.app:app --reload --port 8430
.venv/bin/pytest
```

Open `http://localhost:8430`, then connect Plex in ⚙ → Plex. The front end is plain JavaScript modules
with no build step.

## Adding a TV type

Implement the `TVDriver` protocol in `whatson/devices/base.py` and register the driver in
`whatson/app.py`. `whatson/devices/androidtv.py` is the working example. Keep tune and remote behaviour
behind the driver, so the rest of the app stays TV-agnostic.

## Good to know

- Please test on a real TV before sending a driver, and say which models you tried.
- Before taking over a TV, WhatsOn checks whether something is playing and asks. Keep that for new drivers.
- Keys and tokens must never reach the browser; add a test if you add a new one.
- `whatson/trakt.py` and its routes are present but have no interface for now.
