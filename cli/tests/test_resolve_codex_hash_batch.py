from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "resolve-codex-hash-batch.py"


def _load():
    spec = importlib.util.spec_from_file_location("resolve_codex_hash_batch", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_resolve_codex_hash_batch_records_metadata_without_raw_text(tmp_path: Path):
    resolver = _load()
    resolver.ROOT = tmp_path
    resolver.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    resolver.PRIORITY_INDEX = resolver.PRIVATE_ROOT / "lifecycle" / "prompt-priority-map.json"
    resolver.SESSION_INDEX = resolver.PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
    resolver.BATCH_RESOLUTION_RECEIPTS = tmp_path / "docs" / "prompt-batch-resolution-receipts.json"

    raw_source = tmp_path / "raw-session.jsonl"
    raw_source.write_text("RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR", encoding="utf-8")
    resolver.PRIVATE_ROOT.joinpath("lifecycle").mkdir(parents=True)
    resolver.PRIORITY_INDEX.write_text(
        json.dumps(
            {
                "review_batches": [
                    {
                        "id": "prompt-batch-critical-hash-review-test",
                        "band": "critical",
                        "lane": "hash-review",
                        "session_count": 2,
                        "prompt_events": 8,
                        "unique_prompt_hashes": 5,
                        "sources": {"codex-sessions": 2},
                        "session_keys": ["session-a", "session-b"],
                        "prompt_hashes": ["hash-a", "hash-b", "hash-c", "hash-d", "hash-e"],
                    }
                ],
                "session_items": [
                    {
                        "session_key": "session-a",
                        "source": "codex-sessions",
                        "prompt_events": 5,
                        "unique_prompt_hashes": 3,
                        "duplicate_prompt_events": 2,
                        "first_prompt_hash": "hash-a",
                        "last_prompt_hash": "hash-c",
                    },
                    {
                        "session_key": "session-b",
                        "source": "codex-sessions",
                        "prompt_events": 3,
                        "unique_prompt_hashes": 2,
                        "duplicate_prompt_events": 1,
                        "first_prompt_hash": "hash-d",
                        "last_prompt_hash": "hash-e",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    resolver.SESSION_INDEX.write_text(
        json.dumps(
            {
                "sessions": [
                    {
                        "session_key": "session-a",
                        "source": "codex-sessions",
                        "path": str(raw_source),
                        "cwd": str(tmp_path / "limen"),
                    },
                    {
                        "session_key": "session-b",
                        "source": "codex-sessions",
                        "path": str(raw_source),
                        "cwd": str(tmp_path / "limen"),
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    receipt = resolver.build_receipt("prompt-batch-critical-hash-review-test")

    assert receipt["status"] == "owner-recorded"
    assert receipt["lane"] == "hash-review"
    assert receipt["session_count"] == 2
    assert receipt["prompt_events"] == 8
    assert receipt["unique_prompt_hashes"] == 5
    assert receipt["duplicate_prompt_events"] == 3
    assert receipt["root_statuses"] == {"codex_session_sensitive_context_recorded": 2}
    assert [row["root"] for row in receipt["roots"]] == ["codex-session-session-a", "codex-session-session-b"]
    assert "RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR" not in json.dumps(receipt)

    resolver.BATCH_RESOLUTION_RECEIPTS.parent.mkdir(parents=True)
    resolver.BATCH_RESOLUTION_RECEIPTS.write_text(
        json.dumps({"version": 1, "generated_at": "old", "receipts": []}),
        encoding="utf-8",
    )
    resolver.append_receipt(receipt, replace=False)
    written = json.loads(resolver.BATCH_RESOLUTION_RECEIPTS.read_text(encoding="utf-8"))
    assert written["receipts"][0]["batch"] == "prompt-batch-critical-hash-review-test"
    assert resolver.receipt_exists("prompt-batch-critical-hash-review-test")
