#!/usr/bin/env python3
"""Regenerate PSP-P05-W03 cost/failure summaries from public-safe sampled rows."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import ssl
import subprocess
import sys
from datetime import date, datetime, timezone
from http.client import HTTPException
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_CA_BUNDLE_CANDIDATES = (
    Path("/etc/ssl/cert.pem"),
    Path("/etc/ssl/certs/ca-certificates.crt"),
    Path("/etc/pki/tls/certs/ca-bundle.crt"),
    Path("/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem"),
)
TRUSTED_EXECUTABLE_DIRECTORIES = (
    Path(sys.executable).resolve().parent,
    Path("/opt/homebrew/bin"),
    Path("/usr/local/bin"),
    Path("/usr/bin"),
    Path("/bin"),
)
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
POPULATION_SOURCE_SCHEMA = "limen.positioning_cost_failure_population_source.v1"
MODEL_RATE_SCHEMA = "limen.positioning_model_cost_rate_basis.v1"
MODEL_RATE_SOURCE_SCHEMA = "limen.positioning_model_rate_source.v1"
AUTHORITY_RECEIPT_SCHEMA = "limen.positioning_cost_authority_receipt.v1"
AUTHORITY_RECEIPT_URL = re.compile(r"^https://github\.com/organvm/limen/issues/2200#issuecomment-[0-9]+$")
AUTHORITY_RECEIPT_BLOCK = re.compile(
    r"<!--\s*positioning-cost-authority-receipt\s*-->\s*```json\s*(\{.*?\})\s*```",
    re.DOTALL,
)
AUTHORITY_RECEIPT_FIELDS = {
    "schema_version",
    "evidence_kind",
    "subject_sha256",
    "actor_identity",
    "observed_at",
    "limitations",
}
AUTHORITY_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
TRUSTED_MODEL_REVIEWERS = {"chatgpt-codex-connector", "coderabbitai"}
INDEPENDENT_REVIEWER_CLASSES = {"independent_human", "independent_model", "consented_collaborator"}
REVIEW_VERDICTS = {"publishable_public_safe", "withheld"}
ALLOWED_PROVENANCE = {"public_safe_observed", "synthetic"}
MAX_PUBLIC_NUMBER = 2**53 - 1
AUTHENTICATED_IDENTITY = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?$")
ALLOWED_SAMPLE_FIELDS = {"schema_version", "provenance", "window_start", "window_end", "population", "rows"}
POPULATION_FIELDS = {
    "schema_version",
    "source_id",
    "source_artifact",
    "source_sha256",
    "source_receipt_url",
    "source_receipt_sha256",
    "source_manifest",
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
POPULATION_SOURCE_FIELDS = {"schema_version", "provenance", "source_id", "window_start", "window_end", "records"}
POPULATION_SOURCE_RECORD_FIELDS = {"sample_id", "author_identity", "eligible", "exclusion_reason"}
SELECTION_METHODS = {"census", "deterministic_hash_sample"}
SELECTION_RULES = {
    "census": "census of every eligible public-safe sample_id",
    "deterministic_hash_sample": "sha256(seed_sha256 + ':' + sample_id) ascending; take selected_count",
}
ALLOWED_FIELDS = {
    "sample_id",
    "observed_at",
    "terminal_state",
    "model_cost_usd",
    "model_cost_basis",
    "model_cost_rate_basis",
    "human_minutes",
    "retry_count",
    "retry_cost_usd",
    "verification_cost_usd",
    "failure_class",
}
MODEL_RATE_FIELDS = {
    "schema_version",
    "source_artifact",
    "source_sha256",
    "source_receipt_url",
    "source_receipt_sha256",
    "source_record_id",
    "model_id",
    "model_tier",
    "rate_observed_at",
    "input_units",
    "output_units",
    "input_rate_usd_per_million",
    "output_rate_usd_per_million",
    "formula",
    "calculated_cost_usd",
}
MODEL_RATE_SOURCE_FIELDS = {"schema_version", "provenance", "source_id", "source_url", "observed_at", "records"}
MODEL_RATE_SOURCE_RECORD_FIELDS = {
    "record_id",
    "model_id",
    "model_tier",
    "input_rate_usd_per_million",
    "output_rate_usd_per_million",
}
MODEL_RATE_FORMULA = (
    "((input_units * input_rate_usd_per_million) + (output_units * output_rate_usd_per_million)) / 1000000"
)
REVIEW_FIELDS = {
    "schema_version",
    "reviewer_class",
    "reviewer_identity",
    "observed_at",
    "data_digest",
    "population_digest",
    "verdict",
    "limitations",
    "authority_receipt_url",
    "authority_receipt_sha256",
}


def _canonical_digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _reject_duplicate_json_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON member: {key}")
        value[key] = child
    return value


def _loads_public_artifact(raw: str) -> object:
    return json.loads(raw, object_pairs_hook=_reject_duplicate_json_members)


def _contract_tls_context() -> ssl.SSLContext:
    """Use a fixed OS trust-bundle allowlist instead of ambient CA variables."""
    bundle = next((candidate for candidate in CONTRACT_CA_BUNDLE_CANDIDATES if candidate.is_file()), None)
    if bundle is None:
        raise OSError("contract-owned TLS trust bundle is unavailable")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(cafile=str(bundle))
    return context


def _contract_https_open(request: Request, *, timeout: int):
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=_contract_tls_context()))
    return opener.open(request, timeout=timeout)


def _public_authenticated_identity(value: object) -> bool:
    return isinstance(value, str) and bool(AUTHENTICATED_IDENTITY.fullmatch(value))


def _bounded_nonnegative_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        converted = float(value)
    except (OverflowError, ValueError):
        return False
    return math.isfinite(converted) and 0 <= converted <= MAX_PUBLIC_NUMBER


def _bounded_nonnegative_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= MAX_PUBLIC_NUMBER


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


def _lower_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _derived_selection_seed(population: dict[str, Any]) -> str:
    manifest = population.get("source_manifest")
    source_records = manifest.get("records") if isinstance(manifest, dict) else None
    selection_universe = (
        [
            {
                "sample_id": record.get("sample_id"),
                "eligible": record.get("eligible"),
                "exclusion_reason": record.get("exclusion_reason"),
            }
            for record in source_records
            if isinstance(record, dict)
        ]
        if isinstance(source_records, list)
        else []
    )
    selection_universe.sort(
        key=lambda value: (
            value.get("sample_id") if isinstance(value.get("sample_id"), str) else "",
            json.dumps(value, sort_keys=True, separators=(",", ":")),
        )
    )
    return _canonical_digest(
        {
            "schema_version": "limen.positioning_cost_failure_selection_seed.v1",
            "source_id": population.get("source_id"),
            "window_start": population.get("window_start"),
            "window_end": population.get("window_end"),
            "population_count": population.get("population_count"),
            "eligible_count": population.get("eligible_count"),
            "selection_rule": SELECTION_RULES["deterministic_hash_sample"],
            "selection_universe": selection_universe,
        }
    )


def _credential_free_https_url(value: object) -> bool:
    if not isinstance(value, str) or not value.strip() or "\0" in value:
        return False
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
    )


def _verify_authority_receipt(
    receipt_url: object,
    receipt_sha256: object,
    *,
    evidence_kind: str,
    subject_sha256: object,
    expected_actor: str | None = None,
    require_trusted_association: bool = False,
    expected_observed_at: str | None = None,
    authoritative_not_before: datetime | None = None,
) -> tuple[str, str]:
    if not isinstance(receipt_url, str) or not AUTHORITY_RECEIPT_URL.fullmatch(receipt_url):
        raise ValueError("authority receipt URL must be an immutable PSP-P05-W03 issue comment")
    if not _lower_sha256(receipt_sha256):
        raise ValueError("authority receipt requires a lowercase SHA-256")
    if not _lower_sha256(subject_sha256):
        raise ValueError("authority receipt subject requires a lowercase SHA-256")
    comment_id = receipt_url.rsplit("#issuecomment-", 1)[1]
    request = Request(
        f"https://api.github.com/repos/organvm/limen/issues/comments/{comment_id}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "limen-positioning-cost-failure-reproduction",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with _contract_https_open(request, timeout=30) as response:
        raw_comment = response.read(1_048_577)
    if len(raw_comment) > 1_048_576:
        raise ValueError("authority receipt comment exceeds the bounded response size")
    try:
        comment = _loads_public_artifact(raw_comment.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("authority comment response must be duplicate-free UTF-8 JSON") from exc
    if not isinstance(comment, dict) or comment.get("html_url") != receipt_url:
        raise ValueError("authority receipt comment identity differs from its immutable URL")
    author = comment.get("user")
    login = author.get("login") if isinstance(author, dict) else None
    association = comment.get("author_association")
    if not isinstance(login, str) or not login:
        raise ValueError("authority receipt comment has no authenticated actor")
    if expected_actor is not None and login.casefold() != expected_actor.casefold():
        raise ValueError("authority receipt actor differs from the bound reviewer identity")
    if require_trusted_association and association not in AUTHORITY_ASSOCIATIONS:
        raise ValueError("authority receipt actor is not an authorized repository actor")
    authenticated_comment_times: dict[str, datetime] = {}
    if expected_observed_at is not None or authoritative_not_before is not None:
        for field in ("created_at", "updated_at"):
            raw_timestamp = comment.get(field)
            try:
                timestamp = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
                if timestamp.tzinfo is None:
                    raise ValueError
            except (AttributeError, ValueError) as exc:
                raise ValueError(f"authority comment {field} must be authenticated RFC3339 metadata") from exc
            authenticated_comment_times[field] = timestamp
        if authenticated_comment_times["updated_at"] < authenticated_comment_times["created_at"]:
            raise ValueError("authority comment updated_at predates created_at")
        if authenticated_comment_times["updated_at"] > datetime.now(timezone.utc):
            raise ValueError("authority comment timing cannot be future-dated")
    body = comment.get("body")
    matches = AUTHORITY_RECEIPT_BLOCK.findall(body) if isinstance(body, str) else []
    if len(matches) != 1:
        raise ValueError("authority comment must contain exactly one marked receipt")
    try:
        receipt = _loads_public_artifact(matches[0])
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("authority receipt must be duplicate-free JSON") from exc
    if not isinstance(receipt, dict) or set(receipt) != AUTHORITY_RECEIPT_FIELDS:
        raise ValueError("authority receipt has an invalid exact schema")
    if receipt.get("schema_version") != AUTHORITY_RECEIPT_SCHEMA:
        raise ValueError("authority receipt has an unsupported schema")
    if receipt.get("evidence_kind") != evidence_kind or receipt.get("subject_sha256") != subject_sha256:
        raise ValueError("authority receipt does not bind the exact evidence subject")
    if receipt.get("actor_identity") != login:
        raise ValueError("authority receipt actor differs from the authenticated comment actor")
    observed_at = receipt.get("observed_at")
    try:
        observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        if observed.tzinfo is None:
            raise ValueError
    except (AttributeError, ValueError) as exc:
        raise ValueError("authority receipt observed_at must be RFC3339 with a timezone") from exc
    if observed > datetime.now(timezone.utc):
        raise ValueError("authority receipt cannot be future-dated")
    if expected_observed_at is not None:
        try:
            expected_observed = datetime.fromisoformat(expected_observed_at.replace("Z", "+00:00"))
            if expected_observed.tzinfo is None:
                raise ValueError
        except (AttributeError, ValueError) as exc:
            raise ValueError("bound review observed_at must be RFC3339 with a timezone") from exc
        if observed != expected_observed:
            raise ValueError("authority receipt observed_at differs from the bound independent review")
        if observed != authenticated_comment_times["updated_at"]:
            raise ValueError("independent review timing differs from authenticated comment metadata")
    if authoritative_not_before is not None and authenticated_comment_times["updated_at"] < authoritative_not_before:
        raise ValueError("authenticated independent review predates the complete observation window")
    limitations = receipt.get("limitations")
    if not (
        isinstance(limitations, list)
        and bool(limitations)
        and all(isinstance(value, str) and value.strip() and "\0" not in value for value in limitations)
    ):
        raise ValueError("authority receipt limitations must be public-safe text")
    if _canonical_digest(receipt) != receipt_sha256:
        raise ValueError("authority receipt digest differs from the marked receipt")
    return login, str(association)


def _trusted_named_executable(name: str) -> Path:
    if not name or Path(name).name != name or "/" in name or "\\" in name:
        raise ValueError("trusted executable name must be one path-free component")
    candidate = next(
        (
            directory / name
            for directory in dict.fromkeys(TRUSTED_EXECUTABLE_DIRECTORIES)
            if (directory / name).is_file() and os.access(directory / name, os.X_OK)
        ),
        None,
    )
    if candidate is None:
        raise OSError(f"trusted executable is unavailable: {name}")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise OSError(f"trusted executable is not executable: {resolved}")
    return resolved


def _sanitized_git_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for key in tuple(environment):
        if (
            key
            in {
                "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                "GIT_COMMON_DIR",
                "GIT_CONFIG",
                "GIT_CONFIG_COUNT",
                "GIT_CONFIG_PARAMETERS",
                "GIT_DIR",
                "GIT_EXEC_PATH",
                "GIT_INDEX_FILE",
                "GIT_NAMESPACE",
                "GIT_OBJECT_DIRECTORY",
                "GIT_SHALLOW_FILE",
                "GIT_WORK_TREE",
            }
            or key.startswith("GIT_CONFIG_KEY_")
            or key.startswith("GIT_CONFIG_VALUE_")
            or key.startswith("GIT_SSL_")
            or key.upper().startswith(("LD_", "DYLD_"))
            or key.lower() in {"all_proxy", "http_proxy", "https_proxy", "no_proxy"}
        ):
            environment.pop(key, None)
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_COUNT": "0",
            "GIT_GRAFT_FILE": os.devnull,
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "PATH": os.pathsep.join(str(path) for path in dict.fromkeys(TRUSTED_EXECUTABLE_DIRECTORIES)),
        }
    )
    return environment


def _safe_tracked_artifact(value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip() or value != value.strip() or "\0" in value or ":" in value:
        return None
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        return None
    try:
        candidate = (ROOT / pure).resolve(strict=True)
        candidate.relative_to(ROOT.resolve())
    except (OSError, ValueError):
        return None
    if not candidate.is_file():
        return None
    try:
        committed = subprocess.run(
            [str(_trusted_named_executable("git")), "show", f"HEAD:{pure.as_posix()}"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            timeout=30,
            env=_sanitized_git_environment(),
        )
        worktree_bytes = candidate.read_bytes()
    except (OSError, subprocess.TimeoutExpired):
        return None
    if committed.returncode != 0 or committed.stdout != worktree_bytes:
        return None
    return candidate


def _load_tracked_public_artifact(value: object) -> object:
    artifact = _safe_tracked_artifact(value)
    if artifact is None:
        raise ValueError("artifact is not a safe Git-tracked file matching its committed HEAD blob")
    raw = artifact.read_bytes()
    if len(raw) > 1_048_576:
        raise ValueError("artifact exceeds the bounded size")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("artifact is not UTF-8 JSON") from exc
    return _loads_public_artifact(text)


def _model_rate_source_record(
    detail: dict[str, Any],
    index: int,
    errors: list[str],
    provenance: object,
) -> dict[str, Any] | None:
    artifact = _safe_tracked_artifact(detail.get("source_artifact"))
    if artifact is None:
        errors.append(f"row {index} model rate basis requires a safe tracked rate artifact")
        return None
    try:
        raw = artifact.read_bytes()
    except OSError as exc:
        errors.append(f"row {index} model rate source artifact is unreadable: {exc}")
        return None
    if len(raw) > 65_536:
        errors.append(f"row {index} model rate source artifact exceeds the bounded size")
        return None
    if not _lower_sha256(detail.get("source_sha256")):
        errors.append(f"row {index} model rate basis requires a lowercase source SHA-256")
    elif hashlib.sha256(raw).hexdigest() != detail.get("source_sha256"):
        errors.append(f"row {index} model rate basis source SHA-256 differs from its tracked artifact")
    try:
        source = _loads_public_artifact(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"row {index} model rate source artifact is invalid JSON: {exc}")
        return None
    if not isinstance(source, dict) or set(source) != MODEL_RATE_SOURCE_FIELDS:
        errors.append(f"row {index} model rate source artifact has an invalid exact schema")
        return None
    if source.get("schema_version") != MODEL_RATE_SOURCE_SCHEMA:
        errors.append(f"row {index} model rate source artifact has an unsupported schema")
    if source.get("provenance") != provenance:
        errors.append(f"row {index} model rate source provenance differs from the sample provenance")
    if not isinstance(source.get("source_id"), str) or not source["source_id"].strip() or "\0" in source["source_id"]:
        errors.append(f"row {index} model rate source artifact requires a public-safe source_id")
    if not _credential_free_https_url(source.get("source_url")):
        errors.append(f"row {index} model rate source artifact requires a credential-free HTTPS source")
    if provenance == "public_safe_observed":
        try:
            _verify_authority_receipt(
                detail.get("source_receipt_url"),
                detail.get("source_receipt_sha256"),
                evidence_kind="model_rate_source",
                subject_sha256=detail.get("source_sha256"),
                require_trusted_association=True,
            )
        except (HTTPException, OSError, ValueError) as exc:
            errors.append(f"row {index} model rate source authority failed closed: {exc}")
    elif detail.get("source_receipt_url") is not None or detail.get("source_receipt_sha256") is not None:
        errors.append(f"row {index} synthetic model rate source must not declare an authority receipt")
    observed_at = source.get("observed_at")
    try:
        observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        if not isinstance(observed_at, str) or observed.tzinfo is None:
            raise ValueError
    except (AttributeError, ValueError):
        errors.append(f"row {index} model rate source observed_at must be RFC3339 with a timezone")
    else:
        if observed > datetime.now(timezone.utc):
            errors.append(f"row {index} model rate source cannot be future-dated")
        if detail.get("rate_observed_at") != observed_at:
            errors.append(f"row {index} model rate basis observed_at differs from its tracked source")
    records = source.get("records")
    if not isinstance(records, list) or not records:
        errors.append(f"row {index} model rate source requires a non-empty records list")
        return None
    selected: dict[str, Any] | None = None
    seen: set[str] = set()
    for record_index, record in enumerate(records):
        if not isinstance(record, dict) or set(record) != MODEL_RATE_SOURCE_RECORD_FIELDS:
            errors.append(f"row {index} model rate source record {record_index} has an invalid exact schema")
            continue
        record_id = record.get("record_id")
        if not isinstance(record_id, str) or not record_id.strip() or "\0" in record_id or record_id in seen:
            errors.append(f"row {index} model rate source record {record_index} requires a unique record_id")
            continue
        seen.add(record_id)
        for field in ("model_id", "model_tier"):
            value = record.get(field)
            if not isinstance(value, str) or not value.strip() or "\0" in value:
                errors.append(f"row {index} model rate source record {record_index} requires {field}")
        for field in ("input_rate_usd_per_million", "output_rate_usd_per_million"):
            value = record.get(field)
            if not _bounded_nonnegative_number(value):
                errors.append(f"row {index} model rate source record {record_index} requires a valid {field}")
        if record_id == detail.get("source_record_id"):
            selected = record
    if selected is None:
        errors.append(f"row {index} model rate basis source_record_id is absent from its tracked source")
    return selected


def _validate_population_source(
    population: dict[str, Any],
    provenance: object,
    errors: list[str],
) -> tuple[list[str], dict[str, int]]:
    source = population.get("source_manifest")
    if not isinstance(source, dict) or set(source) != POPULATION_SOURCE_FIELDS:
        errors.append("sample population requires an exact public-safe source manifest")
        return [], {}
    artifact = _safe_tracked_artifact(population.get("source_artifact"))
    artifact_source: object = None
    if artifact is None:
        errors.append("sample population requires a safe tracked authoritative source artifact")
    else:
        try:
            raw = artifact.read_bytes()
        except OSError as exc:
            errors.append(f"sample population source artifact is unreadable: {exc}")
        else:
            if len(raw) > 1_048_576:
                errors.append("sample population source artifact exceeds the bounded size")
            if not _lower_sha256(population.get("source_sha256")):
                errors.append("sample population requires a lowercase source SHA-256")
            elif hashlib.sha256(raw).hexdigest() != population.get("source_sha256"):
                errors.append("sample population source SHA-256 differs from its tracked artifact")
            try:
                artifact_source = _loads_public_artifact(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                errors.append(f"sample population source artifact is invalid JSON: {exc}")
    if artifact_source != source:
        errors.append("sample population source manifest differs from its tracked authoritative artifact")
    if source.get("schema_version") != POPULATION_SOURCE_SCHEMA:
        errors.append("sample population source manifest has an unsupported schema")
    if source.get("provenance") != provenance:
        errors.append("sample population source provenance differs from the sample provenance")
    if source.get("source_id") != population.get("source_id"):
        errors.append("sample population source manifest identity differs from source_id")
    if source.get("window_start") != population.get("window_start") or source.get("window_end") != population.get(
        "window_end"
    ):
        errors.append("sample population source manifest window differs from the population window")
    records = source.get("records")
    if not isinstance(records, list) or not records:
        errors.append("sample population source manifest requires a non-empty records list")
        return [], {}
    eligible_ids: list[str] = []
    exclusion_counts: dict[str, int] = {}
    seen: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict) or set(record) != POPULATION_SOURCE_RECORD_FIELDS:
            errors.append(f"sample population source record {index} has an invalid exact schema")
            continue
        sample_id = record.get("sample_id")
        normalized = sample_id.strip() if isinstance(sample_id, str) else ""
        if not normalized or normalized != sample_id or "\0" in normalized or normalized in seen:
            errors.append(f"sample population source record {index} requires a unique normalized sample_id")
            continue
        seen.add(normalized)
        author_identity = record.get("author_identity")
        if not _public_authenticated_identity(author_identity):
            errors.append(f"sample population source record {index} requires a public-safe author identity")
        eligible = record.get("eligible")
        reason = record.get("exclusion_reason")
        if not isinstance(eligible, bool):
            errors.append(f"sample population source record {index} requires a boolean eligible disposition")
        elif eligible:
            if reason is not None:
                errors.append(f"eligible source record {index} must not declare an exclusion reason")
            eligible_ids.append(normalized)
        elif not isinstance(reason, str) or not reason.strip() or "\0" in reason:
            errors.append(f"ineligible source record {index} requires a public-safe exclusion reason")
        else:
            exclusion_counts[reason] = exclusion_counts.get(reason, 0) + 1
    if provenance == "public_safe_observed":
        try:
            _verify_authority_receipt(
                population.get("source_receipt_url"),
                population.get("source_receipt_sha256"),
                evidence_kind="population_manifest",
                subject_sha256=population.get("source_sha256"),
                require_trusted_association=True,
            )
        except (HTTPException, OSError, ValueError) as exc:
            errors.append(f"sample population source authority failed closed: {exc}")
    elif population.get("source_receipt_url") is not None or population.get("source_receipt_sha256") is not None:
        errors.append("synthetic population source must not declare an authority receipt")
    return eligible_ids, exclusion_counts


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
    if not _lower_sha256(source_sha256):
        errors.append("sample population requires a lowercase source SHA-256")
    if population.get("window_start") != payload.get("window_start") or population.get("window_end") != payload.get(
        "window_end"
    ):
        errors.append("sample population window must exactly match the observed sample window")

    eligible_ids, derived_exclusions = _validate_population_source(population, payload.get("provenance"), errors)
    counts: dict[str, int] = {}
    for field in ("population_count", "eligible_count", "selected_count"):
        value = population.get(field)
        if not _bounded_nonnegative_integer(value):
            errors.append(f"sample population {field} must be a nonnegative integer")
        else:
            counts[field] = value
    if counts.get("selected_count") != len(rows):
        errors.append("sample population selected_count must equal the exact row denominator")
    if {"population_count", "eligible_count", "selected_count"} <= set(counts):
        if counts["eligible_count"] > counts["population_count"] or counts["selected_count"] > counts["eligible_count"]:
            errors.append("sample population counts must satisfy selected <= eligible <= population")
        source = population.get("source_manifest")
        source_records = source.get("records") if isinstance(source, dict) else None
        if isinstance(source_records, list) and counts["population_count"] != len(source_records):
            errors.append("sample population_count must equal the source manifest denominator")
        if counts["eligible_count"] != len(eligible_ids):
            errors.append("sample eligible_count must equal the source manifest eligible set")

    method = population.get("selection_method")
    if not isinstance(method, str) or method not in SELECTION_METHODS:
        errors.append("sample population requires a supported selection_method")
    rule = population.get("selection_rule")
    if not isinstance(rule, str) or method not in SELECTION_RULES or rule != SELECTION_RULES[method]:
        errors.append("sample population requires the exact contract-owned selection_rule")
    seed = population.get("selection_seed_sha256")
    if method == "census":
        if seed is not None:
            errors.append("census selection must not declare a selection seed")
        if counts and len(set(counts.values())) != 1:
            errors.append("census selection requires selected == eligible == population")
    elif not _lower_sha256(seed):
        errors.append("deterministic sampling requires a lowercase selection seed SHA-256")
    elif seed != _derived_selection_seed(population):
        errors.append("deterministic sampling seed must derive from immutable source and window material")

    exclusion_counts = population.get("exclusion_counts")
    valid_exclusions = isinstance(exclusion_counts, dict) and all(
        isinstance(reason, str) and bool(reason.strip()) and "\0" not in reason and _bounded_nonnegative_integer(count)
        for reason, count in exclusion_counts.items()
    )
    if not valid_exclusions:
        errors.append("sample population exclusion_counts must map public-safe reasons to nonnegative integers")
    else:
        if exclusion_counts != derived_exclusions:
            errors.append("sample population exclusions differ from the source manifest dispositions")
        if {"population_count", "eligible_count"} <= set(counts) and sum(exclusion_counts.values()) != (
            counts["population_count"] - counts["eligible_count"]
        ):
            errors.append("sample population exclusions must reconcile population_count to eligible_count")

    selected_ids = [
        row.get("sample_id").strip()
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("sample_id"), str) and row.get("sample_id").strip()
    ]
    if len(selected_ids) == len(rows) and method == "census" and selected_ids != eligible_ids:
        errors.append("census selection must contain every eligible source sample_id in manifest order")
    if len(selected_ids) == len(rows) and method == "deterministic_hash_sample" and _lower_sha256(seed):
        expected_ids = sorted(
            eligible_ids,
            key=lambda sample_id: (hashlib.sha256(f"{seed}:{sample_id}".encode()).hexdigest(), sample_id),
        )[: counts.get("selected_count", 0)]
        if selected_ids != expected_ids:
            errors.append("deterministic sample membership differs from the contract-owned hash selection")
    return population


def _validate_model_rate_basis(row: dict[str, Any], index: int, errors: list[str], provenance: object) -> None:
    basis = row.get("model_cost_basis")
    detail = row.get("model_cost_rate_basis")
    model_cost = row.get("model_cost_usd")
    if basis == "actual":
        if detail is not None:
            errors.append(f"row {index} actual model cost must not declare an estimated rate basis")
        return
    if basis == "unknown":
        if detail is not None or model_cost is not None:
            errors.append(f"row {index} unknown model cost must have null cost and rate basis")
        return
    if basis != "estimated":
        return
    if not isinstance(detail, dict) or set(detail) != MODEL_RATE_FIELDS:
        errors.append(f"row {index} estimated model cost requires an exact public-safe rate basis")
        return
    if detail.get("schema_version") != MODEL_RATE_SCHEMA:
        errors.append(f"row {index} model rate basis has an unsupported schema")
    for field in ("source_record_id", "model_id", "model_tier"):
        value = detail.get(field)
        if not isinstance(value, str) or not value.strip() or "\0" in value:
            errors.append(f"row {index} model rate basis requires a nonblank {field}")
    source_record = _model_rate_source_record(detail, index, errors, provenance)
    rate_observed_at = detail.get("rate_observed_at")
    try:
        parsed_rate = datetime.fromisoformat(rate_observed_at.replace("Z", "+00:00"))
        if parsed_rate.tzinfo is None:
            raise ValueError
    except (AttributeError, ValueError):
        errors.append(f"row {index} model rate basis observed_at must be RFC3339 with a timezone")
    else:
        if parsed_rate > datetime.now(timezone.utc):
            errors.append(f"row {index} model rate basis cannot be future-dated")
    units: dict[str, int] = {}
    for field in ("input_units", "output_units"):
        value = detail.get(field)
        if not _bounded_nonnegative_integer(value):
            errors.append(f"row {index} model rate basis {field} must be a nonnegative integer")
        else:
            units[field] = value
    rates: dict[str, float] = {}
    for field in ("input_rate_usd_per_million", "output_rate_usd_per_million", "calculated_cost_usd"):
        value = detail.get(field)
        if not _bounded_nonnegative_number(value):
            errors.append(f"row {index} model rate basis {field} must be a nonnegative finite number")
        else:
            rates[field] = float(value)
    if detail.get("formula") != MODEL_RATE_FORMULA:
        errors.append(f"row {index} model rate basis must use the contract-owned formula")
    if isinstance(source_record, dict):
        for field in (
            "model_id",
            "model_tier",
            "input_rate_usd_per_million",
            "output_rate_usd_per_million",
        ):
            if detail.get(field) != source_record.get(field):
                errors.append(f"row {index} model rate basis {field} differs from its tracked source record")
    if {"input_units", "output_units"} <= set(units) and {
        "input_rate_usd_per_million",
        "output_rate_usd_per_million",
        "calculated_cost_usd",
    } <= set(rates):
        calculated = (
            units["input_units"] * rates["input_rate_usd_per_million"]
            + units["output_units"] * rates["output_rate_usd_per_million"]
        ) / 1_000_000
        if not math.isclose(calculated, rates["calculated_cost_usd"], rel_tol=0, abs_tol=1e-9):
            errors.append(f"row {index} model rate basis calculated cost differs from the exact formula")
        if not _bounded_nonnegative_number(model_cost) or not math.isclose(
            float(model_cost), rates["calculated_cost_usd"], rel_tol=0, abs_tol=1e-9
        ):
            errors.append(f"row {index} estimated model cost differs from its reproducible rate basis")


def _observation_cutoff(payload: dict[str, Any]) -> datetime | None:
    candidates: list[datetime] = []
    window_end = payload.get("window_end")
    if isinstance(window_end, str):
        try:
            parsed_end = date.fromisoformat(window_end)
        except ValueError:
            pass
        else:
            candidates.append(datetime.combine(parsed_end, datetime.max.time(), tzinfo=timezone.utc))
    rows = payload.get("rows")
    if isinstance(rows, list):
        for row in rows:
            observed_at = row.get("observed_at") if isinstance(row, dict) else None
            if not isinstance(observed_at, str):
                continue
            try:
                observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
            except ValueError:
                continue
            if observed.tzinfo is not None:
                candidates.append(observed)
    return max(candidates) if candidates else None


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
    if window_end is not None and window_end > datetime.now(timezone.utc).date():
        errors.append("sample date window cannot end in the future")
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
        if observed_at is not None and observed_at > datetime.now(timezone.utc):
            errors.append(f"row {index} observed_at cannot be in the future")
        if (
            observed_at is not None
            and window_start is not None
            and window_end is not None
            and not window_start <= observed_at.date() <= window_end
        ):
            errors.append(f"row {index} observed_at falls outside the declared window")
        for field in ("model_cost_usd", "human_minutes", "retry_cost_usd", "verification_cost_usd"):
            value = row.get(field)
            if value is not None and not _bounded_nonnegative_number(value):
                errors.append(f"row {index} field {field} must be null or non-negative")
        retry_count = row.get("retry_count")
        if retry_count is not None and not _bounded_nonnegative_integer(retry_count):
            errors.append(f"row {index} field retry_count must be null or a non-negative integer")
        _validate_model_rate_basis(row, index, errors, provenance)
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
        else:
            try:
                committed_input = _load_tracked_public_artifact(input_artifact)
            except (OSError, ValueError) as exc:
                errors.append(f"analysis reproduction input is not committed and reproducible: {exc}")
            else:
                if not isinstance(committed_input, dict) or _canonical_digest(committed_input) != analysis.get(
                    "data_digest"
                ):
                    errors.append("analysis reproduction input differs from its committed HEAD artifact")
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
            else:
                try:
                    committed_review = _load_tracked_public_artifact(review_artifact)
                except (OSError, ValueError) as exc:
                    errors.append(f"analysis reproduction review is not committed and reproducible: {exc}")
                else:
                    if not isinstance(committed_review, dict) or committed_review != analysis.get("review_verdict"):
                        errors.append("analysis reproduction review differs from its committed HEAD artifact")
            expected_argv.extend(["--review", review_artifact])
        if reproduction.get("argv") != expected_argv:
            errors.append("analysis reproduction_command argv does not exactly replay the bound artifacts")

    verdict = analysis.get("review_verdict")
    if not isinstance(verdict, dict):
        errors.append("analysis requires a structured independent review_verdict")
        return errors
    if set(verdict) != REVIEW_FIELDS:
        errors.append("analysis review_verdict must use the exact contract fields")
    if verdict.get("schema_version") != REVIEW_SCHEMA:
        errors.append("analysis review_verdict has an unsupported schema")
    if verdict.get("reviewer_class") not in INDEPENDENT_REVIEWER_CLASSES:
        errors.append("analysis review_verdict requires an independent reviewer class")
    reviewer_identity = verdict.get("reviewer_identity")
    if not _public_authenticated_identity(reviewer_identity):
        errors.append(
            "analysis review_verdict requires a nonblank reviewer identity in the canonical authenticated character set"
        )
    source_manifest = population.get("source_manifest") if isinstance(population, dict) else None
    source_records = source_manifest.get("records") if isinstance(source_manifest, dict) else None
    author_identities = (
        {
            record.get("author_identity").casefold()
            for record in source_records
            if isinstance(record, dict) and isinstance(record.get("author_identity"), str)
        }
        if isinstance(source_records, list)
        else set()
    )
    if isinstance(reviewer_identity, str) and reviewer_identity.casefold() in author_identities:
        errors.append("analysis review_verdict reviewer must differ from every sample author")
    observed_at = verdict.get("observed_at")
    reviewed_at: datetime | None = None
    try:
        reviewed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        if reviewed_at.tzinfo is None:
            raise ValueError
    except (AttributeError, ValueError):
        errors.append("analysis review_verdict observed_at must be RFC3339 with a timezone")
    else:
        if reviewed_at > datetime.now(timezone.utc):
            errors.append("analysis review_verdict cannot be dated in the future")
    cutoff_value = analysis.get("observation_cutoff")
    cutoff: datetime | None = None
    try:
        cutoff = datetime.fromisoformat(cutoff_value.replace("Z", "+00:00"))
        if cutoff.tzinfo is None:
            raise ValueError
    except (AttributeError, ValueError):
        errors.append("analysis requires an exact observation cutoff")
    else:
        if reviewed_at is not None and reviewed_at < cutoff:
            errors.append("analysis review_verdict must follow the complete observation window")
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
    if analysis.get("provenance") == "public_safe_observed":
        review_subject = {
            key: value
            for key, value in verdict.items()
            if key not in {"authority_receipt_url", "authority_receipt_sha256"}
        }
        try:
            authenticated_login, authenticated_association = _verify_authority_receipt(
                verdict.get("authority_receipt_url"),
                verdict.get("authority_receipt_sha256"),
                evidence_kind="independent_review",
                subject_sha256=_canonical_digest(review_subject),
                expected_actor=reviewer_identity if isinstance(reviewer_identity, str) else None,
                expected_observed_at=observed_at if isinstance(observed_at, str) else None,
                authoritative_not_before=cutoff,
            )
        except (HTTPException, OSError, ValueError) as exc:
            errors.append(f"analysis independent review authority failed closed: {exc}")
        else:
            if verdict.get("reviewer_class") == "independent_model":
                if authenticated_login.casefold() not in {value.casefold() for value in TRUSTED_MODEL_REVIEWERS}:
                    errors.append("analysis independent model review is not owned by a trusted model reviewer")
            elif authenticated_association not in AUTHORITY_ASSOCIATIONS:
                errors.append("analysis independent human review is not owned by an authorized collaborator")
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
    observation_cutoff = _observation_cutoff(payload)
    observation_cutoff_value = (
        observation_cutoff.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        if observation_cutoff is not None
        else None
    )
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
                "observation_cutoff": observation_cutoff_value,
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
        "observation_cutoff": observation_cutoff_value,
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
        payload = _loads_public_artifact(args.input.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("input root must be an object")
        review_verdict: object = None
        if args.review is not None:
            review_verdict = _loads_public_artifact(args.review.read_text(encoding="utf-8"))
            if not isinstance(review_verdict, dict):
                raise ValueError("review root must be an object")
        result = reproduce(
            payload,
            input_artifact=args.input.as_posix(),
            review_artifact=args.review.as_posix() if args.review is not None else None,
            review_verdict=review_verdict,
        )
    except (HTTPException, OSError, json.JSONDecodeError, ValueError) as exc:
        result = {
            "schema_version": "limen.positioning_cost_failure_analysis.v1",
            "provenance": None,
            "reproduction_command": None,
            "review_verdict": None,
            "population": None,
            "population_digest": None,
            "observation_cutoff": None,
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
