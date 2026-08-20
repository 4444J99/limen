"""Pure schema, scope, and normalization contract for recovery reacceptance."""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "limen.reacceptance_ledger.v2"
V1_SCHEMA = "limen.reacceptance_ledger.v1"
SCOPE_SCHEMA = "limen.reacceptance_scope.v2"
REVIEW_GATE_SCHEMA = "limen.pr_review_gate.v1"
REVIEW_GATE_CONTEXT = REVIEW_GATE_SCHEMA
GENERIC_ACTIONS_APP_SLUG = "github-actions"
SOURCE_LINEAGE_SCHEMA = "limen.prompt_corpus_lineage.v1"
TRAJECTORY_SCHEMA = "limen.execution_trajectory.v1"
SIDE_EFFECT_SCHEMA = "limen.side_effect_reconciliation.v1"
SIDE_EFFECT_OUTCOME_SCHEMA = "limen.side_effect_outcome.v1"
REFRESH_RECEIPT_SCHEMA = "limen.reacceptance_refresh_receipt.v1"
PRIVACY_COPY_SCHEMA = "limen.private_custody_copy.v1"
CUTOFF_SCHEMA = "limen.prompt_corpus_cutoff.v1"
OWNER_EVIDENCE_MAX_AGE = dt.timedelta(hours=24)
RELEASE_SNAPSHOT_MAX_AGE = dt.timedelta(hours=1)
TRUSTED_REVIEW_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
TRUSTED_REVIEWER_KINDS = {"github_pull_request_review", "ssh_signed_peer_review"}
REVIEWED_REMEDY_KINDS = {
    "pull_request",
    "commit",
    "reversal",
    "deployment",
    "owner_receipt",
    "checkpoint",
}
OWNER_EVIDENCE_SCHEMAS = {
    "baseline_open_prs": "limen.reacceptance.owner.github.v1",
    "session_value": "limen.reacceptance.owner.trajectory.v1",
    "inflight_custody": "limen.reacceptance.owner.custody.v1",
    "privacy": "limen.reacceptance.owner.privacy.v1",
    "continuation": "limen.reacceptance.owner.continuation.v1",
}

REDACTED_SESSION_ID = re.compile(r"^claude-session-sha256:[0-9a-f]{20}$")
REDACTED_WORKFLOW_ID = re.compile(r"^claude-workflow-sha256:[0-9a-f]{20}$")
FULL_HEAD = re.compile(r"^[0-9a-f]{40}$")
SHA256_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
SAFE_ID = re.compile(r"^[a-z][a-z0-9_.:/#@+-]{2,255}$")

ALLOWED_DISPOSITIONS = {"accepted", "repair_required", "reverted", "superseded"}
TERMINAL_DISPOSITIONS = ALLOWED_DISPOSITIONS - {"repair_required"}
FINDING_DISPOSITIONS = {"repair_required", "repaired", "obsolete", "reverted"}
TERMINAL_FINDING_DISPOSITIONS = FINDING_DISPOSITIONS - {"repair_required"}
REMEDY_KINDS = {"pull_request", "commit", "reversal", "deployment", "owner_receipt", "checkpoint"}
REMEDY_STATUSES = {"accepted", "repair_required", "reverted"}
COVERAGE_DISPOSITIONS = {"repaired", "obsolete", "reverted", "superseded"}

COMPLETION_GATE_KEYS = {
    "open_prs_closed_or_reaccepted",
    "session_value_verified",
    "no_stale_inflight_custody",
    "privacy_containment_terminal",
    "continuation_fixed_point",
}
OWNER_EVIDENCE_KEYS = {
    "baseline_open_prs",
    "session_value",
    "inflight_custody",
    "privacy",
    "continuation",
}

REQUIRED_ROW_KEYS = {
    "id",
    "kind",
    "source_ask",
    "session",
    "attempt_ids",
    "exact_head",
    "outputs",
    "side_effects",
    "owner_surfaces",
    "review_findings",
    "predicate",
    "receipt",
    "keeper",
    "disposition",
}
REQUIRED_REVIEW_GATE_KEYS = {
    "schema",
    "status",
    "final_status",
    "ok",
    "evaluated_at",
    "repository",
    "pull_request",
    "url",
    "fixture",
    "expected_head",
    "head_sha",
    "rechecked_head_sha",
    "reviewed_sha",
    "executing_keeper",
    "reviewing_keeper",
    "reviewer_receipt",
    "signed_receipts",
    "unresolved_current_thread_count",
    "checks",
    "review_threads",
    "reason_codes",
    "reasons",
    "publication",
}

VOLATILE_EVIDENCE_KEYS = {
    "attestation",
    "binding_digest",
    "continuation_digest",
    "refreshed_at",
    "verified_at",
    "evaluated_at",
    "submitted_at",
    "merged_at",
    "closed_at",
    "created_at",
    "updated_at",
}


class LedgerError(RuntimeError):
    """Fail-closed ledger or owner-read failure."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(dt.timezone.utc)


def _reject_nonfinite_json(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _strict_json_loads(payload: str | bytes) -> Any:
    return json.loads(payload, parse_constant=_reject_nonfinite_json)


def _strict_json_dumps(value: Any, **kwargs: Any) -> str:
    return json.dumps(value, allow_nan=False, **kwargs)


def load_json_snapshot(path: Path) -> tuple[dict[str, Any], str]:
    try:
        payload = path.read_bytes()
        value = _strict_json_loads(payload)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise LedgerError(f"cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LedgerError(f"{path} must contain a JSON object")
    return value, hashlib.sha256(payload).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value, _digest = load_json_snapshot(path)
    return value


def expand_prs(scope: dict[str, Any]) -> list[tuple[str, int]]:
    rows: list[tuple[str, int]] = []
    groups = scope.get("pull_requests")
    if not isinstance(groups, list):
        raise LedgerError("scope pull_requests must be a list")
    for group in groups:
        if not isinstance(group, dict):
            raise LedgerError("each pull_requests group must be an object")
        repository = group.get("repository")
        numbers = group.get("numbers")
        if not isinstance(repository, str) or "/" not in repository or not isinstance(numbers, list):
            raise LedgerError("each pull_requests group needs repository and numbers")
        if any(not isinstance(number, int) or isinstance(number, bool) or number <= 0 for number in numbers):
            raise LedgerError(f"scope pull request numbers are invalid for {repository}")
        rows.extend((repository, number) for number in numbers)
    return rows


def _expected_row_ids(scope: dict[str, Any]) -> set[str]:
    return {
        *(f"session:{identifier}" for identifier in scope.get("sessions", [])),
        *(f"workflow:{identifier}" for identifier in scope.get("workflows", [])),
        *(f"pull_request:{repository}#{number}" for repository, number in expand_prs(scope)),
    }


def _scope_cutoff_digest(scope: dict[str, Any]) -> str:
    payload = {
        "boundary": scope.get("boundary"),
        "cutoff_receipt": scope.get("cutoff_receipt"),
        "sessions": scope.get("sessions"),
        "workflows": scope.get("workflows"),
        "pull_requests": scope.get("pull_requests"),
    }
    encoded = _strict_json_dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _event_offsets_digest(offsets: Iterable[str]) -> str:
    encoded = "\n".join(sorted(offsets)).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def load_scope(path: Path) -> dict[str, Any]:
    scope = load_json(path)
    if scope.get("schema") != SCOPE_SCHEMA:
        raise LedgerError(f"scope schema must be {SCOPE_SCHEMA}")
    from limen.reacceptance_owners import owner_attestation_scope_errors

    owner_attestation_errors = owner_attestation_scope_errors(scope)
    if owner_attestation_errors:
        raise LedgerError("; ".join(owner_attestation_errors))
    review_gate_app_slug = scope.get("review_gate_app_slug")
    if review_gate_app_slug is not None and (
        not isinstance(review_gate_app_slug, str)
        or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,98}[a-z0-9])?", review_gate_app_slug)
        or review_gate_app_slug == GENERIC_ACTIONS_APP_SLUG
    ):
        raise LedgerError("scope review_gate_app_slug must name a dedicated non-generic App")
    boundary = scope.get("boundary")
    if not isinstance(boundary, dict) or _parse_timestamp(boundary.get("starts_at")) is None:
        raise LedgerError("scope boundary must preserve a timezone-aware starts_at")
    cutoff = scope.get("cutoff_receipt")
    if not isinstance(cutoff, dict) or cutoff.get("schema") != CUTOFF_SCHEMA:
        raise LedgerError(f"scope cutoff_receipt schema must be {CUTOFF_SCHEMA}")
    if cutoff.get("status") not in {"not_verified", "verified"}:
        raise LedgerError("scope cutoff_receipt status is invalid")
    if not isinstance(cutoff.get("owner"), str) or not cutoff["owner"].strip():
        raise LedgerError("scope cutoff_receipt owner is required")
    offsets = cutoff.get("event_offsets")
    if (
        not isinstance(offsets, list)
        or any(not isinstance(offset, str) or not offset.strip() for offset in offsets)
        or len(offsets) != len(set(offsets))
    ):
        raise LedgerError("scope cutoff_receipt event_offsets must be unique non-empty strings")
    if cutoff.get("status") == "verified":
        if not offsets:
            raise LedgerError("verified scope cutoff_receipt requires immutable event offsets")
        if cutoff.get("digest") != _event_offsets_digest(offsets):
            raise LedgerError("verified scope cutoff_receipt digest must derive from its immutable event offsets")
        if _parse_timestamp(cutoff.get("verified_at")) is None:
            raise LedgerError("verified scope cutoff_receipt requires verified_at")
    sessions = scope.get("sessions")
    if not isinstance(sessions, list) or any(
        not isinstance(identifier, str) or not REDACTED_SESSION_ID.fullmatch(identifier) for identifier in sessions
    ):
        raise LedgerError("scope sessions must contain only redacted truncated SHA-256 identifiers")
    if len(sessions) != len(set(sessions)):
        raise LedgerError("scope sessions must be unique")
    workflows = scope.get("workflows")
    if not isinstance(workflows, list) or any(
        not isinstance(identifier, str) or not REDACTED_WORKFLOW_ID.fullmatch(identifier) for identifier in workflows
    ):
        raise LedgerError("scope workflows must contain only redacted truncated SHA-256 identifiers")
    if len(workflows) != len(set(workflows)):
        raise LedgerError("scope workflows must be unique")
    prs = expand_prs(scope)
    if len(prs) != len(set(prs)):
        raise LedgerError("scope pull requests must be unique")
    baseline = scope.get("baseline_open_prs")
    if (
        not isinstance(baseline, list)
        or len(baseline) != 5
        or len(baseline) != len(set(baseline))
        or any(identifier not in _expected_row_ids(scope) for identifier in baseline)
    ):
        raise LedgerError("scope baseline_open_prs must freeze five unique historical row IDs")
    finding_scope = scope.get("findings")
    if not isinstance(finding_scope, dict):
        raise LedgerError("scope findings must be an object")
    expected_total = sum(
        finding_scope.get(field, -1) if isinstance(finding_scope.get(field), int) else -1
        for field in ("p1", "p2", "unclassified")
    )
    if finding_scope.get("total") != expected_total or expected_total < 0:
        raise LedgerError("scope finding counts are inconsistent")
    if not SHA256_DIGEST.fullmatch(str(finding_scope.get("discussion_url_digest") or "")):
        raise LedgerError("scope findings need a SHA-256 discussion URL digest")
    if not SHA256_DIGEST.fullmatch(str(finding_scope.get("manifest_digest") or "")):
        raise LedgerError("scope findings need a row- and severity-anchored SHA-256 manifest digest")
    known_effects = scope.get("known_side_effects")
    if not isinstance(known_effects, dict):
        raise LedgerError("scope known_side_effects must be an object")
    expected_ids = _expected_row_ids(scope)
    for row_id, effects in known_effects.items():
        if row_id not in expected_ids:
            raise LedgerError(f"scope known_side_effects references unknown row {row_id}")
        if (
            not isinstance(effects, list)
            or not effects
            or any(not isinstance(effect, str) or not SAFE_ID.fullmatch(effect) for effect in effects)
            or len(effects) != len(set(effects))
        ):
            raise LedgerError(f"scope known_side_effects for {row_id} must be unique safe identifiers")
    known_effect_owners = scope.get("known_side_effect_owners")
    if not isinstance(known_effect_owners, dict) or set(known_effect_owners) != set(known_effects):
        raise LedgerError("scope known_side_effect_owners must cover every known side-effect row")
    for row_id, effects in known_effects.items():
        owner_mapping = known_effect_owners.get(row_id)
        if (
            not isinstance(owner_mapping, dict)
            or set(owner_mapping) != set(effects)
            or any(not isinstance(owner, str) or not owner.strip() for owner in owner_mapping.values())
        ):
            raise LedgerError(f"scope known_side_effect_owners for {row_id} must own every frozen effect")
    privacy_rows = scope.get("privacy_affected_row_ids")
    derived_privacy_rows = sorted(
        row_id
        for row_id, effects in known_effects.items()
        if any("privacy" in effect or "private_material" in effect or "public_history" in effect for effect in effects)
    )
    if (
        not isinstance(privacy_rows, list)
        or not privacy_rows
        or len(privacy_rows) != len(set(privacy_rows))
        or any(row_id not in expected_ids for row_id in privacy_rows)
        or sorted(privacy_rows) != derived_privacy_rows
    ):
        raise LedgerError("scope privacy_affected_row_ids must equal the privacy side-effect denominator")
    privacy_manifest_digest = scope.get("privacy_content_manifest_digest")
    if privacy_manifest_digest is not None and (
        not isinstance(privacy_manifest_digest, str) or not SHA256_DIGEST.fullmatch(privacy_manifest_digest)
    ):
        raise LedgerError("scope privacy_content_manifest_digest must be null or a SHA-256 digest")
    if not SHA256_DIGEST.fullmatch(str(scope.get("source_reference_manifest_digest") or "")):
        raise LedgerError("scope source_reference_manifest_digest must freeze the row-anchored source atoms")
    if not SHA256_DIGEST.fullmatch(str(scope.get("legacy_v1_rows_digest") or "")):
        raise LedgerError("scope legacy_v1_rows_digest must freeze the original v1 row payload")
    return scope


def _source_ask(reference: str) -> dict[str, Any]:
    return {
        "status": "unreconciled",
        "references": [reference],
        "private_owner": "private_prompt_corpus_owner",
        "lineage_digest": None,
        "receipt": None,
    }


def _base_row(kind: str, identifier: str) -> dict[str, Any]:
    session = identifier if kind == "session" else None
    return {
        "id": f"{kind}:{identifier}",
        "kind": kind,
        "source_ask": _source_ask(f"private_prompt_corpus:{identifier}"),
        "session": session,
        "attempt_ids": [],
        "exact_head": None,
        "outputs": {"status": "unreconciled", "attempt_ids": []},
        "side_effects": {
            "status": "unreconciled",
            "attempt_ids": [],
            "observed": [],
            "replay_authorized": False,
            "receipt": None,
        },
        "owner_surfaces": [],
        "review_findings": {
            "status": "not_applicable",
            "p1": 0,
            "p2": 0,
            "unclassified": 0,
            "unresolved_current": 0,
            "urls": [],
        },
        "predicate": {
            "status": "not_verified",
            "command": None,
            "requirement": "reconcile source, attempts, spend, outputs, effects, predicate, and receipt",
        },
        "receipt": {"status": "missing", "url": None},
        "keeper": {
            "executing_keeper": "claude",
            "reviewing_keeper": None,
            "provider_route": "claude",
            "owner_surface": "shared_peer_keepers",
        },
        "disposition": "repair_required",
    }


def _default_owner_evidence(scope: dict[str, Any]) -> dict[str, Any]:
    baseline = list(scope["baseline_open_prs"])
    return {
        "baseline_open_prs": {
            "schema": OWNER_EVIDENCE_SCHEMAS["baseline_open_prs"],
            "owner": "github_remote_owner",
            "baseline_row_ids": baseline,
            "terminal_row_ids": [],
            "baseline_digest": None,
            "predicate": None,
            "receipt": None,
        },
        "session_value": {
            "schema": OWNER_EVIDENCE_SCHEMAS["session_value"],
            "owner": "execution_trajectory_owner",
            "attempt_ids": [],
            "uncredited_attempt_ids": [],
            "motion_only_attempt_ids": [],
            "unverifiable_attempt_ids": [],
            "failed_attempt_ids": [],
            "unreconciled_attempt_ids": [],
            "attempt_registry_digest": None,
            "predicate": None,
            "receipt": None,
        },
        "inflight_custody": {
            "schema": OWNER_EVIDENCE_SCHEMAS["inflight_custody"],
            "owner": "private_session_corpus_owner",
            "campaign_attempt_ids": [],
            "stale_ids": [],
            "campaign_attempt_digest": None,
            "cutoff_receipt": copy.deepcopy(scope.get("cutoff_receipt")),
            "predicate": None,
            "receipt": None,
        },
        "privacy": {
            "schema": OWNER_EVIDENCE_SCHEMAS["privacy"],
            "owner": "private_privacy_custody_owner",
            "affected_row_ids": sorted(scope["privacy_affected_row_ids"]),
            "content_manifest_digest": scope.get("privacy_content_manifest_digest"),
            "frozen_manifest_digest": None,
            "current_trees_clean": False,
            "private_copy_receipts": [],
            "history_status": "pending_human",
            "privacy_denominator_digest": None,
            "predicate": None,
            "receipt": None,
        },
        "continuation": {
            "schema": OWNER_EVIDENCE_SCHEMAS["continuation"],
            "owner": "limen_reacceptance_owner",
            "capsule": None,
            "launch_command": None,
            "refresh_receipts": [],
            "continuation_digest": None,
            "predicate": None,
            "receipt": None,
        },
    }


def _id_map(values: Any, *, label: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
    if not isinstance(values, list):
        return {}, [f"{label} must be a list"]
    errors: list[str] = []
    result: dict[str, dict[str, Any]] = {}
    for index, value in enumerate(values):
        if not isinstance(value, dict):
            errors.append(f"{label}[{index}] must be an object")
            continue
        identifier = value.get("id")
        if not isinstance(identifier, str) or not SAFE_ID.fullmatch(identifier):
            errors.append(f"{label}[{index}] id is invalid")
            continue
        if identifier in result:
            errors.append(f"{label} ids must be unique: {identifier}")
            continue
        result[identifier] = value
    return result, errors


def _string_ids(value: Any, *, label: str, require_nonempty: bool = False) -> tuple[list[str], list[str]]:
    if not isinstance(value, list):
        return [], [f"{label} must be a list"]
    errors: list[str] = []
    if require_nonempty and not value:
        errors.append(f"{label} must not be empty")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        errors.append(f"{label} must contain non-empty strings")
        return [], errors
    if len(value) != len(set(value)):
        errors.append(f"{label} must be unique")
    return list(value), errors


def _lineage_digest(references: Iterable[str]) -> str:
    encoded = "\n".join(sorted(references)).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _effect_digest(effects: Iterable[str]) -> str:
    encoded = "\n".join(sorted(effects)).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _output_digest(outputs: Iterable[dict[str, Any]]) -> str:
    encoded = _strict_json_dumps(
        sorted(
            (copy.deepcopy(output) for output in outputs),
            key=lambda output: _strict_json_dumps(
                output,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ),
        ),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _source_reference_manifest_digest(source_references: dict[str, list[str]]) -> str:
    entries = [f"{row_id}\0{_lineage_digest(references)}" for row_id, references in sorted(source_references.items())]
    return "sha256:" + hashlib.sha256("\n".join(entries).encode()).hexdigest()


def _legacy_v1_rows_digest(rows: Iterable[dict[str, Any]]) -> str:
    encoded = _strict_json_dumps(
        sorted(
            (copy.deepcopy(row) for row in rows),
            key=lambda row: str(row.get("id")),
        ),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _document_scope(scope: dict[str, Any]) -> dict[str, Any]:
    from limen.reacceptance_owners import owner_attestation_requirements_digest

    return {
        "review_gate_app_slug": scope.get("review_gate_app_slug"),
        "boundary": copy.deepcopy(scope["boundary"]),
        "cutoff_digest": _scope_cutoff_digest(scope),
        "starts_at": scope["boundary"]["starts_at"],
        "sessions": len(scope["sessions"]),
        "workflows": len(scope["workflows"]),
        "pull_requests": len(expand_prs(scope)),
        "rows": len(_expected_row_ids(scope)),
        "baseline_open_prs": list(scope["baseline_open_prs"]),
        "privacy_affected_row_ids": sorted(scope["privacy_affected_row_ids"]),
        "privacy_content_manifest_digest": scope.get("privacy_content_manifest_digest"),
        "source_reference_manifest_digest": scope["source_reference_manifest_digest"],
        "legacy_v1_rows_digest": scope["legacy_v1_rows_digest"],
        "owner_attestation_requirements_digest": owner_attestation_requirements_digest(scope),
        "known_side_effects": {
            row_id: sorted(effects) for row_id, effects in sorted(scope["known_side_effects"].items())
        },
        "known_side_effect_owners": {
            row_id: {effect: owner for effect, owner in sorted(owners.items())}
            for row_id, owners in sorted(scope["known_side_effect_owners"].items())
        },
        "findings": copy.deepcopy(scope["findings"]),
    }


def _semantic_normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _semantic_normalize(child)
            for key, child in sorted(value.items())
            if key not in VOLATILE_EVIDENCE_KEYS and key != "refresh_receipts"
        }
    if isinstance(value, list):
        normalized = [_semantic_normalize(child) for child in value]
        return sorted(
            normalized,
            key=lambda child: _strict_json_dumps(
                child,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ),
        )
    return value


def normalized_evidence_digest(document: dict[str, Any]) -> str:
    payload = {
        "schema": document.get("schema"),
        "scope": document.get("scope"),
        "rows": document.get("rows"),
        "attempts": document.get("attempts"),
        "remedies": document.get("remedies"),
        "coverage": document.get("coverage"),
        "findings": document.get("findings"),
        "owner_evidence": document.get("owner_evidence"),
    }
    encoded = _strict_json_dumps(
        _semantic_normalize(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _finding_is_debt(finding: dict[str, Any]) -> bool:
    return finding.get("disposition") not in TERMINAL_FINDING_DISPOSITIONS or finding.get("current_status") not in {
        "resolved",
        "outdated",
    }


def _campaign_ready(
    *,
    rows: list[dict[str, Any]],
    remedies: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    completion_gates: dict[str, dict[str, Any]],
) -> bool:
    return (
        bool(rows)
        and all(isinstance(row, dict) and row.get("disposition") in TERMINAL_DISPOSITIONS for row in rows)
        and all(isinstance(remedy, dict) and remedy.get("status") in {"accepted", "reverted"} for remedy in remedies)
        and all(isinstance(finding, dict) and not _finding_is_debt(finding) for finding in findings)
        and set(completion_gates) == COMPLETION_GATE_KEYS
        and all(completion_gates[key].get("status") == "passed" for key in COMPLETION_GATE_KEYS)
    )


def _summary_for(
    *,
    rows: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    remedies: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    completion_gates: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    debt = [finding for finding in findings if isinstance(finding, dict) and _finding_is_debt(finding)]
    return {
        "historical_rows": len(rows),
        "accepted": sum(row.get("disposition") == "accepted" for row in rows if isinstance(row, dict)),
        "repair_required": sum(row.get("disposition") == "repair_required" for row in rows if isinstance(row, dict)),
        "reverted": sum(row.get("disposition") == "reverted" for row in rows if isinstance(row, dict)),
        "superseded": sum(row.get("disposition") == "superseded" for row in rows if isinstance(row, dict)),
        "attempts": len(attempts),
        "remedies": len(remedies),
        "accepted_remedies": sum(remedy.get("status") == "accepted" for remedy in remedies if isinstance(remedy, dict)),
        "repair_required_remedies": sum(
            remedy.get("status") == "repair_required" for remedy in remedies if isinstance(remedy, dict)
        ),
        "findings": len(findings),
        "current_p1": sum(finding.get("severity") == "p1" for finding in debt),
        "current_p2": sum(finding.get("severity") == "p2" for finding in debt),
        "current_unclassified": sum(finding.get("severity") == "unclassified" for finding in debt),
        "release_ready": _campaign_ready(
            rows=rows,
            remedies=remedies,
            findings=findings,
            completion_gates=completion_gates,
        ),
    }


def _discussion_url_digest(findings: list[dict[str, Any]]) -> str:
    urls = sorted(
        str(finding.get("discussion_url"))
        for finding in findings
        if isinstance(finding, dict) and isinstance(finding.get("discussion_url"), str)
    )
    return "sha256:" + hashlib.sha256("\n".join(urls).encode()).hexdigest()


def _finding_manifest_digest(findings: Iterable[dict[str, Any]]) -> str:
    entries = sorted(
        _strict_json_dumps(
            {
                "discussion_url": finding.get("discussion_url"),
                "historical_row_id": finding.get("historical_row_id"),
                "severity": finding.get("severity"),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        for finding in findings
    )
    return "sha256:" + hashlib.sha256("\n".join(entries).encode()).hexdigest()
