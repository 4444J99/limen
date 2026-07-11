from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prompt-batch-review-ledger.py"


def _load():
    spec = importlib.util.spec_from_file_location("prompt_batch_review_ledger", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _priority_payload(batches: list[dict]) -> dict:
    bounded = [
        {
            **batch,
            "authority": "legacy_compatibility_only",
            "governs_execution": False,
        }
        for batch in batches
    ]
    return {
        "control": {
            "authority": "prompt_atom_projection",
            "healthy": True,
            "governing_unit": "atom_id",
            "legacy_can_override": False,
            "projection_digest": "a" * 64,
            "private_check": {
                "result": "pass",
                "projection_digest": "a" * 64,
            },
        },
        "legacy_compatibility": {
            "authoritative": False,
            "governs_execution": False,
            "reason": "legacy batches are custody containers only",
            "review_batches": bounded,
        },
    }


def _github_proof(owner: str, subject: str, number: int, *, sha: str) -> dict:
    return {
        "kind": "github_pr",
        "owner": owner,
        "subject": subject,
        "subject_hash": hashlib.sha256(subject.encode()).hexdigest(),
        "ref": f"https://github.com/{owner}/pull/{number}",
        "commit_sha": sha,
        "state": "merged",
        "reachable": True,
        "predicate": "exact-head CI",
        "result": "pass",
    }


def test_prompt_batch_review_ledger_promotes_preserved_batch_without_raw_text(tmp_path: Path):
    ledger = _load()
    ledger.ROOT = tmp_path
    ledger.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    ledger.PRIORITY_INDEX = ledger.PRIVATE_ROOT / "lifecycle" / "prompt-priority-map.json"
    ledger.ATTACK_INDEX = ledger.PRIVATE_ROOT / "lifecycle" / "session-attack-paths.json"
    ledger.PRESERVATION_RECEIPTS = tmp_path / "docs" / "worktree-preservation-receipts.json"
    ledger.PACKET_RESOLUTION_RECEIPTS = tmp_path / "docs" / "prompt-packet-resolution-receipts.json"
    ledger.BATCH_RESOLUTION_RECEIPTS = tmp_path / "docs" / "prompt-batch-resolution-receipts.json"
    ledger.DOC_PATH = tmp_path / "docs" / "prompt-batch-review-ledger.md"
    ledger.PRIVATE_INDEX = ledger.PRIVATE_ROOT / "lifecycle" / "prompt-batch-review-ledger.json"

    raw_source = tmp_path / "raw-session.jsonl"
    raw_source.write_text("RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR", encoding="utf-8")
    ledger.PRIORITY_INDEX.parent.mkdir(parents=True)
    ledger.PRIORITY_INDEX.write_text(
        json.dumps(
            _priority_payload(
                [
                    {
                        "id": "prompt-batch-critical-owner-blocker-001",
                        "band": "critical",
                        "lane": "owner-blocker",
                        "session_count": 2,
                        "prompt_events": 20,
                        "unique_prompt_hashes": 10,
                        "max_score": 99,
                        "avg_score": 88.0,
                        "next_action": "Classify owner intent before cleanup.",
                        "sources": {"codex-sessions": 1, "claude-projects": 1},
                        "families": {"worktree_lifecycle": 1, "uncategorized": 1},
                        "worktrees": {"root-a": 1, "root-b": 1},
                        "session_keys": ["session-a", "session-b"],
                        "prompt_hashes": ["hash-a", "hash-b"],
                    },
                    {
                        "id": "prompt-batch-critical-stalled-review-001",
                        "band": "critical",
                        "lane": "stalled-review",
                        "session_count": 1,
                        "prompt_events": 5,
                        "unique_prompt_hashes": 4,
                        "max_score": 80,
                        "next_action": "Packetize before delegation.",
                        "sources": {"codex-sessions": 1},
                        "families": {"session_lifecycle": 1},
                        "worktrees": {},
                        "session_keys": ["session-c"],
                        "prompt_hashes": ["hash-c"],
                    },
                    {
                        "id": "prompt-batch-low-parked-secret-001",
                        "band": "parked",
                        "lane": "parked-secret",
                        "session_count": 1,
                        "prompt_events": 1,
                        "unique_prompt_hashes": 1,
                        "max_score": 10,
                        "next_action": "Keep parked.",
                        "sources": {"codex-sessions": 1},
                        "families": {"auth_credentials": 1},
                        "worktrees": {},
                        "session_keys": ["session-d"],
                        "prompt_hashes": ["hash-d"],
                    },
                ]
            )
        ),
        encoding="utf-8",
    )
    ledger.ATTACK_INDEX.write_text(
        json.dumps(
            {
                "ranked_paths": [
                    {"id": "root-a", "kind": "worktree", "score": 70},
                    {"id": "root-b", "kind": "worktree", "score": 60},
                ]
            }
        ),
        encoding="utf-8",
    )
    ledger.PRESERVATION_RECEIPTS.parent.mkdir(parents=True)
    ledger.PRESERVATION_RECEIPTS.write_text(
        json.dumps(
            {
                "receipts": [
                    {
                        "root": "root-a",
                        "repo": "organvm/root-a",
                        "status": "private_patch_preserved",
                        "private_receipt": ".limen-private/path-a/receipt.json",
                    },
                    {
                        "root": "root-b",
                        "repo": "organvm/root-b",
                        "status": "generated_results_patch_preserved",
                        "private_receipt": ".limen-private/path-b/receipt.json",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    snapshot = ledger.build_snapshot(limit=10)
    markdown = ledger.render_markdown(snapshot, limit=10)
    ledger.write_outputs(snapshot, markdown)

    by_id = {item["id"]: item for item in snapshot["batches"]}
    assert by_id["prompt-batch-critical-owner-blocker-001"]["status"] == "owner-recorded"
    assert by_id["prompt-batch-critical-owner-blocker-001"]["resolution_complete"] is False
    assert by_id["prompt-batch-critical-stalled-review-001"]["status"] == "needs-packetization"
    assert by_id["prompt-batch-low-parked-secret-001"]["status"] == "parked-secret"
    assert snapshot["coverage"]["recorded_batches"] == 1
    assert snapshot["coverage"]["closed_batches"] == 0
    assert snapshot["coverage"]["open_review_batches"] == 2
    assert "RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR" not in json.dumps(snapshot)
    assert "RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR" not in markdown
    assert "Prompt Batch Review Ledger" in markdown
    assert "owner-recorded" in markdown
    assert ledger.DOC_PATH.exists()
    assert ledger.PRIVATE_INDEX.exists()


def test_prompt_batch_review_ledger_promotes_completed_packetized_batch(tmp_path: Path):
    ledger = _load()
    ledger.ROOT = tmp_path
    ledger.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    ledger.PRIORITY_INDEX = ledger.PRIVATE_ROOT / "lifecycle" / "prompt-priority-map.json"
    ledger.ATTACK_INDEX = ledger.PRIVATE_ROOT / "lifecycle" / "session-attack-paths.json"
    ledger.PRESERVATION_RECEIPTS = tmp_path / "docs" / "worktree-preservation-receipts.json"
    ledger.PACKET_RESOLUTION_RECEIPTS = tmp_path / "docs" / "prompt-packet-resolution-receipts.json"
    ledger.BATCH_RESOLUTION_RECEIPTS = tmp_path / "docs" / "prompt-batch-resolution-receipts.json"
    ledger.DOC_PATH = tmp_path / "docs" / "prompt-batch-review-ledger.md"
    ledger.PRIVATE_INDEX = ledger.PRIVATE_ROOT / "lifecycle" / "prompt-batch-review-ledger.json"

    ledger.PRIORITY_INDEX.parent.mkdir(parents=True)
    ledger.PRIORITY_INDEX.write_text(
        json.dumps(
            _priority_payload(
                [
                    {
                        "id": "prompt-batch-critical-stalled-review-001",
                        "band": "critical",
                        "lane": "stalled-review",
                        "session_count": 2,
                        "prompt_events": 7,
                        "unique_prompt_hashes": 2,
                        "max_score": 100,
                        "next_action": "Packetize before delegation.",
                        "sources": {"codex-sessions": 2},
                        "families": {"worktree_lifecycle": 1, "session_lifecycle": 1},
                        "worktrees": {"root-a": 1},
                        "session_keys": ["session-a", "session-b"],
                        "prompt_hashes": ["hash-a", "hash-b"],
                    },
                ]
            )
        ),
        encoding="utf-8",
    )
    ledger.ATTACK_INDEX.write_text(json.dumps({"ranked_paths": []}), encoding="utf-8")
    ledger.PRESERVATION_RECEIPTS.parent.mkdir(parents=True)
    ledger.PRESERVATION_RECEIPTS.write_text(json.dumps({"receipts": []}), encoding="utf-8")
    ledger.PACKET_RESOLUTION_RECEIPTS.write_text(
        json.dumps(
            {
                "receipts": [
                    {
                        "packet": "packet-prompt-batch-critical-stalled-review-001-worktree_lifecycle",
                        "source_batch": "prompt-batch-critical-stalled-review-001",
                        "family": "worktree_lifecycle",
                        "status": "owner-recorded",
                    },
                    {
                        "packet": "packet-prompt-batch-critical-stalled-review-001-session_lifecycle",
                        "source_batch": "prompt-batch-critical-stalled-review-001",
                        "family": "session_lifecycle",
                        "status": "owner-recorded",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    snapshot = ledger.build_snapshot(limit=10)
    markdown = ledger.render_markdown(snapshot, limit=10)

    batch = snapshot["batches"][0]
    assert batch["status"] == "owner-recorded"
    assert batch["resolution_complete"] is False
    assert snapshot["coverage"]["recorded_batches"] == 1
    assert snapshot["coverage"]["closed_batches"] == 0
    assert snapshot["coverage"]["open_review_batches"] == 1
    assert snapshot["coverage"]["packet_resolution_receipts"] == 2
    assert batch["evidence"]["packet_receipt_statuses"] == {"owner-recorded": 2}
    assert "Packet resolution receipts available: `2`" in markdown
    assert "packets `owner-recorded` 2" in markdown


def test_prompt_batch_review_ledger_keeps_mixed_legacy_resolution_open(tmp_path: Path):
    ledger = _load()
    ledger.ROOT = tmp_path
    ledger.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    ledger.PRIORITY_INDEX = ledger.PRIVATE_ROOT / "lifecycle" / "prompt-priority-map.json"
    ledger.ATTACK_INDEX = ledger.PRIVATE_ROOT / "lifecycle" / "session-attack-paths.json"
    ledger.PRESERVATION_RECEIPTS = tmp_path / "docs" / "worktree-preservation-receipts.json"
    ledger.PACKET_RESOLUTION_RECEIPTS = tmp_path / "docs" / "prompt-packet-resolution-receipts.json"
    ledger.BATCH_RESOLUTION_RECEIPTS = tmp_path / "docs" / "prompt-batch-resolution-receipts.json"
    ledger.DOC_PATH = tmp_path / "docs" / "prompt-batch-review-ledger.md"
    ledger.PRIVATE_INDEX = ledger.PRIVATE_ROOT / "lifecycle" / "prompt-batch-review-ledger.json"

    ledger.PRIORITY_INDEX.parent.mkdir(parents=True)
    ledger.PRIORITY_INDEX.write_text(
        json.dumps(
            _priority_payload(
                [
                    {
                        "id": "prompt-batch-critical-historical-worktree-review-001",
                        "band": "critical",
                        "lane": "historical-worktree-review",
                        "session_count": 2,
                        "prompt_events": 9,
                        "unique_prompt_hashes": 5,
                        "max_score": 100,
                        "next_action": "Privately inspect historical roots.",
                        "sources": {"claude-projects": 2},
                        "families": {"uncategorized": 2},
                        "worktrees": {"root-a": 1, "root-b": 1},
                        "session_keys": ["session-a", "session-b"],
                        "prompt_hashes": ["hash-a", "hash-b"],
                    },
                ]
            )
        ),
        encoding="utf-8",
    )
    ledger.ATTACK_INDEX.write_text(json.dumps({"ranked_paths": []}), encoding="utf-8")
    ledger.PRESERVATION_RECEIPTS.parent.mkdir(parents=True)
    ledger.PRESERVATION_RECEIPTS.write_text(json.dumps({"receipts": []}), encoding="utf-8")
    ledger.PACKET_RESOLUTION_RECEIPTS.write_text(json.dumps({"receipts": []}), encoding="utf-8")
    ledger.BATCH_RESOLUTION_RECEIPTS.write_text(
        json.dumps(
            {
                "receipts": [
                    {
                        "batch": "prompt-batch-critical-historical-worktree-review-001",
                        "status": "owner-recorded",
                        "roots": [
                            {"root": "root-a", "repo": "organvm/root-a", "status": "remote_pr_merged"},
                            {"root": "root-b", "repo": "organvm/root-b", "status": "owner_repo_routed_absent_branch"},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    snapshot = ledger.build_snapshot(limit=10)
    markdown = ledger.render_markdown(snapshot, limit=10)

    batch = snapshot["batches"][0]
    assert batch["status"] == "owner-recorded"
    assert batch["resolution_complete"] is False
    assert snapshot["coverage"]["recorded_batches"] == 1
    assert snapshot["coverage"]["closed_batches"] == 0
    assert snapshot["coverage"]["open_review_batches"] == 1
    assert snapshot["coverage"]["batch_resolution_receipts"] == 1
    assert batch["evidence"]["batch_root_statuses"] == {
        "remote_pr_merged": 1,
        "owner_repo_routed_absent_branch": 1,
    }
    assert "Batch resolution receipts available: `1`" in markdown
    assert "batch roots `remote_pr_merged` 1, `owner_repo_routed_absent_branch` 1" in markdown


def test_prompt_batch_review_ledger_closes_only_verified_terminal_rows(tmp_path: Path):
    ledger = _load()
    ledger.ROOT = tmp_path
    ledger.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    ledger.PRIORITY_INDEX = ledger.PRIVATE_ROOT / "lifecycle" / "prompt-priority-map.json"
    ledger.ATTACK_INDEX = ledger.PRIVATE_ROOT / "lifecycle" / "session-attack-paths.json"
    ledger.PRESERVATION_RECEIPTS = tmp_path / "docs" / "worktree-preservation-receipts.json"
    ledger.PACKET_RESOLUTION_RECEIPTS = tmp_path / "docs" / "prompt-packet-resolution-receipts.json"
    ledger.BATCH_RESOLUTION_RECEIPTS = tmp_path / "docs" / "prompt-batch-resolution-receipts.json"
    ledger.DOC_PATH = tmp_path / "docs" / "prompt-batch-review-ledger.md"
    ledger.PRIVATE_INDEX = ledger.PRIVATE_ROOT / "lifecycle" / "prompt-batch-review-ledger.json"

    ledger.PRIORITY_INDEX.parent.mkdir(parents=True)
    ledger.PRIORITY_INDEX.write_text(
        json.dumps(
            _priority_payload(
                [
                    {
                        "id": "prompt-batch-high-historical-worktree-review-001",
                        "band": "high",
                        "lane": "historical-worktree-review",
                        "session_count": 2,
                        "prompt_events": 4,
                        "unique_prompt_hashes": 2,
                        "max_score": 80,
                        "sources": {"claude-projects": 2},
                        "families": {"uncategorized": 2},
                        "worktrees": {"root-a": 1, "root-b": 1},
                    }
                ]
            )
        ),
        encoding="utf-8",
    )
    ledger.ATTACK_INDEX.write_text(json.dumps({"ranked_paths": []}), encoding="utf-8")
    ledger.PRESERVATION_RECEIPTS.parent.mkdir(parents=True)
    ledger.PRESERVATION_RECEIPTS.write_text(json.dumps({"receipts": []}), encoding="utf-8")
    ledger.PACKET_RESOLUTION_RECEIPTS.write_text(json.dumps({"receipts": []}), encoding="utf-8")
    ledger.BATCH_RESOLUTION_RECEIPTS.write_text(
        json.dumps(
            {
                "version": 2,
                "receipts": [
                    {
                        "batch": "prompt-batch-high-historical-worktree-review-001",
                        "status": "owner-recorded",
                        "roots": [
                            {
                                "root": "root-a",
                                "repo": "organvm/root-a",
                                "status": "remote_pr_merged",
                                "disposition": "done",
                                "outcome_receipt": _github_proof(
                                    "organvm/root-a",
                                    "root-a",
                                    1,
                                    sha="a" * 40,
                                ),
                            },
                            {
                                "root": "root-b",
                                "repo": "organvm/root-b",
                                "status": "superseded_on_origin_main",
                                "disposition": "superseded",
                                "superseded_by": "origin/main@abc123",
                                "outcome_receipt": _github_proof(
                                    "organvm/root-b",
                                    "root-b",
                                    2,
                                    sha="b" * 40,
                                ),
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    snapshot = ledger.build_snapshot(limit=10)
    batch = snapshot["batches"][0]

    assert batch["status"] == "owner-recorded"
    assert batch["resolution_complete"] is True
    assert batch["evidence"]["disposition_counts"] == {"done": 1, "superseded": 1}
    assert snapshot["coverage"]["recorded_batches"] == 1
    assert snapshot["coverage"]["closed_batches"] == 1
    assert snapshot["coverage"]["open_review_batches"] == 0


def test_prompt_batch_review_ledger_blocked_row_is_recorded_but_open():
    ledger = _load()
    resolution = ledger.resolution_for_rows(
        [
            {
                "root": "root-a",
                "status": "owner_repo_missing_or_private",
                "disposition": "blocked",
                "owner": "organvm/root-a",
                "gate": "repository access",
                "next_command": "gh repo view organvm/root-a",
            }
        ]
    )

    assert resolution["complete"] is False
    assert resolution["disposition_counts"] == {"blocked": 1}
    assert resolution["unresolved_root_count"] == 1


def test_prompt_batch_review_ledger_requires_every_expected_root():
    ledger = _load()
    batch = {"worktrees": {"root-a": 1, "root-b": 1}}
    resolution = ledger.resolution_for_batch(
        batch,
        [],
        [],
        {
            "status": "owner-recorded",
            "roots": [
                {
                    "root": "root-a",
                    "disposition": "done",
                    "outcome_receipt": {
                        "ref": "https://github.com/organvm/root-a/pull/1",
                        "predicate": "exact-head CI",
                        "result": "pass",
                    },
                }
            ],
        },
    )

    assert resolution["complete"] is False
    assert resolution["coverage_complete"] is False
    assert resolution["missing_expected_ids"] == ["root-b"]


def test_prompt_batch_review_ledger_rootless_top_level_receipt_cannot_close_children():
    ledger = _load()
    resolution = ledger.resolution_for_batch(
        {"prompt_events": 1000, "worktrees": {}},
        [],
        [],
        {
            "status": "owner-recorded",
            "disposition": "done",
            "outcome_receipt": {
                "ref": "https://github.com/organvm/limen/issues/1",
                "predicate": "one check",
                "result": "pass",
            },
        },
    )

    assert resolution["complete"] is False
    assert resolution["row_count"] == 0
    assert resolution["coverage_complete"] is False


@pytest.mark.parametrize(
    "payload",
    [
        {"review_batches": []},
        _priority_payload([]) | {"control": {"authority": "legacy_session_batches"}},
        {
            **_priority_payload([]),
            "legacy_compatibility": {
                "authoritative": True,
                "governs_execution": False,
                "reason": "forged boundary",
                "review_batches": [],
            },
        },
    ],
)
def test_prompt_batch_review_ledger_rejects_legacy_authority_confusion(payload: dict):
    ledger = _load()

    with pytest.raises(ledger.BatchAuthorityError):
        ledger.priority_review_batches(payload)


def test_terminal_proof_requires_type_owner_subject_and_hash_binding():
    ledger = _load()
    row = {
        "root": "root-a",
        "repo": "organvm/root-a",
        "disposition": "done",
        "outcome_receipt": _github_proof(
            "organvm/root-a",
            "root-a",
            1,
            sha="a" * 40,
        ),
    }
    assert ledger.row_has_terminal_outcome(row) is True

    for field, value in (
        ("kind", None),
        ("owner", "organvm/other"),
        ("subject", "root-b"),
        ("subject_hash", "0" * 64),
        ("commit_sha", "abc123"),
        ("reachable", False),
        ("state", "open"),
    ):
        forged = {**row, "outcome_receipt": {**row["outcome_receipt"], field: value}}
        assert ledger.row_has_terminal_outcome(forged) is False

    untyped = {
        **row,
        "outcome_receipt": {
            "ref": "https://github.com/organvm/root-a/pull/1",
            "predicate": "looks green",
            "result": "pass",
        },
    }
    assert ledger.row_has_terminal_outcome(untyped) is False


def test_local_predicate_receipt_must_exist_and_match_hash(tmp_path: Path):
    ledger = _load()
    ledger.ROOT = tmp_path
    receipt = tmp_path / "receipts" / "root-a.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text('{"result":"pass"}', encoding="utf-8")
    proof = {
        "kind": "predicate_receipt",
        "owner": "organvm/root-a",
        "subject": "root-a",
        "subject_hash": hashlib.sha256(b"root-a").hexdigest(),
        "path": "receipts/root-a.json",
        "sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
        "predicate": "root predicate",
        "result": "pass",
    }
    row = {
        "root": "root-a",
        "repo": "organvm/root-a",
        "disposition": "done",
        "outcome_receipt": proof,
    }

    assert ledger.row_has_terminal_outcome(row) is True
    receipt.write_text('{"result":"changed"}', encoding="utf-8")
    assert ledger.row_has_terminal_outcome(row) is False
