from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prompt-priority-map.py"


def _load():
    spec = importlib.util.spec_from_file_location("prompt_priority_map", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_prompt_priority_map_builds_redacted_batches_without_raw_text(tmp_path: Path):
    ppm = _load()
    ppm.ROOT = tmp_path
    ppm.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    ppm.PROMPT_INDEX = ppm.PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
    ppm.CODEX_INDEX = ppm.PRIVATE_ROOT / "lifecycle" / "codex-session-lifecycle.json"
    ppm.ATTACK_INDEX = ppm.PRIVATE_ROOT / "lifecycle" / "session-attack-paths.json"
    ppm.BLOCKER_INDEX = ppm.PRIVATE_ROOT / "lifecycle" / "session-lifecycle-blockers.json"
    ppm.CAPABILITY_INDEX = ppm.PRIVATE_ROOT / "lifecycle" / "capability-substrate-index.json"
    ppm.DOC_PATH = tmp_path / "docs" / "prompt-priority-map.md"
    ppm.PRIVATE_INDEX = ppm.PRIVATE_ROOT / "lifecycle" / "prompt-priority-map.json"

    raw_source = tmp_path / "private-source.jsonl"
    raw_source.write_text("RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR", encoding="utf-8")
    ppm.PROMPT_INDEX.parent.mkdir(parents=True)
    ppm.PROMPT_INDEX.write_text(
        json.dumps(
            {
                "sources": [{"source": "codex-sessions", "files": 2, "prompt_events": 5}],
                "sessions": [
                    {
                        "session_key": "session-a",
                        "session_id_hash": "sid-a",
                        "source": "codex-sessions",
                        "path": str(raw_source),
                        "display_path": "~/private-source.jsonl",
                        "worktree_slug": "dirty-root",
                        "prompt_event_count": 4,
                        "prompt_hashes": ["hash-a", "hash-b", "hash-a", "hash-c"],
                        "prompt_bytes": 150000,
                        "event_count": 30,
                        "last_event": "2026-06-28T02:00:00+00:00",
                    },
                    {
                        "session_key": "session-b",
                        "session_id_hash": "sid-b",
                        "source": "codex-sessions",
                        "path": str(raw_source),
                        "display_path": "~/private-source.jsonl",
                        "prompt_event_count": 1,
                        "prompt_hashes": ["hash-secret"],
                        "prompt_bytes": 500,
                        "event_count": 5,
                        "last_event": "2026-06-28T01:00:00+00:00",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    ppm.CODEX_INDEX.write_text(
        json.dumps(
            {
                "session_count": 2,
                "sessions": [
                    {
                        "session_key": "session-a",
                        "family": "session_lifecycle",
                        "state": "STALLED",
                        "owner": "session lifecycle",
                    },
                    {
                        "session_key": "session-b",
                        "family": "auth_credentials",
                        "state": "PARKED",
                        "owner": "credential workstream",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    ppm.ATTACK_INDEX.write_text(
        json.dumps(
            {
                "ranked_paths": [
                    {
                        "kind": "worktree",
                        "id": "dirty-root",
                        "lane": "preserve",
                        "score": 90,
                        "next_action": "Preserve dirty-root before delegation.",
                    },
                    {
                        "kind": "family",
                        "id": "session_lifecycle",
                        "lane": "family",
                        "score": 75,
                        "next_action": "Collapse repeats into owner receipts.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    ppm.BLOCKER_INDEX.write_text(json.dumps({"blockers": [{"id": "local-lifecycle-disk-pressure"}]}), encoding="utf-8")
    ppm.CAPABILITY_INDEX.write_text(json.dumps({"activation_queue": [{"name": "artifact-resurfacing"}]}), encoding="utf-8")

    snapshot = ppm.build_snapshot(batch_size=2)
    markdown = ppm.render_markdown(snapshot, limit=10)
    ppm.write_outputs(snapshot, markdown)

    assert snapshot["coverage"]["prioritized_prompt_events"] == 5
    assert snapshot["coverage"]["unique_prompt_hashes"] == 4
    assert snapshot["session_items"][0]["session_key"] == "session-a"
    assert snapshot["session_items"][0]["lane"] == "preserve"
    assert snapshot["session_items"][1]["lane"] == "parked-secret"
    assert {unit["prompt_hash"] for unit in snapshot["prompt_units"]} == {
        "hash-a",
        "hash-b",
        "hash-c",
        "hash-secret",
    }
    assert any(batch["lane"] == "preserve" for batch in snapshot["review_batches"])
    assert "RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR" not in json.dumps(snapshot)
    assert "RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR" not in markdown
    assert "Prompt Priority Map" in markdown
    assert "Every prompt-like event is represented by a hash" in markdown
    assert ppm.DOC_PATH.exists()
    assert ppm.PRIVATE_INDEX.exists()


def test_prompt_priority_map_keeps_all_batch_worktree_roots():
    ppm = _load()
    session_items = [
        {
            "session_key": f"session-{idx}",
            "band": "critical",
            "lane": "historical-worktree-review",
            "score": 100 - idx,
            "prompt_events": 1,
            "prompt_hashes": [f"hash-{idx}"],
            "source": "claude-projects",
            "family": "uncategorized",
            "worktree_slug": f"root-{idx}",
            "next_action": "Privately inspect the historical worktree session.",
        }
        for idx in range(7)
    ]

    batches = ppm.build_review_batches(session_items, batch_size=10)

    assert len(batches) == 1
    assert set(batches[0]["worktrees"]) == {f"root-{idx}" for idx in range(7)}
