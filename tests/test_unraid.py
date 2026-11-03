from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_unraid_template_matches_how_the_app_runs():
    t = ET.parse(ROOT / "deploy" / "unraid" / "whatson.xml").getroot()
    assert t.findtext("Repository") == "ghcr.io/whatson-app/whatson:latest"
    assert t.findtext("Network") == "host", "TVs are reached directly on the LAN"
    assert t.findtext("WebUI") == "http://[IP]:8430/"
    assert "--port\", \"8430" in (ROOT / "Dockerfile").read_text(encoding="utf-8")
    configs = {c.get("Target"): c for c in t.findall("Config")}
    assert configs["/data"].get("Required") == "true"
    assert configs["PLEX_TOKEN"].get("Mask") == "true", "the token must stay hidden on Unraid's Edit page"
    assert not (configs["PLEX_TOKEN"].text or "").strip(), "the shipped template holds no token"


def test_unraid_template_points_at_files_in_this_repo():
    t = ET.parse(ROOT / "deploy" / "unraid" / "whatson.xml").getroot()
    raw = "https://raw.githubusercontent.com/whatson-app/whatson/main/"
    for tag in ("TemplateURL", "Icon"):
        url = t.findtext(tag)
        assert url.startswith(raw) and (ROOT / url.removeprefix(raw)).exists(), f"{tag} points at a missing file"
