"""check-root-manifest.py — the root is a curated surface, not a landing strip.

Each test builds a tiny real git repo (the checker judges `git ls-tree HEAD`, committed truth,
never the dirty working copy), copies the checker in, writes a manifest, and asserts the exit
code + message the gate would produce. One test per lettered check, plus the --fat listing.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

CHECKER = Path(__file__).resolve().parents[2] / "scripts" / "check-root-manifest.py"


def _git(repo: Path, *args: str) -> None:
    # core.excludesFile is neutralized so the operator's global gitignore (e.g. *.log) can never
    # decide which fixture files get committed — the checker judges ls-tree, so a silently
    # excluded file would flip B/C verdicts machine-by-machine.
    subprocess.run(
        ["git", "-C", str(repo), "-c", "core.excludesFile=/dev/null", *args],
        check=True,
        capture_output=True,
        text=True,
    )


def make_repo(tmp_path: Path, tracked: dict[str, str], manifest: str) -> Path:
    repo = tmp_path / "repo"
    (repo / "institutio" / "governance").mkdir(parents=True)
    (repo / "scripts").mkdir()
    shutil.copy(CHECKER, repo / "scripts" / "check-root-manifest.py")
    for name, body in tracked.items():
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    (repo / "institutio" / "governance" / "root-manifest.yaml").write_text(manifest, encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "add", ".")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed")
    return repo


def run_checker(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["python3", str(repo / "scripts" / "check-root-manifest.py"), *args],
        capture_output=True,
        text=True,
    )


BASE_ROWS = """\
schema_version: 0.1
sanctioned:
  - {path: institutio, kind: dir, owner: governance, why: registries}
  - {path: scripts, kind: dir, owner: fleet, why: operational scripts}
  - {path: README.md, kind: doc, owner: docs, why: front door}
"""


def test_exact_parity_is_ok_and_counts_the_fat(tmp_path):
    manifest = (
        BASE_ROWS
        + """\
grandfathered:
  - {path: error.log, target_home: logs/, why: stray runtime output}
"""
    )
    repo = make_repo(tmp_path, {"README.md": "hi", "error.log": "boom"}, manifest)
    proc = run_checker(repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "3 sanctioned" in proc.stdout
    assert "1 grandfathered" in proc.stdout


def test_undeclared_root_entry_is_named_fat(tmp_path):
    repo = make_repo(tmp_path, {"README.md": "hi", "surprise.json": "{}"}, BASE_ROWS)
    proc = run_checker(repo)
    assert proc.returncode == 1
    assert "[B] undeclared root entry (fat): surprise.json" in proc.stdout


def test_a_rehomed_entry_must_take_its_row_with_it(tmp_path):
    manifest = (
        BASE_ROWS
        + """\
grandfathered:
  - {path: gone.txt, target_home: docs/, why: already rehomed}
"""
    )
    repo = make_repo(tmp_path, {"README.md": "hi"}, manifest)
    proc = run_checker(repo)
    assert proc.returncode == 1
    assert "[C] gone.txt" in proc.stdout
    assert "deleting the row IS the receipt" in proc.stdout


def test_a_path_cannot_sit_in_both_blocks(tmp_path):
    manifest = (
        BASE_ROWS
        + """\
grandfathered:
  - {path: README.md, target_home: docs/, why: contradiction}
"""
    )
    repo = make_repo(tmp_path, {"README.md": "hi"}, manifest)
    proc = run_checker(repo)
    assert proc.returncode == 1
    assert "[A] README.md: appears in both sanctioned and grandfathered" in proc.stdout


def test_target_home_must_leave_the_root(tmp_path):
    manifest = (
        BASE_ROWS
        + """\
grandfathered:
  - {path: error.log, target_home: elsewhere, why: vague}
"""
    )
    repo = make_repo(tmp_path, {"README.md": "hi", "error.log": "boom"}, manifest)
    proc = run_checker(repo)
    assert proc.returncode == 1
    assert "[D] error.log" in proc.stdout


def test_cross_repo_target_home_is_a_sanctioned_disposition(tmp_path):
    manifest = (
        BASE_ROWS
        + """\
grandfathered:
  - {path: error.log, target_home: "organvm/portvs:governance/records/", why: subject lives in the governance graph}
"""
    )
    repo = make_repo(tmp_path, {"README.md": "hi", "error.log": "boom"}, manifest)
    proc = run_checker(repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_delete_is_a_sanctioned_disposition(tmp_path):
    manifest = (
        BASE_ROWS
        + """\
grandfathered:
  - {path: error.log, target_home: DELETE, why: accidental commit — git history is the archive}
"""
    )
    repo = make_repo(tmp_path, {"README.md": "hi", "error.log": "boom"}, manifest)
    proc = run_checker(repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.parametrize("kind", ["mystery", ""])
def test_sanctioned_kind_is_a_closed_enum(tmp_path, kind):
    manifest = f"""\
schema_version: 0.1
sanctioned:
  - {{path: README.md, kind: '{kind}', owner: docs, why: front door}}
  - {{path: institutio, kind: dir, owner: governance, why: registries}}
  - {{path: scripts, kind: dir, owner: fleet, why: operational scripts}}
"""
    repo = make_repo(tmp_path, {"README.md": "hi"}, manifest)
    proc = run_checker(repo)
    assert proc.returncode == 1
    assert "[A]" in proc.stdout


def test_fat_listing_is_the_remaining_work(tmp_path):
    manifest = (
        BASE_ROWS
        + """\
grandfathered:
  - {path: error.log, target_home: logs/, why: stray runtime output}
  - {path: old_audit.json, target_home: docs/audits/, why: one-off audit data}
"""
    )
    repo = make_repo(tmp_path, {"README.md": "hi", "error.log": "boom", "old_audit.json": "{}"}, manifest)
    proc = run_checker(repo, "--fat")
    assert proc.returncode == 0
    assert "error.log  →  logs/" in proc.stdout
    assert "old_audit.json  →  docs/audits/" in proc.stdout
    assert "2 grandfathered row(s) remaining" in proc.stdout


DOCS_MANIFEST = """\
schema_version: 0.1
sanctioned:
  - {path: plans, kind: dir, owner: docs, why: dated plans}
  - {path: pinned-ledger.md, kind: doc, owner: fleet, why: consumed at this path by scripts/x.py}
"""


def make_docs_repo(tmp_path: Path, docs_files: dict[str, str], manifest: str) -> Path:
    tracked = {f"docs/{name}": body for name, body in docs_files.items()}
    tracked["README.md"] = "hi"
    repo = make_repo(tmp_path, tracked, BASE_ROWS + "  - {path: docs, kind: dir, owner: docs, why: docs tree}\n")
    (repo / "institutio" / "governance" / "docs-manifest.yaml").write_text(manifest, encoding="utf-8")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "add", "institutio/governance/docs-manifest.yaml")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "docs manifest")
    return repo


def test_docs_surface_exact_parity_is_ok(tmp_path):
    repo = make_docs_repo(tmp_path, {"plans/p.md": "plan", "pinned-ledger.md": "ledger"}, DOCS_MANIFEST)
    proc = run_checker(repo, "--surface", "docs")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "2 sanctioned" in proc.stdout


def test_docs_surface_names_a_loose_file_as_fat(tmp_path):
    repo = make_docs_repo(tmp_path, {"plans/p.md": "plan", "pinned-ledger.md": "l", "stray.md": "s"}, DOCS_MANIFEST)
    proc = run_checker(repo, "--surface", "docs")
    assert proc.returncode == 1
    assert "[B] undeclared docs/ entry (fat): stray.md" in proc.stdout


def test_docs_surface_rehomed_file_takes_its_row(tmp_path):
    manifest = (
        DOCS_MANIFEST
        + """\
grandfathered:
  - {path: already-moved.md, target_home: docs/reviews/, why: rehomed last PR}
"""
    )
    repo = make_docs_repo(tmp_path, {"plans/p.md": "plan", "pinned-ledger.md": "l"}, manifest)
    proc = run_checker(repo, "--surface", "docs")
    assert proc.returncode == 1
    assert "[C] already-moved.md" in proc.stdout
    assert "deleting the row IS the receipt" in proc.stdout
