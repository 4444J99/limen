"""Canonical Studium research request primitives."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
import urllib.request
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence, cast
from urllib.parse import urlparse

import yaml


DEFAULT_CATALOG_URL = (
    "https://raw.githubusercontent.com/organvm/praxis-perpetua/main/governance/research-backend-profiles.yaml"
)
PERPLEXITY_RESEARCH_URL = "https://www.perplexity.ai/"
STANDING_INSTRUCTIONS_REF = (
    "organvm/praxis-perpetua:.claude/skills/sgo-commission-research/"
    "templates/perplexity-project-standing-instructions.md"
)
_REQUEST_ID = re.compile(r"^SGO-REQ-[0-9]{4}-[A-Z0-9-]+$")
_COMMISSION_ID = re.compile(r"^INQ-[0-9]{4}-[0-9]{3}$")
_CAPABILITY = re.compile(r"^[a-z][a-z0-9_]*$")
_PROFILE_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_SENSITIVE_PRIVACY = {"client_private", "essence_private"}
_PRESERVATION_TIERS = {
    "public_facing",
    "operational_internal",
    "client_private",
    "essence_private",
}
_TRANSMISSION_CLASSES = {"public_only", "sanitized_only", "forbidden"}
_VERIFICATION_SCORES = {
    "basic": 0.25,
    "corroborated": 0.5,
    "primary_source": 0.8,
    "systematic": 1.0,
}
_PRIMARY_SOURCE_RATIOS = {
    "basic": 0.0,
    "corroborated": 0.5,
    "primary_source": 0.8,
    "systematic": 0.8,
}
ATTESTATION_NAME_MAX_LENGTH = 120
RECEIPT_VERIFIER_MAX_LENGTH = ATTESTATION_NAME_MAX_LENGTH + len(" attestation sha256:") + 64


class ResearchContractError(ValueError):
    """Raised when a request, catalog, or output violates the owner contract."""


def now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def stable_hash(value: object) -> str:
    payload = value if isinstance(value, str) else canonical_json(value)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def mapping(value: object, *, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ResearchContractError(f"{field_name} must be a mapping")
    return {str(key): item for key, item in value.items()}


def strict_mapping(value: object, *, field_name: str) -> dict[str, Any]:
    """Return a JSON-object-shaped mapping without coercing YAML keys."""

    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ResearchContractError(f"{field_name} must be a JSON object")
    return dict(value)


def strict_string(value: object, *, field_name: str, min_length: int = 1) -> str:
    if not isinstance(value, str) or len(value) < min_length:
        raise ResearchContractError(f"{field_name} must be a string with at least {min_length} characters")
    return value


def strict_strings(
    value: object,
    *,
    field_name: str,
    min_items: int = 0,
    pattern: re.Pattern[str] | None = None,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ResearchContractError(f"{field_name} must be an array")
    if len(value) < min_items:
        raise ResearchContractError(f"{field_name} must contain at least {min_items} item(s)")
    if any(not isinstance(item, str) or not item for item in value):
        raise ResearchContractError(f"{field_name} items must be non-empty strings")
    if len(set(value)) != len(value):
        raise ResearchContractError(f"{field_name} items must be unique")
    if pattern is not None and any(not pattern.fullmatch(item) for item in value):
        raise ResearchContractError(f"{field_name} contains an invalid identifier")
    return tuple(value)


def strings(value: object, *, field_name: str = "value") -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if not isinstance(value, Sequence):
        raise ResearchContractError(f"{field_name} must be a string or sequence")
    return tuple(str(item).strip() for item in value if str(item).strip())


def nonnegative_number(value: object, *, field_name: str, default: float | None = None) -> float | None:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ResearchContractError(f"{field_name} must be numeric")
    try:
        parsed = float(cast(Any, value))
    except (TypeError, ValueError) as exc:
        raise ResearchContractError(f"{field_name} must be numeric") from exc
    if parsed < 0:
        raise ResearchContractError(f"{field_name} cannot be negative")
    return parsed


def verification_score(level: str) -> float:
    try:
        return _VERIFICATION_SCORES[level]
    except KeyError as exc:
        raise ResearchContractError(f"unsupported verification_strength: {level}") from exc


def safe_owner_reference(value: object, *, field_name: str) -> str:
    reference = strict_string(value, field_name=field_name)
    path = PurePosixPath(reference)
    if (
        not reference
        or reference.startswith(("/", "~"))
        or "://" in reference
        or "\\" in reference
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ResearchContractError(f"{field_name} must be a safe owner-relative path")
    return reference


def iso_datetime(value: object) -> str | None:
    if value is None or not str(value).strip():
        return None
    raw = str(value).strip()
    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", raw):
        return f"{raw}T00:00:00Z"
    candidate = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return raw


def _public_https_url(value: str) -> str:
    """Require an HTTPS URL whose current DNS answers are all globally routable."""

    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError as exc:
        raise ResearchContractError("remote document URL is invalid") from exc
    if parsed.scheme != "https" or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ResearchContractError("remote documents require a public HTTPS URL without userinfo")

    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith((".local", ".localhost")):
        raise ResearchContractError("remote document host must be public")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        try:
            answers = socket.getaddrinfo(host, port or 443, type=socket.SOCK_STREAM)
            addresses = {ipaddress.ip_address(str(answer[4][0]).split("%", 1)[0]) for answer in answers}
        except (OSError, ValueError) as exc:
            raise ResearchContractError("remote document host must resolve to a public address") from exc
        if not addresses or any(not address.is_global for address in addresses):
            raise ResearchContractError("remote document host must resolve only to public addresses")
    else:
        if not literal.is_global:
            raise ResearchContractError("remote document host must be public")
    return value


def load_document(source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    """Load owner YAML/JSON from an injected mapping, local path, or public URL."""

    if isinstance(source, Mapping):
        return strict_mapping(source, field_name="document")
    raw_source = str(source)
    parsed = urlparse(raw_source)
    if parsed.scheme:
        remote_url = _public_https_url(raw_source)
        request = urllib.request.Request(remote_url, headers={"User-Agent": "limen-research/1"})
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - explicit catalog input
            text = response.read().decode("utf-8")
    else:
        text = Path(raw_source).expanduser().read_text(encoding="utf-8")
    return strict_mapping(yaml.safe_load(text), field_name="document")


@dataclass(frozen=True)
class ResearchRequest:
    schema_version: str
    request_id: str
    requested_at: str
    commission_id: str | None
    question: str
    context_refs: tuple[Mapping[str, str], ...]
    required_capabilities: tuple[str, ...]
    freshness: Mapping[str, Any]
    domain_constraints: Mapping[str, Any]
    verification_level: str
    preservation_tier: str
    external_transmission: str
    latency_ceiling_seconds: int
    spend_ceiling_usd: float
    output_format: str
    owner_repo: str
    report_ref: str
    receipt_ref: str
    raw_export_ref: str | None
    required_sections: tuple[str, ...]
    canonical_payload: Mapping[str, object]
    preferred_profile: str | None = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ResearchRequest:
        data = strict_mapping(payload, field_name="ResearchRequest")
        allowed = {
            "schema_version",
            "request_id",
            "commission_id",
            "requested_at",
            "question",
            "context_refs",
            "required_capabilities",
            "freshness",
            "domain_constraints",
            "verification_strength",
            "preservation_tier",
            "external_transmission",
            "latency_ceiling_seconds",
            "spend_ceiling",
            "output_contract",
        }
        extras = sorted(set(data) - allowed)
        if extras:
            raise ResearchContractError("unknown ResearchRequest fields: " + ",".join(extras))

        schema_version = data.get("schema_version")
        if schema_version != "1.0":
            raise ResearchContractError("schema_version must be 1.0")

        request_id = strict_string(data.get("request_id"), field_name="request_id")
        question = strict_string(data.get("question"), field_name="question", min_length=10)
        requested_at = strict_string(data.get("requested_at"), field_name="requested_at")
        if not _REQUEST_ID.fullmatch(request_id):
            raise ResearchContractError("request_id does not match the Studium contract")
        if "T" not in requested_at or not iso_datetime(requested_at):
            raise ResearchContractError("question and ISO requested_at are required")
        raw_commission_id = data.get("commission_id")
        if raw_commission_id is not None and not isinstance(raw_commission_id, str):
            raise ResearchContractError("commission_id must be a string or null")
        commission_id = raw_commission_id or None
        if commission_id and not _COMMISSION_ID.fullmatch(commission_id):
            raise ResearchContractError("commission_id does not match the Studium contract")

        context_refs: list[Mapping[str, str]] = []
        seen_context_refs: set[tuple[str, str]] = set()
        raw_context_refs = data.get("context_refs", [])
        if not isinstance(raw_context_refs, list):
            raise ResearchContractError("context_refs must be an array")
        for item in raw_context_refs:
            context = strict_mapping(item, field_name="context_refs item")
            if set(context) != {"owner_repo", "path"}:
                raise ResearchContractError("context_refs require only owner_repo and path")
            owner_repo = strict_string(
                context.get("owner_repo"),
                field_name="context_refs.owner_repo",
                min_length=3,
            )
            path = safe_owner_reference(context.get("path"), field_name="context_refs.path")
            key = (owner_repo, path)
            if key in seen_context_refs:
                raise ResearchContractError("context_refs must be unique")
            seen_context_refs.add(key)
            context_refs.append({"owner_repo": owner_repo, "path": path})

        capabilities = strict_strings(
            data.get("required_capabilities"),
            field_name="required_capabilities",
            min_items=1,
            pattern=_CAPABILITY,
        )
        verification_level = strict_string(
            data.get("verification_strength"),
            field_name="verification_strength",
        )
        verification_score(verification_level)
        preservation_tier = strict_string(data.get("preservation_tier"), field_name="preservation_tier")
        if preservation_tier not in _PRESERVATION_TIERS:
            raise ResearchContractError(f"unsupported preservation_tier: {preservation_tier}")
        external_transmission = strict_string(data.get("external_transmission"), field_name="external_transmission")
        if external_transmission not in _TRANSMISSION_CLASSES:
            raise ResearchContractError(f"unsupported external_transmission: {external_transmission}")
        if preservation_tier in _SENSITIVE_PRIVACY and external_transmission != "forbidden":
            raise ResearchContractError("client_private and essence_private requests forbid external transmission")

        latency = data.get("latency_ceiling_seconds")
        if isinstance(latency, bool) or not isinstance(latency, int) or latency < 1:
            raise ResearchContractError("latency_ceiling_seconds must be a positive integer")
        spend = strict_mapping(data.get("spend_ceiling"), field_name="spend_ceiling")
        if set(spend) != {"currency", "variable_cost"}:
            raise ResearchContractError("spend_ceiling requires only currency and variable_cost")
        if spend.get("currency") != "USD":
            raise ResearchContractError("spend_ceiling currency must be USD")
        spend_value = spend.get("variable_cost")
        if isinstance(spend_value, bool) or not isinstance(spend_value, (int, float)) or spend_value < 0:
            raise ResearchContractError("spend_ceiling.variable_cost must be a nonnegative number")

        output = strict_mapping(data.get("output_contract"), field_name="output_contract")
        output_fields = {
            "format",
            "owner_repo",
            "report_path",
            "receipt_path",
            "raw_export_ref",
            "required_sections",
        }
        if set(output) - output_fields:
            raise ResearchContractError("output_contract contains unknown fields")
        output_format = strict_string(output.get("format"), field_name="output_contract.format")
        owner_repo = strict_string(
            output.get("owner_repo"),
            field_name="output_contract.owner_repo",
            min_length=3,
        )
        report_ref = safe_owner_reference(output.get("report_path"), field_name="output_contract.report_path")
        receipt_ref = safe_owner_reference(output.get("receipt_path"), field_name="output_contract.receipt_path")
        raw_export_value = output.get("raw_export_ref")
        if raw_export_value is not None and not isinstance(raw_export_value, str):
            raise ResearchContractError("output_contract.raw_export_ref must be a string or null")
        raw_export_ref = raw_export_value or None
        if output_format not in {"json", "markdown"}:
            raise ResearchContractError("output_contract requires format, owner_repo, report_path, and receipt_path")
        if report_ref == receipt_ref:
            raise ResearchContractError("report_path and receipt_path must be distinct")
        if (
            preservation_tier in _SENSITIVE_PRIVACY
            and raw_export_ref
            and not raw_export_ref.startswith("private-owner://")
        ):
            raise ResearchContractError("sensitive raw exports require a private-owner raw_export_ref")
        if raw_export_ref and not raw_export_ref.startswith("private-owner://"):
            safe_owner_reference(raw_export_ref, field_name="output_contract.raw_export_ref")

        required_sections = strict_strings(output.get("required_sections", []), field_name="required_sections")

        freshness_present = "freshness" in data
        freshness = strict_mapping(data.get("freshness", {}), field_name="freshness")
        if freshness_present and not freshness:
            raise ResearchContractError("freshness must contain at least one constraint")
        if set(freshness) - {
            "retrieved_after",
            "published_after",
            "published_before",
            "max_source_age_days",
            "as_of",
        }:
            raise ResearchContractError("freshness contains unknown fields")
        for field_name in ("retrieved_after", "published_after", "published_before"):
            value = freshness.get(field_name)
            if value is not None and not isinstance(value, str):
                raise ResearchContractError(f"freshness.{field_name} must be an ISO date")
            try:
                if value:
                    date.fromisoformat(value)
            except ValueError as exc:
                raise ResearchContractError(f"freshness.{field_name} must be an ISO date") from exc
            if value and not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", value):
                raise ResearchContractError(f"freshness.{field_name} must be an ISO date")
        as_of = freshness.get("as_of")
        if as_of is not None and not isinstance(as_of, str):
            raise ResearchContractError("freshness.as_of must be an ISO date-time")
        if as_of and not iso_datetime(as_of):
            raise ResearchContractError("freshness.as_of must be an ISO date-time")
        max_age = freshness.get("max_source_age_days")
        if max_age is not None and (isinstance(max_age, bool) or not isinstance(max_age, int) or max_age < 0):
            raise ResearchContractError("freshness.max_source_age_days must be nonnegative")
        published_after = freshness.get("published_after")
        published_before = freshness.get("published_before")
        if (
            published_after
            and published_before
            and date.fromisoformat(published_after) > date.fromisoformat(published_before)
        ):
            raise ResearchContractError("freshness.published_after cannot exceed published_before")

        domain_constraints = strict_mapping(data.get("domain_constraints", {}), field_name="domain_constraints")
        if set(domain_constraints) - {
            "allow_domains",
            "deny_domains",
            "source_types",
            "jurisdictions",
            "languages",
        }:
            raise ResearchContractError("domain_constraints contains unknown fields")
        for field_name in (
            "allow_domains",
            "deny_domains",
            "source_types",
            "jurisdictions",
        ):
            strict_strings(
                domain_constraints.get(field_name, []),
                field_name=f"domain_constraints.{field_name}",
            )
        language_pattern = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]+)*$")
        strict_strings(
            domain_constraints.get("languages", []),
            field_name="domain_constraints.languages",
            pattern=language_pattern,
        )

        return cls(
            schema_version=schema_version,
            request_id=request_id,
            requested_at=requested_at,
            commission_id=commission_id,
            question=question,
            context_refs=tuple(context_refs),
            required_capabilities=capabilities,
            freshness=freshness,
            domain_constraints=domain_constraints,
            verification_level=verification_level,
            preservation_tier=preservation_tier,
            external_transmission=external_transmission,
            latency_ceiling_seconds=latency,
            spend_ceiling_usd=float(spend_value),
            output_format=output_format,
            owner_repo=owner_repo,
            report_ref=report_ref,
            receipt_ref=receipt_ref,
            raw_export_ref=raw_export_ref,
            required_sections=required_sections,
            canonical_payload=json.loads(json.dumps(data)),
        )

    @property
    def verification_strength(self) -> float:
        return verification_score(self.verification_level)

    @property
    def primary_source_ratio(self) -> float:
        return _PRIMARY_SOURCE_RATIOS[self.verification_level]

    @property
    def latency_ceiling_minutes(self) -> float:
        return self.latency_ceiling_seconds / 60

    @property
    def sensitive(self) -> bool:
        return self.preservation_tier in _SENSITIVE_PRIVACY

    def with_profile(self, profile_id: str | None) -> ResearchRequest:
        if profile_id is not None and not _PROFILE_ID.fullmatch(profile_id):
            raise ResearchContractError("profile override is not a valid owner profile identifier")
        return replace(self, preferred_profile=profile_id)

    def canonical_contract(self) -> dict[str, object]:
        return json.loads(json.dumps(self.canonical_payload))

    def public_contract(self) -> dict[str, object]:
        result = self.canonical_contract()
        result.pop("question", None)
        result["question_hash"] = stable_hash(self.question)
        if self.preferred_profile:
            result["runtime_preferred_profile"] = self.preferred_profile
        return result


def owner_path(owner_root: Path, reference: str) -> Path:
    root = owner_root.expanduser().resolve()
    target = (root / reference).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ResearchContractError(f"owner reference escapes owner root: {reference}") from exc
    return target


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
