from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "worktree-reclaim-candidates.py"


def load_candidates(name: str = "worktree_reclaim_candidates_under_test"):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_candidate_rows_include_only_remote_preserved_loss_free_classes(tmp_path: Path) -> None:
    mod = load_candidates()
    worktree = tmp_path / "accepted-worktree"
    clone = tmp_path / "accepted-clone"
    pushed = tmp_path / "retained-pushed"
    dirty = tmp_path / "dirty-root"
    for path in (worktree, clone, pushed, dirty):
        path.mkdir()
    (worktree / ".git").write_text("gitdir: /tmp/example\n", encoding="utf-8")
    (clone / ".git").mkdir()
    (pushed / ".git").write_text("gitdir: /tmp/example-pushed\n", encoding="utf-8")

    report = {
        "total": 4,
        "debt": 1,
        "by_reason": {"clean+merged+idle": 2, "not-merged-to-default": 1, "dirty": 1},
        "items": [
            {"name": worktree.name, "path": str(worktree), "reason": "clean+merged+idle", "debt": False},
            {"name": clone.name, "path": str(clone), "reason": "clean+merged+idle", "debt": False},
            {"name": pushed.name, "path": str(pushed), "reason": "not-merged-to-default", "debt": True},
            {"name": dirty.name, "path": str(dirty), "reason": "dirty", "debt": True},
        ],
    }

    rows = mod.candidate_rows(report, limit=10, measure=False, size_scan_limit=0)
    by_name = {row["name"]: row for row in rows}

    assert sorted(by_name) == ["accepted-clone", "accepted-worktree"]
    assert by_name["accepted-worktree"]["action"] == "remove-worktree"
    assert by_name["accepted-clone"]["action"] == "remove-clone"
    assert by_name["accepted-worktree"]["acceptance_event_template"]["redaction_review"] == "not_required_remote_only"


def test_packet_governance_cites_agent_score_authorities() -> None:
    mod = load_candidates()

    gate = mod.governance_context(
        value_repos=["organvm/limen"],
        score_summary={"ledger_present": True, "records_sampled": 7, "by_grade": {"worth_it": 5}, "sunk": 0},
    )

    assert gate["repo_in_value_tier"] is True
    assert gate["prompt_attack_path"]["family"] == "worktree_lifecycle"
    assert gate["prompt_attack_path"]["score"] == 32
    assert "scripts/score-dispatch.py" in gate["authority_sources"]
    assert "cli/src/limen/capacity.py" in gate["authority_sources"]
    assert (
        gate["agent_policy"]["destructive_cleanup_lane"] == "standing-grant-or-human-acceptance-then-reclaim-worktrees"
    )


def test_render_markdown_makes_non_destructive_gate_explicit(tmp_path: Path) -> None:
    mod = load_candidates()
    root = tmp_path / "root"
    root.mkdir()
    report = {
        "total": 1,
        "debt": 0,
        "by_reason": {"clean+merged+idle": 1},
        "items": [{"name": root.name, "path": str(root), "reason": "clean+merged+idle", "debt": False}],
    }

    packet = mod.build_packet(
        report,
        generated_at="2026-07-07T23:00:00Z",
        limit=1,
        measure=False,
        size_scan_limit=0,
    )
    text = mod.render_markdown(packet)

    assert "candidate packet, not acceptance" in text
    assert "Authority Gate" in text
    assert "Pushed but unmerged roots retained" in text
    assert "docs/worktree-reclaim-acceptance.jsonl" in text
    assert "scripts/session-attack-paths.py" in text


def test_load_report_ignores_dispatch_worktree_root_for_estate_scan(tmp_path: Path, monkeypatch) -> None:
    mod = load_candidates("worktree_reclaim_candidates_env_guard")
    dispatch_root = tmp_path / "scratch-worktrees"
    output_root = dispatch_root / "aw-estate-custody"
    state_root = tmp_path / "limen-live"
    output_root.mkdir(parents=True)
    state_root.mkdir()
    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(dispatch_root))
    monkeypatch.setattr(mod, "OUTPUT_ROOT", output_root)
    monkeypatch.setattr(mod, "STATE_ROOT", state_root)

    seen: dict[str, str | None] = {}

    def fake_report(root: Path):
        seen["root"] = str(root)
        seen["worktree_root"] = os.environ.get("LIMEN_WORKTREE_ROOT")
        return {"total": 0, "debt": 0, "by_reason": {}, "items": []}

    monkeypatch.setattr(mod, "worktree_debt_report", fake_report)

    report = mod.load_report(None)

    assert report["total"] == 0
    assert seen == {"root": str(state_root), "worktree_root": None}
    assert os.environ["LIMEN_WORKTREE_ROOT"] == str(dispatch_root)


def test_load_report_reuses_state_root_candidate_packet(tmp_path: Path, monkeypatch) -> None:
    mod = load_candidates("worktree_reclaim_candidates_cached_packet")
    state_root = tmp_path / "live"
    output_root = tmp_path / "isolated"
    (state_root / "docs").mkdir(parents=True)
    output_root.mkdir()
    packet = {
        "schema": "limen.worktree_reclaim_candidates.v1",
        "summary": {"scanned_roots": 99, "debt_roots": 3},
        "by_reason": {"clean+merged+idle": 12, "dirty": 3},
        "candidates": [
            {
                "name": "root-a",
                "path": str(tmp_path / "root-a"),
                "reason": "clean+merged+idle",
                "size_bytes": 1234,
            }
        ],
    }
    (state_root / "docs" / "worktree-reclaim-candidates.json").write_text(json.dumps(packet), encoding="utf-8")
    monkeypatch.setattr(mod, "STATE_ROOT", state_root)
    monkeypatch.setattr(mod, "OUTPUT_ROOT", output_root)

    report = mod.load_report(None)
    rows = mod.candidate_rows(report, limit=10, measure=True, size_scan_limit=10)

    assert report["total"] == 99
    assert report["debt"] == 3
    assert rows[0]["name"] == "root-a"
    assert rows[0]["size_bytes"] == 1234
