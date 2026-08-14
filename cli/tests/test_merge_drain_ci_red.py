"""Exact-head subject ledger for rotating-window CI-red notifications."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "merge-drain.py"


def _load(tmp_path: Path):
    spec = importlib.util.spec_from_file_location("merge_drain_ci_red_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.CI_RED_LEDGER = tmp_path / "ci-red-subjects.json"
    return module


def _subjects(module) -> dict:
    return json.loads(module.CI_RED_LEDGER.read_text(encoding="utf-8"))["subjects"]


def test_rotating_omission_never_clears_and_head_change_rearms(tmp_path: Path) -> None:
    module = _load(tmp_path)
    red = [("organvm/repo", 7, "CI-RED", "a" * 40, ("pr-gate",))]

    first = module.reconcile_ci_red_subjects(red, [("organvm/repo", 7)], enumeration_complete=False)
    omitted = module.reconcile_ci_red_subjects([], [("organvm/other", 8)], enumeration_complete=False)
    same_head = module.reconcile_ci_red_subjects(red, [("organvm/repo", 7)], enumeration_complete=False)
    changed = module.reconcile_ci_red_subjects(
        [("organvm/repo", 7, "CI-RED", "b" * 40, ("python-3.14",))],
        [("organvm/repo", 7)],
        enumeration_complete=False,
    )

    assert [row["head"] for row in first] == ["a" * 40]
    assert omitted == []
    assert same_head == []
    assert [row["head"] for row in changed] == ["b" * 40]
    assert _subjects(module)["organvm/repo#7"]["checks"] == ["python-3.14"]


def test_subject_clears_only_on_explicit_green_or_complete_absence(tmp_path: Path) -> None:
    module = _load(tmp_path)
    module.reconcile_ci_red_subjects(
        [("organvm/repo", 7, "CI-RED", "a" * 40, ("pr-gate",))],
        [("organvm/repo", 7)],
        enumeration_complete=False,
    )
    module.reconcile_ci_red_subjects(
        [("organvm/repo", 7, "READY", "a" * 40, "direct")],
        [("organvm/repo", 7)],
        enumeration_complete=False,
    )
    assert _subjects(module) == {}

    module.reconcile_ci_red_subjects(
        [("organvm/repo", 7, "CI-RED", "a" * 40, ("pr-gate",))],
        [("organvm/repo", 7)],
        enumeration_complete=False,
    )
    module.reconcile_ci_red_subjects([], [("organvm/other", 8)], enumeration_complete=True)
    assert _subjects(module) == {}


def test_failing_required_check_names_are_preserved(monkeypatch, tmp_path: Path) -> None:
    module = _load(tmp_path)

    class Result:
        # `gh pr checks` returns non-zero when a required check is red; the JSON
        # payload remains authoritative and must still drive CI-red classification.
        returncode = 1
        stdout = json.dumps(
            [
                {"name": "pr-gate", "bucket": "fail", "state": "FAILURE"},
                {"name": "advisory", "bucket": "pass", "state": "SUCCESS"},
            ]
        )

    monkeypatch.setattr(module, "gh", lambda *_args, **_kwargs: Result())
    assert module._failing_required_checks("organvm/repo", 7) == ("pr-gate",)


def test_optional_failure_does_not_create_ci_red_onset(monkeypatch, tmp_path: Path) -> None:
    module = _load(tmp_path)
    payload = {
        "state": "OPEN",
        "isDraft": False,
        "labels": [{"name": "lifecycle:delivery"}],
        "mergeable": "MERGEABLE",
        "mergeStateStatus": "UNSTABLE",
        "statusCheckRollup": [
            {"name": "advisory", "conclusion": "FAILURE"},
            {"name": "pr-gate", "conclusion": "SUCCESS"},
        ],
        "files": [],
        "baseRefName": "main",
        "headRefOid": "a" * 40,
    }

    def fake_gh(args, **_kwargs):
        if args[:2] == ["pr", "view"]:
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload))
        assert args[:2] == ["pr", "checks"]
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps([{"name": "pr-gate", "bucket": "pass", "state": "SUCCESS"}]),
        )

    monkeypatch.setattr(module, "gh", fake_gh)
    monkeypatch.setattr(module, "stale_base_verdict", lambda *_args: None)
    monkeypatch.setattr(module, "merge_queue_capability", lambda *_args: "inactive")
    monkeypatch.setattr(module, "_is_trivial", lambda *_args: False)

    assert module.assess(("organvm/repo", 7)) == (
        "organvm/repo",
        7,
        "READY",
        "a" * 40,
        "direct",
    )


def test_ledger_persistence_failure_is_reported_without_crashing(monkeypatch, tmp_path: Path, capsys) -> None:
    module = _load(tmp_path)
    monkeypatch.setattr(module.os, "replace", lambda *_args: (_ for _ in ()).throw(OSError("read-only")))

    assert module._save_ci_red_ledger({"organvm/repo#7": {"head": "a" * 40}}) is False
    assert "ci-red ledger persistence failed" in capsys.readouterr().err


def test_corrupt_ledger_withholds_onset_and_preserves_source(tmp_path: Path, capsys) -> None:
    module = _load(tmp_path)
    module.CI_RED_LEDGER.write_text('{"schema_version":', encoding="utf-8")
    reserved = []

    result = module.reconcile_ci_red_subjects(
        [("organvm/repo", 7, "CI-RED", "a" * 40, ("pr-gate",))],
        [("organvm/repo", 7)],
        enumeration_complete=True,
        reserve_notification=lambda subject: reserved.append(subject) or True,
    )

    assert result == []
    assert reserved == []
    assert module.CI_RED_LEDGER.read_text(encoding="utf-8") == '{"schema_version":'
    assert "ci-red ledger unavailable" in capsys.readouterr().err


def test_unreserved_notification_keeps_ci_red_onset_retryable(tmp_path: Path) -> None:
    module = _load(tmp_path)
    red = [("organvm/repo", 7, "CI-RED", "a" * 40, ("pr-gate",))]

    withheld = module.reconcile_ci_red_subjects(
        red,
        [("organvm/repo", 7)],
        enumeration_complete=False,
        reserve_notification=lambda _subject: False,
    )
    retried = module.reconcile_ci_red_subjects(
        red,
        [("organvm/repo", 7)],
        enumeration_complete=False,
        reserve_notification=lambda _subject: True,
    )

    assert withheld == []
    assert [row["head"] for row in retried] == ["a" * 40]
    assert _subjects(module)["organvm/repo#7"]["head"] == "a" * 40


def test_ci_red_notification_uses_repo_pr_and_exact_head_key(monkeypatch, tmp_path: Path) -> None:
    module = _load(tmp_path)
    calls = []
    monkeypatch.setattr(
        module._notify,
        "notify_event",
        lambda *args, **kwargs: calls.append((args, kwargs)) or SimpleNamespace(status="emitted", reserved=True),
    )

    assert module._reserve_ci_red_notification({"identity": "organvm/repo#7", "head": "a" * 40, "checks": ["pr-gate"]})
    assert calls[0][1]["stable_id"] == f"organvm/repo#7@{'a' * 40}"
