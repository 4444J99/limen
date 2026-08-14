#!/usr/bin/env python3
"""Regenerate PSP-P05-W03 cost/failure summaries from public-safe sampled rows."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


SCHEMA_VERSION = "limen.positioning_cost_failure_sample.v1"
ALLOWED_STATES = {"done", "failed", "failed_blocked", "needs_human"}
ALLOWED_FAILURE_CLASSES = {
    "dependency_failure",
    "external_gate",
    "human_gate",
    "policy_failure",
    "predicate_failure",
    "resource_limit",
    "verification_failure",
}
REPRODUCTION_SCHEMA = "limen.positioning_cost_failure_reproduction.v1"
REVIEW_SCHEMA = "limen.positioning_cost_failure_review.v1"
POPULATION_SCHEMA = "limen.positioning_cost_failure_population.v1"
INDEPENDENT_REVIEWER_CLASSES = {"independent_human", "independent_model", "consented_collaborator"}
REVIEW_VERDICTS = {"publishable_public_safe", "withheld"}
ALLOWED_PROVENANCE = {"public_safe_observed", "synthetic"}
ALLOWED_SAMPLE_FIELDS = {"schema_version", "provenance", "window_start", "window_end", "population", "rows"}
POPULATION_FIELDS = {
    "schema_version",
    "source_id",
    "source_sha256",
    "window_start",
    "window_end",
    "population_count",
    "eligible_count",
    "selected_count",
    "selection_method",
    "selection_rule",
    "selection_seed_sha256",
    "exclusion_counts",
}
SELECTION_METHODS = {"census", "deterministic_hash_sample"}
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


def _parse_window_date(value: object, field: str, errors: list[str]) -> date | None:
    if not isinstance(value, str):
        errors.append(f"sample {field} must be an ISO date")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"sample {field} must be an ISO date")
        return None


def _parse_observed_at(value: object, index: int, errors: list[str]) -> datetime | None:
    if not isinstance(value, str) or not value:
        errors.append(f"row {index} requires observed_at")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"row {index} observed_at must be RFC3339")
        return None
    if parsed.tzinfo is None:
        errors.append(f"row {index} observed_at must include a timezone")
        return None
    return parsed


def _validate_population(payload: dict[str, Any], rows: list[object], errors: list[str]) -> dict[str, Any] | None:
    population = payload.get("population")
    if not isinstance(population, dict):
        errors.append("sample requires an exact source population block")
        return None
    if set(population) != POPULATION_FIELDS:
        errors.append("sample population must use the exact contract fields")
    if population.get("schema_version") != POPULATION_SCHEMA:
        errors.append("sample population has an unsupported schema")
    source_id = population.get("source_id")
    if not isinstance(source_id, str) or not source_id.strip() or "\0" in source_id:
        errors.append("sample population requires a nonblank public-safe source_id")
    source_sha256 = population.get("source_sha256")
    if (
        not isinstance(source_sha256, str)
        or len(source_sha256) != 64
        or any(character not in "0123456789abcdef" for character in source_sha256)
    ):
        errors.append("sample population requires a lowercase source SHA-256")
    if population.get("window_start") != payload.get("window_start") or population.get("window_end") != payload.get(
        "window_end"
    ):
        errors.append("sample population window must exactly match the observed sample window")

    counts: dict[str, int] = {}
    for field in ("population_count", "eligible_count", "selected_count"):
        value = population.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(f"sample population {field} must be a nonnegative integer")
        else:
            counts[field] = value
    if counts.get("selected_count") != len(rows):
        errors.append("sample population selected_count must equal the exact row denominator")
    if {"population_count", "eligible_count", "selected_count"} <= set(counts):
        if counts["eligible_count"] > counts["population_count"] or counts["selected_count"] > counts["eligible_count"]:
            errors.append("sample population counts must satisfy selected <= eligible <= population")

    method = population.get("selection_method")
    if not isinstance(method, str) or method not in SELECTION_METHODS:
        errors.append("sample population requires a supported selection_method")
    rule = population.get("selection_rule")
    if not isinstance(rule, str) or not rule.strip() or "\0" in rule:
        errors.append("sample population requires a nonblank deterministic selection_rule")
    seed = population.get("selection_seed_sha256")
    if method == "census":
        if seed is not None:
            errors.append("census selection must not declare a selection seed")
        if counts and len(set(counts.values())) != 1:
            errors.append("census selection requires selected == eligible == population")
    elif not isinstance(seed, str) or len(seed) != 64 or any(character not in "0123456789abcdef" for character in seed):
        errors.append("deterministic sampling requires a lowercase selection seed SHA-256")

    exclusion_counts = population.get("exclusion_counts")
    valid_exclusions = isinstance(exclusion_counts, dict) and all(
        isinstance(reason, str)
        and bool(reason.strip())
        and "\0" not in reason
        and isinstance(count, int)
        and not isinstance(count, bool)
        and count >= 0
        for reason, count in exclusion_counts.items()
    )
    if not valid_exclusions:
        errors.append("sample population exclusion_counts must map public-safe reasons to nonnegative integers")
    elif {"population_count", "eligible_count"} <= set(counts) and sum(exclusion_counts.values()) != (
        counts["population_count"] - counts["eligible_count"]
    ):
        errors.append("sample population exclusions must reconcile population_count to eligible_count")
    return population


def validate_sample(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    unexpected_sample_fields = sorted(set(payload) - ALLOWED_SAMPLE_FIELDS)
    if unexpected_sample_fields:
        errors.append(f"sample has prohibited or unknown fields: {', '.join(unexpected_sample_fields)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported sample schema")
    provenance = payload.get("provenance")
    if not isinstance(provenance, str) or provenance not in ALLOWED_PROVENANCE:
        errors.append("sample requires explicit synthetic or public_safe_observed provenance")
    window_start = _parse_window_date(payload.get("window_start"), "window_start", errors)
    window_end = _parse_window_date(payload.get("window_end"), "window_end", errors)
    if window_start is not None and window_end is not None and window_start > window_end:
        errors.append("sample date window must be ordered")
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        return [*errors, "sample rows must be a non-empty list"]
    _validate_population(payload, rows, errors)
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"row {index} must be an object")
            continue
        unexpected = sorted(set(row) - ALLOWED_FIELDS)
        if unexpected:
            errors.append(f"row {index} has prohibited or unknown fields: {', '.join(unexpected)}")
        sample_id = row.get("sample_id")
        normalized_sample_id = sample_id.strip() if isinstance(sample_id, str) else None
        if not normalized_sample_id or normalized_sample_id in seen:
            errors.append(f"row {index} requires a unique public-safe sample_id")
        else:
            seen.add(normalized_sample_id)
        terminal_state = row.get("terminal_state")
        if not isinstance(terminal_state, str) or terminal_state not in ALLOWED_STATES:
            errors.append(f"row {index} has an unsupported terminal_state")
        model_cost_basis = row.get("model_cost_basis")
        if not isinstance(model_cost_basis, str) or model_cost_basis not in {"actual", "estimated", "unknown"}:
            errors.append(f"row {index} requires an explicit model_cost_basis")
        observed_at = _parse_observed_at(row.get("observed_at"), index, errors)
        if (
            observed_at is not None
            and window_start is not None
            and window_end is not None
            and not window_start <= observed_at.date() <= window_end
        ):
            errors.append(f"row {index} observed_at falls outside the declared window")
        for field in ("model_cost_usd", "human_minutes", "retry_cost_usd", "verification_cost_usd"):
            value = row.get(field)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0
            ):
                errors.append(f"row {index} field {field} must be null or non-negative")
        retry_count = row.get("retry_count")
        if retry_count is not None and (
            not isinstance(retry_count, int) or isinstance(retry_count, bool) or retry_count < 0
        ):
            errors.append(f"row {index} field retry_count must be null or a non-negative integer")
        failure_class = row.get("failure_class")
        if terminal_state == "done":
            if failure_class is not None:
                errors.append(f"row {index} done work must not carry failure_class")
        elif not isinstance(failure_class, str) or failure_class not in ALLOWED_FAILURE_CLASSES:
            errors.append(f"row {index} requires a reviewed public failure_class for non-done work")
        if terminal_state != "done":
            measured = [
                row.get(field)
                for field in (
                    "model_cost_usd",
                    "human_minutes",
                    "retry_count",
                    "retry_cost_usd",
                    "verification_cost_usd",
                )
            ]
            if all(
                isinstance(value, (int, float)) and not isinstance(value, bool) and value == 0 for value in measured
            ):
                errors.append(f"row {index} non-done work requires positive measured cost/time or an explicit unknown")
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


def _public_artifact_path(value: object) -> bool:
    if not isinstance(value, str) or not value.strip() or "\0" in value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and path.as_posix() == value


def _build_reproduction_command(
    input_artifact: object,
    data_digest: str,
    review_artifact: object,
    review_verdict: object,
) -> dict[str, Any]:
    argv = ["python3", "scripts/positioning-cost-failure-reproduction.py", "--input"]
    if isinstance(input_artifact, str):
        argv.append(input_artifact)
    if review_artifact is not None:
        argv.append("--review")
        if isinstance(review_artifact, str):
            argv.append(review_artifact)
    return {
        "schema_version": REPRODUCTION_SCHEMA,
        "argv": argv,
        "input_artifact": input_artifact,
        "input_sha256": data_digest,
        "review_artifact": review_artifact,
        "review_sha256": _canonical_digest(review_verdict) if isinstance(review_verdict, dict) else None,
    }


def _validate_required_receipt_fields(analysis: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    population = analysis.get("population")
    if not isinstance(population, dict) or analysis.get("population_digest") != _canonical_digest(population):
        errors.append("analysis population digest does not bind the exact source population contract")
    reproduction = analysis.get("reproduction_command")
    reproduction_fields = {
        "schema_version",
        "argv",
        "input_artifact",
        "input_sha256",
        "review_artifact",
        "review_sha256",
    }
    if not isinstance(reproduction, dict):
        errors.append("analysis requires a structured reproduction_command")
    else:
        if set(reproduction) != reproduction_fields:
            errors.append("analysis reproduction_command must use the exact contract fields")
        if reproduction.get("schema_version") != REPRODUCTION_SCHEMA:
            errors.append("analysis reproduction_command has an unsupported schema")
        input_artifact = reproduction.get("input_artifact")
        review_artifact = reproduction.get("review_artifact")
        if not _public_artifact_path(input_artifact):
            errors.append("analysis reproduction_command requires a public-safe input artifact path")
        if reproduction.get("input_sha256") != analysis.get("data_digest"):
            errors.append("analysis reproduction_command input digest does not bind the analyzed data")
        expected_argv = [
            "python3",
            "scripts/positioning-cost-failure-reproduction.py",
            "--input",
            input_artifact,
        ]
        if review_artifact is not None:
            if not _public_artifact_path(review_artifact):
                errors.append("analysis reproduction_command requires a public-safe review artifact path")
            expected_argv.extend(["--review", review_artifact])
        if reproduction.get("argv") != expected_argv:
            errors.append("analysis reproduction_command argv does not exactly replay the bound artifacts")

    verdict = analysis.get("review_verdict")
    verdict_fields = {
        "schema_version",
        "reviewer_class",
        "reviewer_identity",
        "observed_at",
        "data_digest",
        "population_digest",
        "verdict",
        "limitations",
    }
    if not isinstance(verdict, dict):
        errors.append("analysis requires a structured independent review_verdict")
        return errors
    if set(verdict) != verdict_fields:
        errors.append("analysis review_verdict must use the exact contract fields")
    if verdict.get("schema_version") != REVIEW_SCHEMA:
        errors.append("analysis review_verdict has an unsupported schema")
    if verdict.get("reviewer_class") not in INDEPENDENT_REVIEWER_CLASSES:
        errors.append("analysis review_verdict requires an independent reviewer class")
    reviewer_identity = verdict.get("reviewer_identity")
    if not isinstance(reviewer_identity, str) or not reviewer_identity.strip() or "\0" in reviewer_identity:
        errors.append("analysis review_verdict requires a nonblank reviewer identity")
    observed_at = verdict.get("observed_at")
    try:
        reviewed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        if reviewed_at.tzinfo is None:
            raise ValueError
    except (AttributeError, ValueError):
        errors.append("analysis review_verdict observed_at must be RFC3339 with a timezone")
    else:
        if reviewed_at > datetime.now(timezone.utc):
            errors.append("analysis review_verdict cannot be dated in the future")
    if verdict.get("data_digest") != analysis.get("data_digest"):
        errors.append("analysis review_verdict does not bind the analyzed data digest")
    if verdict.get("population_digest") != analysis.get("population_digest"):
        errors.append("analysis review_verdict does not bind the source population digest")
    if verdict.get("verdict") not in REVIEW_VERDICTS:
        errors.append("analysis review_verdict must explicitly publish or withhold")
    limitations = verdict.get("limitations")
    if not (
        isinstance(limitations, list)
        and bool(limitations)
        and all(isinstance(value, str) and bool(value.strip()) and "\0" not in value for value in limitations)
    ):
        errors.append("analysis review_verdict requires nonblank public-safe limitations")
    if analysis.get("provenance") == "synthetic" and verdict.get("verdict") == "publishable_public_safe":
        errors.append("synthetic cost samples cannot receive a publishable review verdict")
    if isinstance(reproduction, dict):
        review_artifact = reproduction.get("review_artifact")
        if not _public_artifact_path(review_artifact):
            errors.append("analysis requires the exact public-safe review artifact")
        if reproduction.get("review_sha256") != _canonical_digest(verdict):
            errors.append("analysis reproduction_command review digest does not bind the review verdict")
    return errors


def _finalize_analysis(analysis: dict[str, Any], *, data_complete: bool) -> dict[str, Any]:
    required_errors = _validate_required_receipt_fields(analysis)
    errors = [*analysis.get("errors", []), *required_errors]
    verdict = analysis.get("review_verdict")
    verdict_passed = isinstance(verdict, dict) and verdict.get("verdict") == "publishable_public_safe"
    publication_eligible = (
        data_complete and analysis.get("provenance") == "public_safe_observed" and verdict_passed and not errors
    )
    analysis["errors"] = errors
    analysis["publication_eligible"] = publication_eligible
    analysis["status"] = "regenerated" if publication_eligible else "withheld"
    return analysis


def reproduce(
    payload: dict[str, Any],
    *,
    input_artifact: object = None,
    review_artifact: object = None,
    review_verdict: object = None,
) -> dict[str, Any]:
    data_digest = _canonical_digest(payload)
    population = payload.get("population")
    population_digest = _canonical_digest(population) if isinstance(population, dict) else None
    reproduction_command = _build_reproduction_command(
        input_artifact,
        data_digest,
        review_artifact,
        review_verdict,
    )
    errors = validate_sample(payload)
    if errors:
        return _finalize_analysis(
            {
                "schema_version": "limen.positioning_cost_failure_analysis.v1",
                "provenance": payload.get("provenance"),
                "reproduction_command": reproduction_command,
                "review_verdict": review_verdict,
                "population": population,
                "population_digest": population_digest,
                "data_digest": data_digest,
                "errors": errors,
            },
            data_complete=False,
        )
    rows = payload["rows"]
    terminal_counts = {state: sum(row["terminal_state"] == state for row in rows) for state in sorted(ALLOWED_STATES)}
    failure_taxonomy: dict[str, int] = {}
    for row in rows:
        failure_class = row.get("failure_class")
        if failure_class:
            failure_taxonomy[failure_class] = failure_taxonomy.get(failure_class, 0) + 1
    model_basis = {
        basis: sum(row["model_cost_basis"] == basis for row in rows) for basis in ("actual", "estimated", "unknown")
    }
    dimensions = {
        "model_cost_usd": _distribution(rows, "model_cost_usd"),
        "human_minutes": _distribution(rows, "human_minutes"),
        "retry_count": _distribution(rows, "retry_count"),
        "retry_cost_usd": _distribution(rows, "retry_cost_usd"),
        "verification_cost_usd": _distribution(rows, "verification_cost_usd"),
    }
    missingness = {field: dimensions[field]["unknown"] for field in dimensions}
    data_complete = all(value == 0 for value in missingness.values()) and model_basis["unknown"] == 0
    analysis = {
        "schema_version": "limen.positioning_cost_failure_analysis.v1",
        "provenance": payload["provenance"],
        "reproduction_command": reproduction_command,
        "review_verdict": review_verdict,
        "population": population,
        "population_digest": population_digest,
        "window": {"start": payload["window_start"], "end": payload["window_end"]},
        "denominator": len(rows),
        "terminal_states": terminal_counts,
        "failure_taxonomy": dict(sorted(failure_taxonomy.items())),
        "model_cost_basis": model_basis,
        "dimensions": dimensions,
        "missingness": missingness,
        "data_digest": data_digest,
        "caveats": [
            "Human time remains minutes and is not converted to currency without a separately approved rate basis.",
            "Estimated model cost is distinguished from actual spend.",
            "Failed, blocked, and human-gated work remain in the denominator.",
        ],
        "errors": [],
    }
    return _finalize_analysis(analysis, data_complete=data_complete)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("input root must be an object")
        review_verdict: object = None
        if args.review is not None:
            review_verdict = json.loads(args.review.read_text(encoding="utf-8"))
            if not isinstance(review_verdict, dict):
                raise ValueError("review root must be an object")
        result = reproduce(
            payload,
            input_artifact=args.input.as_posix(),
            review_artifact=args.review.as_posix() if args.review is not None else None,
            review_verdict=review_verdict,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        result = {
            "schema_version": "limen.positioning_cost_failure_analysis.v1",
            "provenance": None,
            "reproduction_command": None,
            "review_verdict": None,
            "population": None,
            "population_digest": None,
            "data_digest": None,
            "errors": [f"cost/failure input failed closed: {exc}"],
            "publication_eligible": False,
            "status": "withheld",
        }
    serialized = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
