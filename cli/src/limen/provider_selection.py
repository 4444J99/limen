"""Dynamic provider selection from task needs and live capability catalogs.

Limen owns safety, budget, and the requested execution shape. Providers own their
changing model catalogs. Model IDs are runtime outputs and never appear as defaults.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from dataclasses import asdict, dataclass, replace
from datetime import date
from typing import Any, Iterable, Sequence


_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _as_number(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


@dataclass(frozen=True)
class ExecutionProfile:
    """A provider-neutral request that can evolve without adding model names."""

    requested_hint: str | None
    reasoning_depth: float
    cost_pressure: float
    latency_pressure: float
    min_context: int
    min_output: int
    tools_required: bool
    attachments_required: bool
    planning_only: bool
    build_allowed: bool
    verification_strength: float

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))


def execution_profile_for(task: object | None) -> ExecutionProfile:
    """Derive a request profile from the task's current evidence.

    ``tier:*`` remains a backwards-compatible free-form hint, not an enum. New
    profiles derive from quantitative task shape and structured capability labels.
    Unknown hints survive into receipts/prompts without requiring a code change.
    """

    if task is None:
        return ExecutionProfile(None, 0.5, 0.5, 0.5, 8192, 2048, True, False, False, True, 0.5)

    labels = [str(item).strip().lower() for item in (getattr(task, "labels", None) or [])]
    requested_hint = next((label.split(":", 1)[1] for label in labels if label.startswith("tier:")), None)
    planning_only = "mode:plan-only" in labels or requested_hint == "plan"
    attachments_required = "capability:attachments" in labels

    priority = str(getattr(task, "priority", "medium") or "medium").lower()
    priority_weight = {"critical": 1.0, "high": 0.75, "medium": 0.45, "low": 0.2}.get(priority, 0.1)
    budget = max(1, int(getattr(task, "budget_cost", 1) or 1))
    dependencies = len(getattr(task, "depends_on", None) or [])
    text_size = sum(
        len(str(getattr(task, field, "") or ""))
        for field in ("title", "description", "context")
    )
    attempts = 0
    for entry in getattr(task, "dispatch_log", None) or []:
        status = str(getattr(entry, "status", "") or "")
        route_to = str(getattr(entry, "route_to", "") or "")
        if status in {"failed", "failed_blocked"} or route_to or "->" in status:
            attempts += 1

    complexity = _clamp(
        0.15
        + priority_weight * 0.25
        + min(1.0, dependencies / 4) * 0.15
        + min(1.0, text_size / 8000) * 0.2
        + min(1.0, attempts / 3) * 0.25
    )
    if requested_hint == "deep":
        complexity = 1.0
    elif requested_hint == "economy":
        complexity = min(complexity, 0.35)

    # Estimate prompt room from the actual packet, then round to a power of two.
    required_tokens = max(4096, text_size * 2 + dependencies * 1024)
    min_context = 1 << max(13, (required_tokens - 1).bit_length())
    min_output = max(2048, min(32768, min_context // 4))
    cost_pressure = _clamp(1.0 / math.sqrt(float(budget)))
    if requested_hint == "economy":
        cost_pressure = 1.0

    return ExecutionProfile(
        requested_hint=requested_hint,
        reasoning_depth=complexity,
        cost_pressure=cost_pressure,
        latency_pressure=priority_weight,
        min_context=min_context,
        min_output=min_output,
        tools_required=True,
        attachments_required=attachments_required,
        planning_only=planning_only,
        build_allowed=not planning_only,
        verification_strength=_clamp(0.4 + complexity * 0.6),
    )


def effective_profile(profile: ExecutionProfile, *, plan_accepted: bool) -> ExecutionProfile:
    """Without a current planning acceptance, request deep executable work instead."""

    if profile.planning_only and not plan_accepted:
        return replace(
            profile,
            reasoning_depth=1.0,
            planning_only=False,
            build_allowed=True,
            verification_strength=1.0,
        )
    return profile


@dataclass(frozen=True)
class ModelCapability:
    model_id: str
    active: bool
    text_input: bool
    text_output: bool
    toolcall: bool
    reasoning: bool
    attachment: bool
    context_limit: int
    output_limit: int
    input_cost: float
    output_cost: float
    variant_count: int
    release_ordinal: int

    @property
    def zero_cost(self) -> bool:
        return self.input_cost <= 0 and self.output_cost <= 0

    def satisfies(self, profile: ExecutionProfile) -> bool:
        return (
            self.active
            and self.text_input
            and self.text_output
            and (self.toolcall or not profile.tools_required)
            and (self.attachment or not profile.attachments_required)
            and self.context_limit >= profile.min_context
            and self.output_limit >= profile.min_output
        )


def _release_ordinal(value: object) -> int:
    try:
        return date.fromisoformat(str(value)).toordinal()
    except (TypeError, ValueError):
        return 0


def _capability_from_payload(payload: dict[str, Any], reported_id: str = "") -> ModelCapability | None:
    provider = str(payload.get("providerID") or "").strip()
    local_id = str(payload.get("id") or "").strip()
    model_id = reported_id.strip() or (f"{provider}/{local_id}" if provider and local_id else local_id)
    if not model_id:
        return None
    capabilities = payload.get("capabilities") if isinstance(payload.get("capabilities"), dict) else {}
    input_caps = capabilities.get("input") if isinstance(capabilities.get("input"), dict) else {}
    output_caps = capabilities.get("output") if isinstance(capabilities.get("output"), dict) else {}
    limits = payload.get("limit") if isinstance(payload.get("limit"), dict) else {}
    costs = payload.get("cost") if isinstance(payload.get("cost"), dict) else {}
    variants = payload.get("variants") if isinstance(payload.get("variants"), dict) else {}
    status = str(payload.get("status") or "active").strip().lower()
    return ModelCapability(
        model_id=model_id,
        active=status in {"active", "available", "ready"},
        text_input=bool(input_caps.get("text", True)),
        text_output=bool(output_caps.get("text", True)),
        toolcall=bool(capabilities.get("toolcall")),
        reasoning=bool(capabilities.get("reasoning")),
        attachment=bool(capabilities.get("attachment")),
        context_limit=max(0, int(_as_number(limits.get("context")))),
        output_limit=max(0, int(_as_number(limits.get("output")))),
        input_cost=max(0.0, _as_number(costs.get("input"))),
        output_cost=max(0.0, _as_number(costs.get("output"))),
        variant_count=len(variants),
        release_ordinal=_release_ordinal(payload.get("release_date")),
    )


def parse_opencode_catalog(output: str) -> list[ModelCapability]:
    """Parse ``opencode models --verbose`` alternating IDs and JSON objects."""

    decoder = json.JSONDecoder()
    cursor = 0
    models: list[ModelCapability] = []
    while True:
        start = output.find("{", cursor)
        if start < 0:
            break
        try:
            payload, consumed = decoder.raw_decode(output[start:])
        except json.JSONDecodeError:
            cursor = start + 1
            continue
        prefix = output[cursor:start]
        reported = next((line.strip() for line in reversed(prefix.splitlines()) if "/" in line), "")
        if isinstance(payload, dict):
            model = _capability_from_payload(payload, reported)
            if model is not None:
                models.append(model)
        cursor = start + consumed
    return list({model.model_id: model for model in models}.values())


def discover_opencode_models(binary: str = "opencode", *, timeout: int = 30) -> list[ModelCapability]:
    try:
        result = subprocess.run(
            [binary, "models", "--verbose"],
            capture_output=True,
            text=True,
            timeout=max(1, timeout),
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return parse_opencode_catalog(result.stdout) if result.returncode == 0 else []


def _model_score(model: ModelCapability, profile: ExecutionProfile) -> tuple[float, str]:
    cost = model.input_cost + model.output_cost
    context_headroom = math.log2(max(1, model.context_limit / max(1, profile.min_context)))
    output_headroom = math.log2(max(1, model.output_limit / max(1, profile.min_output)))
    score = (
        (1.0 if model.reasoning else 0.0) * profile.reasoning_depth * 8.0
        + min(4.0, model.variant_count / 2) * profile.reasoning_depth
        + min(4.0, context_headroom) * 0.8
        + min(4.0, output_headroom) * 0.6
        + (5.0 if model.zero_cost else -min(5.0, cost)) * profile.cost_pressure
        + (model.release_ordinal / 1_000_000)
    )
    return score, model.model_id


def select_opencode_model(
    models: Iterable[ModelCapability], profile: ExecutionProfile
) -> ModelCapability | None:
    eligible = [model for model in models if model.satisfies(profile)]
    return max(eligible, key=lambda model: _model_score(model, profile)) if eligible else None


def catalog_hash(models: Iterable[ModelCapability]) -> str:
    rows = [asdict(model) for model in sorted(models, key=lambda item: item.model_id)]
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def parse_warp_catalog(output: str) -> list[str]:
    text = _ANSI.sub("", output).strip()
    if not text:
        return []
    payloads: Sequence[object]
    try:
        decoded = json.loads(text)
        payloads = decoded if isinstance(decoded, list) else [decoded]
    except json.JSONDecodeError:
        payloads = []
        for line in text.splitlines():
            try:
                payloads.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return sorted(
        {
            str(item.get("id") or "").strip()
            for item in payloads
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        }
    )


def validate_warp_override(catalog: Iterable[str], override: str | None) -> str | None:
    available = {str(item).strip() for item in catalog if str(item).strip()}
    return override if override and override in available else None


def discover_warp_override(
    binary: str = "oz", *, override: str | None, timeout: int = 30
) -> str | None:
    if not override:
        return None
    try:
        result = subprocess.run(
            [binary, "model", "list", "--output-format", "json"],
            capture_output=True,
            text=True,
            timeout=max(1, timeout),
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return validate_warp_override(parse_warp_catalog(result.stdout), override)


_PAID_SERVICE_RISK = re.compile(
    r"\b(credential|secret|api[ _-]?key|password|personal[ _-]?data|pii|"
    r"irreversible|delete|wipe|purge|paid[ _-]?overage|public[ _-]?identity|"
    r"claim[ _-]?(?:account|profile))\b",
    re.IGNORECASE,
)


def paid_service_block_reason(task: object) -> str | None:
    """Reject human-gated risk before a prompt reaches Warp/Oz."""

    labels = [str(item) for item in (getattr(task, "labels", None) or [])]
    if any(label.strip().lower() == "needs-human" for label in labels):
        return "task is human-gated"
    public_fields = " ".join(
        [str(getattr(task, "title", "") or ""), str(getattr(task, "type", "") or ""), *labels]
    )
    match = _PAID_SERVICE_RISK.search(public_fields)
    return f"paid-service safety gate matched {match.group(1).lower()}" if match else None
