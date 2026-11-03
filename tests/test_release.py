from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("release_notes", ROOT / "scripts" / "release_notes.py")
release_notes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_notes)


def repo(tmp_path, project="1.2.3", init="1.2.3", changelog="## Unreleased\n\n## 1.2.3 - 2026-01-01\n\n- A fix\n\n## 1.2.2\n\n- Old\n"):
    (tmp_path / "whatson").mkdir()
    (tmp_path / "pyproject.toml").write_text(f'[project]\nversion = "{project}"\n', encoding="utf-8")
    (tmp_path / "whatson" / "__init__.py").write_text(f'__version__ = "{init}"\n', encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    return tmp_path


def test_a_consistent_release_prints_only_its_own_notes(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(release_notes, "ROOT", repo(tmp_path))
    assert release_notes.main(["x", "1.2.3"]) == 0
    assert capsys.readouterr().out.strip() == "- A fix"


@pytest.mark.parametrize("files", [{"project": "1.2.2"}, {"init": "1.2.2"}, {"changelog": "## Unreleased\n\n- A fix\n"},
                                   {"changelog": "## 1.2.3\n\n## 1.2.2\n\n- Old\n"}])
def test_a_tag_that_disagrees_with_the_repo_is_refused(tmp_path, monkeypatch, capsys, files):
    monkeypatch.setattr(release_notes, "ROOT", repo(tmp_path, **files))
    assert release_notes.main(["x", "1.2.3"]) == 1
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("bad", ["v1.2.3", "1.2", "latest"])
def test_a_tag_that_is_not_a_version_is_refused(bad):
    assert release_notes.main(["x", bad]) == 2


def test_notes_print_on_a_console_that_is_not_utf8():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    run = subprocess.run([sys.executable, str(ROOT / "scripts" / "release_notes.py"), version], capture_output=True,
                         env={**os.environ, "PYTHONIOENCODING": "cp1252"})
    assert run.returncode == 0, run.stderr.decode()
    assert run.stdout.decode("utf-8").replace("\r\n", "\n").strip() == release_notes.notes(version)


def test_this_repo_could_release_its_current_version():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    assert release_notes.problem(version) == ""
