"""Runtime-discovered source contracts for the work-universe truth plane.

The registry deliberately separates a durable owner registration from the
runtime report produced by that owner. Adding, removing, or renaming a source
therefore changes data, not dispatch code. The registry validates and
normalizes reports; it never infers completeness from a missing source.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

REGISTRATION_SCHEMA = "limen.progress-source-registration.v1"
REPORT_SCHEMA = "limen.progress-source-report.v1"
REGISTRY_SCHEMA = "limen.progress-source-registry.v1"

SEMANTIC_STATUSES = frozenset(
    {
        "ready",
        "partial",
        "capped",
        "failed",
        "unavailable",
        "stale",
        "unknown",
    }
)
DEBT_STATUSES = SEMANTIC_STATUSES - {"ready"}
_SOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,255}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class SourceContractError(ValueError):
    """A registration or report cannot be normalized safely."""


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return sha256(encoded).hexdigest()


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SourceContractError(f"unreadable: {exc.__class__.__name__}") from exc
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SourceContractError("invalid-json") from exc
    if not isinstance(value, dict):
        raise SourceContractError("root-must-be-object")
    return value, sha256(raw).hexdigest()


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceContractError(f"{field}-must-be-nonempty-string")
    return value.strip()


def _source_id(value: Any) -> str:
    source_id = _nonempty_string(value, "source_id")
    if not _SOURCE_ID.fullmatch(source_id):
        raise SourceContractError("source_id-is-not-portable")
    return source_id


def _timestamp(value: Any) -> tuple[str, datetime]:
    rendered = _nonempty_string(value, "generated_at")
    try:
        parsed = datetime.fromisoformat(rendered.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SourceContractError("generated_at-is-not-rfc3339") from exc
    if parsed.tzinfo is None:
        raise SourceContractError("generated_at-requires-timezone")
    normalized = parsed.astimezone(UTC)
    return normalized.isoformat().replace("+00:00", "Z"), normalized


def _normalize_owner(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise SourceContractError("owner-must-be-object")
    return {
        "id": _nonempty_string(value.get("id"), "owner.id"),
        "surface": _nonempty_string(value.get("surface"), "owner.surface"),
    }


def _normalize_registration(value: dict[str, Any]) -> dict[str, Any]:
    if value.get("schema") != REGISTRATION_SCHEMA:
        raise SourceContractError("unsupported-registration-schema")
    report_path = _nonempty_string(value.get("report_path"), "report_path")
    max_age_seconds = value.get("max_age_seconds")
    if isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, int) or max_age_seconds < 1:
        raise SourceContractError("max_age_seconds-must-be-positive-integer")
    required = value.get("required", True)
    if not isinstance(required, bool):
        raise SourceContractError("required-must-be-boolean")
    return {
        "source_id": _source_id(value.get("source_id")),
        "owner": _normalize_owner(value.get("owner")),
        "report_path": report_path,
        "required": required,
        "max_age_seconds": max_age_seconds,
    }


def _normalize_report(value: dict[str, Any], expected_source_id: str) -> dict[str, Any]:
    if value.get("schema") != REPORT_SCHEMA:
        raise SourceContractError("unsupported-report-schema")
    source_id = _source_id(value.get("source_id"))
    if source_id != expected_source_id:
        raise SourceContractError("report-source-id-mismatch")
    if "cursor" not in value:
        raise SourceContractError("cursor-field-is-required")
    exhaustive = value.get("exhaustive")
    if not isinstance(exhaustive, bool):
        raise SourceContractError("exhaustive-must-be-boolean")
    generated_at, generated = _timestamp(value.get("generated_at"))
    content_sha256 = _nonempty_string(value.get("content_sha256"), "content_sha256")
    if not _SHA256.fullmatch(content_sha256):
        raise SourceContractError("content_sha256-must-be-lowercase-sha256")
    semantic_status = _nonempty_string(value.get("semantic_status"), "semantic_status")
    if semantic_status not in SEMANTIC_STATUSES:
        raise SourceContractError("unsupported-semantic-status")
    leaf_count = value.get("normalized_leaf_count")
    if isinstance(leaf_count, bool) or not isinstance(leaf_count, int) or leaf_count < 0:
        raise SourceContractError("normalized_leaf_count-must-be-nonnegative-integer")
    return {
        "source_id": source_id,
        "cursor": value["cursor"],
        "exhaustive": exhaustive,
        "generated_at": generated_at,
        "generated": generated,
        "content_sha256": content_sha256,
        "reported_semantic_status": semantic_status,
        "normalized_leaf_count": leaf_count,
    }


def default_registration_dirs(root: Path) -> list[Path]:
    """Return runtime registry roots without encoding a source catalog in code."""

    roots = [root / "config" / "progress-sources"]
    extra = os.environ.get("LIMEN_PROGRESS_SOURCE_REGISTRY_DIRS", "")
    roots.extend(Path(raw).expanduser() for raw in extra.split(os.pathsep) if raw.strip())
    return roots


def _report_path(root: Path, registration_path: Path, raw: str) -> Path:
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    if raw.startswith("./"):
        return registration_path.parent / path
    return root / path


def _debt_row(
    source_id: str,
    *,
    owner: dict[str, str] | None = None,
    required: bool = True,
    status: str = "unknown",
    reason: str,
    registration_sha256: str | None = None,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "owner": owner or {"id": "unknown", "surface": "unknown"},
        "cursor": None,
        "exhaustive": False,
        "generated_at": None,
        "content_sha256": None,
        "semantic_status": status,
        "reported_semantic_status": None,
        "normalized_leaf_count": None,
        "required": required,
        "coverage_debt": status in DEBT_STATUSES,
        "debt_reasons": [reason],
        "registration_sha256": registration_sha256,
        "report_sha256": None,
    }


def _source_row(
    root: Path,
    registration_path: Path,
    registration: dict[str, Any],
    registration_sha256: str,
    now: datetime,
) -> dict[str, Any]:
    source_id = str(registration["source_id"])
    report_path = _report_path(root, registration_path, str(registration["report_path"]))
    try:
        report_raw, report_sha256 = _read_json(report_path)
        report = _normalize_report(report_raw, source_id)
    except SourceContractError as exc:
        reason = str(exc)
        status = "unavailable" if reason.startswith("unreadable:") else "failed"
        return _debt_row(
            source_id,
            owner=dict(registration["owner"]),
            required=bool(registration["required"]),
            status=status,
            reason=reason,
            registration_sha256=registration_sha256,
        )

    age_seconds = max(0.0, (now - report.pop("generated")).total_seconds())
    reported = str(report["reported_semantic_status"])
    effective = reported
    debt_reasons: list[str] = []
    if reported == "ready" and not report["exhaustive"]:
        effective = "partial"
        debt_reasons.append("non-exhaustive-ready-claim")
    if age_seconds > int(registration["max_age_seconds"]):
        effective = "stale"
        debt_reasons.append("report-stale")
    if effective != "ready" and not debt_reasons:
        debt_reasons.append(f"semantic-status:{effective}")
    required = bool(registration["required"])
    return {
        **report,
        "owner": dict(registration["owner"]),
        "semantic_status": effective,
        "required": required,
        "coverage_debt": effective != "ready",
        "debt_reasons": debt_reasons,
        "age_seconds": round(age_seconds, 3),
        "max_age_seconds": int(registration["max_age_seconds"]),
        "registration_sha256": registration_sha256,
        "report_sha256": report_sha256,
    }


def build_source_registry(
    root: Path,
    *,
    registration_dirs: Iterable[Path] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Discover and normalize every registration in the configured roots."""

    root = root.resolve()
    observed = (now or datetime.now(UTC)).astimezone(UTC)
    directories = list(registration_dirs) if registration_dirs is not None else default_registration_dirs(root)
    parsed: list[tuple[Path, dict[str, Any], str]] = []
    invalid_rows: list[dict[str, Any]] = []
    directory_debt: list[str] = []

    for directory in directories:
        directory = Path(directory).expanduser()
        if not directory.is_dir():
            directory_debt.append("registration-root-unavailable")
            continue
        try:
            files = sorted(directory.glob("*.json"))
        except OSError:
            directory_debt.append("registration-root-unreadable")
            continue
        for path in files:
            try:
                raw, registration_sha256 = _read_json(path)
                registration = _normalize_registration(raw)
            except SourceContractError as exc:
                stable_id = sha256(str(path).encode("utf-8")).hexdigest()[:12]
                invalid_rows.append(
                    _debt_row(
                        f"invalid-registration-{stable_id}",
                        status="failed",
                        reason=str(exc),
                    )
                )
                continue
            parsed.append((path, registration, registration_sha256))

    counts: dict[str, int] = {}
    for _, registration, _ in parsed:
        source_id = str(registration["source_id"])
        counts[source_id] = counts.get(source_id, 0) + 1

    rows = list(invalid_rows)
    for path, registration, registration_sha256 in parsed:
        source_id = str(registration["source_id"])
        if counts[source_id] > 1:
            if not any(row["source_id"] == source_id for row in rows):
                rows.append(
                    _debt_row(
                        source_id,
                        status="failed",
                        reason="duplicate-source-registration",
                    )
                )
            continue
        rows.append(_source_row(root, path, registration, registration_sha256, observed))

    rows.sort(key=lambda row: str(row["source_id"]))
    required_rows = [row for row in rows if row["required"]]
    ready = sum(row["semantic_status"] == "ready" for row in required_rows)
    source_debt = sum(bool(row["coverage_debt"]) for row in rows)
    empty_debt = 1 if not rows else 0
    discovery_debt = len(directory_debt)
    coverage_debt = source_debt + empty_debt + discovery_debt
    discovery_exhaustive = not directory_debt and not invalid_rows
    registry_status = "ready" if rows and coverage_debt == 0 and discovery_exhaustive else "partial"
    if not rows:
        registry_status = "unknown"

    contract_inputs = [
        {
            "source_id": row["source_id"],
            "registration_sha256": row["registration_sha256"],
            "report_sha256": row["report_sha256"],
            "semantic_status": row["semantic_status"],
        }
        for row in rows
    ]
    unknown_leaf_count_sources = sum(row["normalized_leaf_count"] is None for row in rows)
    known_normalized_leaf_count = sum(
        int(row["normalized_leaf_count"]) for row in rows if isinstance(row["normalized_leaf_count"], int)
    )
    normalized_leaf_count = (
        known_normalized_leaf_count if rows and not unknown_leaf_count_sources and not directory_debt else None
    )
    return {
        "schema": REGISTRY_SCHEMA,
        "generated_at": observed.isoformat().replace("+00:00", "Z"),
        "semantic_status": registry_status,
        "content_sha256": _canonical_sha256(
            {
                "schema": REGISTRY_SCHEMA,
                "discovery_exhaustive": discovery_exhaustive,
                "directory_debt": directory_debt,
                "sources": contract_inputs,
            }
        ),
        "discovery": {
            "configured_root_count": len(directories),
            "exhaustive": discovery_exhaustive,
            "debt_reasons": directory_debt,
        },
        "summary": {
            "source_count": len(rows),
            "required_source_count": len(required_rows),
            "ready_required_source_count": ready,
            "coverage_debt": coverage_debt,
            "unknown_leaf_count_sources": unknown_leaf_count_sources,
            "known_normalized_leaf_count": known_normalized_leaf_count,
            "normalized_leaf_count": normalized_leaf_count,
        },
        "sources": rows,
    }
