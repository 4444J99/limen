"""Order-independent selection from the Studium profile catalog."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence, cast

from .contracts import (
    ResearchContractError,
    ResearchRequest,
    mapping,
    nonnegative_number,
    strings,
    verification_score,
)


_PROFILE_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_KIND_MAP = {
    "attended": "manual_handoff",
    "auto": "capability_discovery",
    "automated_adapter": "automated_adapter",
    "capability_discovery": "capability_discovery",
    "manual": "manual_handoff",
    "manual_handoff": "manual_handoff",
}
_FORBIDDEN_MODEL_FIELDS = {
    "default_model",
    "fallback_model",
    "model",
    "model_id",
    "model_name",
    "model_override",
    "selected_model",
}
_PROFILE_FIELDS = {
    "activation",
    "capabilities",
    "execution",
    "execution_kind",
    "execution_timeout_seconds",
    "external_transmission",
    "guardrails",
    "health",
    "id",
    "initial_state",
    "latency_minutes",
    "outcome_type",
    "preservation_tiers",
    "priority",
    "profile_id",
    "provider_ref",
    "provider_surface",
    "state",
    "subscription_policy",
    "variable_cost_usd",
    "verification_strength",
}


def _reject_model_fields(value: object, *, field_name: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_MODEL_FIELDS:
                raise ResearchContractError(f"{field_name} contains forbidden fixed-model field: {key}")
            _reject_model_fields(item, field_name=f"{field_name}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, item in enumerate(value):
            _reject_model_fields(item, field_name=f"{field_name}[{index}]")


@dataclass(frozen=True)
class ResearchProfile:
    profile_id: str
    state: str
    execution_kind: str
    outcome_type: str
    capabilities: frozenset[str]
    preservation_tiers: frozenset[str]
    transmission_classes: frozenset[str]
    verification_level: str
    variable_cost_usd: float | None
    latency_minutes: float | None
    execution_timeout_seconds: int | None
    provider_ref: str | None
    provider_surface: str | None
    health: Mapping[str, Any] = field(default_factory=dict)
    guardrails: Mapping[str, Any] = field(default_factory=dict)
    priority: float = 0.0

    @classmethod
    def from_mapping(cls, profile_id: str, payload: Mapping[str, Any]) -> ResearchProfile:
        if not _PROFILE_ID.fullmatch(profile_id):
            raise ResearchContractError(f"invalid profile identifier: {profile_id}")
        data = mapping(payload, field_name=f"profile {profile_id}")
        extras = sorted(set(data) - _PROFILE_FIELDS)
        if extras:
            raise ResearchContractError(f"profile {profile_id} contains unknown fields: {','.join(extras)}")
        _reject_model_fields(data, field_name=f"profile {profile_id}")

        execution = mapping(data.get("execution") or {}, field_name=f"profile {profile_id}.execution")
        health = mapping(data.get("health") or {}, field_name=f"profile {profile_id}.health")
        guardrails = mapping(data.get("guardrails") or {}, field_name=f"profile {profile_id}.guardrails")
        raw_kind = str(data.get("execution_kind") or execution.get("kind") or "manual_handoff").strip()
        try:
            kind = _KIND_MAP[raw_kind]
        except KeyError as exc:
            raise ResearchContractError(f"unsupported execution_kind for {profile_id}: {raw_kind}") from exc

        outcome_type = str(data.get("outcome_type") or execution.get("outcome") or "").strip()
        if not outcome_type:
            outcome_type = "ManualHandoff" if kind == "manual_handoff" else "BlockedReceipt"
        verification_level = str(data.get("verification_strength") or "").strip()
        verification_score(verification_level)

        raw_cost = data.get("variable_cost_usd", execution.get("variable_cost_usd"))
        if raw_cost is None and "variable_spend_ceiling" in guardrails:
            raw_cost = guardrails.get("variable_spend_ceiling")
        cost = nonnegative_number(raw_cost, field_name=f"{profile_id}.variable_cost_usd")

        timeout_value = data.get("execution_timeout_seconds", execution.get("execution_timeout_seconds"))
        timeout = nonnegative_number(
            timeout_value,
            field_name=f"{profile_id}.execution_timeout_seconds",
        )
        if timeout is not None and (timeout < 1 or not float(timeout).is_integer()):
            raise ResearchContractError(f"{profile_id}.execution_timeout_seconds must be a positive integer")
        latency_value = data.get("latency_minutes", execution.get("latency_minutes"))
        latency = nonnegative_number(latency_value, field_name=f"{profile_id}.latency_minutes")
        if latency is None and timeout is not None:
            latency = timeout / 60
        if timeout is None and latency is not None:
            timeout = math.ceil(latency * 60)

        priority = nonnegative_number(data.get("priority"), field_name=f"{profile_id}.priority", default=0)
        assert priority is not None
        preservation_tiers = frozenset(
            item.lower()
            for item in strings(
                data.get("preservation_tiers"),
                field_name=f"{profile_id}.preservation_tiers",
            )
        )
        transmission = frozenset(
            item.lower()
            for item in strings(
                data.get("external_transmission"),
                field_name=f"{profile_id}.external_transmission",
            )
        )
        if not preservation_tiers or not transmission:
            raise ResearchContractError(
                f"profile {profile_id} must declare preservation_tiers and external_transmission"
            )

        return cls(
            profile_id=profile_id,
            state=str(data.get("state") or data.get("initial_state") or "disabled").strip().lower(),
            execution_kind=kind,
            outcome_type=outcome_type,
            capabilities=frozenset(strings(data.get("capabilities"), field_name=f"{profile_id}.capabilities")),
            preservation_tiers=preservation_tiers,
            transmission_classes=transmission,
            verification_level=verification_level,
            variable_cost_usd=cost,
            latency_minutes=latency,
            execution_timeout_seconds=int(timeout) if timeout is not None else None,
            provider_ref=(str(data.get("provider_ref")).strip() if data.get("provider_ref") else None),
            provider_surface=(str(data.get("provider_surface")).strip() if data.get("provider_surface") else None),
            health=health,
            guardrails=guardrails,
            priority=priority,
        )

    @property
    def verification_strength(self) -> float:
        return verification_score(self.verification_level)


def profiles_from_catalog(catalog: Mapping[str, Any]) -> list[ResearchProfile]:
    data = mapping(catalog, field_name="research profile catalog")
    raw_profiles = data.get("profiles")
    profiles: list[ResearchProfile] = []
    if isinstance(raw_profiles, Mapping):
        for profile_id, payload in raw_profiles.items():
            profiles.append(
                ResearchProfile.from_mapping(str(profile_id), mapping(payload, field_name=f"profile {profile_id}"))
            )
    elif isinstance(raw_profiles, Sequence) and not isinstance(raw_profiles, (str, bytes)):
        for payload in raw_profiles:
            item = mapping(payload, field_name="profile")
            profile_id = str(item.get("id") or item.get("profile_id") or "").strip()
            if not profile_id:
                raise ResearchContractError("list profiles require id")
            profiles.append(ResearchProfile.from_mapping(profile_id, item))
    else:
        raise ResearchContractError("catalog requires profiles as a mapping or list")

    raw_adapters = data.get("adapters") or data.get("providers") or ()
    if isinstance(raw_adapters, Mapping):
        for adapter_id, payload in raw_adapters.items():
            adapter = mapping(payload, field_name=f"adapter {adapter_id}")
            adapter.setdefault("state", "available")
            adapter.setdefault("provider_ref", str(adapter_id))
            profiles.append(ResearchProfile.from_mapping(str(adapter_id), adapter))
    return profiles


def _runtime_observations(runtime_health: Mapping[str, Mapping[str, Any]] | None, profile_id: str) -> dict[str, Any]:
    if not runtime_health:
        return {}
    return mapping(runtime_health.get(profile_id) or {}, field_name=f"runtime health {profile_id}")


def health_reasons(
    profile: ResearchProfile,
    request: ResearchRequest,
    observations: Mapping[str, Any],
) -> list[str]:
    reasons: list[str] = []
    machine = mapping(
        profile.health.get("machine") or {},
        field_name=f"profile {profile.profile_id}.health.machine",
    )
    required_state = machine.get("required_profile_state")
    if required_state and profile.state != str(required_state):
        reasons.append("health:required_profile_state")
    required_format = machine.get("required_export_format")
    if required_format and request.output_format != str(required_format):
        reasons.append("health:required_export_format")
    maximum_cost = machine.get("maximum_variable_cost_usd")
    effective_cost = profile.variable_cost_usd
    projected_cost = observations.get("projected_cost_usd")
    if effective_cost is None and isinstance(projected_cost, (int, float)) and not isinstance(projected_cost, bool):
        effective_cost = float(projected_cost)
    if maximum_cost is not None and (effective_cost is None or effective_cost > float(maximum_cost)):
        reasons.append("health:maximum_variable_cost_usd")
    if machine.get("enforce_execution_timeout") is True and profile.execution_timeout_seconds is None:
        reasons.append("health:execution_timeout_missing")

    if machine.get("live_computer_credit_balance_required") is True:
        credits = observations.get("live_computer_credit_balance")
        if not isinstance(credits, (int, float)) or isinstance(credits, bool) or credits <= 0:
            reasons.append("health:computer_credits_unverified")
    required_refill = machine.get("automatic_refill_state_required")
    if required_refill is not None and observations.get("automatic_refill_state") != required_refill:
        reasons.append("health:automatic_refill_unverified")
    if (
        machine.get("separate_value_case_required") is True
        and observations.get("separate_value_case_confirmed") is not True
    ):
        reasons.append("health:value_case_unverified")

    if profile.execution_kind == "automated_adapter":
        if machine.get("credential_presence_required") is True and observations.get("credential_present") is not True:
            reasons.append("health:credential_missing")
        for requirement, observation in (
            ("api_credit_state_required", "api_credit_state"),
            ("automatic_top_up_state_required", "automatic_top_up_state"),
        ):
            expected = machine.get(requirement)
            if expected is not None and observations.get(observation) != expected:
                reasons.append(f"health:{observation}_unverified")
        for requirement, observation in (
            ("live_catalog_required", "live_catalog_confirmed"),
            ("live_pricing_required", "live_pricing_confirmed"),
        ):
            if machine.get(requirement) is True and observations.get(observation) is not True:
                reasons.append(f"health:{observation}")
        if observations.get("adapter_enabled") is not True:
            reasons.append("health:adapter_disabled")
        projected_cost_valid = (
            isinstance(projected_cost, (int, float)) and not isinstance(projected_cost, bool) and projected_cost >= 0
        )
        if machine.get("projected_cost_required") is True and not projected_cost_valid:
            reasons.append("health:projected_cost_missing")
        elif projected_cost_valid and cast(int | float, projected_cost) > request.spend_ceiling_usd:
            reasons.append("health:projected_cost_exceeds_ceiling")
    return sorted(set(reasons))


def profile_rejection_reasons(
    profile: ResearchProfile,
    request: ResearchRequest,
    observations: Mapping[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if profile.state not in {"available", "enabled"}:
        reasons.append(f"state:{profile.state}")
    missing = sorted(set(request.required_capabilities) - profile.capabilities)
    if missing:
        reasons.append("missing_capabilities:" + ",".join(missing))
    if request.preservation_tier not in profile.preservation_tiers:
        reasons.append(f"preservation:{request.preservation_tier}")
    if request.external_transmission not in profile.transmission_classes:
        reasons.append(f"transmission:{request.external_transmission}")
    if profile.verification_strength < request.verification_strength:
        reasons.append("verification_strength")

    effective_cost = profile.variable_cost_usd
    projected_cost = observations.get("projected_cost_usd")
    if effective_cost is None and isinstance(projected_cost, (int, float)) and not isinstance(projected_cost, bool):
        effective_cost = float(projected_cost)
    if effective_cost is None:
        reasons.append("spend_unknown")
    elif effective_cost > request.spend_ceiling_usd:
        reasons.append("spend_ceiling")
    if profile.latency_minutes is None:
        reasons.append("latency_unknown")
    elif profile.latency_minutes > request.latency_ceiling_minutes:
        reasons.append("latency_ceiling")
    reasons.extend(health_reasons(profile, request, observations))
    return sorted(set(reasons))


def _selector_rejection_reasons(profile: ResearchProfile) -> list[str]:
    reasons = [] if profile.state in {"available", "enabled"} else [f"state:{profile.state}"]
    machine = mapping(
        profile.health.get("machine") or {},
        field_name=f"profile {profile.profile_id}.health.machine",
    )
    required_state = machine.get("required_profile_state")
    if required_state and profile.state != str(required_state):
        reasons.append("health:required_profile_state")
    return sorted(set(reasons))


def _rank(
    profiles: list[ResearchProfile],
    runtime_health: Mapping[str, Mapping[str, Any]] | None,
) -> list[ResearchProfile]:
    def effective_cost(profile: ResearchProfile) -> float:
        if profile.variable_cost_usd is not None:
            return profile.variable_cost_usd
        observed = _runtime_observations(runtime_health, profile.profile_id).get("projected_cost_usd")
        return float(observed) if isinstance(observed, (int, float)) else float("inf")

    return sorted(
        profiles,
        key=lambda item: (
            -item.verification_strength,
            effective_cost(item),
            item.latency_minutes if item.latency_minutes is not None else float("inf"),
            -item.priority,
            item.profile_id,
        ),
    )


def select_profile(
    request: ResearchRequest,
    catalog: Mapping[str, Any],
    *,
    runtime_health: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[ResearchProfile | None, dict[str, list[str]]]:
    """Select by owner-declared capability and live constraints, independent of order."""

    profiles = profiles_from_catalog(catalog)
    selectors = [profile for profile in profiles if profile.execution_kind == "capability_discovery"]
    concrete = [profile for profile in profiles if profile.execution_kind != "capability_discovery"]
    if request.preferred_profile:
        requested = next(
            (profile for profile in profiles if profile.profile_id == request.preferred_profile),
            None,
        )
        if requested is None:
            return None, {request.preferred_profile: ["profile_not_found"]}
        if requested.execution_kind == "capability_discovery":
            selector_reasons = _selector_rejection_reasons(requested)
            if selector_reasons:
                return None, {requested.profile_id: selector_reasons}
            concrete = [profile for profile in concrete if profile.provider_ref]
            if not concrete:
                return None, {requested.profile_id: ["no_reachable_adapters"]}
        else:
            concrete = [requested]

    rejected: dict[str, list[str]] = {}
    eligible: list[ResearchProfile] = []
    for profile in concrete:
        reasons = profile_rejection_reasons(profile, request, _runtime_observations(runtime_health, profile.profile_id))
        if reasons:
            rejected[profile.profile_id] = reasons
        else:
            eligible.append(profile)
    if eligible:
        return _rank(eligible, runtime_health)[0], rejected
    if not request.preferred_profile:
        for selector in selectors:
            rejected[selector.profile_id] = _selector_rejection_reasons(selector) or ["no_reachable_adapters"]
    return None, rejected


def blocker_code(rejected: Mapping[str, Sequence[str]]) -> str:
    reasons = {reason for values in rejected.values() for reason in values}
    if any(reason.startswith("missing_capabilities") for reason in reasons):
        return "missing_capability"
    if any(reason.startswith(("preservation:", "transmission:")) for reason in reasons):
        return "privacy_mismatch"
    if "health:credential_missing" in reasons:
        return "missing_credential"
    if any("credits" in reason for reason in reasons):
        return "insufficient_credits"
    if "spend_ceiling" in reasons or "spend_unknown" in reasons:
        return "spend_ceiling"
    return "provider_unreachable"
