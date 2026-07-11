from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prompt-priority-map.py"
DIGEST = "a" * 64


def _load():
    spec = importlib.util.spec_from_file_location("prompt_priority_map", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _configure(ppm, tmp_path: Path) -> None:
    ppm.ROOT = tmp_path
    ppm.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    ppm.PROMPT_INDEX = ppm.PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
    ppm.ATOM_INDEX = tmp_path / "docs" / "prompt-atom-ledger.json"
    ppm.CODEX_INDEX = ppm.PRIVATE_ROOT / "lifecycle" / "codex-session-lifecycle.json"
    ppm.ATTACK_INDEX = ppm.PRIVATE_ROOT / "lifecycle" / "session-attack-paths.json"
    ppm.BLOCKER_INDEX = ppm.PRIVATE_ROOT / "lifecycle" / "session-lifecycle-blockers.json"
    ppm.CAPABILITY_INDEX = ppm.PRIVATE_ROOT / "lifecycle" / "capability-substrate-index.json"
    ppm.DOC_PATH = tmp_path / "docs" / "prompt-priority-map.md"
    ppm.PRIVATE_INDEX = ppm.PRIVATE_ROOT / "lifecycle" / "prompt-priority-map.json"
    ppm.ATOM_CHECK_RECEIPT = ppm.PRIVATE_ROOT / "prompt-atoms" / "prompt-atom-check-receipt.json"


def _projection(*, atoms: list[dict], scope: str = "all", validation_ok: bool = True) -> dict:
    disposition_counts: dict[str, int] = {}
    kind_counts: dict[str, int] = {}
    for atom in atoms:
        disposition = str((atom.get("outcome") or {}).get("disposition") or "unassessed")
        disposition_counts[disposition] = disposition_counts.get(disposition, 0) + 1
        kind = str(atom.get("kind") or "ask")
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
    return {
        "version": 1,
        "semantic_digest": DIGEST,
        "policy_digest": "b" * 64,
        "source_cursor_digest": "c" * 64,
        "source_scope": {
            "scope": scope,
            "target_scope": "all",
            "pending_files": 0,
            "source_error_count": 0,
            "source_manifest_digest": "d" * 64,
            "adapter_gaps": [],
            "adapter_gap_routes": [],
        },
        "coverage": {
            "atoms": len(atoms),
            "current_intents": sum(1 for atom in atoms if atom.get("is_current_intent", True)),
            "current_unresolved_atoms": sum(
                1
                for atom in atoms
                if atom.get("is_current_intent", True)
                and str((atom.get("outcome") or {}).get("disposition") or "unassessed") not in {"done", "superseded"}
            ),
        },
        "counts": {
            "dispositions": disposition_counts,
            "kinds": kind_counts,
        },
        "validation": {"ok": validation_ok, "errors": [] if validation_ok else ["fixture failure"]},
        "atoms": atoms,
    }


def _write_projection(ppm, payload: dict) -> None:
    material = dict(payload)
    material.pop("projection_digest", None)
    material["projection_digest"] = ppm.canonical_digest(material)
    ppm.ATOM_INDEX.parent.mkdir(parents=True, exist_ok=True)
    ppm.ATOM_INDEX.write_text(json.dumps(material), encoding="utf-8")
    receipt = {
        "version": 1,
        "kind": "prompt_atom_projection_check",
        "checker": "limen.prompt_corpus.check_ledger",
        "result": "pass",
        "projection_digest": material["projection_digest"],
        "projection_file_sha256": hashlib.sha256(ppm.ATOM_INDEX.read_bytes()).hexdigest(),
        "semantic_digest": material["semantic_digest"],
        "policy_digest": material["policy_digest"],
        "source_cursor_digest": material["source_cursor_digest"],
    }
    ppm.ATOM_CHECK_RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    ppm.ATOM_CHECK_RECEIPT.write_text(json.dumps(receipt), encoding="utf-8")
    ppm.ATOM_CHECK_RECEIPT.chmod(0o600)


def _unresolved_atom(
    atom_id: str,
    score: float,
    *,
    owner: str | None = None,
    route: str | None = None,
) -> dict:
    return {
        "atom_id": atom_id,
        "kind": "correction",
        "authority": "operator",
        "priority_score": score,
        "priority_reasons": ["system_leverage"],
        "dimensions": {"system_leverage": 1.0},
        "outcome": {"disposition": "unassessed", "owner": owner, "owner_route": route},
        "is_current_intent": True,
    }


def test_prompt_priority_map_builds_redacted_batches_without_raw_text(tmp_path: Path):
    ppm = _load()
    _configure(ppm, tmp_path)

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
    ppm.CAPABILITY_INDEX.write_text(
        json.dumps({"activation_queue": [{"name": "artifact-resurfacing"}]}), encoding="utf-8"
    )
    _write_projection(
        ppm,
        _projection(
            atoms=[
                {
                    "atom_id": "pa-current",
                    "intent": "RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR",
                    "kind": "correction",
                    "authority": "operator",
                    "priority_score": 99.0,
                    "priority_reasons": ["system_leverage"],
                    "dimensions": {"system_leverage": 1.0},
                    "outcome": {
                        "disposition": "unassessed",
                        "owner": "organvm/limen",
                        "owner_route": "TABVLARIVS/prompt-control",
                    },
                    "is_current_intent": True,
                },
                {
                    "atom_id": "pa-done",
                    "intent": "also private",
                    "kind": "ask",
                    "authority": "operator",
                    "priority_score": 80.0,
                    "priority_reasons": ["magnitude"],
                    "dimensions": {"magnitude": 1.0},
                    "outcome": {"disposition": "done"},
                    "is_current_intent": True,
                },
            ]
        ),
    )

    snapshot = ppm.build_snapshot(batch_size=2)
    markdown = ppm.render_markdown(snapshot, limit=10)
    ppm.write_outputs(snapshot, markdown)

    assert snapshot["coverage"]["prioritized_prompt_events"] == 5
    assert snapshot["coverage"]["unique_prompt_hashes"] == 4
    assert snapshot["coverage"]["prompt_atoms"] == 2
    assert snapshot["coverage"]["current_unresolved_prompt_atoms"] == 1
    expected_control = {
        "authority": "prompt_atom_projection",
        "healthy": True,
        "scope": "all",
        "governing_unit": "atom_id",
        "semantic_digest": DIGEST,
        "policy_digest": "b" * 64,
        "source_cursor_digest": "c" * 64,
        "projection_form": "full",
        "legacy_can_override": False,
    }
    assert all(snapshot["control"].get(key) == value for key, value in expected_control.items())
    assert snapshot["control"]["projection_digest"]
    assert snapshot["control"]["private_check"]["result"] == "pass"
    assert snapshot["atom_control_queue"][0]["atom_id"] == "pa-current"
    assert snapshot["atom_control_queue"][0]["owner"] == "organvm/limen"
    assert snapshot["atom_control_queue"][0]["route"] == "TABVLARIVS/prompt-control"
    assert snapshot["atom_owner_queues"][0]["atom_ids"] == ["pa-current"]
    legacy = snapshot["legacy_compatibility"]
    assert legacy["session_items"][0]["session_key"] == "session-a"
    assert legacy["session_items"][0]["lane"] == "preserve"
    assert legacy["session_items"][1]["lane"] == "parked-secret"
    assert {unit["prompt_hash"] for unit in legacy["prompt_units"]} == {
        "hash-a",
        "hash-b",
        "hash-c",
        "hash-secret",
    }
    assert any(batch["lane"] == "preserve" for batch in legacy["review_batches"])
    assert all(batch["governs_execution"] is False for batch in legacy["review_batches"])
    assert legacy["authoritative"] is False
    assert legacy["governs_execution"] is False
    assert "review_batches" not in snapshot
    assert "session_items" not in snapshot
    assert "RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR" not in json.dumps(snapshot)
    assert "RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR" not in markdown
    assert "Prompt Priority Map" in markdown
    assert "governing unit is an individual ask atom" in markdown
    assert "Legacy Review Batches (compatibility only)" in markdown
    assert "They are not dispatch queues" in markdown
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


def test_missing_atom_projection_fails_before_legacy_fallback(tmp_path: Path):
    ppm = _load()
    _configure(ppm, tmp_path)
    ppm.PROMPT_INDEX.parent.mkdir(parents=True)
    ppm.PROMPT_INDEX.write_text(json.dumps({"sessions": [{"prompt_event_count": 999}]}))

    with pytest.raises(ppm.AtomProjectionError, match="missing authoritative atom projection"):
        ppm.build_snapshot(batch_size=10)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda payload: payload["validation"].update(ok=False, errors=["bad"]), "validation is not PASS"),
        (lambda payload: payload["source_scope"].update(scope="partial:all"), "scope must be exact all/all"),
        (lambda payload: payload["source_scope"].update(pending_files=3), "pending source files"),
        (lambda payload: payload["source_scope"].update(source_error_count=1), "source errors"),
    ],
)
def test_invalid_or_partial_atom_projection_fails_closed(tmp_path: Path, mutate, message: str):
    ppm = _load()
    _configure(ppm, tmp_path)
    payload = _projection(atoms=[_unresolved_atom("pa-one", 50.0)])
    mutate(payload)
    _write_projection(ppm, payload)

    with pytest.raises(ppm.AtomProjectionError, match=message):
        ppm.build_snapshot(batch_size=10)


def test_truncated_redacted_atom_projection_is_not_operational(tmp_path: Path):
    ppm = _load()
    _configure(ppm, tmp_path)
    payload = _projection(atoms=[_unresolved_atom("pa-one", 50.0)])
    payload.pop("atoms")
    payload["unresolved_atoms"] = [
        {
            "atom_id": "pa-one",
            "kind": "ask",
            "authority": "operator",
            "priority_score": 50.0,
            "priority_reasons": ["magnitude"],
            "dimensions": {"magnitude": 1.0},
            "disposition": "unassessed",
        }
    ]
    payload["unresolved_atoms_truncated"] = 12
    payload["counts"]["kinds"] = {"ask": 1}
    _write_projection(ppm, payload)

    with pytest.raises(ppm.AtomProjectionError, match="truncated by 12"):
        ppm.build_snapshot(batch_size=10)


def test_complete_redacted_projection_builds_atom_id_owner_queue(tmp_path: Path):
    ppm = _load()
    _configure(ppm, tmp_path)
    payload = _projection(atoms=[_unresolved_atom("pa-redacted", 72.0)])
    payload.pop("atoms")
    payload["unresolved_atoms"] = [
        {
            "atom_id": "pa-redacted",
            "kind": "ask",
            "authority": "operator",
            "priority_score": 72.0,
            "priority_reasons": ["cost_of_delay"],
            "dimensions": {"cost_of_delay": 0.9},
            "disposition": "not_done",
            "owner": "organvm/limen",
            "owner_route": "TABVLARIVS/atom-intake",
        }
    ]
    payload["unresolved_atoms_truncated"] = 0
    payload["counts"] = {
        "dispositions": {"not_done": 1},
        "kinds": {"ask": 1},
    }
    _write_projection(ppm, payload)

    snapshot = ppm.build_snapshot(batch_size=10)

    assert snapshot["control"]["projection_form"] == "redacted"
    assert snapshot["atom_owner_queues"] == [
        {
            "queue_id": snapshot["atom_owner_queues"][0]["queue_id"],
            "owner": "organvm/limen",
            "route": "TABVLARIVS/atom-intake",
            "routed": True,
            "atom_count": 1,
            "atom_ids": ["pa-redacted"],
            "top_priority_score": 72.0,
            "dispositions": {"not_done": 1},
        }
    ]


def test_redacted_projection_allows_historical_unresolved_noncurrent_atoms(tmp_path: Path):
    ppm = _load()
    _configure(ppm, tmp_path)
    payload = _projection(
        atoms=[
            _unresolved_atom("pa-current", 72.0),
            {**_unresolved_atom("pa-historical", 40.0), "is_current_intent": False},
        ]
    )
    payload.pop("atoms")
    payload["unresolved_atoms"] = [
        {
            "atom_id": "pa-current",
            "kind": "correction",
            "authority": "operator",
            "priority_score": 72.0,
            "priority_reasons": ["cost_of_delay"],
            "dimensions": {"cost_of_delay": 0.9},
            "disposition": "unassessed",
        }
    ]
    payload["unresolved_atoms_truncated"] = 0
    _write_projection(ppm, payload)

    snapshot = ppm.build_snapshot(batch_size=10)

    assert [row["atom_id"] for row in snapshot["atom_control_queue"]] == ["pa-current"]


def test_atom_owner_queue_order_is_independent_of_legacy_session_scores(tmp_path: Path):
    ppm = _load()
    _configure(ppm, tmp_path)
    _write_projection(
        ppm,
        _projection(
            atoms=[
                _unresolved_atom("pa-low", 20.0, owner="owner-low", route="route-low"),
                _unresolved_atom("pa-high", 95.0, owner="owner-high", route="route-high"),
                _unresolved_atom("pa-unrouted", 99.0),
            ]
        ),
    )
    ppm.PROMPT_INDEX.parent.mkdir(parents=True)
    ppm.PROMPT_INDEX.write_text(
        json.dumps(
            {
                "sessions": [
                    {
                        "session_key": "legacy-winner",
                        "source": "codex-sessions",
                        "prompt_event_count": 5000,
                        "prompt_hashes": ["legacy-hash"] * 5000,
                        "prompt_bytes": 999999,
                        "last_event": "2099-01-01T00:00:00Z",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    snapshot = ppm.build_snapshot(batch_size=10)

    assert [row["atom_id"] for row in snapshot["atom_control_queue"]] == [
        "pa-unrouted",
        "pa-high",
        "pa-low",
    ]
    assert snapshot["atom_owner_queues"][0]["atom_ids"] == ["pa-unrouted"]
    assert snapshot["atom_owner_queues"][1]["atom_ids"] == ["pa-high"]
    assert all("legacy" not in atom_id for queue in snapshot["atom_owner_queues"] for atom_id in queue["atom_ids"])
    assert snapshot["legacy_compatibility"]["review_batches"][0]["governs_execution"] is False
    assert "review_batches" not in snapshot


def test_projection_digest_is_recomputed_before_priority_use(tmp_path: Path):
    ppm = _load()
    _configure(ppm, tmp_path)
    payload = _projection(atoms=[_unresolved_atom("pa-one", 50.0)])
    _write_projection(ppm, payload)
    tampered = json.loads(ppm.ATOM_INDEX.read_text(encoding="utf-8"))
    tampered["unresolved_atoms_truncated"] = 0
    ppm.ATOM_INDEX.write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(ppm.AtomProjectionError, match="projection_digest"):
        ppm.build_snapshot(batch_size=10)


@pytest.mark.parametrize("gap_field", ["adapter_gaps", "adapter_gap_routes"])
def test_adapter_gaps_or_routes_block_priority_authority(tmp_path: Path, gap_field: str):
    ppm = _load()
    _configure(ppm, tmp_path)
    payload = _projection(atoms=[_unresolved_atom("pa-one", 50.0)])
    payload["source_scope"][gap_field] = [
        "agy-cli-conversations"
        if gap_field == "adapter_gaps"
        else {
            "source": "agy-cli-conversations",
            "owner": "organvm/limen",
            "route": "issue:641",
        }
    ]
    _write_projection(ppm, payload)

    with pytest.raises(ppm.AtomProjectionError, match="adapter gaps or routes"):
        ppm.build_snapshot(batch_size=10)


def test_projection_counts_must_reconcile_with_complete_rows(tmp_path: Path):
    ppm = _load()
    _configure(ppm, tmp_path)
    payload = _projection(atoms=[_unresolved_atom("pa-one", 50.0)])
    payload["counts"]["dispositions"] = {"unassessed": 2}
    _write_projection(ppm, payload)

    with pytest.raises(ppm.AtomProjectionError, match="counts.dispositions"):
        ppm.build_snapshot(batch_size=10)


def test_redacted_unresolved_rows_must_match_disposition_completeness(tmp_path: Path):
    ppm = _load()
    _configure(ppm, tmp_path)
    payload = _projection(atoms=[_unresolved_atom("pa-one", 50.0)])
    payload.pop("atoms")
    payload["unresolved_atoms"] = [
        {
            "atom_id": "pa-one",
            "kind": "correction",
            "authority": "operator",
            "priority_score": 50.0,
            "priority_reasons": ["system_leverage"],
            "dimensions": {"system_leverage": 1.0},
            "disposition": "unassessed",
        }
    ]
    payload["unresolved_atoms_truncated"] = 0
    payload["coverage"] = {
        "atoms": 2,
        "current_intents": 2,
        "current_unresolved_atoms": 2,
    }
    payload["counts"] = {
        "dispositions": {"unassessed": 2},
        "kinds": {"correction": 2},
    }
    _write_projection(ppm, payload)

    with pytest.raises(ppm.AtomProjectionError, match="unresolved atom rows"):
        ppm.build_snapshot(batch_size=10)


def test_private_check_receipt_must_hash_match_exact_projection(tmp_path: Path):
    ppm = _load()
    _configure(ppm, tmp_path)
    _write_projection(ppm, _projection(atoms=[_unresolved_atom("pa-one", 50.0)]))
    receipt = json.loads(ppm.ATOM_CHECK_RECEIPT.read_text(encoding="utf-8"))
    receipt["projection_file_sha256"] = "0" * 64
    ppm.ATOM_CHECK_RECEIPT.write_text(json.dumps(receipt), encoding="utf-8")
    ppm.ATOM_CHECK_RECEIPT.chmod(0o600)

    with pytest.raises(ppm.AtomProjectionError, match="does not match projection"):
        ppm.build_snapshot(batch_size=10)
