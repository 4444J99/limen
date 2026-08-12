#!/usr/bin/env python3
"""Deterministic, non-closing control plane for PSP-P14 preflight.

The tool validates the P14 event/KPI and review contracts, executes only synthetic
incident/recovery/feedback fixtures, and reports live terminal evidence that is still
missing.  It never runs predecessor commands, calls GitHub, closes work, publishes,
deploys, or treats a synthetic result as a real-world outcome.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re
import runpy
import sys
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = ROOT / "institutio" / "positioning" / "p14" / "control-plane.json"
DEFAULT_LEDGER = ROOT / "institutio" / "positioning" / "p14" / "dependency-ledger.json"
DEFAULT_FIXTURE = ROOT / "cli" / "tests" / "fixtures" / "positioning-p14" / "synthetic-cycle.json"
DEFAULT_EVIDENCE = ROOT / "docs" / "receipts" / "positioning" / "p14" / "live-evidence.json"
PROGRAM_SCRIPT = ROOT / "scripts" / "positioning-program.py"

CONTROL_SCHEMA = "limen.positioning_p14_control_plane.v2"
LEDGER_SCHEMA = "limen.positioning_p14_dependency_ledger.v1"
FIXTURE_SCHEMA = "limen.positioning_p14_fixture.v1"
EVIDENCE_SCHEMA = "limen.positioning_p14_evidence.v1"
PAIR_SCHEMA = "limen.positioning_p14_omega_pair.v1"
OMEGA_PASS_SCHEMA = "limen.positioning_omega_pass.v1"
WORK_IDS = tuple(f"PSP-P14-W{number:02d}" for number in range(1, 10))
WORK_RE = re.compile(r"PSP-P14-W\d{2}\Z")
HEAD_RE = re.compile(r"[0-9a-f]{40}\Z")
DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
EVENT_RE = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\Z")
PREDECESSOR_CHUNK_IDS = tuple(f"PSP-C{number:02d}" for number in range(3, 12))
EXPECTED_DENY_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "client_name",
    "contact_name",
    "credential",
    "email",
    "operator_name",
    "phone",
    "price_amount",
    "private_evidence_body",
    "private_repository_name",
    "secret",
}
PROGRAM_RECEIPT_FIELDS = {
    "command",
    "exit_code",
    "output_sha256",
    "state_digest",
    "observed_head",
    "observed_at",
    "evidence_url",
}


class P14Error(RuntimeError):
    """Raised when a preflight contract or fixture fails closed."""


def _load_json(path: Path, *, missing: object | None = None) -> Any:
    if missing is not None and not path.exists():
        return missing
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise P14Error(f"cannot load JSON {path}: {exc}") from exc


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise P14Error(f"{label} must be an object")
    return value


def _list(value: object, label: str, *, nonempty: bool = False) -> list[Any]:
    if not isinstance(value, list) or (nonempty and not value):
        suffix = " a non-empty list" if nonempty else " a list"
        raise P14Error(f"{label} must be{suffix}")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise P14Error(f"{label} must be non-empty text")
    return value.strip()


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _rfc3339_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if "T" in value and parsed.tzinfo is not None else None


def _is_rfc3339(value: object) -> bool:
    return _rfc3339_datetime(value) is not None


def _is_url(value: object) -> bool:
    return isinstance(value, str) and value.startswith("https://") and " " not in value


def _meaningful(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _normalized_key(value: object) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(value))
    return re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()


def _privacy_violations(value: object, deny_keys: set[str], path: tuple[str, ...] = ()) -> list[str]:
    violations: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = _normalized_key(key)
            child_path = (*path, str(key))
            if normalized in deny_keys:
                violations.append(".".join(child_path))
            violations.extend(_privacy_violations(child, deny_keys, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(_privacy_violations(child, deny_keys, (*path, str(index))))
    return violations


def _program_graph_and_map() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    try:
        module = runpy.run_path(str(PROGRAM_SCRIPT))
        graph = module["index_program"](module["load_manifest"]())
        mapping = module["load_map"]()
        module["validate_map"](mapping, graph, complete=True)
    except Exception as exc:
        raise P14Error(f"cannot derive P14 dependency truth from the program registry: {exc}") from exc
    return graph, mapping, module


def _path_value(value: object, path: str) -> object:
    current = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _period_date(value: object) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _periods_are_consecutive(records: list[dict[str, Any]], cadence: str) -> bool:
    starts = [_period_date(record.get("period_start")) for record in records]
    if any(item is None for item in starts) or len(set(starts)) != len(starts):
        return False
    concrete = sorted(item for item in starts if item is not None)
    if cadence == "weekly":
        return all((right - left).days == 7 for left, right in zip(concrete, concrete[1:]))
    if cadence == "monthly":
        ordinals = [item.year * 12 + item.month for item in concrete]
        return all(right - left == 1 for left, right in zip(ordinals, ordinals[1:]))
    return False


def _topological_stages(stages: list[dict[str, Any]]) -> list[str]:
    dependencies: dict[str, set[str]] = {}
    for index, raw in enumerate(stages):
        stage = _mapping(raw, f"stages[{index}]")
        work_id = _text(stage.get("work_id"), f"stages[{index}].work_id")
        if not WORK_RE.fullmatch(work_id):
            raise P14Error(f"invalid P14 work id: {work_id}")
        if work_id in dependencies:
            raise P14Error(f"duplicate stage: {work_id}")
        depends_on = {
            _text(item, f"{work_id}.depends_on") for item in _list(stage.get("depends_on"), f"{work_id}.depends_on")
        }
        dependencies[work_id] = depends_on
    if set(dependencies) != set(WORK_IDS):
        raise P14Error(f"stages must cover exactly {list(WORK_IDS)}")
    unknown = {dep for deps in dependencies.values() for dep in deps if dep not in dependencies}
    if unknown:
        raise P14Error(f"stage dependencies are outside P14: {sorted(unknown)}")
    ordered: list[str] = []
    remaining = {key: set(value) for key, value in dependencies.items()}
    while remaining:
        ready = sorted(key for key, deps in remaining.items() if deps.issubset(ordered))
        if not ready:
            raise P14Error(f"stage dependency cycle: {sorted(remaining)}")
        for work_id in ready:
            ordered.append(work_id)
            remaining.pop(work_id)
    return ordered


def validate_dependency_ledger(value: object, contract: dict[str, Any]) -> dict[str, Any]:
    ledger = _mapping(value, "dependency ledger")
    if ledger.get("schema_version") != LEDGER_SCHEMA:
        raise P14Error(f"dependency ledger schema_version must be {LEDGER_SCHEMA}")
    if ledger.get("authoritative_registry") != "institutio/positioning/program.yaml":
        raise P14Error("dependency ledger must bind the canonical program registry")
    if ledger.get("program_repository") != "organvm/limen":
        raise P14Error("dependency ledger repository drift")
    if ledger.get("counts_as_closure") is not False:
        raise P14Error("dependency ledger preparation must not count as closure")
    if not _is_rfc3339(ledger.get("observed_at")):
        raise P14Error("dependency ledger observed_at must be RFC3339")

    graph, mapping, program = _program_graph_and_map()
    baseline = _mapping(ledger.get("closed_baseline"), "dependency ledger closed_baseline")
    if (
        baseline.get("chunk_id") != "PSP-C02"
        or baseline.get("phase_id") != "PSP-P02"
        or baseline.get("closure_state") != "closed"
        or not HEAD_RE.fullmatch(str(baseline.get("accepted_main_head") or ""))
        or baseline.get("issue") != "https://github.com/organvm/limen/issues/2172"
        or not _is_url(baseline.get("marked_receipt"))
    ):
        raise P14Error("dependency ledger closed P02 baseline is incomplete")

    phase_ownership = _mapping(ledger.get("phase_ownership"), "dependency ledger phase_ownership")
    expected_phase_ownership = {
        chunk_id: list(graph["chunk_by_id"][chunk_id]["phase_ids"]) for chunk_id in (*PREDECESSOR_CHUNK_IDS, "PSP-C12")
    }
    if phase_ownership != expected_phase_ownership:
        raise P14Error("dependency ledger phase ownership drift")

    raw_chunks = _list(ledger.get("predecessor_chunks"), "dependency ledger predecessor_chunks")
    if len(raw_chunks) != len(PREDECESSOR_CHUNK_IDS):
        raise P14Error(f"dependency ledger must contain {len(PREDECESSOR_CHUNK_IDS)} predecessor chunks")
    chunk_ids: list[str] = []
    for index, raw in enumerate(raw_chunks):
        row = _mapping(raw, f"predecessor_chunks[{index}]")
        chunk_id = _text(row.get("chunk_id"), f"predecessor_chunks[{index}].chunk_id")
        chunk_ids.append(chunk_id)
        if chunk_id not in PREDECESSOR_CHUNK_IDS:
            raise P14Error(f"unexpected predecessor chunk {chunk_id}")
        registry = graph["chunk_by_id"][chunk_id]
        if row.get("depends_on") != registry["depends_on"] or row.get("phase_ids") != registry["phase_ids"]:
            raise P14Error(f"{chunk_id} dependency or phase ownership drift")
        expected_conductor = {key: registry["conductor"][key] for key in ("slug", "effort")}
        if row.get("conductor") != expected_conductor:
            raise P14Error(f"{chunk_id} conductor assignment drift")
        expected_closure = "partial" if chunk_id == "PSP-C03" else "open"
        if row.get("closure_state") != expected_closure or row.get("counts_as_closure") is not False:
            raise P14Error(f"{chunk_id} closure truth drift")
        _text(row.get("preflight_state"), f"{chunk_id}.preflight_state")
        evidence = _list(row.get("evidence"), f"{chunk_id}.evidence", nonempty=True)
        targets: set[str] = set()
        for evidence_index, raw_evidence in enumerate(evidence):
            receipt = _mapping(raw_evidence, f"{chunk_id}.evidence[{evidence_index}]")
            target = _text(receipt.get("target"), f"{chunk_id}.evidence[{evidence_index}].target")
            if target in targets:
                raise P14Error(f"{chunk_id} has duplicate evidence target {target}")
            targets.add(target)
            pull_request = receipt.get("pull_request")
            if not isinstance(pull_request, int) or isinstance(pull_request, bool) or pull_request < 1:
                raise P14Error(f"{chunk_id} evidence pull_request must be a positive integer")
            if not HEAD_RE.fullmatch(str(receipt.get("head") or "")):
                raise P14Error(f"{chunk_id} evidence head must be an exact commit")
        frontier = _list(row.get("frontier_work"), f"{chunk_id}.frontier_work")
        if chunk_id == "PSP-C03":
            if len(frontier) != 1:
                raise P14Error("C03 must expose exactly the current W07 reader frontier")
            reader = _mapping(frontier[0], "C03 frontier work")
            assignment = program["model_assignment_for"]("PSP-P03-W07", graph)
            expected_assignment = {key: assignment[key] for key in ("slug", "effort")}
            if (
                reader.get("work_id") != "PSP-P03-W07"
                or reader.get("issue") != mapping["issues"]["PSP-P03-W07"]["url"]
                or reader.get("state") != "open"
                or reader.get("assignment") != expected_assignment
            ):
                raise P14Error("C03 reader frontier drift")
            _text(reader.get("acceptance_boundary"), "C03 reader frontier acceptance_boundary")
            if not HEAD_RE.fullmatch(str(row.get("accepted_checkpoint") or "")):
                raise P14Error("C03 accepted checkpoint must be an exact commit")
        elif frontier:
            raise P14Error(f"{chunk_id} must not invent a frontier ahead of C03")
    if tuple(chunk_ids) != PREDECESSOR_CHUNK_IDS:
        raise P14Error("predecessor chunks must remain in canonical C03-C11 order")

    c12 = graph["chunk_by_id"]["PSP-C12"]
    expected_p14_conductor = {key: c12["conductor"][key] for key in ("slug", "effort")}
    if ledger.get("p14_conductor") != expected_p14_conductor:
        raise P14Error("P14 conductor assignment drift")
    p14_stages = _list(ledger.get("p14_stages"), "dependency ledger p14_stages")
    if len(p14_stages) != len(WORK_IDS):
        raise P14Error("dependency ledger must contain all nine P14 stages")
    for index, work_id in enumerate(WORK_IDS):
        row = _mapping(p14_stages[index], f"p14_stages[{index}]")
        packet = graph["work_by_id"][work_id]
        assignment = program["model_assignment_for"](work_id, graph)
        if (
            row.get("work_id") != work_id
            or row.get("issue") != mapping["issues"][work_id]["url"]
            or row.get("depends_on") != packet["depends_on"]
            or row.get("assignment") != {key: assignment[key] for key in ("slug", "effort")}
            or row.get("closure_state") != "open"
            or row.get("counts_as_closure") is not False
        ):
            raise P14Error(f"{work_id} dependency, issue, assignment, or closure drift")
        _text(row.get("preflight_state"), f"{work_id}.preflight_state")

    terminal_nodes = _list(ledger.get("terminal_nodes"), "dependency ledger terminal_nodes")
    requirements = contract["terminal_requirements"]
    if len(terminal_nodes) != len(requirements):
        raise P14Error("dependency ledger terminal-node count drift")
    for index, requirement in enumerate(requirements):
        row = _mapping(terminal_nodes[index], f"terminal_nodes[{index}]")
        expected = {key: requirement[key] for key in ("code", "work_id", "kind")}
        if (
            any(row.get(key) != value for key, value in expected.items())
            or row.get("closure_state") != "open"
            or row.get("counts_as_closure") is not False
        ):
            raise P14Error(f"terminal node drift at {requirement['code']}")
    return ledger


def load_dependency_ledger(
    path: Path = DEFAULT_LEDGER,
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if contract is None:
        contract = load_contract()
    return validate_dependency_ledger(_load_json(path), contract)


def dependency_report(ledger: dict[str, Any]) -> dict[str, Any]:
    blockers = [
        {
            "chunk_id": row["chunk_id"],
            "closure_state": row["closure_state"],
            "preflight_state": row["preflight_state"],
            "depends_on": row["depends_on"],
        }
        for row in ledger["predecessor_chunks"]
        if row["closure_state"] != "closed"
    ]
    frontier: list[dict[str, Any]] = []
    for row in ledger["predecessor_chunks"]:
        if row["closure_state"] != "closed" and row["frontier_work"]:
            frontier = deepcopy(row["frontier_work"])
            break
    return {
        "status": "blocked" if blockers else "pass",
        "predecessor_chunk_count": len(ledger["predecessor_chunks"]),
        "predecessor_blocker_count": len(blockers),
        "predecessor_blockers": blockers,
        "execution_frontier": frontier,
        "counts_as_closure": False,
    }


def validate_contract(value: object) -> dict[str, Any]:
    contract = _mapping(value, "control plane")
    if contract.get("schema_version") != CONTROL_SCHEMA:
        raise P14Error(f"schema_version must be {CONTROL_SCHEMA}")
    if contract.get("phase_id") != "PSP-P14" or contract.get("chunk_id") != "PSP-C12":
        raise P14Error("control plane must be scoped to PSP-C12 / PSP-P14")
    predecessor = _mapping(contract.get("predecessor_policy"), "predecessor_policy")
    if predecessor.get("mode") != "receipt-only" or predecessor.get("execute_commands") is not False:
        raise P14Error("predecessor policy must consume receipts without executing predecessor commands")
    dependency_contract = _mapping(contract.get("dependency_ledger"), "dependency_ledger")
    if (
        dependency_contract.get("path") != "institutio/positioning/p14/dependency-ledger.json"
        or dependency_contract.get("schema_version") != LEDGER_SCHEMA
        or dependency_contract.get("predecessor_chunk_count") != len(PREDECESSOR_CHUNK_IDS)
        or dependency_contract.get("terminal_node_count") != 23
        or dependency_contract.get("counts_as_closure") is not False
    ):
        raise P14Error("dependency-ledger contract drift")
    public_contract = _mapping(contract.get("public_evidence_contract"), "public_evidence_contract")
    deny_keys = _list(public_contract.get("deny_keys"), "public_evidence_contract.deny_keys", nonempty=True)
    if len(deny_keys) != len(set(deny_keys)) or set(deny_keys) != EXPECTED_DENY_KEYS:
        raise P14Error("public evidence deny-key contract drift")
    _text(public_contract.get("identity_rule"), "public_evidence_contract.identity_rule")
    _text(public_contract.get("violation_rule"), "public_evidence_contract.violation_rule")
    program_receipt = _mapping(contract.get("program_receipt_contract"), "program_receipt_contract")
    program_fields = _list(program_receipt.get("required_fields"), "program_receipt_contract.required_fields")
    if (
        program_receipt.get("command") != "python3 scripts/positioning-program.py --omega --require-two-pass"
        or set(program_fields) != PROGRAM_RECEIPT_FIELDS
        or len(program_fields) != len(PROGRAM_RECEIPT_FIELDS)
        or program_receipt.get("scope") != "live"
        or program_receipt.get("bind_state_digest_to_omega_pair") is not True
        or program_receipt.get("require_observation_at_or_after_second_pass") is not True
    ):
        raise P14Error("program Omega receipt contract drift")
    stages = _list(contract.get("stages"), "stages", nonempty=True)
    order = _topological_stages(stages)

    event_types: set[str] = set()
    for index, raw in enumerate(_list(contract.get("events"), "events", nonempty=True)):
        event = _mapping(raw, f"events[{index}]")
        event_type = _text(event.get("type"), f"events[{index}].type")
        if not EVENT_RE.fullmatch(event_type):
            raise P14Error(f"invalid event type: {event_type}")
        if event_type in event_types:
            raise P14Error(f"duplicate event type: {event_type}")
        event_types.add(event_type)
        for field in ("owner", "source", "cadence", "privacy", "decision_use"):
            _text(event.get(field), f"{event_type}.{field}")

    metric_ids: set[str] = set()
    for index, raw in enumerate(_list(contract.get("metrics"), "metrics", nonempty=True)):
        metric = _mapping(raw, f"metrics[{index}]")
        metric_id = _text(metric.get("id"), f"metrics[{index}].id")
        if metric_id in metric_ids:
            raise P14Error(f"duplicate metric id: {metric_id}")
        metric_ids.add(metric_id)
        for field in ("numerator_event", "denominator_event"):
            event_type = _text(metric.get(field), f"{metric_id}.{field}")
            if event_type not in event_types:
                raise P14Error(f"{metric_id}.{field} references unknown event {event_type}")
        minimum = metric.get("minimum_denominator")
        if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 1:
            raise P14Error(f"{metric_id}.minimum_denominator must be a positive integer")
        for field in ("owner", "cadence", "decision_use", "guardrail"):
            _text(metric.get(field), f"{metric_id}.{field}")

    reviews = _mapping(contract.get("reviews"), "reviews")
    for cadence, work_id in (("weekly", WORK_IDS[1]), ("monthly", WORK_IDS[2]), ("quarterly", WORK_IDS[3])):
        review = _mapping(reviews.get(cadence), f"reviews.{cadence}")
        if review.get("work_id") != work_id:
            raise P14Error(f"reviews.{cadence}.work_id must be {work_id}")
        minimum = review.get("minimum_live_receipts")
        if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 1:
            raise P14Error(f"reviews.{cadence}.minimum_live_receipts must be positive")
        if review.get("synthetic_counts_as_live") is not False:
            raise P14Error(f"reviews.{cadence} must reject synthetic cycles as live")
        _list(review.get("inputs"), f"reviews.{cadence}.inputs", nonempty=True)
        _list(review.get("outputs"), f"reviews.{cadence}.outputs", nonempty=True)

    claim_incident = _mapping(contract.get("claim_incident"), "claim_incident")
    if claim_incident.get("work_id") != WORK_IDS[4]:
        raise P14Error(f"claim_incident.work_id must be {WORK_IDS[4]}")
    _text(claim_incident.get("required_correction_status"), "claim_incident.required_correction_status")
    _list(claim_incident.get("sequence"), "claim_incident.sequence", nonempty=True)

    release_recovery = _mapping(contract.get("release_recovery"), "release_recovery")
    if release_recovery.get("work_id") != WORK_IDS[5]:
        raise P14Error(f"release_recovery.work_id must be {WORK_IDS[5]}")
    _text(release_recovery.get("required_health"), "release_recovery.required_health")
    _list(release_recovery.get("sequence"), "release_recovery.sequence", nonempty=True)

    feedback = _mapping(contract.get("feedback_loops"), "feedback_loops")
    sales = _mapping(feedback.get("sales"), "feedback_loops.sales")
    delivery = _mapping(feedback.get("delivery"), "feedback_loops.delivery")
    if sales.get("work_id") != WORK_IDS[6] or delivery.get("work_id") != WORK_IDS[7]:
        raise P14Error("feedback loops must map to W07 sales and W08 delivery")
    minimum_outcomes = sales.get("minimum_revision_outcomes")
    if not isinstance(minimum_outcomes, int) or isinstance(minimum_outcomes, bool) or minimum_outcomes < 1:
        raise P14Error("feedback_loops.sales.minimum_revision_outcomes must be positive")
    _text(sales.get("required_human_gate"), "feedback_loops.sales.required_human_gate")
    _list(sales.get("allowed_decisions"), "feedback_loops.sales.allowed_decisions", nonempty=True)
    _list(delivery.get("required_impacts"), "feedback_loops.delivery.required_impacts", nonempty=True)

    omega = _mapping(contract.get("omega"), "omega")
    if omega.get("work_id") != WORK_IDS[-1]:
        raise P14Error(f"omega.work_id must be {WORK_IDS[-1]}")
    if omega.get("pair_schema_version") != PAIR_SCHEMA or omega.get("pass_schema_version") != OMEGA_PASS_SCHEMA:
        raise P14Error("Omega schemas do not match the tracked two-pass contract")
    if (
        omega.get("require_distinct_observed_at") is not True
        or omega.get("require_strict_observation_order") is not True
        or omega.get("require_equal_state_digest") is not True
    ):
        raise P14Error("Omega must require distinct observations of one unchanged digest")
    if omega.get("live_pass_required_fields") != ["ok", "parity", "open", "verified_receipts", "failures"]:
        raise P14Error("Omega live-pass field contract drift")
    if omega.get("live_pair_evidence_urls") != 2:
        raise P14Error("Omega live pair must bind exactly two evidence URLs")
    expected_live = "python3 scripts/positioning-program.py --omega --require-two-pass"
    if omega.get("live_predicate") != expected_live:
        raise P14Error(f"omega.live_predicate must be {expected_live}")

    requirements = _list(contract.get("terminal_requirements"), "terminal_requirements", nonempty=True)
    codes: set[str] = set()
    work_receipts: set[str] = set()
    kinds = {"work_receipt", "minimum_records", "status_record", "human_gate", "omega_pair"}
    for index, raw in enumerate(requirements):
        requirement = _mapping(raw, f"terminal_requirements[{index}]")
        code = _text(requirement.get("code"), f"terminal_requirements[{index}].code")
        if code in codes:
            raise P14Error(f"duplicate terminal requirement code: {code}")
        codes.add(code)
        work_id = _text(requirement.get("work_id"), f"{code}.work_id")
        if work_id not in WORK_IDS:
            raise P14Error(f"{code}.work_id is outside P14")
        kind = _text(requirement.get("kind"), f"{code}.kind")
        if kind not in kinds:
            raise P14Error(f"{code}.kind is unsupported: {kind}")
        _text(requirement.get("owner"), f"{code}.owner")
        _text(requirement.get("description"), f"{code}.description")
        if kind == "work_receipt":
            work_receipts.add(work_id)
        elif kind == "minimum_records":
            _text(requirement.get("path"), f"{code}.path")
            minimum = requirement.get("minimum")
            if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 1:
                raise P14Error(f"{code}.minimum must be positive")
            _list(requirement.get("required_fields"), f"{code}.required_fields", nonempty=True)
            if requirement.get("consecutive") is True and requirement.get("cadence") not in {"weekly", "monthly"}:
                raise P14Error(f"{code}.cadence must be weekly or monthly when consecutive")
        elif kind == "status_record":
            _text(requirement.get("path"), f"{code}.path")
            _text(requirement.get("expected_status"), f"{code}.expected_status")
            _list(requirement.get("required_fields"), f"{code}.required_fields", nonempty=True)
        elif kind == "human_gate":
            _text(requirement.get("gate_id"), f"{code}.gate_id")
        elif kind == "omega_pair":
            _text(requirement.get("path"), f"{code}.path")
    if work_receipts != set(WORK_IDS):
        raise P14Error("terminal requirements must name one durable receipt for every P14 work id")
    if len(requirements) != dependency_contract["terminal_node_count"]:
        raise P14Error("terminal requirement count differs from the dependency-ledger contract")
    program_requirement = next(
        (item for item in requirements if item.get("code") == "PROGRAM_OMEGA_RECEIPT_MISSING"),
        None,
    )
    if (
        not isinstance(program_requirement, dict)
        or set(program_requirement.get("required_fields") or []) != PROGRAM_RECEIPT_FIELDS
    ):
        raise P14Error("terminal program Omega receipt fields drift")
    return {**contract, "stage_order": order}


def load_contract(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    return validate_contract(_load_json(path))


def _event_counts(events: list[Any], event_types: set[str]) -> dict[str, int]:
    counts = {event_type: 0 for event_type in event_types}
    seen_ids: set[str] = set()
    for index, raw in enumerate(events):
        event = _mapping(raw, f"fixture.events[{index}]")
        event_id = _text(event.get("event_id"), f"fixture.events[{index}].event_id")
        if event_id in seen_ids:
            raise P14Error(f"duplicate fixture event id: {event_id}")
        seen_ids.add(event_id)
        event_type = _text(event.get("type"), f"fixture.events[{index}].type")
        if event_type not in event_types:
            raise P14Error(f"fixture event type is not declared: {event_type}")
        if event.get("scope") != "synthetic":
            raise P14Error(f"fixture event {event_id} must remain synthetic")
        _text(event.get("entity_id"), f"fixture.events[{index}].entity_id")
        if not _is_rfc3339(event.get("occurred_at")):
            raise P14Error(f"fixture event {event_id} occurred_at must be RFC3339")
        counts[event_type] += 1
    return counts


def _metric_results(contract: dict[str, Any], fixture: dict[str, Any]) -> dict[str, Any]:
    event_types = {event["type"] for event in contract["events"]}
    counts = _event_counts(_list(fixture.get("events"), "fixture.events", nonempty=True), event_types)
    metrics: dict[str, Any] = {}
    for metric in contract["metrics"]:
        numerator = counts[metric["numerator_event"]]
        denominator = counts[metric["denominator_event"]]
        if denominator < metric["minimum_denominator"]:
            raise P14Error(
                f"synthetic metric {metric['id']} denominator {denominator} is below {metric['minimum_denominator']}"
            )
        metrics[metric["id"]] = {
            "numerator": numerator,
            "denominator": denominator,
            "value": numerator / denominator,
            "scope": "synthetic",
            "decision_use": metric["decision_use"],
            "guardrail": metric["guardrail"],
        }
    return {"status": "definition-valid", "scope": "synthetic", "event_counts": counts, "metrics": metrics}


def _claim_incident_result(contract: dict[str, Any], fixture: dict[str, Any]) -> dict[str, Any]:
    incident = _mapping(fixture.get("claim_incident"), "fixture.claim_incident")
    claim = _mapping(incident.get("claim"), "fixture.claim_incident.claim")
    claim_id = _text(claim.get("claim_id"), "fixture.claim_incident.claim.claim_id")
    surfaces = deepcopy(_list(incident.get("surfaces"), "fixture.claim_incident.surfaces", nonempty=True))
    affected = sorted(
        _text(surface.get("surface_id"), "claim incident surface id")
        for surface in surfaces
        if claim_id in _list(surface.get("published_claim_ids"), "published_claim_ids")
    )
    if not affected:
        raise P14Error("synthetic claim incident has no dependent surfaces")
    quarantined = deepcopy(surfaces)
    for surface in quarantined:
        surface["published_claim_ids"] = [
            item for item in _list(surface.get("published_claim_ids"), "published_claim_ids") if item != claim_id
        ]
    if any(claim_id in surface["published_claim_ids"] for surface in quarantined):
        raise P14Error("claim quarantine did not remove every dependent surface")
    correction = _mapping(incident.get("correction"), "fixture.claim_incident.correction")
    required_status = contract["claim_incident"]["required_correction_status"]
    if correction.get("status") != required_status:
        raise P14Error(f"claim correction status must be {required_status}")
    if correction.get("version") == claim.get("version"):
        raise P14Error("claim correction must bind a new evidence version")
    restore_surfaces = sorted(
        _text(item, "fixture.claim_incident.restore_surfaces")
        for item in _list(incident.get("restore_surfaces"), "fixture.claim_incident.restore_surfaces", nonempty=True)
    )
    if not set(restore_surfaces).issubset(affected):
        raise P14Error("claim correction may restore only previously affected surfaces")
    restored = deepcopy(quarantined)
    for surface in restored:
        if surface["surface_id"] in restore_surfaces:
            surface["published_claim_ids"].append(claim_id)
            surface["published_claim_ids"].sort()
    return {
        "status": "synthetic-pass",
        "scope": "synthetic",
        "claim_id": claim_id,
        "quarantined_surfaces": affected,
        "blocked_republish": True,
        "corrected_evidence": {
            "version": correction["version"],
            "status": correction["status"],
            "evidence_id": _text(correction.get("evidence_id"), "claim correction evidence_id"),
        },
        "restored_surfaces": restore_surfaces,
        "timeline": [
            "quarantined",
            "dependent-surfaces-cleared",
            "republish-blocked",
            "evidence-corrected",
            "corrected-claim-restored",
        ],
    }


def _release_recovery_result(contract: dict[str, Any], fixture: dict[str, Any]) -> dict[str, Any]:
    recovery = _mapping(fixture.get("release_recovery"), "fixture.release_recovery")
    before = _text(recovery.get("before_release_id"), "release before_release_id")
    bad = _text(recovery.get("bad_release_id"), "release bad_release_id")
    restored = _text(recovery.get("restored_release_id"), "release restored_release_id")
    if len({before, bad}) != 2 or restored != before:
        raise P14Error("release drill must restore the exact distinct known-green release")
    health_checks = _mapping(recovery.get("health_checks"), "release health_checks")
    required_health = contract["release_recovery"]["required_health"]
    if not health_checks or any(value != required_health for value in health_checks.values()):
        raise P14Error(f"all release health checks must be {required_health}")
    owner_before = _text(recovery.get("capture_owner_before"), "capture_owner_before")
    owner_after = _text(recovery.get("capture_owner_after"), "capture_owner_after")
    if owner_before != owner_after:
        raise P14Error("release rollback changed capture ownership")
    repositories = sorted(
        _text(item, "release resolved repository")
        for item in _list(recovery.get("resolved_repositories"), "resolved_repositories", nonempty=True)
    )
    return {
        "status": "synthetic-pass",
        "scope": "synthetic",
        "resolved_repositories": repositories,
        "before_release_ids": [before],
        "bad_release_ids": [bad],
        "restored_release_ids": [restored],
        "health_checks": health_checks,
        "capture_continuity": True,
    }


def _sales_feedback_result(contract: dict[str, Any], fixture: dict[str, Any]) -> dict[str, Any]:
    sales = _mapping(fixture.get("sales_feedback"), "fixture.sales_feedback")
    outcomes = _list(sales.get("outcomes"), "fixture.sales_feedback.outcomes", nonempty=True)
    minimum = contract["feedback_loops"]["sales"]["minimum_revision_outcomes"]
    if len(outcomes) < minimum:
        raise P14Error(f"synthetic sales feedback needs at least {minimum} outcomes")
    outcome_ids = []
    for index, raw in enumerate(outcomes):
        outcome = _mapping(raw, f"sales outcome {index}")
        if outcome.get("scope") != "synthetic":
            raise P14Error("sales fixture outcomes must remain synthetic")
        outcome_ids.append(_text(outcome.get("outcome_id"), f"sales outcome {index}.outcome_id"))
        _text(outcome.get("objection"), f"sales outcome {index}.objection")
    if len(set(outcome_ids)) != len(outcome_ids):
        raise P14Error("sales outcome ids must be unique")
    decision = _text(sales.get("decision"), "sales decision")
    if decision not in contract["feedback_loops"]["sales"]["allowed_decisions"]:
        raise P14Error(f"unsupported sales decision: {decision}")
    before = _text(sales.get("before_offer_version"), "before_offer_version")
    after = _text(sales.get("after_offer_version"), "after_offer_version")
    if before == after:
        raise P14Error("offer feedback must preserve distinct before and after versions")
    retained = sorted(
        _text(item, "retained outcome id")
        for item in _list(sales.get("retained_outcome_ids"), "retained_outcome_ids", nonempty=True)
    )
    if retained != sorted(outcome_ids):
        raise P14Error("offer feedback did not preserve the complete outcome history")
    human_gate = _mapping(sales.get("human_gate"), "sales human_gate")
    expected_gate = contract["feedback_loops"]["sales"]["required_human_gate"]
    if human_gate.get("gate_id") != expected_gate or human_gate.get("status") != "pending":
        raise P14Error("synthetic sales feedback must leave the price-anchor human gate pending")
    return {
        "status": "synthetic-pass",
        "scope": "synthetic",
        "outcome_ids": sorted(outcome_ids),
        "decision": decision,
        "before_offer_version": before,
        "after_offer_version": after,
        "retained_outcome_ids": retained,
        "human_gate": {"gate_id": expected_gate, "status": "pending"},
        "real_demand_claimed": False,
    }


def _delivery_feedback_result(contract: dict[str, Any], fixture: dict[str, Any]) -> dict[str, Any]:
    delivery = _mapping(fixture.get("delivery_feedback"), "fixture.delivery_feedback")
    outcomes = _list(delivery.get("outcomes"), "fixture.delivery_feedback.outcomes", nonempty=True)
    required = contract["feedback_loops"]["delivery"]["required_impacts"]
    outcome_ids: list[str] = []
    kinds: set[str] = set()
    impacts: list[dict[str, Any]] = []
    for index, raw in enumerate(outcomes):
        outcome = _mapping(raw, f"delivery outcome {index}")
        if outcome.get("scope") != "synthetic":
            raise P14Error("delivery fixture outcomes must remain synthetic")
        outcome_id = _text(outcome.get("outcome_id"), f"delivery outcome {index}.outcome_id")
        kind = _text(outcome.get("kind"), f"delivery outcome {index}.kind")
        if kind not in {"delivery", "operator"}:
            raise P14Error(f"unsupported outcome kind: {kind}")
        outcome_ids.append(outcome_id)
        kinds.add(kind)
        impact = {field: _text(outcome.get(field), f"{outcome_id}.{field}") for field in required}
        impacts.append({"outcome_id": outcome_id, "kind": kind, **impact})
    if len(set(outcome_ids)) != len(outcome_ids) or kinds != {"delivery", "operator"}:
        raise P14Error("delivery fixture needs unique delivery and operator outcomes")
    changes = _list(delivery.get("portfolio_impacts"), "fixture.delivery_feedback.portfolio_impacts", nonempty=True)
    change_ids = sorted(
        _text(_mapping(item, "portfolio impact").get("outcome_id"), "portfolio impact outcome_id") for item in changes
    )
    if change_ids != sorted(outcome_ids):
        raise P14Error("every synthetic outcome must have one portfolio impact record")
    for item in changes:
        change = _mapping(item, "portfolio impact")
        for field in ("before_class", "after_class", "reason"):
            _text(change.get(field), f"portfolio impact {field}")
    return {
        "status": "synthetic-pass",
        "scope": "synthetic",
        "outcomes": impacts,
        "portfolio_impacts": changes,
        "outcome_receipts_preserved": True,
        "real_delivery_claimed": False,
        "real_operator_outcome_claimed": False,
    }


def verify_omega_pair(value: object, *, required_scope: str) -> dict[str, Any]:
    pair = _mapping(value, "Omega pair")
    if pair.get("schema_version") != PAIR_SCHEMA:
        raise P14Error(f"Omega pair schema_version must be {PAIR_SCHEMA}")
    if pair.get("scope") != required_scope:
        raise P14Error(f"Omega pair scope must be {required_scope}; synthetic evidence cannot satisfy live Omega")
    passes = _list(pair.get("passes"), "Omega pair passes")
    if len(passes) != 2:
        raise P14Error("Omega pair must contain exactly two passes")
    normalized: list[dict[str, Any]] = []
    observed_times: list[datetime] = []
    for number, raw in enumerate(passes, start=1):
        record = _mapping(raw, f"Omega pass {number}")
        if record.get("schema_version") != OMEGA_PASS_SCHEMA:
            raise P14Error(f"Omega pass {number} schema_version must be {OMEGA_PASS_SCHEMA}")
        if record.get("status") != "pass" or record.get("pass") != number:
            raise P14Error(f"Omega pass {number} must be a passing pass-{number} record")
        if not DIGEST_RE.fullmatch(str(record.get("state_digest") or "")):
            raise P14Error(f"Omega pass {number} state_digest must be sha256")
        observed_time = _rfc3339_datetime(record.get("observed_at"))
        if observed_time is None:
            raise P14Error(f"Omega pass {number} observed_at must be RFC3339")
        observed_times.append(observed_time)
        if required_scope == "live":
            missing_fields = [
                field for field in ("ok", "parity", "open", "verified_receipts", "failures") if field not in record
            ]
            if missing_fields:
                raise P14Error(f"Omega pass {number} is missing canonical live fields: {missing_fields}")
            if record.get("ok") is not True or record.get("open") != [] or record.get("failures") != []:
                raise P14Error(f"Omega pass {number} is not a clean canonical live pass")
            verified_receipts = record.get("verified_receipts")
            if not isinstance(verified_receipts, int) or isinstance(verified_receipts, bool) or verified_receipts < 1:
                raise P14Error(f"Omega pass {number} verified_receipts must be positive")
            parity = _mapping(record.get("parity"), f"Omega pass {number} parity")
            expected = parity.get("expected")
            observed = parity.get("observed")
            if (
                parity.get("ok") is not True
                or not isinstance(expected, int)
                or isinstance(expected, bool)
                or expected < 1
                or observed != expected
                or parity.get("missing") != []
                or parity.get("orphan") != []
                or parity.get("drift") != []
            ):
                raise P14Error(f"Omega pass {number} parity is incomplete or drifted")
        normalized.append(record)
    if normalized[0]["state_digest"] != normalized[1]["state_digest"]:
        raise P14Error("Omega pass digests differ")
    if observed_times[1] <= observed_times[0]:
        raise P14Error("Omega passes must be strictly ordered distinct observations")
    if required_scope == "live":
        evidence_urls = _list(pair.get("evidence_urls"), "live Omega evidence_urls", nonempty=True)
        if len(evidence_urls) != 2 or len(set(evidence_urls)) != 2 or not all(_is_url(item) for item in evidence_urls):
            raise P14Error("live Omega must bind exactly two unique HTTPS evidence URLs")
    return {
        "status": "pass",
        "scope": required_scope,
        "state_digest": normalized[0]["state_digest"],
        "observed_at": [record["observed_at"] for record in normalized],
    }


def run_synthetic(contract: dict[str, Any], value: object) -> dict[str, Any]:
    fixture = _mapping(value, "fixture")
    if fixture.get("schema_version") != FIXTURE_SCHEMA or fixture.get("scope") != "synthetic":
        raise P14Error(f"fixture must use {FIXTURE_SCHEMA} with synthetic scope")
    predecessors = _list(fixture.get("predecessor_receipts"), "fixture.predecessor_receipts")
    reused: list[dict[str, str]] = []
    for index, raw in enumerate(predecessors):
        receipt = _mapping(raw, f"fixture.predecessor_receipts[{index}]")
        if receipt.get("status") != "pass":
            raise P14Error("fixture predecessor receipts must already pass")
        work_id = _text(receipt.get("work_id"), "predecessor work_id")
        digest = _text(receipt.get("receipt_sha256"), "predecessor receipt_sha256")
        if not DIGEST_RE.fullmatch(digest):
            raise P14Error("predecessor receipt_sha256 must be sha256")
        reused.append({"work_id": work_id, "receipt_sha256": digest})

    results: dict[str, Any] = {}
    results[WORK_IDS[0]] = _metric_results(contract, fixture)
    for cadence, work_id in (("weekly", WORK_IDS[1]), ("monthly", WORK_IDS[2]), ("quarterly", WORK_IDS[3])):
        review = contract["reviews"][cadence]
        results[work_id] = {
            "status": "contract-ready",
            "scope": "synthetic",
            "cadence": cadence,
            "period": review["period"],
            "minimum_live_receipts": review["minimum_live_receipts"],
            "live_receipts_observed": 0,
            "synthetic_counts_as_live": False,
            "inputs": review["inputs"],
            "outputs": review["outputs"],
        }
    results[WORK_IDS[4]] = _claim_incident_result(contract, fixture)
    results[WORK_IDS[5]] = _release_recovery_result(contract, fixture)
    results[WORK_IDS[6]] = _sales_feedback_result(contract, fixture)
    results[WORK_IDS[7]] = _delivery_feedback_result(contract, fixture)

    state_digest = _canonical_digest({"scope": "synthetic", "stages": results})
    observations = _list(fixture.get("omega_observed_at"), "fixture.omega_observed_at")
    if len(observations) != 2 or not all(_is_rfc3339(item) for item in observations):
        raise P14Error("fixture must name two RFC3339 Omega observation times")
    pair = {
        "schema_version": PAIR_SCHEMA,
        "scope": "synthetic",
        "passes": [
            {
                "schema_version": OMEGA_PASS_SCHEMA,
                "status": "pass",
                "pass": number,
                "state_digest": state_digest,
                "observed_at": observations[number - 1],
            }
            for number in (1, 2)
        ],
    }
    pair_result = verify_omega_pair(pair, required_scope="synthetic")
    results[WORK_IDS[8]] = {**pair_result, "status": "synthetic-pass", "pair": pair}
    return {
        "schema_version": "limen.positioning_p14_fixture_result.v1",
        "status": "synthetic-pass",
        "scope": "synthetic",
        "stage_order": contract["stage_order"],
        "reused_predecessor_receipts": sorted(reused, key=lambda item: item["work_id"]),
        "executed_predecessor_commands": [],
        "stages": results,
        "not_evidence_for": [
            "Omega",
            "real demand",
            "real client outcomes",
            "real operator outcomes",
            "completed weekly, monthly, or quarterly review cycles",
            "human acceptance",
        ],
    }


def _valid_work_receipt(value: object) -> tuple[bool, str]:
    if not isinstance(value, dict):
        return False, "no receipt object"
    if value.get("scope") != "live" or value.get("status") != "pass":
        return False, "receipt is not a passing live receipt"
    if not _is_url(value.get("evidence_url")):
        return False, "evidence_url is not HTTPS"
    if not HEAD_RE.fullmatch(str(value.get("exact_head") or "")):
        return False, "exact_head is not a 40-character commit"
    predicate = value.get("predicate")
    if not isinstance(predicate, dict) or predicate.get("exit_code") != 0:
        return False, "underlying predicate did not record exit 0"
    command = str(predicate.get("command") or "")
    if not command or "--verify-work" in command:
        return False, "predicate is empty or circular"
    return True, "valid"


def _valid_record(value: object, requirement: dict[str, Any]) -> tuple[bool, str]:
    if not isinstance(value, dict):
        return False, "no record object"
    expected = requirement.get("expected_status")
    if expected is not None and value.get("status") != expected:
        return False, f"status is not {expected}"
    required_scope = requirement.get("required_scope")
    if required_scope is not None and value.get("scope") != required_scope:
        return False, f"scope is not {required_scope}"
    missing = [field for field in requirement.get("required_fields") or [] if not _meaningful(value.get(field))]
    if missing:
        return False, f"missing fields: {missing}"
    if "evidence_url" in (requirement.get("required_fields") or []) and not _is_url(value.get("evidence_url")):
        return False, "evidence_url is not HTTPS"
    if requirement["code"] == "CLAIM_INCIDENT_DRILL_MISSING":
        if value.get("blocked_republish") is not True:
            return False, "republish was not blocked before correction"
        if not isinstance(value.get("quarantined_surfaces"), list) or not value["quarantined_surfaces"]:
            return False, "no quarantined surface set"
        corrected = value.get("corrected_evidence")
        if not isinstance(corrected, dict) or corrected.get("status") != "verified":
            return False, "corrected evidence is not verified"
    if requirement["code"] == "RELEASE_RECOVERY_DRILL_MISSING":
        before = value.get("before_release_ids")
        bad = value.get("bad_release_ids")
        restored = value.get("restored_release_ids")
        if (
            not isinstance(before, list)
            or not before
            or not all(isinstance(item, str) and item for item in before)
            or not isinstance(restored, list)
            or not all(isinstance(item, str) and item for item in restored)
            or before != restored
        ):
            return False, "restored release ids do not exactly match the known-green ids"
        if (
            not isinstance(bad, list)
            or not bad
            or not all(isinstance(item, str) and item for item in bad)
            or set(bad) & set(before)
        ):
            return False, "bad release ids are missing or overlap the known-green ids"
        checks = value.get("health_checks")
        if (
            not isinstance(checks, dict)
            or not checks
            or any(item not in {"healthy", "pass"} for item in checks.values())
        ):
            return False, "post-rollback health checks are incomplete"
        if value.get("capture_continuity") is not True:
            return False, "capture ownership continuity did not pass"
    if requirement["code"] == "DEMAND_DECISION_MISSING":
        outcome_ids = value.get("outcome_ids")
        if (
            not isinstance(outcome_ids, list)
            or not outcome_ids
            or not all(isinstance(item, str) and item for item in outcome_ids)
            or len(set(outcome_ids)) != len(outcome_ids)
        ):
            return False, "decision outcome_ids are missing or duplicated"
        if value.get("before_offer_version") == value.get("after_offer_version"):
            return False, "offer decision did not preserve distinct before and after versions"
        if value.get("decision") not in {"keep", "narrow", "promote", "withdraw"}:
            return False, "offer decision is outside the governed vocabulary"
    if requirement["code"] == "COMMERCIAL_SUCCESS_OUTCOME_MISSING":
        outcome_ids = value.get("outcome_ids")
        if (
            not isinstance(outcome_ids, list)
            or not all(isinstance(item, str) and item for item in outcome_ids)
            or len(set(outcome_ids)) != len(outcome_ids)
        ):
            return False, "commercial outcome ids are missing or duplicated"
        mode = value.get("mode")
        if mode == "paid_audit" and len(outcome_ids) < 1:
            return False, "paid-audit mode has no outcome receipt"
        if mode == "documented_no" and len(outcome_ids) < 5:
            return False, "documented-no mode requires five outcome receipts"
        if mode not in {"paid_audit", "documented_no"}:
            return False, "commercial outcome mode must be paid_audit or documented_no"
    if requirement["code"] == "PROGRAM_OMEGA_RECEIPT_MISSING":
        expected_command = "python3 scripts/positioning-program.py --omega --require-two-pass"
        if value.get("command") != expected_command or value.get("exit_code") != 0:
            return False, "program Omega command or exit code does not match"
        if not DIGEST_RE.fullmatch(str(value.get("output_sha256") or "")):
            return False, "program Omega output_sha256 is invalid"
        if not DIGEST_RE.fullmatch(str(value.get("state_digest") or "")):
            return False, "program Omega state_digest is invalid"
        if not HEAD_RE.fullmatch(str(value.get("observed_head") or "")):
            return False, "program Omega observed_head is invalid"
        if not _is_rfc3339(value.get("observed_at")):
            return False, "program Omega observed_at is invalid"
    return True, "valid"


def _valid_records(value: object, requirement: dict[str, Any]) -> tuple[bool, str]:
    if not isinstance(value, list):
        return False, "no record list"
    valid_records: list[dict[str, Any]] = []
    invalid_reasons: list[str] = []
    outcome_codes = {
        "REAL_DEMAND_OUTCOMES_MISSING",
        "REAL_DELIVERY_OUTCOME_MISSING",
        "REAL_OPERATOR_OUTCOME_MISSING",
        "PORTFOLIO_IMPACT_RECEIPT_MISSING",
    }
    seen_outcome_ids: set[str] = set()
    for record in value:
        if not isinstance(record, dict):
            invalid_reasons.append("non-object record")
            continue
        if requirement.get("required_scope") and record.get("scope") != requirement["required_scope"]:
            invalid_reasons.append(f"scope {record.get('scope')!r}")
            continue
        missing = [field for field in requirement.get("required_fields") or [] if not _meaningful(record.get(field))]
        if missing:
            invalid_reasons.append(f"missing {missing}")
            continue
        if "evidence_url" in (requirement.get("required_fields") or []) and not _is_url(record.get("evidence_url")):
            invalid_reasons.append("non-HTTPS evidence_url")
            continue
        if requirement["code"] == "MONTHLY_LIVE_CYCLES_MISSING":
            count_fields = (
                "unowned_stale_claims",
                "unowned_broken_links",
                "unowned_private_leaks",
                "unowned_surface_parity_defects",
            )
            if any(record.get(field) != 0 for field in count_fields):
                invalid_reasons.append("monthly audit retains an unowned truth/link/privacy/parity defect")
                continue
        if requirement["code"] in outcome_codes:
            outcome_id = record.get("outcome_id")
            if not isinstance(outcome_id, str) or not outcome_id or outcome_id in seen_outcome_ids:
                invalid_reasons.append("missing or duplicate outcome_id")
                continue
            seen_outcome_ids.add(outcome_id)
        valid_records.append(record)
    minimum = requirement["minimum"]
    valid = len(valid_records)
    if valid < minimum:
        return False, f"{valid}/{minimum} valid; total={len(value)}; invalid={invalid_reasons}"
    if requirement.get("consecutive") is True:
        cadence = str(requirement.get("cadence") or "")
        if not _periods_are_consecutive(valid_records, cadence):
            return False, f"{valid}/{minimum} valid records are not distinct consecutive {cadence} periods"
    return True, f"{valid}/{minimum} valid"


def terminal_report(
    contract: dict[str, Any],
    value: object,
    ledger: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if ledger is None:
        ledger = load_dependency_ledger(contract=contract)
    dependency = dependency_report(ledger)
    evidence = value if isinstance(value, dict) else {}
    schema_ok = evidence.get("schema_version") == EVIDENCE_SCHEMA
    scope_ok = evidence.get("scope") == "live"
    deny_keys = set(contract["public_evidence_contract"]["deny_keys"])
    privacy_violations = _privacy_violations(evidence, deny_keys) if evidence else []
    public_safe = not privacy_violations
    evidence_valid = schema_ok and scope_ok and public_safe
    missing: list[dict[str, Any]] = []
    work_receipts = evidence.get("work_receipts") if isinstance(evidence.get("work_receipts"), dict) else {}
    human_gates = evidence.get("human_gates") if isinstance(evidence.get("human_gates"), dict) else {}
    requirements_by_code = {item["code"]: item for item in contract["terminal_requirements"]}

    def record_missing(requirement: dict[str, Any], observed: str) -> None:
        row = {
            "code": requirement["code"],
            "work_id": requirement["work_id"],
            "owner": requirement["owner"],
            "required": requirement["description"],
            "observed": observed,
        }
        for index, current in enumerate(missing):
            if current["code"] == row["code"]:
                missing[index] = row
                return
        missing.append(row)

    omega_result: dict[str, Any] | None = None
    for requirement in contract["terminal_requirements"]:
        kind = requirement["kind"]
        valid = False
        observed = "live evidence envelope is missing or invalid"
        if evidence_valid:
            if kind == "work_receipt":
                valid, observed = _valid_work_receipt(work_receipts.get(requirement["work_id"]))
            elif kind == "minimum_records":
                valid, observed = _valid_records(_path_value(evidence, requirement["path"]), requirement)
            elif kind == "status_record":
                valid, observed = _valid_record(_path_value(evidence, requirement["path"]), requirement)
            elif kind == "human_gate":
                gate = human_gates.get(requirement["gate_id"])
                valid = (
                    isinstance(gate, dict) and gate.get("status") == "resolved" and _is_url(gate.get("evidence_url"))
                )
                observed = "resolved with HTTPS receipt" if valid else "no resolved owner receipt"
            elif kind == "omega_pair":
                pair = _path_value(evidence, requirement["path"])
                try:
                    result = verify_omega_pair(pair, required_scope="live")
                    omega_result = result
                    valid, observed = True, f"unchanged digest {result['state_digest']}"
                except P14Error as exc:
                    observed = str(exc)
        if not valid:
            record_missing(requirement, observed)
    if evidence_valid:
        sales_rows = evidence.get("sales_outcomes") if isinstance(evidence.get("sales_outcomes"), list) else []
        sales_ids = {
            row["outcome_id"]
            for row in sales_rows
            if isinstance(row, dict)
            and row.get("scope") == "live"
            and isinstance(row.get("outcome_id"), str)
            and row["outcome_id"]
        }
        decision = evidence.get("demand_decision") if isinstance(evidence.get("demand_decision"), dict) else {}
        raw_decision_ids = decision.get("outcome_ids") if isinstance(decision.get("outcome_ids"), list) else []
        decision_ids = {item for item in raw_decision_ids if isinstance(item, str) and item}
        live_demand_minimum = requirements_by_code["REAL_DEMAND_OUTCOMES_MISSING"]["minimum"]
        if sales_ids != decision_ids or len(sales_ids) < live_demand_minimum:
            record_missing(
                requirements_by_code["DEMAND_DECISION_MISSING"],
                f"decision outcome ids {sorted(decision_ids)} do not exactly preserve live sales ids {sorted(sales_ids)}",
            )

        source_id_rows: list[str] = []
        for path in ("delivery_outcomes", "operator_outcomes"):
            rows = evidence.get(path) if isinstance(evidence.get(path), list) else []
            source_id_rows.extend(
                row["outcome_id"]
                for row in rows
                if isinstance(row, dict)
                and row.get("scope") == "live"
                and isinstance(row.get("outcome_id"), str)
                and row["outcome_id"]
            )
        source_ids = set(source_id_rows)
        impacts = evidence.get("portfolio_impacts") if isinstance(evidence.get("portfolio_impacts"), list) else []
        impact_id_rows = [
            row["outcome_id"]
            for row in impacts
            if isinstance(row, dict)
            and row.get("scope") == "live"
            and isinstance(row.get("outcome_id"), str)
            and row["outcome_id"]
        ]
        impact_ids = set(impact_id_rows)
        if (
            source_ids != impact_ids
            or not source_ids
            or len(source_id_rows) != len(source_ids)
            or len(impact_id_rows) != len(impact_ids)
        ):
            record_missing(
                requirements_by_code["PORTFOLIO_IMPACT_RECEIPT_MISSING"],
                f"portfolio impact ids {sorted(impact_ids)} do not exactly cover live outcome ids {sorted(source_ids)}",
            )
        program_requirement = requirements_by_code["PROGRAM_OMEGA_RECEIPT_MISSING"]
        program_record = evidence.get("program_omega") if isinstance(evidence.get("program_omega"), dict) else {}
        program_valid, program_observed = _valid_record(program_record, program_requirement)
        if program_valid and omega_result is not None:
            if program_record.get("state_digest") != omega_result["state_digest"]:
                record_missing(
                    program_requirement,
                    "program Omega state_digest does not match the verified two-pass digest",
                )
            else:
                program_time = _rfc3339_datetime(program_record.get("observed_at"))
                second_pass_time = _rfc3339_datetime(omega_result["observed_at"][1])
                if program_time is None or second_pass_time is None or program_time < second_pass_time:
                    record_missing(
                        program_requirement,
                        "program Omega observation predates the second verified pass",
                    )
        elif not program_valid:
            record_missing(program_requirement, program_observed)
    predecessor_count = dependency["predecessor_blocker_count"]
    p14_missing_count = len(missing)
    privacy_blocker_count = 0 if public_safe else 1
    total_missing = predecessor_count + p14_missing_count + privacy_blocker_count
    return {
        "schema_version": "limen.positioning_p14_terminal_report.v1",
        "status": "pass" if total_missing == 0 else "blocked",
        "terminal": total_missing == 0,
        "p14_terminal": p14_missing_count == 0,
        "evidence_envelope": {
            "path_schema_valid": schema_ok,
            "scope_live": scope_ok,
            "public_safe": public_safe,
            "privacy_violations": privacy_violations,
        },
        "predecessor_blockers": dependency["predecessor_blockers"],
        "predecessor_blocker_count": predecessor_count,
        "execution_frontier": dependency["execution_frontier"],
        "missing_external_outcomes": missing,
        "p14_missing_count": p14_missing_count,
        "privacy_blocker_count": privacy_blocker_count,
        "missing_count": total_missing,
        "non_claims": [
            "No Omega claim without the passing live program receipt and two unchanged live passes.",
            "No real-demand, client-outcome, operator-outcome, or time-based-cycle claim from fixtures.",
            "No human acceptance is inferred from a pending or absent gate receipt.",
        ],
        "next_terminal_predicate": contract["omega"]["live_predicate"],
    }


def preflight(
    contract: dict[str, Any],
    fixture: object,
    evidence: object,
    ledger: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if ledger is None:
        ledger = load_dependency_ledger(contract=contract)
    fixture_result = run_synthetic(contract, fixture)
    terminal = terminal_report(contract, evidence, ledger)
    if terminal["terminal"]:
        raise P14Error("preflight unexpectedly received terminal live evidence; run the owning live predicates")
    return {
        "schema_version": "limen.positioning_p14_preflight.v1",
        "status": "pass",
        "contract": "valid",
        "synthetic_fixture": fixture_result["status"],
        "predecessor_commands_executed": fixture_result["executed_predecessor_commands"],
        "terminal_status": terminal["status"],
        "predecessor_blockers": terminal["predecessor_blockers"],
        "predecessor_blocker_count": terminal["predecessor_blocker_count"],
        "execution_frontier": terminal["execution_frontier"],
        "missing_external_outcomes": terminal["missing_external_outcomes"],
        "p14_missing_count": terminal["p14_missing_count"],
        "blocking_total": terminal["missing_count"],
        "non_claims": fixture_result["not_evidence_for"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--run-fixture", type=Path, metavar="PATH")
    mode.add_argument("--verify-two-pass", type=Path, metavar="PATH")
    mode.add_argument("--terminal", action="store_true")
    mode.add_argument("--preflight", action="store_true")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--scope", choices=("synthetic", "live"), default="live")
    args = parser.parse_args(argv)
    try:
        contract = load_contract(args.manifest)
        ledger = load_dependency_ledger(args.ledger, contract)
        if args.check:
            result: object = {
                "schema_version": CONTROL_SCHEMA,
                "status": "ok",
                "events": len(contract["events"]),
                "metrics": len(contract["metrics"]),
                "stages": contract["stage_order"],
                "terminal_requirements": len(contract["terminal_requirements"]),
                "predecessor_chunks": len(ledger["predecessor_chunks"]),
                "dependency_blockers": dependency_report(ledger)["predecessor_blocker_count"],
                "execution_frontier": dependency_report(ledger)["execution_frontier"],
                "predecessor_policy": contract["predecessor_policy"],
            }
            exit_code = 0
        elif args.run_fixture:
            result = run_synthetic(contract, _load_json(args.run_fixture))
            exit_code = 0
        elif args.verify_two_pass:
            result = verify_omega_pair(_load_json(args.verify_two_pass), required_scope=args.scope)
            exit_code = 0
        elif args.terminal:
            result = terminal_report(contract, _load_json(args.evidence, missing={}), ledger)
            exit_code = 0 if result["terminal"] else 3
        else:
            result = preflight(
                contract,
                _load_json(DEFAULT_FIXTURE),
                _load_json(args.evidence, missing={}),
                ledger,
            )
            exit_code = 0
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        return exit_code
    except P14Error as exc:
        print(f"positioning-p14-control-plane: BLOCKED — {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
