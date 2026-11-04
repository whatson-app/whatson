"""The docs stay true to the code: ADRs keep their format and index, links and paths work, and the reference docs in
docs/ name every route, module, table, setting and environment variable. See docs/adr/0001-record-decisions-as-adrs.md.

When one fails, fix the docs in the same pull request. A test can't tell whether a change needed an ADR: that's for the
pull request template and the reviewer."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from whatson import ai, arr, db
from whatson.app import app

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
ADR_DIR = DOCS / "adr"
ADRS = sorted(ADR_DIR.glob("[0-9]*.md"))
ADR_NAME = re.compile(r"(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md")
STATUS = re.compile(r"(Proposed|Accepted|Rejected|Deprecated|Superseded by ADR (\d{4}))")
SECTIONS = ("## Context", "## Decision", "## Consequences", "## Alternatives", "## Where it lives")
PAGES = [ROOT / "README.md", ROOT / "CONTRIBUTING.md", ROOT / "AGENTS.md", *sorted(DOCS.rglob("*.md"))]
PY = sorted((ROOT / "whatson").rglob("*.py"))


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def adr_status(p: Path) -> re.Match | None:
    m = re.search(r"^- \*\*Status:\*\* (.+)$", read(p), re.M)
    return STATUS.fullmatch(m.group(1).strip()) if m else None


# -- ADRs -----------------------------------------------------------------------------------------------------------

def test_there_are_adrs():
    assert len(ADRS) >= 24


def test_adrs_are_numbered_in_order():
    names = [ADR_NAME.fullmatch(p.name) for p in ADRS]
    assert all(names), f"name ADRs NNNN-short-title.md: {[p.name for p, n in zip(ADRS, names) if not n]}"
    numbers = [int(n.group(1)) for n in names]
    assert numbers == list(range(1, len(numbers) + 1)), f"ADR numbers must run in order with no gaps: {numbers}"


@pytest.mark.parametrize("p", ADRS, ids=rel)
def test_an_adr_follows_the_template(p):
    text = read(p)
    assert text.startswith(f"# {p.name[:4]}. "), f"{p.name} must start with '# {p.name[:4]}. Title'"
    assert adr_status(p), f"{p.name} needs a status line (see docs/adr/README.md for the allowed values)"
    assert re.search(r"^- \*\*Date:\*\* \d{4}-\d{2}-\d{2}$", text, re.M), f"{p.name} needs a date line"
    missing = [s for s in SECTIONS if not re.search(rf"^{s}$", text, re.M)]
    assert not missing, f"{p.name} is missing {missing}"


@pytest.mark.parametrize("p", ADRS, ids=rel)
def test_a_superseded_adr_names_one_that_exists(p):
    m = adr_status(p)
    if m and m.group(2):
        assert list(ADR_DIR.glob(f"{m.group(2)}-*.md")), f"{p.name} is superseded by a missing ADR {m.group(2)}"


@pytest.mark.parametrize("p", ADRS, ids=rel)
def test_the_index_lists_each_adr_with_its_status(p):
    row = re.search(rf"^\| \[{p.name[:4]}\]\({re.escape(p.name)}\) \| .+ \| (.+) \|$", read(ADR_DIR / "README.md"), re.M)
    assert row, f"add {p.name} to the table in docs/adr/README.md"
    assert row.group(1) == adr_status(p).group(1), f"{p.name}'s status differs in docs/adr/README.md"


def test_adrs_named_in_code_exist():
    named = [(p, n) for p in PY for group in re.findall(r"\bADRs? (\d{4}(?:, \d{4})*)", read(p))
             for n in group.split(", ")]
    assert named
    missing = [f"{rel(p)}: ADR {n}" for p, n in named if not list(ADR_DIR.glob(f"{n}-*.md"))]
    assert not missing, f"these name ADRs that don't exist: {missing}"


# -- Links and paths ------------------------------------------------------------------------------------------------

LINK = re.compile(r"\]\((?!https?://|#|mailto:)([^)#\s]+)(?:#[^)]*)?\)")
PATH = re.compile(r"`((?:whatson|tests|docs|scripts|deploy|\.github)/[\w./-]*)`")


def tracked() -> set[str]:
    """Tracked files and their folders. Not the local disk: a file on one machine must not pass."""
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.decode()
    files = {f for f in out.split("\0") if f}
    return files | {parent.as_posix() for f in files for parent in Path(f).parents}


@pytest.mark.parametrize("p", PAGES, ids=rel)
def test_links_between_pages_work(p):
    missing = [m for m in LINK.findall(read(p)) if not (p.parent / m).exists()]
    assert not missing, f"{rel(p)} links to missing files: {missing}"


@pytest.mark.parametrize("p", [x for x in PAGES if x.is_relative_to(DOCS)], ids=rel)
def test_paths_named_in_docs_exist(p):
    known = tracked()
    missing = [m for m in PATH.findall(read(p)) if "NNNN" not in m and m.rstrip("/") not in known]
    assert not missing, f"{rel(p)} names paths that aren't tracked in git: {missing}"


# -- Reference docs cover the code ----------------------------------------------------------------------------------

def test_every_route_is_in_the_api_docs():
    code = {f"{m.upper()} {path}" for path, ops in app.openapi()["paths"].items() for m in ops}
    documented = set(re.findall(r"^\| `([A-Z]+ /[^`]*)` \|", read(DOCS / "api.md"), re.M))
    assert not code - documented, f"add these to docs/api.md: {sorted(code - documented)}"
    assert not documented - code, f"docs/api.md lists routes that don't exist: {sorted(documented - code)}"


def test_every_module_is_in_the_architecture_doc():
    text = read(DOCS / "architecture.md")
    missing = [rel(p) for p in PY if f"`{rel(p)}`" not in text]
    assert not missing, f"add these to docs/architecture.md: {missing}"


def test_every_front_end_file_is_in_the_front_end_doc():
    static = ROOT / "whatson" / "static"
    text = read(DOCS / "frontend.md")
    missing = [rel(p) for p in static.rglob("*") if p.is_file() and f"`{rel(p)}`" not in text]
    assert not missing, f"add these to docs/frontend.md: {missing}"


def test_every_test_file_is_in_the_testing_doc():
    text = read(DOCS / "testing.md")
    missing = [rel(p) for p in (ROOT / "tests").glob("test_*.py") if f"`{rel(p)}`" not in text]
    assert not missing, f"add these to docs/testing.md: {missing}"


def test_every_table_is_in_the_data_model_doc():
    tables = re.findall(r"CREATE (?:VIRTUAL )?TABLE IF NOT EXISTS (\w+)", db.SCHEMA)
    assert tables
    text = read(DOCS / "data-model.md")
    missing = [t for t in tables if f"`{t}`" not in text]
    assert not missing, f"add these tables to docs/data-model.md: {missing}"


def test_every_saved_setting_is_in_the_data_model_doc():
    used = {k for p in PY for k in re.findall(r"""(?:get_meta|set_meta)\([\w.]+, ["']([\w.]+)["']""", read(p))}
    assert len(used) > 10
    text = read(DOCS / "data-model.md")
    missing = sorted(k for k in used if f"`{k}`" not in text)
    assert not missing, f"add these meta keys to docs/data-model.md: {missing}"


def test_every_environment_variable_is_in_the_configuration_doc():
    read_directly = re.compile(r"""(?:environ(?:\.get)?[\[(]|_int\(|pick\("\w+", )["']([A-Z][A-Z0-9_]+)["']""")
    names = {n for p in PY for n in read_directly.findall(read(p))} | set(ai.KEY_ENV.values())
    names |= {f"{app_name.upper()}_{part}" for app_name in arr.APP.values() for part in ("URL", "KEY")}
    assert len(names) > 15
    text = read(DOCS / "configuration.md")
    missing = sorted(n for n in names if f"`{n}`" not in text)
    assert not missing, f"add these to docs/configuration.md: {missing}"
