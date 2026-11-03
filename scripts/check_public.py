"""Check the tracked files for things that must never be published: private LAN addresses, personal email addresses,
Plex tokens, databases and stray images. CI runs it on every pull request.

    python scripts/check_public.py

Your own values (your server's address, TV or room names, your Plex server id) go one per line in `.private-denylist`
at the repo root. That file is git-ignored, so the check covers them without publishing them."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PRIVATE_IP = re.compile(r"\b(?:192\.168|172\.(?:1[6-9]|2\d|3[01])|10\.\d{1,3})\.\d{1,3}\.\d{1,3}\b")
# WhatsOn is about LAN addresses, so its form hints and tests need some. These stand-ins are the only ones allowed.
EXAMPLE_IP = re.compile(r"^(?:192\.168\.1\.(?:5|10|20|50)|10\.0\.0\.\d{1,3})$")
# user@domain.tld, not user:password@host in a URL, a package@version or an image@2x
EMAIL = re.compile(r"(?<![:/\w.+-])[A-Za-z][\w.+-]*@[A-Za-z][\w-]*(?:\.[A-Za-z][\w-]*)*\.[A-Za-z]{2,}\b")
EMAIL_OK = re.compile(r"@(?:example\.(?:com|org|net)|users\.noreply\.github\.com|anthropic\.com)$"
                      r"|\.(?:test|example|invalid|localhost)$|^noreply@", re.I)
PLEX_TOKEN = re.compile(r"X-Plex-Token=[\w-]{15,}")
DATA_FILES = re.compile(r"\.(?:db|sqlite3?|db-wal|db-shm|pcap|pcapng|log)$|(?:^|/)\.env$|(?:^|/)data/", re.I)
IMAGES = re.compile(r"\.(?:png|jpe?g|webp|gif)$", re.I)
IMAGES_OK = ("whatson/static/", "docs/screenshots/")
SKIP_TEXT = re.compile(r"\.(?:png|jpe?g|webp|gif|ico|woff2?|ttf|pdf)$", re.I)


def tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return [p for p in out.decode().split("\0") if p]


def main() -> int:
    deny = []
    f = ROOT / ".private-denylist"
    if f.exists():
        deny = [s.strip() for s in f.read_text(encoding="utf-8").splitlines() if s.strip() and not s.startswith("#")]
    problems = []
    for path in tracked():
        if DATA_FILES.search(path):
            problems.append(f"{path}: looks like data, not code (databases, logs, .env and data/ stay out of git)")
        if IMAGES.search(path) and not path.startswith(IMAGES_OK):
            problems.append(f"{path}: images belong in whatson/static/ or docs/screenshots/ (made-up content only)")
        if SKIP_TEXT.search(path) or path == "scripts/check_public.py":
            continue
        try:
            text = (ROOT / path).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for m in PRIVATE_IP.finditer(line):
                if not EXAMPLE_IP.match(m.group()):
                    problems.append(f"{path}:{n}: private address {m.group()} (use 192.0.2.x in examples and tests)")
            for m in EMAIL.finditer(line):
                if not EMAIL_OK.search(m.group()):
                    problems.append(f"{path}:{n}: email address (use user@example.com)")
            if PLEX_TOKEN.search(line):
                problems.append(f"{path}:{n}: looks like a Plex token")
            for d in deny:
                if d.lower() in line.lower():
                    problems.append(f"{path}:{n}: a value from .private-denylist")
    for p in problems:
        print(p)
    print(f"check_public: {len(problems)} problem(s) in {len(tracked())} files")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
