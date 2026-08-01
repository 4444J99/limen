"""Shell entrypoints must use the shared exact-plan reclaim controller."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DRAIN = ROOT / "scripts" / "drain.sh"
HEARTBEAT = ROOT / "scripts" / "heartbeat-loop.sh"
RECLAIM = ROOT / "scripts" / "reclaim-worktrees.py"


def _reclaim_block(source: str) -> str:
    start = source.index("# RECLAIM is intentionally outside the queue lock")
    end = source.index("# LIFECYCLE PRESSURE", start)
    return source[start:end]


def test_reclaim_still_refuses_apply_without_a_plan_sha():
    source = RECLAIM.read_text(encoding="utf-8")

    assert "expected-plan-sha-required" in source


def test_drain_delegates_both_passes_to_the_shared_bounded_controller():
    source = DRAIN.read_text(encoding="utf-8")
    start = source.index("# RECLAIM —")
    block = source[start : source.index('echo "[drain] board:"', start)]

    assert block.count("reclaim-cycle.py") == 1
    assert 'reclaim_cycle generated "${LIMEN_RECLAIM_GENERATED_TIMEOUT:-120}" --generated-only' in block
    assert 'reclaim_cycle full "${LIMEN_RECLAIM_TIMEOUT:-300}"' in block
    assert "reclaim-worktrees.py" not in block
    assert "cycle failed" in block
    assert 'LIMEN_RECLAIM_REPO_LOCAL_WT="${LIMEN_RECLAIM_REPO_LOCAL_WT:-1}"' in block
    assert 'LIMEN_RECLAIM_REGISTERED_WT="${LIMEN_RECLAIM_REGISTERED_WT:-1}"' in block
    assert "direct library callers retain worktree_roots.py's auto semantics" in block


def test_heartbeat_uses_controller_and_explicitly_arms_live_broad_discovery():
    block = _reclaim_block(HEARTBEAT.read_text(encoding="utf-8"))

    assert block.count("reclaim-cycle.py") == 2
    assert "reclaim-worktrees.py" not in block
    assert block.count("LIMEN_RECLAIM_REPO_LOCAL_WT=1") == 2
    assert block.count("LIMEN_RECLAIM_REGISTERED_WT=1") == 2
    assert "LIMEN_RECLAIM_GENERATED_TIMEOUT:-120" in block
    assert "LIMEN_RECLAIM_TIMEOUT:-300" in block
    assert "next beat retries" in block
