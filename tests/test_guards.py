"""Guard tests: the rules in AGENTS.md that a test can check, checked. They exist so that a contributor, human or AI,
who has not read the rules still can't break them by accident. When one fails, read the message and the AGENTS.md
rule it names; don't edit the test to make it pass. Changing a guard (a new outside host, a new use of state.http) is
a design decision: say so in the pull request and expect a closer review.

They read the source or call the app in-process. They never use the network or a real TV."""
from __future__ import annotations

import ast
import re
import subprocess
import tomllib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from whatson import ai_settings, arr, db, remote_routes, safe_http
from whatson.ai import Interpreter
from whatson.app import app, host_allowed
from whatson.sources.plex import PlexClient
from whatson.state import state

ROOT = Path(__file__).resolve().parent.parent
PY = sorted((ROOT / "whatson").rglob("*.py"))
STATIC = ROOT / "whatson" / "static"
JS = sorted((STATIC / "js").glob("*.js"))
HTML = sorted(STATIC.rglob("*.html"))


def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def js_code(text: str) -> str:
    """JS with // line comments and /* block */ comments blanked out (good enough for the patterns checked here)."""
    text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group().count("\n"), text, flags=re.S)
    return re.sub(r"(^|[^:\"'\\])//.*", r"\1", text)


def client() -> TestClient:
    return TestClient(app, base_url="http://localhost")  # not used as a context manager, so start-up doesn't run


# -- Requests that change things ------------------------------------------------------------------------------------

CHANGING = sorted((path, m.upper()) for path, ops in app.openapi()["paths"].items()
                  for m in ops if m in ("post", "put", "patch", "delete"))


def test_the_route_list_is_not_empty():
    assert len(CHANGING) > 10


@pytest.mark.parametrize(("path", "method"), CHANGING)
def test_changing_something_needs_the_header(path, method):
    res = client().request(method, re.sub(r"\{[^}]+\}", "1", path))
    assert res.status_code == 403 and res.json()["detail"] == "Missing X-WhatsOn header", (
        f"{method} {path} works without X-WhatsOn. Never exempt a route (AGENTS.md → Security)")


def test_unknown_host_names_are_refused():
    assert not host_allowed("rebind.example.com:8430")
    res = client().get("/health", headers={"host": "rebind.example.com"})
    assert res.status_code == 403, "don't loosen host_allowed: it stops DNS rebinding (AGENTS.md → Security)"


# -- Keys and tokens ------------------------------------------------------------------------------------------------

SECRET = "guard-secret-value-12345678"
JF_URL = "http://192.0.2.7:8096"


@pytest.fixture
def saved_keys(monkeypatch):
    """A database with a key saved in every place the app keeps one."""
    conn = db.connect(":memory:")
    for key in ("plex.jwt", "plex.key", "plex.server_token", "jellyfin.key", "arr.movie.key", "arr.show.key",
                "ai.key.openai", "ai.key.anthropic", "ai.key.openrouter"):
        db.set_meta(conn, key, SECRET)
    db.set_meta(conn, "plex.source", "token")
    db.set_meta(conn, "plex.url", "http://192.0.2.8:32400")
    db.set_meta(conn, "jellyfin.url", JF_URL)
    for kind in ("movie", "show"):
        db.set_meta(conn, f"arr.{kind}", '{"url": "http://192.0.2.9:7878"}')
        db.set_meta(conn, f"arr.{kind}.key_base", "http://192.0.2.9:7878")
    for provider in ("openai", "anthropic", "openrouter"):
        db.set_meta(conn, f"ai.key_base.{provider}", "")
    plex = PlexClient("http://192.0.2.8:32400", SECRET, "WhatsOn")
    monkeypatch.setattr(state, "conn", conn, raising=False)
    monkeypatch.setattr(state, "plex", plex)
    monkeypatch.setattr(state, "source", plex)
    monkeypatch.setattr(state, "interpreter", Interpreter("none"))
    return conn


@pytest.mark.parametrize("path", ["/api/settings/ai", "/api/settings/downloads", "/api/settings/jellyfin",
                                  "/api/settings/plex", "/api/settings/source"])
def test_settings_never_send_a_key_to_the_browser(saved_keys, path):
    res = client().get(path)
    assert res.status_code == 200, res.text
    assert SECRET not in res.text and "guard-secret" not in res.text, (
        f"{path} returned a saved key. Say it's saved and show a short hint at most (AGENTS.md → Security)")


@pytest.mark.parametrize("p", JS, ids=rel)
def test_the_plex_token_stays_out_of_the_front_end(p):  # index.html only tells people where to find theirs
    assert "x-plex-token" not in read(p).lower(), "Plex artwork goes through /api/thumb (AGENTS.md → Security)"


def test_saved_keys_only_go_to_the_address_they_were_saved_with(saved_keys):
    assert remote_routes._key_for(JF_URL, "") == SECRET
    assert remote_routes._key_for("http://192.0.2.66:8096", "") == "", "Jellyfin key offered to a new address"
    assert arr.load(saved_keys, "movie").key == SECRET
    db.set_meta(saved_keys, "arr.movie", '{"url": "http://192.0.2.66:7878"}')
    assert arr.load(saved_keys, "movie").key == "", "Radarr key offered to a new address"
    assert ai_settings.load(saved_keys).keys["openai"][0] == SECRET
    db.set_meta(saved_keys, "ai.base_url", "http://192.0.2.66:1234/v1")
    assert ai_settings.load(saved_keys).keys["openai"][0] == "", "AI key offered to a new address"


# -- Addresses typed in Settings ------------------------------------------------------------------------------------

# state.http doesn't re-check addresses and is only for fixed public hosts: ESPN, Trakt and plex.tv.
STATE_HTTP_OK = re.compile(r"state\.http = httpx\.AsyncClient|state\.http\.aclose\(\)|Trakt\(state\.conn, state\.http\)"
                           r"|PlexTV\(state\.conn, state\.http,|espn\.fetch_\w+\(.*state\.http\)")


def test_state_http_is_only_for_fixed_public_hosts():
    bad = [f"{rel(p)}:{n}" for p in PY if p.name != "state.py" for n, line in enumerate(read(p).splitlines(), 1)
           if "state.http" in line and not STATE_HTTP_OK.search(line)]
    assert not bad, f"{bad} use state.http. Addresses typed in Settings go through state.lan_http (AGENTS.md → Security)"


def test_the_lan_client_does_not_follow_redirects():
    assert safe_http.client().follow_redirects is False, "a redirect could carry a saved key somewhere else"


# -- Radarr and Sonarr ----------------------------------------------------------------------------------------------

def test_radarr_and_sonarr_are_add_and_search_only():
    tree = ast.parse(read(ROOT / "whatson" / "arr.py"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "_req"]
    assert calls
    posts = set()
    for call in calls:
        method = call.args[0].value
        assert method in ("GET", "POST"), f"arr.py sends {method}. WhatsOn never edits or deletes (AGENTS.md → Security)"
        if method == "POST":
            posts.add(ast.unparse(call.args[1]))
    assert posts == {"'/movie' if self.kind == 'movie' else '/series'", "'/command'"}, (
        f"arr.py posts to {posts}. Only adding a title and starting a search are allowed (AGENTS.md → Security)")
    commands = set(re.findall(r"""["']name["']:\s*["'](\w+)["']""", read(ROOT / "whatson" / "arr.py")))
    assert commands == {"MoviesSearch", "SeriesSearch"}, f"Radarr/Sonarr commands changed: {commands}"
    outside = [rel(p) for p in PY if p.name != "arr.py" and re.search(r"\._req\(.*(PUT|DELETE|PATCH)", read(p))]
    assert not outside, f"{outside} reach Radarr or Sonarr's API directly"


# -- Interrupting a TV ----------------------------------------------------------------------------------------------

# open_link replaces what's playing. Only these may call it without the busy check. They start nothing by themselves:
# the driver's own code, and the Remote tab's app row, where a person pressed a button for that app on that TV.
OPEN_LINK_OK = {"whatson/devices/androidtv.py", "whatson/devices/base.py", "whatson/remote_routes.py"}


def test_starting_something_on_a_tv_checks_whether_its_busy():
    for p in PY:
        if rel(p) in OPEN_LINK_OK:
            continue
        for fn in ast.walk(ast.parse(read(p))):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                src = ast.unparse(fn)
                if ".open_link(" in src:
                    assert "check_busy(" in src, (f"{rel(p)}:{fn.name} starts something on a TV without asking first "
                                                  "(AGENTS.md → Security)")


# -- AI -------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("p", PY, ids=rel)
def test_ai_libraries_stay_optional(p):
    top = [n for n in ast.parse(read(p)).body if isinstance(n, (ast.Import, ast.ImportFrom))]
    names = {a.name.split(".")[0] for n in top if isinstance(n, ast.Import) for a in n.names}
    names |= {(n.module or "").split(".")[0] for n in top if isinstance(n, ast.ImportFrom)}
    assert not names & {"anthropic", "openai"}, "everything must work with AI off: import these inside the function"


def test_ai_off_means_off():
    assert not Interpreter("none").enabled


# -- Outside services -----------------------------------------------------------------------------------------------

OUTSIDE_HOSTS = {
    "api.trakt.tv", "app.plex.tv", "clients.plex.tv", "image.tmdb.org", "openrouter.ai", "site.api.espn.com",
    # Links that open an app on a TV; WhatsOn never calls these itself.
    "app.primevideo.com", "play.max.com", "tv.apple.com", "tv.youtube.com", "www.disneyplus.com", "www.hulu.com",
    "www.netflix.com", "www.paramountplus.com", "www.peacocktv.com", "www.youtube.com",
}
HOST = re.compile(r"https?://([A-Za-z][\w-]*(?:\.[\w-]+)+)")


def test_no_new_outside_services():
    found = {h.lower() for p in PY for h in HOST.findall(read(p))} - {"example.com"}
    new = found - OUTSIDE_HOSTS
    assert not new, f"new outside hosts {sorted(new)}: telemetry and new services need an agreed issue (AGENTS.md)"


def test_the_front_end_loads_nothing_from_the_web():
    load = re.compile(r"""<(?:script|link|img|iframe)\b[^>]*\b(?:src|href)\s*=\s*["']https?://"""
                      r"""|\bimport\b[^;\n]*["']https?://|fetch\(\s*["'`]https?://""")
    hits = [rel(p) for p in [*JS, *HTML] if load.search(read(p))]
    assert not hits, f"{hits} load from the web. No CDNs and no outside calls from the browser"


def test_no_new_dependencies_or_build_step():
    project = tomllib.loads(read(ROOT / "pyproject.toml"))["project"]
    names = {re.match(r"[\w-]+", d).group().lower() for d in project["dependencies"]}
    assert names == {"fastapi", "uvicorn", "httpx", "androidtvremote2", "zeroconf", "cryptography"}, (
        f"dependencies are now {sorted(names)}. A new one must be agreed first (AGENTS.md → Don't do these)")
    assert set(project["optional-dependencies"]) == {"anthropic", "openai", "dev"}
    assert not (ROOT / "package.json").exists(), "the front end has no build step, on purpose"


# -- Front end ------------------------------------------------------------------------------------------------------

def test_no_running_text_as_code():
    bad = re.compile(r"document\.write\s*\(|\beval\s*\(|new Function\s*\(")
    hits = [f"{rel(p)}:{n}" for p in JS for n, line in enumerate(js_code(read(p)).splitlines(), 1) if bad.search(line)]
    assert not hits, f"{hits}: guide data and titles come from outside, so never run or write them raw"


def test_titles_are_escaped_when_put_in_html():
    """Catches the common slip, <b>${x.title}</b>. It can't see every path, so review still has to look for esc()."""
    field = re.compile(r"\$\{\s*[A-Za-z_][\w.?]*\.(?:title|subtitle|summary|overview|name|tagline|studio|network)\s*\}")
    hits = [f"{rel(p)}:{n}" for p in JS for n, line in enumerate(js_code(read(p)).splitlines(), 1)
            if field.search(line) and re.search(r"</?[a-z]", line)]
    assert not hits, f"{hits}: wrap anything from outside in esc() (AGENTS.md → Security)"


# Hard-coded colours left when this test was written. The rule is the tokens in whatson/static/style.css; this only
# stops the number from growing. Lower a count when you remove some.
# Both are the browser's theme-color, which can't read a CSS token.
HEX_BASELINE = {"whatson/static/index.html": 2, "whatson/static/js/core.js": 2}
HEX = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b(?![\w-])")


@pytest.mark.parametrize("p", [*JS, *HTML], ids=rel)
def test_no_new_hard_coded_colours(p):
    n, allowed = len(HEX.findall(js_code(read(p)) if p.suffix == ".js" else read(p))), HEX_BASELINE.get(rel(p), 0)
    assert n <= allowed, f"{rel(p)} has {n} hard-coded colours (allowed {allowed}). Use the tokens in style.css"
    assert n == allowed, f"{rel(p)} is down to {n} hard-coded colours: lower HEX_BASELINE to match, so it stays down"


# -- Rules for AI agents --------------------------------------------------------------------------------------------

AGENT_DOCS = [ROOT / "AGENTS.md", *sorted(p for p in ROOT.glob("*/AGENTS.md"))]
PATH_REF = re.compile(r"`((?:whatson|tests|docs|scripts|\.github)/[\w./-]*)`")


def test_claude_reads_the_rules():
    """Claude Code reads CLAUDE.md, not AGENTS.md, so each AGENTS.md needs a CLAUDE.md beside it that imports it."""
    for doc in AGENT_DOCS:
        beside = doc.with_name("CLAUDE.md")
        assert beside.exists() and "@AGENTS.md" in read(beside), f"{rel(beside)} must contain @AGENTS.md"


def _in_repo(path: str) -> bool:
    """Tracked in git or a folder holding tracked files. Not the local disk: a file on one machine must not pass."""
    return bool(subprocess.run(["git", "ls-files", "--", path.rstrip("/")], cwd=ROOT, capture_output=True,
                               text=True).stdout.strip())


@pytest.mark.parametrize("doc", AGENT_DOCS, ids=rel)
def test_paths_in_agent_docs_exist(doc):
    missing = [m for m in PATH_REF.findall(read(doc)) if not _in_repo(m)]
    assert not missing, f"{rel(doc)} names paths that don't exist: {missing}. Fix the doc in the same pull request."
