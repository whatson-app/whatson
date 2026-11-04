"""The front end has no browser tests, so these only catch the wiring being removed. How it looks and behaves is
checked by hand."""
from __future__ import annotations

from pathlib import Path

import pytest

JS = Path(__file__).resolve().parent.parent / "whatson" / "static" / "js"
CSS = (JS.parent / "style.css").read_text(encoding="utf-8")


@pytest.mark.parametrize(("file", "waits_for"), [("search.js", "/api/answer"), ("live.js", "/api/suggest/live"),
                                                 ("library.js", "/api/suggest/library"), ("sports.js", "/api/sports/recap")])
def test_a_placeholder_shows_before_waiting_on_ai(file, waits_for):
    text = (JS / file).read_text(encoding="utf-8")
    assert "aiPlaceholder(" in text and text.index("aiPlaceholder(", text.index("import") + 100) < text.index(waits_for)


def test_placeholders_only_claim_ai_when_it_is_on():
    for file in ("live.js", "library.js"):
        assert 'if (ai.on) $(' in (JS / file).read_text(encoding="utf-8")


def test_a_slow_search_cannot_overwrite_a_newer_one():
    assert "id !== latest" in (JS / "search.js").read_text(encoding="utf-8")


def test_motion_respects_the_reduced_motion_setting():
    assert "prefers-reduced-motion: reduce" in CSS
