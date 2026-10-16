from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "merge-drain.py"


def _load():
    spec = importlib.util.spec_from_file_location("merge_drain_uut", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _R:
    def __init__(self, out: str, returncode: int = 0):
        self.returncode = returncode
        self.stdout = out
        self.stderr = ""


def test_conflict_wins_over_stale_failing_checks(monkeypatch):
    mod = _load()

    def fake_gh(args, timeout=60):
        if args[:2] == ["pr", "view"]:
            return _R(
                json.dumps(
                    {
                        "state": "OPEN",
                        "isDraft": False,
                        "labels": [{"name": "lifecycle:delivery"}],
                        "mergeable": "CONFLICTING",
                        "statusCheckRollup": [{"conclusion": "FAILURE"}],
                    }
                )
            )
        raise AssertionError(f"unexpected gh call: {args!r}")

    monkeypatch.setattr(mod, "gh", fake_gh)

    assert mod.assess(("organvm/domus-genoma", 185)) == (
        "organvm/domus-genoma",
        185,
        "CONFLICT",
    )


def _stale_view():
    return {
        "state": "OPEN",
        "isDraft": False,
        "labels": [{"name": "lifecycle:delivery"}],
        "mergeable": "MERGEABLE",
        "statusCheckRollup": [{"conclusion": "SUCCESS"}],
        "files": [{"path": "cli/src/limen/dispatch.py"}],
        "baseRefName": "main",
        "headRefOid": "deadbeefcafe",
    }


def test_green_preservation_and_unknown_prs_never_reach_merge_assessment(monkeypatch):
    for labels, expected in (
        ([{"name": "lifecycle:preservation"}], "PRESERVATION"),
        ([{"name": "lifecycle:active-human"}], "ACTIVE-HUMAN"),
        ([], "LIFECYCLE-UNKNOWN"),
        (
            [{"name": "lifecycle:delivery"}, {"name": "lifecycle:preservation"}],
            "LIFECYCLE-UNKNOWN",
        ),
    ):
        mod = _load()

        def fake_gh(args, timeout=60, selected=labels):
            if args[:2] == ["pr", "view"]:
                return _R(json.dumps(_stale_view() | {"labels": selected}))
            raise AssertionError(f"non-delivery PR reached another GitHub probe: {args!r}")

        monkeypatch.setattr(mod, "gh", fake_gh)

        assert mod.assess(("organvm/limen", 99)) == ("organvm/limen", 99, expected)


def test_stale_pr_is_ready_only_with_positive_active_queue(monkeypatch):
    mod = _load()

    def fake_gh(args, timeout=60):
        if args[:2] == ["pr", "view"]:
            return _R(json.dumps(_stale_view()))
        if args and args[0] == "api" and "graphql" not in args:
            return _R("5")
        if args[:2] == ["pr", "diff"]:
            return _R("diff --git a/x b/x\n--- a/x\n+++ b/x\n-old\n+new\n")
        raise AssertionError(f"unexpected gh call: {args!r}")

    monkeypatch.setattr(mod, "gh", fake_gh)
    monkeypatch.setattr(mod, "merge_queue_capability", lambda repo, branch, gh_fn: "active")

    assert mod.assess(("organvm/limen", 1194)) == (
        "organvm/limen",
        1194,
        "READY",
        "deadbeefcafe",
        "queue",
    )


def test_stale_pr_keeps_guard_when_queue_absent_or_unknown(monkeypatch):
    for capability in ("absent", "unknown"):
        mod = _load()

        def fake_gh(args, timeout=60):
            if args[:2] == ["pr", "view"]:
                return _R(json.dumps(_stale_view()))
            if args and args[0] == "api":
                return _R("5")
            raise AssertionError(f"unexpected gh call: {args!r}")

        monkeypatch.setattr(mod, "gh", fake_gh)
        monkeypatch.setattr(mod, "merge_queue_capability", lambda repo, branch, gh_fn, c=capability: c)

        assert mod.assess(("organvm/limen", 1194)) == (
            "organvm/limen",
            1194,
            "STALE-CORE",
        )


def test_queue_enqueue_is_exact_head_method_free_and_not_merged(monkeypatch):
    mod = _load()
    calls = []
    policy = []
    monkeypatch.setattr(
        mod,
        "_queue_state",
        lambda repo, num: {"state": "OPEN", "head": "deadbeefcafe", "queued": False},
    )
    monkeypatch.setattr(
        mod,
        "_merge_policy",
        lambda repo, num, head: policy.append((repo, num, head)) or "queue",
    )

    def fake_gh(args, timeout=60):
        calls.append(args)
        return _R("")

    monkeypatch.setattr(mod, "gh", fake_gh)

    assert mod.merge("organvm/limen", 1194, "deadbeefcafe", "queue") == "QUEUED"
    assert policy == [("organvm/limen", 1194, "deadbeefcafe")]
    assert calls == [
        [
            "pr",
            "merge",
            "1194",
            "-R",
            "organvm/limen",
            "--auto",
            "--match-head-commit",
            "deadbeefcafe",
        ]
    ]
    assert not {"--squash", "--merge", "--rebase", "--admin"} & set(calls[0])


def test_policy_recheck_is_exact_head_bound(monkeypatch):
    mod = _load()
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout="VERDICT: CLEARED — queueable\nMERGE-MODE: queue\nMERGE-HEAD: deadbeefcafe (exact)\n",
            stderr="",
        )

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    assert mod._merge_policy("organvm/limen", 1194, "deadbeefcafe") == "queue"
    assert calls[0][0] == [
        "bash",
        str(mod.POLICY),
        "1194",
        "--repo",
        "organvm/limen",
        "--expected-head",
        "deadbeefcafe",
    ]
    assert calls[0][1]["check"] is False


def test_policy_recheck_rejects_different_reported_head(monkeypatch):
    mod = _load()
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="VERDICT: CLEARED\nMERGE-MODE: direct\nMERGE-HEAD: changedhead\n",
            stderr="",
        ),
    )

    assert mod._merge_policy("organvm/limen", 1194, "deadbeefcafe") is None


def test_queue_enqueue_is_idempotent_without_policy_or_effect(monkeypatch):
    mod = _load()
    monkeypatch.setattr(
        mod,
        "_queue_state",
        lambda repo, num: {"state": "OPEN", "head": "deadbeefcafe", "queued": True},
    )
    monkeypatch.setattr(
        mod,
        "_merge_policy",
        lambda *args: (_ for _ in ()).throw(AssertionError("already queued must not reassess/effect")),
    )
    monkeypatch.setattr(
        mod,
        "gh",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("already queued must not enqueue again")),
    )

    assert mod.merge("organvm/limen", 1194, "deadbeefcafe", "queue") == "QUEUED"


def test_direct_merge_has_one_exact_head_method_and_no_fallback(monkeypatch):
    mod = _load()
    calls = []
    monkeypatch.setattr(mod, "_merge_policy", lambda repo, num, head: "direct")

    def fake_gh(args, timeout=60):
        calls.append(args)
        return _R("", returncode=1)

    monkeypatch.setattr(mod, "gh", fake_gh)

    assert mod.merge("organvm/limen", 1194, "deadbeefcafe", "direct") == "FAILED"
    assert len(calls) == 1
    assert calls[0][-3:] == ["--squash", "--match-head-commit", "deadbeefcafe"]


def test_submit_one_returns_queued_without_polling_or_retry(monkeypatch, capsys):
    mod = _load()
    head = "a" * 40
    calls = []
    monkeypatch.setattr(mod, "ensure_delivery_classification", lambda *_args: None)
    monkeypatch.setattr(
        mod,
        "_queue_state",
        lambda repo, num: {"state": "OPEN", "head": head, "queued": False},
    )
    monkeypatch.setattr(
        mod,
        "assess",
        lambda value: (value[0], value[1], "READY", head, "queue"),
    )
    monkeypatch.setattr(
        mod,
        "merge",
        lambda repo, num, expected, mode: calls.append((repo, num, expected, mode)) or "QUEUED",
    )

    assert mod.submit_one("4444J99/limen", 2543, head) == 0
    assert calls == [("4444J99/limen", 2543, head, "queue")]
    assert capsys.readouterr().out.strip() == f"MERGE-SUBMISSION 4444J99/limen#2543@{head}: QUEUED"


def test_submit_one_deferred_is_terminal_for_the_invocation(monkeypatch, capsys):
    mod = _load()
    head = "b" * 40
    monkeypatch.setattr(mod, "ensure_delivery_classification", lambda *_args: None)
    monkeypatch.setattr(
        mod,
        "_queue_state",
        lambda repo, num: {"state": "OPEN", "head": head, "queued": False},
    )
    monkeypatch.setattr(mod, "assess", lambda value: (value[0], value[1], "CI-PENDING"))
    monkeypatch.setattr(
        mod,
        "merge",
        lambda *args: (_ for _ in ()).throw(AssertionError("deferred submission must not mutate")),
    )

    assert mod.submit_one("4444J99/limen", 2543, head) == 2
    assert capsys.readouterr().out.strip().endswith(": DEFERRED — CI-PENDING")


def _delivery_view(**changes):
    return {"state": "OPEN", "isDraft": False, "headRefOid": "a" * 40, "labels": [], "body": ""} | changes


@pytest.mark.parametrize("readiness", ["READY", "CI-PENDING", "CI-RED", "STALE-BASE", "CONFLICT"])
def test_explicit_submission_labels_before_assessment_without_weakening_readiness(monkeypatch, readiness):
    mod = _load()
    state = _delivery_view()
    calls = []
    monkeypatch.setattr(mod, "merge_prohibition", lambda: None)
    monkeypatch.setattr(mod._dependency_upkeep, "pilot", lambda _repo: False)
    monkeypatch.setattr(mod, "_queue_state", lambda *_args: {"state": "OPEN", "head": "a" * 40, "queued": False})

    def fake_gh(args, timeout=60):
        calls.append(args[:2])
        if args[:2] == ["pr", "view"]:
            return _R(json.dumps(state))
        assert args == ["pr", "edit", "446", "-R", "owner/repo", "--add-label", "lifecycle:delivery"]
        state["labels"] = [{"name": "lifecycle:delivery"}]
        return _R("")

    def assess(value):
        assert state["labels"] == [{"name": "lifecycle:delivery"}]
        calls.append(["assess"])
        return (*value, readiness, "a" * 40, "direct")

    monkeypatch.setattr(mod, "gh", fake_gh)
    monkeypatch.setattr(mod, "assess", assess)
    monkeypatch.setattr(mod, "merge", lambda *_args: calls.append(["merge"]) or "MERGED")
    assert mod.submit_one("owner/repo", 446, "a" * 40) == (0 if readiness == "READY" else 2)
    assert calls[:4] == [["pr", "view"], ["pr", "edit"], ["pr", "view"], ["assess"]]
    assert (["merge"] in calls) == (readiness == "READY")


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"labels": [{"name": "lifecycle:delivery"}]}, None),
        ({"labels": [{"name": "lifecycle:blocked"}]}, "BLOCKED"),
        ({"labels": [{"name": "lifecycle:preservation"}]}, "PRESERVATION"),
        ({"labels": [{"name": "lifecycle:active-human"}]}, "ACTIVE-HUMAN"),
        ({"labels": [{"name": "lifecycle:superseded"}]}, "SUPERSEDED"),
        ({"labels": [{"name": "lifecycle:future-hold"}]}, "LIFECYCLE-UNKNOWN"),
        ({"labels": [{"name": "lifecycle:delivery"}, {"name": "lifecycle:blocked"}]}, "LIFECYCLE-UNKNOWN"),
        ({"labels": [{"name": "custody:preservation"}]}, "PRESERVATION"),
        ({"body": "Lifecycle preservation PR opened by `scripts/worktree-pr-receipts.py`."}, "PRESERVATION"),
        ({"isDraft": True}, "DRAFT-OR-UNMEASURED"),
        ({"isDraft": None}, "DRAFT-OR-UNMEASURED"),
        ({"state": "CLOSED"}, "PR-NOT-OPEN"),
        ({"headRefOid": "b" * 40}, "HEAD-CHANGED"),
        ({"labels": None}, "LIFECYCLE-UNAVAILABLE"),
        ({"labels": [None]}, "LIFECYCLE-UNAVAILABLE"),
    ],
)
def test_delivery_classification_preserves_existing_states_without_writes(monkeypatch, changes, reason):
    mod = _load()
    calls = []

    def fake_gh(args, timeout=60):
        calls.append(args)
        assert args[:2] == ["pr", "view"]
        return _R(json.dumps(_delivery_view(**changes)))

    monkeypatch.setattr(mod, "gh", fake_gh)
    assert mod.ensure_delivery_classification("owner/repo", 446, "a" * 40) == reason
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("after", "reason"),
    [
        ({"headRefOid": "b" * 40}, "HEAD-CHANGED"),
        ({"isDraft": True}, "DRAFT-OR-UNMEASURED"),
        ({"state": "CLOSED"}, "PR-NOT-OPEN"),
        ({"labels": []}, "LIFECYCLE-NOT-PERSISTED"),
        ({"labels": [{"name": "lifecycle:blocked"}]}, "BLOCKED"),
        ({"labels": [{"name": "lifecycle:delivery"}, {"name": "lifecycle:preservation"}]}, "LIFECYCLE-UNKNOWN"),
    ],
)
def test_classification_readback_rejects_races_without_removing_labels(monkeypatch, after, reason):
    mod = _load()
    calls = []

    def fake_gh(args, timeout=60):
        calls.append(args[:2])
        if args[:2] == ["pr", "edit"]:
            assert "--add-label" in args and "--remove-label" not in args
            return _R("")
        return _R(json.dumps(_delivery_view(**(after if len(calls) > 1 else {}))))

    monkeypatch.setattr(mod, "gh", fake_gh)
    assert mod.ensure_delivery_classification("owner/repo", 446, "a" * 40) == reason
    assert calls == [["pr", "view"], ["pr", "edit"], ["pr", "view"]]


@pytest.mark.parametrize("failure", ["read", "invalid-json", "write", "readback", "timeout"])
def test_classification_api_failures_stop_before_assessment(monkeypatch, failure):
    mod = _load()
    calls = []
    monkeypatch.setattr(mod, "merge_prohibition", lambda: None)
    monkeypatch.setattr(mod._dependency_upkeep, "pilot", lambda _repo: False)
    monkeypatch.setattr(mod, "_queue_state", lambda *_args: {"state": "OPEN", "head": "a" * 40, "queued": False})
    monkeypatch.setattr(mod, "assess", lambda *_args: pytest.fail("classification failure reached assessment"))

    def fake_gh(args, timeout=60):
        calls.append(args[:2])
        if failure == "timeout":
            raise mod.subprocess.TimeoutExpired("gh", timeout)
        if failure == "invalid-json":
            return _R("not-json")
        if failure == "read" or (failure == "readback" and len(calls) == 3):
            return _R("", returncode=1)
        if args[:2] == ["pr", "edit"]:
            return _R("", returncode=1 if failure == "write" else 0)
        return _R(json.dumps(_delivery_view()))

    monkeypatch.setattr(mod, "gh", fake_gh)
    assert mod.submit_one("owner/repo", 446, "a" * 40) == 2
    assert len(calls) <= 3


def test_one_shot_dry_run_is_rejected_before_submission(monkeypatch):
    mod = _load()
    head = "a" * 40
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "merge-drain.py",
            "--repo",
            "4444J99/limen",
            "--pr",
            "2543",
            "--expected-head",
            head,
            "--dry-run",
        ],
    )
    monkeypatch.setattr(
        mod,
        "submit_one",
        lambda *_args: (_ for _ in ()).throw(AssertionError("rejected dry-run must not submit a merge")),
    )

    with pytest.raises(SystemExit) as raised:
        mod.main()

    assert raised.value.code == 2


def test_submit_one_is_idempotent_for_already_queued_head(monkeypatch, capsys):
    mod = _load()
    head = "c" * 40
    monkeypatch.setattr(
        mod,
        "_queue_state",
        lambda repo, num: {"state": "OPEN", "head": head, "queued": True},
    )
    monkeypatch.setattr(
        mod,
        "assess",
        lambda *args: (_ for _ in ()).throw(AssertionError("already queued must not reassess")),
    )

    assert mod.submit_one("4444J99/limen", 2543, head) == 0
    assert ": QUEUED — already owned by GitHub" in capsys.readouterr().out


def test_queue_state_uses_authoritative_merge_queue_membership(monkeypatch):
    mod = _load()
    calls = []

    def fake_gh(args, timeout=60):
        calls.append((args, timeout))
        return _R(
            json.dumps(
                {
                    "data": {
                        "repository": {
                            "pullRequest": {
                                "state": "OPEN",
                                "headRefOid": "c" * 40,
                                "mergeStateStatus": "CLEAN",
                                "isInMergeQueue": True,
                                "autoMergeRequest": None,
                            }
                        }
                    }
                }
            )
        )

    monkeypatch.setattr(mod, "gh", fake_gh)

    assert mod._queue_state("4444J99/limen", 2543) == {
        "state": "OPEN",
        "head": "c" * 40,
        "queued": True,
    }
    assert calls[0][0][:2] == ["api", "graphql"]
    assert "isInMergeQueue" in calls[0][0][3]
    assert calls[0][1] == 40


def test_submit_one_refuses_merge_prohibiting_pause_before_github(monkeypatch, tmp_path, capsys):
    mod = _load()
    head = "d" * 40
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "AUTONOMY_PAUSED").write_text(
        "prohibitions: dispatch, merge\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(
        mod,
        "_queue_state",
        lambda *args: (_ for _ in ()).throw(AssertionError("pause must refuse before GitHub")),
    )

    assert mod.submit_one("4444J99/limen", 2543, head) == 3
    assert capsys.readouterr().out.strip().endswith("REFUSED — prohibitions: dispatch, merge")


def test_submit_one_refuses_when_pause_marker_is_unreadable(monkeypatch, tmp_path, capsys):
    mod = _load()
    head = "e" * 40
    marker = tmp_path / "logs" / "AUTONOMY_PAUSED"
    marker.mkdir(parents=True)
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(
        mod,
        "_queue_state",
        lambda *args: (_ for _ in ()).throw(AssertionError("unreadable pause must refuse before GitHub")),
    )

    assert mod.submit_one("4444J99/limen", 2543, head) == 3
    assert capsys.readouterr().out.strip().endswith("REFUSED — AUTONOMY_PAUSED unreadable (IsADirectoryError)")


@pytest.mark.parametrize("verdict", ["HOLD", "BLOCKED", "UNEXPECTED"])
def test_policy_failure_diagnostic_is_bounded_and_redacted(monkeypatch, capsys, verdict):
    mod = _load()
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(
            returncode=2, stdout=f"VERDICT: {verdict} secret-provider-detail\n", stderr="secret-token"
        ),
    )
    assert mod._merge_policy("organvm/laurea", 10, "a" * 40) is None
    out = capsys.readouterr().out
    expected = verdict if verdict in {"HOLD", "BLOCKED"} else "unknown"
    assert out == f"MERGE-DIAGNOSTIC: stage=policy exit=2 verdict={expected}\n"


@pytest.mark.parametrize("stage", ["policy", "effect"])
def test_merge_timeout_is_unconfirmed_and_never_retried(monkeypatch, capsys, stage):
    mod = _load()
    calls = []

    def timeout(*args, **kwargs):
        calls.append(args)
        raise mod.subprocess.TimeoutExpired("secret-command", 90, output="secret-output")

    if stage == "policy":
        monkeypatch.setattr(mod.subprocess, "run", timeout)
        assert mod._merge_policy("organvm/laurea", 10, "a" * 40) is None
    else:
        monkeypatch.setattr(mod, "_merge_policy", lambda *args: "direct")
        monkeypatch.setattr(mod, "gh", timeout)
        assert mod.merge("organvm/laurea", 10, "a" * 40, "direct") == "FAILED"
    assert len(calls) == 1
    out = capsys.readouterr().out
    assert "reason=timeout" in out
    assert "secret" not in out
    if stage == "effect":
        assert "outcome=unconfirmed" in out


def test_readable_nonexecutable_policy_runs_through_bash(tmp_path, monkeypatch):
    mod = _load()
    policy = tmp_path / "merge-policy.sh"
    policy.write_text(
        "#!/bin/bash\nprintf 'VERDICT: CLEARED\\nMERGE-MODE: direct\\nMERGE-HEAD: " + "a" * 40 + "\\n'\nexit 0\n"
    )
    policy.chmod(0o644)
    monkeypatch.setattr(mod, "POLICY", policy)
    assert mod._merge_policy("example/project", 1, "a" * 40) == "direct"
