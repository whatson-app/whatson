from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "whatson" / "static"
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
SETTINGS_JS = (STATIC / "js" / "settings.js").read_text(encoding="utf-8")
ALL_JS = "\n".join(p.read_text(encoding="utf-8") for p in (STATIC / "js").glob("*.js"))
PLACES = {m.group(1): (m.group(2), m.group(3)) for m in re.finditer(
    r'(\w+): \["(\w+)"(?:, "(\w+)")?\]', re.search(r"const PLACES = \{(.*?)\n\};", SETTINGS_JS, re.S).group(1))}


def test_settings_has_the_four_tabs_in_order():
    assert re.findall(r'data-tab="(\w+)"', HTML) == ["server", "tvs", "sports", "more"]


def test_every_place_points_at_a_real_tab_and_section():
    assert len(PLACES) == 11
    for tab, fold in PLACES.values():
        assert f'<section data-panel="{tab}"' in HTML
        if fold:
            assert f'id="fold-{fold}"' in HTML


def test_every_link_into_settings_has_a_place():
    used = set(re.findall(r'data-settings="(\w+)"', HTML + ALL_JS)) | set(re.findall(r'openSettings\("(\w+)"\)', ALL_JS))
    assert used and used <= set(PLACES), f"no place for {used - set(PLACES)}"


def test_every_section_kept_its_controls():
    for control in ('id="px-signin"', 'id="px-manual"', 'id="jf-form"', 'id="jf-user"', 'id="add-tv"', 'id="sp-leagues"',
                    'id="dl-allow"', 'name="theme"', 'id="tk-app-form"', 'id="tk-connect"'):
        assert control in HTML, control
