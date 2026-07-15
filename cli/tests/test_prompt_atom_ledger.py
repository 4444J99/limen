from __future__ import annotations

import importlib.util
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "cli" / "src" / "limen" / "prompt_corpus.py"
SCRIPT = ROOT / "scripts" / "prompt-atom-ledger.py"


def _load():
    spec = importlib.util.spec_from_file_location("limen_prompt_corpus", MODULE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _paths(module, tmp_path: Path):
    return module.LedgerPaths.for_root(tmp_path)


def _cursor(module, *, scope: str = "fixture") -> dict:
    return {
        "version": 1,
        "scope": scope,
        "horizon_days": None,
        "source_manifest_digest": module.digest({"fixture": 1}),
        "files": {},
    }


def _exact_authority_snapshot(module, *, policy_digest: str = "b" * 64) -> dict:
    contract = module.current_source_adapter_contract()
    return {
        "semantic_digest": "a" * 64,
        "policy_digest": policy_digest,
        "source_cursor_digest": "c" * 64,
        "source_scope": {
            "scope": "all",
            "target_scope": "all",
            "all_baseline_complete": True,
            "scanner_version": contract["scanner_version"],
            "horizon_days": None,
            "pending_files": 0,
            "source_unit_count": 0,
            "unsupported_source_count": 0,
            "unresolved_unit_count": 0,
            "excluded_source_count": 0,
            "adapted_source_count": 0,
            "source_manifest_digest": "d" * 64,
            "all_source_manifest_digest": "d" * 64,
            "source_units_digest": "e" * 64,
            "unsupported_units_digest": "f" * 64,
            "unresolved_units_digest": "1" * 64,
            "excluded_unit_receipts_digest": "2" * 64,
            "adapted_unit_receipts_digest": "3" * 64,
            "source_adapter_contract": contract,
            "source_scan_receipt": {
                "sha256": "5" * 64,
                "scanner_code_digest": "6" * 64,
                "scan_payload_digest": "7" * 64,
            },
            "source_errors": [],
            "source_families": {},
            "source_alias_blocker_counts": {},
            "adapter_gaps": [],
        },
        "coverage": {},
        "counts": {},
        "validation": {"ok": True, "errors": []},
    }


def _attest_exact_cursor(module, cursor: dict) -> dict:
    cursor.setdefault("base_revision", 0)
    cursor.setdefault("base_cursor_digest", module.cursor_digest({}))
    cursor.setdefault(
        "source_discovery_spec",
        {
            "version": 1,
            "regular": [],
            "gemini_root": None,
            "opencode_db": "/definitely/missing/opencode.db",
            "agy_conversations_root": "/definitely/missing/agy",
        },
    )
    cursor.setdefault("resource_limits", {"max_discovery_units": 100})
    cursor.setdefault("source_container_signatures", {"opencode-db": None})
    module.attest_source_scan(
        cursor,
        scanner_code_digest=module.current_source_scanner_code_digest(),
    )
    return cursor


def _event(
    text: str,
    *,
    event_ref: str,
    timestamp: str = "2026-07-11T12:00:00Z",
    provenance: str = "operator_typed",
    authority: str = "operator",
    atoms: list[dict] | None = None,
) -> dict:
    row = {
        "source": "fixture",
        "session_ref": "session-one",
        "event_ref": event_ref,
        "timestamp": timestamp,
        "text": text,
        "body_kind": "direct",
        "provenance": provenance,
        "authority": authority,
    }
    if atoms is not None:
        row["atoms"] = atoms
    return row


def test_private_session_corpus_env_owns_default_journal_root(tmp_path: Path, monkeypatch):
    corpus = _load()
    durable = tmp_path / "durable-session-corpus"
    monkeypatch.setenv("LIMEN_PRIVATE_SESSION_CORPUS", str(durable))

    paths = corpus.LedgerPaths.for_root(tmp_path / "checkout")

    assert paths.private_dir == durable / "prompt-atoms"
    assert paths.public_snapshot == tmp_path / "checkout" / "docs" / "prompt-atom-ledger.json"
    assert paths.public_seal == tmp_path / "checkout" / "docs" / "prompt-authority-seal.json"


def test_compound_prompt_yields_distinct_asks_and_correction(tmp_path: Path):
    corpus = _load()
    snapshot = corpus.update_ledger(
        _paths(corpus, tmp_path),
        events=[
            _event(
                "Build the registry. Verify the exact-head receipt. No, keep selection dynamic.",
                event_ref="compound",
            )
        ],
    )

    assert snapshot["coverage"]["occurrences"] == 1
    assert snapshot["coverage"]["atoms"] == 3
    assert [atom["kind"] for atom in snapshot["atoms"]].count("correction") == 1
    correction = next(atom for atom in snapshot["atoms"] if atom["kind"] == "correction")
    assert correction["predecessor_ids"] == []
    assert correction["candidate_predecessor_ids"]
    assert correction["lineage_evidence"] is None
    assert snapshot["validation"]["ok"] is True


def test_atomization_never_truncates_large_compound_prompt(tmp_path: Path):
    corpus = _load()
    asks = [f"Handle independent ask {index}." for index in range(40)]
    snapshot = corpus.update_ledger(
        _paths(corpus, tmp_path),
        events=[_event(" ".join(asks), event_ref="large-compound")],
        cursor=_cursor(corpus),
    )

    assert snapshot["coverage"]["atoms"] == len(asks)


def test_transport_echo_is_preserved_without_inflating_operator_atoms(tmp_path: Path):
    corpus = _load()
    text = "Ship the owner receipt."
    snapshot = corpus.update_ledger(
        _paths(corpus, tmp_path),
        events=[
            _event(text, event_ref="response-item"),
            _event(
                text,
                event_ref="event-msg",
                provenance="transport_echo",
                authority="derived",
            ),
        ],
    )

    assert snapshot["coverage"]["occurrences"] == 2
    assert snapshot["coverage"]["operator_occurrences"] == 1
    assert snapshot["coverage"]["atoms"] == 1
    duplicate = next(row for row in snapshot["occurrences"] if row["provenance"] == "transport_echo")
    assert duplicate["excluded_reason"] == "transport_echo"


def test_explicit_correction_edge_moves_current_intent(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    first = corpus.update_ledger(
        paths,
        events=[_event("Use a fixed provider list.", event_ref="old")],
        cursor=_cursor(corpus),
    )
    predecessor = first["atoms"][0]["atom_id"]
    lineage_id = first["atoms"][0]["lineage_id"]

    second = corpus.update_ledger(
        paths,
        events=[
            _event(
                "No, derive provider capability at runtime.",
                event_ref="new",
                timestamp="2026-07-11T12:01:00Z",
                atoms=[
                    {
                        "text": "No, derive provider capability at runtime.",
                        "kind": "correction",
                        "lineage_id": lineage_id,
                        "relation": "corrects",
                        "predecessor_ids": [predecessor],
                        "classifier_provenance": "fixture-adapter",
                        "lineage_evidence": {
                            "kind": "semantic_adapter",
                            "classifier_provenance": "fixture-adapter",
                            "confidence": 1.0,
                        },
                    }
                ],
            )
        ],
    )

    by_id = {atom["atom_id"]: atom for atom in second["atoms"]}
    assert by_id[predecessor]["is_current_intent"] is False
    successor = next(atom for atom in second["atoms"] if atom["atom_id"] != predecessor)
    assert successor["is_current_intent"] is True
    assert successor["predecessor_ids"] == [predecessor]
    assert second["coverage"]["current_unresolved_atoms"] == 1


def test_runtime_dimensions_let_short_system_correction_outrank_volume(tmp_path: Path):
    corpus = _load()
    low = "Document the minor note with several extra words so the request is visibly longer."
    high = "No, fix the control plane."
    snapshot = corpus.update_ledger(
        _paths(corpus, tmp_path),
        events=[
            _event(
                low,
                event_ref="low",
                atoms=[
                    {
                        "text": low,
                        "kind": "ask",
                        "dimensions": {
                            "system_leverage": 0.05,
                            "dependency_impact": 0.0,
                            "cost_of_delay": 0.0,
                        },
                    }
                ],
            ),
            _event(
                high,
                event_ref="high",
                atoms=[
                    {
                        "text": high,
                        "kind": "correction",
                        "dimensions": {
                            "operator_emphasis": 1.0,
                            "system_leverage": 1.0,
                            "dependency_impact": 1.0,
                            "cost_of_delay": 1.0,
                        },
                    }
                ],
            ),
        ],
        cursor=_cursor(corpus),
    )

    scores = {atom["intent"]: atom["priority_score"] for atom in snapshot["atoms"]}
    assert scores[high] > scores[low]


def test_done_fails_closed_until_referenced_predicate_passes(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    first = corpus.update_ledger(
        paths,
        events=[_event("Land the exact head.", event_ref="one")],
        cursor=_cursor(corpus),
    )
    atom_id = first["atoms"][0]["atom_id"]

    try:
        corpus.update_ledger(
            paths,
            outcomes=[{"atom_id": atom_id, "disposition": "done", "evidence": []}],
        )
    except ValueError as exc:
        assert "done requires" in str(exc)
    else:
        raise AssertionError("invalid done outcome was appended")

    valid = corpus.update_ledger(
        paths,
        outcomes=[
            {
                "atom_id": atom_id,
                "disposition": "done",
                "owner": "organvm/limen",
                "assessed_at": "2026-07-11T12:05:00Z",
                "evidence": [_passing_receipt(paths, atom_id)],
            }
        ],
    )
    assert valid["validation"]["ok"] is True
    assert valid["counts"]["dispositions"] == {"done": 1}


def test_public_projection_never_contains_raw_prompt_text(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    secret_text = "PRIVATE_RAW_PROMPT_DO_NOT_TRACK"
    corpus.update_ledger(
        paths,
        events=[_event(secret_text, event_ref="secret")],
        cursor=_cursor(corpus),
    )

    occurrence = corpus.load_event_journal(paths.event_journal)[0][0]
    assert corpus.read_raw_object(paths, occurrence["raw_object"]) == secret_text
    assert secret_text not in paths.private_snapshot.read_text(encoding="utf-8")
    assert secret_text not in paths.public_snapshot.read_text(encoding="utf-8")
    assert secret_text not in paths.public_markdown.read_text(encoding="utf-8")


def test_cursor_advance_without_projection_fails_closed(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    cursor = _cursor(corpus)
    corpus.update_ledger(
        paths,
        events=[_event("Keep the cursor honest.", event_ref="cursor")],
        cursor=cursor,
    )
    cursor["files"] = {"new-source": {"size": 1, "mtime_ns": 2}}
    corpus.atomic_write_text(paths.cursor, json.dumps(cursor))

    errors = corpus.check_ledger(paths)
    assert any("cursor changed" in error for error in errors)


def test_runtime_repeat_limit_fails_unassessed_lineage_closed(tmp_path: Path):
    corpus = _load()
    events = [
        _event(
            "Please close the same missing loop.",
            event_ref=f"repeat-{index}",
            timestamp=f"2026-07-11T12:{index:02d}:00Z",
        )
        for index in range(16)
    ]
    snapshot = corpus.update_ledger(_paths(corpus, tmp_path), events=events, cursor=_cursor(corpus))

    assert snapshot["validation"]["ok"] is False
    assert "operator repeats exceed 15" in " ".join(snapshot["validation"]["errors"])


def test_two_concurrent_drains_are_idempotent(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    events.write_text(
        json.dumps(_event("Concurrently ingest me once.", event_ref="same")) + "\n",
        encoding="utf-8",
    )
    private_root = tmp_path / "private"
    public_markdown = tmp_path / "prompt-atom-ledger.md"
    public_snapshot = tmp_path / "prompt-atom-ledger.json"
    command = [
        sys.executable,
        str(SCRIPT),
        "--root",
        str(tmp_path),
        "--private-root",
        str(private_root),
        "--public-markdown",
        str(public_markdown),
        "--public-snapshot",
        str(public_snapshot),
        "--events-jsonl",
        str(events),
        "--write",
    ]
    first = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    second = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    first_out, first_err = first.communicate(timeout=20)
    second_out, second_err = second.communicate(timeout=20)
    assert first.returncode == 0, first_out + first_err
    assert second.returncode == 0, second_out + second_err

    event_journal = private_root / "prompt-atoms" / "prompt-events.jsonl"
    assert len([line for line in event_journal.read_text().splitlines() if line]) == 1
    before = public_snapshot.stat().st_mtime_ns
    third = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
    assert third.returncode == 0, third.stdout + third.stderr
    assert public_snapshot.stat().st_mtime_ns == before


def test_semantic_candidates_are_union_with_structural_coverage(tmp_path: Path):
    corpus = _load()
    snapshot = corpus.update_ledger(
        _paths(corpus, tmp_path),
        events=[
            _event(
                "Build the registry. Verify the receipt.",
                event_ref="incomplete-classifier",
                atoms=[
                    {
                        "text": "Build the registry.",
                        "kind": "ask",
                        "classifier_provenance": "fixture-adapter",
                    }
                ],
            )
        ],
        cursor=_cursor(corpus),
    )

    assert snapshot["coverage"]["atoms"] == 2
    assert {atom["atomization_mode"] for atom in snapshot["atoms"]} == {
        "semantic_adapter",
        "structural_fallback",
    }
    assert snapshot["validation"]["ok"] is True


def test_semantic_candidate_cannot_replace_exact_covered_source_text(tmp_path: Path):
    corpus = _load()
    snapshot = corpus.update_ledger(
        _paths(corpus, tmp_path),
        events=[
            _event(
                "Preserve the retained root.",
                event_ref="hostile-paraphrase",
                atoms=[
                    {
                        "text": "Delete the retained root.",
                        "kind": "ask",
                        "coverage_segment_indexes": [0],
                        "source_segments": ["Preserve the retained root."],
                        "classifier_provenance": "hostile-fixture",
                        "classification_confidence": 1.0,
                    }
                ],
            )
        ],
        cursor=_cursor(corpus),
    )

    atom = snapshot["atoms"][0]
    assert atom["intent"] == "Preserve the retained root."
    assert atom["classifier_label_hash"] == corpus.digest("delete the retained root")
    assert "Delete" not in atom["intent"]
    assert snapshot["validation"]["ok"] is True


def test_raw_fenced_body_round_trips_and_private_files_are_private(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    raw = "Implement the parser.\n```python\nvalue = 1\n```\nVerify the output."
    snapshot = corpus.update_ledger(
        paths,
        events=[_event(raw, event_ref="fenced")],
        cursor=_cursor(corpus),
    )
    occurrence = snapshot["occurrences"][0]

    assert corpus.read_raw_object(paths, occurrence["raw_object"]) == raw
    assert "value = 1" in {atom["intent"] for atom in snapshot["atoms"]}
    assert paths.event_journal.stat().st_mode & 0o777 == 0o600
    assert paths.private_snapshot.stat().st_mode & 0o777 == 0o600
    assert paths.public_snapshot.stat().st_mode & 0o777 == 0o644


def test_event_journal_row_is_transactional_and_incomplete_row_fails_check(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    corpus.update_ledger(
        paths,
        events=[_event("Preserve this event atomically.", event_ref="atomic")],
        cursor=_cursor(corpus),
    )
    row = json.loads(paths.event_journal.read_text(encoding="utf-8").splitlines()[0])
    assert row["occurrence"]["atom_ids"] == [row["atoms"][0]["atom_id"]]

    with paths.event_journal.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"occurrence": {"occurrence_id": "po-crash"}}) + "\n")
    errors = corpus.check_ledger(paths)
    assert any("lacks occurrence/atoms" in error or "compact checkpoint" in error for error in errors)


def test_malformed_journal_and_tampered_public_projection_fail_closed_and_repair(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    corpus.update_ledger(
        paths,
        events=[_event("Keep projections reconstructible.", event_ref="projection")],
        cursor=_cursor(corpus),
    )
    original = paths.public_snapshot.read_bytes()
    public = json.loads(original)
    public["coverage"]["atoms"] = 999
    paths.public_snapshot.write_text(json.dumps(public, indent=2, sort_keys=True) + "\n")
    assert any("public prompt projection" in error for error in corpus.check_ledger(paths))

    repaired = corpus.update_ledger(paths)
    assert repaired["write_changed"] is True
    assert paths.public_snapshot.read_bytes() == original
    assert corpus.check_ledger(paths) == []

    with paths.outcome_journal.open("a", encoding="utf-8") as handle:
        handle.write("{malformed\n")
    assert any("malformed JSON" in error for error in corpus.check_ledger(paths))


def _bind_github_receipt(paths, evidence: dict) -> dict:
    bound = {
        key: value
        for key, value in evidence.items()
        if key not in {"verification_receipt_ref", "verification_receipt_sha256"}
    }
    atom_id = str((bound.get("subject_atom_ids") or ["unknown"])[0])
    receipt_ref = f"docs/github-proof-{atom_id}.json"
    receipt = paths.root / receipt_ref
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(
        json.dumps(
            {
                "schema": "limen.github-verification.v1",
                "exit_code": 0,
                "evidence": bound,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    bound["verification_receipt_ref"] = receipt_ref
    bound["verification_receipt_sha256"] = hashlib.sha256(receipt.read_bytes()).hexdigest()
    return bound


def _passing_receipt(paths, atom_id: str, *, owner: str = "organvm/limen") -> dict:
    return _bind_github_receipt(
        paths,
        {
            "kind": "github_pr",
            "ref": "https://github.com/organvm/limen/pull/1",
            "predicate": "exact-head CI",
            "result": "pass",
            "verified_at": "2026-07-11T12:05:00Z",
            "owner": owner,
            "subject_atom_ids": [atom_id],
            "verifier": "github_api",
            "state": "merged",
            "head_sha": "a" * 40,
            "merge_commit_sha": "b" * 40,
            "reachable_from_default": True,
        },
    )


def test_outcome_evidence_residuals_and_unknown_atoms_fail_closed(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    first = corpus.update_ledger(
        paths,
        events=[_event("Finish the actual ask.", event_ref="outcome")],
        cursor=_cursor(corpus),
    )
    atom_id = first["atoms"][0]["atom_id"]

    try:
        corpus.update_ledger(
            paths,
            outcomes=[
                {
                    "atom_id": atom_id,
                    "disposition": "partial",
                    "owner": "organvm/limen",
                    "assessed_at": "2026-07-11T12:05:00Z",
                    "residual_atom_ids": ["pa-does-not-exist"],
                    "evidence": [_passing_receipt(paths, atom_id)],
                }
            ],
        )
    except ValueError as exc:
        assert "residual atom ids" in str(exc)
    else:
        raise AssertionError("invalid partial outcome was appended")

    try:
        corpus.update_ledger(
            paths,
            outcomes=[{"atom_id": "pa-unknown", "disposition": "unassessed"}],
        )
    except ValueError as exc:
        assert "unknown atoms" in str(exc)
    else:
        raise AssertionError("unknown outcome atom was accepted")


def test_evidence_ref_injection_and_self_supersession_do_not_close(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    first = corpus.update_ledger(
        paths,
        events=[_event("Do not accept fake closure.", event_ref="fake")],
        cursor=_cursor(corpus),
    )
    atom_id = first["atoms"][0]["atom_id"]
    unsafe = dict(_passing_receipt(paths, atom_id))
    unsafe.update({"kind": "predicate_receipt", "ref": "docs/x.md|PRIVATE"})
    try:
        corpus.update_ledger(
            paths,
            outcomes=[
                {
                    "atom_id": atom_id,
                    "disposition": "superseded",
                    "owner": "organvm/limen",
                    "assessed_at": "2026-07-11T12:05:00Z",
                    "successor_atom_id": atom_id,
                    "evidence": [unsafe],
                }
            ],
        )
    except ValueError as exc:
        assert "typed, canonical" in str(exc)
        assert "distinct newer successor" in str(exc)
    else:
        raise AssertionError("unsafe supersession was appended")


def test_public_projection_is_redacted_and_has_complete_opaque_queue(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    corpus.update_ledger(
        paths,
        events=[_event("A private but unresolved ask.", event_ref="redacted")],
        cursor=_cursor(corpus),
    )
    public = json.loads(paths.public_snapshot.read_text(encoding="utf-8"))

    assert public["unresolved_atoms_truncated"] == 0
    assert len(public["unresolved_atoms"]) == 1
    assert public["coverage"]["current_unresolved_atoms"] == 1
    assert "lineage_id" not in public["unresolved_atoms"][0]
    assert "private but unresolved" not in paths.public_snapshot.read_text(encoding="utf-8")
    assert corpus.check_ledger(paths) == []


def test_prompt_authority_seal_is_counts_hash_only_private_safe_and_schema_bound():
    corpus = _load()
    private_prompt = "PRIVATE_RAW_PROMPT_DO_NOT_PUBLISH"
    private_home = "/Users/example/.claude/projects/private/session.jsonl"
    private_volume = "/Volumes/Private/opencode.db"
    snapshot = {
        "semantic_digest": "a" * 64,
        "policy_digest": "b" * 64,
        "source_cursor_digest": "c" * 64,
        "source_scope": {
            "scope": "partial:all",
            "target_scope": "all",
            "all_baseline_complete": False,
            "horizon_days": None,
            "pending_files": 0,
            "source_unit_count": 17,
            "unsupported_source_count": 3,
            "unresolved_unit_count": 7,
            "excluded_source_count": 4,
            "adapted_source_count": 5,
            "source_manifest_digest": "d" * 64,
            "all_source_manifest_digest": None,
            "source_units_digest": "e" * 64,
            "unsupported_units_digest": "f" * 64,
            "unresolved_units_digest": "1" * 64,
            "excluded_unit_receipts_digest": "2" * 64,
            "adapted_unit_receipts_digest": "3" * 64,
            "source_adapter_contract": {"digest": "4" * 64},
            "source_scan_receipt": {
                "sha256": "5" * 64,
                "scanner_code_digest": "6" * 64,
                "scan_payload_digest": "7" * 64,
            },
            "source_errors": [
                f"claude-projects:{private_home}: source path contains a symlink hop",
                f"scan-v2:opencode-db:{private_volume}: SQLite row count 900 exceeds bounded ceiling 100",
                "agy-cli-conversations:/private/agy.db: Agy prompt step could not be grounded in an exact source segment",
                f"codex-sessions:/private/codex.jsonl: novel parser failure {private_prompt}",
            ],
            "source_families": {
                "claude-projects": {
                    "discovered": 7,
                    "converged": 2,
                    "adapted": 2,
                    "excluded": 2,
                    "errors": 1,
                },
                "opencode-db": {
                    "discovered": 4,
                    "converged": 1,
                    "adapted": 1,
                    "excluded": 1,
                    "errors": 1,
                    "unsupported": 1,
                },
                "agy-cli-conversations": {
                    "discovered": 3,
                    "converged": 1,
                    "adapted": 1,
                    "excluded": 1,
                    "errors": 1,
                },
                "codex-sessions": {
                    "discovered": 2,
                    "converged": 1,
                    "adapted": 1,
                    "errors": 1,
                    "unsupported": 1,
                },
                private_home: {"discovered": 1, "unsupported": 1},
                private_prompt: {"discovered": 0},
            },
            "source_alias_blocker_counts": {"alias_changed": 1, private_home: 2},
            "adapter_gaps": ["claude-projects", private_home],
        },
        "coverage": {
            "occurrences": 100_000,
            "operator_occurrences": 75_000,
            "derived_occurrences": 25_000,
            "excluded_occurrences": 1_000,
            "atoms": 900_000,
            "current_intents": 80_000,
            "current_unresolved_atoms": 79_000,
            "lineages": 70_000,
            "assessed_atoms": 10_000,
        },
        "validation": {"ok": False, "errors": [f"atom-secret: {private_prompt}"]},
        "atoms": [{"intent": private_prompt, "source_locator": private_home}],
        "occurrences": [{"source_locator": private_volume}],
    }

    seal = corpus.prompt_authority_seal(snapshot)
    payload = corpus.prompt_authority_seal_bytes(snapshot)
    serialized = payload.decode("utf-8")

    assert seal["schema"] == "limen.prompt-authority-seal.v1"
    assert seal["schema_version"] == 1
    assert seal["authority_ready"] is False
    assert seal["validation_ok"] is False
    assert seal["totals"] == {
        "adapted": 5,
        "adapter_gaps": 2,
        "converged": 5,
        "errors": 4,
        "excluded": 4,
        "pending": 0,
        "source_units": 17,
        "unsupported": 3,
        "unresolved": 7,
        "validation_errors": 1,
    }
    assert seal["source_families"]["claude-projects"]["discovered"] == 7
    assert seal["source_alias_blocker_counts"]["alias_changed"] == 1
    assert seal["source_alias_blocker_counts"]["other"] == 2
    assert f"source-{corpus.digest(private_prompt)[:16]}" in seal["source_families"]
    assert seal["source_error_reason_counts"] == {
        "adapter_missing": 0,
        "bounded_ceiling_exceeded": 1,
        "containment_violation": 1,
        "malformed_source": 0,
        "other": 1,
        "prompt_grounding_failed": 1,
        "source_changed": 0,
        "source_unavailable": 0,
    }
    assert corpus._prompt_authority_seal_digest_valid(seal)
    assert len(payload) <= corpus.PROMPT_AUTHORITY_SEAL_MAX_BYTES
    assert "atoms" not in seal
    assert "occurrences" not in seal
    assert "unresolved_atoms" not in seal
    assert private_prompt not in serialized
    assert private_home not in serialized
    assert private_volume not in serialized
    assert "/Users/" not in serialized
    assert "/Volumes/" not in serialized
    assert "/private/" not in serialized


def test_prompt_authority_seal_ready_verdict_requires_complete_bound_evidence_and_is_derived():
    corpus = _load()
    exact_snapshot = _exact_authority_snapshot(corpus)

    seal = corpus.prompt_authority_seal(exact_snapshot)

    assert seal["validation_ok"] is True
    assert seal["authority_ready"] is True
    assert corpus._prompt_authority_seal_digest_valid(seal)

    tampered = json.loads(json.dumps(seal))
    tampered["authority_ready"] = False
    tampered["content_hash"] = corpus.digest({key: value for key, value in tampered.items() if key != "content_hash"})
    assert corpus._prompt_authority_seal_digest_valid(tampered) is False
    assert "seal authority verdict does not match its evidence" in corpus._prompt_authority_seal_schema_errors(tampered)

    missing_hash = json.loads(json.dumps(exact_snapshot))
    del missing_hash["source_scope"]["source_scan_receipt"]["scan_payload_digest"]
    incomplete = corpus.prompt_authority_seal(missing_hash)
    assert incomplete["authority_ready"] is False
    assert corpus._prompt_authority_seal_digest_valid(incomplete)


def test_prompt_authority_seal_binds_projection_alias_blockers_and_current_contract():
    corpus = _load()
    snapshot = _exact_authority_snapshot(corpus)
    public = corpus.public_projection(snapshot)
    seal = corpus.prompt_authority_seal(snapshot, public=public)

    assert seal["public_projection_digest"] == public["projection_digest"]
    assert not any(seal["source_alias_blocker_counts"].values())
    assert corpus._prompt_authority_seal_matches_public(seal, public)

    blocker_public = json.loads(json.dumps(public))
    blocker_public["source_scope"]["source_alias_blocker_counts"] = {"alias_changed": 1}
    blocker_public["projection_digest"] = corpus.digest(
        {key: value for key, value in blocker_public.items() if key != "projection_digest"}
    )
    assert corpus._prompt_authority_seal_matches_public(seal, blocker_public) is False

    leaky_alias_public = json.loads(json.dumps(public))
    leaky_alias_public["source_scope"]["source_alias_blocker_counts"] = {"/Users/private/source": 0}
    leaky_alias_public["projection_digest"] = corpus.digest(
        {key: value for key, value in leaky_alias_public.items() if key != "projection_digest"}
    )
    leaky_alias_seal = corpus.prompt_authority_seal(snapshot, public=leaky_alias_public)
    assert corpus._prompt_authority_seal_matches_public(leaky_alias_seal, leaky_alias_public) is False

    forged_ready = json.loads(json.dumps(seal))
    forged_ready["public_projection_digest"] = blocker_public["projection_digest"]
    forged_ready["source_alias_blocker_counts"]["alias_changed"] = 1
    forged_ready["content_hash"] = corpus.digest(
        {key: value for key, value in forged_ready.items() if key != "content_hash"}
    )
    assert corpus._prompt_authority_seal_digest_valid(forged_ready) is False
    assert "seal authority verdict does not match its evidence" in corpus._prompt_authority_seal_schema_errors(
        forged_ready
    )

    stale_contract_public = json.loads(json.dumps(public))
    stale_contract_public["source_scope"]["source_adapter_contract"]["adapter_ids"].append("forged-adapter")
    stale_contract_public["projection_digest"] = corpus.digest(
        {key: value for key, value in stale_contract_public.items() if key != "projection_digest"}
    )
    stale_contract_seal = corpus.prompt_authority_seal(snapshot, public=stale_contract_public)
    assert corpus._prompt_authority_seal_digest_valid(stale_contract_seal)
    assert corpus._prompt_authority_seal_matches_public(stale_contract_seal, stale_contract_public) is False


def test_prompt_authority_seal_rejects_rehashed_converged_aggregate_tamper():
    corpus = _load()
    snapshot = _exact_authority_snapshot(corpus)
    snapshot["source_scope"]["source_unit_count"] = 1
    snapshot["source_scope"]["source_families"] = {
        "codex-sessions": {
            "discovered": 1,
            "converged": 1,
            "adapted": 0,
            "excluded": 0,
            "pending": 0,
            "errors": 0,
            "unsupported": 0,
        }
    }
    seal = corpus.prompt_authority_seal(snapshot)
    assert seal["authority_ready"] is True
    assert corpus._prompt_authority_seal_digest_valid(seal)

    family_only = json.loads(json.dumps(seal))
    family_only["source_families"]["codex-sessions"]["converged"] = 999
    family_only["hashes"]["source_families"] = corpus.digest(
        {
            "families": family_only["source_families"],
            "overflow": family_only["source_family_overflow"],
        }
    )
    family_only["content_hash"] = corpus.digest(
        {key: value for key, value in family_only.items() if key != "content_hash"}
    )
    assert corpus._prompt_authority_seal_digest_valid(family_only) is False
    assert "seal source family converged counts do not match converged" in (
        corpus._prompt_authority_seal_schema_errors(family_only)
    )

    coherent_aggregate = json.loads(json.dumps(family_only))
    coherent_aggregate["totals"]["converged"] = 999
    coherent_aggregate["content_hash"] = corpus.digest(
        {key: value for key, value in coherent_aggregate.items() if key != "content_hash"}
    )
    assert corpus._prompt_authority_seal_digest_valid(coherent_aggregate) is False
    assert "seal exact-all source family coverage is incomplete" in (
        corpus._prompt_authority_seal_schema_errors(coherent_aggregate)
    )


@pytest.mark.parametrize("schema_version", [True, 1.0])
def test_prompt_authority_seal_schema_version_requires_exact_integer(schema_version):
    corpus = _load()
    seal = corpus.prompt_authority_seal(_exact_authority_snapshot(corpus))
    seal["schema_version"] = schema_version
    seal["content_hash"] = corpus.digest({key: value for key, value in seal.items() if key != "content_hash"})

    assert corpus._prompt_authority_seal_digest_valid(seal) is False
    assert "seal schema version is stale" in corpus._prompt_authority_seal_schema_errors(seal)


def test_require_all_rejects_exact_scope_without_authority_ready_seal(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    policy = corpus.load_policy(paths.policy)
    snapshot = _exact_authority_snapshot(corpus, policy_digest=corpus.digest(policy))
    del snapshot["source_scope"]["source_scan_receipt"]["scan_payload_digest"]
    public = corpus.public_projection(snapshot)
    seal = corpus.prompt_authority_seal(snapshot, public=public)
    paths.public_snapshot.parent.mkdir(parents=True, exist_ok=True)
    paths.public_snapshot.write_bytes(corpus._json_bytes(public))
    paths.public_seal.write_bytes(corpus._json_bytes(seal))
    paths.public_markdown.write_text(corpus.render_markdown(public, policy), encoding="utf-8")

    assert seal["authority_ready"] is False
    assert corpus.check_ledger(paths) == []
    assert "public prompt authority seal is not authority-ready for required all scope" in corpus.check_ledger(
        paths,
        require_scope="all",
    )


def test_prompt_authority_seal_family_cardinality_is_hard_bounded():
    corpus = _load()
    family_count = 5_000
    snapshot = {
        "semantic_digest": "a" * 64,
        "policy_digest": "b" * 64,
        "source_cursor_digest": "c" * 64,
        "source_scope": {
            "scope": "partial:all",
            "target_scope": "all",
            "source_unit_count": family_count,
            "unsupported_source_count": family_count,
            "source_families": {
                f"family-{index:05d}": {"discovered": 1, "unsupported": 1} for index in range(family_count)
            },
        },
        "coverage": {},
        "validation": {"ok": False, "errors": []},
    }

    seal = corpus.prompt_authority_seal(snapshot)
    payload = corpus.prompt_authority_seal_bytes(snapshot)

    assert len(seal["source_families"]) == corpus.PROMPT_AUTHORITY_SEAL_MAX_SOURCE_FAMILIES
    assert sum(row["discovered"] for row in seal["source_families"].values()) == family_count
    assert seal["source_family_overflow"]["count"] == (
        family_count - corpus.PROMPT_AUTHORITY_SEAL_MAX_SOURCE_FAMILIES + 1
    )
    assert len(seal["source_family_overflow"]["labels_digest"]) == 64
    assert len(payload) <= corpus.PROMPT_AUTHORITY_SEAL_MAX_BYTES


def test_prompt_authority_seal_rejects_rehashed_locator_and_private_string_leakage():
    corpus = _load()
    snapshot = {
        "semantic_digest": "a" * 64,
        "policy_digest": "b" * 64,
        "source_cursor_digest": "c" * 64,
        "source_scope": {"scope": "partial:all", "target_scope": "all", "source_families": {}},
        "coverage": {},
        "validation": {"ok": False, "errors": []},
    }
    locator_leak = corpus.prompt_authority_seal(snapshot)
    locator_leak["source_locator"] = "/Users/example/private.jsonl"
    locator_leak["content_hash"] = corpus.digest(
        {key: value for key, value in locator_leak.items() if key != "content_hash"}
    )
    private_string_leak = corpus.prompt_authority_seal(snapshot)
    private_string_leak["source_families"] = {
        "PRIVATE_RAW_PROMPT_DO_NOT_PUBLISH": {field: 0 for field in corpus._PROMPT_AUTHORITY_FAMILY_FIELDS}
    }
    private_string_leak["content_hash"] = corpus.digest(
        {key: value for key, value in private_string_leak.items() if key != "content_hash"}
    )
    scope_leak = corpus.prompt_authority_seal(snapshot)
    scope_leak["scope"]["scope"] = "PRIVATE_RAW_PROMPT_DO_NOT_PUBLISH"
    scope_leak["content_hash"] = corpus.digest(
        {key: value for key, value in scope_leak.items() if key != "content_hash"}
    )

    assert corpus._prompt_authority_seal_digest_valid(locator_leak) is False
    assert corpus._prompt_authority_seal_digest_valid(private_string_leak) is False
    assert corpus._prompt_authority_seal_digest_valid(scope_leak) is False


def test_prompt_authority_seal_is_byte_identical_on_zero_change_rerun(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    first = corpus.update_ledger(
        paths,
        events=[_event("Keep the public authority seal bounded.", event_ref="authority-seal")],
        cursor=_cursor(corpus),
    )
    before = paths.public_seal.read_bytes()
    before_mtime = paths.public_seal.stat().st_mtime_ns

    second = corpus.update_ledger(paths)

    assert first["write_changed"] is True
    assert second["write_changed"] is False
    assert paths.public_seal.read_bytes() == before
    assert paths.public_seal.stat().st_mtime_ns == before_mtime
    assert corpus.check_ledger(paths) == []


def test_update_ledger_repairs_coherently_rehashed_public_seal_and_marker(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    corpus.update_ledger(
        paths,
        events=[_event("Keep canonical journals authoritative.", event_ref="coherent-rehash")],
        cursor=_cursor(corpus),
    )
    public = corpus.load_json(paths.public_snapshot)
    seal = corpus.load_json(paths.public_seal)
    marker = corpus.load_json(paths.private_snapshot)
    original_atoms = public["coverage"]["atoms"]

    public["coverage"]["atoms"] = original_atoms + 999
    public["projection_digest"] = corpus.digest(
        {key: value for key, value in public.items() if key != "projection_digest"}
    )
    seal["coverage"]["atoms"] = public["coverage"]["atoms"]
    seal["public_projection_digest"] = public["projection_digest"]
    seal["content_hash"] = corpus.digest({key: value for key, value in seal.items() if key != "content_hash"})
    marker["public_projection_digest"] = public["projection_digest"]
    marker["public_authority_seal_hash"] = seal["content_hash"]
    paths.public_snapshot.write_bytes(corpus._json_bytes(public))
    paths.public_seal.write_bytes(corpus._json_bytes(seal))
    paths.private_snapshot.write_bytes(corpus._json_bytes(marker))
    paths.public_markdown.write_text(
        corpus.render_markdown(public, corpus.load_policy(paths.policy)),
        encoding="utf-8",
    )

    assert corpus._prompt_authority_seal_digest_valid(seal)
    assert corpus._prompt_authority_seal_matches_public(seal, public)
    repaired = corpus.update_ledger(paths)

    repaired_public = corpus.load_json(paths.public_snapshot)
    assert repaired["write_changed"] is True
    assert repaired_public["coverage"]["atoms"] == original_atoms
    assert corpus.check_ledger(paths) == []


def test_cursor_merge_accepts_fresh_cas_file_replacement_without_promoting_partial_all():
    corpus = _load()
    current = {
        "scope": "partial:all",
        "target_scope": "all",
        "pending_files": 4,
        "source_errors": [],
        "files": {"scan-v2:fixture:a": {"size": 10, "mtime_ns": 20}},
    }
    recent = {
        "base_revision": 0,
        "base_cursor_digest": corpus.cursor_digest(current),
        "scope": "recent:14",
        "target_scope": "recent:14",
        "pending_files": 0,
        "source_errors": [],
        "files": {"scan-v2:fixture:a": {"size": 99, "mtime_ns": 10}},
    }
    merged = corpus.merge_cursor(current, recent)

    assert merged["scope"] == "partial:all"
    assert merged["pending_files"] == 4
    assert merged["files"]["scan-v2:fixture:a"] == {"size": 99, "mtime_ns": 10}


def test_raw_object_tamper_fails_explicit_check(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    snapshot = corpus.update_ledger(
        paths,
        events=[_event("Protect exact private raw input.", event_ref="raw-tamper")],
        cursor=_cursor(corpus),
    )
    raw_path = paths.raw_objects / snapshot["occurrences"][0]["raw_object"]
    assert raw_path.stat().st_mode & 0o777 == 0o400
    raw_path.chmod(0o600)
    raw_path.write_bytes(b"not gzip")

    assert any("raw object is unreadable" in error for error in corpus.check_ledger(paths))


def test_stale_cursor_cas_cannot_erase_partial_all_failures():
    corpus = _load()
    contract = corpus.current_source_adapter_contract()
    exclusion_receipts = {
        "scan-v2:claude-plans:/home/.claude/plans/opaque.md": {
            "version": contract["version"],
            "disposition": "excluded",
            "contract_id": "claude-generated-plan-v1",
            "contract_digest": contract["digest"],
            "signature": {"size": 10, "mtime_ns": 20},
        }
    }
    current = {
        "revision": 7,
        "scanner_version": 2,
        "scope": "partial:all",
        "target_scope": "all",
        "pending_files": 3,
        "source_errors": ["claude-plans: adapter missing"],
        "source_adapter_contract": contract,
        "excluded_source_count": 1,
        "source_exclusion_counts": {"claude-generated-plan-v1": 1},
        "excluded_unit_receipts": exclusion_receipts,
        "excluded_unit_receipts_digest": corpus.digest(exclusion_receipts),
        "files": {"scan-v2:fixture:a": {"size": 20, "mtime_ns": 20}},
    }
    proposed = {
        "base_revision": 6,
        "base_cursor_digest": corpus.digest({"stale": True}),
        "revision": 6,
        "scanner_version": 2,
        "source_adapter_contract": contract,
        "scope": "all",
        "target_scope": "all",
        "pending_files": 0,
        "source_errors": [],
        "files": {
            "scan-v2:fixture:a": {"size": 10, "mtime_ns": 10},
            "scan-v2:fixture:b": {"size": 1, "mtime_ns": 30},
        },
    }

    before = json.dumps(current, sort_keys=True)
    with pytest.raises(ValueError, match="stale cursor proposal requires a fresh scan"):
        corpus.merge_cursor(current, proposed)
    assert json.dumps(current, sort_keys=True) == before


def test_stale_cursor_update_is_rejected_without_changing_private_cursor_bytes(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    corpus.update_ledger(
        paths,
        events=[_event("Preserve exact CAS state.", event_ref="cas-state")],
        cursor=_cursor(corpus),
    )
    current = corpus.load_json(paths.cursor)
    before = paths.cursor.read_bytes()
    stale = {
        "base_revision": int(current["revision"]) - 1,
        "base_cursor_digest": "0" * 64,
        "scope": "all",
        "target_scope": "all",
        "pending_files": 0,
        "source_errors": [],
        "files": {},
    }

    with pytest.raises(ValueError, match="stale cursor proposal requires a fresh scan"):
        corpus.update_ledger(paths, cursor=stale)
    assert paths.cursor.read_bytes() == before


def test_exact_all_cannot_be_seeded_by_an_invented_self_certifying_source_unit(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    contract = corpus.current_source_adapter_contract()
    key = "scan-v2:codex-sessions:/definitely/not/a/real/source.jsonl"
    signature = {"size": 123, "mtime_ns": 456, "ctime_ns": 789, "inode": 1011, "device": 12}
    cursor = {
        "base_revision": 0,
        "base_cursor_digest": corpus.cursor_digest({}),
        "scanner_version": contract["scanner_version"],
        "scope": "all",
        "target_scope": "all",
        "all_baseline_complete": True,
        "all_source_manifest_digest": "f" * 64,
        "source_manifest_digest": "f" * 64,
        "source_unit_count": 1,
        "source_units": [key],
        "source_units_digest": corpus.digest([key]),
        "source_adapter_contract": contract,
        "excluded_source_count": 0,
        "source_exclusion_counts": {},
        "excluded_unit_receipts": {},
        "excluded_unit_receipts_digest": corpus.digest({}),
        "adapted_source_count": 0,
        "source_adapter_counts": {},
        "adapted_unit_receipts": {},
        "adapted_unit_receipts_digest": corpus.digest({}),
        "unsupported_source_count": 0,
        "unsupported_units": {},
        "unsupported_units_digest": corpus.digest({}),
        "unresolved_unit_count": 0,
        "unresolved_units": [],
        "unresolved_units_digest": corpus.digest([]),
        "source_families": {
            "codex-sessions": {
                "discovered": 1,
                "converged": 1,
                "adapted": 0,
                "excluded": 0,
                "pending": 0,
                "errors": 0,
                "unsupported": 0,
            }
        },
        "files": {key: signature},
    }

    with pytest.raises(ValueError, match="live scanner attestation"):
        corpus.update_ledger(
            paths,
            events=[_event("Do not authorize invented exact source custody.", event_ref="invented-all")],
            cursor=cursor,
        )

    assert not paths.cursor.exists()
    assert not paths.event_journal.exists()
    assert not paths.public_snapshot.exists()


def test_source_adapter_receipts_are_contract_and_signature_bound():
    corpus = _load()
    contract = corpus.current_source_adapter_contract()
    receipts = {
        "scan-v2:claude-plans:/home/.claude/plans/opaque.md": {
            "version": contract["version"],
            "disposition": "excluded",
            "contract_id": "claude-generated-plan-v1",
            "contract_digest": contract["digest"],
            "signature": {"size": 12, "mtime_ns": 34, "ctime_ns": 35, "inode": 36, "device": 37},
        }
    }
    source_key = next(iter(receipts))
    cursor = {
        "scanner_version": contract["scanner_version"],
        "scope": "all",
        "target_scope": "all",
        "all_baseline_complete": True,
        "all_source_manifest_digest": "f" * 64,
        "source_manifest_digest": "f" * 64,
        "source_unit_count": 1,
        "source_units": [source_key],
        "source_units_digest": corpus.digest([source_key]),
        "source_adapter_contract": contract,
        "excluded_source_count": 1,
        "source_exclusion_counts": {"claude-generated-plan-v1": 1},
        "excluded_unit_receipts": receipts,
        "excluded_unit_receipts_digest": corpus.digest(receipts),
        "adapted_source_count": 0,
        "source_adapter_counts": {},
        "adapted_unit_receipts": {},
        "adapted_unit_receipts_digest": corpus.digest({}),
        "unsupported_source_count": 0,
        "unsupported_units": {},
        "unsupported_units_digest": corpus.digest({}),
        "unresolved_unit_count": 0,
        "unresolved_units": [],
        "unresolved_units_digest": corpus.digest([]),
        "source_families": {
            "claude-plans": {
                "discovered": 1,
                "converged": 0,
                "adapted": 0,
                "excluded": 1,
                "pending": 0,
                "errors": 0,
                "unsupported": 0,
            }
        },
        "files": {},
    }

    _attest_exact_cursor(corpus, cursor)
    assert corpus.validate_source_adapter_cursor(cursor) == []
    original_digest = corpus.cursor_digest(cursor)

    weak_receipts = json.loads(json.dumps(receipts))
    weak_receipts[source_key]["signature"] = {"size": 12, "mtime_ns": 34}
    weak_cursor = {
        **cursor,
        "excluded_unit_receipts": weak_receipts,
        "excluded_unit_receipts_digest": corpus.digest(weak_receipts),
    }
    assert any("malformed or stale" in error for error in corpus.validate_source_adapter_cursor(weak_cursor))

    tampered_receipts = json.loads(json.dumps(receipts))
    tampered_receipts[source_key]["signature"]["mtime_ns"] = 35
    tampered = {**cursor, "excluded_unit_receipts": tampered_receipts}
    assert corpus.cursor_digest(tampered) != original_digest
    assert "excluded unit receipt digest is missing or stale" in corpus.validate_source_adapter_cursor(tampered)

    stale_contract = {**contract, "digest": "0" * 64}
    assert "source adapter contract is missing or stale" in corpus.validate_source_adapter_cursor(
        {**cursor, "source_adapter_contract": stale_contract}
    )
    incomplete_baseline = {**cursor, "all_baseline_complete": False}
    assert corpus.cursor_digest(incomplete_baseline) != original_digest
    assert "exact all/all scope requires a complete all-history baseline" in corpus.validate_source_adapter_cursor(
        incomplete_baseline
    )
    stale_all_manifest = {**cursor, "all_source_manifest_digest": "bad"}
    assert corpus.cursor_digest(stale_all_manifest) != original_digest
    assert "all_source_manifest_digest is missing or malformed" in corpus.validate_source_adapter_cursor(
        stale_all_manifest
    )
    stale_scanner = {**cursor, "scanner_version": contract["scanner_version"] + 1}
    assert corpus.cursor_digest(stale_scanner) != original_digest
    assert "source scanner version is missing or stale" in corpus.validate_source_adapter_cursor(stale_scanner)
    malformed_key_receipts = {"garbage": next(iter(receipts.values()))}
    malformed_key_cursor = {
        **cursor,
        "excluded_unit_receipts": malformed_key_receipts,
        "excluded_unit_receipts_digest": corpus.digest(malformed_key_receipts),
    }
    assert "excluded unit receipt is malformed" in corpus.validate_source_adapter_cursor(malformed_key_cursor)

    for forged_key, family in (
        ("scan-v2:codex-sessions:/home/.claude/plans/opaque.md", "codex-sessions"),
        ("scan-v2:claude-plans:/home/.claude/projects/project/session.jsonl", "claude-plans"),
    ):
        forged_receipts = {forged_key: json.loads(json.dumps(receipts[source_key]))}
        forged_cursor = {
            **cursor,
            "source_units": [forged_key],
            "source_units_digest": corpus.digest([forged_key]),
            "excluded_unit_receipts": forged_receipts,
            "excluded_unit_receipts_digest": corpus.digest(forged_receipts),
            "source_families": {
                family: {
                    "discovered": 1,
                    "converged": 0,
                    "adapted": 0,
                    "excluded": 1,
                    "pending": 0,
                    "errors": 0,
                    "unsupported": 0,
                }
            },
        }
        assert f"{forged_key}: excluded unit receipt is malformed or stale" in (
            corpus.validate_source_adapter_cursor(forged_cursor)
        )

    unsupported_key = "scan-v2:codex-sessions:opaque-media"
    unsupported_signature = {"size": 22, "mtime_ns": 44}
    unsupported_cursor = {
        **cursor,
        "unsupported_source_count": 1,
        "unsupported_units": {unsupported_key: unsupported_signature},
        "unsupported_units_digest": corpus.digest({unsupported_key: unsupported_signature}),
        "unresolved_unit_count": 1,
        "unresolved_units": [unsupported_key],
        "unresolved_units_digest": corpus.digest([unsupported_key]),
        "source_families": {"codex-sessions": {"unsupported": 1}},
    }
    unsupported_errors = corpus.validate_source_adapter_cursor(unsupported_cursor)
    assert "exact all/all scope cannot have unsupported source units" in unsupported_errors
    assert "exact all/all scope cannot have unresolved source obligations" in unsupported_errors
    assert corpus.cursor_digest(unsupported_cursor) != original_digest

    recent_with_stale_unsupported_digest = {
        **unsupported_cursor,
        "scope": "partial:recent:14",
        "target_scope": "recent:14",
        "all_baseline_complete": False,
        "all_source_manifest_digest": None,
        "unsupported_units_digest": "0" * 64,
    }
    assert "unsupported unit cache digest is missing or stale" in corpus.validate_source_adapter_cursor(
        recent_with_stale_unsupported_digest
    )

    family_pending = {**cursor, "source_families": {"codex-sessions": {"pending": 1}}}
    assert "source family pending counts do not match pending_files" in corpus.validate_source_adapter_cursor(
        family_pending
    )
    family_errors = {**cursor, "source_families": {"codex-sessions": {"errors": 1}}}
    assert "source family error counts do not match source_errors" in corpus.validate_source_adapter_cursor(
        family_errors
    )


def test_memory_mirror_receipt_binds_sibling_locator_signature_and_content_equality():
    corpus = _load()
    contract = corpus.current_source_adapter_contract()
    locator = "/home/.claude/projects/project/notes.md"
    sibling = "/home/.claude/projects/project/memory/notes.md"
    key = f"scan-v2:claude-projects:{locator}"
    signature = {"size": 12, "mtime_ns": 34, "ctime_ns": 35, "inode": 36, "device": 37}
    sibling_signature = {"size": 12, "mtime_ns": 44, "ctime_ns": 45, "inode": 46, "device": 47}
    content_sha = "a" * 64
    receipt = {
        "version": contract["version"],
        "disposition": "excluded",
        "contract_id": "claude-project-memory-mirror-v1",
        "contract_digest": contract["digest"],
        "signature": signature,
        "related_signatures": {"memory_sibling": sibling_signature},
        "related_evidence": {
            "memory_sibling": {
                "locator_sha256": hashlib.sha256(sibling.encode()).hexdigest(),
                "primary_content_sha256": content_sha,
                "related_content_sha256": content_sha,
            }
        },
    }

    def cursor_for(candidate: dict) -> dict:
        receipts = {key: candidate}
        return _attest_exact_cursor(
            corpus,
            {
                "scanner_version": contract["scanner_version"],
                "scope": "all",
                "target_scope": "all",
                "all_baseline_complete": True,
                "all_source_manifest_digest": "f" * 64,
                "source_manifest_digest": "f" * 64,
                "source_unit_count": 1,
                "source_units": [key],
                "source_units_digest": corpus.digest([key]),
                "source_adapter_contract": contract,
                "excluded_source_count": 1,
                "source_exclusion_counts": {"claude-project-memory-mirror-v1": 1},
                "excluded_unit_receipts": receipts,
                "excluded_unit_receipts_digest": corpus.digest(receipts),
                "adapted_source_count": 0,
                "source_adapter_counts": {},
                "adapted_unit_receipts": {},
                "adapted_unit_receipts_digest": corpus.digest({}),
                "unsupported_source_count": 0,
                "unsupported_units": {},
                "unsupported_units_digest": corpus.digest({}),
                "unresolved_unit_count": 0,
                "unresolved_units": [],
                "unresolved_units_digest": corpus.digest([]),
                "source_families": {
                    "claude-projects": {
                        "discovered": 1,
                        "converged": 0,
                        "adapted": 0,
                        "excluded": 1,
                        "pending": 0,
                        "errors": 0,
                        "unsupported": 0,
                    }
                },
                "files": {},
            },
        )

    assert corpus.validate_source_adapter_cursor(cursor_for(receipt)) == []

    forged = json.loads(json.dumps(receipt))
    forged["related_signatures"]["memory_sibling"]["size"] = 99
    assert any("malformed or stale" in error for error in corpus.validate_source_adapter_cursor(cursor_for(forged)))

    forged = json.loads(json.dumps(receipt))
    forged["related_evidence"]["memory_sibling"]["locator_sha256"] = "0" * 64
    assert any("malformed or stale" in error for error in corpus.validate_source_adapter_cursor(cursor_for(forged)))

    forged = json.loads(json.dumps(receipt))
    forged["related_evidence"]["memory_sibling"]["related_content_sha256"] = "b" * 64
    assert any("malformed or stale" in error for error in corpus.validate_source_adapter_cursor(cursor_for(forged)))


def test_exact_all_source_family_counts_are_bound_to_unit_custody():
    corpus = _load()
    contract = corpus.current_source_adapter_contract()
    key = "scan-v2:codex-sessions:one"
    signature = {"size": 12, "mtime_ns": 34, "ctime_ns": 35, "inode": 36, "device": 37}
    cursor = {
        "scanner_version": contract["scanner_version"],
        "scope": "all",
        "target_scope": "all",
        "all_baseline_complete": True,
        "all_source_manifest_digest": "f" * 64,
        "source_manifest_digest": "f" * 64,
        "source_unit_count": 1,
        "source_units": [key],
        "source_units_digest": corpus.digest([key]),
        "source_adapter_contract": contract,
        "excluded_source_count": 0,
        "source_exclusion_counts": {},
        "excluded_unit_receipts": {},
        "excluded_unit_receipts_digest": corpus.digest({}),
        "adapted_source_count": 0,
        "source_adapter_counts": {},
        "adapted_unit_receipts": {},
        "adapted_unit_receipts_digest": corpus.digest({}),
        "unsupported_source_count": 0,
        "unsupported_units": {},
        "unsupported_units_digest": corpus.digest({}),
        "unresolved_unit_count": 0,
        "unresolved_units": [],
        "unresolved_units_digest": corpus.digest([]),
        "source_families": {
            "codex-sessions": {
                "discovered": 1,
                "converged": 1,
                "adapted": 0,
                "excluded": 0,
                "pending": 0,
                "errors": 0,
                "unsupported": 0,
            }
        },
        "files": {key: signature},
    }
    _attest_exact_cursor(corpus, cursor)
    assert corpus.validate_source_adapter_cursor(cursor) == []

    invented = "scan-v2:codex-sessions:invented"
    invented_cursor = {
        **cursor,
        "source_units": [invented],
        "source_units_digest": corpus.digest([invented]),
    }
    assert "exact all/all source units do not match parsed and excluded unit custody" in (
        corpus.validate_source_adapter_cursor(invented_cursor)
    )
    no_files = {**cursor, "files": {}}
    assert "exact all/all source units do not match parsed and excluded unit custody" in (
        corpus.validate_source_adapter_cursor(no_files)
    )
    moved_family = {
        **cursor,
        "source_families": {"claude-projects": dict(cursor["source_families"]["codex-sessions"])},
    }
    assert any(
        "count does not match unit custody" in error for error in corpus.validate_source_adapter_cursor(moved_family)
    )
    negative = json.loads(json.dumps(cursor))
    negative["source_families"]["codex-sessions"]["discovered"] = -1
    assert "source family unresolved counts are malformed" in corpus.validate_source_adapter_cursor(negative)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("excluded_source_count", "1"),
        ("excluded_source_count", True),
        ("excluded_source_count", -1),
        ("adapted_source_count", "0"),
        ("source_exclusion_counts", []),
        ("source_exclusion_counts", {"claude-generated-plan-v1": True}),
        ("source_exclusion_counts", {"unrelated-rule": 1}),
        ("source_adapter_counts", []),
        ("excluded_unit_receipts", []),
        ("adapted_unit_receipts", []),
        ("files", []),
        ("files", {"garbage": {"size": 1, "mtime_ns": 2}}),
        ("files", {"scan-v2:claude-projects:opaque": "not-a-signature"}),
        ("unsupported_units", {"scan-v2:claude-projects:opaque": {"size": True, "mtime_ns": 1}}),
    ],
)
def test_malformed_source_adapter_cursor_fields_fail_closed_without_digest_crash(field, value):
    corpus = _load()
    contract = corpus.current_source_adapter_contract()
    receipts = {
        "scan-v2:claude-plans:/home/.claude/plans/opaque.md": {
            "version": contract["version"],
            "disposition": "excluded",
            "contract_id": "claude-generated-plan-v1",
            "contract_digest": contract["digest"],
            "signature": {"size": 12, "mtime_ns": 34},
            "related_signatures": {},
        }
    }
    source_key = next(iter(receipts))
    cursor = {
        "scanner_version": contract["scanner_version"],
        "scope": "all",
        "target_scope": "all",
        "all_baseline_complete": True,
        "all_source_manifest_digest": "f" * 64,
        "source_manifest_digest": "f" * 64,
        "source_unit_count": 1,
        "source_units": [source_key],
        "source_units_digest": corpus.digest([source_key]),
        "source_adapter_contract": contract,
        "excluded_source_count": 1,
        "source_exclusion_counts": {"claude-generated-plan-v1": 1},
        "excluded_unit_receipts": receipts,
        "excluded_unit_receipts_digest": corpus.digest(receipts),
        "adapted_source_count": 0,
        "source_adapter_counts": {},
        "adapted_unit_receipts": {},
        "adapted_unit_receipts_digest": corpus.digest({}),
        "unsupported_source_count": 0,
        "unsupported_units": {},
        "unsupported_units_digest": corpus.digest({}),
        "unresolved_unit_count": 0,
        "unresolved_units": [],
        "unresolved_units_digest": corpus.digest([]),
        "source_families": {
            "claude-plans": {
                "discovered": 1,
                "converged": 0,
                "adapted": 0,
                "excluded": 1,
                "pending": 0,
                "errors": 0,
                "unsupported": 0,
            }
        },
        "files": {},
    }
    malformed = {**cursor, field: value}

    assert isinstance(corpus.cursor_digest(malformed), str)
    assert corpus.validate_source_adapter_cursor(malformed)


def test_malformed_source_contract_sequences_and_receipts_fail_closed_without_crashing():
    corpus = _load()
    contract = corpus.current_source_adapter_contract()
    malformed_receipt = {
        "scan-v2:claude-plans:/home/.claude/plans/opaque.md": {
            "version": True,
            "disposition": "excluded",
            "contract_id": ["not", "typed"],
            "contract_digest": contract["digest"],
            "signature": {"size": True, "mtime_ns": -1},
            "related_signatures": [],
        }
    }
    cursor = {
        "scanner_version": contract["scanner_version"],
        "scope": "all",
        "target_scope": "all",
        "all_baseline_complete": True,
        "all_source_manifest_digest": "f" * 64,
        "source_adapter_contract": {**contract, "adapter_ids": 7, "exclusion_ids": {"bad": 1}},
        "excluded_source_count": 1,
        "source_exclusion_counts": {"opaque": 1},
        "excluded_unit_receipts": malformed_receipt,
        "excluded_unit_receipts_digest": corpus.digest(malformed_receipt),
        "adapted_source_count": 0,
        "source_adapter_counts": {},
        "adapted_unit_receipts": {},
        "adapted_unit_receipts_digest": corpus.digest({}),
        "source_errors": 7,
        "adapter_gaps": 7,
        "adapter_gap_routes": 7,
        "files": {},
    }

    assert isinstance(corpus.cursor_digest(cursor), str)
    errors = corpus.validate_source_adapter_cursor(cursor)
    assert "source adapter contract is missing or stale" in errors
    assert any("receipt is malformed or stale" in error for error in errors)


def test_fresh_exclusion_proposal_removes_prior_parser_cache_but_stale_cannot():
    corpus = _load()
    key = "scan-v2:claude-projects:tool-result"
    current = {
        "revision": 4,
        "scope": "partial:all",
        "target_scope": "all",
        "pending_files": 0,
        "source_errors": [],
        "files": {key: {"size": 9, "mtime_ns": 10}},
    }
    proposal = {
        "base_revision": 4,
        "base_cursor_digest": corpus.cursor_digest(current),
        "scope": "all",
        "target_scope": "all",
        "pending_files": 0,
        "source_errors": [],
        "files": {},
        "excluded_file_keys": [key],
    }

    merged = corpus.merge_cursor(current, proposal)
    assert key not in merged["files"]
    assert "excluded_file_keys" not in merged

    with pytest.raises(ValueError, match="stale cursor proposal requires a fresh scan"):
        corpus.merge_cursor(
            current,
            {**proposal, "base_revision": 3, "base_cursor_digest": "0" * 64},
        )


def test_fresh_contract_reset_replaces_parser_cache_but_stale_reset_cannot():
    corpus = _load()
    contract = corpus.current_source_adapter_contract()
    current = {
        "revision": 4,
        "scanner_version": 2,
        "scope": "all",
        "target_scope": "all",
        "pending_files": 0,
        "source_errors": [],
        "source_adapter_contract": contract,
        "files": {"scan-v2:claude-projects:legacy": {"size": 9, "mtime_ns": 10}},
    }
    proposal = {
        "base_revision": 4,
        "base_cursor_digest": corpus.cursor_digest(current),
        "scope": "partial:all",
        "target_scope": "all",
        "pending_files": 0,
        "source_errors": [],
        "scanner_version": 2,
        "source_adapter_contract": contract,
        "replace_files": True,
        "files": {"scan-v2:claude-projects:fresh": {"size": 3, "mtime_ns": 20}},
    }

    merged = corpus.merge_cursor(current, proposal)
    assert merged["files"] == {"scan-v2:claude-projects:fresh": {"size": 3, "mtime_ns": 20}}
    assert "replace_files" not in merged

    with pytest.raises(ValueError, match="stale cursor proposal requires a fresh scan"):
        corpus.merge_cursor(
            current,
            {
                **proposal,
                "base_revision": 3,
                "base_cursor_digest": "0" * 64,
                "source_adapter_contract": {**contract, "digest": "0" * 64},
            },
        )


@pytest.mark.parametrize(("current_updated", "proposed_updated"), [(9, 10), (10, 9)])
def test_exact_cas_accepts_fresh_observed_opencode_signature(current_updated, proposed_updated):
    corpus = _load()
    contract = corpus.current_source_adapter_contract()
    key = "scan-v2:opencode-db:session-1"
    current = {
        "revision": 5,
        "scanner_version": 2,
        "scope": "partial:all",
        "target_scope": "all",
        "pending_files": 0,
        "source_errors": [],
        "source_adapter_contract": contract,
        "files": {key: {"time_created": 1, "time_updated": current_updated}},
    }
    proposed = {
        "base_revision": 5,
        "base_cursor_digest": corpus.cursor_digest(current),
        "scanner_version": 2,
        "scope": "partial:all",
        "target_scope": "all",
        "pending_files": 1,
        "source_errors": [],
        "source_adapter_contract": contract,
        "files": {key: {"time_created": 1, "time_updated": proposed_updated}},
    }

    merged = corpus.merge_cursor(current, proposed)

    assert merged["files"][key]["time_updated"] == proposed_updated


def test_exact_cas_accepts_replacement_with_lower_times_and_different_inode():
    corpus = _load()
    contract = corpus.current_source_adapter_contract()
    key = "scan-v2:claude-projects:session.jsonl"
    current = {
        "revision": 5,
        "scanner_version": 2,
        "scope": "partial:all",
        "target_scope": "all",
        "pending_files": 1,
        "source_errors": [],
        "source_adapter_contract": contract,
        "files": {key: {"size": 10, "mtime_ns": 20, "ctime_ns": 30, "inode": 40, "device": 1}},
    }
    proposed = {
        "base_revision": 5,
        "base_cursor_digest": corpus.cursor_digest(current),
        "scanner_version": 2,
        "scope": "partial:all",
        "target_scope": "all",
        "pending_files": 1,
        "source_errors": [],
        "source_adapter_contract": contract,
        "files": {key: {"size": 99, "mtime_ns": 10, "ctime_ns": 15, "inode": 41, "device": 1}},
    }

    merged = corpus.merge_cursor(current, proposed)

    assert merged["files"][key] == {
        "size": 99,
        "mtime_ns": 10,
        "ctime_ns": 15,
        "inode": 41,
        "device": 1,
    }


@pytest.mark.parametrize(
    ("side", "field", "value", "message"),
    [
        ("current", "revision", "broken", "invalid current cursor"),
        ("current", "source_errors", 7, "invalid current cursor"),
        ("proposed", "base_revision", "broken", "invalid proposed cursor"),
        ("proposed", "pending_files", "broken", "invalid proposed cursor"),
        ("proposed", "excluded_file_keys", 7, "invalid proposed cursor"),
    ],
)
def test_merge_cursor_rejects_malformed_cas_fields_explicitly(side, field, value, message):
    corpus = _load()
    current = {
        "revision": 1,
        "scope": "partial:all",
        "target_scope": "all",
        "pending_files": 1,
        "source_errors": [],
        "files": {},
    }
    proposed = {
        "base_revision": 1,
        "base_cursor_digest": corpus.cursor_digest(current),
        "scope": "partial:all",
        "target_scope": "all",
        "pending_files": 1,
        "source_errors": [],
        "files": {},
    }
    target = current if side == "current" else proposed
    target[field] = value

    with pytest.raises(ValueError, match=message):
        corpus.merge_cursor(current, proposed)


def test_merge_cursor_requires_exact_cas_pair_and_future_revision_cannot_poison_writer_state():
    corpus = _load()
    current = {
        "revision": 7,
        "scope": "partial:all",
        "target_scope": "all",
        "pending_files": 2,
        "source_errors": ["owner-routed gap"],
        "files": {"scan-v2:fixture:current": {"size": 1, "mtime_ns": 2}},
    }
    missing_digest = {
        "base_revision": 999,
        "scope": "all",
        "target_scope": "all",
        "pending_files": 0,
        "source_errors": [],
        "files": {},
    }
    with pytest.raises(ValueError, match="exact CAS revision and digest"):
        corpus.merge_cursor(current, missing_digest)

    future = {
        **missing_digest,
        "base_cursor_digest": corpus.cursor_digest(current),
        "revision": 10**9,
    }
    with pytest.raises(ValueError, match="stale cursor proposal requires a fresh scan"):
        corpus.merge_cursor(current, future)
    assert current["revision"] == 7


def test_fresh_cas_cannot_clear_unresolved_obligation_without_unit_resolution_proof():
    corpus = _load()
    key = "scan-v2:codex-sessions:unresolved"
    signature = {"size": 12, "mtime_ns": 34}
    current = {
        "revision": 3,
        "scope": "partial:all",
        "target_scope": "all",
        "pending_files": 1,
        "source_errors": [],
        "unresolved_units": [key],
        "files": {},
    }
    proposal = {
        "base_revision": 3,
        "base_cursor_digest": corpus.cursor_digest(current),
        "scope": "all",
        "target_scope": "all",
        "pending_files": 0,
        "source_errors": [],
        "source_units": [],
        "unresolved_units": [],
        "files": {},
    }

    with pytest.raises(ValueError, match="lack parsed or excluded resolution proof"):
        corpus.merge_cursor(current, proposal)

    resolved = {
        **proposal,
        "source_units": [key],
        "files": {key: signature},
    }
    merged = corpus.merge_cursor(current, resolved)
    assert merged["unresolved_units"] == []
    assert merged["files"] == {key: signature}


def test_update_ledger_rejects_malformed_private_cursor_before_merge(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    paths.private_dir.mkdir(parents=True)
    paths.cursor.write_text(json.dumps({"revision": "broken"}), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid current cursor"):
        corpus.update_ledger(paths, cursor=_cursor(corpus))


def test_check_ledger_rejects_malformed_nonsemantic_cursor_revision(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    corpus.update_ledger(
        paths,
        events=[_event("Preserve cursor CAS shape.", event_ref="cursor-shape")],
        cursor=_cursor(corpus),
    )
    cursor = corpus.load_json(paths.cursor)
    cursor["revision"] = -1
    paths.cursor.write_text(json.dumps(cursor), encoding="utf-8")

    assert any("live cursor revision must be a non-negative integer" in error for error in corpus.check_ledger(paths))


def test_source_authority_change_revises_existing_occurrence_once_without_losing_history(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    original = {
        **_event("Delegated child instruction.", event_ref="same-source-event"),
        "source": "claude-projects",
        "source_locator": "/private/project/session/subagents/child.jsonl#0:0",
    }
    first = corpus.update_ledger(paths, events=[original], cursor=_cursor(corpus))
    assert first["occurrences"][0]["authority"] == "operator"

    revised_event = {
        **original,
        "provenance": "delegated_task_frame",
        "authority": "derived",
        "atoms": [
            {
                "text": "Delegated child instruction.",
                "kind": "ask",
                "classifier_provenance": "runtime-classifier",
                "classification_confidence": 0.96,
            }
        ],
    }
    second = corpus.update_ledger(paths, events=[revised_event])

    assert second["appended"]["reclassified"] == 1
    assert second["occurrences"][0]["authority"] == "derived"
    assert second["occurrences"][0]["provenance"] == "delegated_task_frame"
    assert {atom["authority"] for atom in second["atoms"]} == {"derived"}
    assert {atom["atomization_mode"] for atom in second["atoms"]} == {"semantic_adapter"}
    assert len(paths.event_journal.read_text(encoding="utf-8").splitlines()) == 2

    third = corpus.update_ledger(paths, events=[revised_event])
    assert third["appended"]["reclassified"] == 0
    assert len(paths.event_journal.read_text(encoding="utf-8").splitlines()) == 2


def test_source_exclusion_receipt_retracts_prior_false_atoms_once_and_preserves_occurrence(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    source_path = "/private/home/.claude/projects/project/session/tool-results/result.json"
    original = {
        **_event("Tool output that was previously mistaken for an ask.", event_ref="tool-result"),
        "source": "claude-projects",
        "source_locator": f"{source_path}#0:0",
    }
    first = corpus.update_ledger(paths, events=[original], cursor=_cursor(corpus))
    assert first["coverage"]["atoms"] == 1
    current_cursor = corpus.load_json(paths.cursor)
    contract = corpus.current_source_adapter_contract()
    signature = {"size": 42, "mtime_ns": 99, "ctime_ns": 100, "inode": 101, "device": 102}
    key = f"scan-v2:claude-projects:{source_path}"
    receipts = {
        key: {
            "version": contract["version"],
            "disposition": "excluded",
            "contract_id": "claude-project-tool-result-v1",
            "contract_digest": contract["digest"],
            "signature": signature,
            "related_signatures": {},
        }
    }
    proposal = {
        "base_revision": current_cursor["revision"],
        "base_cursor_digest": corpus.cursor_digest(current_cursor),
        "version": 1,
        "scanner_version": contract["scanner_version"],
        "scope": "partial:all",
        "target_scope": "all",
        "all_baseline_complete": False,
        "pending_files": 0,
        "source_errors": [],
        "source_manifest_digest": "f" * 64,
        "source_unit_count": 1,
        "source_units": [key],
        "source_units_digest": corpus.digest([key]),
        "source_adapter_contract": contract,
        "excluded_source_count": 1,
        "source_exclusion_counts": {"claude-project-tool-result-v1": 1},
        "excluded_unit_receipts": receipts,
        "excluded_unit_receipts_digest": corpus.digest(receipts),
        "adapted_source_count": 0,
        "source_adapter_counts": {},
        "adapted_unit_receipts": {},
        "adapted_unit_receipts_digest": corpus.digest({}),
        "unsupported_source_count": 0,
        "unsupported_units": {},
        "unsupported_units_digest": corpus.digest({}),
        "unresolved_unit_count": 0,
        "unresolved_units": [],
        "unresolved_units_digest": corpus.digest([]),
        "source_families": {
            "claude-projects": {
                "discovered": 1,
                "converged": 0,
                "adapted": 0,
                "excluded": 1,
                "pending": 0,
                "errors": 0,
                "unsupported": 0,
            }
        },
        "files": {},
    }

    second = corpus.update_ledger(paths, cursor=proposal)

    assert second["appended"]["reclassified"] == 1
    assert second["coverage"]["occurrences"] == 1
    assert second["coverage"]["atoms"] == 0
    assert second["occurrences"][0]["excluded_reason"] == "source_contract_excluded"
    assert second["validation"]["ok"] is True
    journal_lines = len(paths.event_journal.read_text(encoding="utf-8").splitlines())

    third = corpus.update_ledger(paths)
    assert third["appended"]["reclassified"] == 0
    assert len(paths.event_journal.read_text(encoding="utf-8").splitlines()) == journal_lines

    current_cursor = corpus.load_json(paths.cursor)
    restored_cursor = {
        **proposal,
        "base_revision": current_cursor["revision"],
        "base_cursor_digest": corpus.cursor_digest(current_cursor),
        "excluded_source_count": 0,
        "source_exclusion_counts": {},
        "excluded_unit_receipts": {},
        "excluded_unit_receipts_digest": corpus.digest({}),
        "source_families": {
            "claude-projects": {
                "discovered": 1,
                "converged": 1,
                "adapted": 0,
                "excluded": 0,
                "pending": 0,
                "errors": 0,
                "unsupported": 0,
            }
        },
        "files": {key: signature},
    }
    restored = corpus.update_ledger(paths, events=[original], cursor=restored_cursor)
    assert restored["appended"]["reclassified"] == 1
    assert restored["coverage"]["atoms"] == 1
    assert restored["occurrences"][0]["excluded_reason"] is None

    stable = corpus.update_ledger(paths, events=[original])
    assert stable["appended"]["reclassified"] == 0


def test_malformed_or_deleted_private_marker_fails_closed(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    corpus.update_ledger(
        paths,
        events=[_event("Preserve the canonical marker.", event_ref="marker")],
        cursor=_cursor(corpus),
    )

    paths.private_snapshot.write_text("{malformed", encoding="utf-8")
    assert "private prompt checkpoint is malformed" in corpus.check_ledger(paths)

    paths.private_snapshot.unlink()
    errors = corpus.check_ledger(paths)
    assert any("checkpoint is missing" in error for error in errors)


def test_duplicate_source_segments_keep_positional_coverage(tmp_path: Path):
    corpus = _load()
    text = "Repeat this exact ask. Repeat this exact ask."
    candidate = {
        "text": "Repeat this exact ask.",
        "kind": "ask",
        "classifier_provenance": "fixture-adapter",
        "classification_confidence": 0.9,
    }
    snapshot = corpus.update_ledger(
        _paths(corpus, tmp_path),
        events=[_event(text, event_ref="duplicate-segments", atoms=[candidate, candidate])],
        cursor=_cursor(corpus),
    )

    assert snapshot["coverage"]["atoms"] == 2
    assert {atom["atomization_mode"] for atom in snapshot["atoms"]} == {"semantic_adapter"}
    coverage = [tuple(atom["coverage_hashes"]) for atom in snapshot["atoms"]]
    assert len(set(coverage)) == 2
    assert snapshot["validation"]["ok"] is True


def test_corrections_use_chronology_not_input_order(tmp_path: Path):
    corpus = _load()
    snapshot = corpus.update_ledger(
        _paths(corpus, tmp_path),
        events=[
            _event(
                "No, derive the live capability.",
                event_ref="newer-first",
                timestamp="2026-07-11T12:02:00Z",
            ),
            _event(
                "Use the static capability table.",
                event_ref="older-second",
                timestamp="2026-07-11T12:01:00Z",
            ),
        ],
        cursor=_cursor(corpus),
    )

    correction = next(atom for atom in snapshot["atoms"] if atom["kind"] == "correction")
    predecessor = next(atom for atom in snapshot["atoms"] if atom["atom_id"] in correction["candidate_predecessor_ids"])
    assert predecessor["timestamp"] == "2026-07-11T12:01:00Z"
    assert correction["predecessor_ids"] == []
    assert predecessor["is_current_intent"] is True
    assert snapshot["validation"]["ok"] is True


@pytest.mark.parametrize(
    ("predecessor_timestamp", "predecessor_index", "successor_timestamp", "successor_index"),
    [
        ("2026-07-11T12:00:00Z", 0, "", 1),
        ("2026-07-11T12:00:00Z", 0, True, 1),
        ("2026-07-11T12:00:00Z", 0, "2026-07-11T12:00:00Z", 0),
        ("2026-07-11T12:02:00Z", 0, "2026-07-11T12:01:00Z", 1),
    ],
    ids=("missing-time", "boolean-time", "equal-order", "future-predecessor"),
)
def test_semantic_correction_edges_fail_closed_without_strict_chronology(
    tmp_path: Path,
    predecessor_timestamp: str,
    predecessor_index: int,
    successor_timestamp: str,
    successor_index: int,
):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    predecessor_event = _event(
        "Use the earlier implementation shape.",
        event_ref="chronology-predecessor",
        timestamp=predecessor_timestamp,
    )
    predecessor_event["event_index"] = predecessor_index
    first = corpus.update_ledger(paths, events=[predecessor_event], cursor=_cursor(corpus))
    predecessor = first["atoms"][0]
    classifier = "fixture-chronology-adapter"

    successor_event = _event(
        "No, use the corrected implementation shape.",
        event_ref="chronology-successor",
        timestamp=successor_timestamp,
        atoms=[
            {
                "text": "No, use the corrected implementation shape.",
                "kind": "correction",
                "lineage_id": predecessor["lineage_id"],
                "relation": "corrects",
                "predecessor_ids": [predecessor["atom_id"]],
                "classifier_provenance": classifier,
                "lineage_evidence": {
                    "kind": "semantic_adapter",
                    "classifier_provenance": classifier,
                    "confidence": 1.0,
                },
            }
        ],
    )
    successor_event["event_index"] = successor_index
    snapshot = corpus.update_ledger(paths, events=[successor_event])

    by_id = {atom["atom_id"]: atom for atom in snapshot["atoms"]}
    successor = next(atom for atom in snapshot["atoms"] if atom["atom_id"] != predecessor["atom_id"])
    assert by_id[predecessor["atom_id"]]["is_current_intent"] is True
    assert successor["is_current_intent"] is True
    assert snapshot["validation"]["ok"] is False
    assert "predecessor edge is not strictly chronological" in " ".join(snapshot["validation"]["errors"])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("event_index", True),
        ("text_index", True),
        ("event_index", float("nan")),
        ("text_index", float("inf")),
        ("event_index", -1),
        ("text_index", "1"),
    ],
)
def test_event_positions_require_exact_nonnegative_integers(tmp_path: Path, field: str, value):
    corpus = _load()
    event = _event("Reject malformed chronology evidence.", event_ref="bad-position")
    event[field] = value

    with pytest.raises(ValueError, match=f"{field} must be a non-negative integer"):
        corpus.update_ledger(_paths(corpus, tmp_path), events=[event], cursor=_cursor(corpus))


def test_semantic_correction_accepts_equal_timestamp_with_later_same_session_order(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    predecessor_event = _event(
        "Use the first source segment.",
        event_ref="same-source-event",
        timestamp="2026-07-11T12:00:00Z",
    )
    predecessor_event.update({"event_index": 7, "text_index": 0})
    first = corpus.update_ledger(paths, events=[predecessor_event], cursor=_cursor(corpus))
    predecessor = first["atoms"][0]
    classifier = "fixture-chronology-adapter"

    successor_event = _event(
        "No, use the later source segment.",
        event_ref="same-source-event",
        timestamp="2026-07-11T12:00:00Z",
        atoms=[
            {
                "text": "No, use the later source segment.",
                "kind": "correction",
                "lineage_id": predecessor["lineage_id"],
                "relation": "corrects",
                "predecessor_ids": [predecessor["atom_id"]],
                "classifier_provenance": classifier,
                "lineage_evidence": {
                    "kind": "semantic_adapter",
                    "classifier_provenance": classifier,
                    "confidence": 1.0,
                },
            }
        ],
    )
    successor_event.update({"event_index": 7, "text_index": 1})
    snapshot = corpus.update_ledger(paths, events=[successor_event])

    by_id = {atom["atom_id"]: atom for atom in snapshot["atoms"]}
    assert by_id[predecessor["atom_id"]]["is_current_intent"] is False
    assert snapshot["validation"]["ok"] is True


def test_semantic_correction_with_missing_predecessor_never_retires_intent(tmp_path: Path):
    corpus = _load()
    classifier = "fixture-chronology-adapter"
    snapshot = corpus.update_ledger(
        _paths(corpus, tmp_path),
        events=[
            _event(
                "No, use the available intent only.",
                event_ref="missing-predecessor",
                atoms=[
                    {
                        "text": "No, use the available intent only.",
                        "kind": "correction",
                        "lineage_id": "pl-missing-predecessor",
                        "relation": "corrects",
                        "predecessor_ids": ["pa-missing-predecessor"],
                        "classifier_provenance": classifier,
                        "lineage_evidence": {
                            "kind": "semantic_adapter",
                            "classifier_provenance": classifier,
                            "confidence": 1.0,
                        },
                    }
                ],
            )
        ],
        cursor=_cursor(corpus),
    )

    assert snapshot["atoms"][0]["is_current_intent"] is True
    assert snapshot["validation"]["ok"] is False
    assert "lineage/dependency edge does not resolve" in " ".join(snapshot["validation"]["errors"])


def test_invalid_disposition_is_never_promoted(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    first = corpus.update_ledger(
        paths,
        events=[_event("Assess this atom honestly.", event_ref="invalid-disposition")],
        cursor=_cursor(corpus),
    )
    atom_id = first["atoms"][0]["atom_id"]

    before = paths.outcome_journal.read_bytes() if paths.outcome_journal.exists() else b""
    try:
        corpus.update_ledger(
            paths,
            outcomes=[
                {
                    "atom_id": atom_id,
                    "disposition": "completed",
                    "assessed_at": "2026-07-11T12:05:00Z",
                }
            ],
        )
    except ValueError as exc:
        assert "invalid disposition 'completed'" in str(exc)
    else:
        raise AssertionError("invalid disposition was appended")
    after = paths.outcome_journal.read_bytes() if paths.outcome_journal.exists() else b""
    assert after == before


def test_semantic_edge_cannot_join_unrelated_lineages(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    first = corpus.update_ledger(
        paths,
        events=[
            _event("Keep the first owner.", event_ref="lineage-one"),
            _event("Keep the second owner.", event_ref="lineage-two"),
        ],
        cursor=_cursor(corpus),
    )
    by_intent = {atom["intent"]: atom for atom in first["atoms"]}
    unrelated = by_intent["Keep the second owner."]
    intended_lineage = by_intent["Keep the first owner."]["lineage_id"]
    classifier = "fixture-adapter"

    snapshot = corpus.update_ledger(
        paths,
        events=[
            _event(
                "No, refine only the first owner.",
                event_ref="cross-lineage",
                timestamp="2026-07-11T12:03:00Z",
                atoms=[
                    {
                        "text": "No, refine only the first owner.",
                        "kind": "correction",
                        "lineage_id": intended_lineage,
                        "relation": "refines",
                        "predecessor_ids": [unrelated["atom_id"]],
                        "classifier_provenance": classifier,
                        "lineage_evidence": {
                            "kind": "semantic_adapter",
                            "classifier_provenance": classifier,
                            "confidence": 1.0,
                        },
                    }
                ],
            )
        ],
    )

    assert snapshot["validation"]["ok"] is False
    assert "crosses unrelated lineages" in " ".join(snapshot["validation"]["errors"])


def test_reclassification_is_append_only_and_preserves_assessed_outcome(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    text = "Route the durable owner receipt."
    first = corpus.update_ledger(
        paths,
        events=[_event(text, event_ref="reclassify")],
        cursor=_cursor(corpus),
    )
    atom_id = first["atoms"][0]["atom_id"]
    corpus.update_ledger(
        paths,
        outcomes=[
            {
                "atom_id": atom_id,
                "disposition": "not_done",
                "assessed_at": "2026-07-11T12:04:00Z",
            }
        ],
    )

    revised = corpus.update_ledger(
        paths,
        events=[
            _event(
                text,
                event_ref="reclassify",
                atoms=[
                    {
                        "text": text,
                        "kind": "ask",
                        "classifier_provenance": "improved-runtime",
                        "classification_confidence": 0.95,
                    }
                ],
            )
        ],
    )

    assert revised["appended"]["reclassified"] == 1
    assert revised["atoms"][0]["atom_id"] == atom_id
    assert revised["atoms"][0]["atomization_mode"] == "semantic_adapter"
    assert revised["atoms"][0]["outcome"]["disposition"] == "not_done"
    assert revised["occurrences"][0]["classification_revision"] == 1
    assert len(paths.event_journal.read_text(encoding="utf-8").splitlines()) == 2
    assert corpus.check_ledger(paths) == []


def test_operator_authority_band_dominates_derived_volume(tmp_path: Path):
    corpus = _load()
    names = tuple(corpus.DIMENSIONS)
    derived_text = "Produce a very large delegated summary with many words and maximum scores."
    operator_text = "Fix this."
    snapshot = corpus.update_ledger(
        _paths(corpus, tmp_path),
        events=[
            _event(
                derived_text,
                event_ref="derived-volume",
                provenance="continuation_summary",
                authority="derived",
                atoms=[
                    {
                        "text": derived_text,
                        "kind": "ask",
                        "dimensions": {name: 1.0 for name in names},
                    }
                ],
            ),
            _event(
                operator_text,
                event_ref="operator-short",
                atoms=[
                    {
                        "text": operator_text,
                        "kind": "ask",
                        "dimensions": {name: 0.0 for name in names},
                    }
                ],
            ),
        ],
        cursor=_cursor(corpus),
    )

    scores = {atom["intent"]: atom["priority_score"] for atom in snapshot["atoms"]}
    assert scores[operator_text] > scores[derived_text]


def test_runtime_policy_controls_confidence_and_owner_route(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    paths.policy.parent.mkdir(parents=True, exist_ok=True)
    paths.policy.write_text(
        json.dumps(
            {
                "confidence_thresholds": {
                    "semantic_atom": 0.9,
                    "structural_fallback": 0.1,
                },
                "owner_routing": {
                    "default_owner": "owner/runtime",
                    "default_route": "route/runtime",
                    "default_next_command": "python3 scripts/runtime-owner.py",
                    "sources": {"agy-cli-conversations": {"route": "issue:641"}},
                },
            }
        ),
        encoding="utf-8",
    )
    text = "Keep weak classifications structural."
    snapshot = corpus.update_ledger(
        paths,
        events=[
            _event(
                text,
                event_ref="runtime-policy",
                atoms=[
                    {
                        "text": text,
                        "kind": "ask",
                        "classification_confidence": 0.8,
                    }
                ],
            )
        ],
        cursor=_cursor(corpus),
    )
    atom = snapshot["atoms"][0]
    public = json.loads(paths.public_snapshot.read_text(encoding="utf-8"))
    policy = corpus.load_policy(paths.policy)

    assert atom["atomization_mode"] == "structural_fallback"
    assert atom["classification_confidence"] == 0.1
    assert atom["owner"] == "owner/runtime"
    assert atom["owner_route"] == "route/runtime"
    assert public["unresolved_atoms"][0]["owner"] == "owner/runtime"
    assert public["unresolved_atoms"][0]["owner_route"] == "route/runtime"
    assert policy["owner_routing"]["default_next_command"] == "python3 scripts/runtime-owner.py"
    assert policy["owner_routing"]["sources"] == {"agy-cli-conversations": {"route": "issue:641"}}


def test_runtime_policy_weights_and_authority_bands_control_exact_ranking(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    paths.policy.parent.mkdir(parents=True, exist_ok=True)
    weights = {name: 0.0 for name in corpus.DIMENSIONS}
    weights["magnitude"] = 1.0
    paths.policy.write_text(
        json.dumps(
            {
                "weights": weights,
                "authority_bands": {
                    "derived": {"floor": 0.0, "ceiling": 0.1},
                    "unknown": {"floor": 0.2, "ceiling": 0.3},
                    "operator": {"floor": 0.8, "ceiling": 0.9},
                },
            }
        ),
        encoding="utf-8",
    )
    low = "Keep the runtime-weighted low-magnitude item."
    high = "Keep the runtime-weighted high-magnitude item."
    snapshot = corpus.update_ledger(
        paths,
        events=[
            _event(
                low,
                event_ref="runtime-low",
                atoms=[
                    {
                        "text": low,
                        "kind": "ask",
                        "dimensions": {"magnitude": 0.0},
                    }
                ],
            ),
            _event(
                high,
                event_ref="runtime-high",
                atoms=[
                    {
                        "text": high,
                        "kind": "ask",
                        "dimensions": {"magnitude": 1.0},
                    }
                ],
            ),
        ],
        cursor=_cursor(corpus),
    )
    by_intent = {atom["intent"]: atom for atom in snapshot["atoms"]}

    assert by_intent[low]["priority_score"] == 80.0
    assert by_intent[high]["priority_score"] == 90.0
    assert by_intent[high]["priority_score"] > by_intent[low]["priority_score"]
    assert by_intent[high]["authority_band"] == {"floor": 0.8, "ceiling": 0.9}
    assert snapshot["atoms"][0]["intent"] == high


def test_hash_matched_local_predicate_receipt_can_close_atom(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    first = corpus.update_ledger(
        paths,
        events=[_event("Honor a local predicate receipt.", event_ref="local-proof")],
        cursor=_cursor(corpus),
    )
    atom_id = first["atoms"][0]["atom_id"]
    receipt = tmp_path / "docs" / "local-proof.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text('{"predicate":"pass"}\n', encoding="utf-8")
    receipt_hash = hashlib.sha256(receipt.read_bytes()).hexdigest()

    closed = corpus.update_ledger(
        paths,
        outcomes=[
            {
                "atom_id": atom_id,
                "disposition": "done",
                "owner": "organvm/limen",
                "assessed_at": "2026-07-11T12:05:00Z",
                "evidence": [
                    {
                        "kind": "predicate_receipt",
                        "ref": "docs/local-proof.json",
                        "predicate": "fixture predicate",
                        "result": "pass",
                        "verified_at": "2026-07-11T12:05:00Z",
                        "owner": "organvm/limen",
                        "subject_atom_ids": [atom_id],
                        "verifier": "local_predicate",
                        "exit_code": 0,
                        "artifact_sha256": receipt_hash,
                    }
                ],
            }
        ],
    )

    assert closed["validation"]["ok"] is True
    assert closed["counts"]["dispositions"] == {"done": 1}


@pytest.mark.parametrize("artifact_state", ["missing", "tampered"])
def test_local_predicate_receipt_must_still_exist_and_match_its_hash(tmp_path: Path, artifact_state: str):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    first = corpus.update_ledger(
        paths,
        events=[_event("Reject stale local predicate evidence.", event_ref=f"local-{artifact_state}")],
        cursor=_cursor(corpus),
    )
    atom_id = first["atoms"][0]["atom_id"]
    receipt = tmp_path / "docs" / "local-proof.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text('{"predicate":"pass"}\n', encoding="utf-8")
    receipt_hash = hashlib.sha256(receipt.read_bytes()).hexdigest()
    evidence = {
        "kind": "predicate_receipt",
        "ref": "docs/local-proof.json",
        "predicate": "fixture predicate",
        "result": "pass",
        "verified_at": "2026-07-11T12:05:00Z",
        "owner": "organvm/limen",
        "subject_atom_ids": [atom_id],
        "verifier": "local_predicate",
        "exit_code": 0,
        "artifact_sha256": receipt_hash,
    }
    if artifact_state == "missing":
        receipt.unlink()
    else:
        receipt.write_text('{"predicate":"changed"}\n', encoding="utf-8")
    before = paths.outcome_journal.read_bytes() if paths.outcome_journal.exists() else b""

    with pytest.raises(ValueError, match="typed, canonical"):
        corpus.update_ledger(
            paths,
            outcomes=[
                {
                    "atom_id": atom_id,
                    "disposition": "done",
                    "owner": "organvm/limen",
                    "assessed_at": "2026-07-11T12:05:00Z",
                    "evidence": [evidence],
                }
            ],
        )
    after = paths.outcome_journal.read_bytes() if paths.outcome_journal.exists() else b""
    assert after == before


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("owner", "organvm/other"),
        ("subject_atom_ids", ["pa-unrelated"]),
        ("state", "open"),
        ("reachable_from_default", False),
    ],
    ids=("owner", "subject", "state", "reachability"),
)
def test_github_proof_must_bind_owner_subject_merge_and_reachability(tmp_path: Path, field: str, value):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    first = corpus.update_ledger(
        paths,
        events=[_event("Reject forged GitHub closure fields.", event_ref=f"github-{field}")],
        cursor=_cursor(corpus),
    )
    atom_id = first["atoms"][0]["atom_id"]
    evidence = _passing_receipt(paths, atom_id)
    evidence[field] = value
    evidence = _bind_github_receipt(paths, evidence)
    before = paths.outcome_journal.read_bytes() if paths.outcome_journal.exists() else b""

    with pytest.raises(ValueError, match="typed, canonical"):
        corpus.update_ledger(
            paths,
            outcomes=[
                {
                    "atom_id": atom_id,
                    "disposition": "done",
                    "owner": "organvm/limen",
                    "assessed_at": "2026-07-11T12:05:00Z",
                    "evidence": [evidence],
                }
            ],
        )
    after = paths.outcome_journal.read_bytes() if paths.outcome_journal.exists() else b""
    assert after == before


def test_github_claim_requires_existing_hash_matched_verification_receipt(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    first = corpus.update_ledger(
        paths,
        events=[_event("Require durable GitHub verification.", event_ref="github-proof")],
        cursor=_cursor(corpus),
    )
    atom_id = first["atoms"][0]["atom_id"]
    evidence = _passing_receipt(paths, atom_id)
    receipt = paths.root / evidence["verification_receipt_ref"]
    receipt.write_text('{"tampered":true}\n', encoding="utf-8")

    try:
        corpus.update_ledger(
            paths,
            outcomes=[
                {
                    "atom_id": atom_id,
                    "disposition": "done",
                    "owner": "organvm/limen",
                    "assessed_at": "2026-07-11T12:05:00Z",
                    "evidence": [evidence],
                }
            ],
        )
    except ValueError as exc:
        assert "typed, canonical" in str(exc)
    else:
        raise AssertionError("self-asserted GitHub proof was accepted")


def test_outcome_history_is_revision_linked_monotonic_and_terminal(tmp_path: Path):
    corpus = _load()
    paths = _paths(corpus, tmp_path)
    snapshot = corpus.update_ledger(
        paths,
        events=[_event("Close this only with monotonic history.", event_ref="history")],
        cursor=_cursor(corpus),
    )
    atom_id = snapshot["atoms"][0]["atom_id"]
    first = {
        "atom_id": atom_id,
        "disposition": "not_done",
        "assessed_at": "2026-07-11T12:01:00Z",
    }
    corpus.update_ledger(paths, outcomes=[first])
    blocked = {
        "atom_id": atom_id,
        "disposition": "blocked",
        "owner": "organvm/limen",
        "gate": "external approval",
        "next_command": "gh issue view 1",
        "assessed_at": "2026-07-11T12:02:00Z",
        "revision_of": corpus.digest(first),
    }
    corpus.update_ledger(paths, outcomes=[blocked])
    before_rollback = paths.outcome_journal.read_bytes()

    rollback = {
        "atom_id": atom_id,
        "disposition": "not_done",
        "assessed_at": "2026-07-11T12:03:00Z",
        "revision_of": corpus.digest(blocked),
    }
    try:
        corpus.update_ledger(paths, outcomes=[rollback])
    except ValueError as exc:
        assert "rollback" in str(exc)
    else:
        raise AssertionError("outcome rollback was appended")
    assert paths.outcome_journal.read_bytes() == before_rollback

    done = {
        "atom_id": atom_id,
        "disposition": "done",
        "owner": "organvm/limen",
        "assessed_at": "2026-07-11T12:04:00Z",
        "revision_of": corpus.digest(blocked),
        "evidence": [_passing_receipt(paths, atom_id)],
    }
    closed = corpus.update_ledger(paths, outcomes=[done])
    assert closed["validation"]["ok"] is True
    terminal_bytes = paths.outcome_journal.read_bytes()

    terminal_rollback = {
        "atom_id": atom_id,
        "disposition": "blocked",
        "owner": "organvm/limen",
        "gate": "invented regression",
        "next_command": "false",
        "assessed_at": "2026-07-11T12:05:00Z",
        "revision_of": corpus.digest(done),
    }
    try:
        corpus.update_ledger(paths, outcomes=[terminal_rollback])
    except ValueError as exc:
        assert "terminal done outcome is immutable" in str(exc)
    else:
        raise AssertionError("terminal outcome was rolled back")
    assert paths.outcome_journal.read_bytes() == terminal_bytes


# --- source-missing exclusion receipt tests ---


def _source_missing_receipt(corpus) -> dict:
    """Build a minimal valid source-missing exclusion receipt."""
    contract = corpus.current_source_adapter_contract()
    return {
        "version": contract["version"],
        "disposition": "excluded",
        "contract_id": "source-missing-v1",
        "contract_digest": contract["digest"],
        "related_signatures": {},
        "related_evidence": {"observed_missing_at": "2026-07-14T12:00:00+00:00"},
    }


def _source_missing_cursor_proposal(corpus, key: str, *, base_revision: int = 0, current: dict) -> dict:
    """Build a minimal scan proposal that resolves one missing-source key."""
    contract = corpus.current_source_adapter_contract()
    receipt = _source_missing_receipt(corpus)
    receipts = {key: receipt}
    source_units = sorted([key])
    unresolved = []
    return {
        "base_revision": base_revision,
        "base_cursor_digest": corpus.cursor_digest(current),
        "scanner_version": contract["scanner_version"],
        "scope": "partial:all",
        "target_scope": "all",
        "all_baseline_complete": False,
        "source_manifest_digest": corpus.digest({"test": 1}),
        "all_source_manifest_digest": None,
        "source_unit_count": len(source_units),
        "source_units": source_units,
        "source_units_digest": corpus.digest(source_units),
        "source_adapter_contract": contract,
        "excluded_source_count": len(receipts),
        "source_exclusion_counts": {"source-missing-v1": 1},
        "excluded_unit_receipts": receipts,
        "excluded_unit_receipts_digest": corpus.digest(receipts),
        "adapted_source_count": 0,
        "source_adapter_counts": {},
        "adapted_unit_receipts": {},
        "adapted_unit_receipts_digest": corpus.digest({}),
        "unsupported_source_count": 0,
        "unsupported_units": {},
        "unsupported_units_digest": corpus.digest({}),
        "unresolved_unit_count": 0,
        "unresolved_units": unresolved,
        "unresolved_units_digest": corpus.digest(unresolved),
        "source_errors": [],
        "pending_files": 0,
        "files": {},
    }


def test_source_missing_receipt_passes_validate_source_adapter_cursor():
    """validate_source_adapter_cursor accepts source-missing-v1 receipts without a file signature."""
    corpus = _load()
    contract = corpus.current_source_adapter_contract()
    key = "scan-v2:agy-cli-conversations:/home/.gemini/antigravity-cli/conversations/gone.db"
    receipt = _source_missing_receipt(corpus)
    receipts = {key: receipt}
    source_units = sorted([key])
    cursor = {
        "scanner_version": contract["scanner_version"],
        "scope": "partial:all",
        "target_scope": "all",
        "all_baseline_complete": False,
        "source_manifest_digest": corpus.digest({"test": 1}),
        "all_source_manifest_digest": None,
        "source_unit_count": len(source_units),
        "source_units": source_units,
        "source_units_digest": corpus.digest(source_units),
        "source_adapter_contract": contract,
        "excluded_source_count": 1,
        "source_exclusion_counts": {"source-missing-v1": 1},
        "excluded_unit_receipts": receipts,
        "excluded_unit_receipts_digest": corpus.digest(receipts),
        "adapted_source_count": 0,
        "source_adapter_counts": {},
        "adapted_unit_receipts": {},
        "adapted_unit_receipts_digest": corpus.digest({}),
        "unsupported_source_count": 0,
        "unsupported_units": {},
        "unsupported_units_digest": corpus.digest({}),
        "unresolved_unit_count": 0,
        "unresolved_units": [],
        "unresolved_units_digest": corpus.digest([]),
        "source_errors": [],
        "pending_files": 0,
        "files": {},
        "source_families": {
            "agy-cli-conversations": {
                "discovered": 1,
                "converged": 0,
                "adapted": 0,
                "excluded": 1,
                "pending": 0,
                "errors": 0,
                "unsupported": 0,
            }
        },
    }

    errors = corpus.validate_source_adapter_cursor(cursor)
    assert errors == [], f"Unexpected validation errors: {errors}"


def test_merge_cursor_accepts_source_missing_exclusion_for_vanished_paths():
    """merge_cursor accepts a proposal that resolves unresolved units via source-missing receipts."""
    corpus = _load()
    contract = corpus.current_source_adapter_contract()
    gone_key = "scan-v2:agy-cli-conversations:/home/.gemini/antigravity-cli/conversations/gone.db"

    unresolved_list = [gone_key]
    current = {
        "revision": 3,
        "scanner_version": contract["scanner_version"],
        "scope": "partial:all",
        "target_scope": "all",
        "pending_files": 0,
        "source_errors": [],
        "source_adapter_contract": contract,
        "excluded_source_count": 0,
        "source_exclusion_counts": {},
        "excluded_unit_receipts": {},
        "excluded_unit_receipts_digest": corpus.digest({}),
        "adapted_source_count": 0,
        "source_adapter_counts": {},
        "adapted_unit_receipts": {},
        "adapted_unit_receipts_digest": corpus.digest({}),
        "unsupported_source_count": 0,
        "unsupported_units": {},
        "unsupported_units_digest": corpus.digest({}),
        "unresolved_unit_count": 1,
        "unresolved_units": unresolved_list,
        "unresolved_units_digest": corpus.digest(unresolved_list),
        "files": {},
    }

    proposed = _source_missing_cursor_proposal(corpus, gone_key, base_revision=3, current=current)

    merged = corpus.merge_cursor(current, proposed)

    assert merged["unresolved_unit_count"] == 0
    assert merged["unresolved_units"] == []
    assert gone_key in merged["excluded_unit_receipts"]
    assert merged["excluded_unit_receipts"][gone_key]["contract_id"] == "source-missing-v1"
    assert gone_key in merged["source_units"]


def test_merge_cursor_source_missing_is_idempotent():
    """A second proposal for already-resolved source-missing keys is a no-op (no errors)."""
    corpus = _load()
    contract = corpus.current_source_adapter_contract()
    gone_key = "scan-v2:agy-cli-conversations:/home/.gemini/antigravity-cli/conversations/gone2.db"

    unresolved_list = [gone_key]
    current = {
        "revision": 1,
        "scanner_version": contract["scanner_version"],
        "scope": "partial:all",
        "target_scope": "all",
        "pending_files": 0,
        "source_errors": [],
        "source_adapter_contract": contract,
        "excluded_source_count": 0,
        "source_exclusion_counts": {},
        "excluded_unit_receipts": {},
        "excluded_unit_receipts_digest": corpus.digest({}),
        "adapted_source_count": 0,
        "source_adapter_counts": {},
        "adapted_unit_receipts": {},
        "adapted_unit_receipts_digest": corpus.digest({}),
        "unsupported_source_count": 0,
        "unsupported_units": {},
        "unsupported_units_digest": corpus.digest({}),
        "unresolved_unit_count": 1,
        "unresolved_units": unresolved_list,
        "unresolved_units_digest": corpus.digest(unresolved_list),
        "files": {},
    }
    proposed = _source_missing_cursor_proposal(corpus, gone_key, base_revision=1, current=current)
    merged1 = corpus.merge_cursor(current, proposed)
    assert merged1["unresolved_unit_count"] == 0

    # Second proposal: gone_key already gone from unresolved, already in excluded.
    # Build a fresh proposal against the merged state.
    proposed2 = _source_missing_cursor_proposal(corpus, gone_key, base_revision=merged1["revision"], current=merged1)
    # gone_key is no longer in merged1["unresolved_units"], so cleared_unresolved is empty.
    merged2 = corpus.merge_cursor(merged1, proposed2)
    assert merged2["unresolved_unit_count"] == 0
    assert gone_key in merged2["excluded_unit_receipts"]


def test_existing_path_is_not_excluded_as_source_missing(tmp_path: Path):
    """A unit key whose path EXISTS is not resolved by the source-missing path."""
    corpus = _load()
    contract = corpus.current_source_adapter_contract()

    existing_file = tmp_path / "real_file.db"
    existing_file.write_bytes(b"data")
    existing_key = f"scan-v2:agy-cli-conversations:{existing_file}"

    gone_key = "scan-v2:agy-cli-conversations:/definitely/does/not/exist/nowhere.db"
    unresolved_list = sorted([existing_key, gone_key])
    current = {
        "revision": 0,
        "scanner_version": contract["scanner_version"],
        "scope": "partial:all",
        "target_scope": "all",
        "pending_files": 0,
        "source_errors": [],
        "source_adapter_contract": contract,
        "excluded_source_count": 0,
        "source_exclusion_counts": {},
        "excluded_unit_receipts": {},
        "excluded_unit_receipts_digest": corpus.digest({}),
        "adapted_source_count": 0,
        "source_adapter_counts": {},
        "adapted_unit_receipts": {},
        "adapted_unit_receipts_digest": corpus.digest({}),
        "unsupported_source_count": 0,
        "unsupported_units": {},
        "unsupported_units_digest": corpus.digest({}),
        "unresolved_unit_count": 2,
        "unresolved_units": unresolved_list,
        "unresolved_units_digest": corpus.digest(unresolved_list),
        "files": {},
    }

    # Build a proposal that resolves only the gone key (not the existing one).
    receipt = _source_missing_receipt(corpus)
    receipts = {gone_key: receipt}
    source_units = sorted([gone_key])
    proposed = {
        "base_revision": 0,
        "base_cursor_digest": corpus.cursor_digest(current),
        "scanner_version": contract["scanner_version"],
        "scope": "partial:all",
        "target_scope": "all",
        "all_baseline_complete": False,
        "source_manifest_digest": corpus.digest({"test": 2}),
        "all_source_manifest_digest": None,
        "source_unit_count": len(source_units),
        "source_units": source_units,
        "source_units_digest": corpus.digest(source_units),
        "source_adapter_contract": contract,
        "excluded_source_count": len(receipts),
        "source_exclusion_counts": {"source-missing-v1": 1},
        "excluded_unit_receipts": receipts,
        "excluded_unit_receipts_digest": corpus.digest(receipts),
        "adapted_source_count": 0,
        "source_adapter_counts": {},
        "adapted_unit_receipts": {},
        "adapted_unit_receipts_digest": corpus.digest({}),
        "unsupported_source_count": 0,
        "unsupported_units": {},
        "unsupported_units_digest": corpus.digest({}),
        "unresolved_unit_count": 1,
        "unresolved_units": [existing_key],
        "unresolved_units_digest": corpus.digest([existing_key]),
        "source_errors": [],
        "pending_files": 0,
        "files": {},
    }

    merged = corpus.merge_cursor(current, proposed)

    # The existing-path key stays unresolved; only gone_key is resolved.
    assert existing_key in merged["unresolved_units"]
    assert gone_key not in merged["unresolved_units"]
    assert gone_key in merged["excluded_unit_receipts"]
    assert existing_key not in merged["excluded_unit_receipts"]


def test_merge_cursor_accepts_version_superseded_cleared_keys(tmp_path: Path):
    """A cleared old-version key whose (source, path) is tracked under a newer
    scan-version key in the proposal is version-superseded — accepted without
    an explicit receipt."""
    corpus = _load()
    contract = corpus.current_source_adapter_contract()
    scanner_version = contract["scanner_version"]

    path = tmp_path / "conv.db"
    path.write_bytes(b"data")
    old_key = f"scan-v{scanner_version - 1}:agy-cli-conversations:{path}"
    new_key = f"scan-v{scanner_version}:agy-cli-conversations:{path}"
    current = {
        "revision": 0,
        "scanner_version": scanner_version,
        "scope": "partial:all",
        "target_scope": "all",
        "pending_files": 0,
        "source_errors": [],
        "source_adapter_contract": contract,
        "excluded_source_count": 0,
        "source_exclusion_counts": {},
        "excluded_unit_receipts": {},
        "excluded_unit_receipts_digest": corpus.digest({}),
        "adapted_source_count": 0,
        "source_adapter_counts": {},
        "adapted_unit_receipts": {},
        "adapted_unit_receipts_digest": corpus.digest({}),
        "unsupported_source_count": 0,
        "unsupported_units": {},
        "unsupported_units_digest": corpus.digest({}),
        "unresolved_unit_count": 1,
        "unresolved_units": [old_key],
        "unresolved_units_digest": corpus.digest([old_key]),
        "files": {},
    }
    source_units = [new_key]
    proposed = {
        "base_revision": 0,
        "base_cursor_digest": corpus.cursor_digest(current),
        "scanner_version": scanner_version,
        "scope": "partial:all",
        "target_scope": "all",
        "all_baseline_complete": False,
        "source_manifest_digest": corpus.digest({"test": 3}),
        "all_source_manifest_digest": None,
        "source_unit_count": len(source_units),
        "source_units": source_units,
        "source_units_digest": corpus.digest(source_units),
        "source_adapter_contract": contract,
        "excluded_source_count": 0,
        "source_exclusion_counts": {},
        "excluded_unit_receipts": {},
        "excluded_unit_receipts_digest": corpus.digest({}),
        "adapted_source_count": 0,
        "source_adapter_counts": {},
        "adapted_unit_receipts": {},
        "adapted_unit_receipts_digest": corpus.digest({}),
        "unsupported_source_count": 0,
        "unsupported_units": {},
        "unsupported_units_digest": corpus.digest({}),
        "unresolved_unit_count": 1,
        "unresolved_units": [new_key],
        "unresolved_units_digest": corpus.digest([new_key]),
        "source_errors": [],
        "pending_files": 0,
        "files": {},
    }

    merged = corpus.merge_cursor(current, proposed)

    # The old-version key is superseded by the new-version key; no receipt required.
    assert old_key not in merged["unresolved_units"]
    assert new_key in merged["unresolved_units"]

    # A CURRENT-version key gets no supersession excuse: clearing it without
    # parsed or excluded proof must still be rejected.
    current_same = dict(current)
    current_same["unresolved_units"] = [new_key]
    current_same["unresolved_units_digest"] = corpus.digest([new_key])
    proposed_same = dict(proposed)
    proposed_same["base_cursor_digest"] = corpus.cursor_digest(current_same)
    proposed_same["unresolved_unit_count"] = 0
    proposed_same["unresolved_units"] = []
    proposed_same["unresolved_units_digest"] = corpus.digest([])
    with pytest.raises(ValueError, match="lack parsed or excluded resolution proof"):
        corpus.merge_cursor(current_same, proposed_same)


def _load_ledger_script():
    spec = importlib.util.spec_from_file_location("prompt_atom_ledger_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_checkpointed_cursor(corpus, paths, cursor: dict) -> None:
    paths.private_dir.mkdir(parents=True, exist_ok=True)
    paths.cursor.write_text(json.dumps(cursor), encoding="utf-8")
    marker = {
        "source_cursor_digest": corpus.cursor_digest(cursor),
        "journal_signatures": {"cursor": corpus._path_signature(paths.cursor)},
    }
    paths.private_snapshot.write_text(json.dumps(marker), encoding="utf-8")


def test_check_cursor_state_passes_on_coherent_cursor(tmp_path: Path):
    corpus = _load()
    ledger = _load_ledger_script()
    paths = _paths(corpus, tmp_path)
    key = f"scan-v{ledger.SCANNER_VERSION}:agy-cli-conversations:/tmp/live.db"
    cursor = {
        "revision": 1,
        "scanner_version": ledger.SCANNER_VERSION,
        "unresolved_units": [key],
        "files": {},
    }
    _write_checkpointed_cursor(corpus, paths, cursor)

    assert ledger.check_cursor_state(paths) == []


def test_check_cursor_state_flags_orphaned_scan_version_keys(tmp_path: Path):
    corpus = _load()
    ledger = _load_ledger_script()
    paths = _paths(corpus, tmp_path)
    orphan = f"scan-v{ledger.SCANNER_VERSION - 1}:agy-cli-conversations:/tmp/gone.db"
    cursor = {
        "revision": 1,
        "scanner_version": ledger.SCANNER_VERSION,
        "unresolved_units": [orphan],
        "files": {},
    }
    _write_checkpointed_cursor(corpus, paths, cursor)

    errors = ledger.check_cursor_state(paths)
    assert any("orphaned" in error for error in errors)


def test_check_cursor_state_flags_unbound_checkpoint(tmp_path: Path):
    corpus = _load()
    ledger = _load_ledger_script()
    paths = _paths(corpus, tmp_path)
    cursor = {
        "revision": 1,
        "scanner_version": ledger.SCANNER_VERSION,
        "unresolved_units": [],
        "files": {},
    }
    _write_checkpointed_cursor(corpus, paths, cursor)
    # Mutate the cursor after the checkpoint marker was sealed.
    cursor["revision"] = 2
    paths.cursor.write_text(json.dumps(cursor), encoding="utf-8")

    errors = ledger.check_cursor_state(paths)
    assert any("not bound" in error for error in errors)
