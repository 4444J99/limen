from __future__ import annotations

import copy
import importlib.machinery
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

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
        "milestone": {
            "number": 1,
            "title": graph["program"]["issue_projection"]["milestone"],
            "url": "https://example.test/milestone/1",
        },
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


def test_every_phase_uses_its_exact_manifest_owned_proof_predicate() -> None:
    graph, _mapping = graph_and_map()

    assert len(graph["phase_by_id"]) == 15
    for phase_id in graph["phase_by_id"]:
        assert MODULE.phase_proof_command(phase_id, graph) == (
            f"python3 scripts/positioning-program.py --phase-proof {phase_id}"
        )


def test_phase_exit_predicate_rejects_missing_or_circular_contract() -> None:
    missing = copy.deepcopy(MODULE.load_manifest(MANIFEST))
    del missing["phases"][0]["exit_predicate"]
    with pytest.raises(MODULE.ProgramError, match="exit_predicate"):
        MODULE.index_program(missing)

    circular = copy.deepcopy(MODULE.load_manifest(MANIFEST))
    circular["phases"][0]["exit_predicate"] = "python3 scripts/positioning-program.py --verify-phase PSP-P00"
    with pytest.raises(MODULE.ProgramError, match="exit_predicate"):
        MODULE.index_program(circular)


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
    assert "Assigned model: `gpt-5.6-sol`" in work
    assert "Assigned effort: `max`" in work
    assert "**Execution chunk:** `PSP-C02`" in work
    assert "`PSP-C00` — Land the program control plane" in root


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


def test_every_object_has_an_explicit_model_and_effort_assignment() -> None:
    graph, _mapping = graph_and_map()
    assignments = {object_id: MODULE.model_assignment_for(object_id, graph) for object_id in graph["ordered_ids"]}

    assert len(assignments) == 127
    assert assignments["PSP-ROOT"]["slug"] == "gpt-5.6-sol"
    assert assignments["PSP-ROOT"]["effort"] == "ultra"
    assert assignments["PSP-P01"]["slug"] == "gpt-5.6-terra"
    assert assignments["PSP-P01"]["effort"] == "high"
    assert assignments["PSP-P00-W07"]["effort"] == "max"
    assert assignments["PSP-P02-W08"]["effort"] == "max"
    assert assignments["PSP-P14-W09"]["effort"] == "ultra"
    assert all(row["effort"] in MODULE.EFFORTS for row in assignments.values())


def test_execution_chunks_cover_every_leaf_once_and_respect_the_crossover() -> None:
    graph, _mapping = graph_and_map()

    assert len(graph["chunks"]) == 13
    assert len(graph["work_chunk"]) == 111
    assert set(graph["work_chunk"]) == set(graph["work_by_id"])
    assert graph["work_chunk"]["PSP-P10-W07"] == "PSP-C09"
    assert graph["work_chunk"]["PSP-P10-W08"] == "PSP-C10"
    assert graph["work_chunk"]["PSP-P12-W01"] == "PSP-C10"
    assert "PSP-P10" not in graph["phase_by_id"]["PSP-P12"]["depends_on"]
    assert set(graph["chunk_by_id"]["PSP-C09"]["depends_on"]) == {"PSP-C05", "PSP-C08"}


def test_execution_chunk_cycle_fails_closed() -> None:
    data = copy.deepcopy(MODULE.load_manifest(MANIFEST))
    data["execution_chunks"]["chunks"][0]["depends_on"] = ["PSP-C12"]

    with pytest.raises(MODULE.ProgramError, match="execution chunk dependency cycle"):
        MODULE.index_program(data)


def test_live_catalog_validator_checks_every_assigned_pair(monkeypatch) -> None:
    graph, _mapping = graph_and_map()
    catalog: dict[str, set[str]] = {}
    for object_id in graph["ordered_ids"]:
        assignment = MODULE.model_assignment_for(object_id, graph)
        catalog.setdefault(assignment["slug"], set()).add(assignment["effort"])
    for chunk in graph["chunks"]:
        assignment = MODULE.chunk_assignment_for(chunk["id"], graph)
        catalog.setdefault(assignment["slug"], set()).add(assignment["effort"])
    payload = {
        "models": [
            {"slug": slug, "supported_reasoning_levels": [{"effort": effort} for effort in sorted(efforts)]}
            for slug, efforts in sorted(catalog.items())
        ]
    }
    monkeypatch.setattr(
        MODULE.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr=""),
    )

    result = MODULE.verify_model_assignments(graph)

    assert result["status"] == "ok"
    assert result["objects"] == 127
    assert result["execution_chunks"] == 13
    assert sum(result["assignments"].values()) == 127
    assert sum(result["chunk_assignments"].values()) == 13


def test_packet_seed_carries_the_human_model_override_and_is_not_a_lease() -> None:
    graph, mapping = graph_and_map()

    seed = MODULE.packet_seed("PSP-P01-W01", graph, mapping)

    assert seed["schema_version"] == MODULE.SEED_SCHEMA
    assert seed["not_a_lease"] is True
    assert seed["execution_requirements"]["reasoning_class"] == "routine"
    assert seed["execution_requirements"]["model_override"]["slug"] == "gpt-5.6-luna"
    assert seed["execution_requirements"]["model_override"]["effort"] == "medium"
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

    extra_repository = copy.deepcopy(receipt)
    extra_repository["observed_heads"]["other/repository"] = "c" * 40
    with pytest.raises(MODULE.ProgramError, match="exactly the packet target repository"):
        MODULE.validate_work_receipt(extra_repository, work_id, graph)


def test_phase_exit_gate_is_explicit_executable_and_not_circular() -> None:
    graph, _mapping = graph_and_map()
    phase_id = "PSP-P00"
    phase = graph["phase_by_id"][phase_id]
    receipt = {
        "schema_version": MODULE.PHASE_RECEIPT_SCHEMA,
        "phase_id": phase_id,
        "status": "pass",
        "exit_gate_sha256": MODULE.hashlib.sha256(phase["exit_gate"].encode()).hexdigest(),
        "observed_heads": {graph["program"]["repository"]: "a" * 40},
        "child_receipts_sha256": "b" * 64,
        "remote_state_sha256": "c" * 64,
        "parity_sha256": "d" * 64,
        "predicate": {
            "command": "python3 scripts/positioning-program.py --phase-proof PSP-P00",
            "exit_code": 0,
            "output_sha256": "d" * 64,
            "observed_at": "2026-08-09T12:00:00Z",
        },
        "evidence_urls": ["https://example.test/phase-receipt/PSP-P00"],
    }

    assert (
        MODULE.validate_phase_receipt(
            receipt,
            phase_id,
            graph,
            child_receipt_digest="b" * 64,
            remote_state_digest="c" * 64,
            parity_digest="d" * 64,
        )
        == receipt
    )
    assert "--phase-proof PSP-P00" in MODULE.body_for(phase_id, graph, graph_and_map()[1])

    circular = copy.deepcopy(receipt)
    circular["predicate"]["command"] = f"python3 scripts/positioning-program.py --verify-phase {phase_id}"
    with pytest.raises(MODULE.ProgramError, match="manifest proof contract"):
        MODULE.validate_phase_receipt(
            circular,
            phase_id,
            graph,
            child_receipt_digest="b" * 64,
            remote_state_digest="c" * 64,
            parity_digest="d" * 64,
        )

    stale_state = copy.deepcopy(receipt)
    stale_state["remote_state_sha256"] = "e" * 64
    with pytest.raises(MODULE.ProgramError, match="remote state digest"):
        MODULE.validate_phase_receipt(
            stale_state,
            phase_id,
            graph,
            child_receipt_digest="b" * 64,
            remote_state_digest="c" * 64,
            parity_digest="d" * 64,
        )


def test_phase_binding_digest_is_local_and_stable(monkeypatch) -> None:
    graph, mapping = graph_and_map()
    remote = {
        object_id: {
            "number": row["number"],
            "state": "closed",
            "body": MODULE.marker(object_id),
            "labels": [],
            "milestone": {"number": 1},
            "updated_at": "2026-08-09T12:00:00Z",
        }
        for object_id, row in mapping["issues"].items()
    }
    original = MODULE._phase_remote_state_digest("PSP-P00", graph, mapping, remote)
    original_parity = MODULE._phase_parity_digest("PSP-P00", graph, mapping, remote)
    remote["PSP-P00"]["state"] = "open"
    assert MODULE._phase_remote_state_digest("PSP-P00", graph, mapping, remote) == original
    assert MODULE._phase_parity_digest("PSP-P00", graph, mapping, remote) == original_parity

    remote["PSP-P00"]["state"] = "closed"
    remote["PSP-P01"]["state"] = "open"
    remote["PSP-P01"]["updated_at"] = "2026-08-10T12:00:00Z"
    assert MODULE._phase_remote_state_digest("PSP-P00", graph, mapping, remote) == original
    assert MODULE._phase_parity_digest("PSP-P00", graph, mapping, remote) == original_parity

    remote["PSP-P00-W01"]["state"] = "open"
    assert MODULE._phase_remote_state_digest("PSP-P00", graph, mapping, remote) != original
    assert MODULE._phase_parity_digest("PSP-P00", graph, mapping, remote) == original_parity

    receipts = {
        packet["id"]: {"receipt": packet["id"], "revision": 1} for packet in graph["phase_by_id"]["PSP-P00"]["work"]
    }
    monkeypatch.setattr(
        MODULE,
        "fetch_work_receipt",
        lambda work_id, _graph, _mapping: (receipts[work_id], f"https://example.test/{work_id}"),
    )
    first_receipts = MODULE._phase_child_receipt_digest("PSP-P00", graph, mapping)
    receipts["PSP-P00-W01"]["revision"] = 2
    assert MODULE._phase_child_receipt_digest("PSP-P00", graph, mapping) != first_receipts


def _phase_remote_snapshot(graph, mapping, phase_id: str) -> dict[str, dict[str, object]]:
    phase = graph["phase_by_id"][phase_id]
    object_ids = [phase_id, *(packet["id"] for packet in phase["work"])]
    return {
        object_id: {
            "number": mapping["issues"][object_id]["number"],
            "html_url": mapping["issues"][object_id]["url"],
            "state": "open" if object_id == phase_id else "closed",
            "title": MODULE.title_for(object_id, graph),
            "body": MODULE.body_for(object_id, graph, mapping),
            "labels": [{"name": label} for label in MODULE.labels_for(object_id, graph)],
            "milestone": {"number": mapping["milestone"]["number"]},
        }
        for object_id in object_ids
    }


def test_phase_proof_is_receipt_independent_and_checks_children_and_projection(monkeypatch) -> None:
    graph, mapping = graph_and_map()
    remote = _phase_remote_snapshot(graph, mapping, "PSP-P00")
    monkeypatch.setattr(MODULE, "fetch_program_issues", lambda _graph: remote)
    monkeypatch.setattr(
        MODULE,
        "fetch_phase_receipt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(MODULE.ProgramError("must not fetch phase receipt")),
    )
    monkeypatch.setattr(
        MODULE,
        "fetch_work_receipt",
        lambda work_id, _graph, _mapping: ({"work_id": work_id}, f"https://example.test/{work_id}"),
    )

    result = MODULE.phase_proof("PSP-P00", graph, mapping)

    assert result["status"] == "pass"
    assert result["phase_id"] == "PSP-P00"
    assert set(result["child_receipt_evidence"]) == {packet["id"] for packet in graph["phase_by_id"]["PSP-P00"]["work"]}

    remote["PSP-P00-W01"]["state"] = "open"
    with pytest.raises(MODULE.ProgramError, match="PSP-P00-W01 is not closed"):
        MODULE.phase_proof("PSP-P00", graph, mapping)

    remote["PSP-P00-W01"]["state"] = "closed"
    remote["PSP-P00"]["title"] = "drifted title"
    with pytest.raises(MODULE.ProgramError, match="title drift"):
        MODULE.phase_proof("PSP-P00", graph, mapping)

    remote["PSP-P00"]["title"] = MODULE.title_for("PSP-P00", graph)
    remote["PSP-P00-W01"]["body"] = "drifted body"
    with pytest.raises(MODULE.ProgramError, match="body drift"):
        MODULE.phase_proof("PSP-P00", graph, mapping)


def test_phase_proof_recovers_only_missing_phase_objects(monkeypatch) -> None:
    graph, mapping = graph_and_map()
    remote = _phase_remote_snapshot(graph, mapping, "PSP-P00")
    recovered = remote.pop("PSP-P00-W01")
    monkeypatch.setattr(MODULE, "fetch_program_issues", lambda _graph: remote)
    requested: list[str] = []

    def recover(repository, path, *, allow_failure=False):
        del repository, allow_failure
        object_id = path.rsplit("/", 1)[-1]
        requested.append(object_id)
        if object_id != str(mapping["issues"]["PSP-P00-W01"]["number"]):
            raise AssertionError(f"unrelated recovery requested: {object_id}")
        return recovered

    monkeypatch.setattr(MODULE, "_api", recover)
    monkeypatch.setattr(
        MODULE,
        "fetch_work_receipt",
        lambda work_id, _graph, _mapping: ({"work_id": work_id}, f"https://example.test/{work_id}"),
    )

    result = MODULE.phase_proof("PSP-P00", graph, mapping)

    assert result["status"] == "pass"
    assert requested == [str(mapping["issues"]["PSP-P00-W01"]["number"])]


def test_phase_proof_rejects_stale_child_receipt(monkeypatch) -> None:
    graph, mapping = graph_and_map()
    remote = _phase_remote_snapshot(graph, mapping, "PSP-P00")
    monkeypatch.setattr(MODULE, "fetch_program_issues", lambda _graph: remote)
    monkeypatch.setattr(
        MODULE,
        "fetch_work_receipt",
        lambda work_id, _graph, _mapping: (
            (_ for _ in ()).throw(MODULE.ProgramError(f"{work_id} stale receipt"))
            if work_id == "PSP-P00-W01"
            else ({"work_id": work_id}, f"https://example.test/{work_id}")
        ),
    )

    with pytest.raises(MODULE.ProgramError, match="stale receipt"):
        MODULE.phase_proof("PSP-P00", graph, mapping)


def test_phase_proof_rejects_stale_routing_labels_and_phase_local_orphans(monkeypatch) -> None:
    graph, mapping = graph_and_map()
    remote = _phase_remote_snapshot(graph, mapping, "PSP-P00")
    monkeypatch.setattr(MODULE, "fetch_program_issues", lambda _graph: remote)
    monkeypatch.setattr(
        MODULE,
        "fetch_work_receipt",
        lambda work_id, _graph, _mapping: ({"work_id": work_id}, f"https://example.test/{work_id}"),
    )

    remote["PSP-P00-W01"]["labels"].append({"name": "model:stale"})
    with pytest.raises(MODULE.ProgramError, match="routing label drift"):
        MODULE.phase_proof("PSP-P00", graph, mapping)

    remote["PSP-P00-W01"]["labels"] = [{"name": label} for label in MODULE.labels_for("PSP-P00-W01", graph)]
    remote["PSP-P00-W99"] = {
        "number": 999,
        "title": "orphan",
        "body": MODULE.marker("PSP-P00-W99"),
        "labels": [],
        "milestone": {"number": mapping["milestone"]["number"]},
        "state": "open",
    }
    with pytest.raises(MODULE.ProgramError, match="orphan phase-local markers"):
        MODULE.phase_proof("PSP-P00", graph, mapping)


def test_phase_proof_cli_mode_is_read_only(monkeypatch, capsys) -> None:
    graph, mapping = graph_and_map()
    manifest = MODULE.load_manifest(MANIFEST)
    remote = _phase_remote_snapshot(graph, mapping, "PSP-P00")
    monkeypatch.setattr(MODULE, "load_manifest", lambda _path: manifest)
    monkeypatch.setattr(MODULE, "load_map", lambda _path: mapping)
    monkeypatch.setattr(MODULE, "fetch_program_issues", lambda _graph: remote)
    monkeypatch.setattr(
        MODULE,
        "fetch_work_receipt",
        lambda work_id, _graph, _mapping: ({"work_id": work_id}, f"https://example.test/{work_id}"),
    )

    assert MODULE.main(["--phase-proof", "PSP-P00"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "pass"
    assert output["phase_id"] == "PSP-P00"


def test_phase_receipt_template_is_read_only_cli_output(monkeypatch, capsys) -> None:
    graph, mapping = graph_and_map()
    manifest = MODULE.load_manifest(MANIFEST)
    remote = {
        object_id: {
            "number": row["number"],
            "html_url": row["url"],
            "state": "closed",
            "body": MODULE.marker(object_id),
            "labels": [],
            "milestone": {"number": 1},
        }
        for object_id, row in mapping["issues"].items()
    }
    monkeypatch.setattr(MODULE, "load_manifest", lambda _path: manifest)
    monkeypatch.setattr(MODULE, "load_map", lambda _path: mapping)
    monkeypatch.setattr(MODULE, "fetch_program_issues", lambda _graph: remote)
    monkeypatch.setattr(
        MODULE,
        "fetch_work_receipt",
        lambda work_id, _graph, _mapping: ({"work_id": work_id, "revision": 1}, f"https://example.test/{work_id}"),
    )

    assert MODULE.main(["--phase-receipt-template", "PSP-P00"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["schema_version"] == MODULE.PHASE_RECEIPT_SCHEMA
    assert output["phase_id"] == "PSP-P00"
    assert output["status"] == "pass"
    assert output["predicate"]["command"] == "python3 scripts/positioning-program.py --phase-proof PSP-P00"
    assert output["observed_heads"][graph["program"]["repository"]].startswith("REPLACE_WITH_")
    assert output["evidence_urls"] == [mapping["issues"]["PSP-P00"]["url"]]
    output["observed_heads"][graph["program"]["repository"]] = "a" * 40
    output["predicate"]["output_sha256"] = "b" * 64
    output["predicate"]["observed_at"] = "2026-08-09T12:00:00Z"
    bindings = MODULE._phase_binding_values("PSP-P00", graph, mapping, remote)
    assert (
        MODULE.validate_phase_receipt(
            output,
            "PSP-P00",
            graph,
            child_receipt_digest=bindings["child_receipt_digest"],
            remote_state_digest=bindings["remote_state_digest"],
            parity_digest=bindings["parity_digest"],
        )
        == output
    )


def test_omega_pass_schema_requires_pass_number_and_distinct_observation() -> None:
    digest = "e" * 64
    first = {
        "schema_version": MODULE.OMEGA_PASS_SCHEMA,
        "status": "pass",
        "pass": 1,
        "state_digest": digest,
        "observed_at": "2026-08-09T12:00:00Z",
    }
    second = copy.deepcopy(first)
    second["pass"] = 2
    second["observed_at"] = "2026-08-09T12:01:00Z"

    assert MODULE.validate_omega_pass(first, 1, digest) == first
    assert MODULE.validate_omega_pass(second, 2, digest) == second

    wrong_status = copy.deepcopy(first)
    wrong_status["status"] = "succeeded"
    with pytest.raises(MODULE.ProgramError, match="status must be pass"):
        MODULE.validate_omega_pass(wrong_status, 1, digest)


def test_omega_digest_covers_remote_completion_facts() -> None:
    graph, mapping = graph_and_map()
    remote = {
        object_id: {"state": "closed", "body": MODULE.marker(object_id), "labels": []}
        for object_id in graph["ordered_ids"]
    }
    first = MODULE._state_digest(graph, mapping, remote)
    remote["PSP-P00"]["labels"] = [{"name": "changed"}]
    second = MODULE._state_digest(graph, mapping, remote)

    assert first != second


def test_terminal_omega_leaf_phase_and_root_can_remain_open_for_readiness(monkeypatch) -> None:
    graph, mapping = graph_and_map()
    remote = {
        object_id: {"state": "closed", "body": MODULE.marker(object_id), "labels": []}
        for object_id in graph["ordered_ids"]
    }
    remote["PSP-ROOT"]["state"] = "open"
    remote["PSP-P14"]["state"] = "open"
    remote["PSP-P14-W09"]["state"] = "open"
    monkeypatch.setattr(MODULE, "remote_parity", lambda _graph, _mapping: {"ok": True})
    monkeypatch.setattr(MODULE, "fetch_program_issues", lambda _graph: remote)
    monkeypatch.setattr(
        MODULE,
        "closure_integrity",
        lambda _graph, _mapping, _remote, **_kwargs: {
            work_id: f"https://example.test/receipts/{work_id}"
            for work_id in graph["work_by_id"]
            if work_id != "PSP-P14-W09"
        },
    )
    monkeypatch.setattr(
        MODULE,
        "fetch_work_receipt",
        lambda work_id, _graph, _mapping: ({"work_id": work_id}, f"https://example.test/receipts/{work_id}"),
    )
    monkeypatch.setattr(
        MODULE,
        "fetch_phase_receipt",
        lambda phase_id, _graph, _mapping, **_kwargs: (
            (_ for _ in ()).throw(MODULE.ProgramError("missing terminal phase receipt"))
            if phase_id == "PSP-P14"
            else ({"phase_id": phase_id, "status": "pass"}, "https://example.test/phase")
        ),
    )

    result = MODULE.omega(graph, mapping, require_two_pass=False, allow_open_terminal=True)

    assert result["status"] == "pass"
    assert {"PSP-ROOT", "PSP-P14", "PSP-P14-W09"}.isdisjoint(result["open"])
    assert "PSP-P14-W09" in MODULE.terminal_omega_work_ids(graph)

    remote["PSP-P13"]["state"] = "open"
    with pytest.raises(MODULE.ProgramError, match="open program objects"):
        MODULE.omega(graph, mapping, require_two_pass=False, allow_open_terminal=True)

    remote["PSP-P13"]["state"] = "closed"
    with pytest.raises(MODULE.ProgramError, match="open program objects"):
        MODULE.omega(graph, mapping, require_two_pass=False)


def test_closed_phase_requires_a_valid_exit_gate_receipt(monkeypatch) -> None:
    graph, mapping = graph_and_map()
    remote = {object_id: {"state": "open"} for object_id in graph["ordered_ids"]}
    phase_id = "PSP-P00"
    remote[phase_id]["state"] = "closed"
    for packet in graph["phase_by_id"][phase_id]["work"]:
        remote[packet["id"]]["state"] = "closed"
    monkeypatch.setattr(
        MODULE,
        "fetch_work_receipt",
        lambda work_id, _graph, _mapping: ({"work_id": work_id}, f"https://example.test/{work_id}"),
    )
    monkeypatch.setattr(
        MODULE,
        "fetch_phase_receipt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(MODULE.ProgramError("missing phase exit-gate receipt")),
    )

    with pytest.raises(MODULE.ProgramError, match="missing phase exit-gate receipt"):
        MODULE.closure_integrity(graph, mapping, remote)


def test_normal_closure_requires_terminal_receipts_without_proof_exclusions(monkeypatch) -> None:
    graph, mapping = graph_and_map()
    remote = {object_id: {"state": "open"} for object_id in graph["ordered_ids"]}
    remote["PSP-P14"]["state"] = "closed"
    for packet in graph["phase_by_id"]["PSP-P14"]["work"]:
        remote[packet["id"]]["state"] = "closed"
    monkeypatch.setattr(
        MODULE,
        "fetch_work_receipt",
        lambda work_id, _graph, _mapping: ({"work_id": work_id}, f"https://example.test/{work_id}"),
    )
    monkeypatch.setattr(
        MODULE,
        "fetch_phase_receipt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(MODULE.ProgramError("missing terminal phase receipt")),
    )

    with pytest.raises(MODULE.ProgramError, match="missing terminal phase receipt"):
        MODULE.closure_integrity(graph, mapping, remote)


def test_multi_repository_receipt_requires_resolved_concrete_heads() -> None:
    graph, _mapping = graph_and_map()
    work_id = "PSP-P07-W05"
    packet = graph["work_by_id"][work_id]
    receipt = {
        "schema_version": MODULE.RECEIPT_SCHEMA,
        "work_id": work_id,
        "acceptance_sha256": MODULE.acceptance_digest(packet),
        "outcome": "succeeded",
        "authority": {"kind": "broker", "run_id": "run-1", "lease_id": "lease-1", "executor": "codex"},
        "resolved_repositories": ["organvm/alpha", "organvm/beta"],
        "observed_heads": {"organvm/alpha": "a" * 40, "organvm/beta": "b" * 40},
        "changed_paths": [],
        "predicate": {
            "command": "python3 scripts/check-positioning-gate.py",
            "exit_code": 0,
            "output_sha256": "c" * 64,
            "observed_at": "2026-08-09T12:00:00Z",
        },
        "evidence_urls": ["https://example.test/receipt"],
        "rollback": {"invoked": False, "state": "not needed"},
    }

    assert MODULE.validate_work_receipt(receipt, work_id, graph) == receipt

    missing_resolution = copy.deepcopy(receipt)
    del missing_resolution["resolved_repositories"]
    with pytest.raises(MODULE.ProgramError, match="resolved_repositories"):
        MODULE.validate_work_receipt(missing_resolution, work_id, graph)

    mismatched_heads = copy.deepcopy(receipt)
    mismatched_heads["observed_heads"]["organvm/extra"] = "d" * 40
    with pytest.raises(MODULE.ProgramError, match="every resolved repository"):
        MODULE.validate_work_receipt(mismatched_heads, work_id, graph)


def test_omega_pass_cli_contract_and_record_schema(capsys) -> None:
    assert MODULE.main(["--check", "--omega-pass", "1"]) == 2
    assert "valid only with --omega" in capsys.readouterr().err

    record = MODULE.omega_pass_record({"ok": True, "state_digest": "f" * 64}, 2)
    assert record["schema_version"] == MODULE.OMEGA_PASS_SCHEMA
    assert record["status"] == "pass"
    assert record["pass"] == 2
    assert MODULE.validate_omega_pass(record, 2, "f" * 64) == record


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


def test_p12_can_start_before_p10_closes_and_unlock_p10_w08(monkeypatch) -> None:
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
    for phase in graph["phases"]:
        if phase["id"] in {"PSP-P10", "PSP-P12", "PSP-P13", "PSP-P14"}:
            continue
        remote[phase["id"]]["state"] = "closed"
        for packet in phase["work"]:
            remote[packet["id"]]["state"] = "closed"
    for index in range(1, 8):
        remote[f"PSP-P10-W{index:02d}"]["state"] = "closed"
    monkeypatch.setattr(MODULE, "fetch_program_issues", lambda _graph: remote)
    monkeypatch.setattr(
        MODULE,
        "fetch_work_receipt",
        lambda work_id, _graph, _mapping: ({"work_id": work_id}, f"https://example.test/receipts/{work_id}"),
    )
    monkeypatch.setattr(
        MODULE,
        "fetch_phase_receipt",
        lambda phase_id, _graph, _mapping, **_kwargs: (
            {"phase_id": phase_id, "status": "pass"},
            "https://example.test/phase",
        ),
    )

    ready = {row["id"] for row in MODULE.ready_work(graph, mapping)}

    assert "PSP-P12-W01" in ready
    assert "PSP-P10-W08" not in ready


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


def test_complete_map_rejects_wrong_milestone() -> None:
    graph, mapping = graph_and_map()
    mapping["milestone"]["title"] = "Wrong program"

    with pytest.raises(MODULE.ProgramError, match="map milestone"):
        MODULE.validate_map(mapping, graph, complete=True)


def test_mapped_issue_recovers_after_label_or_marker_drift(monkeypatch) -> None:
    graph, mapping = graph_and_map()
    missing_id = "PSP-P00-W01"
    remote = {
        object_id: {"number": row["number"], "body": MODULE.marker(object_id)}
        for object_id, row in mapping["issues"].items()
        if object_id != missing_id
    }
    recovered_row = {
        "number": mapping["issues"][missing_id]["number"],
        "html_url": mapping["issues"][missing_id]["url"],
        "body": "body and label were edited",
    }
    monkeypatch.setattr(MODULE, "_api", lambda *_args, **_kwargs: recovered_row)

    recovered = MODULE.recover_mapped_issues(graph, mapping, remote)

    assert recovered[missing_id] == recovered_row


def test_remote_parity_includes_milestone_assignment(monkeypatch) -> None:
    graph, mapping = graph_and_map()
    remote = {
        object_id: {
            "number": mapping["issues"][object_id]["number"],
            "title": MODULE.title_for(object_id, graph),
            "body": MODULE.body_for(object_id, graph, mapping),
            "labels": [{"name": label} for label in MODULE.labels_for(object_id, graph)],
            "milestone": {"number": mapping["milestone"]["number"]},
        }
        for object_id in graph["ordered_ids"]
    }
    monkeypatch.setattr(MODULE, "fetch_program_issues", lambda _graph: remote)

    assert MODULE.remote_parity(graph, mapping)["ok"] is True

    remote["PSP-ROOT"]["milestone"] = None
    with pytest.raises(MODULE.ProgramError, match="milestone drift"):
        MODULE.remote_parity(graph, mapping)


def test_index_render_is_deterministic(tmp_path: Path) -> None:
    graph, mapping = graph_and_map()
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"

    assert MODULE.render_index(graph, mapping, first) == MODULE.render_index(graph, mapping, second)
    assert first.read_bytes() == second.read_bytes()
    assert "Atomic work packets: **111**" in first.read_text()
    assert "Root model / effort: **`gpt-5.6-sol` / `ultra`**" in first.read_text()
    assert "`PSP-C10`" in first.read_text()


def test_chunk_prompt_and_render_are_deterministic(tmp_path: Path) -> None:
    graph, mapping = graph_and_map()
    bootstrap = MODULE.chunk_packet("PSP-C00", graph, mapping)
    packet = MODULE.chunk_packet("PSP-C10", graph, mapping)
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"

    assert packet["conductor_assignment"]["slug"] == "gpt-5.6-sol"
    assert packet["conductor_assignment"]["effort"] == "max"
    assert packet["work"][-1]["id"] == "PSP-P10-W08"
    assert "Continue draft PR #2156" in bootstrap["launch_prompt"]
    assert "Start from current `main` only after C00 is closed" in packet["launch_prompt"]
    assert "Continue from relay at <absolute-pointer-path>" in packet["launch_prompt"]
    assert MODULE.render_execution_chunks(graph, mapping, first) == MODULE.render_execution_chunks(
        graph, mapping, second
    )
    assert first.read_bytes() == second.read_bytes()
    rendered = first.read_text()
    assert "C04 (proof/experience) and C05 (service delivery) may run in parallel" in rendered
    assert "former P10↔P12 phase-gating deadlock" in rendered
