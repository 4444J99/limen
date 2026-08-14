#!/usr/bin/env python3
"""Regenerate PSP-P05-W03 cost/failure summaries from public-safe sampled rows."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "limen.positioning_cost_failure_sample.v1"
ALLOWED_STATES = {"done", "failed", "failed_blocked", "needs_human"}
ALLOWED_FIELDS = {
    "sample_id",
    "observed_at",
    "terminal_state",
    "model_cost_usd",
    "model_cost_basis",
    "human_minutes",
    "retry_count",
    "retry_cost_usd",
    "verification_cost_usd",
    "failure_class",
}


def _canonical_digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def validate_sample(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported sample schema")
    if payload.get("synthetic_or_public_safe") is not True:
        errors.append("sample must declare synthetic_or_public_safe true")
    if not payload.get("window_start") or not payload.get("window_end"):
        errors.append("sample requires a date window")
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        return [*errors, "sample rows must be a non-empty list"]
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"row {index} must be an object")
            continue
        unexpected = sorted(set(row) - ALLOWED_FIELDS)
        if unexpected:
            errors.append(f"row {index} has prohibited or unknown fields: {', '.join(unexpected)}")
        sample_id = row.get("sample_id")
        if not sample_id or sample_id in seen:
            errors.append(f"row {index} requires a unique public-safe sample_id")
        seen.add(str(sample_id))
        if row.get("terminal_state") not in ALLOWED_STATES:
            errors.append(f"row {index} has an unsupported terminal_state")
        if row.get("model_cost_basis") not in {"actual", "estimated", "unknown"}:
            errors.append(f"row {index} requires an explicit model_cost_basis")
        for field in ("model_cost_usd", "human_minutes", "retry_count", "retry_cost_usd", "verification_cost_usd"):
            value = row.get(field)
            if value is not None and (not isinstance(value, (int, float)) or value < 0):
                errors.append(f"row {index} field {field} must be null or non-negative")
        if row.get("terminal_state") != "done" and not row.get("failure_class"):
            errors.append(f"row {index} requires failure_class for non-done work")
    return errors


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return round(ordered[low], 6)
    value = ordered[low] * (high - rank) + ordered[high] * (rank - low)
    return round(value, 6)


def _distribution(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    values = [float(row[field]) for row in rows if isinstance(row.get(field), (int, float))]
    return {
        "known": len(values),
        "unknown": len(rows) - len(values),
        "total": round(sum(values), 6) if values else None,
        "min": min(values) if values else None,
        "p50": _percentile(values, 0.5),
        "p90": _percentile(values, 0.9),
        "max": max(values) if values else None,
    }


def reproduce(payload: dict[str, Any]) -> dict[str, Any]:
    errors = validate_sample(payload)
    if errors:
        return {"status": "withheld", "errors": errors, "publication_eligible": False}
    rows = payload["rows"]
    terminal_counts = {state: sum(row["terminal_state"] == state for row in rows) for state in sorted(ALLOWED_STATES)}
    failure_taxonomy: dict[str, int] = {}
    for row in rows:
        failure_class = row.get("failure_class")
        if failure_class:
            failure_taxonomy[failure_class] = failure_taxonomy.get(failure_class, 0) + 1
    model_basis = {
        basis: sum(row["model_cost_basis"] == basis for row in rows)
        for basis in ("actual", "estimated", "unknown")
    }
    dimensions = {
        "model_cost_usd": _distribution(rows, "model_cost_usd"),
        "human_minutes": _distribution(rows, "human_minutes"),
        "retry_count": _distribution(rows, "retry_count"),
        "retry_cost_usd": _distribution(rows, "retry_cost_usd"),
        "verification_cost_usd": _distribution(rows, "verification_cost_usd"),
    }
    missingness = {field: dimensions[field]["unknown"] for field in dimensions}
    publication_eligible = all(value == 0 for value in missingness.values()) and model_basis["unknown"] == 0
    return {
        "schema_version": "limen.positioning_cost_failure_analysis.v1",
        "status": "regenerated" if publication_eligible else "withheld",
        "publication_eligible": publication_eligible,
        "window": {"start": payload["window_start"], "end": payload["window_end"]},
        "denominator": len(rows),
        "terminal_states": terminal_counts,
        "failure_taxonomy": dict(sorted(failure_taxonomy.items())),
        "model_cost_basis": model_basis,
        "dimensions": dimensions,
        "missingness": missingness,
        "data_digest": _canonical_digest(payload),
        "caveats": [
            "Human time remains minutes and is not converted to currency without a separately approved rate basis.",
            "Estimated model cost is distinguished from actual spend.",
            "Failed, blocked, and human-gated work remain in the denominator.",
        ],
        "errors": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("input root must be an object")
    result = reproduce(payload)
    serialized = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
