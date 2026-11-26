"""WhatsOn can be served under a path prefix, such as a Home Assistant ingress panel at /api/ingress/whatson/.
That only works while the page asks for its files and the API with relative URLs."""
from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "whatson" / "static"
JS = STATIC / "js"


def test_the_page_loads_its_files_relatively():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert not re.search(r'(?:src|href)="/(?!/)', html)


def test_direct_fetches_use_relative_urls():
    for f in JS.glob("*.js"):
        assert not re.search(r"fetch\(\s*[\"'`]/(?!/)", f.read_text(encoding="utf-8")), f.name


def test_api_calls_and_artwork_resolve_under_a_prefix():
    core = (JS / "core.js").read_text(encoding="utf-8")
    assert "fetch(rel(path)" in core
    assert "`api/thumb?path=" in core
