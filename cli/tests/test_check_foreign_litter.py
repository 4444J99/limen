"""Tests for scripts/check-foreign-litter.py — the sensor that must never report clean over litter.

The 2026-08-07 miss is the reason this file exists. An npmrc carrying `prefix=${XDG_DATA_HOME}/npm`
was read by a child process whose environment had been filtered to an allowlist without `XDG_*`;
npm left the variable literal, the prefix became relative, and 121 MB of `@google/gemini-cli` landed
in a directory named `${XDG_DATA_HOME}` at the repo root. The sensor whose stated job is "no other
vendor's session state squats untracked in the live checkout" printed `clean` and exited 0.

It missed because both original classes are narrower than their names suggest: class 1 looks only under
`.agents/`, and class 2 skips anything that is not a single-component *file*. An untracked root-level
DIRECTORY fell between them. Class 3 closes that gap, and its predicate carries the real subtlety —
"git tracks nothing under it", not merely "its first path component is untracked". Grouping untracked
paths by first component alone flags `docs/` and `studium/`, which are tracked directories that
merely contain untracked files. `test_tracked_dir_holding_untracked_files_is_not_litter` is the guard
on that, and it is the test that would have failed the naive implementation.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_foreign_litter", ROOT / "scripts" / "check-foreign-litter.py")
fl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fl)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    """A real git repo with one tracked directory — the sensor's verdict is git's, so git must be real."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "test")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "tracked.md").write_text("tracked\n")
    # Committed locally so the test does not depend on the host's global core.excludesFile —
    # limen's own .gitignore carries this rule, and the sensor's blind spot below turns on it.
    (tmp_path / ".gitignore").write_text("node_modules/\n")
    _git(tmp_path, "add", "docs/tracked.md", ".gitignore")
    _git(tmp_path, "commit", "-qm", "init")
    monkeypatch.setattr(fl, "ROOT", tmp_path)
    return tmp_path


def _plant_foreign_tree(repo: Path, name: str = "${XDG_DATA_HOME}") -> Path:
    """The exact shape npm produced: a literal-variable dir holding a global prefix.

    The `npm/bin/` entry is load-bearing, not decoration. `node_modules/` is excluded by the standard
    ignore rules, so a tree planted ONLY under it is invisible to `--exclude-standard` — see
    `test_a_wholly_ignored_tree_is_outside_this_sensors_definition`. The real install was catchable
    because npm also writes `bin/` and `etc/`, which nothing ignores.
    """
    pkg = repo / name / "npm" / "lib" / "node_modules" / "@google" / "gemini-cli"
    pkg.mkdir(parents=True)
    (pkg / "package.json").write_text('{"name":"@google/gemini-cli"}\n')
    binary = repo / name / "npm" / "bin"
    binary.mkdir(parents=True)
    (binary / "gemini").write_text("#!/bin/sh\n")
    return repo / name


def test_untracked_root_dir_is_litter(repo):
    planted = _plant_foreign_tree(repo)
    assert fl.find_root_dirs() == [planted]


def test_tracked_dir_holding_untracked_files_is_not_litter(repo):
    """The false-positive guard: `docs/` is tracked and merely contains an untracked file."""
    (repo / "docs" / "untracked.md").write_text("new\n")
    assert fl.find_root_dirs() == []


def test_class3_is_reported_alongside_the_original_classes(repo):
    planted = _plant_foreign_tree(repo)
    (repo / "docs" / "untracked.md").write_text("new\n")
    findings = fl.find_agents_litter() + fl.find_root_droppings() + fl.find_root_dirs()
    assert findings == [planted]


def test_class3_label_names_the_directory_case(repo):
    planted = _plant_foreign_tree(repo)
    assert "directory" in fl._label(planted)


def test_root_file_dropping_is_still_class2(repo):
    """A single-component file stays class 2's — class 3 must not swallow it."""
    (repo / "1").write_text("stray redirect\n")
    assert fl.find_root_droppings() == [repo / "1"]
    assert fl.find_root_dirs() == []


def test_reap_quarantines_a_directory(repo, monkeypatch):
    """Class 3 findings are the first directories to reach reap(); the move must carry the tree."""
    planted = _plant_foreign_tree(repo)
    monkeypatch.setattr(fl, "QUARANTINE", repo / "logs" / "foreign-litter-quarantine")
    monkeypatch.setattr(fl, "STAMP", repo / "logs" / "foreign-litter.json")

    dest_root = fl.reap([planted])

    assert not planted.exists(), "reap must move the tree out of the checkout"
    moved = dest_root / planted.name
    assert (moved / "npm" / "lib" / "node_modules" / "@google" / "gemini-cli" / "package.json").is_file(), (
        "quarantine is a reversible MOVE — the whole tree must survive it, not just the top entry"
    )
    assert (repo / "logs" / "foreign-litter.json").is_file(), "organs must stamp — gauges lie"


def test_a_wholly_ignored_tree_is_outside_this_sensors_definition(repo):
    """A documented limit, not a bug: the sensor uses `--exclude-standard`, i.e. git's own notion of
    litter. A foreign tree living entirely under an ignored path is invisible to it. The 2026-08-07
    npm install was catchable only because npm writes `bin/` and `etc/` beside `lib/node_modules/`.
    If this ever needs to change, it is a deliberate widening — not a quiet patch."""
    buried = repo / "vendor-junk" / "node_modules" / "pkg"
    buried.mkdir(parents=True)
    (buried / "index.js").write_text("//\n")
    assert fl.find_root_dirs() == []


def test_git_failure_fails_open(repo, monkeypatch):
    """A broken git can not fabricate litter — the sensor's standing convention."""
    _plant_foreign_tree(repo)
    monkeypatch.setattr(fl, "ROOT", repo / "does-not-exist")
    assert fl.find_root_dirs() == []
