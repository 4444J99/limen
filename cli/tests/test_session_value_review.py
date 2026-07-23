from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "session-value-review.py"


def _load():
    spec = importlib.util.spec_from_file_location("session_value_review", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> None:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    subprocess.run(["git", "-C", str(repo), *args], check=True, env=full_env, capture_output=True)


def test_session_value_review_summarizes_long_run_without_raw_text(tmp_path: Path):
    review = _load()
    review.ROOT = tmp_path
    review.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    review.BATCH_RESOLUTION_RECEIPTS = tmp_path / "docs" / "prompt-batch-resolution-receipts.json"
    review.BATCH_REVIEW_INDEX = review.PRIVATE_ROOT / "lifecycle" / "prompt-batch-review-ledger.json"
    review.DOC_PATH = tmp_path / "docs" / "session-value-review.md"
    review.PRIVATE_INDEX = review.PRIVATE_ROOT / "lifecycle" / "session-value-review.json"
    review.GATE_HISTORY = review.PRIVATE_ROOT / "lifecycle" / "session-value-gate-history.jsonl"

    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test User")
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    stamp = "2026-06-28T08:00:00+00:00"
    _git(
        tmp_path,
        "add",
        "README.md",
        env={"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp},
    )
    _git(
        tmp_path,
        "commit",
        "-m",
        "limen: resolve test prompt batch",
        env={"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp},
    )

    raw_source = tmp_path / "raw-session.jsonl"
    raw_source.write_text("RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR", encoding="utf-8")
    review.BATCH_RESOLUTION_RECEIPTS.parent.mkdir(parents=True)
    review.BATCH_RESOLUTION_RECEIPTS.write_text(
        json.dumps(
            {
                "receipts": [
                    {
                        "generated_at": "2026-06-28T08:10:00Z",
                        "batch": "prompt-batch-medium-family-test",
                        "status": "owner-recorded",
                        "band": "medium",
                        "lane": "family",
                        "session_count": 2,
                        "prompt_events": 10,
                        "unique_prompt_hashes": 8,
                        "roots": [
                            {"root": "root-a", "repo": "organvm/a", "status": "remote_pr_merged"},
                            {
                                "root": "root-b",
                                "repo": "organvm/b",
                                "status": "owner_repo_routed_absent_branch",
                            },
                            {"root": "root-c", "repo": "organvm/c", "status": "remote_pr_preserved"},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    review.BATCH_REVIEW_INDEX.parent.mkdir(parents=True)
    review.BATCH_REVIEW_INDEX.write_text(
        json.dumps(
            {
                "coverage": {
                    "recorded_batches": 1,
                    "open_review_batches": 1,
                    "parked_secret_batches": 0,
                },
                "counts": {"statuses": {"owner-recorded": 1, "needs-private-review": 1}},
                "review_queue": [
                    {
                        "id": "prompt-batch-medium-legacy-session-review-test",
                        "status": "needs-private-review",
                        "band": "medium",
                        "lane": "legacy-session-review",
                        "session_count": 2,
                        "prompt_events": 9,
                        "unique_prompt_hashes": 7,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    snapshot = review.build_snapshot(
        review.parse_timestamp("2026-06-28T07:00:00Z"),
        review.parse_timestamp("2026-06-28T09:00:00Z"),
    )
    markdown = review.render_markdown(snapshot, limit=10)
    review.write_outputs(snapshot, markdown)

    assert snapshot["metrics"]["commits"] == 1
    assert snapshot["metrics"]["batch_receipts"] == 1
    assert snapshot["metrics"]["sessions_recorded"] == 2
    assert snapshot["metrics"]["prompt_events_recorded"] == 10
    assert snapshot["metrics"]["merged_roots"] == 1
    assert snapshot["metrics"]["followup_roots"] == 1
    assert snapshot["metrics"]["owner_absent_roots"] == 1
    assert snapshot["findings"]["commit_kinds"] == {"prompt_corpus": 1}
    assert "valuable" in snapshot["findings"]["verdict"]
    assert snapshot["gate"]["action"] == "continue_prompt_sweep"
    assert snapshot["gate"]["exit_code"] == 0
    assert snapshot["gate"]["next_commands"] == [
        "python3 scripts/resolve-legacy-session-batch.py prompt-batch-medium-legacy-session-review-test --write"
    ]
    assert "RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR" not in json.dumps(snapshot)
    assert "RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR" not in markdown
    assert "Session Value Review" in markdown
    assert "Operating Gate" in markdown
    assert "prompt-batch-medium-family-test" in markdown
    assert review.DOC_PATH.exists()
    assert review.PRIVATE_INDEX.exists()


def test_commit_kind_classifies_operating_work():
    review = _load()

    assert review.commit_kind("limen: resolve ninth medium family prompt batch") == "prompt_corpus"
    assert review.commit_kind("limen: update task board states") == "task_board"
    assert review.commit_kind("tabularius: preserve board projection 2026-07-09T09:09:17Z") == "task_board"
    assert review.commit_kind("limen: refresh autonomous PR receipts") == "receipt_refresh"
    assert review.commit_kind("docs: derive accurate usage section") == "direct_engineering"
    assert review.commit_kind("capture: autonomic off-disk sync") == "capture"


def test_session_value_review_critiques_high_motion_without_receipts():
    review = _load()
    commits = [
        {
            "kind": "receipt_refresh",
            "files": 2,
            "insertions": 10,
            "deletions": 1,
        }
        for _ in range(21)
    ]
    queue = {
        "coverage": {
            "recorded_batches": 91,
            "open_review_batches": 201,
            "parked_secret_batches": 17,
        }
    }

    findings = review.build_findings(commits, [], queue, hours=48)
    critique = "\n".join(findings["critique_points"])

    assert findings["commit_kinds"] == {"receipt_refresh": 21}
    assert "zero prompt-batch receipts moved" in critique
    assert "High-motion/no-receipt window" in critique
    assert "Most commits were PR-receipt refreshes" in critique


def test_session_value_gate_switches_after_repeated_followup_pressure():
    review = _load()
    snapshot = {
        "window": {"hours": 1.5},
        "inputs": {
            "batch_resolution_receipts": {"present": True},
            "batch_review_index": {"present": True},
        },
        "metrics": {
            "commits": 1,
            "batch_receipts": 1,
            "prompt_events_recorded": 12,
            "followup_roots": 5,
            "merged_roots": 1,
            "owner_absent_roots": 1,
        },
        "current_queue": {
            "coverage": {"open_review_batches": 3},
            "next": [
                {
                    "id": "prompt-batch-medium-family-015",
                    "lane": "family",
                }
            ],
        },
    }
    history = [
        {
            "gate": {
                "pressures": {
                    "followup_over_done_or_routed": True,
                }
            }
        }
    ]

    gate = review.decide_gate(snapshot, history=history)

    assert gate["action"] == "switch_to_packetization"
    assert gate["exit_code"] == 10
    assert gate["pressures"]["consecutive_followup_pressure_reports"] == 2
    assert gate["next_commands"][0] == "python3 scripts/prompt-packet-ledger.py --write"


def test_session_value_gate_switches_after_repeated_high_motion_without_receipts():
    review = _load()
    snapshot = {
        "window": {"hours": 1.5},
        "inputs": {
            "batch_resolution_receipts": {"present": True},
            "batch_review_index": {"present": True},
        },
        "metrics": {
            "commits": 22,
            "batch_receipts": 0,
            "prompt_events_recorded": 0,
            "followup_roots": 0,
            "merged_roots": 0,
            "owner_absent_roots": 0,
        },
        "findings": {"commit_kinds": {"direct_engineering": 22}},
        "current_queue": {
            "coverage": {"open_review_batches": 3},
            "next": [
                {
                    "id": "prompt-batch-medium-family-015",
                    "lane": "family",
                }
            ],
        },
    }
    history = [
        {
            "gate": {
                "pressures": {
                    "motion_without_receipts": True,
                    "high_motion_no_receipts": True,
                }
            }
        }
    ]

    gate = review.decide_gate(snapshot, history=history)

    assert gate["action"] == "switch_to_packetization"
    assert gate["exit_code"] == 10
    assert gate["pressures"]["motion_without_receipts"] is True
    assert gate["pressures"]["high_motion_no_receipts"] is True
    assert gate["pressures"]["consecutive_motion_without_receipts"] == 2
    assert gate["pressures"]["consecutive_high_motion_no_receipts"] == 2
    assert gate["next_commands"] == [
        "python3 scripts/resolve-codex-family-batch.py prompt-batch-medium-family-015 --write"
    ]


def test_session_value_gate_routes_hash_review_to_hash_resolver():
    review = _load()
    snapshot = {
        "window": {"hours": 1.5},
        "inputs": {
            "batch_resolution_receipts": {"present": True},
            "batch_review_index": {"present": True},
        },
        "metrics": {
            "commits": 2,
            "batch_receipts": 0,
            "prompt_events_recorded": 0,
            "followup_roots": 0,
            "merged_roots": 0,
            "owner_absent_roots": 0,
        },
        "findings": {"commit_kinds": {"direct_engineering": 2}},
        "current_queue": {
            "coverage": {"open_review_batches": 3},
            "next": [
                {
                    "id": "prompt-batch-critical-hash-review-001",
                    "lane": "hash-review",
                }
            ],
        },
    }
    history = [{"gate": {"pressures": {"motion_without_receipts": True}}}]

    gate = review.decide_gate(snapshot, history=history)

    assert gate["action"] == "switch_to_packetization"
    assert gate["next_commands"] == [
        "python3 scripts/resolve-codex-hash-batch.py prompt-batch-critical-hash-review-001 --write"
    ]


def test_session_value_gate_allows_product_dispatch_after_packets_close(tmp_path):
    review = _load()
    review.PRODUCT_LEDGER_INDEX = tmp_path / "product-ledger.json"
    review.PRODUCT_LEDGER_INDEX.write_text(
        json.dumps(
            {
                "next_unblocked": [
                    {
                        "id": "PROD-repo-test",
                        "owner": "organvm/value-repo",
                        "state": "ship",
                        "disposition": "sell-ready",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    snapshot = {
        "window": {"hours": 1.5},
        "inputs": {
            "batch_resolution_receipts": {"present": True},
            "batch_review_index": {"present": True},
            "prompt_packet_index": {"present": True},
        },
        "metrics": {
            "commits": 1,
            "batch_receipts": 1,
            "prompt_events_recorded": 10,
            "followup_roots": 0,
            "merged_roots": 0,
            "owner_absent_roots": 0,
        },
        "findings": {"commit_kinds": {"direct_engineering": 1}},
        "current_queue": {
            "coverage": {"open_review_batches": 0},
            "next": [],
        },
        "current_packet_queue": {
            "present": True,
            "coverage": {"open_packets": 0},
            "next": [],
        },
    }

    gate = review.decide_gate(snapshot, history=[])

    assert gate["action"] == "continue_direct_product_work"
    assert gate["exit_code"] == 0
    assert gate["evidence"]["open_prompt_packets"] == 0
    assert gate["evidence"]["next_product"] == "PROD-repo-test"
    assert gate["evidence"]["next_product_owner"] == "organvm/value-repo"
    assert gate["next_commands"] == ["python3 scripts/product-ledger.py --refresh --redacted-summary"]


def test_session_value_gate_keeps_packetization_block_when_packets_open():
    review = _load()
    snapshot = {
        "window": {"hours": 1.5},
        "inputs": {
            "batch_resolution_receipts": {"present": True},
            "batch_review_index": {"present": True},
            "prompt_packet_index": {"present": True},
        },
        "metrics": {
            "commits": 1,
            "batch_receipts": 1,
            "prompt_events_recorded": 10,
            "followup_roots": 0,
            "merged_roots": 0,
            "owner_absent_roots": 0,
        },
        "findings": {"commit_kinds": {"direct_engineering": 1}},
        "current_queue": {
            "coverage": {"open_review_batches": 0},
            "next": [],
        },
        "current_packet_queue": {
            "present": True,
            "coverage": {"open_packets": 1},
            "next": [{"id": "packet-test", "dispatchability": "needs-owner-repo"}],
        },
    }

    gate = review.decide_gate(snapshot, history=[])

    assert gate["action"] == "switch_to_packetization"
    assert gate["exit_code"] == 10
    assert gate["evidence"]["open_prompt_packets"] == 1
    assert gate["next_commands"] == ["python3 scripts/prompt-packet-ledger.py --write"]


def test_session_value_gate_blocks_receipt_only_custody_motion(tmp_path):
    review = _load()
    review.PRODUCT_LEDGER_INDEX = tmp_path / "product-ledger.json"
    review.PRODUCT_LEDGER_INDEX.write_text(
        json.dumps(
            {
                "next_unblocked": [
                    {
                        "id": "PROD-repo-test",
                        "owner": "organvm/value-repo",
                        "state": "ship",
                        "disposition": "sell-ready",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    snapshot = {
        "window": {"hours": 1.5},
        "inputs": {
            "batch_resolution_receipts": {"present": True},
            "batch_review_index": {"present": True},
        },
        "metrics": {
            "commits": 5,
            "batch_receipts": 0,
            "prompt_events_recorded": 0,
            "followup_roots": 0,
            "merged_roots": 0,
            "owner_absent_roots": 0,
        },
        "findings": {"commit_kinds": {"receipt_refresh": 4, "task_board": 1}},
        "current_queue": {
            "coverage": {"open_review_batches": 3},
            "next": [],
        },
    }

    gate = review.decide_gate(snapshot, history=[])

    assert gate["action"] == "switch_to_direct_product_work"
    assert gate["exit_code"] == 10
    assert gate["pressures"]["receipt_only_motion"] is True
    assert gate["evidence"]["next_product"] == "PROD-repo-test"
    assert gate["evidence"]["next_product_owner"] == "organvm/value-repo"
    assert gate["next_commands"] == ["python3 scripts/product-ledger.py --refresh --redacted-summary"]


def test_session_value_gate_stops_without_durable_progress():
    review = _load()
    snapshot = {
        "window": {"hours": 1.5},
        "inputs": {
            "batch_resolution_receipts": {"present": True},
            "batch_review_index": {"present": True},
        },
        "metrics": {
            "commits": 0,
            "batch_receipts": 0,
            "prompt_events_recorded": 0,
            "followup_roots": 0,
            "merged_roots": 0,
            "owner_absent_roots": 0,
        },
        "current_queue": {
            "coverage": {"open_review_batches": 3},
            "next": [],
        },
    }

    gate = review.decide_gate(snapshot, history=[])

    assert gate["action"] == "stop_no_durable_progress"
    assert gate["exit_code"] == 20
    assert gate["pressures"]["no_durable_progress"] is True
