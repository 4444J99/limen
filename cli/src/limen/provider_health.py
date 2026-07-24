"""Append-only provider outcomes and a deterministic runtime health projection.

The ledger contains execution metadata only. Prompts, provider responses, and
credentials are deliberately outside its schema.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping

from limen.vigilia.params import get as parameter


PROVIDER_TERMINALS = frozenset({"auth_failure", "rate_limit"})
MODEL_TERMINALS = frozenset({"stream_failure", "transport_failure", "timeout", "no_output", "failure"})
TRANSIENT_TERMINALS = frozenset({"stream_failure", "transport_failure", "timeout", "no_output"})
SUCCESS_TERMINALS = frozenset({"success", "smoke_success"})
TERMINAL_CLASSES = PROVIDER_TERMINALS | MODEL_TERMINALS | SUCCESS_TERMINALS
_SECRETISH = re.compile(r"(?i)(?:bearer\s+|api[_-]?key|token=|sk-[a-z0-9])")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _parse_time(value: object) -> datetime:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return _utc(datetime.fromisoformat(text))


def _retry_count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("retry_count must be an integer")
    return value


def provider_for_model(model_id: str) -> str:
    provider, separator, _ = model_id.partition("/")
    return provider if separator else model_id


def execution_profile_hash(profile: Mapping[str, object]) -> str:
    payload = json.dumps(dict(profile), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class ProviderHealthPolicy:
    failure_window_seconds: int
    cooldown_seconds: int
    terminal_attempts: int
    same_model_retries: int
    smoke_timeout_seconds: int

    def __post_init__(self) -> None:
        values = (
            self.failure_window_seconds,
            self.cooldown_seconds,
            self.terminal_attempts,
            self.smoke_timeout_seconds,
        )
        if any(isinstance(value, bool) or value < 1 for value in values):
            raise ValueError("provider health durations and terminal_attempts must be positive")
        if isinstance(self.same_model_retries, bool) or not 0 <= self.same_model_retries <= 3:
            raise ValueError("same_model_retries must be between 0 and 3")


def provider_health_policy() -> ProviderHealthPolicy:
    return ProviderHealthPolicy(
        failure_window_seconds=int(parameter("LIMEN_PROVIDER_FAILURE_WINDOW_SECONDS", 86_400, cast=int)),
        cooldown_seconds=int(parameter("LIMEN_PROVIDER_COOLDOWN_SECONDS", 3_600, cast=int)),
        terminal_attempts=int(parameter("LIMEN_PROVIDER_TERMINAL_ATTEMPTS", 2, cast=int)),
        same_model_retries=int(parameter("LIMEN_PROVIDER_SAME_MODEL_RETRIES", 1, cast=int)),
        smoke_timeout_seconds=int(parameter("LIMEN_PROVIDER_SMOKE_TIMEOUT_SECONDS", 120, cast=int)),
    )


def provider_outcome_ledger_path() -> Path:
    root = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen")).expanduser()
    raw = str(parameter("LIMEN_PROVIDER_OUTCOME_LEDGER", str(root / "logs" / "provider-outcomes.jsonl")))
    return Path(raw.replace("$LIMEN_ROOT", str(root))).expanduser()


@dataclass(frozen=True)
class ProviderOutcome:
    provider: str
    runtime_model: str
    catalog_hash: str
    execution_profile_hash: str
    terminal_class: str
    started_at: datetime
    finished_at: datetime
    retry_count: int
    receipt_reference: str

    def __post_init__(self) -> None:
        if self.terminal_class not in TERMINAL_CLASSES:
            raise ValueError(f"unsupported terminal_class: {self.terminal_class}")
        if not self.provider or not self.runtime_model:
            raise ValueError("provider and runtime_model are required")
        if not re.fullmatch(r"[0-9a-f]{64}", self.catalog_hash):
            raise ValueError("catalog_hash must be sha256")
        if not re.fullmatch(r"[0-9a-f]{64}", self.execution_profile_hash):
            raise ValueError("execution_profile_hash must be sha256")
        if isinstance(self.retry_count, bool) or self.retry_count < 0:
            raise ValueError("retry_count must be non-negative")
        if _utc(self.finished_at) < _utc(self.started_at):
            raise ValueError("finished_at precedes started_at")
        if _SECRETISH.search(self.receipt_reference):
            raise ValueError("receipt_reference contains secret-shaped text")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": "limen.provider_outcome.v1",
            "provider": self.provider,
            "runtime_model": self.runtime_model,
            "catalog_hash": self.catalog_hash,
            "execution_profile_hash": self.execution_profile_hash,
            "terminal_class": self.terminal_class,
            "started_at": _iso(self.started_at),
            "finished_at": _iso(self.finished_at),
            "retry_count": self.retry_count,
            "receipt_reference": self.receipt_reference,
        }

    @classmethod
    def from_dict(cls, row: Mapping[str, object]) -> "ProviderOutcome":
        return cls(
            provider=str(row.get("provider") or ""),
            runtime_model=str(row.get("runtime_model") or ""),
            catalog_hash=str(row.get("catalog_hash") or ""),
            execution_profile_hash=str(row.get("execution_profile_hash") or ""),
            terminal_class=str(row.get("terminal_class") or ""),
            started_at=_parse_time(row.get("started_at")),
            finished_at=_parse_time(row.get("finished_at")),
            retry_count=_retry_count(row.get("retry_count", 0)),
            receipt_reference=str(row.get("receipt_reference") or ""),
        )


def append_provider_outcome(path: Path, outcome: ProviderOutcome) -> None:
    """Append one bounded JSON record with owner-only permissions."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(outcome.as_dict(), sort_keys=True, separators=(",", ":")) + "\n").encode()
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def load_provider_outcomes(path: Path, *, max_rows: int = 10_000) -> list[ProviderOutcome]:
    if not path.exists():
        return []
    rows: list[ProviderOutcome] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-max(1, max_rows) :]
    except OSError:
        return []
    for line in lines:
        try:
            decoded = json.loads(line)
            if isinstance(decoded, dict):
                rows.append(ProviderOutcome.from_dict(decoded))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    return rows


@dataclass(frozen=True)
class HealthEntry:
    failure_count: int
    cooldown_until: datetime | None
    requires_smoke: bool
    last_success: datetime | None
    last_terminal_failure: datetime | None

    def blocked(self, now: datetime) -> bool:
        current = _utc(now)
        return bool((self.cooldown_until and current < _utc(self.cooldown_until)) or self.requires_smoke)

    def as_dict(self) -> dict[str, object]:
        return {
            "failure_count": self.failure_count,
            "cooldown_until": _iso(self.cooldown_until) if self.cooldown_until else None,
            "requires_smoke": self.requires_smoke,
            "last_success": _iso(self.last_success) if self.last_success else None,
            "last_terminal_failure": _iso(self.last_terminal_failure) if self.last_terminal_failure else None,
        }


@dataclass(frozen=True)
class ProviderHealthSnapshot:
    providers: Mapping[str, HealthEntry]
    models: Mapping[str, HealthEntry]

    def entry_for(self, model_id: str) -> tuple[HealthEntry | None, HealthEntry | None]:
        return self.providers.get(provider_for_model(model_id)), self.models.get(model_id)

    def allows(self, model_id: str, *, now: datetime) -> bool:
        provider, model = self.entry_for(model_id)
        return not ((provider and provider.blocked(now)) or (model and model.blocked(now)))

    def fitness(self, model_id: str) -> float:
        provider, model = self.entry_for(model_id)
        successes = [entry.last_success.timestamp() for entry in (provider, model) if entry and entry.last_success]
        return max(successes, default=0.0)

    def evidence_for(self, model_id: str) -> dict[str, object]:
        provider, model = self.entry_for(model_id)
        return {
            "provider": provider.as_dict() if provider else None,
            "model": model.as_dict() if model else None,
        }

    def snapshot_hash(self) -> str:
        payload = {
            "providers": {key: value.as_dict() for key, value in sorted(self.providers.items())},
            "models": {key: value.as_dict() for key, value in sorted(self.models.items())},
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _entry(
    events: list[ProviderOutcome],
    *,
    failure_classes: frozenset[str],
    policy: ProviderHealthPolicy,
    now: datetime,
) -> HealthEntry:
    successes = [event for event in events if event.terminal_class in SUCCESS_TERMINALS]
    last_success = max((_utc(event.finished_at) for event in successes), default=None)
    failures = [
        event
        for event in events
        if event.terminal_class in failure_classes and (last_success is None or _utc(event.finished_at) > last_success)
    ]
    last_failure = max((_utc(event.finished_at) for event in failures), default=None)
    tripped = len(failures) >= policy.terminal_attempts
    cooldown_until = last_failure + timedelta(seconds=policy.cooldown_seconds) if tripped and last_failure else None
    smoke_after_cooldown = bool(
        cooldown_until
        and any(
            event.terminal_class == "smoke_success" and _utc(event.finished_at) >= cooldown_until for event in successes
        )
    )
    requires_smoke = bool(tripped and not smoke_after_cooldown and cooldown_until and _utc(now) >= cooldown_until)
    return HealthEntry(
        failure_count=len(failures),
        cooldown_until=cooldown_until,
        requires_smoke=requires_smoke,
        last_success=last_success,
        last_terminal_failure=last_failure,
    )


def project_provider_health(
    outcomes: Iterable[ProviderOutcome],
    policy: ProviderHealthPolicy,
    *,
    now: datetime | None = None,
) -> ProviderHealthSnapshot:
    current = _utc(now or datetime.now(timezone.utc))
    window_start = current - timedelta(seconds=policy.failure_window_seconds)
    recent = [outcome for outcome in outcomes if _utc(outcome.finished_at) >= window_start]
    providers: dict[str, list[ProviderOutcome]] = {}
    models: dict[str, list[ProviderOutcome]] = {}
    for outcome in recent:
        providers.setdefault(outcome.provider, []).append(outcome)
        models.setdefault(outcome.runtime_model, []).append(outcome)
    return ProviderHealthSnapshot(
        providers={
            key: _entry(events, failure_classes=PROVIDER_TERMINALS, policy=policy, now=current)
            for key, events in providers.items()
        },
        models={
            key: _entry(events, failure_classes=MODEL_TERMINALS, policy=policy, now=current)
            for key, events in models.items()
        },
    )


def classify_provider_terminal(
    *,
    returncode: int | None = None,
    output: str = "",
    timed_out: bool = False,
    no_output: bool = False,
) -> str:
    if timed_out:
        return "timeout"
    if no_output:
        return "no_output"
    text = output.lower()
    if any(token in text for token in ("unauthorized", "authentication", "oauth", "invalid api key", "401")):
        return "auth_failure"
    if any(token in text for token in ("rate limit", "rate-limit", "too many requests", "429")):
        return "rate_limit"
    if any(token in text for token in ("stream", "sse", "unexpected eof")):
        return "stream_failure"
    if any(token in text for token in ("connection reset", "network", "transport", "dns", "socket")):
        return "transport_failure"
    return "success" if returncode == 0 else "failure"
