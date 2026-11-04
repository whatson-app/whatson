from __future__ import annotations

from fastapi.testclient import TestClient

from whatson import __version__, db
from whatson.ai import Interpreter
from whatson.app import app
from whatson.sources.plex import PlexClient
from whatson.state import state


def test_status_says_which_version_is_running(monkeypatch):
    monkeypatch.setattr(state, "conn", db.connect(":memory:"), raising=False)
    monkeypatch.setattr(state, "source", PlexClient("", "", "WhatsOn"))
    monkeypatch.setattr(state, "interpreter", Interpreter("none"))
    res = TestClient(app, base_url="http://localhost").get("/api/status")
    assert res.status_code == 200 and res.json()["version"] == __version__
