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

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = ROOT / "institutio" / "positioning" / "p14" / "control-plane.json"
DEFAULT_LEDGER = ROOT / "institutio" / "positioning" / "p14" / "dependency-ledger.json"
DEFAULT_FIXTURE = ROOT / "cli" / "tests" / "fixtures" / "positioning-p14" / "synthetic-cycle.json"
DEFAULT_OPERATIONS = ROOT / "institutio" / "positioning" / "p14" / "operations.json"
DEFAULT_OPERATION_FIXTURE = ROOT / "cli" / "tests" / "fixtures" / "positioning-p14" / "operational-cycle.json"
DEFAULT_EVIDENCE = ROOT / "docs" / "receipts" / "positioning" / "p14" / "live-evidence.json"
PROGRAM_SCRIPT = ROOT / "scripts" / "positioning-program.py"

CONTROL_SCHEMA = "limen.positioning_p14_control_plane.v3"
LEDGER_SCHEMA = "limen.positioning_p14_dependency_ledger.v3"
OPERATIONS_SCHEMA = "limen.positioning_p14_operations.v1"
OPERATION_FIXTURE_SCHEMA = "limen.positioning_p14_operational_fixture.v1"
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
EXPECTED_OPERATION_SCHEMAS = {
    "event_bundle",
    "weekly_review",
    "monthly_audit",
    "quarterly_decision",
    "claim_incident",
    "release_recovery",
    "demand_private_ledger",
    "delivery_private_ledger",
    "operator_private_ledger",
    "evidence_source_bundle",
    "omega_observation",
}
EXPECTED_OPERATION_SCHEMA_PATHS = {
    name: f"institutio/positioning/p14/schemas/{name.replace('_', '-')}.schema.json"
    for name in (
        "event_bundle",
        "weekly_review",
        "monthly_audit",
        "quarterly_decision",
        "claim_incident",
        "release_recovery",
        "evidence_source_bundle",
        "omega_observation",
    )
}
EXPECTED_OPERATION_SCHEMA_PATHS.update(
    {
        "demand_private_ledger": "institutio/positioning/p14/schemas/demand-ledger.private.schema.json",
        "delivery_private_ledger": "institutio/positioning/p14/schemas/delivery-ledger.private.schema.json",
        "operator_private_ledger": "institutio/positioning/p14/schemas/operator-ledger.private.schema.json",
    }
)
EXPECTED_RUNNER_IDS = {
    "collect_metrics",
    "weekly_review",
    "monthly_audit",
    "quarterly_decision",
    "claim_incident",
    "release_recovery",
    "demand_projection",
    "delivery_projection",
    "operator_projection",
    "evidence_envelope",
    "omega_observation",
    "omega_pair",
    "frontiers",
}
EXPECTED_RUNNERS = {
    "collect_metrics": (WORK_IDS[0], "--collect-metrics", "event_bundle", "read_only"),
    "weekly_review": (WORK_IDS[1], "--weekly-review", "weekly_review", "read_only"),
    "monthly_audit": (WORK_IDS[2], "--monthly-audit", "monthly_audit", "read_only"),
    "quarterly_decision": (WORK_IDS[3], "--quarterly-decision", "quarterly_decision", "read_only"),
    "claim_incident": (WORK_IDS[4], "--claim-drill", "claim_incident", "synthetic_temp_only"),
    "release_recovery": (WORK_IDS[5], "--release-drill", "release_recovery", "synthetic_temp_only"),
    "demand_projection": (WORK_IDS[6], "--project-private-ledger", "demand_private_ledger", "read_only"),
    "delivery_projection": (WORK_IDS[7], "--project-private-ledger", "delivery_private_ledger", "read_only"),
    "operator_projection": (WORK_IDS[7], "--project-private-ledger", "operator_private_ledger", "read_only"),
    "evidence_envelope": (WORK_IDS[8], "--build-evidence-envelope", "evidence_source_bundle", "read_only"),
    "omega_observation": (WORK_IDS[8], "--omega-observation", "omega_observation", "read_only"),
    "omega_pair": (WORK_IDS[8], "--assemble-omega-pair", "omega_observation", "read_only"),
    "frontiers": ("PSP-C12", "--frontiers", "dependency_ledger", "read_only"),
}
EXPECTED_TEMPLATE_MARKERS = {
    "weekly": {
        "{{period_start}}",
        "{{scope}}",
        "{{ready_work}}",
        "{{blockers}}",
        "{{qualified_demand_count}}",
        "{{delivery_risks}}",
        "{{evidence_changes}}",
        "{{decision}}",
        "{{owner}}",
        "{{next_predicate}}",
        "{{routed_packet_ids}}",
    },
    "monthly": {
        "{{period_start}}",
        "{{scope}}",
        "{{truth_findings}}",
        "{{link_findings}}",
        "{{privacy_findings}}",
        "{{parity_findings}}",
        "{{correction_packets}}",
        "{{verdict}}",
    },
    "quarterly": {
        "{{period_start}}",
        "{{scope}}",
        "{{conversation_evidence}}",
        "{{funnel_evidence}}",
        "{{delivery_evidence}}",
        "{{claim_evidence}}",
        "{{decision}}",
        "{{truth_finding}}",
        "{{prominence_finding}}",
        "{{prior_strategy_version}}",
        "{{proposed_strategy_version}}",
        "{{owner}}",
        "{{next_experiment}}",
    },
}
PREPARATION_CHUNK_IDS = tuple(f"PSP-C{number:02d}" for number in range(4, 13))
PREPARATION_OWNERS = {
    "PSP-C04": (2313, "codex/psp-c04-proof-experience-preflight"),
    "PSP-C05": (2315, "codex/psp-c05-delivery-os-preflight-relay"),
    "PSP-C06": (2317, "codex/psp-c06-public-surfaces-relay"),
    "PSP-C07": (2318, "codex/psp-c07-private-inbound-preflight"),
    "PSP-C08": (2316, "codex/psp-c08-proof-led-content-preflight"),
    "PSP-C09": (2322, "codex/psp-c09-qualification-conversion-relay"),
    "PSP-C10": (2321, "codex/psp-c10-readiness-preflight"),
    "PSP-C11": (2319, "codex/psp-c11-governed-foundry-preflight"),
    "PSP-C12": (2320, "codex/psp-c12-control-plane-preflight"),
}
ASSIGNMENT_POLICY = {
    "selection": "runtime_catalog",
    "registry": "institutio/positioning/program.yaml",
    "catalog_predicate": "python3 scripts/positioning-program.py --verify-model-assignments",
    "unavailable_action": "fail_blocked_no_silent_substitution",
}
EXPECTED_LEDGER_KEYS = {
    "schema_version",
    "observed_at",
    "authoritative_registry",
    "program_repository",
    "counts_as_closure",
    "closed_baseline",
    "phase_ownership",
    "predecessor_chunks",
    "preparation_owners",
    "p14_stages",
    "terminal_nodes",
    "assignment_policy",
    "p14_assignment_requirement",
}


class P14Error(RuntimeError):
    """Raised when a preflight contract or fixture fails closed."""


def _load_json(path: Path, *, missing: object | None = None) -> Any:
    if missing is not None and not path.exists():
        return missing

    def object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise P14Error(f"duplicate JSON member: {key}")
            value[key] = item
        return value

    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=object_without_duplicate_keys,
        )
    except (OSError, json.JSONDecodeError, P14Error) as exc:
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


def _chunk_assignment_requirement(
    chunk_id: str,
    graph: dict[str, Any],
    program: dict[str, Any],
) -> dict[str, Any]:
    assignment = program["chunk_assignment_for"](chunk_id, graph)
    return {
        "selection": "runtime_catalog",
        "role": "chunk_conductor",
        "effort": assignment["effort"],
        "capabilities": sorted(
            {
                capability
                for work_id in graph["chunk_work"][chunk_id]
                for capability in graph["work_by_id"][work_id]["capabilities"]
            }
        ),
    }


def _work_assignment_requirement(
    work_id: str,
    graph: dict[str, Any],
    program: dict[str, Any],
) -> dict[str, Any]:
    packet = graph["work_by_id"][work_id]
    assignment = program["model_assignment_for"](work_id, graph)
    return {
        "selection": "runtime_catalog",
        "reasoning": packet["reasoning"],
        "effect": packet["effect"],
        "effort": assignment["effort"],
        "capabilities": packet["capabilities"],
    }


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


def _schema_path(operations: dict[str, Any], schema_name: str) -> Path:
    raw_path = _text(
        _mapping(operations.get("schemas"), "operations.schemas").get(schema_name),
        f"operations.schemas.{schema_name}",
    )
    path = (ROOT / raw_path).resolve()
    try:
        path.relative_to(ROOT)
    except ValueError as exc:
        raise P14Error(f"operations schema path escapes the repository: {raw_path}") from exc
    return path


def _validate_named_schema(operations: dict[str, Any], schema_name: str, value: object) -> dict[str, Any]:
    schema = _load_json(_schema_path(operations, schema_name))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(value), key=lambda item: tuple(str(part) for part in item.absolute_path))
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        raise P14Error(f"{schema_name} schema violation at {location}: {error.message}")
    return _mapping(value, schema_name)


def _require_live_receipt(value: dict[str, Any], *, label: str, field: str = "evidence_url") -> None:
    if value.get("scope") == "live" and not _is_url(value.get(field)):
        raise P14Error(f"{label} live scope requires an HTTPS {field}")


def _require_single_scope(parent: dict[str, Any], records: list[Any], *, label: str) -> str:
    scope = _text(parent.get("scope"), f"{label}.scope")
    if scope not in {"synthetic", "live"}:
        raise P14Error(f"{label}.scope must be synthetic or live")
    for index, raw in enumerate(records):
        record = _mapping(raw, f"{label}[{index}]")
        if record.get("scope") != scope:
            raise P14Error(f"{label}[{index}] scope differs from its parent {scope} scope")
    return scope


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


def validate_operations_contract(value: object) -> dict[str, Any]:
    operations = _mapping(value, "operations")
    if operations.get("schema_version") != OPERATIONS_SCHEMA:
        raise P14Error(f"operations schema_version must be {OPERATIONS_SCHEMA}")
    if operations.get("control_plane_schema_version") != CONTROL_SCHEMA:
        raise P14Error("operations must bind the current control-plane schema")
    if operations.get("counts_as_closure") is not False:
        raise P14Error("operational preparation must not count as closure")

    separation = _mapping(operations.get("scope_separation"), "operations.scope_separation")
    if (
        separation.get("allowed_scopes") != ["synthetic", "live"]
        or separation.get("require_single_scope_per_input") is not True
        or separation.get("synthetic_counts_as_live") is not False
    ):
        raise P14Error("operations synthetic/live separation contract drift")
    forbidden = set(_list(separation.get("synthetic_may_not_satisfy"), "synthetic_may_not_satisfy"))
    if not {"Omega", "real demand", "completed weekly, monthly, or quarterly cycles"}.issubset(forbidden):
        raise P14Error("operations synthetic non-claims are incomplete")

    schemas = _mapping(operations.get("schemas"), "operations.schemas")
    if set(schemas) != EXPECTED_OPERATION_SCHEMAS:
        raise P14Error("operations schema inventory drift")
    if schemas != EXPECTED_OPERATION_SCHEMA_PATHS:
        raise P14Error("operations schema path mapping drift")
    for schema_name in sorted(schemas):
        schema = _load_json(_schema_path(operations, schema_name))
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:
            raise P14Error(f"operations schema {schema_name} is invalid: {exc}") from exc

    templates = _mapping(operations.get("templates"), "operations.templates")
    if set(templates) != {"weekly", "monthly", "quarterly"}:
        raise P14Error("operations review template inventory drift")
    for name, raw in templates.items():
        template = _mapping(raw, f"operations.templates.{name}")
        path = (ROOT / _text(template.get("path"), f"operations.templates.{name}.path")).resolve()
        try:
            path.relative_to(ROOT)
            body = path.read_text(encoding="utf-8")
        except (ValueError, OSError) as exc:
            raise P14Error(f"cannot load {name} review template: {exc}") from exc
        markers = _list(template.get("required_markers"), f"operations.templates.{name}.required_markers")
        if set(markers) != EXPECTED_TEMPLATE_MARKERS[name] or len(markers) != len(set(markers)):
            raise P14Error(f"{name} review template marker contract drift")
        missing = [marker for marker in markers if marker not in body]
        if missing:
            raise P14Error(f"{name} review template is missing markers: {missing}")
        unresolved = set(re.findall(r"\{\{[a-z0-9_]+\}\}", body)) - set(markers)
        if unresolved:
            raise P14Error(f"{name} review template has ungoverned markers: {sorted(unresolved)}")

    runners = _list(operations.get("runners"), "operations.runners", nonempty=True)
    runner_ids: set[str] = set()
    for index, raw in enumerate(runners):
        runner = _mapping(raw, f"operations.runners[{index}]")
        runner_id = _text(runner.get("id"), f"operations.runners[{index}].id")
        if runner_id in runner_ids:
            raise P14Error(f"duplicate operations runner id: {runner_id}")
        runner_ids.add(runner_id)
        if runner.get("counts_as_closure") is not False:
            raise P14Error(f"operations runner {runner_id} must not count as closure")
        if runner.get("effect_scope") not in {"read_only", "synthetic_temp_only"}:
            raise P14Error(f"operations runner {runner_id} effect scope is not reversible")
        _text(runner.get("mode"), f"operations runner {runner_id}.mode")
        work_id = _text(runner.get("work_id"), f"operations runner {runner_id}.work_id")
        if work_id not in {*WORK_IDS, "PSP-C12"}:
            raise P14Error(f"operations runner {runner_id} has an unknown work id")
        input_schema = _text(runner.get("input_schema"), f"operations runner {runner_id}.input_schema")
        if input_schema != "dependency_ledger" and input_schema not in schemas:
            raise P14Error(f"operations runner {runner_id} has an unknown input schema")
        expected = EXPECTED_RUNNERS.get(runner_id)
        observed = (work_id, runner.get("mode"), input_schema, runner.get("effect_scope"))
        if expected != observed:
            raise P14Error(f"operations runner {runner_id} mapping drift")
        expected_kind = {
            "demand_projection": "demand",
            "delivery_projection": "delivery",
            "operator_projection": "operator",
        }.get(runner_id)
        if expected_kind is not None and runner.get("ledger_kind") != expected_kind:
            raise P14Error(f"operations runner {runner_id} ledger kind drift")
        if runner_id == "omega_pair" and runner.get("input_cardinality") != 2:
            raise P14Error("Omega pair runner must require exactly two observations")
    if runner_ids != EXPECTED_RUNNER_IDS:
        raise P14Error("operations runner inventory drift")

    rollback = _mapping(operations.get("rollback_invariants"), "operations.rollback_invariants")
    if not rollback or any(value is not True for value in rollback.values()):
        raise P14Error("every operational rollback invariant must be enabled")
    return operations


def load_operations(path: Path = DEFAULT_OPERATIONS) -> dict[str, Any]:
    return validate_operations_contract(_load_json(path))


def validate_dependency_ledger(value: object, contract: dict[str, Any]) -> dict[str, Any]:
    ledger = _mapping(value, "dependency ledger")
    if set(ledger) != EXPECTED_LEDGER_KEYS:
        raise P14Error("dependency ledger must use the exact public-safe root schema")
    if ledger.get("schema_version") != LEDGER_SCHEMA:
        raise P14Error(f"dependency ledger schema_version must be {LEDGER_SCHEMA}")
    if ledger.get("authoritative_registry") != "institutio/positioning/program.yaml":
        raise P14Error("dependency ledger must bind the canonical program registry")
    if ledger.get("program_repository") != "organvm/limen":
        raise P14Error("dependency ledger repository drift")
    if ledger.get("counts_as_closure") is not False:
        raise P14Error("dependency ledger preparation must not count as closure")
    if ledger.get("assignment_policy") != ASSIGNMENT_POLICY:
        raise P14Error("dependency ledger assignment policy drift")
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
        expected_requirement = _chunk_assignment_requirement(chunk_id, graph, program)
        if row.get("assignment_requirement") != expected_requirement:
            raise P14Error(f"{chunk_id} runtime assignment requirement drift")
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
            if not HEAD_RE.fullmatch(str(receipt.get("source_head") or "")):
                raise P14Error(f"{chunk_id} evidence source_head must be an exact commit")
            if not HEAD_RE.fullmatch(str(receipt.get("integrated_main_head") or "")):
                raise P14Error(f"{chunk_id} evidence integrated_main_head must be an exact commit")
        frontier = _list(row.get("frontier_work"), f"{chunk_id}.frontier_work")
        if chunk_id == "PSP-C03":
            if len(frontier) != 1:
                raise P14Error("C03 must expose exactly the current W07 reader frontier")
            reader = _mapping(frontier[0], "C03 frontier work")
            expected_requirement = _work_assignment_requirement("PSP-P03-W07", graph, program)
            if (
                reader.get("work_id") != "PSP-P03-W07"
                or reader.get("issue") != mapping["issues"]["PSP-P03-W07"]["url"]
                or reader.get("state") != "open"
                or reader.get("assignment_requirement") != expected_requirement
            ):
                raise P14Error("C03 reader frontier drift")
            _text(reader.get("acceptance_boundary"), "C03 reader frontier acceptance_boundary")
            if not HEAD_RE.fullmatch(str(row.get("accepted_checkpoint") or "")):
                raise P14Error("C03 accepted checkpoint must be an exact commit")
        elif frontier:
            raise P14Error(f"{chunk_id} must not invent a frontier ahead of C03")
    if tuple(chunk_ids) != PREDECESSOR_CHUNK_IDS:
        raise P14Error("predecessor chunks must remain in canonical C03-C11 order")

    predecessor_limen_heads: dict[str, dict[str, str]] = {}
    for raw in raw_chunks:
        row = _mapping(raw, "predecessor chunk")
        chunk_id = _text(row.get("chunk_id"), "predecessor chunk id")
        for raw_evidence in _list(row.get("evidence"), f"{chunk_id}.evidence", nonempty=True):
            evidence = _mapping(raw_evidence, f"{chunk_id}.evidence")
            if evidence.get("target") == "limen":
                predecessor_limen_heads[chunk_id] = {
                    "source_head": _text(evidence.get("source_head"), f"{chunk_id}.limen source_head"),
                    "integrated_main_head": _text(
                        evidence.get("integrated_main_head"),
                        f"{chunk_id}.limen integrated_main_head",
                    ),
                }
                break

    preparation_owners = _list(ledger.get("preparation_owners"), "dependency ledger preparation_owners")
    owner_chunk_ids: list[str] = []
    for index, raw in enumerate(preparation_owners):
        owner = _mapping(raw, f"preparation_owners[{index}]")
        chunk_id = _text(owner.get("chunk_id"), f"preparation_owners[{index}].chunk_id")
        owner_chunk_ids.append(chunk_id)
        if chunk_id not in PREPARATION_OWNERS:
            raise P14Error(f"unexpected reversible preparation owner {chunk_id}")
        pull_request, branch = PREPARATION_OWNERS[chunk_id]
        if (
            owner.get("repository") != "organvm/limen"
            or owner.get("branch") != branch
            or owner.get("pull_request") != pull_request
            or owner.get("pull_request_url") != f"https://github.com/organvm/limen/pull/{pull_request}"
            or owner.get("effect_scope") != "repository_reversible"
            or owner.get("counts_as_closure") is not False
        ):
            raise P14Error(f"{chunk_id} reversible preparation owner drift")
        expected_state = "open" if chunk_id == "PSP-C12" else "merged"
        expected_draft = True if chunk_id == "PSP-C12" else False
        if owner.get("state") != expected_state or owner.get("draft") != expected_draft:
            raise P14Error(f"{chunk_id} reversible preparation owner lifecycle drift")
        _list(owner.get("reversible_actions"), f"{chunk_id}.reversible_actions", nonempty=True)
        if chunk_id == "PSP-C12":
            if owner.get("head_binding") != "runtime_exact_head" or "observed_head" in owner:
                raise P14Error("C12 preparation owner must bind its runtime exact head without self-reference")
        elif not HEAD_RE.fullmatch(str(owner.get("source_head") or "")) or not HEAD_RE.fullmatch(
            str(owner.get("integrated_main_head") or "")
        ):
            raise P14Error(f"{chunk_id} preparation owner must bind exact source and integrated heads")
        elif {
            "source_head": owner["source_head"],
            "integrated_main_head": owner["integrated_main_head"],
        } != predecessor_limen_heads.get(chunk_id):
            raise P14Error(f"{chunk_id} preparation owner heads must match predecessor evidence")
    if tuple(owner_chunk_ids) != PREPARATION_CHUNK_IDS:
        raise P14Error("reversible preparation owners must remain in canonical C04-C12 order")

    expected_p14_requirement = _chunk_assignment_requirement("PSP-C12", graph, program)
    if ledger.get("p14_assignment_requirement") != expected_p14_requirement:
        raise P14Error("P14 runtime assignment requirement drift")
    p14_stages = _list(ledger.get("p14_stages"), "dependency ledger p14_stages")
    if len(p14_stages) != len(WORK_IDS):
        raise P14Error("dependency ledger must contain all nine P14 stages")
    for index, work_id in enumerate(WORK_IDS):
        row = _mapping(p14_stages[index], f"p14_stages[{index}]")
        packet = graph["work_by_id"][work_id]
        assignment_requirement = _work_assignment_requirement(work_id, graph, program)
        if (
            row.get("work_id") != work_id
            or row.get("issue") != mapping["issues"][work_id]["url"]
            or row.get("depends_on") != packet["depends_on"]
            or row.get("assignment_requirement") != assignment_requirement
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
    formal_frontier: list[dict[str, Any]] = []
    for row in ledger["predecessor_chunks"]:
        if row["closure_state"] != "closed" and row["frontier_work"]:
            formal_frontier = deepcopy(row["frontier_work"])
            break
    reversible_frontier = [
        {
            "chunk_id": owner["chunk_id"],
            "repository": owner["repository"],
            "branch": owner["branch"],
            "pull_request": owner["pull_request"],
            "pull_request_url": owner["pull_request_url"],
            "state": owner["state"],
            "draft": owner["draft"],
            "source_head": owner.get("source_head"),
            "integrated_main_head": owner.get("integrated_main_head"),
            "head_binding": owner.get("head_binding"),
            "effect_scope": owner["effect_scope"],
            "reversible_actions": deepcopy(owner["reversible_actions"]),
            "counts_as_closure": False,
        }
        for owner in ledger["preparation_owners"]
    ]
    if formal_frontier and not reversible_frontier:
        raise P14Error("formal execution blockage must not empty the independent reversible preparation frontier")
    return {
        "status": "blocked" if blockers else "pass",
        "predecessor_chunk_count": len(ledger["predecessor_chunks"]),
        "predecessor_blocker_count": len(blockers),
        "predecessor_blockers": blockers,
        "formal_execution_frontier": formal_frontier,
        "execution_frontier": formal_frontier,
        "reversible_preparation_frontier": reversible_frontier,
        "frontier_invariant": {
            "independent": True,
            "formal_gate_suppresses_reversible_preparation": False,
            "owner_branches_or_pull_requests_count_as_closure": False,
        },
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
    operations_contract = _mapping(contract.get("operations"), "operations")
    if (
        operations_contract.get("path") != "institutio/positioning/p14/operations.json"
        or operations_contract.get("schema_version") != OPERATIONS_SCHEMA
        or operations_contract.get("fixture_path") != "cli/tests/fixtures/positioning-p14/operational-cycle.json"
        or operations_contract.get("counts_as_closure") is not False
    ):
        raise P14Error("operations contract drift")
    frontier_policy = _mapping(contract.get("frontier_policy"), "frontier_policy")
    if (
        frontier_policy.get("frontiers_are_independent") is not True
        or frontier_policy.get("formal_gate_must_not_empty_reversible_frontier") is not True
        or frontier_policy.get("allowed_preparation_effect_scope") != "repository_reversible"
        or set(frontier_policy.get("non_closure_signals") or [])
        != {
            "preflight",
            "prepared",
            "draft_pull_request",
            "green_ci",
            "synthetic_fixture",
            "generated_visual_direction",
        }
    ):
        raise P14Error("formal/reversible frontier policy drift")
    _text(frontier_policy.get("formal_execution_frontier"), "frontier_policy.formal_execution_frontier")
    _text(
        frontier_policy.get("reversible_preparation_frontier"),
        "frontier_policy.reversible_preparation_frontier",
    )
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
    minimum_repositories = release_recovery.get("minimum_repositories")
    if not isinstance(minimum_repositories, int) or isinstance(minimum_repositories, bool) or minimum_repositories < 2:
        raise P14Error("release_recovery.minimum_repositories must be at least two")

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
            if "minimum_repositories" in requirement:
                minimum_repositories = requirement["minimum_repositories"]
                if (
                    not isinstance(minimum_repositories, int)
                    or isinstance(minimum_repositories, bool)
                    or minimum_repositories < 2
                ):
                    raise P14Error(f"{code}.minimum_repositories must be at least two")
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


def collect_metrics(
    contract: dict[str, Any],
    operations: dict[str, Any],
    value: object,
) -> dict[str, Any]:
    bundle = _validate_named_schema(operations, "event_bundle", value)
    events = _list(bundle.get("events"), "event_bundle.events", nonempty=True)
    scope = _require_single_scope(bundle, events, label="event_bundle.events")
    declared = {event["type"]: event for event in contract["events"]}
    counts = {event_type: 0 for event_type in declared}
    entities = {event_type: set() for event_type in declared}
    seen_ids: set[str] = set()
    for index, raw in enumerate(events):
        event = _mapping(raw, f"event_bundle.events[{index}]")
        event_id = _text(event.get("event_id"), f"event_bundle.events[{index}].event_id")
        if event_id in seen_ids:
            raise P14Error(f"duplicate event bundle event id: {event_id}")
        seen_ids.add(event_id)
        event_type = _text(event.get("type"), f"event_bundle.events[{index}].type")
        if event_type not in declared:
            raise P14Error(f"event bundle type is not declared: {event_type}")
        if scope == "live" and not _is_url(event.get("source_receipt_url")):
            raise P14Error(f"live event {event_id} requires an HTTPS source_receipt_url")
        counts[event_type] += 1
        entities[event_type].add(_text(event.get("entity_id"), f"event bundle {event_id}.entity_id"))

    metrics: dict[str, Any] = {}
    for metric in contract["metrics"]:
        numerator = counts[metric["numerator_event"]]
        denominator = counts[metric["denominator_event"]]
        if denominator < metric["minimum_denominator"]:
            raise P14Error(f"metric {metric['id']} denominator {denominator} is below {metric['minimum_denominator']}")
        orphan_numerators = sorted(entities[metric["numerator_event"]] - entities[metric["denominator_event"]])
        if orphan_numerators or numerator > denominator:
            raise P14Error(
                f"metric {metric['id']} numerator is not a subset of its denominator entities: {orphan_numerators}"
            )
        metrics[metric["id"]] = {
            "numerator": numerator,
            "denominator": denominator,
            "value": numerator / denominator,
            "numerator_event": metric["numerator_event"],
            "denominator_event": metric["denominator_event"],
            "source": {
                "numerator": declared[metric["numerator_event"]]["source"],
                "denominator": declared[metric["denominator_event"]]["source"],
            },
            "owner": metric["owner"],
            "cadence": metric["cadence"],
            "decision_use": metric["decision_use"],
            "guardrail": metric["guardrail"],
            "scope": scope,
        }
    return {
        "schema_version": "limen.positioning_p14_metric_snapshot.v1",
        "status": "pass",
        "scope": scope,
        "event_counts": counts,
        "metrics": metrics,
        "source_event_count": len(events),
        "source_digest": _canonical_digest(bundle),
        "source_scope_live": scope == "live",
        "counts_as_live_outcomes": False,
        "counts_as_terminal_evidence": False,
        "counts_as_closure": False,
    }


def run_weekly_review(operations: dict[str, Any], value: object) -> dict[str, Any]:
    review = _validate_named_schema(operations, "weekly_review", value)
    _require_live_receipt(review, label="weekly review")
    start = _period_date(review.get("period_start"))
    end = _period_date(review.get("period_end"))
    if start is None or end is None or (end - start).days != 6:
        raise P14Error("weekly review must cover one inclusive seven-day period")
    ready = [_mapping(row, "weekly ready work") for row in review["ready_work"]]
    ready_ids = [_text(row.get("work_id"), "weekly ready work id") for row in ready]
    closed_ids = set(review["closed_work_ids"])
    if len(set(ready_ids)) != len(ready_ids):
        raise P14Error("weekly review contains duplicate ready work")
    overlap = sorted(set(ready_ids) & closed_ids)
    if overlap:
        raise P14Error(f"weekly review would replay already-closed work: {overlap}")
    decision = _mapping(review["decision"], "weekly review decision")
    routed = decision["routed_packet_ids"]
    if decision["action"] == "route" and not routed:
        raise P14Error("weekly route decision requires a routed packet id")
    if len(set(routed)) != len(routed):
        raise P14Error("weekly review contains duplicate routed packets")
    result = {
        "schema_version": "limen.positioning_p14_weekly_review_receipt.v1",
        "status": "pass",
        "scope": review["scope"],
        "period_start": review["period_start"],
        "period_end": review["period_end"],
        "decision": decision["action"],
        "owner": decision["owner"],
        "next_predicate": decision["next_predicate"],
        "ready_work": ready,
        "blockers": deepcopy(review["blockers"]),
        "qualified_demand_count": review["qualified_demand_count"],
        "delivery_risks": deepcopy(review["delivery_risks"]),
        "evidence_changes": deepcopy(review["evidence_changes"]),
        "routed_packet_ids": deepcopy(routed),
        "source_scope_live": review["scope"] == "live",
        "counts_as_live_cycle": False,
        "counts_as_terminal_evidence": False,
        "counts_as_closure": False,
    }
    if "evidence_url" in review:
        result["evidence_url"] = review["evidence_url"]
    return result


def run_monthly_audit(operations: dict[str, Any], value: object) -> dict[str, Any]:
    audit = _validate_named_schema(operations, "monthly_audit", value)
    _require_live_receipt(audit, label="monthly audit")
    findings = _mapping(audit["findings"], "monthly audit findings")
    all_findings: dict[str, tuple[str, dict[str, Any]]] = {}
    unowned = {"truth": 0, "links": 0, "privacy": 0, "parity": 0}
    for category, rows in findings.items():
        for raw in rows:
            finding = _mapping(raw, f"monthly {category} finding")
            finding_id = _text(finding.get("finding_id"), f"monthly {category} finding_id")
            if finding_id in all_findings:
                raise P14Error(f"duplicate monthly finding id: {finding_id}")
            all_findings[finding_id] = (category, finding)
            if finding["status"] != "pass" and (
                not _meaningful(finding.get("owner")) or not _meaningful(finding.get("next_predicate"))
            ):
                unowned[category] += 1
    corrections: dict[str, dict[str, Any]] = {}
    for raw in audit["correction_packets"]:
        correction = _mapping(raw, "monthly correction packet")
        finding_id = _text(correction.get("finding_id"), "monthly correction finding_id")
        if finding_id in corrections:
            raise P14Error(f"duplicate monthly correction packet: {finding_id}")
        if finding_id not in all_findings or all_findings[finding_id][1]["status"] == "pass":
            raise P14Error(f"monthly correction packet has no failing finding: {finding_id}")
        finding = all_findings[finding_id][1]
        if correction["owner"] != finding.get("owner") or correction["next_predicate"] != finding.get("next_predicate"):
            raise P14Error(f"monthly correction packet does not preserve owner and predicate: {finding_id}")
        corrections[finding_id] = correction
    missing_packets = sorted(
        finding_id
        for finding_id, (_, finding) in all_findings.items()
        if finding["status"] != "pass" and _meaningful(finding.get("owner")) and finding_id not in corrections
    )
    if missing_packets:
        raise P14Error(f"monthly failing findings lack correction packets: {missing_packets}")
    result = {
        "schema_version": "limen.positioning_p14_monthly_audit_receipt.v1",
        "status": "pass",
        "scope": audit["scope"],
        "period_start": audit["period_start"],
        "verdict": "pass" if sum(unowned.values()) == 0 else "blocked",
        "unowned_stale_claims": unowned["truth"],
        "unowned_broken_links": unowned["links"],
        "unowned_private_leaks": unowned["privacy"],
        "unowned_surface_parity_defects": unowned["parity"],
        "finding_count": len(all_findings),
        "correction_packets": deepcopy(audit["correction_packets"]),
        "source_scope_live": audit["scope"] == "live",
        "counts_as_live_cycle": False,
        "counts_as_terminal_evidence": False,
        "counts_as_closure": False,
    }
    if "evidence_url" in audit:
        result["evidence_url"] = audit["evidence_url"]
    return result


def run_quarterly_decision(operations: dict[str, Any], value: object) -> dict[str, Any]:
    review = _validate_named_schema(operations, "quarterly_decision", value)
    _require_live_receipt(review, label="quarterly decision")
    if review["decision"] == "keep":
        if review["prior_strategy_version"] != review["proposed_strategy_version"]:
            raise P14Error("quarterly keep decision must preserve the strategy version")
    elif review["prior_strategy_version"] == review["proposed_strategy_version"]:
        raise P14Error("quarterly strategy change must use a distinct proposed version")
    evidence = review["evidence"]
    result = {
        "schema_version": "limen.positioning_p14_quarterly_decision_receipt.v1",
        "status": "pass",
        "scope": review["scope"],
        "period_start": review["period_start"],
        "conversation_evidence": deepcopy(evidence["conversation"]),
        "funnel_evidence": deepcopy(evidence["funnel"]),
        "delivery_evidence": deepcopy(evidence["delivery"]),
        "claim_evidence": deepcopy(evidence["claim"]),
        "decision": review["decision"],
        "truth_finding": review["truth_finding"],
        "prominence_finding": review["prominence_finding"],
        "next_experiment": review["next_experiment"],
        "owner": review["owner"],
        "prior_strategy_version": review["prior_strategy_version"],
        "proposed_strategy_version": review["proposed_strategy_version"],
        "source_scope_live": review["scope"] == "live",
        "counts_as_live_cycle": False,
        "counts_as_terminal_evidence": False,
        "counts_as_closure": False,
    }
    if "evidence_url" in review:
        result["evidence_url"] = review["evidence_url"]
    return result


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
        "counts_as_terminal_evidence": False,
        "counts_as_closure": False,
    }


def _release_recovery_result(contract: dict[str, Any], fixture: dict[str, Any]) -> dict[str, Any]:
    recovery = _mapping(fixture.get("release_recovery"), "fixture.release_recovery")
    required_health = contract["release_recovery"]["required_health"]
    minimum_repositories = contract["release_recovery"]["minimum_repositories"]
    if "repositories" in recovery:
        repository_rows = [_mapping(row, "release repository") for row in recovery["repositories"]]
    else:
        repository_ids = _list(recovery.get("resolved_repositories"), "resolved_repositories", nonempty=True)
        repository_rows = [
            {
                "repository_id": repository_id,
                "before_release_id": recovery.get("before_release_id"),
                "bad_release_id": recovery.get("bad_release_id"),
                "restored_release_id": recovery.get("restored_release_id"),
                "health_checks": recovery.get("health_checks"),
                "capture_owner_before": recovery.get("capture_owner_before"),
                "capture_owner_after": recovery.get("capture_owner_after"),
            }
            for repository_id in repository_ids
        ]
    if len(repository_rows) < minimum_repositories:
        raise P14Error(f"release drill must cover at least {minimum_repositories} repositories")
    repository_ids: list[str] = []
    before_ids: list[str] = []
    bad_ids: list[str] = []
    restored_ids: list[str] = []
    health_checks: dict[str, str] = {}
    normalized_rows: list[dict[str, Any]] = []
    for index, row in enumerate(repository_rows):
        repository_id = _text(row.get("repository_id"), f"release repositories[{index}].repository_id")
        before = _text(row.get("before_release_id"), f"{repository_id}.before_release_id")
        bad = _text(row.get("bad_release_id"), f"{repository_id}.bad_release_id")
        restored = _text(row.get("restored_release_id"), f"{repository_id}.restored_release_id")
        if len({before, bad}) != 2 or restored != before:
            raise P14Error(f"release drill must exactly restore {repository_id}'s distinct known-green release")
        checks = _mapping(row.get("health_checks"), f"{repository_id}.health_checks")
        if not checks or any(value not in {required_health, "pass"} for value in checks.values()):
            raise P14Error(f"all {repository_id} release health checks must be {required_health} or pass")
        owner_before = _text(row.get("capture_owner_before"), f"{repository_id}.capture_owner_before")
        owner_after = _text(row.get("capture_owner_after"), f"{repository_id}.capture_owner_after")
        if owner_before != owner_after:
            raise P14Error(f"release rollback changed {repository_id} capture ownership")
        if repository_id in repository_ids:
            raise P14Error(f"duplicate release recovery repository: {repository_id}")
        repository_ids.append(repository_id)
        before_ids.append(before)
        bad_ids.append(bad)
        restored_ids.append(restored)
        for name, status in checks.items():
            health_checks[f"{repository_id}:{name}"] = status
        normalized_rows.append(
            {
                "repository_id": repository_id,
                "before_release_id": before,
                "bad_release_id": bad,
                "restored_release_id": restored,
                "health_checks": deepcopy(checks),
                "capture_owner": owner_before,
            }
        )
    return {
        "status": "synthetic-pass",
        "scope": "synthetic",
        "resolved_repositories": repository_ids,
        "repositories": normalized_rows,
        "before_release_ids": before_ids,
        "bad_release_ids": bad_ids,
        "restored_release_ids": restored_ids,
        "health_checks": health_checks,
        "capture_continuity": True,
        "counts_as_terminal_evidence": False,
        "counts_as_closure": False,
    }


def run_claim_incident(contract: dict[str, Any], operations: dict[str, Any], value: object) -> dict[str, Any]:
    incident = _validate_named_schema(operations, "claim_incident", value)
    return _claim_incident_result(contract, {"claim_incident": incident})


def run_release_recovery(contract: dict[str, Any], operations: dict[str, Any], value: object) -> dict[str, Any]:
    recovery = _validate_named_schema(operations, "release_recovery", value)
    return _release_recovery_result(contract, {"release_recovery": recovery})


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


def project_private_ledger(operations: dict[str, Any], ledger_kind: str, value: object) -> dict[str, Any]:
    schema_names = {
        "demand": "demand_private_ledger",
        "delivery": "delivery_private_ledger",
        "operator": "operator_private_ledger",
    }
    if ledger_kind not in schema_names:
        raise P14Error(f"private ledger kind must be one of {sorted(schema_names)}")
    ledger = _validate_named_schema(operations, schema_names[ledger_kind], value)
    records = _list(ledger.get("records"), f"{ledger_kind} private ledger records")
    scope = _text(ledger.get("scope"), f"{ledger_kind} private ledger scope")
    seen_ids: set[str] = set()
    projected: list[dict[str, Any]] = []
    excluded = 0
    for index, raw in enumerate(records):
        record = _mapping(raw, f"{ledger_kind} private ledger records[{index}]")
        outcome_id = _text(record.get("outcome_id"), f"{ledger_kind} outcome_id")
        if outcome_id in seen_ids:
            raise P14Error(f"duplicate {ledger_kind} outcome id: {outcome_id}")
        seen_ids.add(outcome_id)
        if scope == "live" and not _is_url(record.get("evidence_url")):
            raise P14Error(f"live {ledger_kind} outcome {outcome_id} requires an HTTPS evidence_url")
        if ledger_kind == "demand":
            if record["eligibility"] != "eligible" or record["qualification"] != "qualified":
                excluded += 1
                continue
            public = {
                "outcome_id": outcome_id,
                "scope": scope,
                "offer_version": record["offer_version"],
                "disposition": record["disposition"],
                "objection_code": record["objection_code"],
                "observed_at": record["observed_at"],
            }
        else:
            public = {
                "outcome_id": outcome_id,
                "scope": scope,
                "result": record["result"],
                "observed_at": record["observed_at"],
                "claim_impact": record["claim_impact"],
                "classification_impact": record["classification_impact"],
                "proof_impact": record["proof_impact"],
            }
        if "evidence_url" in record:
            public["evidence_url"] = record["evidence_url"]
        public["counts_as_terminal_evidence"] = False
        projected.append(public)
    result = {
        "schema_version": f"limen.positioning_p14_{ledger_kind}_public_projection.v1",
        "status": "pass",
        "scope": scope,
        "records": projected,
        "source_count": len(records),
        "projected_count": len(projected),
        "excluded_count": excluded,
        "source_digest": _canonical_digest(ledger),
        "source_scope_live": scope == "live",
        "counts_as_real_outcomes": False,
        "counts_as_terminal_evidence": False,
        "counts_as_closure": False,
    }
    violations = _privacy_violations(
        result,
        EXPECTED_DENY_KEYS
        | {
            "private_identity_ref",
            "private_evidence_ref",
            "private_operator_ref",
        },
    )
    if violations:
        raise P14Error(f"private ledger projection leaked private fields: {violations}")
    return result


def normalize_omega_observation(operations: dict[str, Any], value: object) -> dict[str, Any]:
    observation = _validate_named_schema(operations, "omega_observation", value)
    _require_live_receipt(observation, label="Omega observation")
    scope = observation["scope"]
    program_pass = deepcopy(observation["program_pass"])
    # Validate the canonical pass fields without pretending one observation is a pair.
    record = program_pass
    if not DIGEST_RE.fullmatch(str(record.get("state_digest") or "")) or not _is_rfc3339(record.get("observed_at")):
        raise P14Error("Omega observation pass digest or timestamp is invalid")
    if scope == "live":
        missing = [field for field in ("ok", "parity", "open", "verified_receipts", "failures") if field not in record]
        if missing:
            raise P14Error(f"Omega observation is missing canonical live fields: {missing}")
        if record.get("ok") is not True or record.get("open") != [] or record.get("failures") != []:
            raise P14Error("Omega observation is not a clean canonical live pass")
        parity = _mapping(record.get("parity"), "Omega observation parity")
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
            raise P14Error("Omega observation parity is incomplete or drifted")
        verified = record.get("verified_receipts")
        if not isinstance(verified, int) or isinstance(verified, bool) or verified < 1:
            raise P14Error("Omega observation verified_receipts must be positive")
    return {
        "schema_version": "limen.positioning_p14_omega_observation_receipt.v1",
        "status": "pass",
        "scope": scope,
        "observed_head": observation["observed_head"],
        "program_pass": program_pass,
        "evidence_url": observation.get("evidence_url"),
        "counts_as_omega_pair": False,
        "counts_as_terminal_evidence": False,
        "counts_as_closure": False,
    }


def assemble_omega_pair(operations: dict[str, Any], values: list[object]) -> dict[str, Any]:
    if len(values) != 2:
        raise P14Error("Omega pair assembly requires exactly two observations")
    observations = [normalize_omega_observation(operations, value) for value in values]
    scopes = {item["scope"] for item in observations}
    heads = {item["observed_head"] for item in observations}
    if len(scopes) != 1:
        raise P14Error("Omega observation scopes differ")
    if len(heads) != 1:
        raise P14Error("Omega observations do not bind one unchanged exact head")
    scope = observations[0]["scope"]
    passes = [item["program_pass"] for item in observations]
    if [item.get("pass") for item in passes] != [1, 2]:
        raise P14Error("Omega observations must be supplied in pass-1 then pass-2 order")
    pair: dict[str, Any] = {
        "schema_version": PAIR_SCHEMA,
        "scope": scope,
        "observed_head": observations[0]["observed_head"],
        "passes": passes,
    }
    if scope == "live":
        pair["evidence_urls"] = [item["evidence_url"] for item in observations]
    verified = verify_omega_pair(pair, required_scope=scope)
    return {
        **verified,
        "schema_version": "limen.positioning_p14_omega_pair_receipt.v1",
        "observed_head": observations[0]["observed_head"],
        "pair": pair,
        "source_scope_live": scope == "live",
        "counts_as_live_omega": False,
        "counts_as_terminal_evidence": False,
        "counts_as_closure": False,
    }


def build_evidence_envelope(contract: dict[str, Any], operations: dict[str, Any], value: object) -> dict[str, Any]:
    source = _validate_named_schema(operations, "evidence_source_bundle", value)
    scope = source["scope"]
    observed_head = source["observed_head"]
    ledgers = _mapping(source["private_ledgers"], "evidence source private_ledgers")
    projections = {
        kind: project_private_ledger(operations, kind, ledgers[kind]) for kind in ("demand", "delivery", "operator")
    }
    if any(projection["scope"] != scope for projection in projections.values()):
        raise P14Error("evidence envelope mixes synthetic and live private ledgers")
    reviews = _mapping(source["review_receipts"], "evidence source review_receipts")
    for cadence in ("weekly", "monthly", "quarterly"):
        for index, raw in enumerate(_list(reviews[cadence], f"review_receipts.{cadence}")):
            review = _mapping(raw, f"review_receipts.{cadence}[{index}]")
            if review.get("scope") != scope:
                raise P14Error(f"evidence envelope review_receipts.{cadence}[{index}] scope mismatch")
    work_receipts = _mapping(source["work_receipts"], "evidence source work_receipts")
    for work_id, raw in work_receipts.items():
        receipt = _mapping(raw, f"work_receipts.{work_id}")
        if receipt.get("scope") != scope:
            raise P14Error(f"evidence envelope work receipt {work_id} scope mismatch")
        if scope == "live" and receipt.get("exact_head") != observed_head:
            raise P14Error(f"evidence envelope work receipt {work_id} exact head mismatch")
    for field in (
        "claim_incident_drill",
        "release_recovery_drill",
        "demand_decision",
        "commercial_outcome",
        "program_omega",
    ):
        raw = source.get(field)
        if isinstance(raw, dict) and raw.get("scope") != scope:
            raise P14Error(f"evidence envelope {field} scope mismatch")
    for index, raw in enumerate(source.get("portfolio_impacts") or []):
        impact = _mapping(raw, f"portfolio_impacts[{index}]")
        if impact.get("scope") != scope:
            raise P14Error(f"evidence envelope portfolio_impacts[{index}] scope mismatch")
    omega_pair = source.get("omega_pair")
    if isinstance(omega_pair, dict):
        if omega_pair.get("scope") != scope:
            raise P14Error("evidence envelope Omega pair scope mismatch")
        if omega_pair.get("observed_head") != observed_head:
            raise P14Error("evidence envelope Omega pair exact head mismatch")
    program_omega = source.get("program_omega")
    if isinstance(program_omega, dict) and program_omega.get("observed_head") != observed_head:
        raise P14Error("evidence envelope program Omega exact head mismatch")
    envelope: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA,
        "scope": scope,
        "observed_head": observed_head,
        "work_receipts": deepcopy(source["work_receipts"]),
        "review_receipts": deepcopy(source["review_receipts"]),
        "sales_outcomes": deepcopy(projections["demand"]["records"]),
        "delivery_outcomes": deepcopy(projections["delivery"]["records"]),
        "operator_outcomes": deepcopy(projections["operator"]["records"]),
        "counts_as_closure": False,
    }
    passthrough = (
        "claim_incident_drill",
        "release_recovery_drill",
        "demand_decision",
        "commercial_outcome",
        "portfolio_impacts",
        "human_gates",
        "omega_pair",
        "program_omega",
    )
    for field in passthrough:
        if field in source:
            envelope[field] = deepcopy(source[field])
    violations = _privacy_violations(envelope, set(contract["public_evidence_contract"]["deny_keys"]))
    if violations:
        raise P14Error(f"evidence envelope contains denied public fields: {violations}")
    envelope["source_digest"] = _canonical_digest(source)
    envelope["source_scope_live"] = scope == "live"
    envelope["counts_as_live_evidence"] = False
    envelope["counts_as_terminal_evidence"] = False
    return envelope


def run_operational_fixture(contract: dict[str, Any], operations: dict[str, Any], value: object) -> dict[str, Any]:
    fixture = _mapping(value, "operational fixture")
    if fixture.get("schema_version") != OPERATION_FIXTURE_SCHEMA or fixture.get("scope") != "synthetic":
        raise P14Error(f"operational fixture must use {OPERATION_FIXTURE_SCHEMA} with synthetic scope")
    required = {
        "observed_head",
        "event_bundle",
        "weekly_review",
        "monthly_audit",
        "quarterly_decision",
        "claim_incident",
        "release_recovery",
        "private_ledgers",
        "demand_decision",
        "commercial_outcome",
        "portfolio_impacts",
        "human_gates",
        "omega_observations",
    }
    missing = sorted(required - set(fixture))
    if missing:
        raise P14Error(f"operational fixture is missing required fields: {missing}")
    if not HEAD_RE.fullmatch(str(fixture.get("observed_head") or "")):
        raise P14Error("operational fixture observed_head must be an exact commit")
    nested_scope_values: list[tuple[str, object]] = [
        (name, _mapping(fixture[name], f"operational fixture {name}").get("scope"))
        for name in (
            "event_bundle",
            "weekly_review",
            "monthly_audit",
            "quarterly_decision",
            "claim_incident",
            "release_recovery",
            "demand_decision",
            "commercial_outcome",
        )
    ]
    private_ledgers = _mapping(fixture["private_ledgers"], "operational fixture private_ledgers")
    if set(private_ledgers) != {"demand", "delivery", "operator"}:
        raise P14Error("operational fixture requires demand, delivery, and operator private ledgers")
    nested_scope_values.extend(
        (f"private_ledgers.{kind}", _mapping(private_ledgers[kind], kind).get("scope"))
        for kind in ("demand", "delivery", "operator")
    )
    omega_observations = _list(fixture["omega_observations"], "omega observations")
    nested_scope_values.extend(
        (f"omega_observations[{index}]", _mapping(row, "omega observation").get("scope"))
        for index, row in enumerate(omega_observations)
    )
    for name, scope in nested_scope_values:
        if scope != "synthetic":
            raise P14Error(f"operational fixture {name} must remain synthetic")
    for index, raw in enumerate(omega_observations):
        observation = _mapping(raw, f"omega observations[{index}]")
        if observation.get("observed_head") != fixture["observed_head"]:
            raise P14Error(f"operational fixture omega observations[{index}] exact head mismatch")
    portfolio_impacts = _list(fixture["portfolio_impacts"], "portfolio impacts", nonempty=True)
    impact_ids: list[str] = []
    for index, raw in enumerate(portfolio_impacts):
        impact = _mapping(raw, f"portfolio impacts[{index}]")
        required_impact_fields = {
            "outcome_id",
            "scope",
            "before_class",
            "after_class",
            "reason",
            "evidence_url",
        }
        if set(impact) != required_impact_fields:
            raise P14Error(f"operational fixture portfolio impacts[{index}] field contract drift")
        if impact.get("scope") != "synthetic":
            raise P14Error(f"operational fixture portfolio impacts[{index}] must remain synthetic")
        impact_ids.append(_text(impact.get("outcome_id"), f"portfolio impacts[{index}].outcome_id"))
        for field in ("before_class", "after_class", "reason"):
            _text(impact.get(field), f"portfolio impacts[{index}].{field}")
        if not _is_url(impact.get("evidence_url")):
            raise P14Error(f"operational fixture portfolio impacts[{index}] evidence_url must be HTTPS")
    if len(set(impact_ids)) != len(impact_ids):
        raise P14Error("operational fixture portfolio impacts contain duplicate outcome ids")
    metric_result = collect_metrics(contract, operations, fixture["event_bundle"])
    weekly = run_weekly_review(operations, fixture["weekly_review"])
    monthly = run_monthly_audit(operations, fixture["monthly_audit"])
    quarterly = run_quarterly_decision(operations, fixture["quarterly_decision"])
    claim = run_claim_incident(contract, operations, fixture["claim_incident"])
    release = run_release_recovery(contract, operations, fixture["release_recovery"])
    projections = {
        kind: project_private_ledger(operations, kind, fixture["private_ledgers"][kind])
        for kind in ("demand", "delivery", "operator")
    }
    demand_ids = {row["outcome_id"] for row in projections["demand"]["records"]}
    demand_decision = _mapping(fixture["demand_decision"], "operational fixture demand_decision")
    if (
        demand_decision.get("status") != "decided"
        or demand_decision.get("scope") != "synthetic"
        or demand_decision.get("decision") not in contract["feedback_loops"]["sales"]["allowed_decisions"]
        or demand_decision.get("before_offer_version") == demand_decision.get("after_offer_version")
        or not _is_url(demand_decision.get("evidence_url"))
    ):
        raise P14Error("operational fixture demand decision contract is incomplete")
    decision_ids = demand_decision.get("outcome_ids")
    if not isinstance(decision_ids, list) or set(decision_ids) != demand_ids or len(decision_ids) != len(demand_ids):
        raise P14Error("operational fixture demand decision must exactly preserve projected demand outcomes")
    commercial = _mapping(fixture["commercial_outcome"], "operational fixture commercial_outcome")
    commercial_ids = commercial.get("outcome_ids")
    if (
        commercial.get("status") != "validated"
        or commercial.get("scope") != "synthetic"
        or commercial.get("mode") not in {"paid_audit", "documented_no"}
        or not isinstance(commercial_ids, list)
        or not commercial_ids
        or len(set(commercial_ids)) != len(commercial_ids)
        or not set(commercial_ids).issubset(demand_ids)
        or not _is_url(commercial.get("evidence_url"))
    ):
        raise P14Error("operational fixture commercial outcome contract is incomplete")
    outcome_ids = {row["outcome_id"] for kind in ("delivery", "operator") for row in projections[kind]["records"]}
    if set(impact_ids) != outcome_ids:
        raise P14Error("operational fixture portfolio impacts must exactly cover delivery and operator outcomes")
    gates = _mapping(fixture["human_gates"], "operational fixture human_gates")
    expected_gate = contract["feedback_loops"]["sales"]["required_human_gate"]
    if gates != {expected_gate: {"status": "pending"}}:
        raise P14Error("operational fixture must leave the price-anchor human gate pending")
    omega = assemble_omega_pair(operations, omega_observations)
    if omega["observed_head"] != fixture["observed_head"]:
        raise P14Error("operational fixture Omega pair exact head mismatch")
    source_bundle = {
        "schema_version": "limen.positioning_p14_evidence_source_bundle.v1",
        "scope": "synthetic",
        "observed_head": fixture["observed_head"],
        "work_receipts": {},
        "review_receipts": {"weekly": [weekly], "monthly": [monthly], "quarterly": [quarterly]},
        "claim_incident_drill": claim,
        "release_recovery_drill": release,
        "private_ledgers": deepcopy(fixture["private_ledgers"]),
        "demand_decision": deepcopy(demand_decision),
        "commercial_outcome": deepcopy(commercial),
        "portfolio_impacts": deepcopy(portfolio_impacts),
        "human_gates": deepcopy(gates),
        "omega_pair": deepcopy(omega["pair"]),
    }
    envelope = build_evidence_envelope(contract, operations, source_bundle)
    terminal = terminal_report(contract, envelope)
    if terminal["terminal"]:
        raise P14Error("synthetic operational fixture must never satisfy the live terminal predicate")
    stages = {
        WORK_IDS[0]: metric_result,
        WORK_IDS[1]: weekly,
        WORK_IDS[2]: monthly,
        WORK_IDS[3]: quarterly,
        WORK_IDS[4]: claim,
        WORK_IDS[5]: release,
        WORK_IDS[6]: projections["demand"],
        WORK_IDS[7]: {
            "delivery": projections["delivery"],
            "operator": projections["operator"],
            "portfolio_impacts": deepcopy(fixture["portfolio_impacts"]),
            "counts_as_closure": False,
        },
        WORK_IDS[8]: omega,
    }
    return {
        "schema_version": "limen.positioning_p14_operational_fixture_result.v1",
        "status": "synthetic-pass",
        "scope": "synthetic",
        "stages": stages,
        "evidence_envelope": envelope,
        "terminal_status": terminal["status"],
        "terminal": False,
        "executed_predecessor_commands": [],
        "counts_as_live_outcomes": False,
        "counts_as_closure": False,
        "not_evidence_for": deepcopy(operations["scope_separation"]["synthetic_may_not_satisfy"]),
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
    if value.get("counts_as_terminal_evidence") is False:
        return False, "prepared runner output lacks its durable owner receipt"
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
        repositories = value.get("resolved_repositories")
        minimum_repositories = requirement.get("minimum_repositories", 2)
        if (
            not isinstance(repositories, list)
            or len(repositories) < minimum_repositories
            or len(set(repositories)) != len(repositories)
            or not all(isinstance(item, str) and item for item in repositories)
        ):
            return False, f"release recovery needs {minimum_repositories} distinct repositories"
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
            or len(before) != len(repositories)
            or len(set(before)) != len(before)
        ):
            return False, "restored release ids do not exactly match the known-green ids"
        if (
            not isinstance(bad, list)
            or not bad
            or not all(isinstance(item, str) and item for item in bad)
            or set(bad) & set(before)
            or len(bad) != len(repositories)
            or len(set(bad)) != len(bad)
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
        if record.get("counts_as_terminal_evidence") is False:
            invalid_reasons.append("prepared runner output lacks its durable owner receipt")
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
    owner_receipt_ok = bool(evidence) and evidence.get("counts_as_terminal_evidence") is not False
    evidence_valid = schema_ok and scope_ok and public_safe and owner_receipt_ok
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
        "schema_version": "limen.positioning_p14_terminal_report.v2",
        "status": "pass" if total_missing == 0 else "blocked",
        "terminal": total_missing == 0,
        "p14_terminal": p14_missing_count == 0,
        "evidence_envelope": {
            "path_schema_valid": schema_ok,
            "scope_live": scope_ok,
            "public_safe": public_safe,
            "owner_receipt_eligible": owner_receipt_ok,
            "privacy_violations": privacy_violations,
        },
        "predecessor_blockers": dependency["predecessor_blockers"],
        "predecessor_blocker_count": predecessor_count,
        "formal_execution_frontier": dependency["formal_execution_frontier"],
        "execution_frontier": dependency["formal_execution_frontier"],
        "reversible_preparation_frontier": dependency["reversible_preparation_frontier"],
        "frontier_invariant": dependency["frontier_invariant"],
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
    operations: dict[str, Any] | None = None,
    operation_fixture: object | None = None,
) -> dict[str, Any]:
    if ledger is None:
        ledger = load_dependency_ledger(contract=contract)
    if operations is None:
        operations = load_operations()
    if operation_fixture is None:
        operation_fixture = _load_json(DEFAULT_OPERATION_FIXTURE)
    fixture_result = run_synthetic(contract, fixture)
    operational_result = run_operational_fixture(contract, operations, operation_fixture)
    terminal = terminal_report(contract, evidence, ledger)
    if terminal["terminal"]:
        raise P14Error("preflight unexpectedly received terminal live evidence; run the owning live predicates")
    return {
        "schema_version": "limen.positioning_p14_preflight.v2",
        "status": "pass",
        "contract": "valid",
        "synthetic_fixture": fixture_result["status"],
        "operational_fixture": operational_result["status"],
        "predecessor_commands_executed": fixture_result["executed_predecessor_commands"],
        "terminal_status": terminal["status"],
        "predecessor_blockers": terminal["predecessor_blockers"],
        "predecessor_blocker_count": terminal["predecessor_blocker_count"],
        "formal_execution_frontier": terminal["formal_execution_frontier"],
        "execution_frontier": terminal["formal_execution_frontier"],
        "reversible_preparation_frontier": terminal["reversible_preparation_frontier"],
        "frontier_invariant": terminal["frontier_invariant"],
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
    mode.add_argument("--run-operational-fixture", type=Path, metavar="PATH")
    mode.add_argument("--collect-metrics", type=Path, metavar="PATH")
    mode.add_argument("--weekly-review", type=Path, metavar="PATH")
    mode.add_argument("--monthly-audit", type=Path, metavar="PATH")
    mode.add_argument("--quarterly-decision", type=Path, metavar="PATH")
    mode.add_argument("--claim-drill", type=Path, metavar="PATH")
    mode.add_argument("--release-drill", type=Path, metavar="PATH")
    mode.add_argument("--project-private-ledger", type=Path, metavar="PATH")
    mode.add_argument("--build-evidence-envelope", type=Path, metavar="PATH")
    mode.add_argument("--omega-observation", type=Path, metavar="PATH")
    mode.add_argument("--assemble-omega-pair", type=Path, nargs=2, metavar=("PASS1", "PASS2"))
    mode.add_argument("--frontiers", action="store_true")
    mode.add_argument("--verify-two-pass", type=Path, metavar="PATH")
    mode.add_argument("--terminal", action="store_true")
    mode.add_argument("--preflight", action="store_true")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--operations", type=Path, default=DEFAULT_OPERATIONS)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--ledger-kind", choices=("demand", "delivery", "operator"))
    parser.add_argument("--scope", choices=("synthetic", "live"), default="live")
    args = parser.parse_args(argv)
    try:
        contract = load_contract(args.manifest)
        operations = load_operations(args.operations)
        ledger = load_dependency_ledger(args.ledger, contract)
        dependency = dependency_report(ledger)
        if args.check:
            operational_fixture = run_operational_fixture(contract, operations, _load_json(DEFAULT_OPERATION_FIXTURE))
            result: object = {
                "schema_version": CONTROL_SCHEMA,
                "status": "ok",
                "events": len(contract["events"]),
                "metrics": len(contract["metrics"]),
                "stages": contract["stage_order"],
                "terminal_requirements": len(contract["terminal_requirements"]),
                "predecessor_chunks": len(ledger["predecessor_chunks"]),
                "operations_schema_version": operations["schema_version"],
                "operational_runners": len(operations["runners"]),
                "operational_fixture": operational_fixture["status"],
                "dependency_blockers": dependency["predecessor_blocker_count"],
                "formal_execution_frontier": dependency["formal_execution_frontier"],
                "execution_frontier": dependency["formal_execution_frontier"],
                "reversible_preparation_frontier": dependency["reversible_preparation_frontier"],
                "frontier_invariant": dependency["frontier_invariant"],
                "predecessor_policy": contract["predecessor_policy"],
                "counts_as_closure": False,
            }
            exit_code = 0
        elif args.run_fixture:
            result = run_synthetic(contract, _load_json(args.run_fixture))
            exit_code = 0
        elif args.run_operational_fixture:
            result = run_operational_fixture(contract, operations, _load_json(args.run_operational_fixture))
            exit_code = 0
        elif args.collect_metrics:
            result = collect_metrics(contract, operations, _load_json(args.collect_metrics))
            exit_code = 0
        elif args.weekly_review:
            result = run_weekly_review(operations, _load_json(args.weekly_review))
            exit_code = 0
        elif args.monthly_audit:
            result = run_monthly_audit(operations, _load_json(args.monthly_audit))
            exit_code = 0
        elif args.quarterly_decision:
            result = run_quarterly_decision(operations, _load_json(args.quarterly_decision))
            exit_code = 0
        elif args.claim_drill:
            result = run_claim_incident(contract, operations, _load_json(args.claim_drill))
            exit_code = 0
        elif args.release_drill:
            result = run_release_recovery(contract, operations, _load_json(args.release_drill))
            exit_code = 0
        elif args.project_private_ledger:
            if args.ledger_kind is None:
                raise P14Error("--project-private-ledger requires --ledger-kind")
            result = project_private_ledger(operations, args.ledger_kind, _load_json(args.project_private_ledger))
            exit_code = 0
        elif args.build_evidence_envelope:
            result = build_evidence_envelope(contract, operations, _load_json(args.build_evidence_envelope))
            exit_code = 0
        elif args.omega_observation:
            result = normalize_omega_observation(operations, _load_json(args.omega_observation))
            exit_code = 0
        elif args.assemble_omega_pair:
            result = assemble_omega_pair(operations, [_load_json(path) for path in args.assemble_omega_pair])
            exit_code = 0
        elif args.frontiers:
            result = dependency
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
                operations,
                _load_json(DEFAULT_OPERATION_FIXTURE),
            )
            exit_code = 0
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        return exit_code
    except P14Error as exc:
        print(f"positioning-p14-control-plane: BLOCKED — {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
