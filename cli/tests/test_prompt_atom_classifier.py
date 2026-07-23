from __future__ import annotations

import importlib.util
import json
import os
import shlex
import subprocess
import sys
import textwrap
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prompt-atom-ledger.py"


def _load():
    spec = importlib.util.spec_from_file_location("prompt_atom_classifier", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _event(text: str, event_ref: str, *, timestamp: str = "2026-07-11T12:00:00Z") -> dict:
    return {
        "source": "fixture",
        "session_ref": "session-one",
        "event_ref": event_ref,
        "event_index": 0,
        "text_index": 0,
        "timestamp": timestamp,
        "text": text,
        "body_kind": "direct",
        "provenance": "operator_typed",
        "authority": "operator",
    }


def _write_helper(path: Path, source: str) -> None:
    path.write_text(textwrap.dedent(source), encoding="utf-8")


def test_classifier_command_uses_exact_jsonl_ids_and_grounded_segments(
    tmp_path: Path,
    monkeypatch,
):
    ledger = _load()
    helper = tmp_path / "classifier.py"
    capture = tmp_path / "requests.json"
    _write_helper(
        helper,
        """
        import json
        import sys

        requests = [json.loads(line) for line in sys.stdin if line.strip()]
        with open(sys.argv[1], "w", encoding="utf-8") as handle:
            json.dump(requests, handle, sort_keys=True)
        for request in reversed(requests):
            segment = request["segments"][0]
            print(json.dumps({
                "occurrence_id": request["occurrence_id"],
                "atoms": [{
                    "text": segment["text"],
                    "kind": "ask",
                    "coverage_segment_indexes": [segment["index"]],
                    "source_segments": [segment["text"]],
                    "classification_confidence": 0.91,
                    "classifier_provenance": "untrusted-output-label",
                }],
            }, sort_keys=True))
        """,
    )
    command = shlex.join([sys.executable, str(helper), str(capture)])
    seen: dict = {}
    real_popen = ledger.subprocess.Popen

    def recording_popen(*args, **kwargs):
        seen.update(kwargs)
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(ledger.subprocess, "Popen", recording_popen)
    events = [
        _event("Build the registry. Verify it.", "one"),
        _event("Preserve the receipt.", "two"),
    ]
    result = ledger.classify_events(events, command=command, policy={})

    assert result.error is None
    assert result.attempted is True
    assert result.classified_occurrences == 2
    assert seen["shell"] is False
    assert all(event["atoms"][0]["classifier_provenance"] == "runtime_command" for event in result.events)
    requests = json.loads(capture.read_text(encoding="utf-8"))
    assert [request["occurrence_id"] for request in requests] == [
        ledger.occurrence_from_event(event)["occurrence_id"] for event in events
    ]
    assert requests[0]["segments"] == [
        {"index": 0, "text": "Build the registry."},
        {"index": 1, "text": "Verify it."},
    ]
    assert all("model" not in request and "provider" not in request for request in requests)


def test_cli_main_uses_opaque_classifier_command_from_environment(tmp_path: Path):
    ledger = _load()
    helper = tmp_path / "classifier.py"
    _write_helper(
        helper,
        """
        import json
        import sys

        for line in sys.stdin:
            request = json.loads(line)
            segment = request["segments"][0]
            print(json.dumps({
                "occurrence_id": request["occurrence_id"],
                "atoms": [{
                    "text": segment["text"],
                    "kind": "ask",
                    "coverage_segment_indexes": [segment["index"]],
                    "source_segments": [segment["text"]],
                    "classification_confidence": 0.97,
                }],
            }, sort_keys=True))
        """,
    )
    event_path = tmp_path / "events.jsonl"
    event_path.write_text(
        json.dumps(_event("Classify this through the CLI environment.", "cli-env")) + "\n",
        encoding="utf-8",
    )
    root = tmp_path / "ledger"
    private_root = tmp_path / "private"
    env = os.environ.copy()
    env.pop("LIMEN_PRIVATE_SESSION_CORPUS", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["LIMEN_PROMPT_CLASSIFIER_CMD"] = shlex.join([sys.executable, str(helper)])

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--events-jsonl",
            str(event_path),
            "--write",
            "--root",
            str(root),
            "--private-root",
            str(private_root),
        ],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert completed.returncode == 0, completed.stderr
    paths = ledger.LedgerPaths.for_root(root, private_root=private_root)
    occurrences, atoms, errors = ledger.load_event_journal(paths.event_journal)
    assert errors == []
    assert len(occurrences) == 1
    assert len(atoms) == 1
    assert atoms[0]["atomization_mode"] == "semantic_adapter"
    assert atoms[0]["classifier_provenance"] == "runtime_command"
    assert atoms[0]["classification_confidence"] == 0.97


def test_classifier_absence_or_wrong_occurrence_id_keeps_structural_fallback(tmp_path: Path):
    ledger = _load()
    event = _event("Keep every source segment.", "fallback")

    absent = ledger.classify_events([event], command=None, policy={})
    assert absent.attempted is False
    assert "atoms" not in absent.events[0]

    helper = tmp_path / "wrong-id.py"
    _write_helper(
        helper,
        """
        import json
        print(json.dumps({"occurrence_id": "po-wrong", "atoms": []}))
        """,
    )
    wrong = ledger.classify_events(
        [event],
        command=shlex.join([sys.executable, str(helper)]),
        policy={},
    )
    assert "unexpected occurrence id" in str(wrong.error)
    assert wrong.classified_occurrences == 0
    assert "atoms" not in wrong.events[0]


def test_classifier_timeout_is_strict_and_falls_back(tmp_path: Path):
    ledger = _load()
    helper = tmp_path / "slow.py"
    _write_helper(
        helper,
        """
        import time
        time.sleep(5)
        """,
    )
    started = time.monotonic()
    result = ledger.classify_events(
        [_event("Bound the classifier.", "timeout")],
        command=shlex.join([sys.executable, str(helper)]),
        policy={"confidence_thresholds": {"command_timeout_seconds": 0.05}},
    )

    assert time.monotonic() - started < 2.0
    assert "exceeded 0.05s timeout" in str(result.error)
    assert "atoms" not in result.events[0]


def test_classifier_streams_under_input_output_and_stderr_caps(tmp_path: Path):
    ledger = _load()
    helper = tmp_path / "oversized.py"
    _write_helper(
        helper,
        """
        import sys
        sys.stdout.write("x" * 4096)
        """,
    )
    policy = {
        "resource_limits": {
            "max_classifier_input_bytes": 1024,
            "max_classifier_output_bytes": 128,
            "max_classifier_stderr_bytes": 128,
        }
    }

    oversized_output = ledger.classify_events(
        [_event("Bound classifier output.", "output-cap")],
        command=shlex.join([sys.executable, str(helper)]),
        policy=policy,
    )
    oversized_input = ledger.classify_events(
        [_event("x" * 4096, "input-cap")],
        command=shlex.join([sys.executable, str(helper)]),
        policy=policy,
    )

    assert "bounded response limit" in str(oversized_output.error)
    assert "bounded byte limit" in str(oversized_input.error)
    assert "atoms" not in oversized_output.events[0]
    assert "atoms" not in oversized_input.events[0]

    _write_helper(
        helper,
        """
        import sys
        sys.stderr.write("x" * 4096)
        """,
    )
    oversized_stderr = ledger.classify_events(
        [_event("Bound classifier stderr.", "stderr-cap")],
        command=shlex.join([sys.executable, str(helper)]),
        policy=policy,
    )
    assert "bounded diagnostic limit" in str(oversized_stderr.error)


def test_reclassification_rehydrates_canonical_raw_objects_with_reserved_ids(tmp_path: Path):
    ledger = _load()
    paths = ledger.LedgerPaths.for_root(tmp_path)
    events = [
        _event("First structural ask.", "first", timestamp="2026-07-11T12:00:00Z"),
        _event("Second structural ask.", "second", timestamp="2026-07-11T12:01:00Z"),
        _event("Third structural ask.", "third", timestamp="2026-07-11T12:02:00Z"),
    ]
    snapshot = ledger.update_ledger(
        paths,
        events=events,
        cursor={
            "version": 1,
            "scope": "fixture",
            "source_manifest_digest": ledger.digest({"fixture": 1}),
            "files": {},
        },
    )

    selected = ledger.existing_reclassification_events(
        paths,
        {"reclassification": {"max_occurrences_per_run": 2}},
    )

    assert len(selected) == 2
    assert [event["existing_occurrence_id"] for event in selected] == [
        occurrence["occurrence_id"] for occurrence in snapshot["occurrences"][:2]
    ]
    assert [event["text"] for event in selected] == [
        "First structural ask.",
        "Second structural ask.",
    ]
    assert all("occurrence_id" not in event for event in selected)


def test_classifier_reclassifies_existing_identity_once_without_journal_churn(tmp_path: Path):
    ledger = _load()
    paths = ledger.LedgerPaths.for_root(tmp_path)
    first = ledger.update_ledger(
        paths,
        events=[_event("Enrich this structural ask.", "existing")],
        cursor={
            "version": 1,
            "scope": "fixture",
            "source_manifest_digest": ledger.digest({"fixture": 1}),
            "files": {},
        },
    )
    occurrence_id = first["occurrences"][0]["occurrence_id"]
    helper = tmp_path / "enrich.py"
    _write_helper(
        helper,
        """
        import json
        import sys

        for line in sys.stdin:
            request = json.loads(line)
            segment = request["segments"][0]
            print(json.dumps({
                "occurrence_id": request["occurrence_id"],
                "atoms": [{
                    "text": segment["text"],
                    "kind": "ask",
                    "coverage_segment_indexes": [segment["index"]],
                    "source_segments": [segment["text"]],
                    "classification_confidence": 0.9,
                }],
            }))
        """,
    )
    selected = ledger.existing_reclassification_events(paths, {})
    classified = ledger.classify_events(
        selected,
        command=shlex.join([sys.executable, str(helper)]),
        policy={},
    )
    revised = ledger.update_ledger(paths, events=classified.events)
    journal_lines = paths.event_journal.read_text(encoding="utf-8").splitlines()
    unchanged = ledger.update_ledger(paths, events=classified.events)

    assert revised["appended"]["reclassified"] == 1
    assert revised["coverage"]["occurrences"] == 1
    assert revised["occurrences"][0]["occurrence_id"] == occurrence_id
    assert revised["occurrences"][0]["classification_revision"] == 1
    assert revised["atoms"][0]["atomization_mode"] == "semantic_adapter"
    assert unchanged["appended"]["reclassified"] == 0
    assert paths.event_journal.read_text(encoding="utf-8").splitlines() == journal_lines


def test_adapter_gaps_are_owner_routed_without_local_paths():
    ledger = _load()
    routes = ledger.build_adapter_gap_routes(
        ["agy-cli-conversations", "/Users/private/raw-adapter"],
        {
            "owner_routing": {
                "default_owner": "organvm/limen",
                "default_route": "TABVLARIVS/prompt-atom-intake",
                "sources": {
                    "agy-cli-conversations": {
                        "owner": "organvm/limen#641",
                        "route": "issue:641",
                        "failed_predicate": "agy-native-prompt-adapter-complete",
                        "next_command": "python3 scripts/prompt-atom-ledger.py --scan --all --write",
                    },
                    "/Users/private/raw-adapter": {
                        "next_command": "/Users/private/fix-adapter",
                    },
                },
            }
        },
    )

    assert routes[0] == {
        "source": "source-" + ledger.digest("/Users/private/raw-adapter")[:12],
        "owner": "organvm/limen",
        "route": "TABVLARIVS/prompt-atom-intake",
        "failed_predicate": "prompt-source-adapter:source-"
        + ledger.digest("/Users/private/raw-adapter")[:12]
        + ":complete",
        "next_command": "python3 scripts/prompt-atom-ledger.py --scan --all --write",
    }
    assert routes[1] == {
        "source": "agy-cli-conversations",
        "owner": "organvm/limen#641",
        "route": "issue:641",
        "failed_predicate": "agy-native-prompt-adapter-complete",
        "next_command": "python3 scripts/prompt-atom-ledger.py --scan --all --write",
    }
    assert "/Users/" not in json.dumps(routes)


def test_scan_proposal_rotates_fair_budget_and_carries_nonsemantic_cas_metadata(
    tmp_path: Path,
    monkeypatch,
):
    ledger = _load()
    paths = ledger.LedgerPaths.for_root(tmp_path)
    paths.private_dir.mkdir(parents=True)
    current = {
        "version": 1,
        "revision": 1,
        "scope": "partial:all",
        "target_scope": "all",
        "pending_files": 3,
        "source_errors": [],
        "source_manifest_digest": "old",
        "source_families": {},
        "files": {},
    }
    paths.cursor.write_text(json.dumps(current), encoding="utf-8")
    scan_paths = type("ScanPaths", (), {"cursor": paths.cursor, "policy": paths.policy})()
    lifecycle = type(
        "Lifecycle",
        (),
        {
            "LOCAL_SOURCES": [],
            "HOME": tmp_path / "missing-home",
            "OPENCODE_DB": tmp_path / "missing-opencode.db",
            "AGY_CLI_CONVERSATIONS": tmp_path / "missing-agy",
        },
    )()
    monkeypatch.setattr(ledger, "load_lifecycle_module", lambda: lifecycle)
    monkeypatch.setattr(
        ledger,
        "regular_source_rows",
        lambda _lifecycle, _days, **_kwargs: [],
    )
    monkeypatch.setattr(
        ledger,
        "active_scan_lanes",
        lambda _lifecycle, _rows: {"codex", "claude", "gemini", "opencode", "agy"},
    )
    volatile_scanned = {"value": 9}
    used: dict[str, int] = {}

    def result_for(source: str, budget, *, regular: bool = False):
        while budget.claim():
            pass
        used[source] = budget.used
        signature = {"size": 1, "mtime_ns": 1, "ctime_ns": 1, "inode": 1, "device": 1}
        unit = f"scan-v2:{source}:fixture"
        common = {
            "discovered": {unit: signature},
            "errors": [],
            "unsupported": [],
            "pending_files": 0,
            "attempted_files": budget.used,
            "coverage": {
                source: {
                    "discovered": 1,
                    "converged": 1,
                    "scanned": volatile_scanned["value"],
                    "pending": 0,
                    "errors": 0,
                    "unsupported": 0,
                }
            },
        }
        if regular:
            return [], {
                **common,
                "files": {unit: signature},
                "processed_files": budget.used,
                "unsupported_units": {},
            }
        return [], {**common, "processed": {unit: signature}}

    def regular_result(_lifecycle, _cursor, *, days, budget, rows, limits):
        discovered = {}
        files = {}
        coverage = {}
        for lane in ("codex", "claude", "gemini"):
            while budget[lane].claim():
                pass
            used[lane] = budget[lane].used
            signature = {"size": 1, "mtime_ns": 1, "ctime_ns": 1, "inode": 1, "device": 1}
            unit = f"scan-v2:{lane}:fixture"
            discovered[unit] = signature
            files[unit] = signature
            coverage[lane] = {
                "discovered": 1,
                "converged": 1,
                "scanned": volatile_scanned["value"],
                "pending": 0,
                "errors": 0,
                "unsupported": 0,
            }
        return [], {
            "discovered": discovered,
            "files": files,
            "processed_files": sum(used[lane] for lane in ("codex", "claude", "gemini")),
            "errors": [],
            "unsupported": [],
            "unsupported_units": {},
            "excluded_unit_receipts": {},
            "excluded_file_keys": [],
            "source_exclusion_counts": {},
            "adapted_unit_receipts": {},
            "source_adapter_counts": {},
            "pending_files": 0,
            "attempted_files": sum(used[lane] for lane in ("codex", "claude", "gemini")),
            "coverage": coverage,
        }

    monkeypatch.setattr(ledger, "scan_regular_sources", regular_result)
    monkeypatch.setattr(
        ledger,
        "scan_opencode",
        lambda _lifecycle, _cursor, *, days, budget, limits: result_for("opencode", budget),
    )
    monkeypatch.setattr(
        ledger,
        "scan_agy_conversations",
        lambda _lifecycle, _cursor, *, days, budget, limits: result_for("agy", budget),
    )

    policy = {
        "owner_routing": {
            "default_owner": "organvm/limen",
            "default_route": "TABVLARIVS/prompt-atom-intake",
        }
    }
    _events, first = ledger.scan_native_sources(
        scan_paths,
        days=None,
        max_files=5,
        policy=policy,
    )
    first_used = dict(used)
    volatile_scanned["value"] = 0
    _events, second = ledger.scan_native_sources(
        scan_paths,
        days=None,
        max_files=5,
        policy=policy,
    )

    assert first_used == {
        "codex": 1,
        "claude": 1,
        "gemini": 1,
        "opencode": 1,
        "agy": 1,
    }
    assert first["work_units_used"] == 5
    assert first["base_revision"] == 1
    assert first["base_cursor_digest"] == ledger.cursor_digest(current)
    assert first["adapter_gap_routes"] == []
    without_cas = {key: value for key, value in first.items() if key not in {"base_revision", "base_cursor_digest"}}
    assert ledger.cursor_digest(first) == ledger.cursor_digest(without_cas)
    assert first["source_manifest_digest"] == second["source_manifest_digest"]
