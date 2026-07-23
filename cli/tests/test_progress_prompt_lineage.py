from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from limen.progress_prompt_lineage import build_prompt_lineage_source

NOW = datetime(2026, 7, 21, 12, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "progress-prompt-lineage.py"


def _digest(value) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _seal(*, atoms: int, unresolved: int, ready: bool = True) -> dict:
    payload = {
        "schema": "limen.prompt-authority-seal.v1",
        "authority_ready": ready,
        "validation_ok": ready,
        "scope": {
            "scope": "all" if ready else "partial:all",
            "target_scope": "all",
            "all_baseline_complete": ready,
        },
        "totals": {
            "pending": 0 if ready else 3,
            "errors": 0,
            "unsupported": 0,
            "unresolved": 0 if ready else 3,
            "adapter_gaps": 0,
            "validation_errors": 0,
        },
        "coverage": {"atoms": atoms, "current_unresolved_atoms": unresolved},
    }
    payload["content_hash"] = _digest(payload)
    return payload


def _evidence(ref: str) -> dict:
    return {
        "kind": "predicate_receipt",
        "ref": ref,
        "predicate": "focused predicate",
        "result": "pass",
        "verified_at": "2026-07-21T11:00:00Z",
    }


def _atom(
    atom_id: str,
    *,
    kind: str = "ask",
    disposition: str = "unassessed",
    current: bool = True,
    predecessors: list[str] | None = None,
    successor: str | None = None,
    evidence: list[dict] | None = None,
) -> dict:
    outcome = {
        "disposition": disposition,
        "owner": "organvm/limen",
        "evidence": evidence or [],
        "successor_atom_id": successor,
    }
    if disposition == "blocked":
        outcome.update({"gate": "external-account", "next_command": "owner bootstrap"})
    return {
        "atom_id": atom_id,
        "lineage_id": "pl-lineage",
        "kind": kind,
        "authority": "operator",
        "predecessor_ids": predecessors or [],
        "is_current_intent": current,
        "owner_route": "TABVLARIVS/prompt-control",
        "outcome": outcome,
    }


def _reconciliation(atom_ids: list[str]) -> dict:
    rows = []
    for atom_id in atom_ids:
        rows.append(
            {
                "atom_id": atom_id,
                "owner_receipts": [
                    {
                        "owner": "organvm/limen",
                        "receipts": [
                            {"surface": "task", "receipt_id": f"task:TASK-{atom_id}"},
                            {"surface": "pull_request", "receipt_id": "pr:organvm/limen#42"},
                        ],
                    }
                ],
            }
        )
    return {
        "control": {
            "authority": "prompt_atom_projection",
            "source_scope": "all",
            "target_scope": "all",
            "matching": "exact_atom_id_only",
            "read_only": True,
            "estate_mutations": 0,
            "private_check": {"result": "pass"},
        },
        "coverage": {"unresolved_atom_ids": len(rows)},
        "atom_reconciliation": rows,
    }


def test_exact_authority_joins_tasks_prs_supersession_blocker_and_predicates() -> None:
    atoms = [
        _atom(
            "pa-old",
            disposition="superseded",
            current=False,
            successor="pa-correction",
            evidence=[_evidence("docs/old-proof.json")],
        ),
        _atom(
            "pa-correction",
            kind="correction",
            disposition="blocked",
            predecessors=["pa-old"],
        ),
        _atom(
            "pa-done",
            kind="acceptance_criterion",
            disposition="done",
            evidence=[_evidence("docs/done-proof.json")],
        ),
    ]

    full, tracked = build_prompt_lineage_source(
        _seal(atoms=3, unresolved=1),
        atoms,
        _reconciliation(["pa-correction"]),
        generated_at=NOW,
    )

    assert full["source_report"]["exhaustive"] is True
    assert full["source_report"]["normalized_leaf_count"] == 3
    rows = {row["leaf_id"]: row for row in full["leaves"]}
    assert rows["pa-correction"]["task_receipts"] == ["task:TASK-pa-correction"]
    assert rows["pa-correction"]["pull_request_receipts"] == ["pr:organvm/limen#42"]
    assert rows["pa-correction"]["blocker"]["next_command"] == "owner bootstrap"
    assert rows["pa-old"]["superseded_by"] == "pa-correction"
    assert rows["pa-old"]["verified_outcome"] is True
    assert rows["pa-done"]["predicates"] == ["focused predicate"]
    assert tracked["summary"]["correction_count"] == 1


def test_partial_authority_preserves_denominator_without_fake_zero_or_traversal() -> None:
    full, _ = build_prompt_lineage_source(
        _seal(atoms=741_827, unresolved=741_827, ready=False),
        [],
        None,
        generated_at=NOW,
    )

    report = full["source_report"]
    assert report["exhaustive"] is False
    assert report["semantic_status"] == "partial"
    assert report["normalized_leaf_count"] == 0
    assert report["cursor"]["expected_atom_count"] == 741_827
    assert full["summary"]["expected_atom_count"] == 741_827


def test_exact_authority_count_mismatch_fails_closed() -> None:
    full, _ = build_prompt_lineage_source(
        _seal(atoms=2, unresolved=1),
        [_atom("pa-one")],
        _reconciliation(["pa-one"]),
        generated_at=NOW,
    )

    assert full["source_report"]["exhaustive"] is False
    assert "prompt-authority-atom-count-not-reconciled" in full["failures"]


def test_reconciliation_must_cover_the_exact_current_unresolved_set() -> None:
    atoms = [_atom("pa-one"), _atom("pa-two")]

    full, _ = build_prompt_lineage_source(
        _seal(atoms=2, unresolved=2),
        atoms,
        _reconciliation(["pa-one"]),
        generated_at=NOW,
    )

    assert full["source_report"]["exhaustive"] is False
    assert "estate-reconciliation-unresolved-set-mismatch" in full["failures"]


def test_correction_edges_and_supersession_must_resolve() -> None:
    atoms = [
        _atom("pa-correction", kind="correction", predecessors=["pa-missing"]),
        _atom(
            "pa-old",
            disposition="superseded",
            current=False,
            successor="pa-missing-successor",
            evidence=[_evidence("docs/proof.json")],
        ),
    ]

    full, _ = build_prompt_lineage_source(
        _seal(atoms=2, unresolved=1),
        atoms,
        _reconciliation(["pa-correction"]),
        generated_at=NOW,
    )

    assert full["source_report"]["exhaustive"] is False
    assert "pa-correction:predecessor-does-not-resolve" in full["failures"]
    assert "pa-old:successor-does-not-resolve" in full["failures"]


def test_prompt_bodies_never_enter_full_or_tracked_lineage_outputs() -> None:
    sentinel = "PRIVATE PROMPT BODY MUST NOT LEAVE THE CORPUS"
    atom = {**_atom("pa-private"), "intent": sentinel, "raw_prompt": sentinel}

    full, tracked = build_prompt_lineage_source(
        _seal(atoms=1, unresolved=1),
        [atom],
        _reconciliation(["pa-private"]),
        generated_at=NOW,
        input_failures=[sentinel],
    )

    assert sentinel not in json.dumps(full)
    assert sentinel not in json.dumps(tracked)
    assert set(tracked["leaves"][0]) == {
        "authority",
        "blocked",
        "disposition",
        "has_durable_receipt",
        "has_pull_request_receipt",
        "has_task_receipt",
        "is_current_intent",
        "kind",
        "leaf_key",
        "superseded",
        "unmatched",
        "verified_outcome",
    }


def test_tracked_projection_is_bounded_without_changing_complete_leaf_count() -> None:
    atoms = [_atom(f"pa-{index}") for index in range(5)]

    full, tracked = build_prompt_lineage_source(
        _seal(atoms=5, unresolved=5),
        atoms,
        _reconciliation([f"pa-{index}" for index in range(5)]),
        generated_at=NOW,
        public_limit=2,
    )

    assert full["source_report"]["normalized_leaf_count"] == 5
    assert tracked["tracked_leaf_count"] == 2
    assert tracked["tracked_leaf_truncated_count"] == 3


def test_runtime_write_cannot_dirty_the_tracked_projection(tmp_path: Path) -> None:
    seal = tmp_path / "seal.json"
    seal.write_text(json.dumps(_seal(atoms=9, unresolved=9, ready=False)), encoding="utf-8")
    source = tmp_path / "source.json"
    private = tmp_path / "private.json"
    tracked = tmp_path / "tracked.json"
    common = [
        sys.executable,
        str(SCRIPT),
        "--authority-seal",
        str(seal),
        "--source-report",
        str(source),
        "--private-output",
        str(private),
        "--tracked-output",
        str(tracked),
    ]

    first = subprocess.run([*common, "--write"], check=False, capture_output=True, text=True)

    assert first.returncode == 0
    assert source.is_file()
    assert private.is_file()
    assert not tracked.exists()

    second = subprocess.run([*common, "--write-tracked"], check=False, capture_output=True, text=True)

    assert second.returncode == 0
    assert tracked.is_file()
