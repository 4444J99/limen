from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "reclaim-worktrees.py"


def load_reclaim_worktrees():
    spec = importlib.util.spec_from_file_location("reclaim_worktrees_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["reclaim_worktrees_under_test"] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def acceptance_event(root: Path, action: str = "remove-worktree", reason: str = "clean+merged+idle") -> dict:
    return {
        "accepted_at": "2026-07-06T06:00:00Z",
        "root": root.name,
        "accepted": True,
        "action": action,
        "reason": reason,
        "archive_status": "not_required_clean_merged_remote",
        "archive_proof": "remote/default preservation verified",
        "redaction_review": "not_required_remote_only",
        "redaction_proof": "clean merged worktree contains no private-only payload",
    }


def test_reclaim_standing_grant_accepts_loss_free_class_without_ledger(tmp_path: Path) -> None:
    # covenant standing grant 2026-07-09: clean+merged+idle needs no per-root ledger event
    reclaim = load_reclaim_worktrees()
    worktree = tmp_path / "example-worktree"
    worktree.mkdir()

    ok, reason = reclaim.reclaim_accepted(worktree, "remove-worktree", "clean+merged+idle", [])

    assert ok is True
    assert reason == "standing-grant-2026-07-09"


def test_reclaim_standing_grant_accepts_remote_receipt_loss_free_class_without_ledger(tmp_path: Path) -> None:
    # covenant standing grant 2026-07-09: receipt-backed merged PRs are also loss-free
    reclaim = load_reclaim_worktrees()
    worktree = tmp_path / "receipt-backed-worktree"
    worktree.mkdir()

    ok, reason = reclaim.reclaim_accepted(
        worktree,
        "remove-worktree",
        "receipt-remote-merged+clean+idle",
        [],
    )

    assert ok is True
    assert reason == "standing-grant-2026-07-09"


def test_debt_classifier_matches_accepted_reaper_for_remote_merged_receipt(tmp_path: Path) -> None:
    reclaim = load_reclaim_worktrees()
    from limen import worktree_debt as debt

    root = tmp_path / "receipt-backed-clone"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "init", "--allow-empty"], cwd=root, check=True)
    receipts = {
        root.name: {
            "root": root.name,
            "lane": "remote-merged",
            "status": "merged_pr_preserved",
            "pr_state": "MERGED",
            "pr_url": "https://github.com/example/repo/pull/7",
        }
    }
    now = time.time()

    action, reaper_reason = reclaim.classify(root, now, 0, receipts)
    debt_reason = debt._classify(root, now, 0, set(), receipts)
    accepted, _accept_reason = reclaim.reclaim_accepted(root, action, reaper_reason, [])

    assert (action, reaper_reason, accepted) == (
        "remove-clone",
        "receipt-remote-merged+clean+idle",
        True,
    )
    assert debt_reason == reaper_reason
    assert debt_reason in debt.REAPABLE_REASONS


def test_reclaim_skips_antigravity_scratch_root_removal(tmp_path: Path) -> None:
    reclaim = load_reclaim_worktrees()
    scratch = tmp_path / "agy-scratch"
    root = scratch / "clean-merged-root"
    root.mkdir(parents=True)
    reclaim.AGY_SCRATCH_ROOT = scratch

    action, reason = reclaim.classify(root, time.time(), 0)

    assert action == "skip"
    assert reason == "antigravity-scratch-uses-bridge-acceptance"


def test_reclaim_remote_reachability_uses_single_contains_query(tmp_path: Path, monkeypatch) -> None:
    reclaim = load_reclaim_worktrees()
    calls: list[list[str]] = []

    def fake_git(args: list[str], cwd: Path, timeout: int = 20) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        assert cwd == tmp_path
        assert timeout == 20
        if args == [
            "for-each-ref",
            "--contains=abc123",
            "--format=%(refname)",
            "refs/remotes",
        ]:
            return subprocess.CompletedProcess(
                ["git", *args],
                0,
                "refs/remotes/origin/main\nrefs/remotes/origin/feature\n",
                "",
            )
        raise AssertionError(f"unexpected git call: {args}")

    monkeypatch.setattr(reclaim, "git", fake_git)

    assert reclaim.reachable_from_remote(tmp_path, "abc123") is True
    assert calls == [
        [
            "for-each-ref",
            "--contains=abc123",
            "--format=%(refname)",
            "refs/remotes",
        ]
    ]


def test_reclaim_help_does_not_discover_targets(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["reclaim-worktrees.py", "--help"])
    reclaim = load_reclaim_worktrees()

    def fail_discovery(_root):
        raise AssertionError("help should not discover worktree targets")

    monkeypatch.setattr(reclaim, "iter_worktree_targets", fail_discovery)

    assert reclaim.main() == 0
    assert "usage: reclaim-worktrees.py" in capsys.readouterr().out


def test_persist_apply_receipt_records_finite_completion_in_log_and_marker(tmp_path: Path, monkeypatch) -> None:
    reclaim = load_reclaim_worktrees()
    marker = tmp_path / "logs" / ".reclaim-last"
    log = tmp_path / "logs" / "reclaim-worktrees.jsonl"
    monkeypatch.setattr(reclaim, "MARKER", marker)
    monkeypatch.setattr(reclaim, "LOG", log)
    monkeypatch.setattr(reclaim.time, "time", lambda: 200.0)

    completed = reclaim.persist_apply_receipt(
        started_ts=100.0,
        dirs=[(tmp_path / "one", 0), (tmp_path / "two", 0)],
        removed=[("one", "remove-worktree:clean+merged+idle")],
        skipped=[("two", "not-merged-to-default")],
        failed=[],
        deferred=[],
        generated_reclaim={"failed": []},
    )

    event = json.loads(log.read_text(encoding="utf-8"))
    assert completed == 200.0
    assert event["ts"] == 100.0
    assert event["completed_ts"] == 200.0
    assert event["apply"] is True
    assert marker.read_text(encoding="utf-8") == "200.0"


def test_reclaim_acceptance_matches_clean_merged_worktree(tmp_path: Path) -> None:
    reclaim = load_reclaim_worktrees()
    reclaim.STANDING_ACCEPTANCE = False  # pin ledger-matching semantics
    worktree = tmp_path / "example-worktree"
    worktree.mkdir()

    ok, reason = reclaim.reclaim_accepted(
        worktree,
        "remove-worktree",
        "clean+merged+idle",
        [acceptance_event(worktree)],
    )

    assert ok is True
    assert reason == "reclaim-accepted"


def test_reclaim_acceptance_requires_archive_and_redaction_proofs(tmp_path: Path) -> None:
    reclaim = load_reclaim_worktrees()
    reclaim.STANDING_ACCEPTANCE = False  # pin ledger-matching semantics
    worktree = tmp_path / "proof-required"
    worktree.mkdir()

    for required_field in reclaim.REQUIRED_ACCEPTANCE_PROOF_FIELDS:
        event = acceptance_event(worktree)
        event.pop(required_field)

        ok, reason = reclaim.reclaim_accepted(
            worktree,
            "remove-worktree",
            "clean+merged+idle",
            [event],
        )

        assert ok is False
        assert reason == "missing-reclaim-acceptance"


def test_reclaim_generated_payloads_cleans_inactive_ignored_dirs(tmp_path: Path, monkeypatch) -> None:
    reclaim = load_reclaim_worktrees()
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    (repo / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    (repo / "README.md").write_text("source\n", encoding="utf-8")
    subprocess.run(["git", "add", ".gitignore", "README.md"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=test", "commit", "-qm", "base"],
        cwd=repo,
        check=True,
    )
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "dep.txt").write_text("generated\n", encoding="utf-8")

    monkeypatch.setattr(reclaim, "active_async_task_prefixes", lambda: set())
    target = type("Target", (), {"path": repo, "min_age_h": 0})()
    result = reclaim.reclaim_generated_payloads([target])

    assert len(result["cleaned"]) == 1
    assert (repo / "README.md").exists()
    assert not (repo / "node_modules").exists()


def test_reclaim_generated_payloads_skips_non_idle_roots(tmp_path: Path, monkeypatch) -> None:
    reclaim = load_reclaim_worktrees()
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    (repo / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    subprocess.run(["git", "add", ".gitignore"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=test", "commit", "-qm", "base"],
        cwd=repo,
        check=True,
    )
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "dep.txt").write_text("generated\n", encoding="utf-8")

    monkeypatch.setattr(reclaim, "active_async_task_prefixes", lambda: set())
    target = type("Target", (), {"path": repo, "min_age_h": 24})()
    result = reclaim.reclaim_generated_payloads([target])

    assert result["cleaned"] == []
    assert (repo / "node_modules").exists()


def test_reclaim_generated_log_shell_dry_run_requires_acceptance(tmp_path: Path, monkeypatch, capsys) -> None:
    reclaim = load_reclaim_worktrees()
    limen_root = tmp_path / "limen"
    (limen_root / "logs").mkdir(parents=True)
    wtroot = tmp_path / ".limen-worktrees"
    shell = wtroot / "generated-log-shell"
    (shell / "logs").mkdir(parents=True)
    (shell / "logs" / "session-lifecycle-pressure.md").write_text("generated\n", encoding="utf-8")
    (shell / "logs" / "session-lifecycle-pressure.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(reclaim, "LIMEN_ROOT", limen_root)
    monkeypatch.setattr(reclaim, "JSON_OUT", True)
    monkeypatch.setattr(reclaim, "APPLY", False)
    monkeypatch.setattr(reclaim, "CHECK", False)
    monkeypatch.setattr(
        reclaim,
        "iter_worktree_targets",
        lambda _root: [type("Target", (), {"path": shell, "min_age_h": 0, "source": "test"})()],
    )

    assert reclaim.main() == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["reapable_count"] == 0
    assert payload["would_reclaim"] == []
    assert payload["kept_safe"] == [{"reason": "missing-reclaim-acceptance", "root": "generated-log-shell"}]


def _committed_repo(tmp_path: Path, name: str = "pushed-unmerged") -> Path:
    """A clean, committed real git repo — valid HEAD, empty status, .git is a dir (⇒ clone, not wt)."""
    repo = tmp_path / name
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    (repo / "f.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=test", "commit", "-qm", "base"],
        cwd=repo,
        check=True,
    )
    return repo


def _model_pushed_unmerged(reclaim, monkeypatch) -> None:
    # HEAD is on a remote ref (preserved/re-cloneable) but NOT merged to default and not patch-equal.
    monkeypatch.setattr(reclaim, "reachable_from_remote", lambda d, head: True)
    monkeypatch.setattr(reclaim, "merged_into_default", lambda d, head: False)
    monkeypatch.setattr(reclaim, "patch_equivalent_to_default", lambda d: False)
    monkeypatch.setattr(reclaim, "receipt_remote_merged", lambda d, r: False)


def test_reclaim_reaps_pushed_unmerged_when_pushed_ok(tmp_path: Path, monkeypatch) -> None:
    # The operator's push-first rule (LIMEN_RECLAIM_PUSHED_OK): a clean, idle, pushed-but-unmerged
    # root is loss-free to remove locally — the branch stays on origin. This drains the dominant
    # not-merged-to-default boot-disk backlog. Standing grant pre-accepts it without a ledger event.
    reclaim = load_reclaim_worktrees()
    repo = _committed_repo(tmp_path)
    monkeypatch.setattr(reclaim, "PUSHED_OK", True)
    _model_pushed_unmerged(reclaim, monkeypatch)

    action, reason = reclaim.classify(repo, time.time(), 0)

    assert action == "remove-clone"  # real git init ⇒ .git is a dir ⇒ not a registered worktree
    assert reason == "clean+pushed+idle"

    ok, grant = reclaim.reclaim_accepted(repo, action, reason, [])
    assert ok is True
    assert grant == "standing-grant-2026-07-09"


def test_reclaim_keeps_pushed_unmerged_when_pushed_ok_off(tmp_path: Path, monkeypatch) -> None:
    # With the push-first rule off, the conservative merged-only gate is restored: a pushed-but-
    # unmerged root is kept, exactly as before. The reversibility guardrail for the standing grant.
    reclaim = load_reclaim_worktrees()
    repo = _committed_repo(tmp_path)
    monkeypatch.setattr(reclaim, "PUSHED_OK", False)
    _model_pushed_unmerged(reclaim, monkeypatch)

    action, reason = reclaim.classify(repo, time.time(), 0)

    assert action == "skip"
    assert reason == "not-merged-to-default"
