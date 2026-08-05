"""Bounded, tool-using OpenCode health smoke with append-only outcome receipts."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import tempfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from limen.host_admission import AdmissionDenied, hold_lease
from limen.provider_health import (
    ProviderHealthSnapshot,
    ProviderOutcome,
    append_provider_outcome,
    classify_provider_terminal,
    execution_profile_hash,
    load_provider_outcomes,
    project_provider_health,
    provider_for_model,
    provider_health_policy,
    provider_outcome_ledger_path,
)
from limen.provider_selection import (
    ExecutionProfile,
    ModelCapability,
    catalog_hash,
    discover_opencode_models,
    execution_profile_for,
    select_opencode_model,
)

_SMOKE_PERMISSION = json.dumps(
    {
        "*": "deny",
        "read": {"*": "allow"},
        "glob": "allow",
        "grep": "allow",
        "list": "allow",
    },
    sort_keys=True,
    separators=(",", ":"),
)


@dataclass(frozen=True)
class OpenCodeSmokeResult:
    status: str
    runtime_model: str | None
    terminal_class: str | None
    tool_read_observed: bool
    marker_observed: bool
    catalog_hash: str
    health_snapshot_hash: str
    receipt_reference: str | None
    reason: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status == "succeeded"

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _provider_allows_smoke(health: ProviderHealthSnapshot, model_id: str, now: datetime) -> bool:
    provider, _model = health.entry_for(model_id)
    return not bool(provider and provider.blocked(now))


def select_opencode_smoke_candidate(
    models: Iterable[ModelCapability],
    profile: ExecutionProfile,
    health: ProviderHealthSnapshot,
    *,
    now: datetime,
    allow_healthy: bool = True,
) -> ModelCapability | None:
    """Prefer a post-cooldown model awaiting proof, then a normal healthy model."""

    eligible = [model for model in models if model.satisfies(profile)]
    awaiting = []
    for model in eligible:
        _provider, entry = health.entry_for(model.model_id)
        if not entry or not entry.requires_smoke or not _provider_allows_smoke(health, model.model_id, now):
            continue
        if entry.cooldown_until and now < _utc(entry.cooldown_until):
            continue
        awaiting.append((entry.last_terminal_failure or datetime.min.replace(tzinfo=UTC), model))
    if awaiting:
        return max(awaiting, key=lambda item: (item[0], item[1].model_id))[1]
    if not allow_healthy:
        return None
    return select_opencode_model(eligible, profile, health, now=now)


def _walk(value: object) -> Iterable[object]:
    yield value
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield key
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _tool_evidence(output: str, marker: str) -> tuple[bool, bool]:
    tool_read_observed = False
    marker_observed = False
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        values = [str(value) for value in _walk(event) if isinstance(value, (str, int, float))]
        lowered = [value.lower() for value in values]
        event_text = "\n".join(values)
        marker_observed = marker_observed or marker in event_text
        names_read = any(value in {"read", "file_read", "read_file"} or value.endswith(".read") for value in lowered)
        names_smoke_file = any("smoke.txt" in value for value in lowered)
        tool_read_observed = tool_read_observed or (names_read and names_smoke_file)
    return tool_read_observed, marker_observed


def _receipt_reference(payload: Mapping[str, object]) -> str:
    digest = hashlib.sha256(json.dumps(dict(payload), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return f"opencode-smoke:{digest}"


def _smoke_environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    environment = dict(source or os.environ)
    environment.update(
        {
            "OPENCODE_PERMISSION": _SMOKE_PERMISSION,
            "OPENCODE_PURE": "1",
            "OPENCODE_DISABLE_EXTERNAL_SKILLS": "1",
            "OPENCODE_DISABLE_SHARE": "1",
            "OPENCODE_DISABLE_PROJECT_CONFIG": "1",
        }
    )
    return environment


def run_opencode_smoke(
    *,
    binary: str | None = None,
    ledger_path: Path | None = None,
    models: list[ModelCapability] | None = None,
    profile: ExecutionProfile | None = None,
    allow_healthy: bool = True,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    clock: Callable[[], datetime] | None = None,
) -> OpenCodeSmokeResult:
    """Run one read-only smoke under the machine-wide heavy admission lease."""

    clock = clock or (lambda: datetime.now(UTC))
    now = _utc(clock())
    policy = provider_health_policy()
    ledger = ledger_path or provider_outcome_ledger_path()
    outcomes = load_provider_outcomes(ledger)
    health = project_provider_health(outcomes, policy, now=now)
    requested = profile or execution_profile_for(None)
    executable = binary or os.environ.get("LIMEN_OPENCODE_BIN", "opencode")
    catalog = models if models is not None else discover_opencode_models(executable)
    fingerprint = catalog_hash(catalog)
    candidate = select_opencode_smoke_candidate(
        catalog,
        requested,
        health,
        now=now,
        allow_healthy=allow_healthy,
    )
    if candidate is None:
        return OpenCodeSmokeResult(
            status="blocked",
            runtime_model=None,
            terminal_class=None,
            tool_read_observed=False,
            marker_observed=False,
            catalog_hash=fingerprint,
            health_snapshot_hash=health.snapshot_hash(),
            receipt_reference=None,
            reason="no eligible model is awaiting smoke or healthy",
        )

    marker = f"SMOKE_PROOF_{secrets.token_hex(16)}"
    prompt = "Use the file-reading tool to read SMOKE.txt. Return only the exact token stored in that file."
    started_at = _utc(clock())
    returncode: int | None = None
    output = ""
    timed_out = False
    try:
        with tempfile.TemporaryDirectory(prefix="limen-opencode-smoke-") as raw_directory:
            directory = Path(raw_directory)
            (directory / "SMOKE.txt").write_text(marker + "\n", encoding="utf-8")
            argv = [
                executable,
                "run",
                "--pure",
                "--format",
                "json",
                "--model",
                candidate.model_id,
                "--dir",
                str(directory),
                prompt,
            ]
            with hold_lease(
                "heavy",
                owner=f"opencode-smoke-{os.getpid()}",
                surface="limen-opencode-health-smoke",
                pid=os.getpid(),
            ):
                completed = runner(
                    argv,
                    cwd=str(directory),
                    env=_smoke_environment(),
                    capture_output=True,
                    text=True,
                    timeout=policy.smoke_timeout_seconds,
                    check=False,
                )
            returncode = completed.returncode
            output = (completed.stdout or "") + "\n" + (completed.stderr or "")
    except subprocess.TimeoutExpired:
        timed_out = True
    except AdmissionDenied as exc:
        return OpenCodeSmokeResult(
            status="blocked",
            runtime_model=candidate.model_id,
            terminal_class=None,
            tool_read_observed=False,
            marker_observed=False,
            catalog_hash=fingerprint,
            health_snapshot_hash=health.snapshot_hash(),
            receipt_reference=None,
            reason="host admission denied: " + ",".join(exc.decision.get("reasons") or []),
        )

    tool_read_observed, marker_observed = _tool_evidence(output, marker)
    if returncode == 0 and tool_read_observed and marker_observed:
        terminal_class = "smoke_success"
        status = "succeeded"
    else:
        terminal_class = classify_provider_terminal(
            returncode=returncode,
            output=output,
            timed_out=timed_out,
            no_output=not marker_observed,
        )
        status = "failed"
    finished_at = _utc(clock())
    receipt_payload = {
        "catalog_hash": fingerprint,
        "execution_profile_hash": execution_profile_hash(requested.as_dict()),
        "marker_observed": marker_observed,
        "returncode": returncode,
        "runtime_model": candidate.model_id,
        "terminal_class": terminal_class,
        "tool_read_observed": tool_read_observed,
    }
    reference = _receipt_reference(receipt_payload)
    append_provider_outcome(
        ledger,
        ProviderOutcome(
            provider=provider_for_model(candidate.model_id),
            runtime_model=candidate.model_id,
            catalog_hash=fingerprint,
            execution_profile_hash=execution_profile_hash(requested.as_dict()),
            terminal_class=terminal_class,
            started_at=started_at,
            finished_at=finished_at,
            retry_count=0,
            receipt_reference=reference,
        ),
    )
    updated = project_provider_health(load_provider_outcomes(ledger), policy, now=finished_at)
    return OpenCodeSmokeResult(
        status=status,
        runtime_model=candidate.model_id,
        terminal_class=terminal_class,
        tool_read_observed=tool_read_observed,
        marker_observed=marker_observed,
        catalog_hash=fingerprint,
        health_snapshot_hash=updated.snapshot_hash(),
        receipt_reference=reference,
        reason=None if status == "succeeded" else "tool-using smoke predicate failed",
    )
