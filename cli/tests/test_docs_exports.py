"""check-docs-exports.py — the export program is a shrinking work-list, and every row must be real.

Each test builds a tiny real git repo (the checker judges `git ls-files`, committed truth, never the
dirty working copy), copies the checker in, writes a registry, and asserts the exit code + message
the gate would produce. One test per lettered check, plus the --work listing.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

CHECKER = Path(__file__).resolve().parents[2] / "scripts" / "check-docs-exports.py"


def _git(repo: Path, *args: str) -> None:
    # core.excludesFile is neutralized so the operator's global gitignore can never decide which
    # fixture files get tracked — the checker judges ls-files, so a silently excluded file would
    # flip the B/E verdicts machine-by-machine.
    subprocess.run(
        ["git", "-C", str(repo), "-c", "core.excludesFile=/dev/null", *args],
        check=True,
        capture_output=True,
        text=True,
    )


def make_repo(tmp_path: Path, tracked: list[str], registry: str) -> Path:
    repo = tmp_path / "repo"
    (repo / "institutio" / "governance").mkdir(parents=True)
    (repo / "scripts").mkdir()
    shutil.copy(CHECKER, repo / "scripts" / "check-docs-exports.py")
    for name in tracked:
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fixture\n", encoding="utf-8")
    (repo / "institutio" / "governance" / "docs-exports.yaml").write_text(registry, encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "add", ".")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed")
    return repo


def run_checker(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["python3", str(repo / "scripts" / "check-docs-exports.py"), *args],
        capture_output=True,
        text=True,
    )


def registry(rows: str) -> str:
    return "schema_version: 0.1\n\nexports:\n" + rows


GOOD_ROW = """\
  - path: docs/reviews/estate-thing.md
    target: "organvm/portvs:governance/records/"
    tranche: T3
    leak_risk: none
    patch: []
    why: ""
"""


def test_a_well_formed_registry_is_ok(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, ["docs/reviews/estate-thing.md"], registry(GOOD_ROW))
    result = run_checker(repo)
    assert result.returncode == 0, result.stdout
    assert "1 export rows" in result.stdout


def test_a_duplicate_path_is_a_failure(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, ["docs/reviews/estate-thing.md"], registry(GOOD_ROW + GOOD_ROW))
    result = run_checker(repo)
    assert result.returncode == 1
    assert "[A] duplicate path: docs/reviews/estate-thing.md" in result.stdout


def test_b_a_row_whose_file_already_left_is_a_failure(tmp_path: Path) -> None:
    """The half-done export: portvs received the file, limen deleted it, the row lingered."""
    repo = make_repo(tmp_path, ["docs/keep-me.md"], registry(GOOD_ROW))
    result = run_checker(repo)
    assert result.returncode == 1
    assert "[B] docs/reviews/estate-thing.md" in result.stdout
    assert "retire the row in the shipping commit" in result.stdout


def test_c_a_bare_directory_target_is_not_a_cross_repo_destination(tmp_path: Path) -> None:
    row = GOOD_ROW.replace('"organvm/portvs:governance/records/"', '"governance/records/"')
    repo = make_repo(tmp_path, ["docs/reviews/estate-thing.md"], registry(row))
    result = run_checker(repo)
    assert result.returncode == 1
    assert "[C]" in result.stdout


def test_c_delete_is_a_sanctioned_target(tmp_path: Path) -> None:
    row = GOOD_ROW.replace('"organvm/portvs:governance/records/"', "DELETE")
    repo = make_repo(tmp_path, ["docs/reviews/estate-thing.md"], registry(row))
    assert run_checker(repo).returncode == 0


def test_d_an_unknown_tranche_is_a_failure(tmp_path: Path) -> None:
    row = GOOD_ROW.replace("tranche: T3", "tranche: T9")
    repo = make_repo(tmp_path, ["docs/reviews/estate-thing.md"], registry(row))
    result = run_checker(repo)
    assert result.returncode == 1
    assert "[D]" in result.stdout


def test_e_a_prose_annotation_is_not_a_patch_consumer(tmp_path: Path) -> None:
    """patch is machine-consumable — 'tasks.yaml (2 mentions)' sends the author at no real file."""
    row = GOOD_ROW.replace("patch: []", "patch: [tasks.yaml (2 path mentions)]")
    repo = make_repo(tmp_path, ["docs/reviews/estate-thing.md", "tasks.yaml"], registry(row))
    result = run_checker(repo)
    assert result.returncode == 1
    assert "[E]" in result.stdout
    assert "is not a tracked path" in result.stdout


def test_e_a_real_consumer_path_is_accepted(tmp_path: Path) -> None:
    row = GOOD_ROW.replace("patch: []", "patch: [tasks.yaml]")
    repo = make_repo(tmp_path, ["docs/reviews/estate-thing.md", "tasks.yaml"], registry(row))
    assert run_checker(repo).returncode == 0


def test_work_lists_the_remaining_rows_by_tranche(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, ["docs/reviews/estate-thing.md"], registry(GOOD_ROW))
    result = run_checker(repo, "--work")
    assert result.returncode == 0
    assert "T3 (1):" in result.stdout
    assert "docs/reviews/estate-thing.md" in result.stdout
