"""Print the CHANGELOG.md section for a release, after checking the release is consistent.

    python scripts/release_notes.py 1.0.0 > notes.md

Fails (exit 1) unless pyproject.toml and whatson/__init__.py say that version and CHANGELOG.md has a "## 1.0.0" section
with something in it. The release workflow runs it on every v* tag, so a tag can't ship an image that reports another
version. Standard library only: the workflow runs it before installing anything."""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def problem(want: str) -> str:
    """What's wrong with releasing this version, or nothing."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    if project != want:
        return f"pyproject.toml says {project}, the tag says {want}"
    init = re.search(r'__version__\s*=\s*"([^"]+)"', (ROOT / "whatson" / "__init__.py").read_text(encoding="utf-8"))
    if not init or init.group(1) != want:
        return f"whatson/__init__.py says {init.group(1) if init else '?'}, the tag says {want}"
    if not notes(want):
        return f'CHANGELOG.md has no "## {want}" section (move Unreleased under it)'
    return ""


def notes(want: str) -> str:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(rf"^## {re.escape(want)}\b[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1).strip() if m else ""


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not re.fullmatch(r"\d+\.\d+\.\d+", argv[1]):
        print("usage: release_notes.py X.Y.Z", file=sys.stderr)
        return 2
    wrong = problem(argv[1])
    if wrong:
        print(wrong, file=sys.stderr)
        return 1
    print(notes(argv[1]))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # the changelog isn't plain ASCII, and a Windows console may not be UTF-8
    sys.exit(main(sys.argv))
