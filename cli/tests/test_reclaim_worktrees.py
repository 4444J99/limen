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


def test_reclaim_skips_antigravity_system_generated_worktree(tmp_path: Path) -> None:
    reclaim = load_reclaim_worktrees()
    agy_root = tmp_path / "antigravity-cli"
    root = agy_root / "brain" / "session" / ".system_generated" / "worktrees" / "child"
    root.mkdir(parents=True)
    reclaim.AGY_ROOT = agy_root
    reclaim.AGY_SCRATCH_ROOT = agy_root / "scratch"

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


def test_candidate_manifest_digest_is_order_independent_and_bounded(tmp_path: Path, monkeypatch) -> None:
    reclaim = load_reclaim_worktrees()
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    monkeypatch.setattr(reclaim, "MAX_REMOVE", 1)
    monkeypatch.setattr(
        reclaim,
        "classify",
        lambda path, *_args, **_kwargs: ("remove-clone", f"clean+merged+idle-{path.name}"),
    )
    monkeypatch.setattr(
        reclaim,
        "reclaim_accepted",
        lambda *_args, **_kwargs: (True, "accepted"),
    )

    left = reclaim.build_candidate_manifest(
        [(second, 0, "test"), (first, 0, "test")],
        100.0,
        {},
        [],
    )
    right = reclaim.build_candidate_manifest(
        [(first, 0, "test"), (second, 0, "test")],
        100.0,
        {},
        [],
    )

    assert left == right
    manifest, digest, skipped, deferred = left
    assert len(digest) == 64
    assert [row["root"] for row in manifest["candidates"]] == ["a"]
    assert skipped == []
    assert deferred == ["b"]


def test_apply_requires_matching_plan_digest_before_abandonment(tmp_path: Path, monkeypatch, capsys) -> None:
    reclaim = load_reclaim_worktrees()
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    target = type(
        "Target",
        (),
        {"path": candidate, "min_age_h": 0, "source": "test"},
    )()
    monkeypatch.setattr(reclaim, "APPLY", True)
    monkeypatch.setattr(reclaim, "CHECK", False)
    monkeypatch.setattr(reclaim, "JSON_OUT", True)
    monkeypatch.setattr(reclaim, "FORCE", True)
    monkeypatch.setattr(reclaim, "GENERATED_ONLY", False)
    monkeypatch.setattr(reclaim, "EXPECTED_PLAN_SHA", "")
    monkeypatch.setattr(reclaim, "iter_worktree_targets", lambda _root: [target])
    monkeypatch.setattr(reclaim, "active_process_cwds", lambda: {})
    monkeypatch.setattr(reclaim, "load_preservation_receipts", lambda: {})
    monkeypatch.setattr(reclaim, "load_reclaim_acceptance", lambda: [])
    monkeypatch.setattr(
        reclaim,
        "classify",
        lambda *_args, **_kwargs: ("remove-clone", "clean+merged+idle"),
    )
    monkeypatch.setattr(
        reclaim,
        "quarantine_path",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("digest denial must precede abandonment")),
    )

    assert reclaim.main() == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "APPLY-BLOCKED"
    assert payload["failed"] == [{"reason": "expected-plan-sha-required", "root": "plan"}]
    assert len(payload["plan_sha256"]) == 64
    assert candidate.exists()


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
    quarantine = tmp_path / "quarantine"

    monkeypatch.setattr(reclaim, "active_async_task_prefixes", lambda: set())
    monkeypatch.setattr(reclaim, "ABANDONMENT_QUARANTINE", str(quarantine))
    monkeypatch.setattr(reclaim, "ABANDONMENT_RECEIPTS", tmp_path / "receipts")
    target = type("Target", (), {"path": repo, "min_age_h": 0})()
    result = reclaim.reclaim_generated_payloads([target])

    assert len(result["cleaned"]) == 1
    assert (repo / "README.md").exists()
    assert not (repo / "node_modules").exists()
    preserved = list(quarantine.glob("generated-repo-node_modules-*"))
    assert len(preserved) == 1
    assert (preserved[0] / "dep.txt").read_text(encoding="utf-8") == "generated\n"
    receipt = next((tmp_path / "receipts").glob("*.json"))
    assert json.loads(receipt.read_text(encoding="utf-8"))["state"] == "completed"


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


def test_reclaim_generated_payloads_preserves_tracked_generated_name(
    tmp_path: Path,
    monkeypatch,
) -> None:
    reclaim = load_reclaim_worktrees()
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    (repo / "dist").mkdir()
    (repo / "dist" / "bundle.js").write_text("tracked\n", encoding="utf-8")
    subprocess.run(["git", "add", "dist/bundle.js"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=test", "commit", "-qm", "base"],
        cwd=repo,
        check=True,
    )

    monkeypatch.setattr(reclaim, "active_async_task_prefixes", lambda: set())
    monkeypatch.setattr(reclaim, "ABANDONMENT_QUARANTINE", str(tmp_path / "quarantine"))
    target = type("Target", (), {"path": repo, "min_age_h": 0})()
    result = reclaim.reclaim_generated_payloads([target])

    assert result["cleaned"] == [{"root": "repo", "detail": "quarantined:0"}]
    assert (repo / "dist" / "bundle.js").read_text(encoding="utf-8") == "tracked\n"
    assert not (tmp_path / "quarantine").exists()


def test_reclaim_root_apply_does_not_run_generated_cleanup(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    reclaim = load_reclaim_worktrees()
    repo = tmp_path / "repo"
    repo.mkdir()
    limen_root = tmp_path / "limen"
    (limen_root / "logs").mkdir(parents=True)
    target = type("Target", (), {"path": repo, "min_age_h": 0, "source": "test"})()

    monkeypatch.setattr(reclaim, "LIMEN_ROOT", limen_root)
    monkeypatch.setattr(reclaim, "MARKER", tmp_path / "last-run")
    monkeypatch.setattr(reclaim, "LOG", tmp_path / "reclaim.jsonl")
    monkeypatch.setattr(reclaim, "APPLY", True)
    monkeypatch.setattr(reclaim, "FORCE", True)
    monkeypatch.setattr(reclaim, "JSON_OUT", True)
    monkeypatch.setattr(reclaim, "CHECK", False)
    monkeypatch.setattr(reclaim, "GENERATED_ONLY", False)
    monkeypatch.setattr(reclaim, "iter_worktree_targets", lambda _root: [target])
    monkeypatch.setattr(reclaim, "active_process_cwds", lambda: {})
    monkeypatch.setattr(
        reclaim,
        "reclaim_generated_payloads",
        lambda _targets: (_ for _ in ()).throw(AssertionError("root apply must not clean generated payloads")),
    )
    monkeypatch.setattr(reclaim, "load_preservation_receipts", lambda: {})
    monkeypatch.setattr(reclaim, "load_reclaim_acceptance", lambda: [])
    monkeypatch.setattr(reclaim, "classify", lambda *_args, **_kwargs: ("skip", "dirty"))
    plan_sha = reclaim.build_candidate_manifest([(repo, 0, "test")], 0.0, {}, [])[1]
    monkeypatch.setattr(reclaim, "EXPECTED_PLAN_SHA", plan_sha)

    assert reclaim.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["reclaimed"] == []
    assert payload["failed"] == []
    assert payload["generated_reclaim"] == {"enabled": False, "cleaned": [], "failed": []}
    assert payload["kept_safe"] == [{"root": "repo", "reason": "dirty"}]
    assert repo.exists()


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


def test_reclaim_defaults_to_pushed_remote_custody(monkeypatch) -> None:
    monkeypatch.delenv("LIMEN_RECLAIM_PUSHED_OK", raising=False)
    reclaim = load_reclaim_worktrees()

    assert reclaim.PUSHED_OK is True


def test_reclaim_keeps_root_owned_by_live_process(tmp_path: Path, monkeypatch) -> None:
    reclaim = load_reclaim_worktrees()
    repo = _committed_repo(tmp_path, "live-process-root")
    nested_cwd = repo / "src"
    nested_cwd.mkdir()
    monkeypatch.setattr(reclaim, "_ACTIVE_PROCESS_CWDS", {nested_cwd.resolve(): 4242})

    action, reason = reclaim.classify(repo, time.time(), 0)

    assert action == "skip"
    assert reason == "active-process-cwd:4242"


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


# ── dead-gitdir orphan sweep (prune-race debris) ──────────────────────────────────────────────
def _dead_gitdir_orphan(tmp_path: Path, name: str = "agy-conversation-adapter-0713") -> Path:
    """A checkout whose .git pointer targets a gitdir that no longer exists (prune-race orphan)."""
    d = tmp_path / name
    d.mkdir()
    (d / "src.py").write_text("work\n", encoding="utf-8")  # real content ⇒ not a generated-log-shell
    (d / ".git").write_text(f"gitdir: /nonexistent/.git/worktrees/{name}\n", encoding="utf-8")
    return d


def test_orphan_detector_finds_dead_gitdir_and_ignores_live(tmp_path: Path) -> None:
    reclaim = load_reclaim_worktrees()
    assert reclaim.orphan_gitdir_name(_dead_gitdir_orphan(tmp_path, "wt-name")) == "wt-name"
    # a pointer to a gitdir that DOES exist is a registered worktree, not an orphan
    live = tmp_path / "live"
    live.mkdir()
    gd = tmp_path / "realgitdir"
    gd.mkdir()
    (live / ".git").write_text(f"gitdir: {gd}\n", encoding="utf-8")
    assert reclaim.orphan_gitdir_name(live) is None


def test_reclaim_quarantines_dead_gitdir_orphan_under_throwaway_when_armed(tmp_path: Path, monkeypatch) -> None:
    reclaim = load_reclaim_worktrees()
    monkeypatch.setattr(reclaim, "ORPHAN_SWEEP", True)
    orphan = _dead_gitdir_orphan(tmp_path)
    action, reason = reclaim.classify(orphan, time.time(), 0, source="dispatch-root")
    assert (action, reason) == ("quarantine-orphan", reclaim.ORPHAN_REASON)


def test_quarantine_orphan_moves_and_never_deletes(tmp_path: Path, monkeypatch) -> None:
    # LOAD-BEARING: an orphan is PRESERVED by move, never destroyed — the fix for "could this delete
    # work that never walked its lifecycle". After the sweep the source is gone but every byte, walked
    # or not, survives in quarantine, and a receipt records where it went.
    reclaim = load_reclaim_worktrees()
    qroot = tmp_path / "quarantine"
    monkeypatch.setattr(reclaim, "ORPHAN_QUARANTINE", str(qroot))
    monkeypatch.setattr(reclaim, "ORPHAN_QUARANTINE_LOG", tmp_path / "orphan-quarantine.jsonl")
    orphan = _dead_gitdir_orphan(tmp_path, "wt-unwalked")
    (orphan / "uncommitted.txt").write_text("work that was never pushed\n", encoding="utf-8")

    ok, dest = reclaim.quarantine_orphan(orphan, "20260715T000000Z")

    assert ok is True
    assert not orphan.exists()  # removed from the worktree root (debt resolved)
    moved = Path(dest)
    assert moved.exists()  # but PRESERVED — nothing deleted
    assert (moved / "uncommitted.txt").read_text(encoding="utf-8") == "work that was never pushed\n"
    assert (moved / "src.py").exists()
    receipt = json.loads((tmp_path / "orphan-quarantine.jsonl").read_text(encoding="utf-8").strip())
    assert receipt["recoverable"] == "moved-not-deleted" and receipt["to"] == dest


def test_quarantine_orphan_refuses_when_destination_unwritable(tmp_path: Path, monkeypatch) -> None:
    # Fail-closed: if quarantine can't be prepared, the orphan is LEFT in place, never half-removed.
    reclaim = load_reclaim_worktrees()
    monkeypatch.setattr(reclaim, "ORPHAN_QUARANTINE", str(tmp_path / "afile" / "under"))
    (tmp_path / "afile").write_text("not a dir\n", encoding="utf-8")  # mkdir under a file → OSError
    orphan = _dead_gitdir_orphan(tmp_path, "wt-keep")
    ok, reason = reclaim.quarantine_orphan(orphan, "20260715T000000Z")
    assert ok is False
    assert orphan.exists()  # untouched


def test_reclaim_skips_orphan_when_sweep_disarmed(tmp_path: Path, monkeypatch) -> None:
    # DEFAULT posture: unarmed, a dead-gitdir orphan is conservatively kept as not-a-git-dir.
    reclaim = load_reclaim_worktrees()
    monkeypatch.setattr(reclaim, "ORPHAN_SWEEP", False)
    orphan = _dead_gitdir_orphan(tmp_path)
    assert reclaim.classify(orphan, time.time(), 0, source="dispatch-root") == ("skip", "not-a-git-dir")


def test_reclaim_skips_orphan_under_interactive_source_even_when_armed(tmp_path: Path, monkeypatch) -> None:
    # SAFETY: only THROWAWAY roots are orphan-eligible; interactive/registered cells are never reaped.
    reclaim = load_reclaim_worktrees()
    monkeypatch.setattr(reclaim, "ORPHAN_SWEEP", True)
    orphan = _dead_gitdir_orphan(tmp_path)
    assert reclaim.classify(orphan, time.time(), 0, source="claude-worktrees") == ("skip", "not-a-git-dir")


def test_reclaim_keeps_orphan_active_under_min_age(tmp_path: Path, monkeypatch) -> None:
    # A fresh orphan (age < min-age) could still be mid-run debris — keep it until idle.
    reclaim = load_reclaim_worktrees()
    monkeypatch.setattr(reclaim, "ORPHAN_SWEEP", True)
    orphan = _dead_gitdir_orphan(tmp_path)
    action, reason = reclaim.classify(orphan, time.time(), 100, source="dispatch-root")
    assert action == "skip"
    assert reason.startswith("orphan-active")
