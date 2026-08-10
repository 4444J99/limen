#!/usr/bin/env python3
"""Validate, render, project, and inspect the Production-Systems Positioning Program.

The tracked YAML manifest is canonical. GitHub issues and the issue-number map are projections.
Every projected object carries a stable HTML marker, making sync idempotent and allowing drift,
duplicates, and orphans to fail closed.

Mutation is explicit:

  python3 scripts/positioning-program.py --check
  python3 scripts/positioning-program.py --render
  python3 scripts/positioning-program.py --sync              # dry run
  python3 scripts/positioning-program.py --sync --apply      # GitHub writes + map/index rewrite
  python3 scripts/positioning-program.py --verify-remote
  python3 scripts/positioning-program.py --verify-model-assignments
  python3 scripts/positioning-program.py --render-chunks
  python3 scripts/positioning-program.py --chunk PSP-C00
  python3 scripts/positioning-program.py --ready --json
  python3 scripts/positioning-program.py --seed PSP-P01-W01
  python3 scripts/positioning-program.py --receipt-template PSP-P01-W01
  python3 scripts/positioning-program.py --phase-proof PSP-P00
  python3 scripts/positioning-program.py --phase-receipt-template PSP-P00
  python3 scripts/positioning-program.py --verify-work PSP-P01-W01

This tool never closes/reopens issues, merges pull requests, submits to the conduct broker, edits
tasks.yaml, sends, publishes, changes DNS, spends, or accepts terms. A packet seed is deliberately
not a WorkPacketV1: a live registered conductor must add current identity, authority, resource
claims, deadline, spend, and retry bounds before submission.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = ROOT / "institutio" / "positioning" / "program.yaml"
DEFAULT_MAP = ROOT / "institutio" / "positioning" / "github-map.json"
DEFAULT_INDEX = ROOT / "docs" / "positioning" / "program" / "ISSUE-INDEX.md"
DEFAULT_CHUNKS = ROOT / "docs" / "positioning" / "program" / "EXECUTION-CHUNKS.md"
OMEGA_DIR = ROOT / "docs" / "receipts" / "positioning"
PROGRAM_SCHEMA = "limen.positioning_program.v1"
MAP_SCHEMA = "limen.positioning_github_map.v1"
SEED_SCHEMA = "limen.positioning_packet_seed.v1"
RECEIPT_SCHEMA = "limen.positioning_work_receipt.v1"
PHASE_RECEIPT_SCHEMA = "limen.positioning_phase_receipt.v1"
OMEGA_PASS_SCHEMA = "limen.positioning_omega_pass.v1"
MODEL_ASSIGNMENT_SCHEMA = "limen.positioning_model_assignments.v1"
EXECUTION_CHUNKS_SCHEMA = "limen.positioning_execution_chunks.v1"
REPOSITORY_IDENTITIES_SCHEMA = "limen.positioning_repository_identities.v1"
MARKER_RE = re.compile(r"<!--\s*positioning-program:(PSP-(?:ROOT|P\d{2}(?:-W\d{2})?))\s*-->")
RECEIPT_MARKER_RE = re.compile(r"<!--\s*positioning-receipt:(PSP-P\d{2}-W\d{2})\s*-->")
RECEIPT_BLOCK_RE = re.compile(
    r"<!--\s*positioning-receipt:(PSP-P\d{2}-W\d{2})\s*-->\s*```json\s*(\{.*?\})\s*```",
    re.DOTALL,
)
PHASE_RECEIPT_MARKER_RE = re.compile(r"<!--\s*positioning-phase-receipt:(PSP-P\d{2})\s*-->")
PHASE_RECEIPT_BLOCK_RE = re.compile(
    r"<!--\s*positioning-phase-receipt:(PSP-P\d{2})\s*-->\s*```json\s*(\{.*?\})\s*```",
    re.DOTALL,
)
DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
HEAD_RE = re.compile(r"[0-9a-f]{40}\Z")
RFC3339_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z")
URL_RE = re.compile(r"https://[^\s]+\Z")
REPOSITORY_RE = re.compile(r"[^/:\s]+/[^/:\s]+\Z")
PHASE_RE = re.compile(r"PSP-P\d{2}\Z")
WORK_RE = re.compile(r"PSP-P\d{2}-W\d{2}\Z")
CHUNK_RE = re.compile(r"PSP-C\d{2}\Z")
REASONING = frozenset({"routine", "deep", "frontier_review"})
EFFECTS = frozenset({"read", "write", "external"})
EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max", "ultra"})
FORBIDDEN_ROUTING_KEYS = frozenset({"model", "model_id", "provider", "preferred_agent"})
REQUIRED_WORK_FIELDS = (
    "id",
    "title",
    "outcome",
    "target_repo",
    "target_paths",
    "capabilities",
    "reasoning",
    "effect",
    "depends_on",
    "external_dependencies",
    "human_gates",
    "deliverables",
    "acceptance",
    "predicate",
    "rollback",
    "return_evidence",
)


class ProgramError(RuntimeError):
    pass


def _is_nonempty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_text_list(value: object, *, nonempty: bool = False) -> bool:
    return isinstance(value, list) and (not nonempty or bool(value)) and all(_is_nonempty_text(item) for item in value)


def _assignment_failures(value: object, label: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{label} must be a mapping"]
    failures = []
    if set(value) != {"slug", "effort", "rationale"}:
        failures.append(f"{label} must contain exactly slug, effort, and rationale")
    if not _is_nonempty_text(value.get("slug")):
        failures.append(f"{label}.slug must be non-empty text")
    if value.get("effort") not in EFFORTS:
        failures.append(f"{label}.effort must be one of {sorted(EFFORTS)}")
    if not _is_nonempty_text(value.get("rationale")):
        failures.append(f"{label}.rationale must be non-empty text")
    return failures


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ProgramError(f"cannot load manifest {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProgramError("program manifest must be a mapping")
    return value


def load_map(path: Path = DEFAULT_MAP) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": MAP_SCHEMA, "repository": "", "milestone": None, "issues": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProgramError(f"cannot load GitHub map {path}: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != MAP_SCHEMA:
        raise ProgramError("unsupported GitHub map schema")
    if not isinstance(value.get("issues"), dict):
        raise ProgramError("GitHub map issues must be a mapping")
    return value


def _walk_keys(value: object, trail: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], object]]:
    if isinstance(value, dict):
        for key, child in value.items():
            next_trail = (*trail, str(key))
            yield next_trail, child
            yield from _walk_keys(child, next_trail)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_keys(child, (*trail, str(index)))


def index_program(data: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    if data.get("schema_version") != PROGRAM_SCHEMA:
        failures.append(f"schema_version must be {PROGRAM_SCHEMA}")
    program = data.get("program")
    phases = data.get("phases")
    external = data.get("external_references")
    gates = data.get("human_gates")
    assignments = data.get("model_assignments")
    execution_chunks = data.get("execution_chunks")
    repository_identities = data.get("repository_identities")
    if not isinstance(program, dict):
        failures.append("program must be a mapping")
        program = {}
    if not isinstance(phases, list) or not phases:
        failures.append("phases must be a non-empty list")
        phases = []
    if not isinstance(external, dict):
        failures.append("external_references must be a mapping")
        external = {}
    if not isinstance(gates, dict):
        failures.append("human_gates must be a mapping")
        gates = {}
    if not isinstance(assignments, dict):
        failures.append("model_assignments must be a mapping")
        assignments = {}
    if not isinstance(execution_chunks, dict):
        failures.append("execution_chunks must be a mapping")
        execution_chunks = {}
    if not isinstance(repository_identities, dict):
        failures.append("repository_identities must be a mapping")
        repository_identities = {}
    if program.get("id") != "PSP-ROOT":
        failures.append("program.id must be PSP-ROOT")
    for key in ("title", "repository", "outcome", "terminal_predicate"):
        if not _is_nonempty_text(program.get(key)):
            failures.append(f"program.{key} must be non-empty text")
    projection = program.get("issue_projection")
    if not isinstance(projection, dict) or not all(
        _is_nonempty_text(projection.get(key)) for key in ("milestone", "program_label", "phase_label", "work_label")
    ):
        failures.append("program.issue_projection is incomplete")

    if repository_identities.get("schema_version") != REPOSITORY_IDENTITIES_SCHEMA:
        failures.append(f"repository_identities.schema_version must be {REPOSITORY_IDENTITIES_SCHEMA}")
    identity_observed_at = repository_identities.get("observed_at")
    if not isinstance(identity_observed_at, str) or not RFC3339_RE.fullmatch(identity_observed_at):
        failures.append("repository_identities.observed_at must be RFC3339")
    identity_rows = repository_identities.get("repositories")
    if not isinstance(identity_rows, dict) or not identity_rows:
        failures.append("repository_identities.repositories must be a non-empty mapping")
        identity_rows = {}
    repository_identity_by_slug: dict[str, dict[str, Any]] = {}
    retired_repository_slugs: dict[str, str] = {}
    repository_ids: dict[int, str] = {}
    for identity_name, value in identity_rows.items():
        label = f"repository_identities.repositories.{identity_name}"
        if not isinstance(value, dict):
            failures.append(f"{label} must be a mapping")
            continue
        repository_id = value.get("github_repository_id")
        canonical_slug = value.get("canonical_slug")
        previous_slugs = value.get("previous_slugs")
        if not isinstance(repository_id, int) or isinstance(repository_id, bool) or repository_id <= 0:
            failures.append(f"{label}.github_repository_id must be a positive integer")
        elif repository_id in repository_ids:
            failures.append(
                f"{label}.github_repository_id duplicates {repository_ids[repository_id]!r}"
            )
        else:
            repository_ids[repository_id] = str(identity_name)
        if not isinstance(canonical_slug, str) or not REPOSITORY_RE.fullmatch(canonical_slug):
            failures.append(f"{label}.canonical_slug must be an owner/repository slug")
            continue
        if canonical_slug in repository_identity_by_slug:
            failures.append(f"duplicate canonical repository identity slug: {canonical_slug}")
            continue
        if value.get("visibility") not in {"public", "private", "internal"}:
            failures.append(f"{label}.visibility must be public, private, or internal")
        if not _is_nonempty_text(value.get("default_branch")):
            failures.append(f"{label}.default_branch must be non-empty text")
        if not isinstance(value.get("archived"), bool):
            failures.append(f"{label}.archived must be boolean")
        expected_source = f"https://api.github.com/repositories/{repository_id}"
        if value.get("source") != expected_source:
            failures.append(
                f"{label}.source must exactly bind github_repository_id to {expected_source!r}"
            )
        if not _is_nonempty_text(value.get("resolution_rule")):
            failures.append(f"{label}.resolution_rule must be non-empty text")
        if not _is_text_list(previous_slugs, nonempty=True):
            failures.append(f"{label}.previous_slugs must be a non-empty text list")
            previous_slugs = []
        if canonical_slug in previous_slugs:
            failures.append(f"{label}.previous_slugs cannot contain the canonical slug")
        if canonical_slug in retired_repository_slugs:
            failures.append(
                f"{label}.canonical_slug is already declared as a retired repository slug"
            )
        normalized = {**value, "identity": str(identity_name), "observed_at": identity_observed_at}
        repository_identity_by_slug[canonical_slug] = normalized
        for previous_slug in previous_slugs:
            if not REPOSITORY_RE.fullmatch(previous_slug):
                failures.append(f"{label}.previous_slugs contains invalid slug {previous_slug!r}")
                continue
            if previous_slug in retired_repository_slugs:
                failures.append(f"retired repository slug is declared more than once: {previous_slug}")
                continue
            if previous_slug in repository_identity_by_slug:
                failures.append(
                    f"{label}.previous_slugs contains canonical repository slug {previous_slug!r}"
                )
                continue
            retired_repository_slugs[previous_slug] = canonical_slug

    for trail, _value in _walk_keys(data):
        if trail and trail[-1] in FORBIDDEN_ROUTING_KEYS:
            failures.append(f"provider/model routing key is forbidden in static program data: {'.'.join(trail)}")

    phase_by_id: dict[str, dict[str, Any]] = {}
    work_by_id: dict[str, dict[str, Any]] = {}
    work_phase: dict[str, str] = {}
    ordered_ids = ["PSP-ROOT"]
    for phase in phases:
        if not isinstance(phase, dict):
            failures.append(f"phase is not a mapping: {phase!r}")
            continue
        phase_id = str(phase.get("id") or "")
        if not PHASE_RE.fullmatch(phase_id):
            failures.append(f"invalid phase id: {phase_id!r}")
            continue
        if phase_id in phase_by_id:
            failures.append(f"duplicate phase id: {phase_id}")
            continue
        phase_by_id[phase_id] = phase
        ordered_ids.append(phase_id)
        for key in ("title", "outcome", "exit_gate", "exit_predicate"):
            if not _is_nonempty_text(phase.get(key)):
                failures.append(f"{phase_id}.{key} must be non-empty text")
        expected_exit_predicate = f"python3 scripts/positioning-program.py --phase-proof {phase_id}"
        exit_predicate = str(phase.get("exit_predicate") or "").strip()
        if exit_predicate != expected_exit_predicate:
            failures.append(f"{phase_id}.exit_predicate must be {expected_exit_predicate}")
        if any(
            token in exit_predicate
            for token in ("--verify-phase", "--phase-receipt-template", "--verify-work", "--receipt-template")
        ):
            failures.append(f"{phase_id}.exit_predicate cannot verify or template a receipt")
        if not _is_text_list(phase.get("depends_on")):
            failures.append(f"{phase_id}.depends_on must be a text list")
        work = phase.get("work")
        if not isinstance(work, list) or not work:
            failures.append(f"{phase_id}.work must be a non-empty list")
            continue
        for packet in work:
            if not isinstance(packet, dict):
                failures.append(f"{phase_id} has a non-mapping work packet")
                continue
            work_id = str(packet.get("id") or "")
            if not WORK_RE.fullmatch(work_id) or not work_id.startswith(f"{phase_id}-W"):
                failures.append(f"invalid work id for {phase_id}: {work_id!r}")
                continue
            if work_id in work_by_id:
                failures.append(f"duplicate work id: {work_id}")
                continue
            work_by_id[work_id] = packet
            work_phase[work_id] = phase_id
            ordered_ids.append(work_id)
            for key in REQUIRED_WORK_FIELDS:
                if key not in packet:
                    failures.append(f"{work_id}.{key} is missing")
            for key in ("title", "outcome", "target_repo", "acceptance", "predicate", "rollback"):
                if not _is_nonempty_text(packet.get(key)):
                    failures.append(f"{work_id}.{key} must be non-empty text")
            target_repo = str(packet.get("target_repo") or "")
            if target_repo in retired_repository_slugs:
                failures.append(
                    f"{work_id}.target_repo uses retired repository slug {target_repo!r}; "
                    f"use {retired_repository_slugs[target_repo]!r}"
                )
            for key in (
                "target_paths",
                "capabilities",
                "depends_on",
                "external_dependencies",
                "human_gates",
                "deliverables",
                "return_evidence",
            ):
                if not _is_text_list(
                    packet.get(key), nonempty=key in {"target_paths", "capabilities", "deliverables", "return_evidence"}
                ):
                    failures.append(f"{work_id}.{key} must be a valid text list")
            if packet.get("reasoning") not in REASONING:
                failures.append(f"{work_id}.reasoning must be one of {sorted(REASONING)}")
            if packet.get("effect") not in EFFECTS:
                failures.append(f"{work_id}.effect must be one of {sorted(EFFECTS)}")
            expected_predicate = f"python3 scripts/positioning-program.py --verify-work {work_id}"
            if packet.get("predicate") != expected_predicate:
                failures.append(f"{work_id}.predicate must be the executable receipt verifier: {expected_predicate}")

    for phase_id, phase in phase_by_id.items():
        for dependency in phase.get("depends_on") or []:
            if dependency not in phase_by_id:
                failures.append(f"{phase_id} has unknown phase dependency {dependency}")
    for work_id, packet in work_by_id.items():
        for dependency in packet.get("depends_on") or []:
            if dependency not in work_by_id:
                failures.append(f"{work_id} has unknown work dependency {dependency}")
            if dependency == work_id:
                failures.append(f"{work_id} cannot depend on itself")
        for reference in packet.get("external_dependencies") or []:
            if reference not in external:
                failures.append(f"{work_id} has unknown external reference {reference}")
        for gate in packet.get("human_gates") or []:
            if gate not in gates:
                failures.append(f"{work_id} has unknown human gate {gate}")
    for gate_id, gate in gates.items():
        if not isinstance(gate, dict) or not _is_text_list(gate.get("references")):
            failures.append(f"human gate {gate_id} is malformed")
            continue
        for reference in gate.get("references") or []:
            if reference not in external:
                failures.append(f"human gate {gate_id} has unknown external reference {reference}")
    for reference_id, reference in external.items():
        if not isinstance(reference, dict) or reference.get("kind") not in {"issue", "pull_request"}:
            failures.append(f"external reference {reference_id} is malformed")
        elif not _is_nonempty_text(reference.get("repository")) or not isinstance(reference.get("number"), int):
            failures.append(f"external reference {reference_id} lacks repository/number")
    for work_id in program.get("critical_path") or []:
        if work_id not in work_by_id:
            failures.append(f"critical_path has unknown work id {work_id}")

    if assignments.get("schema_version") != MODEL_ASSIGNMENT_SCHEMA:
        failures.append(f"model_assignments.schema_version must be {MODEL_ASSIGNMENT_SCHEMA}")
    for key in ("authority", "adapter", "catalog_command", "catalog_validated_at", "unavailable_action"):
        if not _is_nonempty_text(assignments.get(key)):
            failures.append(f"model_assignments.{key} must be non-empty text")
    if assignments.get("adapter") != "codex":
        failures.append("model_assignments.adapter must be codex for the current human override")
    observed_at = assignments.get("catalog_validated_at")
    if isinstance(observed_at, str) and not RFC3339_RE.fullmatch(observed_at):
        failures.append("model_assignments.catalog_validated_at must be RFC3339")
    failures.extend(_assignment_failures(assignments.get("root"), "model_assignments.root"))

    phase_assignments = assignments.get("phases")
    if not isinstance(phase_assignments, dict):
        failures.append("model_assignments.phases must be a mapping")
        phase_assignments = {}
    if set(phase_assignments) != set(phase_by_id):
        failures.append("model_assignments.phases must assign every phase exactly once")
    for phase_id, assignment in phase_assignments.items():
        failures.extend(_assignment_failures(assignment, f"model_assignments.phases.{phase_id}"))

    work_matrix = assignments.get("work_matrix")
    if not isinstance(work_matrix, dict) or set(work_matrix) != set(REASONING):
        failures.append("model_assignments.work_matrix must assign every reasoning class")
        work_matrix = {}
    for reasoning in REASONING:
        effect_rows = work_matrix.get(reasoning)
        if not isinstance(effect_rows, dict) or set(effect_rows) != set(EFFECTS):
            failures.append(f"model_assignments.work_matrix.{reasoning} must assign every effect")
            continue
        for effect, assignment in effect_rows.items():
            failures.extend(_assignment_failures(assignment, f"model_assignments.work_matrix.{reasoning}.{effect}"))

    if not _is_text_list(assignments.get("sensitive_capabilities"), nonempty=True):
        failures.append("model_assignments.sensitive_capabilities must be a non-empty text list")
    failures.extend(
        _assignment_failures(assignments.get("sensitive_assignment"), "model_assignments.sensitive_assignment")
    )
    failures.extend(
        _assignment_failures(
            assignments.get("multi_repository_assignment"), "model_assignments.multi_repository_assignment"
        )
    )
    object_overrides = assignments.get("object_overrides")
    if not isinstance(object_overrides, dict):
        failures.append("model_assignments.object_overrides must be a mapping")
        object_overrides = {}
    unknown_overrides = set(object_overrides) - set(work_by_id)
    if unknown_overrides:
        failures.append(f"model_assignments.object_overrides has unknown work ids: {sorted(unknown_overrides)}")
    for work_id, assignment in object_overrides.items():
        failures.extend(_assignment_failures(assignment, f"model_assignments.object_overrides.{work_id}"))

    if execution_chunks.get("schema_version") != EXECUTION_CHUNKS_SCHEMA:
        failures.append(f"execution_chunks.schema_version must be {EXECUTION_CHUNKS_SCHEMA}")
    for key in ("authority", "relay_template"):
        if not _is_nonempty_text(execution_chunks.get(key)):
            failures.append(f"execution_chunks.{key} must be non-empty text")
    chunk_rows = execution_chunks.get("chunks")
    if not isinstance(chunk_rows, list) or not chunk_rows:
        failures.append("execution_chunks.chunks must be a non-empty list")
        chunk_rows = []
    chunk_by_id: dict[str, dict[str, Any]] = {}
    chunk_work: dict[str, list[str]] = {}
    work_owners: dict[str, list[str]] = {}
    for chunk in chunk_rows:
        if not isinstance(chunk, dict):
            failures.append(f"execution chunk is not a mapping: {chunk!r}")
            continue
        chunk_id = str(chunk.get("id") or "")
        if not CHUNK_RE.fullmatch(chunk_id):
            failures.append(f"invalid execution chunk id: {chunk_id!r}")
            continue
        if chunk_id in chunk_by_id:
            failures.append(f"duplicate execution chunk id: {chunk_id}")
            continue
        chunk_by_id[chunk_id] = chunk
        for key in ("title", "objective", "exit_gate"):
            if not _is_nonempty_text(chunk.get(key)):
                failures.append(f"{chunk_id}.{key} must be non-empty text")
        for key in ("depends_on", "phase_ids", "exclude_work_ids", "extra_work_ids"):
            if not _is_text_list(chunk.get(key), nonempty=key == "phase_ids"):
                failures.append(f"{chunk_id}.{key} must be a valid text list")
        failures.extend(_assignment_failures(chunk.get("conductor"), f"{chunk_id}.conductor"))
        phase_ids = chunk.get("phase_ids") if isinstance(chunk.get("phase_ids"), list) else []
        exclude_ids = set(chunk.get("exclude_work_ids") or [])
        extra_ids = chunk.get("extra_work_ids") if isinstance(chunk.get("extra_work_ids"), list) else []
        if len(phase_ids) != len(set(phase_ids)):
            failures.append(f"{chunk_id}.phase_ids contains duplicates")
        if len(extra_ids) != len(set(extra_ids)):
            failures.append(f"{chunk_id}.extra_work_ids contains duplicates")
        expanded: list[str] = []
        for phase_id in phase_ids:
            phase = phase_by_id.get(phase_id)
            if phase is None:
                failures.append(f"{chunk_id} has unknown phase {phase_id}")
                continue
            expanded.extend(packet["id"] for packet in phase.get("work") or [] if isinstance(packet, dict))
        unknown_excludes = exclude_ids - set(expanded)
        if unknown_excludes:
            failures.append(f"{chunk_id} excludes work outside its phases: {sorted(unknown_excludes)}")
        unknown_extras = set(extra_ids) - set(work_by_id)
        if unknown_extras:
            failures.append(f"{chunk_id} has unknown extra work ids: {sorted(unknown_extras)}")
        resolved = [work_id for work_id in expanded if work_id not in exclude_ids]
        resolved.extend(work_id for work_id in extra_ids if work_id not in resolved)
        if not resolved:
            failures.append(f"{chunk_id} resolves to no work packets")
        chunk_work[chunk_id] = resolved
        for work_id in resolved:
            work_owners.setdefault(work_id, []).append(chunk_id)

    for chunk_id, chunk in chunk_by_id.items():
        for dependency in chunk.get("depends_on") or []:
            if dependency not in chunk_by_id:
                failures.append(f"{chunk_id} has unknown execution chunk dependency {dependency}")
            if dependency == chunk_id:
                failures.append(f"{chunk_id} cannot depend on itself")
    missing_chunk_work = set(work_by_id) - set(work_owners)
    duplicate_chunk_work = {work_id: owners for work_id, owners in work_owners.items() if len(owners) != 1}
    if missing_chunk_work:
        failures.append(f"execution chunks do not cover work ids: {sorted(missing_chunk_work)}")
    if duplicate_chunk_work:
        failures.append(f"execution chunks assign work more than once: {duplicate_chunk_work}")
    work_chunk = {work_id: owners[0] for work_id, owners in work_owners.items() if len(owners) == 1}

    def assert_acyclic(nodes: dict[str, dict[str, Any]], label: str) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str, chain: list[str]) -> None:
            if node_id in visited:
                return
            if node_id in visiting:
                failures.append(f"{label} dependency cycle: {' -> '.join([*chain, node_id])}")
                return
            visiting.add(node_id)
            for dependency in nodes[node_id].get("depends_on") or []:
                if dependency in nodes:
                    visit(dependency, [*chain, node_id])
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in nodes:
            visit(node_id, [])

    assert_acyclic(phase_by_id, "phase")
    assert_acyclic(work_by_id, "work")
    assert_acyclic(chunk_by_id, "execution chunk")

    def chunk_ancestors(chunk_id: str) -> set[str]:
        seen: set[str] = set()
        pending = list(chunk_by_id.get(chunk_id, {}).get("depends_on") or [])
        while pending:
            dependency = pending.pop()
            if dependency in seen or dependency not in chunk_by_id:
                continue
            seen.add(dependency)
            pending.extend(chunk_by_id[dependency].get("depends_on") or [])
        return seen

    for work_id, packet in work_by_id.items():
        owner = work_chunk.get(work_id)
        if owner is None:
            continue
        allowed_chunks = {owner, *chunk_ancestors(owner)}
        for dependency in packet.get("depends_on") or []:
            dependency_owner = work_chunk.get(dependency)
            if dependency_owner is not None and dependency_owner not in allowed_chunks:
                failures.append(
                    f"{work_id} in {owner} depends on {dependency} in non-ancestor chunk {dependency_owner}"
                )
        phase_id = work_phase[work_id]
        for phase_dependency in phase_by_id[phase_id].get("depends_on") or []:
            for dependency_packet in phase_by_id.get(phase_dependency, {}).get("work") or []:
                dependency_owner = work_chunk.get(str(dependency_packet.get("id") or ""))
                if dependency_owner is not None and dependency_owner not in allowed_chunks:
                    failures.append(
                        f"{work_id} in {owner} is phase-gated by {phase_dependency} work in "
                        f"non-ancestor chunk {dependency_owner}"
                    )
    if failures:
        raise ProgramError("program validation failed:\n- " + "\n- ".join(failures))
    return {
        "program": program,
        "phases": phases,
        "phase_by_id": phase_by_id,
        "work_by_id": work_by_id,
        "work_phase": work_phase,
        "external": external,
        "gates": gates,
        "model_assignments": assignments,
        "repository_identities": repository_identities,
        "repository_identity_by_slug": repository_identity_by_slug,
        "retired_repository_slugs": retired_repository_slugs,
        "execution_chunks": execution_chunks,
        "chunks": chunk_rows,
        "chunk_by_id": chunk_by_id,
        "chunk_work": chunk_work,
        "work_chunk": work_chunk,
        "ordered_ids": ordered_ids,
    }


def validate_map(mapping: dict[str, Any], graph: dict[str, Any], *, complete: bool = False) -> None:
    failures: list[str] = []
    if mapping.get("schema_version") != MAP_SCHEMA:
        failures.append("unsupported map schema")
    if mapping.get("repository") not in {"", graph["program"]["repository"]}:
        failures.append("map repository differs from program repository")
    issues = mapping.get("issues") or {}
    expected = set(graph["ordered_ids"])
    actual = set(issues)
    if actual - expected:
        failures.append(f"map has orphan ids: {sorted(actual - expected)}")
    if complete and expected - actual:
        failures.append(f"map is missing ids: {sorted(expected - actual)}")
    milestone = mapping.get("milestone")
    if complete:
        expected_milestone = graph["program"]["issue_projection"]["milestone"]
        if (
            not isinstance(milestone, dict)
            or not isinstance(milestone.get("number"), int)
            or milestone.get("title") != expected_milestone
            or not _is_nonempty_text(milestone.get("url"))
        ):
            failures.append(f"map milestone must identify {expected_milestone!r}")
    numbers: dict[int, str] = {}
    for object_id, row in issues.items():
        if not isinstance(row, dict) or not isinstance(row.get("number"), int) or not _is_nonempty_text(row.get("url")):
            failures.append(f"map row {object_id} is malformed")
            continue
        number = int(row["number"])
        if number in numbers:
            failures.append(f"map reuses issue #{number} for {numbers[number]} and {object_id}")
        numbers[number] = object_id
    if failures:
        raise ProgramError("GitHub map validation failed:\n- " + "\n- ".join(failures))


def marker(object_id: str) -> str:
    return f"<!-- positioning-program:{object_id} -->"


def repository_identity_for(repository: str, graph: dict[str, Any]) -> dict[str, Any] | None:
    identity = graph["repository_identity_by_slug"].get(repository)
    return identity if isinstance(identity, dict) else None


def public_repository_identity(identity: dict[str, Any]) -> dict[str, Any]:
    return {
        "identity": identity["identity"],
        "github_repository_id": identity["github_repository_id"],
        "canonical_slug": identity["canonical_slug"],
        "visibility": identity["visibility"],
        "default_branch": identity["default_branch"],
        "archived": identity["archived"],
        "source": identity["source"],
        "observed_at": identity.get("observed_at"),
    }


def receipt_marker(work_id: str) -> str:
    return f"<!-- positioning-receipt:{work_id} -->"


def acceptance_digest(packet: dict[str, Any]) -> str:
    return hashlib.sha256(str(packet["acceptance"]).encode("utf-8")).hexdigest()


def model_assignment_for(object_id: str, graph: dict[str, Any]) -> dict[str, str]:
    routing = graph["model_assignments"]
    if object_id == "PSP-ROOT":
        selected = routing["root"]
        basis = "root override"
    elif object_id in graph["phase_by_id"]:
        selected = routing["phases"][object_id]
        basis = "phase plan override"
    else:
        packet = graph["work_by_id"][object_id]
        overrides = routing["object_overrides"]
        sensitive = set(routing["sensitive_capabilities"])
        if object_id in overrides:
            selected = overrides[object_id]
            basis = "work override"
        elif packet["reasoning"] != "frontier_review" and sensitive.intersection(packet["capabilities"]):
            selected = routing["sensitive_assignment"]
            basis = "sensitive-capability override"
        elif packet["reasoning"] != "frontier_review" and packet["target_repo"].startswith("multi-repository:"):
            selected = routing["multi_repository_assignment"]
            basis = "multi-repository override"
        else:
            selected = routing["work_matrix"][packet["reasoning"]][packet["effect"]]
            basis = f"{packet['reasoning']}/{packet['effect']} matrix"
    return {
        "adapter": str(routing["adapter"]),
        "slug": str(selected["slug"]),
        "effort": str(selected["effort"]),
        "rationale": str(selected["rationale"]),
        "basis": basis,
        "authority": str(routing["authority"]),
        "catalog_validated_at": str(routing["catalog_validated_at"]),
        "unavailable_action": str(routing["unavailable_action"]),
    }


def chunk_assignment_for(chunk_id: str, graph: dict[str, Any]) -> dict[str, str]:
    chunk = graph["chunk_by_id"].get(chunk_id)
    if chunk is None:
        raise ProgramError(f"unknown execution chunk: {chunk_id}")
    selected = chunk["conductor"]
    routing = graph["model_assignments"]
    return {
        "adapter": str(routing["adapter"]),
        "slug": str(selected["slug"]),
        "effort": str(selected["effort"]),
        "rationale": str(selected["rationale"]),
        "basis": "execution-chunk conductor override",
        "authority": str(graph["execution_chunks"]["authority"]),
        "catalog_validated_at": str(routing["catalog_validated_at"]),
        "unavailable_action": str(routing["unavailable_action"]),
    }


def chunks_for_object(object_id: str, graph: dict[str, Any]) -> list[str]:
    if object_id == "PSP-ROOT":
        return [chunk["id"] for chunk in graph["chunks"]]
    if object_id in graph["work_by_id"]:
        return [graph["work_chunk"][object_id]]
    if object_id in graph["phase_by_id"]:
        phase_work = {packet["id"] for packet in graph["phase_by_id"][object_id]["work"]}
        return [chunk["id"] for chunk in graph["chunks"] if phase_work.intersection(graph["chunk_work"][chunk["id"]])]
    raise ProgramError(f"unknown program object: {object_id}")


def verify_model_assignments(graph: dict[str, Any]) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["codex", "debug", "models"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProgramError(f"live Codex model catalog is unavailable: {exc}") from exc
    if result.returncode != 0:
        raise ProgramError(result.stderr.strip() or "live Codex model catalog query failed")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ProgramError("live Codex model catalog returned invalid JSON") from exc
    entries = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise ProgramError("live Codex model catalog has an unsupported shape")
    catalog: dict[str, set[str]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not _is_nonempty_text(entry.get("slug")):
            continue
        levels = entry.get("supported_reasoning_levels")
        if not isinstance(levels, list):
            continue
        catalog[str(entry["slug"])] = {
            str(level if isinstance(level, str) else level.get("effort"))
            for level in levels
            if isinstance(level, str) or isinstance(level, dict)
        }
    failures: list[str] = []
    counts: dict[str, int] = {}
    chunk_counts: dict[str, int] = {}
    for object_id in graph["ordered_ids"]:
        assignment = model_assignment_for(object_id, graph)
        slug = assignment["slug"]
        effort = assignment["effort"]
        if slug not in catalog:
            failures.append(f"{object_id}: {slug!r} is absent from the live catalog")
        elif effort not in catalog[slug]:
            failures.append(f"{object_id}: {slug!r} does not support effort {effort!r}")
        key = f"{slug}/{effort}"
        counts[key] = counts.get(key, 0) + 1
    for chunk in graph["chunks"]:
        chunk_id = chunk["id"]
        assignment = chunk_assignment_for(chunk_id, graph)
        slug = assignment["slug"]
        effort = assignment["effort"]
        if slug not in catalog:
            failures.append(f"{chunk_id}: {slug!r} is absent from the live catalog")
        elif effort not in catalog[slug]:
            failures.append(f"{chunk_id}: {slug!r} does not support effort {effort!r}")
        key = f"{slug}/{effort}"
        chunk_counts[key] = chunk_counts.get(key, 0) + 1
    if failures:
        raise ProgramError("model assignment validation failed:\n- " + "\n- ".join(failures))
    return {
        "status": "ok",
        "objects": len(graph["ordered_ids"]),
        "execution_chunks": len(graph["chunks"]),
        "catalog_entries": len(catalog),
        "assignments": dict(sorted(counts.items())),
        "chunk_assignments": dict(sorted(chunk_counts.items())),
    }


def _issue_row(mapping: dict[str, Any], object_id: str) -> dict[str, Any] | None:
    row = (mapping.get("issues") or {}).get(object_id)
    return row if isinstance(row, dict) else None


def _link(mapping: dict[str, Any], object_id: str) -> str:
    row = _issue_row(mapping, object_id)
    return f"[#{row['number']}]({row['url']})" if row else f"`{object_id}`"


def _external_link(reference_id: str, graph: dict[str, Any]) -> str:
    row = graph["external"][reference_id]
    suffix = "pull" if row["kind"] == "pull_request" else "issues"
    url = f"https://github.com/{row['repository']}/{suffix}/{row['number']}"
    return f"[{reference_id} · {row['repository']}#{row['number']}]({url})"


def title_for(object_id: str, graph: dict[str, Any]) -> str:
    if object_id == "PSP-ROOT":
        return f"[PSP] {graph['program']['title']}"
    if object_id in graph["phase_by_id"]:
        return f"[PSP {object_id.removeprefix('PSP-')}] {graph['phase_by_id'][object_id]['title']}"
    return f"[{object_id}] {graph['work_by_id'][object_id]['title']}"


def _checklist(items: Iterable[str], mapping: dict[str, Any], labels: dict[str, str]) -> list[str]:
    return [f"- [ ] {_link(mapping, item)} — {labels[item]}" for item in items]


def _assignment_lines(object_id: str, graph: dict[str, Any]) -> list[str]:
    assignment = model_assignment_for(object_id, graph)
    return [
        "## Assigned model / effort",
        "",
        f"- Adapter: `{assignment['adapter']}`",
        f"- Model: `{assignment['slug']}`",
        f"- Effort: `{assignment['effort']}`",
        f"- Basis: {assignment['basis']}",
        f"- Rationale: {assignment['rationale']}",
        f"- Human override: {assignment['authority']}",
        f"- Catalog observed: `{assignment['catalog_validated_at']}`",
        f"- If unavailable: {assignment['unavailable_action']}",
    ]


def _chunk_lines(object_id: str, graph: dict[str, Any]) -> list[str]:
    chunk_ids = chunks_for_object(object_id, graph)
    heading = "## Execution chunk" if len(chunk_ids) == 1 else "## Execution chunks"
    lines = [heading, ""]
    for chunk_id in chunk_ids:
        chunk = graph["chunk_by_id"][chunk_id]
        assignment = chunk_assignment_for(chunk_id, graph)
        lines.append(f"- `{chunk_id}` — {chunk['title']} · conductor `{assignment['slug']}` / `{assignment['effort']}`")
    return lines


def body_for(object_id: str, graph: dict[str, Any], mapping: dict[str, Any]) -> str:
    if object_id == "PSP-ROOT":
        phases = [phase["id"] for phase in graph["phases"]]
        labels = {phase["id"]: phase["title"] for phase in graph["phases"]}
        return "\n".join(
            [
                "# Alpha-to-Omega program",
                "",
                graph["program"]["outcome"],
                "",
                *_assignment_lines(object_id, graph),
                "",
                *_chunk_lines(object_id, graph),
                "",
                "The tracked source is `institutio/positioning/program.yaml`; this issue is its GitHub index. "
                "Agents must claim bounded leaves through the Limen conduct broker before mutation.",
                "",
                "## Phase graph",
                "",
                *_checklist(phases, mapping, labels),
                "",
                "## Critical path",
                "",
                *[
                    f"{index}. {_link(mapping, item)}"
                    for index, item in enumerate(graph["program"]["critical_path"], 1)
                ],
                "",
                "## Terminal predicate",
                "",
                f"`{graph['program']['terminal_predicate']}`",
                "",
                "Closing this epic requires every phase predicate plus two unchanged Omega receipts. A persuasive narrative, "
                "website launch, or open branch is not completion.",
                "",
                marker(object_id),
            ]
        )
    if object_id in graph["phase_by_id"]:
        phase = graph["phase_by_id"][object_id]
        children = [packet["id"] for packet in phase["work"]]
        labels = {packet["id"]: packet["title"] for packet in phase["work"]}
        dependencies = phase.get("depends_on") or []
        try:
            phase_command = phase_proof_command(object_id, graph)
        except ProgramError:
            phase_command = "UNAVAILABLE: no unambiguous executable proof contract in manifest"
        return "\n".join(
            [
                f"# {object_id} — {phase['title']}",
                "",
                phase["outcome"],
                "",
                *_assignment_lines(object_id, graph),
                "",
                *_chunk_lines(object_id, graph),
                "",
                "## Upstream phases",
                "",
                *[f"- {_link(mapping, item)}" for item in dependencies],
                *(["- None"] if not dependencies else []),
                "",
                "## Work packets",
                "",
                *_checklist(children, mapping, labels),
                "",
                "## Exit gate",
                "",
                phase["exit_gate"],
                "",
                "## Executable exit-gate predicate",
                "",
                f"`{phase_command}`",
                "",
                "The gate requires a passing, content-pinned phase receipt; child closure alone is not sufficient, and "
                "the phase issue may remain open while the gate establishes closure readiness. The canonical definition "
                "lives in `institutio/positioning/program.yaml`.",
                "",
                marker(object_id),
            ]
        )
    packet = graph["work_by_id"][object_id]
    assignment = model_assignment_for(object_id, graph)
    chunk_id = graph["work_chunk"][object_id]
    chunk = graph["chunk_by_id"][chunk_id]
    phase_id = graph["work_phase"][object_id]
    dependencies = packet.get("depends_on") or []
    externals = packet.get("external_dependencies") or []
    gates = packet.get("human_gates") or []
    repository_identity = repository_identity_for(packet["target_repo"], graph)
    target_line = f"**Target:** `{packet['target_repo']}` · " + ", ".join(
        f"`{path}`" for path in packet["target_paths"]
    )
    if repository_identity is not None:
        target_line += (
            f" · stable GitHub repository ID `{repository_identity['github_repository_id']}` "
            f"(resolved `{repository_identity['observed_at']}`)"
        )
    authority_line = (
        "- This corrected leaf runs in a fresh human-protected Codex task; "
        "direct human session authority is valid, and no non-Codex canary is required."
        if object_id == "PSP-P00-W07"
        else "- GitHub issue is not a lease; a registered native lane must obtain current broker authority before mutation."
    )
    lines = [
        f"# {object_id} — {packet['title']}",
        "",
        f"**Parent:** {_link(mapping, phase_id)}",
        f"**Execution chunk:** `{chunk_id}` — {chunk['title']}",
        target_line,
        "",
        "## Outcome",
        "",
        packet["outcome"],
        "",
        "## Deliverables",
        "",
        *[f"- {item}" for item in packet["deliverables"]],
        "",
        "## Dependencies",
        "",
        *([f"- Program: {_link(mapping, item)}" for item in dependencies] or ["- Program: none"]),
        *[
            f"- Live reference: {_external_link(item, graph)} — {graph['external'][item]['purpose']}"
            for item in externals
        ],
        "",
        "## Effect and authority",
        "",
        f"- Effect: `{packet['effect']}`",
        f"- Reasoning class: `{packet['reasoning']}`",
        f"- Assigned model: `{assignment['slug']}` via `{assignment['adapter']}`",
        f"- Assigned effort: `{assignment['effort']}`",
        f"- Assignment basis: {assignment['basis']} — {assignment['rationale']}",
        f"- Model authority: {assignment['authority']}",
        f"- Catalog observed: `{assignment['catalog_validated_at']}`",
        f"- If unavailable: {assignment['unavailable_action']}",
        f"- Required capabilities: {', '.join(f'`{item}`' for item in packet['capabilities'])}",
        authority_line,
    ]
    if gates:
        lines += [
            "- Human gates:",
            *[
                f"  - `{gate}` — {graph['gates'][gate]['gate']}"
                + (
                    " (" + ", ".join(_external_link(ref, graph) for ref in graph["gates"][gate]["references"]) + ")"
                    if graph["gates"][gate]["references"]
                    else " (must be materialized in the named registry before the external act)"
                )
                for gate in gates
            ],
        ]
    else:
        lines.append("- Human gates: none")
    lines += [
        "",
        "## Acceptance condition",
        "",
        packet["acceptance"],
        "",
        "## Executable completion predicate",
        "",
        f"`{packet['predicate']}`",
        "",
        "The command passes only when the latest marked GitHub receipt matches this acceptance condition, records a "
        "non-circular successful predicate, and carries durable authority, exact-head, evidence, and rollback data.",
        "",
        "## Return evidence",
        "",
        *[f"- {item}" for item in packet["return_evidence"]],
        "",
        "## Rollback / return path",
        "",
        packet["rollback"],
        "",
        "Close only after the predicate passes and the durable receipt is linked. New work must enter the manifest through review, "
        "not remain only in an issue comment or agent transcript.",
        "",
        marker(object_id),
    ]
    return "\n".join(lines)


def labels_for(object_id: str, graph: dict[str, Any]) -> list[str]:
    projection = graph["program"]["issue_projection"]
    assignment = model_assignment_for(object_id, graph)
    routing_labels = [f"model:{assignment['slug']}", f"effort:{assignment['effort']}"]
    if object_id == "PSP-ROOT":
        return [projection["program_label"], "plan", "meta", *routing_labels]
    if object_id in graph["phase_by_id"]:
        return [projection["program_label"], projection["phase_label"], "plan", "meta", *routing_labels]
    labels = [projection["program_label"], projection["work_label"], "lane:fleet", *routing_labels]
    if graph["work_by_id"][object_id]["effect"] == "write":
        labels.append("lifecycle:delivery")
    return labels


def _gh(args: list[str], *, input_value: object | None = None, allow_failure: bool = False) -> Any:
    result = subprocess.run(
        ["gh", *args],
        input=json.dumps(input_value) if input_value is not None else None,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if result.returncode != 0:
        if allow_failure:
            return None
        raise ProgramError(result.stderr.strip() or result.stdout.strip() or f"gh {' '.join(args)} failed")
    if not result.stdout.strip():
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ProgramError(f"GitHub returned non-JSON output for {' '.join(args)}") from exc


def _api(
    repository: str, path: str, *, method: str = "GET", payload: object | None = None, allow_failure: bool = False
) -> Any:
    args = ["api", f"repos/{repository}/{path}"]
    if method != "GET":
        args += ["--method", method]
    if payload is not None:
        args += ["--input", "-"]
    return _gh(args, input_value=payload, allow_failure=allow_failure)


def verify_repository_identities(graph: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    resolved: list[dict[str, Any]] = []
    identities = graph["repository_identity_by_slug"]
    for canonical_slug, identity in sorted(identities.items()):
        repository_id = int(identity["github_repository_id"])
        value = _gh(["api", f"repositories/{repository_id}"])
        if not isinstance(value, dict):
            failures.append(f"repository ID {repository_id} returned a non-object")
            continue
        live_visibility = str(value.get("visibility") or ("private" if value.get("private") else "public"))
        checks = {
            "id": (value.get("id"), repository_id),
            "full_name": (value.get("full_name"), canonical_slug),
            "visibility": (live_visibility, identity["visibility"]),
            "default_branch": (value.get("default_branch"), identity["default_branch"]),
            "archived": (value.get("archived"), identity["archived"]),
        }
        for field, (actual, expected) in checks.items():
            if actual != expected:
                failures.append(
                    f"repository ID {repository_id} {field} drift: expected {expected!r}, observed {actual!r}"
                )
        resolved.append(
            {
                **public_repository_identity(identity),
                "html_url": value.get("html_url"),
                "resolved_full_name": value.get("full_name"),
            }
        )
    if failures:
        raise ProgramError("repository identity validation failed:\n- " + "\n- ".join(failures))
    return {"status": "ok", "repositories": resolved}


def _pages(repository: str, path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        separator = "&" if "?" in path else "?"
        value = _api(repository, f"{path}{separator}per_page=100&page={page}")
        if not isinstance(value, list):
            raise ProgramError(f"GitHub list endpoint returned a non-list: {path}")
        rows.extend(item for item in value if isinstance(item, dict))
        if len(value) < 100:
            return rows
        page += 1


def _ensure_labels(graph: dict[str, Any], *, apply: bool) -> list[str]:
    repository = graph["program"]["repository"]
    existing = {str(row.get("name") or "") for row in _pages(repository, "labels")}
    projection = graph["program"]["issue_projection"]
    definitions = {
        projection["program_label"]: ("1f6feb", "Production-systems positioning and commercial foundry program"),
        projection["phase_label"]: ("8250df", "Program phase / aggregate exit gate"),
        projection["work_label"]: (
            "0e8a16",
            "Atomic cross-agent work packet with model assignment and executable predicate",
        ),
    }
    model_colors = {
        "gpt-5.4-mini": "6b7280",
        "gpt-5.6-luna": "06b6d4",
        "gpt-5.6-terra": "3b82f6",
        "gpt-5.6-sol": "8b5cf6",
    }
    effort_colors = {
        "low": "c2e0c6",
        "medium": "0e8a16",
        "high": "fbca04",
        "xhigh": "f97316",
        "max": "d93f0b",
        "ultra": "5319e7",
    }
    for object_id in graph["ordered_ids"]:
        assignment = model_assignment_for(object_id, graph)
        slug = assignment["slug"]
        effort = assignment["effort"]
        definitions[f"model:{slug}"] = (model_colors.get(slug, "6b7280"), f"Assigned execution model: {slug}")
        definitions[f"effort:{effort}"] = (
            effort_colors.get(effort, "6b7280"),
            f"Assigned reasoning effort: {effort}",
        )
    missing = [name for name in definitions if name not in existing]
    if apply:
        for name in missing:
            color, description = definitions[name]
            _api(
                repository, "labels", method="POST", payload={"name": name, "color": color, "description": description}
            )
    return missing


def _ensure_milestone(graph: dict[str, Any], *, apply: bool) -> dict[str, Any] | None:
    repository = graph["program"]["repository"]
    title = graph["program"]["issue_projection"]["milestone"]
    rows = _pages(repository, "milestones?state=all")
    for row in rows:
        if row.get("title") == title:
            return {"number": int(row["number"]), "title": title, "url": row.get("html_url")}
    if not apply:
        return None
    row = _api(
        repository,
        "milestones",
        method="POST",
        payload={
            "title": title,
            "description": "Alpha-to-Omega execution graph for the production-systems positioning, commercial delivery, and foundry program.",
        },
    )
    return {"number": int(row["number"]), "title": title, "url": row.get("html_url")}


def fetch_program_issues(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    repository = graph["program"]["repository"]
    # The marker, not a mutable label, is the projection identity. Scan every issue in a stable
    # creation order so label drift cannot hide duplicates or orphans from verification or sync.
    rows = _pages(repository, "issues?state=all&sort=created&direction=asc")
    by_id: dict[str, dict[str, Any]] = {}
    duplicates: dict[str, list[int]] = {}
    for row in rows:
        if "pull_request" in row:
            continue
        found = MARKER_RE.findall(str(row.get("body") or ""))
        for object_id in found:
            if object_id in by_id:
                duplicates.setdefault(object_id, [int(by_id[object_id]["number"])]).append(int(row["number"]))
            else:
                by_id[object_id] = row
    if duplicates:
        raise ProgramError(f"duplicate program issue markers: {duplicates}")
    return by_id


def recover_mapped_issues(
    graph: dict[str, Any],
    mapping: dict[str, Any],
    remote: dict[str, dict[str, Any]],
    *,
    object_ids: Iterable[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Recover label or marker drift by exact mapped number without creating duplicates."""
    repository = graph["program"]["repository"]
    recovered = dict(remote)
    candidates = graph["ordered_ids"] if object_ids is None else object_ids
    for object_id in candidates:
        if object_id in recovered:
            continue
        map_row = _issue_row(mapping, object_id)
        if map_row is None:
            continue
        row = _api(repository, f"issues/{int(map_row['number'])}", allow_failure=True)
        if not isinstance(row, dict) or "pull_request" in row:
            continue
        found = MARKER_RE.findall(str(row.get("body") or ""))
        if found and found != [object_id]:
            raise ProgramError(
                f"mapped {object_id} issue #{map_row['number']} carries conflicting program markers: {found}"
            )
        recovered[object_id] = row
    return recovered


def receipt_template(work_id: str, graph: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
    if work_id not in graph["work_by_id"]:
        raise ProgramError(f"unknown work id: {work_id}")
    validate_map(mapping, graph, complete=True)
    packet = graph["work_by_id"][work_id]
    observed_heads: dict[str, str]
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "work_id": work_id,
        "acceptance_sha256": acceptance_digest(packet),
        "outcome": "succeeded",
        "authority": {
            "kind": "broker",
            "run_id": "REPLACE_WITH_RUN_ID",
            "lease_id": "REPLACE_WITH_LEASE_ID",
            "executor": "REPLACE_WITH_NATIVE_AGENT_IDENTITY",
        },
        "changed_paths": [],
        "predicate": {
            "command": "REPLACE_WITH_NON_CIRCULAR_EXECUTABLE_PREDICATE",
            "exit_code": 0,
            "output_sha256": "REPLACE_WITH_64_CHARACTER_SHA256",
            "observed_at": "REPLACE_WITH_RFC3339_TIMESTAMP",
        },
        "evidence_urls": [mapping["issues"][work_id]["url"]],
        "rollback": {"invoked": False, "state": "not needed"},
    }
    if packet["target_repo"].startswith("multi-repository:"):
        receipt["resolved_repositories"] = ["REPLACE_WITH_OWNER/REPOSITORY"]
        observed_heads = {"REPLACE_WITH_OWNER/REPOSITORY": "REPLACE_WITH_EXACT_40_CHARACTER_GIT_HEAD"}
    else:
        observed_heads = {packet["target_repo"]: "REPLACE_WITH_EXACT_40_CHARACTER_GIT_HEAD"}
    receipt["observed_heads"] = observed_heads
    return receipt


def validate_work_receipt(receipt: object, work_id: str, graph: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    packet = graph["work_by_id"].get(work_id)
    if packet is None:
        raise ProgramError(f"unknown work id: {work_id}")
    if not isinstance(receipt, dict):
        raise ProgramError(f"{work_id} receipt must be a JSON object")
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        failures.append(f"schema_version must be {RECEIPT_SCHEMA}")
    if receipt.get("work_id") != work_id:
        failures.append(f"work_id must be {work_id}")
    if receipt.get("acceptance_sha256") != acceptance_digest(packet):
        failures.append("acceptance_sha256 is stale or incorrect")
    if receipt.get("outcome") != "succeeded":
        failures.append("outcome must be succeeded")

    authority = receipt.get("authority")
    if not isinstance(authority, dict):
        failures.append("authority must be a mapping")
    else:
        kind = authority.get("kind")
        if kind == "broker":
            for key in ("run_id", "lease_id", "executor"):
                if not _is_nonempty_text(authority.get(key)):
                    failures.append(f"broker authority.{key} must be non-empty")
        elif kind == "direct_human_session":
            for key in ("session_id", "executor"):
                if not _is_nonempty_text(authority.get(key)):
                    failures.append(f"direct authority.{key} must be non-empty")
            if authority.get("human_protected") is not True:
                failures.append("direct authority must record human_protected=true")
        else:
            failures.append("authority.kind must be broker or direct_human_session")

    observed_heads = receipt.get("observed_heads")
    expected_repository = str(packet["target_repo"])
    if expected_repository.startswith("multi-repository:"):
        resolved = receipt.get("resolved_repositories")
        if not _is_text_list(resolved, nonempty=True) or any(not REPOSITORY_RE.fullmatch(item) for item in resolved):
            failures.append("resolved_repositories must be a non-empty list of concrete owner/repo targets")
            resolved_set: set[str] = set()
        else:
            resolved_set = set(resolved)
            if len(resolved_set) != len(resolved):
                failures.append("resolved_repositories must not contain duplicates")
        if not isinstance(observed_heads, dict) or set(observed_heads) != resolved_set:
            failures.append("observed_heads must contain exactly every resolved repository")
    elif not isinstance(observed_heads, dict) or set(observed_heads) != {expected_repository}:
        failures.append(f"observed_heads must contain exactly the packet target repository {expected_repository!r}")
    if isinstance(observed_heads, dict):
        for repository, head in observed_heads.items():
            if not _is_nonempty_text(repository) or not isinstance(head, str) or not HEAD_RE.fullmatch(head):
                failures.append(f"observed_heads has invalid exact head for {repository!r}")

    changed_paths = receipt.get("changed_paths")
    if not _is_text_list(changed_paths):
        failures.append("changed_paths must be a text list")

    predicate = receipt.get("predicate")
    if not isinstance(predicate, dict):
        failures.append("predicate must be a mapping")
    else:
        command = predicate.get("command")
        if not _is_nonempty_text(command):
            failures.append("predicate.command must be non-empty")
        elif "--verify-work" in str(command):
            failures.append("predicate.command cannot call the receipt verifier itself")
        if predicate.get("exit_code") != 0:
            failures.append("predicate.exit_code must be zero")
        output_sha256 = predicate.get("output_sha256")
        if not isinstance(output_sha256, str) or not DIGEST_RE.fullmatch(output_sha256):
            failures.append("predicate.output_sha256 must be a lowercase SHA-256 digest")
        observed_at = predicate.get("observed_at")
        if not isinstance(observed_at, str) or not RFC3339_RE.fullmatch(observed_at):
            failures.append("predicate.observed_at must be RFC3339")

    evidence_urls = receipt.get("evidence_urls")
    if not _is_text_list(evidence_urls, nonempty=True):
        failures.append("evidence_urls must be a non-empty text list")
    else:
        for url in evidence_urls:
            if not URL_RE.fullmatch(url):
                failures.append(f"evidence URL must use https: {url!r}")

    rollback = receipt.get("rollback")
    if (
        not isinstance(rollback, dict)
        or not isinstance(rollback.get("invoked"), bool)
        or not _is_nonempty_text(rollback.get("state"))
    ):
        failures.append("rollback must record boolean invoked and non-empty state")
    if failures:
        raise ProgramError(f"{work_id} receipt validation failed:\n- " + "\n- ".join(failures))
    return receipt


def phase_proof_command(phase_id: str, graph: dict[str, Any]) -> str:
    phase = graph["phase_by_id"].get(phase_id)
    if phase is None:
        raise ProgramError(f"unknown phase id: {phase_id}")
    command = str(phase.get("exit_predicate") or "").strip()
    expected = f"python3 scripts/positioning-program.py --phase-proof {phase_id}"
    if command != expected:
        raise ProgramError(f"{phase_id} has no valid manifest-owned phase proof predicate")
    return command


def phase_terminal_scope(graph: dict[str, Any]) -> tuple[set[str], set[str]]:
    terminal_work = terminal_omega_work_ids(graph)
    terminal_phases = {graph["work_phase"][work_id] for work_id in terminal_work}
    return terminal_work, terminal_phases


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _stable_remote_row(object_id: str, row: dict[str, Any], *, include_state: bool = True) -> dict[str, Any]:
    body = str(row.get("body") or "")
    labels = sorted(
        str(item.get("name") or "") for item in row.get("labels") or [] if isinstance(item, dict)
    )
    milestone = row.get("milestone")
    projection = {
        "id": object_id,
        "number": row.get("number"),
        "title": str(row.get("title") or ""),
        "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "markers": sorted(MARKER_RE.findall(body)),
        "labels": labels,
        "milestone": milestone.get("number") if isinstance(milestone, dict) else None,
    }
    if include_state:
        projection["state"] = str(row.get("state") or "").lower()
    return projection


def _phase_remote_state_digest(
    phase_id: str, graph: dict[str, Any], mapping: dict[str, Any], remote: dict[str, dict[str, Any]]
) -> str:
    phase = graph["phase_by_id"][phase_id]
    object_ids = [phase_id, *(packet["id"] for packet in phase["work"])]
    projection = [
        _stable_remote_row(phase_id, remote[phase_id], include_state=False),
        *[_stable_remote_row(object_id, remote[object_id]) for object_id in object_ids[1:]],
    ]
    return _canonical_digest(projection)


def _phase_parity_digest(
    phase_id: str, graph: dict[str, Any], mapping: dict[str, Any], remote: dict[str, dict[str, Any]]
) -> str:
    phase = graph["phase_by_id"][phase_id]
    object_ids = [phase_id, *(packet["id"] for packet in phase["work"])]
    expected = {
        object_id: {
            "number": mapping["issues"][object_id]["number"],
            "url": mapping["issues"][object_id]["url"],
            "title": title_for(object_id, graph),
            "body_sha256": hashlib.sha256(body_for(object_id, graph, mapping).encode("utf-8")).hexdigest(),
            "labels": sorted(labels_for(object_id, graph)),
        }
        for object_id in object_ids
    }
    observed = {
        object_id: _stable_remote_row(object_id, remote[object_id], include_state=False) for object_id in object_ids
    }
    return _canonical_digest({"expected": expected, "observed": observed})


def _phase_binding_values(
    phase_id: str,
    graph: dict[str, Any],
    mapping: dict[str, Any],
    remote: dict[str, dict[str, Any]] | None = None,
    child_receipts: dict[str, dict[str, Any]] | None = None,
) -> dict[str, str]:
    if remote is None:
        remote = recover_mapped_issues(graph, mapping, fetch_program_issues(graph))
    return {
        "child_receipt_digest": _canonical_digest(child_receipts)
        if child_receipts is not None
        else _phase_child_receipt_digest(phase_id, graph, mapping),
        "remote_state_digest": _phase_remote_state_digest(phase_id, graph, mapping, remote),
        "parity_digest": _phase_parity_digest(phase_id, graph, mapping, remote),
    }


def _phase_child_receipt_digest(phase_id: str, graph: dict[str, Any], mapping: dict[str, Any]) -> str:
    receipts = {
        packet["id"]: fetch_work_receipt(packet["id"], graph, mapping)[0]
        for packet in graph["phase_by_id"][phase_id]["work"]
    }
    return _canonical_digest(receipts)


def validate_phase_receipt(
    receipt: object,
    phase_id: str,
    graph: dict[str, Any],
    *,
    child_receipt_digest: str,
    remote_state_digest: str,
    parity_digest: str,
) -> dict[str, Any]:
    failures: list[str] = []
    phase = graph["phase_by_id"].get(phase_id)
    if phase is None:
        raise ProgramError(f"unknown phase id: {phase_id}")
    if not isinstance(receipt, dict):
        raise ProgramError(f"{phase_id} phase receipt must be a JSON object")
    if receipt.get("schema_version") != PHASE_RECEIPT_SCHEMA:
        failures.append(f"schema_version must be {PHASE_RECEIPT_SCHEMA}")
    if receipt.get("phase_id") != phase_id:
        failures.append(f"phase_id must be {phase_id}")
    if receipt.get("status") != "pass":
        failures.append("status must be pass")
    expected_gate_digest = hashlib.sha256(str(phase["exit_gate"]).encode("utf-8")).hexdigest()
    if receipt.get("exit_gate_sha256") != expected_gate_digest:
        failures.append("exit_gate_sha256 is stale or incorrect")
    expected_command = phase_proof_command(phase_id, graph)
    predicate = receipt.get("predicate")
    if not isinstance(predicate, dict):
        failures.append("predicate must be a mapping")
    else:
        command = predicate.get("command")
        if not _is_nonempty_text(command):
            failures.append("predicate.command must be non-empty")
        elif command != expected_command:
            failures.append(f"predicate.command must match manifest proof contract {expected_command!r}")
        if predicate.get("exit_code") != 0:
            failures.append("predicate.exit_code must be zero")
        if not isinstance(predicate.get("output_sha256"), str) or not DIGEST_RE.fullmatch(predicate["output_sha256"]):
            failures.append("predicate.output_sha256 must be a lowercase SHA-256 digest")
        if not isinstance(predicate.get("observed_at"), str) or not RFC3339_RE.fullmatch(predicate["observed_at"]):
            failures.append("predicate.observed_at must be RFC3339")
    evidence_urls = receipt.get("evidence_urls")
    if not _is_text_list(evidence_urls, nonempty=True):
        failures.append("evidence_urls must be a non-empty text list")
    elif any(not URL_RE.fullmatch(url) for url in evidence_urls):
        failures.append("evidence URLs must use https")
    observed_heads = receipt.get("observed_heads")
    repository = str(graph["program"]["repository"])
    if not isinstance(observed_heads, dict) or set(observed_heads) != {repository}:
        failures.append(f"observed_heads must contain exactly the program repository {repository!r}")
    elif not HEAD_RE.fullmatch(str(observed_heads[repository])):
        failures.append("observed_heads must record an exact 40-character head")
    for field, expected, label in (
        ("child_receipts_sha256", child_receipt_digest, "child receipt digest"),
        ("remote_state_sha256", remote_state_digest, "remote state digest"),
        ("parity_sha256", parity_digest, "parity digest"),
    ):
        actual = receipt.get(field)
        if not isinstance(actual, str) or not DIGEST_RE.fullmatch(actual):
            failures.append(f"{field} must be a lowercase SHA-256 digest")
        elif actual != expected:
            failures.append(f"{label} is stale or incorrect")
    if failures:
        raise ProgramError(f"{phase_id} phase receipt validation failed:\n- " + "\n- ".join(failures))
    return receipt


def fetch_phase_receipt(
    phase_id: str,
    graph: dict[str, Any],
    mapping: dict[str, Any],
    *,
    child_receipt_digest: str | None = None,
    remote_state_digest: str | None = None,
    parity_digest: str | None = None,
    remote: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], str]:
    if phase_id not in graph["phase_by_id"]:
        raise ProgramError(f"unknown phase id: {phase_id}")
    validate_map(mapping, graph, complete=True)
    repository = graph["program"]["repository"]
    issue_number = int(mapping["issues"][phase_id]["number"])
    comments = _pages(repository, f"issues/{issue_number}/comments")
    marked = [row for row in comments if f"positioning-phase-receipt:{phase_id}" in str(row.get("body") or "")]
    if not marked:
        raise ProgramError(f"{phase_id} has no marked phase exit-gate receipt")
    latest = max(marked, key=lambda row: int(row.get("id") or 0))
    body = str(latest.get("body") or "")
    matches = [match for match in PHASE_RECEIPT_BLOCK_RE.findall(body) if match[0] == phase_id]
    if len(matches) != 1:
        raise ProgramError(f"{phase_id} latest marked comment must contain exactly one JSON phase receipt block")
    try:
        receipt = json.loads(matches[0][1])
    except json.JSONDecodeError as exc:
        raise ProgramError(f"{phase_id} latest marked phase receipt is invalid JSON: {exc}") from exc
    bindings = _phase_binding_values(phase_id, graph, mapping, remote)
    if child_receipt_digest is None:
        child_receipt_digest = bindings["child_receipt_digest"]
    if remote_state_digest is None:
        remote_state_digest = bindings["remote_state_digest"]
    if parity_digest is None:
        parity_digest = bindings["parity_digest"]
    return (
        validate_phase_receipt(
            receipt,
            phase_id,
            graph,
            child_receipt_digest=child_receipt_digest,
            remote_state_digest=remote_state_digest,
            parity_digest=parity_digest,
        ),
        str(latest.get("html_url") or ""),
    )


def verify_phase(phase_id: str, graph: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
    remote = recover_mapped_issues(graph, mapping, fetch_program_issues(graph))
    receipt, comment_url = fetch_phase_receipt(phase_id, graph, mapping, remote=remote)
    canonical = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "status": "pass",
        "phase_id": phase_id,
        "issue": mapping["issues"][phase_id],
        "receipt_url": comment_url,
        "receipt_sha256": hashlib.sha256(canonical).hexdigest(),
    }


def _validate_phase_projection(
    phase_id: str, graph: dict[str, Any], mapping: dict[str, Any], remote: dict[str, dict[str, Any]]
) -> None:
    phase = graph["phase_by_id"][phase_id]
    object_ids = [phase_id, *(packet["id"] for packet in phase["work"])]
    failures: list[str] = []
    for object_id in object_ids:
        row = remote.get(object_id)
        if not isinstance(row, dict):
            failures.append(f"{phase_id} missing remote object {object_id}")
            continue
        map_row = mapping["issues"][object_id]
        if int(row.get("number") or 0) != int(map_row["number"]):
            failures.append(f"{object_id} issue number differs from map")
        if str(row.get("title") or "") != title_for(object_id, graph):
            failures.append(f"{object_id} title drift")
        if str(row.get("body") or "") != body_for(object_id, graph, mapping):
            failures.append(f"{object_id} body drift")
        current_labels = {
            str(item.get("name") or "") for item in row.get("labels") or [] if isinstance(item, dict)
        }
        expected_routing = {
            label for label in labels_for(object_id, graph) if label.startswith(("model:", "effort:"))
        }
        current_routing = {
            label
            for label in current_labels
            if label.startswith(("model:", "effort:"))
        }
        if current_routing != expected_routing:
            failures.append(f"{object_id} routing label drift")
        if not set(labels_for(object_id, graph)).issubset(current_labels):
            failures.append(f"{object_id} required label drift")
        milestone = row.get("milestone")
        if not isinstance(milestone, dict) or int(milestone.get("number") or 0) != int(mapping["milestone"]["number"]):
            failures.append(f"{object_id} milestone drift")
    expected_children = {packet["id"] for packet in phase["work"]}
    orphan_prefix = f"{phase_id}-W"
    for remote_id, row in remote.items():
        markers = MARKER_RE.findall(str(row.get("body") or "")) if isinstance(row, dict) else []
        orphans = [marker_id for marker_id in markers if marker_id.startswith(orphan_prefix) and marker_id not in expected_children]
        if orphans:
            failures.append(f"{phase_id} has orphan phase-local markers {sorted(orphans)}")
    if failures:
        raise ProgramError(f"{phase_id} phase projection failed:\n- " + "\n- ".join(failures))


def phase_proof(phase_id: str, graph: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
    if phase_id not in graph["phase_by_id"]:
        raise ProgramError(f"unknown phase id: {phase_id}")
    phase_proof_command(phase_id, graph)
    validate_map(mapping, graph, complete=True)
    initial_remote = fetch_program_issues(graph)
    phase_object_ids = [
        phase_id,
        *(packet["id"] for packet in graph["phase_by_id"][phase_id]["work"]),
    ]
    remote = recover_mapped_issues(graph, mapping, initial_remote, object_ids=phase_object_ids)
    _validate_phase_projection(phase_id, graph, mapping, remote)
    phase = graph["phase_by_id"][phase_id]
    child_receipts: dict[str, dict[str, Any]] = {}
    child_evidence: dict[str, str] = {}
    failures: list[str] = []
    for packet in phase["work"]:
        work_id = packet["id"]
        if str(remote[work_id].get("state") or "").lower() != "closed":
            failures.append(f"{work_id} is not closed")
            continue
        try:
            child_receipts[work_id], child_evidence[work_id] = fetch_work_receipt(work_id, graph, mapping)
        except ProgramError as exc:
            failures.append(str(exc))
    if failures:
        raise ProgramError(f"{phase_id} phase proof failed:\n- " + "\n- ".join(failures))
    bindings = _phase_binding_values(phase_id, graph, mapping, remote, child_receipts)
    return {
        "status": "pass",
        "phase_id": phase_id,
        "exit_gate_sha256": hashlib.sha256(str(phase["exit_gate"]).encode("utf-8")).hexdigest(),
        "child_receipts_sha256": _canonical_digest(child_receipts),
        "child_receipt_evidence": child_evidence,
        "remote_state_sha256": bindings["remote_state_digest"],
        "parity_sha256": bindings["parity_digest"],
    }


def phase_receipt_template(phase_id: str, graph: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
    if phase_id not in graph["phase_by_id"]:
        raise ProgramError(f"unknown phase id: {phase_id}")
    validate_map(mapping, graph, complete=True)
    remote = recover_mapped_issues(graph, mapping, fetch_program_issues(graph))
    bindings = _phase_binding_values(phase_id, graph, mapping, remote)
    phase = graph["phase_by_id"][phase_id]
    return {
        "schema_version": PHASE_RECEIPT_SCHEMA,
        "phase_id": phase_id,
        "status": "pass",
        "exit_gate_sha256": hashlib.sha256(str(phase["exit_gate"]).encode("utf-8")).hexdigest(),
        "observed_heads": {graph["program"]["repository"]: "REPLACE_WITH_EXACT_40_CHARACTER_GIT_HEAD"},
        "child_receipts_sha256": bindings["child_receipt_digest"],
        "remote_state_sha256": bindings["remote_state_digest"],
        "parity_sha256": bindings["parity_digest"],
        "predicate": {
            "command": phase_proof_command(phase_id, graph),
            "exit_code": 0,
            "output_sha256": "REPLACE_WITH_64_CHARACTER_SHA256",
            "observed_at": "REPLACE_WITH_RFC3339_TIMESTAMP",
        },
        "evidence_urls": [mapping["issues"][phase_id]["url"]],
    }


def fetch_work_receipt(work_id: str, graph: dict[str, Any], mapping: dict[str, Any]) -> tuple[dict[str, Any], str]:
    if work_id not in graph["work_by_id"]:
        raise ProgramError(f"unknown work id: {work_id}")
    validate_map(mapping, graph, complete=True)
    repository = graph["program"]["repository"]
    issue_number = int(mapping["issues"][work_id]["number"])
    comments = _pages(repository, f"issues/{issue_number}/comments")
    marked = [row for row in comments if receipt_marker(work_id) in str(row.get("body") or "")]
    if not marked:
        raise ProgramError(f"{work_id} has no marked completion receipt")
    latest = max(marked, key=lambda row: int(row.get("id") or 0))
    body = str(latest.get("body") or "")
    matches = [match for match in RECEIPT_BLOCK_RE.findall(body) if match[0] == work_id]
    if len(matches) != 1:
        raise ProgramError(f"{work_id} latest marked comment must contain exactly one JSON receipt block")
    try:
        receipt = json.loads(matches[0][1])
    except json.JSONDecodeError as exc:
        raise ProgramError(f"{work_id} latest marked receipt is invalid JSON: {exc}") from exc
    return validate_work_receipt(receipt, work_id, graph), str(latest.get("html_url") or "")


def verify_work(work_id: str, graph: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
    receipt, comment_url = fetch_work_receipt(work_id, graph, mapping)
    canonical = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "status": "pass",
        "work_id": work_id,
        "issue": mapping["issues"][work_id],
        "receipt_url": comment_url,
        "receipt_sha256": hashlib.sha256(canonical).hexdigest(),
    }


def closure_integrity(
    graph: dict[str, Any],
    mapping: dict[str, Any],
    remote: dict[str, dict[str, Any]],
    *,
    excluded_work_ids: set[str] | None = None,
    excluded_phase_ids: set[str] | None = None,
    phase_bindings: dict[str, dict[str, str]] | None = None,
) -> dict[str, str]:
    excluded_work_ids = excluded_work_ids or set()
    excluded_phase_ids = excluded_phase_ids or set()
    closed = {object_id for object_id, row in remote.items() if str(row.get("state") or "").lower() == "closed"}
    failures: list[str] = []
    receipt_urls: dict[str, str] = {}
    for work_id in sorted((closed & set(graph["work_by_id"])) - excluded_work_ids):
        try:
            _receipt, receipt_urls[work_id] = fetch_work_receipt(work_id, graph, mapping)
        except ProgramError as exc:
            failures.append(str(exc))
    for phase_id, phase in graph["phase_by_id"].items():
        if phase_id not in closed or phase_id in excluded_phase_ids:
            continue
        missing_children = [packet["id"] for packet in phase["work"] if packet["id"] not in closed]
        if missing_children:
            failures.append(f"{phase_id} is closed before child issues {missing_children}")
            continue
        try:
            phase_kwargs = dict(
                phase_bindings.get(phase_id)
                if phase_bindings and phase_id in phase_bindings
                else _phase_binding_values(phase_id, graph, mapping, remote)
            )
            phase_kwargs["remote"] = remote
            _receipt, receipt_urls[phase_id] = fetch_phase_receipt(phase_id, graph, mapping, **phase_kwargs)
        except ProgramError as exc:
            failures.append(str(exc))
    if "PSP-ROOT" in closed:
        missing_phases = [phase["id"] for phase in graph["phases"] if phase["id"] not in closed]
        if missing_phases:
            failures.append(f"PSP-ROOT is closed before phase issues {missing_phases}")
    if failures:
        raise ProgramError("remote closure integrity failed:\n- " + "\n- ".join(failures))
    return receipt_urls


def _write_map(
    path: Path, graph: dict[str, Any], milestone: dict[str, Any], remote: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    value = {
        "schema_version": MAP_SCHEMA,
        "repository": graph["program"]["repository"],
        "milestone": milestone,
        "issues": {
            object_id: {"number": int(remote[object_id]["number"]), "url": str(remote[object_id]["html_url"])}
            for object_id in graph["ordered_ids"]
            if object_id in remote
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return value


def sync(
    graph: dict[str, Any],
    mapping: dict[str, Any],
    *,
    apply: bool,
    map_path: Path,
    index_path: Path,
    chunks_path: Path = DEFAULT_CHUNKS,
) -> dict[str, Any]:
    repository = graph["program"]["repository"]
    missing_labels = _ensure_labels(graph, apply=apply)
    milestone = _ensure_milestone(graph, apply=apply)
    if not apply and (missing_labels or milestone is None):
        remote = recover_mapped_issues(graph, mapping, {})
        return {
            "mode": "dry-run",
            "missing_labels": missing_labels,
            "missing_milestone": milestone is None,
            "create": [object_id for object_id in graph["ordered_ids"] if object_id not in remote],
            "update": [object_id for object_id in graph["ordered_ids"] if object_id in remote],
        }
    if milestone is None:
        raise ProgramError("milestone is unavailable")
    remote = recover_mapped_issues(graph, mapping, fetch_program_issues(graph))
    create_ids = [object_id for object_id in graph["ordered_ids"] if object_id not in remote]
    if not apply:
        provisional = dict(mapping)
        provisional["milestone"] = milestone
        return {
            "mode": "dry-run",
            "missing_labels": missing_labels,
            "missing_milestone": False,
            "create": create_ids,
            "update": [object_id for object_id in graph["ordered_ids"] if object_id in remote],
        }
    for object_id in create_ids:
        row = _api(
            repository,
            "issues",
            method="POST",
            payload={
                "title": title_for(object_id, graph),
                "body": body_for(object_id, graph, mapping),
                "labels": labels_for(object_id, graph),
                "milestone": int(milestone["number"]),
            },
        )
        remote[object_id] = row
        mapping = {
            **mapping,
            "issues": {
                **(mapping.get("issues") or {}),
                object_id: {"number": int(row["number"]), "url": str(row["html_url"])},
            },
        }
    mapping = _write_map(map_path, graph, milestone, remote)
    for object_id in graph["ordered_ids"]:
        row = remote[object_id]
        required_labels = labels_for(object_id, graph)
        current_labels = {str(item.get("name") or "") for item in row.get("labels") or [] if isinstance(item, dict)}
        stale_routing_labels = {
            label for label in current_labels if label.startswith("model:") or label.startswith("effort:")
        }
        payload = {
            "title": title_for(object_id, graph),
            "body": body_for(object_id, graph, mapping),
            "labels": sorted((current_labels - stale_routing_labels) | set(required_labels)),
            "milestone": int(milestone["number"]),
        }
        _api(repository, f"issues/{row['number']}", method="PATCH", payload=payload)
    render_index(graph, mapping, index_path)
    render_execution_chunks(graph, mapping, chunks_path)
    return {"mode": "apply", "created": create_ids, "updated": graph["ordered_ids"], "milestone": milestone}


def remote_parity(
    graph: dict[str, Any],
    mapping: dict[str, Any],
    *,
    remote: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    validate_map(mapping, graph, complete=True)
    repository_identities = verify_repository_identities(graph)
    if remote is None:
        remote = recover_mapped_issues(graph, mapping, fetch_program_issues(graph))
    expected_ids = set(graph["ordered_ids"])
    actual_ids = set(remote)
    missing = sorted(expected_ids - actual_ids)
    orphan = sorted(actual_ids - expected_ids)
    drift: list[str] = []
    for object_id in sorted(expected_ids & actual_ids):
        map_row = mapping["issues"][object_id]
        remote_row = remote[object_id]
        if int(map_row["number"]) != int(remote_row["number"]):
            drift.append(f"{object_id}: map #{map_row['number']} != remote #{remote_row['number']}")
        if str(remote_row.get("title") or "") != title_for(object_id, graph):
            drift.append(f"{object_id}: title drift")
        if str(remote_row.get("body") or "") != body_for(object_id, graph, mapping):
            drift.append(f"{object_id}: body drift")
        remote_milestone = remote_row.get("milestone")
        expected_milestone = mapping["milestone"]["number"]
        if not isinstance(remote_milestone, dict) or int(remote_milestone.get("number") or 0) != expected_milestone:
            drift.append(f"{object_id}: milestone drift")
        current_labels = {
            str(item.get("name") or "") for item in remote_row.get("labels") or [] if isinstance(item, dict)
        }
        if not set(labels_for(object_id, graph)).issubset(current_labels):
            drift.append(f"{object_id}: required label drift")
        expected_routing_labels = {
            label for label in labels_for(object_id, graph) if label.startswith("model:") or label.startswith("effort:")
        }
        current_routing_labels = {
            label for label in current_labels if label.startswith("model:") or label.startswith("effort:")
        }
        if current_routing_labels != expected_routing_labels:
            drift.append(f"{object_id}: stale model/effort label drift")
    result = {
        "expected": len(expected_ids),
        "observed": len(actual_ids),
        "missing": missing,
        "orphan": orphan,
        "drift": drift,
        "repository_identities": repository_identities,
        "ok": not missing and not orphan and not drift,
    }
    if not result["ok"]:
        raise ProgramError(f"remote parity failed: {json.dumps(result, sort_keys=True)}")
    return result


def ready_work(graph: dict[str, Any], mapping: dict[str, Any]) -> list[dict[str, Any]]:
    validate_map(mapping, graph, complete=True)
    remote = recover_mapped_issues(graph, mapping, fetch_program_issues(graph))
    if set(remote) != set(graph["ordered_ids"]):
        raise ProgramError("remote graph is incomplete; run --verify-remote")
    closed = {object_id for object_id, row in remote.items() if str(row.get("state") or "").lower() == "closed"}
    closure_integrity(graph, mapping, remote)
    ready: list[dict[str, Any]] = []
    for phase in graph["phases"]:
        phase_dependencies = set(phase.get("depends_on") or [])
        phase_ready = phase_dependencies.issubset(closed)
        for packet in phase["work"]:
            work_id = packet["id"]
            dependencies = set(packet.get("depends_on") or [])
            if work_id in closed or not phase_ready or not dependencies.issubset(closed):
                continue
            row = mapping["issues"][work_id]
            repository_identity = repository_identity_for(packet["target_repo"], graph)
            ready.append(
                {
                    "id": work_id,
                    "title": packet["title"],
                    "issue": row,
                    "target_repo": packet["target_repo"],
                    "target_repository_identity": (
                        public_repository_identity(repository_identity)
                        if repository_identity is not None
                        else None
                    ),
                    "target_paths": packet["target_paths"],
                    "capabilities": packet["capabilities"],
                    "reasoning": packet["reasoning"],
                    "model_assignment": model_assignment_for(work_id, graph),
                    "effect": packet["effect"],
                    "predicate": packet["predicate"],
                    "human_gates": packet["human_gates"],
                }
            )
    return ready


def packet_seed(work_id: str, graph: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
    if work_id not in graph["work_by_id"]:
        raise ProgramError(f"unknown work id: {work_id}")
    validate_map(mapping, graph, complete=True)
    packet = graph["work_by_id"][work_id]
    issue = mapping["issues"][work_id]
    repository_identity = repository_identity_for(packet["target_repo"], graph)
    execution_requirements: dict[str, Any] = {
        "target_repository": packet["target_repo"],
        "path_prefixes": packet["target_paths"],
        "required_capabilities": packet["capabilities"],
        "reasoning_class": packet["reasoning"],
        "model_override": model_assignment_for(work_id, graph),
        "effect": packet["effect"],
        "human_gates": packet["human_gates"],
        "dependencies": packet["depends_on"],
        "live_references": packet["external_dependencies"],
    }
    if repository_identity is not None:
        execution_requirements["target_repository_identity"] = public_repository_identity(repository_identity)
    return {
        "schema_version": SEED_SCHEMA,
        "work_id": work_id,
        "work_key": f"positioning/{work_id.lower()}",
        "intent": {
            "objective": packet["outcome"],
            "deliverables": packet["deliverables"],
            "acceptance_condition": packet["acceptance"],
            "program_phase": graph["work_phase"][work_id],
            "github_issue": issue,
        },
        "execution_requirements": execution_requirements,
        "predicate": packet["predicate"],
        "receipt_target": f"github:{graph['program']['repository']}:issue:{issue['number']}",
        "rollback": packet["rollback"],
        "return_evidence": packet["return_evidence"],
        "not_a_lease": True,
    }


def chunk_launch_prompt(chunk_id: str, graph: dict[str, Any], mapping: dict[str, Any]) -> str:
    chunk = graph["chunk_by_id"].get(chunk_id)
    if chunk is None:
        raise ProgramError(f"unknown execution chunk: {chunk_id}")
    assignment = chunk_assignment_for(chunk_id, graph)
    work_ids = graph["chunk_work"][chunk_id]
    phase_scope = ", ".join(chunk["phase_ids"])
    dependency_scope = ", ".join(chunk.get("depends_on") or []) or "none"
    excluded = ", ".join(chunk.get("exclude_work_ids") or []) or "none"
    extras = ", ".join(chunk.get("extra_work_ids") or []) or "none"
    root_row = mapping.get("issues", {}).get("PSP-ROOT") or {}
    root_url = str(root_row.get("url") or "https://github.com/organvm/limen/issues/2157")
    if chunk_id == "PSP-C00":
        bootstrap = (
            "Continue draft PR #2156 on branch `codex/production-systems-program`; do not recreate the graph or "
            "its issues. Use the repository merge rail only when live authority permits it."
        )
    else:
        bootstrap = (
            "Start from current `main` only after C00 is closed and PR #2156 has landed; otherwise stop and resume C00."
        )
    return f"""Execute Production-Systems Program chunk {chunk_id}: {chunk["title"]}.

Run this conductor session with `{assignment["slug"]}` at `{assignment["effort"]}` effort. Leaf executors must use the exact model/effort assignment on each issue; never silently substitute.

Scope
- Repository: `{graph["program"]["repository"]}`
- Root program: {root_url}
- Bootstrap: {bootstrap}
- Phase scope: {phase_scope}
- Resolved leaf count: {len(work_ids)}
- Excluded leaves: {excluded}
- Extra cross-phase leaves: {extras}
- Required predecessor chunks: {dependency_scope}
- Objective: {chunk["objective"]}
- Exit gate: {chunk["exit_gate"]}

Execution contract
1. Start from live remote state. Read `AGENTS.md`, `institutio/positioning/program.yaml`, `docs/positioning/program/AGENT-RUNBOOK.md`, `docs/positioning/program/EXECUTION-CHUNKS.md`, and the root/phase/leaf GitHub issues. Do not trust this prompt over newer tracked state.
2. Run `python3 scripts/positioning-program.py --check`, `--verify-remote`, and `--verify-model-assignments`. Then run `python3 scripts/positioning-program.py --chunk {chunk_id}` and `--ready --json`.
3. Work only on leaves that are both in this chunk's resolved scope and currently ready. For each leaf, run `--seed <WORK-ID>`, obtain a conduct-broker lease before mutation, preserve native agent identity, and honor its exact repository/path/effect/authority boundary.
4. Drive dependencies to the chunk exit gate. Independent ready leaves may run in parallel only after separate broker reservations. Do not redo a green exact-head predicate or overwrite sibling work.
5. A leaf closes only after its executable predicate passes and a structured durable receipt is attached. A phase closes only after every child and its phase exit gate pass. GitHub prose, an open branch, or an unmerged draft is not completion.
6. Do not send, publish, change DNS, spend, sign, merge, expose private evidence, or mutate an account unless live authority explicitly permits that exact act. Stage reversible work, record the named human gate once, and continue every other safe lane.
7. If the session ends before the chunk closes, create a new dated envelope from `docs/positioning/program/RELAY-TEMPLATE.md` under `docs/receipts/positioning/relays/`, commit and push it, and attach it to the owning issue/PR. Then create the target agent's local pickup pointer when supported. Return the canonical phrase: `Continue from relay at <absolute-pointer-path>. mid-task — see Next Actions for current step.` The relay transfers context, never lease or approval.
8. Stop only when the chunk exit gate is verified or an irreducible external blocker has a durable owner.

Return exactly: chunk status; closed and open work IDs; commits/PRs/issue receipts; predicate results; human gates; next ready IDs; and the relay pointer when incomplete."""


def chunk_packet(chunk_id: str, graph: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
    chunk = graph["chunk_by_id"].get(chunk_id)
    if chunk is None:
        raise ProgramError(f"unknown execution chunk: {chunk_id}")
    return {
        "schema_version": EXECUTION_CHUNKS_SCHEMA,
        "id": chunk_id,
        "title": chunk["title"],
        "depends_on": chunk.get("depends_on") or [],
        "objective": chunk["objective"],
        "exit_gate": chunk["exit_gate"],
        "conductor_assignment": chunk_assignment_for(chunk_id, graph),
        "phase_ids": chunk["phase_ids"],
        "exclude_work_ids": chunk.get("exclude_work_ids") or [],
        "extra_work_ids": chunk.get("extra_work_ids") or [],
        "work": [
            {
                "id": work_id,
                "title": graph["work_by_id"][work_id]["title"],
                "issue": mapping.get("issues", {}).get(work_id),
                "leaf_assignment": model_assignment_for(work_id, graph),
            }
            for work_id in graph["chunk_work"][chunk_id]
        ],
        "launch_prompt": chunk_launch_prompt(chunk_id, graph, mapping),
    }


def render_execution_chunks(graph: dict[str, Any], mapping: dict[str, Any], path: Path = DEFAULT_CHUNKS) -> str:
    lines = [
        "# Production-Systems Program execution chunks",
        "",
        "Generated from `institutio/positioning/program.yaml`. Do not edit by hand. The manifest and live GitHub "
        "state outrank this projection.",
        "",
        "These prompts are conductor envelopes: the chunk conductor coordinates the work, while every leaf retains "
        "its own exact model/effort assignment, lease, authority boundary, predicate, and receipt.",
        "",
        "## Dependency order",
        "",
        "```mermaid",
        "flowchart LR",
    ]
    for chunk in graph["chunks"]:
        chunk_id = chunk["id"]
        safe_title = str(chunk["title"]).replace('"', "'")
        lines.append(f'  {chunk_id}["{chunk_id} · {safe_title}"]')
    for chunk in graph["chunks"]:
        for dependency in chunk.get("depends_on") or []:
            lines.append(f"  {dependency} --> {chunk['id']}")
    lines += [
        "```",
        "",
        "C04 (proof/experience) and C05 (service delivery) may run in parallel after C03. They rejoin before "
        "commercial validation. C10 intentionally interleaves P12 with P10-W08: P12-W02 unlocks P10-W08, "
        "eliminating the former P10↔P12 phase-gating deadlock.",
        "",
        "## Chunk index",
        "",
        "| Chunk | Scope | Conductor | Depends on | Leaves | Exit gate |",
        "|---|---|---|---|---:|---|",
    ]
    for chunk in graph["chunks"]:
        chunk_id = chunk["id"]
        assignment = chunk_assignment_for(chunk_id, graph)
        scope = ", ".join(f"`{item}`" for item in chunk["phase_ids"])
        if chunk.get("extra_work_ids"):
            scope += " + " + ", ".join(f"`{item}`" for item in chunk["extra_work_ids"])
        if chunk.get("exclude_work_ids"):
            scope += " − " + ", ".join(f"`{item}`" for item in chunk["exclude_work_ids"])
        dependencies = ", ".join(f"`{item}`" for item in chunk.get("depends_on") or []) or "—"
        lines.append(
            f"| `{chunk_id}` {chunk['title']} | {scope} | `{assignment['slug']}` / `{assignment['effort']}` | "
            f"{dependencies} | {len(graph['chunk_work'][chunk_id])} | {chunk['exit_gate']} |"
        )
    lines += [
        "",
        "## How to use the prompts",
        "",
        "1. Start with C00. Do not launch a chunk until every named predecessor has a durable completion receipt.",
        "2. C04 and C05 are the only intended parallel branch. Run them in isolated worktrees and broker leases.",
        "3. Paste one prompt below into a fresh conductor session using its assigned model/effort.",
        "4. If a session exhausts context or usage, use `RELAY-TEMPLATE.md`; the next agent resumes the same chunk "
        "rather than skipping ahead.",
        "5. The live `--ready --json` result controls which leaf starts next. Issue numbers are not execution order.",
    ]
    for index, chunk in enumerate(graph["chunks"], 1):
        chunk_id = chunk["id"]
        lines += [
            "",
            f"## {index}. {chunk_id} — {chunk['title']}",
            "",
            "Copy and paste:",
            "",
            "```text",
            chunk_launch_prompt(chunk_id, graph, mapping),
            "```",
        ]
    text = "\n".join(lines) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


def render_index(graph: dict[str, Any], mapping: dict[str, Any], path: Path = DEFAULT_INDEX) -> str:
    root_assignment = model_assignment_for("PSP-ROOT", graph)
    lines = [
        "# Production-Systems Program issue index",
        "",
        "Generated from `institutio/positioning/program.yaml` and `institutio/positioning/github-map.json`. "
        "Do not edit by hand.",
        "",
        f"- Phases: **{len(graph['phase_by_id'])}**",
        f"- Atomic work packets: **{len(graph['work_by_id'])}**",
        f"- Total projected GitHub objects: **{len(graph['ordered_ids'])}**",
        f"- Root model / effort: **`{root_assignment['slug']}` / `{root_assignment['effort']}`**",
        "",
        "## Phases",
        "",
        "| Phase | Issue | Chunk(s) | Model | Effort | Leaves | Depends on | Exit gate |",
        "|---|---:|---|---|---|---:|---|---|",
    ]
    for phase in graph["phases"]:
        assignment = model_assignment_for(phase["id"], graph)
        chunk_ids = ", ".join(f"`{item}`" for item in chunks_for_object(phase["id"], graph))
        dependencies = ", ".join(_link(mapping, item) for item in phase.get("depends_on") or []) or "—"
        lines.append(
            f"| `{phase['id']}` {phase['title']} | {_link(mapping, phase['id'])} | {chunk_ids} | "
            f"`{assignment['slug']}` | "
            f"`{assignment['effort']}` | {len(phase['work'])} | {dependencies} | {phase['exit_gate']} |"
        )
    for phase in graph["phases"]:
        lines += [
            "",
            f"## {phase['id']} — {phase['title']}",
            "",
            phase["outcome"],
            "",
            "| Work ID | Issue | Chunk | Model | Effort | Target | Reasoning | Effect | Depends on |",
            "|---|---:|---|---|---|---|---|---|---|",
        ]
        for packet in phase["work"]:
            assignment = model_assignment_for(packet["id"], graph)
            chunk_id = graph["work_chunk"][packet["id"]]
            dependencies = ", ".join(_link(mapping, item) for item in packet.get("depends_on") or []) or "—"
            lines.append(
                f"| `{packet['id']}` {packet['title']} | {_link(mapping, packet['id'])} | `{chunk_id}` | "
                f"`{assignment['slug']}` | "
                f"`{assignment['effort']}` | `{packet['target_repo']}` | `{packet['reasoning']}` | "
                f"`{packet['effect']}` | {dependencies} |"
            )
    text = "\n".join(lines) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


def _state_digest(graph: dict[str, Any], mapping: dict[str, Any], remote: dict[str, dict[str, Any]]) -> str:
    payload = {
        "program": graph["program"]["id"],
        "issues": [
            {
                "id": object_id,
                "number": mapping["issues"][object_id]["number"],
                "remote": remote[object_id],
            }
            for object_id in graph["ordered_ids"]
            if object_id in remote
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _remote_state_digest(
    graph: dict[str, Any], mapping: dict[str, Any], remote: dict[str, dict[str, Any]], excluded: set[str]
) -> str:
    projection = [
        _stable_remote_row(object_id, remote[object_id])
        for object_id in graph["ordered_ids"]
        if object_id in remote and object_id not in excluded
    ]
    return _canonical_digest(projection)


def validate_omega_pass(value: object, number: int, digest: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProgramError(f"Omega pass {number} must be a JSON object")
    failures: list[str] = []
    if value.get("schema_version") != OMEGA_PASS_SCHEMA:
        failures.append(f"schema_version must be {OMEGA_PASS_SCHEMA}")
    if value.get("status") != "pass":
        failures.append("status must be pass")
    if value.get("pass") != number:
        failures.append(f"pass must be {number}")
    if value.get("state_digest") != digest:
        failures.append("state_digest does not attest the current passing digest")
    observed_at = value.get("observed_at")
    if not isinstance(observed_at, str) or not RFC3339_RE.fullmatch(observed_at):
        failures.append("observed_at must be RFC3339")
    if failures:
        raise ProgramError(f"Omega pass {number} validation failed:\n- " + "\n- ".join(failures))
    return value


def terminal_omega_work_ids(graph: dict[str, Any]) -> set[str]:
    return {
        work_id
        for work_id, packet in graph["work_by_id"].items()
        if "--omega" in str(packet.get("acceptance") or "") or "--omega" in str(packet.get("predicate") or "")
    }


def omega_pass_record(result: dict[str, Any], number: int) -> dict[str, Any]:
    return {
        **result,
        "schema_version": OMEGA_PASS_SCHEMA,
        "status": "pass",
        "pass": number,
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
    }


def omega(
    graph: dict[str, Any], mapping: dict[str, Any], *, require_two_pass: bool, allow_open_terminal: bool = False
) -> dict[str, Any]:
    remote = recover_mapped_issues(graph, mapping, fetch_program_issues(graph))
    parity = remote_parity(graph, mapping, remote=remote)
    terminal_work_ids, terminal_phase_ids = phase_terminal_scope(graph)
    proof_window = allow_open_terminal or require_two_pass
    excluded_terminal = {"PSP-ROOT", *terminal_phase_ids, *terminal_work_ids} if proof_window else set()
    remote_state_digest = _remote_state_digest(graph, mapping, remote, excluded_terminal)
    phase_bindings = {
        phase["id"]: _phase_binding_values(phase["id"], graph, mapping, remote)
        for phase in graph["phases"]
        if not (proof_window and phase["id"] in terminal_phase_ids)
    }
    failures = []
    receipt_urls: dict[str, str] = {}
    closure_kwargs = {}
    if proof_window:
        closure_kwargs = {
            "excluded_work_ids": terminal_work_ids,
            "excluded_phase_ids": terminal_phase_ids,
        }
    try:
        receipt_urls = closure_integrity(
            graph,
            mapping,
            remote,
            phase_bindings=phase_bindings,
            **closure_kwargs,
        )
    except ProgramError as exc:
        failures.append(str(exc))
    phase_receipts: dict[str, dict[str, Any]] = {}
    for phase in graph["phases"]:
        phase_id = phase["id"]
        if proof_window and phase_id in terminal_phase_ids:
            continue
        try:
            phase_receipts[phase_id], _url = fetch_phase_receipt(
                phase_id,
                graph,
                mapping,
                **phase_bindings[phase_id],
                remote=remote,
            )
        except ProgramError as exc:
            failures.append(str(exc))
    digest_payload = {
        "parity": parity,
        "remote_state": remote_state_digest,
        "work_receipts": {
            work_id: hashlib.sha256(
                json.dumps(fetch_work_receipt(work_id, graph, mapping)[0], sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            for work_id in sorted(graph["work_by_id"])
            if work_id in receipt_urls and work_id not in terminal_work_ids
        },
        "phase_receipts": phase_receipts,
    }
    digest = hashlib.sha256(json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    passes: list[dict[str, Any]] = []
    if require_two_pass:
        for number in (1, 2):
            path = OMEGA_DIR / f"omega-pass-{number}.json"
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                failures.append(f"missing or invalid {path}: {exc}")
                continue
            try:
                passes.append(validate_omega_pass(value, number, digest))
            except ProgramError as exc:
                failures.append(f"{path}: {exc}")
        if len(passes) == 2:
            if passes[0]["state_digest"] != passes[1]["state_digest"]:
                failures.append("Omega pass digests differ")
            if passes[0]["observed_at"] == passes[1]["observed_at"]:
                failures.append("Omega passes must record distinct observations")
    proof_complete = allow_open_terminal or (require_two_pass and len(passes) == 2)
    allowed_open = {"PSP-ROOT", *terminal_phase_ids, *terminal_work_ids} if proof_complete else set()
    open_ids = [
        object_id
        for object_id in graph["ordered_ids"]
        if str(remote[object_id].get("state") or "").lower() != "closed"
        and object_id not in allowed_open
    ]
    if open_ids:
        failures.append(f"open program objects: {open_ids}")
    result = {
        "status": "pass" if not failures else "fail",
        "ok": not failures,
        "state_digest": digest,
        "parity": parity,
        "open": open_ids,
        "verified_receipts": len(receipt_urls),
        "failures": failures,
    }
    if failures:
        raise ProgramError("Omega not reached:\n- " + "\n- ".join(failures))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--render", action="store_true")
    mode.add_argument("--sync", action="store_true")
    mode.add_argument("--verify-remote", action="store_true")
    mode.add_argument("--verify-model-assignments", action="store_true")
    mode.add_argument("--render-chunks", action="store_true")
    mode.add_argument("--chunk", metavar="CHUNK_ID")
    mode.add_argument("--ready", action="store_true")
    mode.add_argument("--seed", metavar="WORK_ID")
    mode.add_argument("--receipt-template", metavar="WORK_ID")
    mode.add_argument("--phase-receipt-template", metavar="PHASE_ID")
    mode.add_argument("--verify-work", metavar="WORK_ID")
    mode.add_argument("--phase-proof", metavar="PHASE_ID")
    mode.add_argument("--verify-phase", metavar="PHASE_ID")
    mode.add_argument("--omega", action="store_true")
    parser.add_argument("--apply", action="store_true", help="allow GitHub writes; valid only with --sync")
    parser.add_argument("--json", action="store_true", help="emit machine-readable ready-work output")
    parser.add_argument("--require-two-pass", action="store_true", help="require two current Omega receipt files")
    parser.add_argument("--omega-pass", type=int, choices=(1, 2), metavar="{1,2}")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--github-map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS)
    args = parser.parse_args(argv)
    try:
        if args.apply and not args.sync:
            raise ProgramError("--apply is valid only with --sync")
        if args.omega_pass is not None and not args.omega:
            raise ProgramError("--omega-pass is valid only with --omega")
        if args.omega_pass is not None and args.require_two_pass:
            raise ProgramError("--omega-pass is incompatible with --require-two-pass")
        data = load_manifest(args.manifest)
        graph = index_program(data)
        mapping = load_map(args.github_map)
        validate_map(mapping, graph, complete=False)
        if args.check:
            result: object = {
                "status": "ok",
                "phases": len(graph["phase_by_id"]),
                "execution_chunks": len(graph["chunks"]),
                "repository_identities": len(graph["repository_identity_by_slug"]),
                "work_packets": len(graph["work_by_id"]),
                "projected_objects": len(graph["ordered_ids"]),
                "mapped_objects": len(mapping.get("issues") or {}),
            }
        elif args.render:
            render_index(graph, mapping, args.index)
            result = {"status": "rendered", "path": str(args.index), "objects": len(graph["ordered_ids"])}
        elif args.sync:
            result = sync(
                graph,
                mapping,
                apply=args.apply,
                map_path=args.github_map,
                index_path=args.index,
                chunks_path=args.chunks,
            )
        elif args.verify_remote:
            result = remote_parity(graph, mapping)
        elif args.verify_model_assignments:
            result = verify_model_assignments(graph)
        elif args.render_chunks:
            render_execution_chunks(graph, mapping, args.chunks)
            result = {"status": "rendered", "path": str(args.chunks), "chunks": len(graph["chunks"])}
        elif args.chunk:
            result = chunk_packet(args.chunk, graph, mapping)
        elif args.ready:
            result = ready_work(graph, mapping)
            if not args.json:
                for row in result:
                    print(
                        f"{row['id']}  {row['reasoning']}/{row['effect']}  {row['target_repo']}  {row['issue']['url']}"
                    )
                return 0
        elif args.seed:
            result = packet_seed(args.seed, graph, mapping)
        elif args.receipt_template:
            result = receipt_template(args.receipt_template, graph, mapping)
        elif args.phase_receipt_template:
            result = phase_receipt_template(args.phase_receipt_template, graph, mapping)
        elif args.verify_work:
            result = verify_work(args.verify_work, graph, mapping)
        elif args.phase_proof:
            result = phase_proof(args.phase_proof, graph, mapping)
        elif args.verify_phase:
            result = verify_phase(args.verify_phase, graph, mapping)
        else:
            result = omega(
                graph,
                mapping,
                require_two_pass=args.require_two_pass,
                allow_open_terminal=args.omega_pass is not None,
            )
            if args.omega_pass is not None:
                result = omega_pass_record(result, args.omega_pass)
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        return 0
    except ProgramError as exc:
        print(f"positioning-program: BLOCKED — {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
