from __future__ import annotations

import importlib.util
import sys
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


def test_reclaim_acceptance_matches_clean_merged_worktree(tmp_path: Path) -> None:
    reclaim = load_reclaim_worktrees()
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
