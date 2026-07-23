from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_merge_automation_does_not_delete_source_branches() -> None:
    for rel in ("scripts/merge-ready.sh", "scripts/merge-drain.py"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "--delete-branch" not in text
        assert "accepted reap" in text
