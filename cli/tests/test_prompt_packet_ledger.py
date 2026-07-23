from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prompt-packet-ledger.py"


def _load():
    spec = importlib.util.spec_from_file_location("prompt_packet_ledger", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_prompt_packet_ledger_groups_stalled_batches_without_raw_text(tmp_path: Path):
    packets = _load()
    packets.ROOT = tmp_path
    packets.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    packets.BATCH_REVIEW_INDEX = packets.PRIVATE_ROOT / "lifecycle" / "prompt-batch-review-ledger.json"
    packets.PRIORITY_INDEX = packets.PRIVATE_ROOT / "lifecycle" / "prompt-priority-map.json"
    packets.ATTACK_INDEX = packets.PRIVATE_ROOT / "lifecycle" / "session-attack-paths.json"
    packets.DOC_PATH = tmp_path / "docs" / "prompt-packet-ledger.md"
    packets.PRIVATE_INDEX = packets.PRIVATE_ROOT / "lifecycle" / "prompt-packet-ledger.json"
    packets.RESOLUTION_RECEIPTS = tmp_path / "docs" / "prompt-packet-resolution-receipts.json"

    raw_source = tmp_path / "raw-session.jsonl"
    raw_source.write_text("RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR", encoding="utf-8")
    packets.BATCH_REVIEW_INDEX.parent.mkdir(parents=True)
    packets.BATCH_REVIEW_INDEX.write_text(
        json.dumps(
            {
                "counts": {"statuses": {"needs-packetization": 1}},
                "batches": [{"id": "prompt-batch-critical-stalled-review-001"}],
                "review_queue": [
                    {
                        "id": "prompt-batch-critical-stalled-review-001",
                        "status": "needs-packetization",
                        "band": "critical",
                        "lane": "stalled-review",
                        "session_keys": ["session-a", "session-b", "session-c"],
                    },
                    {
                        "id": "prompt-batch-critical-legacy-session-review-001",
                        "status": "needs-private-review",
                        "band": "critical",
                        "lane": "legacy-session-review",
                        "session_keys": ["session-d"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    packets.PRIORITY_INDEX.write_text(
        json.dumps(
            {
                "session_items": [
                    {
                        "session_key": "session-a",
                        "family": "worktree_lifecycle",
                        "state": "STALLED",
                        "source": "codex-sessions",
                        "worktree_slug": "root-a",
                        "score": 100,
                        "prompt_events": 4,
                        "prompt_hashes": ["hash-a", "hash-b"],
                        "private_source_path": str(raw_source),
                    },
                    {
                        "session_key": "session-b",
                        "family": "session_lifecycle",
                        "state": "STALLED",
                        "source": "codex-sessions",
                        "worktree_slug": "root-b",
                        "score": 90,
                        "prompt_events": 3,
                        "prompt_hashes": ["hash-c"],
                        "private_source_path": str(raw_source),
                    },
                    {
                        "session_key": "session-c",
                        "family": "worktree_lifecycle",
                        "state": "STALLED",
                        "source": "codex-sessions",
                        "worktree_slug": "root-a",
                        "score": 80,
                        "prompt_events": 2,
                        "prompt_hashes": ["hash-a", "hash-d"],
                        "private_source_path": str(raw_source),
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    packets.ATTACK_INDEX.write_text(
        json.dumps(
            {
                "ranked_paths": [
                    {"id": "root-a", "lane": "owner-blocker", "reason": "dirty", "score": 70},
                    {"id": "root-b", "lane": "family", "reason": "stalled", "score": 60},
                ]
            }
        ),
        encoding="utf-8",
    )

    snapshot = packets.build_snapshot(limit=10)
    markdown = packets.render_markdown(snapshot, limit=10)
    packets.write_outputs(snapshot, markdown)

    by_family = {packet["family"]: packet for packet in snapshot["packets"]}
    assert set(by_family) == {"worktree_lifecycle", "session_lifecycle"}
    assert by_family["worktree_lifecycle"]["prompt_events"] == 6
    assert by_family["worktree_lifecycle"]["unique_prompt_hashes"] == 3
    assert by_family["session_lifecycle"]["dispatchability"] == "codex-owner-packet"
    assert snapshot["coverage"]["packets"] == 2
    assert snapshot["coverage"]["recorded_packets"] == 0
    assert snapshot["coverage"]["open_packets"] == 2
    assert snapshot["coverage"]["prompt_events"] == 9
    assert "RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR" not in json.dumps(snapshot)
    assert "RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR" not in markdown
    assert "Prompt Packet Ledger" in markdown
    assert packets.DOC_PATH.exists()
    assert packets.PRIVATE_INDEX.exists()


def test_prompt_packet_ledger_records_packet_resolution_receipts(tmp_path: Path):
    packets = _load()
    packets.ROOT = tmp_path
    packets.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    packets.BATCH_REVIEW_INDEX = packets.PRIVATE_ROOT / "lifecycle" / "prompt-batch-review-ledger.json"
    packets.PRIORITY_INDEX = packets.PRIVATE_ROOT / "lifecycle" / "prompt-priority-map.json"
    packets.ATTACK_INDEX = packets.PRIVATE_ROOT / "lifecycle" / "session-attack-paths.json"
    packets.DOC_PATH = tmp_path / "docs" / "prompt-packet-ledger.md"
    packets.PRIVATE_INDEX = packets.PRIVATE_ROOT / "lifecycle" / "prompt-packet-ledger.json"
    packets.RESOLUTION_RECEIPTS = tmp_path / "docs" / "prompt-packet-resolution-receipts.json"

    packets.BATCH_REVIEW_INDEX.parent.mkdir(parents=True)
    packets.BATCH_REVIEW_INDEX.write_text(
        json.dumps(
            {
                "counts": {"statuses": {"needs-packetization": 1}},
                "batches": [{"id": "prompt-batch-critical-stalled-review-001"}],
                "review_queue": [
                    {
                        "id": "prompt-batch-critical-stalled-review-001",
                        "status": "needs-packetization",
                        "band": "critical",
                        "lane": "stalled-review",
                        "session_keys": ["session-a", "session-b"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    packets.PRIORITY_INDEX.write_text(
        json.dumps(
            {
                "session_items": [
                    {
                        "session_key": "session-a",
                        "family": "worktree_lifecycle",
                        "state": "STALLED",
                        "source": "codex-sessions",
                        "worktree_slug": "root-a",
                        "score": 100,
                        "prompt_events": 4,
                        "prompt_hashes": ["hash-a"],
                    },
                    {
                        "session_key": "session-b",
                        "family": "session_lifecycle",
                        "state": "STALLED",
                        "source": "codex-sessions",
                        "score": 90,
                        "prompt_events": 3,
                        "prompt_hashes": ["hash-b"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    packets.ATTACK_INDEX.write_text(json.dumps({"ranked_paths": []}), encoding="utf-8")
    packets.RESOLUTION_RECEIPTS.parent.mkdir(parents=True)
    packets.RESOLUTION_RECEIPTS.write_text(
        json.dumps(
            {
                "receipts": [
                    {
                        "packet": "packet-prompt-batch-critical-stalled-review-001-worktree_lifecycle",
                        "status": "owner-recorded",
                        "classification": "root state recorded",
                        "roots": [{"root": "root-a", "status": "historical_absent_reference"}],
                        "next_action": "No local cleanup remains for this root.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    snapshot = packets.build_snapshot(limit=10)
    markdown = packets.render_markdown(snapshot, limit=10)

    by_family = {packet["family"]: packet for packet in snapshot["packets"]}
    assert by_family["worktree_lifecycle"]["status"] == "owner-recorded"
    assert by_family["worktree_lifecycle"]["dispatchability"] == "recorded-owner-receipt"
    assert by_family["session_lifecycle"]["status"] == "packetized"
    assert snapshot["coverage"]["recorded_packets"] == 1
    assert snapshot["coverage"]["open_packets"] == 1
    assert snapshot["coverage"]["packet_resolution_receipts"] == 1
    assert "Recorded Packets" in markdown
    assert "historical_absent_reference" in markdown


def test_prompt_packet_ledger_keeps_recorded_source_batch_history(tmp_path: Path):
    packets = _load()
    packets.ROOT = tmp_path
    packets.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    packets.BATCH_REVIEW_INDEX = packets.PRIVATE_ROOT / "lifecycle" / "prompt-batch-review-ledger.json"
    packets.PRIORITY_INDEX = packets.PRIVATE_ROOT / "lifecycle" / "prompt-priority-map.json"
    packets.ATTACK_INDEX = packets.PRIVATE_ROOT / "lifecycle" / "session-attack-paths.json"
    packets.DOC_PATH = tmp_path / "docs" / "prompt-packet-ledger.md"
    packets.PRIVATE_INDEX = packets.PRIVATE_ROOT / "lifecycle" / "prompt-packet-ledger.json"
    packets.RESOLUTION_RECEIPTS = tmp_path / "docs" / "prompt-packet-resolution-receipts.json"

    packets.BATCH_REVIEW_INDEX.parent.mkdir(parents=True)
    packets.BATCH_REVIEW_INDEX.write_text(
        json.dumps(
            {
                "counts": {"statuses": {"owner-recorded": 1}},
                "batches": [
                    {
                        "id": "prompt-batch-critical-stalled-review-001",
                        "status": "owner-recorded",
                        "band": "critical",
                        "lane": "stalled-review",
                        "session_keys": ["session-a", "session-b"],
                    }
                ],
                "review_queue": [],
            }
        ),
        encoding="utf-8",
    )
    packets.PRIORITY_INDEX.write_text(
        json.dumps(
            {
                "session_items": [
                    {
                        "session_key": "session-a",
                        "family": "worktree_lifecycle",
                        "state": "STALLED",
                        "source": "codex-sessions",
                        "worktree_slug": "root-a",
                        "score": 100,
                        "prompt_events": 4,
                        "prompt_hashes": ["hash-a"],
                    },
                    {
                        "session_key": "session-b",
                        "family": "session_lifecycle",
                        "state": "STALLED",
                        "source": "codex-sessions",
                        "score": 90,
                        "prompt_events": 3,
                        "prompt_hashes": ["hash-b"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    packets.ATTACK_INDEX.write_text(json.dumps({"ranked_paths": []}), encoding="utf-8")
    packets.RESOLUTION_RECEIPTS.parent.mkdir(parents=True)
    packets.RESOLUTION_RECEIPTS.write_text(
        json.dumps(
            {
                "receipts": [
                    {
                        "packet": "packet-prompt-batch-critical-stalled-review-001-worktree_lifecycle",
                        "source_batch": "prompt-batch-critical-stalled-review-001",
                        "family": "worktree_lifecycle",
                        "status": "owner-recorded",
                        "roots": [{"root": "root-a", "status": "historical_absent_reference"}],
                    },
                    {
                        "packet": "packet-prompt-batch-critical-stalled-review-001-session_lifecycle",
                        "source_batch": "prompt-batch-critical-stalled-review-001",
                        "family": "session_lifecycle",
                        "status": "owner-recorded",
                        "roots": [{"session": "session-b", "status": "session_ledger_recorded_no_root"}],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    snapshot = packets.build_snapshot(limit=10)
    markdown = packets.render_markdown(snapshot, limit=10)

    assert snapshot["coverage"]["needs_packetization_batches"] == 0
    assert snapshot["coverage"]["packets"] == 2
    assert snapshot["coverage"]["recorded_packets"] == 2
    assert snapshot["coverage"]["open_packets"] == 0
    assert "packet-prompt-batch-critical-stalled-review-001-worktree_lifecycle" in markdown
    assert "Packet Queue" in markdown
    assert "| 0 | none | n/a | n/a | n/a | 0 | 0 | none | n/a | n/a |" in markdown
