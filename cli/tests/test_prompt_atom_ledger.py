from __future__ import annotations

import importlib.util
import hashlib
import json
import subprocess
import sys
from pathlib import Path


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
        cursor=_cursor(corpus),
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
        cursor=_cursor(corpus),
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
        cursor=_cursor(corpus),
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


def _passing_receipt(paths, atom_id: str, *, owner: str = "organvm/limen") -> dict:
    evidence = {
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
    }
    receipt_ref = f"docs/github-proof-{atom_id}.json"
    receipt = paths.root / receipt_ref
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(
        json.dumps(
            {
                "schema": "limen.github-verification.v1",
                "exit_code": 0,
                "evidence": evidence,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    evidence["verification_receipt_ref"] = receipt_ref
    evidence["verification_receipt_sha256"] = hashlib.sha256(receipt.read_bytes()).hexdigest()
    return evidence


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


def test_cursor_merge_never_downgrades_newer_file_or_promotes_partial_all():
    corpus = _load()
    current = {
        "scope": "partial:all",
        "target_scope": "all",
        "pending_files": 4,
        "source_errors": [],
        "files": {"source:a": {"size": 10, "mtime_ns": 20}},
    }
    recent = {
        "scope": "recent:14",
        "target_scope": "recent:14",
        "pending_files": 0,
        "source_errors": [],
        "files": {"source:a": {"size": 99, "mtime_ns": 10}},
    }
    merged = corpus.merge_cursor(current, recent)

    assert merged["scope"] == "partial:all"
    assert merged["pending_files"] == 4
    assert merged["files"]["source:a"] == {"size": 10, "mtime_ns": 20}


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
    current = {
        "revision": 7,
        "scope": "partial:all",
        "target_scope": "all",
        "pending_files": 3,
        "source_errors": ["claude-plans: adapter missing"],
        "files": {"source:a": {"size": 20, "mtime_ns": 20}},
    }
    proposed = {
        "base_revision": 6,
        "base_cursor_digest": corpus.digest({"stale": True}),
        "revision": 6,
        "scope": "all",
        "target_scope": "all",
        "pending_files": 0,
        "source_errors": [],
        "files": {
            "source:a": {"size": 10, "mtime_ns": 10},
            "source:b": {"size": 1, "mtime_ns": 30},
        },
    }

    merged = corpus.merge_cursor(current, proposed)

    assert merged["scope"] == "partial:all"
    assert merged["pending_files"] == 3
    assert merged["source_errors"] == [
        "claude-plans: adapter missing",
        "stale cursor proposal requires a fresh scan",
    ]
    assert merged["files"]["source:a"] == {"size": 20, "mtime_ns": 20}
    assert merged["files"]["source:b"] == {"size": 1, "mtime_ns": 30}
    assert "base_revision" not in merged
    assert "base_cursor_digest" not in merged


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
