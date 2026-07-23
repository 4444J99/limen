"""Append-only accounting for capacity requested, reserved, consumed, and repaid."""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from limen.work_loan import task_work_loan_readiness

JOURNAL_SCHEMA: Literal["limen.work_loan_journal_event.v1"] = "limen.work_loan_journal_event.v1"
SNAPSHOT_SCHEMA = "limen.work_loan_journal.v1"
REPORT_SCHEMA = "limen.progress-source-report.v1"
SOURCE_ID = "work-loan"
PHASES = frozenset({"requested", "reserved", "actual", "settled"})
TERMINAL_TASK_STATES = frozenset({"done", "failed", "failed_blocked", "archived"})
SAFE_CORRELATION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,511}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
USAGE_FIELDS = (
    "runs",
    "input_tokens",
    "output_tokens",
    "cache_tokens",
    "dollars_usd",
    "elapsed_seconds",
    "host_local_seconds",
    "host_cpu_seconds",
    "host_memory_gib_seconds",
    "host_disk_gib_seconds",
)


class WorkLoanJournalError(RuntimeError):
    """Journal custody, validation, or phase ordering failed."""


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _value(subject: Mapping[str, Any] | object, field: str, default: Any = None) -> Any:
    if isinstance(subject, Mapping):
        return subject.get(field, default)
    return getattr(subject, field, default)


def _dump(subject: Any) -> dict[str, Any]:
    if isinstance(subject, BaseModel):
        return subject.model_dump(mode="json", exclude_none=False)
    if isinstance(subject, Mapping):
        return dict(subject)
    raise WorkLoanJournalError("journal subject must be a model or mapping")


def _timestamp(value: datetime | None = None) -> datetime:
    observed = value or datetime.now(UTC)
    if observed.tzinfo is None:
        raise WorkLoanJournalError("journal timestamps require a timezone")
    return observed.astimezone(UTC)


class CapacityUseV1(BaseModel):
    """Provider-neutral usage. ``None`` means unknown; zero means measured zero."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    runs: int | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cache_tokens: int | None = Field(default=None, ge=0)
    dollars_usd: float | None = Field(default=None, ge=0)
    elapsed_seconds: float | None = Field(default=None, ge=0)
    host_local_seconds: float | None = Field(default=None, ge=0)
    host_cpu_seconds: float | None = Field(default=None, ge=0)
    host_memory_gib_seconds: float | None = Field(default=None, ge=0)
    host_disk_gib_seconds: float | None = Field(default=None, ge=0)

    @field_validator(
        "dollars_usd",
        "elapsed_seconds",
        "host_local_seconds",
        "host_cpu_seconds",
        "host_memory_gib_seconds",
        "host_disk_gib_seconds",
    )
    @classmethod
    def finite_measurements(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("capacity measurements must be finite")
        return value

    @property
    def has_measurement(self) -> bool:
        return any(getattr(self, field) is not None for field in USAGE_FIELDS)


class WorkLoanJournalEventV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["limen.work_loan_journal_event.v1"] = JOURNAL_SCHEMA
    event_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    loan_id: str = Field(pattern=r"^loan-[0-9a-f]{32}$")
    subject_id: str = Field(min_length=1, max_length=512)
    phase: Literal["requested", "reserved", "actual", "settled"]
    correlation_id: str = Field(min_length=1, max_length=512)
    sequence: int = Field(ge=0)
    previous_event_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    recorded_at: datetime
    usage: CapacityUseV1 | None = None
    source_origin: str | None = None
    horizon: str | None = None
    value_case: str | None = None
    owner_surface: str | None = None
    predicate: str | None = None
    receipt_target: str | None = None
    reservation_id: str | None = None
    agent: str | None = None
    outcome: str | None = None
    receipt_verified: bool | None = None
    predicate_passed: bool | None = None
    earned_credit: bool | None = None
    unrepaid_debt: bool | None = None
    verification_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("correlation_id", "reservation_id", "agent")
    @classmethod
    def safe_correlations(cls, value: str | None, info) -> str | None:
        if value is not None and not SAFE_CORRELATION.fullmatch(value):
            raise ValueError(f"{info.field_name} contains unsupported characters")
        return value

    @field_validator("recorded_at")
    @classmethod
    def timestamp_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("recorded_at requires a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def phase_contract(self) -> WorkLoanJournalEventV1:
        if self.phase == "requested":
            required = (
                self.source_origin,
                self.horizon,
                self.value_case,
                self.owner_surface,
                self.predicate,
                self.receipt_target,
            )
            if not all(str(value or "").strip() for value in required) or self.usage is None:
                raise ValueError("requested event requires forecast, collateral, and requested usage")
        elif self.phase == "reserved":
            if self.reservation_id is None or self.agent is None or self.usage is None:
                raise ValueError("reserved event requires reservation, agent, and reserved usage")
        elif self.phase == "actual":
            if (
                self.reservation_id is None
                or self.agent is None
                or self.usage is None
                or not self.usage.has_measurement
            ):
                raise ValueError("actual event requires reservation, agent, and measured usage")
        elif not (
            self.outcome
            and self.receipt_verified is not None
            and self.predicate_passed is not None
            and self.earned_credit is not None
            and self.unrepaid_debt is not None
        ):
            raise ValueError("settled event requires outcome, verification, credit, and debt state")
        if self.earned_credit is True and not (
            self.outcome == "done" and self.receipt_verified is True and self.predicate_passed is True
        ):
            raise ValueError("earned credit requires done plus predicate and durable-receipt verification")
        if self.earned_credit is not None and self.unrepaid_debt is self.earned_credit:
            raise ValueError("earned credit and unrepaid debt must be complements")
        return self

    @model_validator(mode="after")
    def event_id_matches_content(self) -> WorkLoanJournalEventV1:
        material = self.model_dump(mode="json", exclude={"event_id"}, exclude_none=False)
        if self.event_id != canonical_sha256(material):
            raise ValueError("event_id does not match canonical event content")
        return self


def _event(
    *,
    loan_id: str,
    subject_id: str,
    phase: Literal["requested", "reserved", "actual", "settled"],
    correlation_id: str,
    sequence: int,
    previous_event_id: str | None,
    recorded_at: datetime,
    **fields: Any,
) -> WorkLoanJournalEventV1:
    material = {
        "schema_version": JOURNAL_SCHEMA,
        "loan_id": loan_id,
        "subject_id": subject_id,
        "phase": phase,
        "correlation_id": correlation_id,
        "sequence": sequence,
        "previous_event_id": previous_event_id,
        "recorded_at": _timestamp(recorded_at),
        **fields,
    }
    # Construct only to apply model defaults before hashing. Ordinary validation
    # cannot run yet because the canonical identifier is the value being derived.
    draft = WorkLoanJournalEventV1.model_construct(event_id="0" * 64, **material)
    payload = draft.model_dump(mode="json", exclude={"event_id"}, exclude_none=False)
    return WorkLoanJournalEventV1.model_validate({**payload, "event_id": canonical_sha256(payload)})


def _semantic_event(event: WorkLoanJournalEventV1) -> dict[str, Any]:
    return event.model_dump(
        mode="json",
        exclude={"event_id", "sequence", "previous_event_id", "recorded_at"},
        exclude_none=False,
    )


def append_event(
    events: list[WorkLoanJournalEventV1],
    *,
    loan_id: str,
    subject_id: str,
    phase: Literal["requested", "reserved", "actual", "settled"],
    correlation_id: str,
    recorded_at: datetime,
    **fields: Any,
) -> tuple[WorkLoanJournalEventV1, bool]:
    """Append one phase with per-loan chaining and correlation idempotency."""

    loan_events = [event for event in events if event.loan_id == loan_id]
    matches = [event for event in loan_events if event.phase == phase and event.correlation_id == correlation_id]
    if matches:
        candidate = _event(
            loan_id=loan_id,
            subject_id=subject_id,
            phase=phase,
            correlation_id=correlation_id,
            sequence=matches[0].sequence,
            previous_event_id=matches[0].previous_event_id,
            recorded_at=matches[0].recorded_at,
            **fields,
        )
        if _semantic_event(candidate) != _semantic_event(matches[0]):
            raise WorkLoanJournalError("journal correlation was reused with different accounting")
        return matches[0], False
    if loan_events and loan_events[-1].phase == "settled":
        raise WorkLoanJournalError("settled work loan is immutable")
    if phase == "requested" and loan_events:
        raise WorkLoanJournalError("requested event must be the first loan event")
    if phase != "requested" and not loan_events:
        raise WorkLoanJournalError(f"{phase} event requires an existing request")
    if phase == "actual" and not any(
        event.phase == "reserved" and event.reservation_id == fields.get("reservation_id") for event in loan_events
    ):
        raise WorkLoanJournalError("actual usage has no matching reservation")
    sequence = len(loan_events)
    previous = loan_events[-1].event_id if loan_events else None
    created = _event(
        loan_id=loan_id,
        subject_id=subject_id,
        phase=phase,
        correlation_id=correlation_id,
        sequence=sequence,
        previous_event_id=previous,
        recorded_at=recorded_at,
        **fields,
    )
    events.append(created)
    return created, True


def validate_events(events: Sequence[WorkLoanJournalEventV1]) -> list[str]:
    failures: list[str] = []
    by_loan: dict[str, list[WorkLoanJournalEventV1]] = defaultdict(list)
    event_ids: set[str] = set()
    for event in events:
        if event.event_id in event_ids:
            failures.append(f"{event.event_id}:duplicate-event-id")
        event_ids.add(event.event_id)
        by_loan[event.loan_id].append(event)
    for loan_id, rows in by_loan.items():
        for expected, event in enumerate(rows):
            if event.sequence != expected:
                failures.append(f"{loan_id}:sequence-gap")
            previous = rows[expected - 1].event_id if expected else None
            if event.previous_event_id != previous:
                failures.append(f"{loan_id}:hash-chain-broken")
            if expected == 0 and event.phase != "requested":
                failures.append(f"{loan_id}:first-phase-not-requested")
            if expected < len(rows) - 1 and event.phase == "settled":
                failures.append(f"{loan_id}:post-settlement-event")
    return sorted(set(failures))


def loan_id_for_task(task: Mapping[str, Any] | object) -> str:
    readiness = task_work_loan_readiness(task)
    if not readiness.ready or readiness.loan is None:
        raise WorkLoanJournalError(readiness.reason_code or "task-not-underwritten")
    material = {
        "task_id": str(_value(task, "id") or ""),
        "predicate": str(_value(task, "predicate") or ""),
        "receipt_target": str(_value(task, "receipt_target") or ""),
        "work_loan": readiness.loan.model_dump(mode="json"),
    }
    return f"loan-{canonical_sha256(material)[:32]}"


def _capacity_from_mapping(
    metrics: Mapping[str, Any] | None,
    *,
    default_runs: int | None = None,
    elapsed_seconds: float | None = None,
    local_host: bool = False,
) -> CapacityUseV1:
    source = dict(metrics or {})

    def first(*keys: str) -> Any:
        return next((source[key] for key in keys if key in source), None)

    return CapacityUseV1(
        runs=first("runs", "run_count") if first("runs", "run_count") is not None else default_runs,
        input_tokens=first("input_tokens", "prompt_tokens"),
        output_tokens=first("output_tokens", "completion_tokens"),
        cache_tokens=first("cache_tokens", "cached_tokens"),
        dollars_usd=first("dollars_usd", "cost_usd", "dollars"),
        elapsed_seconds=(
            first("elapsed_seconds", "duration_seconds")
            if first("elapsed_seconds", "duration_seconds") is not None
            else elapsed_seconds
        ),
        host_local_seconds=(
            first("host_local_seconds")
            if first("host_local_seconds") is not None
            else (elapsed_seconds if local_host else None)
        ),
        host_cpu_seconds=first("host_cpu_seconds", "cpu_seconds"),
        host_memory_gib_seconds=first("host_memory_gib_seconds", "memory_gib_seconds"),
        host_disk_gib_seconds=first("host_disk_gib_seconds", "disk_gib_seconds"),
    )


def _sum_usage(rows: Iterable[CapacityUseV1]) -> CapacityUseV1:
    material = list(rows)
    values: dict[str, int | float | None] = {}
    integer_fields = {"runs", "input_tokens", "output_tokens", "cache_tokens"}
    for field in USAGE_FIELDS:
        known = [getattr(row, field) for row in material if getattr(row, field) is not None]
        if not known:
            values[field] = None
        else:
            total = sum(known)
            values[field] = int(total) if field in integer_fields else float(total)
    return CapacityUseV1.model_validate(values)


def journal_snapshots(events: Sequence[WorkLoanJournalEventV1]) -> list[dict[str, Any]]:
    failures = validate_events(events)
    if failures:
        raise WorkLoanJournalError("invalid journal: " + "; ".join(failures))
    by_loan: dict[str, list[WorkLoanJournalEventV1]] = defaultdict(list)
    for event in events:
        by_loan[event.loan_id].append(event)
    snapshots: list[dict[str, Any]] = []
    for loan_id, rows in sorted(by_loan.items()):
        requested = rows[0]
        settled = next((event for event in reversed(rows) if event.phase == "settled"), None)
        reserved = _sum_usage(event.usage for event in rows if event.phase == "reserved" and event.usage)
        actual = _sum_usage(event.usage for event in rows if event.phase == "actual" and event.usage)
        earned = settled.earned_credit is True if settled else False
        requested_runs = requested.usage.runs if requested.usage else None
        snapshot = {
            "loan_id": loan_id,
            "subject_id": requested.subject_id,
            "forecast": {
                "source_origin": requested.source_origin,
                "horizon": requested.horizon,
                "value_case": requested.value_case,
                "owner_surface": requested.owner_surface,
            },
            "collateral": {
                "predicate": requested.predicate,
                "receipt_target": requested.receipt_target,
            },
            "requested": requested.usage.model_dump(mode="json") if requested.usage else None,
            "reserved": reserved.model_dump(mode="json"),
            "actual": actual.model_dump(mode="json"),
            "reservation_count": sum(event.phase == "reserved" for event in rows),
            "actual_event_count": sum(event.phase == "actual" for event in rows),
            "outcome": settled.outcome if settled else None,
            "predicate_passed": settled.predicate_passed if settled else None,
            "receipt_verified": settled.receipt_verified if settled else None,
            "verification_digest": settled.verification_digest if settled else None,
            "earned_credit": earned,
            "unrepaid_debt": not earned,
            "unrepaid_requested_runs": 0 if earned else requested_runs,
            "settled": settled is not None,
            "event_count": len(rows),
            "last_event_id": rows[-1].event_id,
        }
        snapshot["content_sha256"] = canonical_sha256(snapshot)
        snapshots.append(snapshot)
    return snapshots


def _tracked_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "loan_key": hashlib.sha256(str(row["loan_id"]).encode()).hexdigest(),
        "forecast": {
            "source_origin": row["forecast"]["source_origin"],
            "horizon": row["forecast"]["horizon"],
        },
        "requested": row["requested"],
        "reserved": row["reserved"],
        "actual": row["actual"],
        "outcome": row["outcome"],
        "receipt_verified": row["receipt_verified"],
        "earned_credit": row["earned_credit"],
        "unrepaid_debt": row["unrepaid_debt"],
        "settled": row["settled"],
    }


def build_work_loan_source(
    events: Sequence[WorkLoanJournalEventV1],
    *,
    generated_at: datetime | None = None,
    public_limit: int = 256,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if public_limit < 0:
        raise ValueError("public_limit must be non-negative")
    failures = validate_events(events)
    snapshots: list[dict[str, Any]] = []
    if not failures:
        try:
            snapshots = journal_snapshots(events)
        except WorkLoanJournalError as exc:
            failures.append(str(exc))
    observed = _timestamp(generated_at)
    source_report = {
        "schema": REPORT_SCHEMA,
        "source_id": SOURCE_ID,
        "cursor": {
            "scope": "post-adoption-v1",
            "event_count": len(events),
            "loan_count": len(snapshots),
            "last_event_id": events[-1].event_id if events else None,
            "failure_count": len(failures),
        },
        "exhaustive": not failures,
        "generated_at": observed.isoformat().replace("+00:00", "Z"),
        "content_sha256": canonical_sha256(snapshots),
        "semantic_status": "ready" if not failures else "failed",
        "normalized_leaf_count": len(snapshots),
    }
    summary = {
        "event_count": len(events),
        "loan_count": len(snapshots),
        "settled_count": sum(bool(row["settled"]) for row in snapshots),
        "earned_credit_count": sum(bool(row["earned_credit"]) for row in snapshots),
        "unrepaid_debt_count": sum(bool(row["unrepaid_debt"]) for row in snapshots),
        "actual_runs": sum(int((row["actual"] or {}).get("runs") or 0) for row in snapshots),
        "actual_tokens": sum(
            int((row["actual"] or {}).get(field) or 0)
            for row in snapshots
            for field in ("input_tokens", "output_tokens", "cache_tokens")
        ),
        "actual_dollars_usd": round(
            sum(float((row["actual"] or {}).get("dollars_usd") or 0.0) for row in snapshots), 8
        ),
        "actual_elapsed_seconds": round(
            sum(float((row["actual"] or {}).get("elapsed_seconds") or 0.0) for row in snapshots), 6
        ),
        "actual_host_local_seconds": round(
            sum(float((row["actual"] or {}).get("host_local_seconds") or 0.0) for row in snapshots), 6
        ),
        "failure_count": len(failures),
    }
    full = {
        "schema": SNAPSHOT_SCHEMA,
        "source_report": source_report,
        "summary": summary,
        "failures": failures,
        "loans": snapshots,
    }
    selected = snapshots[:public_limit]
    tracked = {
        "schema": SNAPSHOT_SCHEMA,
        "source_report": source_report,
        "summary": summary,
        "failure_codes": [f"failure-{hashlib.sha256(reason.encode()).hexdigest()}" for reason in failures],
        "loans": [_tracked_snapshot(row) for row in selected],
        "tracked_loan_limit": public_limit,
        "tracked_loan_count": len(selected),
        "tracked_loan_truncated_count": max(0, len(snapshots) - len(selected)),
    }
    return full, tracked


class WorkLoanJournalStore:
    """Cross-process append store. It records accounting only and never selects work."""

    def __init__(self, path: Path):
        self.path = path
        self.lock_path = path.with_suffix(path.suffix + ".lock")

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            with os.fdopen(descriptor, "a+", encoding="utf-8") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                yield
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            pass

    def read(self) -> list[WorkLoanJournalEventV1]:
        with self._locked():
            return self._read_unlocked()

    def _read_unlocked(self) -> list[WorkLoanJournalEventV1]:
        try:
            lines = self.path.read_text(encoding="utf-8", errors="strict").splitlines()
        except FileNotFoundError:
            return []
        except (OSError, UnicodeError) as exc:
            raise WorkLoanJournalError("work-loan journal is unreadable") from exc
        events: list[WorkLoanJournalEventV1] = []
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                raise WorkLoanJournalError(f"work-loan journal line {number} is blank")
            try:
                events.append(WorkLoanJournalEventV1.model_validate_json(line))
            except ValueError as exc:
                raise WorkLoanJournalError(f"work-loan journal line {number} is invalid") from exc
        failures = validate_events(events)
        if failures:
            raise WorkLoanJournalError("invalid journal: " + "; ".join(failures))
        return events

    def _write_new(self, events: Sequence[WorkLoanJournalEventV1], start: int) -> None:
        if start >= len(events):
            return
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                for event in events[start:]:
                    handle.write(event.model_dump_json(exclude_none=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(self.path, 0o600)
        except OSError as exc:
            raise WorkLoanJournalError("work-loan journal append failed") from exc

    def mutate(self, operation: Callable[[list[WorkLoanJournalEventV1]], Any]) -> Any:
        with self._locked():
            events = self._read_unlocked()
            start = len(events)
            result = operation(events)
            failures = validate_events(events)
            if failures:
                raise WorkLoanJournalError("invalid journal mutation: " + "; ".join(failures))
            self._write_new(events, start)
            return result

    def record_reservation(
        self,
        task: Mapping[str, Any] | object,
        *,
        agent: str,
        reservation_id: str,
        now: datetime | None = None,
    ) -> str:
        readiness = task_work_loan_readiness(task)
        if not readiness.ready or readiness.loan is None:
            raise WorkLoanJournalError(readiness.reason_code or "task-not-underwritten")
        loan = readiness.loan
        loan_id = loan_id_for_task(task)
        subject_id = str(_value(task, "id") or "")
        if not SAFE_CORRELATION.fullmatch(reservation_id) or not SAFE_CORRELATION.fullmatch(agent):
            raise WorkLoanJournalError("reservation correlation is not portable")
        observed = _timestamp(now)

        def operation(events: list[WorkLoanJournalEventV1]) -> None:
            append_event(
                events,
                loan_id=loan_id,
                subject_id=subject_id,
                phase="requested",
                correlation_id=loan_id,
                recorded_at=observed,
                usage=CapacityUseV1(runs=loan.budget_cost),
                source_origin=loan.source_origin,
                horizon=loan.horizon,
                value_case=loan.value_case,
                owner_surface=loan.owner_surface,
                predicate=str(_value(task, "predicate") or ""),
                receipt_target=str(_value(task, "receipt_target") or ""),
            )
            append_event(
                events,
                loan_id=loan_id,
                subject_id=subject_id,
                phase="reserved",
                correlation_id=reservation_id,
                recorded_at=observed,
                usage=CapacityUseV1(runs=loan.budget_cost),
                reservation_id=reservation_id,
                agent=agent,
            )

        self.mutate(operation)
        return loan_id

    def record_actual(
        self,
        task: Mapping[str, Any] | object,
        *,
        agent: str,
        reservation_id: str,
        elapsed_seconds: float,
        local_host: bool,
        metrics: Mapping[str, Any] | None = None,
        now: datetime | None = None,
    ) -> str:
        loan_id = loan_id_for_task(task)
        subject_id = str(_value(task, "id") or "")
        usage = _capacity_from_mapping(
            metrics,
            default_runs=1,
            elapsed_seconds=elapsed_seconds,
            local_host=local_host,
        )

        def operation(events: list[WorkLoanJournalEventV1]) -> None:
            append_event(
                events,
                loan_id=loan_id,
                subject_id=subject_id,
                phase="actual",
                correlation_id=reservation_id,
                recorded_at=_timestamp(now),
                usage=usage,
                reservation_id=reservation_id,
                agent=agent,
            )

        self.mutate(operation)
        return loan_id

    def record_settlement(
        self,
        task: Mapping[str, Any] | object,
        *,
        outcome: str,
        receipt_verified: bool,
        predicate_passed: bool,
        verification_digest: str | None,
        correlation_id: str,
        now: datetime | None = None,
    ) -> str:
        loan_id = loan_id_for_task(task)
        earned = outcome == "done" and receipt_verified and predicate_passed

        def operation(events: list[WorkLoanJournalEventV1]) -> None:
            append_event(
                events,
                loan_id=loan_id,
                subject_id=str(_value(task, "id") or ""),
                phase="settled",
                correlation_id=correlation_id,
                recorded_at=_timestamp(now),
                outcome=outcome,
                receipt_verified=receipt_verified,
                predicate_passed=predicate_passed,
                earned_credit=earned,
                unrepaid_debt=not earned,
                verification_digest=(
                    verification_digest if verification_digest and SHA256_RE.fullmatch(verification_digest) else None
                ),
            )

        self.mutate(operation)
        return loan_id


def default_store(root: Path | None = None) -> WorkLoanJournalStore:
    owner = root or Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
    return WorkLoanJournalStore(owner / "logs" / "work-loan-journal.jsonl")


def work_loan_selection_key(task: Mapping[str, Any] | object) -> tuple[int, str, int]:
    """Deadline/cost tie-breaker after the existing focus and priority buckets."""

    readiness = task_work_loan_readiness(task)
    if not readiness.ready or readiness.loan is None:
        return (2, "9999-12-31T23:59:59Z", 2**31 - 1)
    loan = readiness.loan
    due = loan.due_at
    if isinstance(due, datetime):
        due_key = due.astimezone(UTC).isoformat()
    elif isinstance(due, date):
        due_key = due.isoformat()
    else:
        due_key = "9999-12-31T23:59:59Z"
    return (0 if loan.external_deadline else 1, due_key, loan.budget_cost)


def terminal_credit(task: Mapping[str, Any] | object) -> tuple[bool, bool, str | None]:
    status = str(_value(task, "status") or "")
    logs = list(_value(task, "dispatch_log", []) or [])
    latest = _dump(logs[-1]) if logs else {}
    predicate_passed = latest.get("predicate_exit_code") == 0
    receipt_target = str(_value(task, "receipt_target") or "")
    receipt_verified = bool(
        _value(task, "receipt_verified") is True
        and status in {"done", "archived"}
        and predicate_passed
        and receipt_target
        and latest.get("remote_receipt") == receipt_target
        and SHA256_RE.fullmatch(str(latest.get("verification_context_digest") or ""))
    )
    digest = str(latest.get("verification_context_digest") or "")
    return receipt_verified, predicate_passed, digest if SHA256_RE.fullmatch(digest) else None


def reconcile_terminal_tasks(
    tasks: Iterable[Mapping[str, Any] | object],
    store: WorkLoanJournalStore,
    *,
    now: datetime | None = None,
) -> int:
    events = store.read()
    known_loans = {event.loan_id for event in events}
    settled_loans = {event.loan_id for event in events if event.phase == "settled"}
    count = 0
    for task in tasks:
        status = str(_value(task, "status") or "")
        if status not in TERMINAL_TASK_STATES:
            continue
        try:
            loan_id = loan_id_for_task(task)
        except WorkLoanJournalError:
            continue
        if loan_id not in known_loans or loan_id in settled_loans:
            continue
        verified, predicate_passed, digest = terminal_credit(task)
        logs = list(_value(task, "dispatch_log", []) or [])
        latest = _dump(logs[-1]) if logs else {"status": status}
        correlation = f"terminal-{canonical_sha256(latest)}"
        store.record_settlement(
            task,
            outcome="done" if status in {"done", "archived"} else status,
            receipt_verified=verified,
            predicate_passed=predicate_passed,
            verification_digest=digest,
            correlation_id=correlation,
            now=now,
        )
        settled_loans.add(loan_id)
        count += 1
    return count
