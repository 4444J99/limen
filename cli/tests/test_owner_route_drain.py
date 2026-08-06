from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

from limen.owner_route_drain import (
    CLOSE,
    MERGE,
    ROUTE_TO_HEAL,
    SKIP,
    SUPERSEDE,
    classify,
    task_family,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "owner-route-drain.py"

NOW = dt.datetime(2026, 8, 6, 12, 0, tzinfo=dt.timezone.utc)


def _facts(**overrides) -> dict:
    base = {
        "state": "OPEN",
        "isDraft": False,
        "mergeable": "MERGEABLE",
        "statusCheckRollup": [{"conclusion": "SUCCESS"}],
        "createdAt": (NOW - dt.timedelta(days=2)).isoformat(),
        "headRefOid": "abc123",
        "headRefName": "jules/LIMEN-42-fix-thing",
        "title": "[limen jules LIMEN-42] fix thing",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------- classify()


def test_not_open_and_draft_skip():
    assert classify(_facts(state="MERGED"), now=NOW).action == SKIP
    assert classify(_facts(isDraft=True), now=NOW).action == SKIP


def test_merged_sibling_supersedes_everything_else():
    verdict = classify(_facts(), now=NOW, merged_sibling="https://github.com/o/r/pull/9")
    assert verdict.action == SUPERSEDE
    assert "pull/9" in verdict.reason


def test_trivial_diff_closes():
    verdict = classify(_facts(), now=NOW, is_trivial=True)
    assert verdict.action == CLOSE
    assert "trivial" in verdict.reason


def test_young_red_ci_routes_to_heal_and_never_acts():
    verdict = classify(_facts(statusCheckRollup=[{"conclusion": "FAILURE"}]), now=NOW)
    assert verdict.action == ROUTE_TO_HEAL


def test_aged_out_red_ci_closes():
    facts = _facts(
        statusCheckRollup=[{"conclusion": "FAILURE"}],
        createdAt=(NOW - dt.timedelta(days=60)).isoformat(),
    )
    verdict = classify(facts, now=NOW, max_age_days=45)
    assert verdict.action == CLOSE
    assert "aged out" in verdict.reason


def test_conflicting_routes_to_heal():
    verdict = classify(_facts(mergeable="CONFLICTING"), now=NOW)
    assert verdict.action == ROUTE_TO_HEAL


def test_pending_ci_skips():
    verdict = classify(_facts(statusCheckRollup=[{"state": "PENDING"}]), now=NOW)
    assert verdict.action == SKIP


def test_green_mergeable_is_merge_candidate():
    verdict = classify(_facts(), now=NOW)
    assert verdict.action == MERGE
    assert "merge-policy" in verdict.reason


def test_missing_head_oid_skips():
    verdict = classify(_facts(headRefOid=""), now=NOW)
    assert verdict.action == SKIP


def test_task_family_from_title_and_branch():
    assert task_family("[limen jules LIMEN-42] fix", "") == "LIMEN-42"
    assert task_family("plain title", "jules/HEAL-9-abcdef01") == "HEAL-9"
    assert task_family("plain", "feat/other") is None


# ---------------------------------------------------------------- effector


def _load():
    spec = importlib.util.spec_from_file_location("owner_route_drain_uut", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _R:
    def __init__(self, out: str = "", returncode: int = 0):
        self.returncode = returncode
        self.stdout = out
        self.stderr = ""


def test_apply_merge_refuses_without_policy_exit_zero(monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "_policy_cleared", lambda repo, num, head: (False, 2))

    def forbidden_gh(args, timeout=60):
        raise AssertionError(f"gh must not be called when policy refuses: {args!r}")

    monkeypatch.setattr(mod, "gh", forbidden_gh)
    assert mod._apply_merge("o/r", 1, "abc").startswith("policy-refused")


def test_apply_merge_pins_exact_head_on_policy_green(monkeypatch):
    mod = _load()
    calls: list[list[str]] = []
    monkeypatch.setattr(mod, "_policy_cleared", lambda repo, num, head: (True, 0))

    def fake_gh(args, timeout=60):
        calls.append(list(args))
        return _R()

    monkeypatch.setattr(mod, "gh", fake_gh)
    assert mod._apply_merge("o/r", 1, "abc123") == "merged-or-queued"
    assert calls and "--match-head-commit" in calls[0] and "abc123" in calls[0]


def _run_main(mod, monkeypatch, tmp_path, *, argv, verdict_facts, armed_env="0", pause=False):
    receipts = tmp_path / "owner-route-drain.jsonl"
    monkeypatch.setattr(mod, "RECEIPTS", receipts)
    monkeypatch.setattr(mod, "CURSOR", tmp_path / "cursor")
    marker = tmp_path / "AUTONOMY_PAUSED"
    if pause:
        marker.write_text("paused")
    monkeypatch.setattr(mod, "PAUSE_MARKER", marker)
    monkeypatch.setenv("LIMEN_OWNER_ROUTE_DRAIN_APPLY", armed_env)
    monkeypatch.setattr(mod, "_enumerate_jules_prs", lambda max_total: list(verdict_facts))
    monkeypatch.setattr(mod, "_pr_facts", lambda repo, num: verdict_facts[(repo, num)])
    monkeypatch.setattr(mod, "_is_trivial", lambda repo, num: False)
    monkeypatch.setattr(mod, "_merged_sibling", lambda repo, num, family: None)
    monkeypatch.setattr(mod, "_policy_cleared", lambda repo, num, head: (True, 0))
    mutations: list[list[str]] = []

    def fake_gh(args, timeout=60):
        if args[:2] in (["pr", "merge"], ["pr", "close"], ["pr", "comment"], ["pr", "edit"]):
            mutations.append(list(args))
        return _R("[]")

    monkeypatch.setattr(mod, "gh", fake_gh)
    monkeypatch.setattr(sys, "argv", ["owner-route-drain.py", *argv])
    assert mod.main() == 0
    rows = [json.loads(line) for line in receipts.read_text().splitlines()]
    return rows, mutations


def test_dry_run_default_writes_receipts_and_never_mutates(monkeypatch, tmp_path):
    mod = _load()
    facts = {("o/r", 1): _facts()}
    rows, mutations = _run_main(mod, monkeypatch, tmp_path, argv=[], verdict_facts=facts)
    assert mutations == []
    assert rows[0]["verdict"] == MERGE and rows[0]["applied"] is False


def test_pause_marker_forces_classification_only_even_when_armed(monkeypatch, tmp_path):
    mod = _load()
    facts = {("o/r", 1): _facts()}
    rows, mutations = _run_main(mod, monkeypatch, tmp_path, argv=[], verdict_facts=facts, armed_env="1", pause=True)
    assert mutations == []
    assert rows[0]["applied"] is False and rows[0]["paused"] is True


def test_merge_limit_bounds_merges(monkeypatch, tmp_path):
    mod = _load()
    facts = {("o/r", 1): _facts(), ("o/r", 2): _facts(headRefOid="def456")}
    rows, mutations = _run_main(
        mod,
        monkeypatch,
        tmp_path,
        argv=["--apply", "--merge-limit", "1"],
        verdict_facts=facts,
        armed_env="0",
    )
    merges = [m for m in mutations if m[:2] == ["pr", "merge"]]
    assert len(merges) == 1
    outcomes = {row["pr"]: row["outcome"] for row in rows}
    assert "merge-limit-reached" in outcomes.values()


def test_route_to_heal_takes_no_action_when_armed(monkeypatch, tmp_path):
    mod = _load()
    facts = {("o/r", 3): _facts(statusCheckRollup=[{"conclusion": "FAILURE"}])}
    rows, mutations = _run_main(mod, monkeypatch, tmp_path, argv=["--apply"], verdict_facts=facts)
    assert mutations == []
    assert rows[0]["verdict"] == ROUTE_TO_HEAL and rows[0]["outcome"] == "no-action"
