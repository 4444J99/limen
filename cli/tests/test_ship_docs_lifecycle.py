from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ship-docs.sh"


def test_ship_docs_retains_roots_and_branches_for_accepted_reclaim() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "LIMEN_WORKTREES" in text
    assert "worktree-reclaim-acceptance.jsonl" in text
    assert "branch-reap-acceptance.jsonl" in text
    assert "worktree remove" not in text
    assert "branch -D" not in text
    assert "--delete-branch" not in text
