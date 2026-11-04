from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from whatson import db
from whatson.ai import Interpreter
from whatson.app import app
from whatson.state import state
from whatson.trakt import Trakt


async def _no_up_next() -> list:
    return []


@pytest.fixture
def saved_seerr_row(monkeypatch):
    """A database from an older install, which may still hold the address."""
    conn = db.connect(":memory:")
    db.set_meta(conn, "seerr_url", "http://192.0.2.5:5055")
    monkeypatch.setattr(state, "conn", conn, raising=False)
    monkeypatch.setattr(state, "trakt", Trakt(conn, http=object()))
    monkeypatch.setattr(state, "source", SimpleNamespace(name="fake", label="Fake", up_next=_no_up_next))
    monkeypatch.setattr(state, "interpreter", Interpreter("none"))
    return conn


def client() -> TestClient:
    return TestClient(app, base_url="http://localhost")


def test_the_seerr_address_can_no_longer_be_saved(saved_seerr_row):
    res = client().put("/api/settings/seerr", json={"url": "http://192.0.2.6:5055"}, headers={"X-WhatsOn": "1"})
    assert res.status_code == 404
    assert db.get_meta(saved_seerr_row, "seerr_url") == "http://192.0.2.5:5055"


@pytest.mark.parametrize("path", ["/api/trakt", "/api/suggest/library"])
def test_a_saved_seerr_address_is_not_returned(saved_seerr_row, path):
    res = client().get(path)
    assert res.status_code == 200, res.text
    assert "seerr" not in res.text and "192.0.2.5" not in res.text
