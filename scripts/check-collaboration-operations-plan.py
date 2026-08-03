#!/usr/bin/env python3
"""Validate the complete Collaboration Operations Platform execution plan."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLAN_ROOT = ROOT / "docs" / "continuations" / "collaboration-operations-platform-alpha-omega-20260803"
DAG_PATH = PLAN_ROOT / "execution-dag.yaml"
PLAN_INDEX = ROOT / ".codex" / "plans" / "2026-08-03-collaboration-operations-platform-alpha-omega.md"
REQUIRED_MODULES = (
    PLAN_ROOT / "architecture.md",
    PLAN_ROOT / "execution-dag.yaml",
    PLAN_ROOT / "acceptance.md",
    PLAN_ROOT / "agy-autonomous-intent.md",
)
PHASES = (
    ("alpha", "α", "ALPHA"),
    ("beta", "β", "BETA"),
    ("gamma", "γ", "GAMMA"),
    ("delta", "δ", "DELTA"),
    ("epsilon", "ε", "EPSILON"),
    ("zeta", "ζ", "ZETA"),
    ("eta", "η", "ETA"),
    ("theta", "θ", "THETA"),
    ("iota", "ι", "IOTA"),
    ("kappa", "κ", "KAPPA"),
    ("lambda", "λ", "LAMBDA"),
    ("mu", "μ", "MU"),
    ("nu", "ν", "NU"),
    ("xi", "ξ", "XI"),
    ("omicron", "ο", "OMICRON"),
    ("pi", "π", "PI"),
    ("rho", "ρ", "RHO"),
    ("sigma", "σ", "SIGMA"),
    ("tau", "τ", "TAU"),
    ("upsilon", "υ", "UPSILON"),
    ("phi", "φ", "PHI"),
    ("chi", "χ", "CHI"),
    ("psi", "ψ", "PSI"),
    ("omega", "ω", "OMEGA"),
)
RETAINED_GATES = {
    "destructive_personal_data_action",
    "credential_or_secret_movement",
    "paid_spend",
    "collaborator_invitation_or_transfer",
    "public_send_or_release",
    "dns_mutation",
    "production_deployment",
    "live_client_data_or_transcript_import",
}
PACKET_FIELDS = {
    "id",
    "title",
    "depends_on",
    "effect",
    "scope",
    "deliverables",
    "predicate",
    "receipt_target",
    "required_capabilities",
}


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ValueError("execution DAG root must be a mapping")
    return value


def _cycles(nodes: set[str], dependencies: dict[str, list[str]]) -> list[str]:
    inbound = {node: 0 for node in nodes}
    followers: dict[str, list[str]] = defaultdict(list)
    for node, deps in dependencies.items():
        for dep in deps:
            if dep in nodes:
                inbound[node] += 1
                followers[dep].append(node)
    ready = deque(sorted(node for node, count in inbound.items() if count == 0))
    visited = 0
    while ready:
        node = ready.popleft()
        visited += 1
        for follower in followers[node]:
            inbound[follower] -= 1
            if inbound[follower] == 0:
                ready.append(follower)
    return sorted(node for node, count in inbound.items() if count) if visited != len(nodes) else []


def validate_plan(document: dict[str, Any], *, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    if document.get("schema_version") != "limen.collaboration_operations_execution_dag.v1":
        errors.append("execution DAG schema_version is invalid")

    program = document.get("program") or {}
    expected_program = {
        "id": "collaboration-operations-platform-alpha-omega",
        "owner": "organvm/limen",
        "target_repository": "organvm-iii-ergon/collaboration-operations-platform",
        "target_class": "operation_private",
        "audience": "self",
        "start_state": "prepared_not_created",
        "target_state": "omega_fixed_point",
        "root_predicate": "./scripts/omega.sh",
        "root_receipt": "receipts/omega/latest.json",
    }
    for key, expected in expected_program.items():
        if program.get(key) != expected:
            errors.append(f"program.{key} must be {expected!r}")
    if program.get("source_origin") != "human_prompt" or program.get("horizon") != "future":
        errors.append("program must preserve human_prompt source origin and future horizon")
    if not str(program.get("value_case") or "").strip():
        errors.append("program.value_case must be non-empty")

    authority = document.get("authority") or {}
    retained = set(authority.get("retained_gates") or [])
    if retained != RETAINED_GATES:
        errors.append("authority.retained_gates must match the complete retained-gate set")
    if "github_private_repo_create" not in set(authority.get("allowed_external_effects") or []):
        errors.append("authority must explicitly carry private repository genesis")

    team = document.get("team") or {}
    if team.get("root_agent") != "agy" or team.get("provider_selection") != "live_capability_derived":
        errors.append("team must use native Agy with live capability-derived children")
    if team.get("max_children") != 4 or team.get("max_depth") != 1:
        errors.append("team fanout must remain bounded to four children at depth one")
    if team.get("writer_rule") != "one_writer_per_worktree":
        errors.append("team writer rule must be one_writer_per_worktree")
    if team.get("session_rule") != "human_protected":
        errors.append("team session must remain human_protected")

    phases = document.get("phases") or []
    if not isinstance(phases, list):
        return errors + ["phases must be a list"]
    expected_ids = [row[0] for row in PHASES]
    actual_ids = [phase.get("id") for phase in phases if isinstance(phase, dict)]
    if actual_ids != expected_ids:
        errors.append("phases must contain Alpha through Omega exactly once in canonical order")

    phase_nodes = set(expected_ids)
    phase_deps: dict[str, list[str]] = {}
    packet_nodes: set[str] = set()
    packet_deps: dict[str, list[str]] = {}
    packet_rows: list[tuple[str, str, dict[str, Any]]] = []
    phase_index = {phase_id: index for index, phase_id in enumerate(expected_ids)}

    for index, phase in enumerate(phases):
        if not isinstance(phase, dict) or index >= len(PHASES):
            errors.append(f"phase at index {index} must be a mapping")
            continue
        expected_id, expected_symbol, prefix = PHASES[index]
        if phase.get("id") != expected_id or phase.get("symbol") != expected_symbol:
            errors.append(f"phase {index} must be {expected_id}/{expected_symbol}")
        for field in ("title", "purpose", "exit_predicate"):
            if not str(phase.get(field) or "").strip():
                errors.append(f"phase {expected_id}.{field} must be non-empty")
        if phase.get("exit_predicate") != (
            "./scripts/omega.sh" if expected_id == "omega" else f"./scripts/gates/{expected_id}.sh"
        ):
            errors.append(f"phase {expected_id} exit predicate is not canonical")
        deps = phase.get("depends_on") or []
        if not isinstance(deps, list) or any(dep not in phase_nodes for dep in deps):
            errors.append(f"phase {expected_id} has an unknown dependency")
            deps = [dep for dep in deps if dep in phase_nodes] if isinstance(deps, list) else []
        if any(phase_index[dep] >= index for dep in deps):
            errors.append(f"phase {expected_id} dependencies must point to earlier phases")
        phase_deps[expected_id] = deps

        packets = phase.get("packets") or []
        if not isinstance(packets, list) or len(packets) != 3:
            errors.append(f"phase {expected_id} must contain exactly three bounded packets")
            continue
        for ordinal, packet in enumerate(packets, start=1):
            if not isinstance(packet, dict):
                errors.append(f"phase {expected_id} packet {ordinal} must be a mapping")
                continue
            packet_id = packet.get("id")
            expected_packet_id = f"{prefix}-{ordinal:02d}"
            if packet_id != expected_packet_id:
                errors.append(f"phase {expected_id} packet {ordinal} must be {expected_packet_id}")
            if set(packet) - (PACKET_FIELDS | {"requires_gate"}):
                errors.append(f"packet {packet_id} has unknown fields")
            if not PACKET_FIELDS.issubset(packet):
                errors.append(f"packet {packet_id} is missing required fields")
            if packet_id in packet_nodes:
                errors.append(f"duplicate packet id: {packet_id}")
            if isinstance(packet_id, str):
                packet_nodes.add(packet_id)
                packet_rows.append((expected_id, packet_id, packet))

    for phase_id, packet_id, packet in packet_rows:
        deps = packet.get("depends_on") or []
        if not isinstance(deps, list):
            errors.append(f"packet {packet_id}.depends_on must be a list")
            deps = []
        packet_deps[packet_id] = deps
        if packet_id in deps:
            errors.append(f"packet {packet_id} cannot depend on itself")
        if packet.get("effect") not in {"read", "write", "external"}:
            errors.append(f"packet {packet_id}.effect is invalid")
        for field in ("scope", "deliverables", "required_capabilities"):
            value = packet.get(field)
            if not isinstance(value, list) or not value or any(not str(item).strip() for item in value):
                errors.append(f"packet {packet_id}.{field} must be a non-empty list")
        slug = packet_id.lower()
        if packet.get("predicate") != f"./scripts/gates/packets/{slug}.sh":
            errors.append(f"packet {packet_id} predicate is not canonical")
        if packet.get("receipt_target") != f"receipts/packets/{slug}.json":
            errors.append(f"packet {packet_id} receipt target is not canonical")
        required_gate = packet.get("requires_gate")
        if required_gate is not None and required_gate not in RETAINED_GATES:
            errors.append(f"packet {packet_id} names an unknown retained gate")

    for packet_id, deps in packet_deps.items():
        unknown = [dep for dep in deps if dep not in packet_nodes]
        if unknown:
            errors.append(f"packet {packet_id} has unknown dependencies: {', '.join(unknown)}")

    phase_cycle = _cycles(phase_nodes, phase_deps)
    if phase_cycle:
        errors.append(f"phase graph has a cycle: {', '.join(phase_cycle)}")
    packet_cycle = _cycles(packet_nodes, packet_deps)
    if packet_cycle:
        errors.append(f"packet graph has a cycle: {', '.join(packet_cycle)}")
    if len(packet_nodes) != 72:
        errors.append("execution DAG must contain exactly 72 bounded packets")

    plan_index = root / ".codex" / "plans" / "2026-08-03-collaboration-operations-platform-alpha-omega.md"
    modules = tuple(
        root / "docs" / "continuations" / "collaboration-operations-platform-alpha-omega-20260803" / name
        for name in ("architecture.md", "execution-dag.yaml", "acceptance.md", "agy-autonomous-intent.md")
    )
    for path in (plan_index, *modules):
        try:
            if path.is_symlink() or not path.is_file() or not path.read_text(encoding="utf-8").strip():
                errors.append(f"required plan module is missing or empty: {path.relative_to(root)}")
        except OSError:
            errors.append(f"required plan module is unreadable: {path.relative_to(root)}")

    lever_path = root / "his-hand-levers.json"
    try:
        lever_document = json.loads(lever_path.read_text(encoding="utf-8"))
        genesis_levers = [
            lever
            for lever in lever_document.get("levers", [])
            if isinstance(lever, dict) and lever.get("id") == "L-COLLABORATION-OPERATIONS-PLATFORM-GENESIS"
        ]
    except (OSError, json.JSONDecodeError, AttributeError):
        genesis_levers = []
    if len(genesis_levers) != 1:
        errors.append("the collaboration-operations genesis lever must exist exactly once")
    else:
        lever = genesis_levers[0]
        if lever.get("status") != "discharged" or lever.get("issue") != 1790:
            errors.append("the collaboration-operations genesis lever must be discharged through issue 1790")
        gate = str(lever.get("gate") or "")
        retained_tokens = ("credential", "paid spend", "collaborator", "production deployment", "live client-data")
        if not all(token in gate for token in retained_tokens):
            errors.append("the discharged genesis lever must preserve every material retained gate")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dag", type=Path, default=DAG_PATH)
    args = parser.parse_args()
    try:
        errors = validate_plan(load_yaml(args.dag))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"collaboration-operations-plan: invalid input: {exc}", file=sys.stderr)
        return 2
    for error in errors:
        print(f"FAIL {error}")
    if errors:
        print(f"collaboration-operations-plan: {len(errors)} failure(s)")
        return 1
    print("collaboration-operations-plan: OK — 24 phases, 72 bounded packets, native Agy conductor")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
