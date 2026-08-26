from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


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
