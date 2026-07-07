from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "worktree-reclaim-candidates.py"


def load_candidates():
    spec = importlib.util.spec_from_file_location("worktree_reclaim_candidates_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["worktree_reclaim_candidates_under_test"] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_candidate_rows_include_only_clean_merged_idle(tmp_path: Path) -> None:
    mod = load_candidates()
    worktree = tmp_path / "accepted-worktree"
    clone = tmp_path / "accepted-clone"
    dirty = tmp_path / "dirty-root"
    for path in (worktree, clone, dirty):
        path.mkdir()
    (worktree / ".git").write_text("gitdir: /tmp/example\n", encoding="utf-8")
    (clone / ".git").mkdir()

    report = {
        "total": 3,
        "debt": 1,
        "by_reason": {"clean+merged+idle": 2, "dirty": 1},
        "items": [
            {"name": worktree.name, "path": str(worktree), "reason": "clean+merged+idle", "debt": False},
            {"name": clone.name, "path": str(clone), "reason": "clean+merged+idle", "debt": False},
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
    assert gate["agent_policy"]["destructive_cleanup_lane"] == "human-acceptance-then-reclaim-worktrees"


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
    assert "docs/worktree-reclaim-acceptance.jsonl" in text
    assert "scripts/session-attack-paths.py" in text
