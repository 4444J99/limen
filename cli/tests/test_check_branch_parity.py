"""Tests for scripts/check-branch-parity.py — one positive and one deliberately broken input per defect.

The four defects (D1-D4) and the vacuum rule are the reasons the 2026-10-18 parity audit reported
"complete parity" over 70 deleted branches. A negative that is not exercised proves nothing about a
predicate that is built to be quiet, so every rule below has a case that must fail LOUDLY.
"""

import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-branch-parity.py"
REAL_RECEIPTS = ROOT / "docs" / "receipts" / "session-closeout-parity-t2-deletion-correction-20261018"

spec = importlib.util.spec_from_file_location("check_branch_parity_under_test", SCRIPT)
M = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = M  # @dataclass resolves string annotations through sys.modules[cls.__module__]
spec.loader.exec_module(M)

GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], env=GIT_ENV, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def commit(repo: Path, name: str, text: str = "x\n") -> str:
    (repo / name).write_text(text)
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", f"add {name}")
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A clone whose ``origin`` is a real bare repo, with ``main`` pushed so refs/remotes/origin/main exists."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True, env=GIT_ENV)
    work = tmp_path / "work"
    subprocess.run(["git", "init", "-q", "-b", "main", str(work)], check=True, env=GIT_ENV)
    commit(work, "seed")
    git(work, "remote", "add", "origin", str(remote))
    git(work, "push", "-q", "-u", "origin", "main")
    return work


# ── D1: existence is not preservation ───────────────────────────────────────────────────────────────────


def test_branch_inside_origin_main_is_contained(repo: Path) -> None:
    git(repo, "branch", "landed")
    got = M.classify(repo, "landed", pull_heads=set())
    assert got.verdict == "CONTAINED"
    assert re.fullmatch(r"[0-9a-f]{40}", got.tip)


def test_branch_inside_a_non_main_remote_ref_is_contained(repo: Path) -> None:
    git(repo, "switch", "-q", "-c", "side")
    commit(repo, "side.txt")
    git(repo, "push", "-q", "origin", "side")
    git(repo, "fetch", "-q", "origin")
    git(repo, "switch", "-q", "main")
    git(repo, "branch", "-q", "-m", "side", "side-local")  # local name differs; the tip is on origin/side
    assert M.classify(repo, "side-local", pull_heads=set()).verdict == "CONTAINED"


def test_self_upstream_is_not_evidence(repo: Path) -> None:
    git(repo, "switch", "-q", "-c", "lonely")
    commit(repo, "lonely.txt")
    git(repo, "config", "branch.lonely.remote", ".")
    git(repo, "config", "branch.lonely.merge", "refs/heads/lonely")
    got = M.classify(repo, "lonely", pull_heads=set())
    assert got.verdict == "UNPRESERVED"  # the old predicate would have called it preserved
    assert got.self_upstream is True


def test_not_contained_without_the_pr_probe_is_unmeasured_not_unpreserved(repo: Path) -> None:
    git(repo, "switch", "-q", "-c", "lonely")
    commit(repo, "lonely.txt")
    assert M.classify(repo, "lonely", pull_heads=None).verdict == "UNMEASURED"


def test_tip_advertised_as_a_pr_head_is_preserved(repo: Path) -> None:
    git(repo, "switch", "-q", "-c", "pr")
    tip = commit(repo, "pr.txt")
    assert M.classify(repo, "pr", pull_heads={tip}).verdict == "PR_HEAD"


# ── D2: silence is not equivalence ──────────────────────────────────────────────────────────────────────


def test_squash_equivalent_patch_is_recognised_with_a_checked_exit_status(repo: Path) -> None:
    git(repo, "switch", "-q", "-c", "feature")
    tip = commit(repo, "f.txt", "feature\n")
    git(repo, "switch", "-q", "main")
    commit(repo, "moved.txt")  # main advances, so the cherry-pick below cannot reproduce the same commit id
    git(repo, "cherry-pick", tip)  # same patch, new commit id: what a squash-merge leaves behind
    git(repo, "push", "-q", "origin", "main")
    got = M.classify(repo, "feature", pull_heads=set())
    assert got.tip != git(repo, "rev-parse", "main")
    assert got.verdict == "PATCH_EQUIVALENT"


def test_missing_base_ref_is_an_error_never_zero_unlanded(repo: Path) -> None:
    git(repo, "switch", "-q", "-c", "feature")
    commit(repo, "f.txt")
    got = M.classify(repo, "feature", pull_heads=set(), base_ref="refs/remotes/origin/does-not-exist")
    assert got.verdict == "ERROR"  # `git cherry` / merge-base exit nonzero on a missing ref


def test_unresolvable_branch_is_an_error(repo: Path) -> None:
    assert M.classify(repo, "no-such-branch", pull_heads=set()).verdict == "ERROR"


def test_not_a_repository_is_an_error(tmp_path: Path) -> None:
    assert M.classify(tmp_path, "main", pull_heads=set()).verdict == "ERROR"


def test_the_forbidden_silent_pipeline_shape_is_absent_from_the_source() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert not re.search(r"cherry[^\n]*\|\s*grep", source)
    assert "|| true" not in source


# ── D3: full identity only ──────────────────────────────────────────────────────────────────────────────


def _receipts(tmp_path: Path) -> Path:
    dest = tmp_path / "receipts"
    shutil.copytree(REAL_RECEIPTS, dest)
    return dest


def test_the_real_receipts_validate() -> None:
    assert M.main(["--ledgers"]) == 0


def test_a_ten_char_oid_in_a_ledger_fails_on_the_oid_rule_itself(tmp_path: Path, capsys) -> None:
    receipts = _receipts(tmp_path)
    path = receipts / "recovery-ledger.tsv"
    restored = {line.split("\t")[0] for line in (receipts / "restored-branches.tsv").read_text().splitlines()}
    lines = path.read_text().splitlines()
    # Truncate a row the restored ledger does NOT repeat, so the only rule that can object is D3's.
    index = next(i for i, line in enumerate(lines[1:], start=1) if line.split("\t")[0] not in restored)
    cols = lines[index].split("\t")
    cols[1] = cols[1][:10]
    lines[index] = "\t".join(cols)
    path.write_text("\n".join(lines) + "\n")
    assert M.main(["--ledgers", "--receipt-dir", str(receipts)]) == 1
    out = capsys.readouterr().out
    assert "not a full 40-hex" in out
    assert "identical row" not in out  # the restored-subset rule did not fire, so D3 carried the failure alone


def test_a_restored_row_must_be_an_identical_ledger_row(tmp_path: Path) -> None:
    receipts = _receipts(tmp_path)
    path = receipts / "restored-branches.tsv"
    lines = path.read_text().splitlines()
    cols = lines[0].split("\t")
    cols[1] = "0" * 40  # a well-formed OID that is not the ledger's
    lines[0] = "\t".join(cols)
    path.write_text("\n".join(lines) + "\n")
    assert M.main(["--ledgers", "--receipt-dir", str(receipts)]) == 1


def test_evidence_digest_mismatch_on_a_present_file_fails(tmp_path: Path, monkeypatch) -> None:
    receipts = _receipts(tmp_path)
    present = tmp_path / "present.bin"
    present.write_bytes(b"real bytes")
    (receipts / "evidence-sha256.txt").write_text(f"{'0' * 64}  present.bin\n")
    monkeypatch.setattr(M, "ROOT", tmp_path)
    assert M.main(["--ledgers", "--receipt-dir", str(receipts)]) == 1


# ── vacuum: reading nothing is not clean ────────────────────────────────────────────────────────────────


def test_a_truncated_ledger_fails_on_the_row_count_rule_itself(tmp_path: Path, capsys) -> None:
    receipts = _receipts(tmp_path)
    path = receipts / "recovery-ledger.tsv"
    path.write_text("\n".join(path.read_text().splitlines()[:10]) + "\n")
    assert M.main(["--ledgers", "--receipt-dir", str(receipts)]) == 1
    assert f"expected exactly {M.EXPECTED_RECOVERY}" in capsys.readouterr().out


def test_a_missing_receipt_directory_fails(tmp_path: Path) -> None:
    assert M.main(["--ledgers", "--receipt-dir", str(tmp_path / "nope")]) == 1


def test_live_on_a_repo_with_no_remote_refs_is_unmeasured(tmp_path: Path, capsys) -> None:
    empty = tmp_path / "empty"
    subprocess.run(["git", "init", "-q", "-b", "main", str(empty)], check=True, env=GIT_ENV)
    commit(empty, "seed")
    assert M.main(["--live", "--repo", str(empty), "--receipt-dir", str(REAL_RECEIPTS)]) == 2
    assert "no usable remote-tracking refs" in capsys.readouterr().out


# ── D4: state is re-read at the moment of use ───────────────────────────────────────────────────────────


def test_classify_holds_no_snapshot(repo: Path) -> None:
    git(repo, "branch", "landed")
    assert M.classify(repo, "landed", pull_heads=set()).verdict == "CONTAINED"
    git(repo, "branch", "-q", "-D", "landed")  # a concurrent lane removes it between two calls
    assert M.classify(repo, "landed", pull_heads=set()).verdict == "ERROR"


# ── restored refs, measured live ────────────────────────────────────────────────────────────────────────


def _row(branch: str, oid: str) -> list[str]:
    return [branch, oid, "refs/pull/1/head", "1", "MERGED", "yes", "post-D3"]


def test_restored_branch_at_its_recorded_oid_is_ok(repo: Path) -> None:
    git(repo, "switch", "-q", "-c", "keep")
    tip = commit(repo, "k.txt")
    report = M.Report()
    M.check_restored_live(repo, [_row("keep", tip)], set(), report)
    assert report.code == 0
    assert "at recorded OID 1" in report.lines[-1]


def test_restored_branch_that_advanced_is_not_drift(repo: Path) -> None:
    git(repo, "switch", "-q", "-c", "keep")
    recorded = commit(repo, "k.txt")
    commit(repo, "k2.txt")
    report = M.Report()
    M.check_restored_live(repo, [_row("keep", recorded)], set(), report)
    assert report.code == 0
    assert "advanced 1" in report.lines[-1]


def test_restored_branch_rewritten_away_from_its_oid_is_drift(repo: Path) -> None:
    git(repo, "switch", "-q", "-c", "keep")
    recorded = commit(repo, "k.txt")
    git(repo, "reset", "-q", "--hard", "main")
    commit(repo, "other.txt")  # same name, history no longer contains the recorded commit
    report = M.Report()
    M.check_restored_live(repo, [_row("keep", recorded)], set(), report)
    assert report.code == 1
    assert any(line.startswith("DRIFTED") for line in report.lines)


def test_restored_branch_gone_and_nowhere_remote_is_missing(repo: Path) -> None:
    git(repo, "switch", "-q", "-c", "keep")
    recorded = commit(repo, "k.txt")
    git(repo, "switch", "-q", "main")
    git(repo, "branch", "-q", "-D", "keep")
    report = M.Report()
    M.check_restored_live(repo, [_row("keep", recorded)], set(), report)
    assert report.code == 1
    assert any(line.startswith("MISSING") for line in report.lines)
