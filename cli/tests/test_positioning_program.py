from __future__ import annotations

import copy
import importlib.machinery
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "positioning-program.py"
MANIFEST = ROOT / "institutio" / "positioning" / "program.yaml"


def _load_module():
    loader = importlib.machinery.SourceFileLoader("positioning_program", str(SCRIPT))
    spec = importlib.util.spec_from_loader("positioning_program", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


MODULE = _load_module()


def graph_and_map():
    graph = MODULE.index_program(MODULE.load_manifest(MANIFEST))
    mapping = {
        "schema_version": MODULE.MAP_SCHEMA,
        "repository": "organvm/limen",
        "milestone": {"number": 1, "title": "Program", "url": "https://example.test/milestone/1"},
        "issues": {
            object_id: {"number": index, "url": f"https://example.test/issues/{index}"}
            for index, object_id in enumerate(graph["ordered_ids"], 1)
        },
    }
    return graph, mapping


def test_real_manifest_is_complete_and_acyclic() -> None:
    graph, mapping = graph_and_map()

    assert len(graph["phase_by_id"]) == 15
    assert len(graph["work_by_id"]) == 111
    assert len(graph["ordered_ids"]) == 127
    MODULE.validate_map(mapping, graph, complete=True)


def test_static_model_or_provider_routing_key_fails_closed() -> None:
    data = MODULE.load_manifest(MANIFEST)
    data["phases"][0]["work"][0]["model"] = "future-model-name"

    with pytest.raises(MODULE.ProgramError, match="routing key"):
        MODULE.index_program(data)


def test_work_dependency_cycle_fails_closed() -> None:
    data = MODULE.load_manifest(MANIFEST)
    data = copy.deepcopy(data)
    first = data["phases"][0]["work"][0]
    second = data["phases"][0]["work"][1]
    first["depends_on"] = [second["id"]]
    second["depends_on"] = [first["id"]]

    with pytest.raises(MODULE.ProgramError, match="dependency cycle"):
        MODULE.index_program(data)


def test_issue_bodies_are_complete_and_stably_marked() -> None:
    graph, mapping = graph_and_map()

    root = MODULE.body_for("PSP-ROOT", graph, mapping)
    phase = MODULE.body_for("PSP-P00", graph, mapping)
    dependent_phase = MODULE.body_for("PSP-P01", graph, mapping)
    work = MODULE.body_for("PSP-P02-W08", graph, mapping)

    assert MODULE.marker("PSP-ROOT") in root
    assert MODULE.marker("PSP-P00") in phase
    assert MODULE.marker("PSP-P01") in dependent_phase
    assert "PSP-P00" not in dependent_phase or "issues/2" in dependent_phase
    assert MODULE.marker("PSP-P02-W08") in work
    assert "## Acceptance condition" in work
    assert "## Executable completion predicate" in work
    assert "measurement, inference, implication, and prominence" in work
    assert "model/provider selected dynamically" in work


def test_every_projected_issue_fits_github_limits() -> None:
    graph, mapping = graph_and_map()

    for object_id in graph["ordered_ids"]:
        title = MODULE.title_for(object_id, graph)
        body = MODULE.body_for(object_id, graph, mapping)

        assert len(title) <= 256, object_id
        assert len(body) <= 65_536, object_id
        assert body.count(MODULE.marker(object_id)) == 1, object_id
        assert len(MODULE.labels_for(object_id, graph)) == len(set(MODULE.labels_for(object_id, graph)))


def test_every_leaf_has_an_executable_non_provider_pinned_predicate() -> None:
    graph, _mapping = graph_and_map()

    for work_id, packet in graph["work_by_id"].items():
        assert packet["predicate"] == f"python3 scripts/positioning-program.py --verify-work {work_id}"
        assert packet["acceptance"].strip()


def test_packet_seed_is_provider_neutral_and_not_a_lease() -> None:
    graph, mapping = graph_and_map()

    seed = MODULE.packet_seed("PSP-P01-W01", graph, mapping)

    assert seed["schema_version"] == MODULE.SEED_SCHEMA
    assert seed["not_a_lease"] is True
    assert seed["execution_requirements"]["reasoning_class"] == "routine"
    assert "model" not in json.dumps(seed).lower()
    assert seed["receipt_target"] == "github:organvm/limen:issue:11"


def test_work_receipt_is_bound_to_current_acceptance_and_non_circular_predicate() -> None:
    graph, _mapping = graph_and_map()
    work_id = "PSP-P02-W08"
    packet = graph["work_by_id"][work_id]
    receipt = {
        "schema_version": MODULE.RECEIPT_SCHEMA,
        "work_id": work_id,
        "acceptance_sha256": MODULE.acceptance_digest(packet),
        "outcome": "succeeded",
        "authority": {"kind": "broker", "run_id": "run-1", "lease_id": "lease-1", "executor": "copilot"},
        "observed_heads": {"organvm/limen": "a" * 40},
        "changed_paths": [],
        "predicate": {
            "command": "python3 scripts/check-claim-adjudication.py",
            "exit_code": 0,
            "output_sha256": "b" * 64,
            "observed_at": "2026-08-09T12:00:00Z",
        },
        "evidence_urls": ["https://github.com/organvm/limen/issues/1"],
        "rollback": {"invoked": False, "state": "not needed"},
    }

    assert MODULE.validate_work_receipt(receipt, work_id, graph) == receipt

    stale = copy.deepcopy(receipt)
    stale["acceptance_sha256"] = "0" * 64
    with pytest.raises(MODULE.ProgramError, match="acceptance_sha256"):
        MODULE.validate_work_receipt(stale, work_id, graph)

    circular = copy.deepcopy(receipt)
    circular["predicate"]["command"] = packet["predicate"]
    with pytest.raises(MODULE.ProgramError, match="cannot call the receipt verifier"):
        MODULE.validate_work_receipt(circular, work_id, graph)


def test_ready_work_requires_closed_phase_and_work_dependencies(monkeypatch) -> None:
    graph, mapping = graph_and_map()
    remote = {
        object_id: {
            "number": row["number"],
            "html_url": row["url"],
            "state": "open",
            "body": MODULE.marker(object_id),
            "title": MODULE.title_for(object_id, graph),
            "labels": [],
        }
        for object_id, row in mapping["issues"].items()
    }
    monkeypatch.setattr(MODULE, "fetch_program_issues", lambda _graph: remote)
    monkeypatch.setattr(
        MODULE,
        "fetch_work_receipt",
        lambda work_id, _graph, _mapping: ({"work_id": work_id}, f"https://example.test/receipts/{work_id}"),
    )

    initial = {row["id"] for row in MODULE.ready_work(graph, mapping)}
    assert initial == {"PSP-P00-W01"}

    remote["PSP-P00-W01"]["state"] = "closed"
    after_first = {row["id"] for row in MODULE.ready_work(graph, mapping)}
    assert {"PSP-P00-W02", "PSP-P00-W04"}.issubset(after_first)
    assert "PSP-P01-W01" not in after_first


def test_closed_phase_cannot_hide_open_children() -> None:
    graph, mapping = graph_and_map()
    remote = {object_id: {"state": "open"} for object_id in graph["ordered_ids"]}
    remote["PSP-P00"]["state"] = "closed"

    with pytest.raises(MODULE.ProgramError, match="closed before child issues"):
        MODULE.closure_integrity(graph, mapping, remote)


def test_map_rejects_duplicate_issue_numbers() -> None:
    graph, mapping = graph_and_map()
    mapping["issues"]["PSP-P00"]["number"] = mapping["issues"]["PSP-ROOT"]["number"]

    with pytest.raises(MODULE.ProgramError, match="reuses issue"):
        MODULE.validate_map(mapping, graph, complete=True)


def test_index_render_is_deterministic(tmp_path: Path) -> None:
    graph, mapping = graph_and_map()
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"

    assert MODULE.render_index(graph, mapping, first) == MODULE.render_index(graph, mapping, second)
    assert first.read_bytes() == second.read_bytes()
    assert "Atomic work packets: **111**" in first.read_text()
