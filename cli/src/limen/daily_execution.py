"""The single daily professional communications/application execution loop.

This module is intentionally a coordinator, not a second mail or application
engine.  It calls the existing Limen/UMA/application-pipeline entry points,
normalizes their count-only results behind small versioned records, and writes a
private, bounded receipt.  A draft, filled form, or generated social template is
never a delivery receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


LIFECYCLE_STATES = (
    "observed",
    "prepared",
    "approved",
    "attempted",
    "delivered",
    "confirmed",
    "blocked",
    "superseded",
)
TERMINAL_STATES = {"confirmed", "blocked", "superseded"}
ALLOWED_TRANSITIONS = {
    "observed": {"prepared", "blocked", "superseded"},
    "prepared": {"approved", "blocked", "superseded"},
    "approved": {"attempted", "blocked", "superseded"},
    "attempted": {"delivered", "blocked", "superseded"},
    "delivered": {"confirmed", "blocked", "superseded"},
    "confirmed": set(),
    "blocked": {"prepared", "approved", "superseded"},
    "superseded": set(),
}
DAILY_APPLICATION_TARGET = 3
RECEIPT_SCHEMA = "limen.daily_execution.v1"
DEFAULT_TIMEOUT_SECONDS = 1800
LOCAL_DATE_ENV = "LIMEN_DAILY_EXECUTION_TIMEZONE"
DELIVERY_RECEIPT_ENV = "LIMEN_DELIVERY_RECEIPTS"
OUTBOUND_ENV_NAMES = {
    "LIMEN_APPLY_FIRE",
    "LIMEN_CORRESPONDENCE_FIRE",
    "LIMEN_LINKEDIN_FIRE",
    "LIMEN_MAIL_SEND",
}


def _stable_id(prefix: str, *values: object) -> str:
    """Build a deterministic, PII-safe record identifier."""

    material = "\x1f".join(str(value) for value in values).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(material).hexdigest()[:24]}"


def _local_zone() -> Any:
    configured = os.environ.get(LOCAL_DATE_ENV, "").strip()
    if configured:
        try:
            return ZoneInfo(configured)
        except ZoneInfoNotFoundError:
            pass
    return datetime.now().astimezone().tzinfo or timezone.utc


def _local_date(value: str | datetime | None = None) -> date:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(_local_zone()).date()
    elif isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(_local_zone()).date()


def _text(value: Any, field_name: str, *, required: bool = True) -> str:
    if not isinstance(value, str) or (required and not value.strip()):
        raise ValueError(f"{field_name} must be a non-empty string")
    if any(ord(char) < 32 and char not in "\t\n\r" for char in value):
        raise ValueError(f"{field_name} contains control characters")
    return value


def _required(value: Any, field_name: str) -> str:
    return _text(value, field_name)


def _string_or_object(value: Any, field_name: str) -> str | dict[str, Any]:
    if not isinstance(value, (str, dict)):
        raise ValueError(f"{field_name} must be a string or object")
    return value


def _list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be a list of strings")
    return list(value)


def _evidence_list(value: Any, field_name: str) -> list[str | dict[str, Any]]:
    """Validate redacted evidence references while preserving exact bindings."""
    if not isinstance(value, list) or any(not isinstance(item, (str, dict)) for item in value):
        raise ValueError(f"{field_name} must be a list of strings or objects")
    return [dict(item) if isinstance(item, dict) else item for item in value]


def _state(value: Any, field_name: str = "state") -> str:
    if value not in LIFECYCLE_STATES:
        raise ValueError(f"{field_name} must be one of {', '.join(LIFECYCLE_STATES)}")
    return str(value)


def _coalesce(value: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in value:
            return value[name]
    return default


def _confirmation_reference(value: Any, exact_target: str) -> bool:
    """Accept only portal/mailbox evidence tied to the receipt's target.

    Provider adapters may keep the target binding private, so a redacted reference
    such as ``portal:<opaque-id>`` is sufficient in the public shape. Generic
    labels (``submitted``, ``accepted``, a filled form, or an SMTP response) are
    deliberately not confirmation evidence.
    """

    if isinstance(value, Mapping):
        kind = str(value.get("kind") or value.get("source") or "").lower()
        target = value.get("exact_target") or value.get("target") or value.get("role")
        return kind in {"portal", "mailbox"} and (not target or str(target) == exact_target)
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower()
    return normalized.startswith(("portal:", "mailbox:", "sent-mail:")) and normalized not in {
        "portal:submitted",
        "portal:filled",
        "portal:template",
        "mailbox:submitted",
        "mailbox:accepted",
        "sent-mail:submitted",
        "sent-mail:accepted",
    }


@dataclass(frozen=True)
class InteractionEventV1:
    """An observed channel event, with content kept behind a private reference."""

    source: str
    account: str
    thread: str
    participants: list[str]
    timestamp: str
    content_ref: str
    attachments: list[str] = field(default_factory=list)
    observation_receipt: str | dict[str, Any] = ""
    state: str = "observed"
    schema: str = "limen.interaction_event.v1"
    record_id: str = ""
    run_id: str = ""
    obligation_id: str = ""

    def __post_init__(self) -> None:
        _text(self.source, "source")
        _text(self.account, "account")
        _text(self.thread, "thread")
        _text(self.timestamp, "timestamp")
        _text(self.content_ref, "content_ref")
        _list(self.participants, "participants")
        _list(self.attachments, "attachments")
        if not isinstance(self.observation_receipt, (str, dict)):
            raise ValueError("observation_receipt must be a string or object")
        if not self.observation_receipt:
            raise ValueError("observation_receipt is required")
        _state(self.state)
        if self.state != "observed":
            raise ValueError("an InteractionEventV1 is created in observed state")
        if not self.record_id:
            object.__setattr__(
                self,
                "record_id",
                _stable_id(
                    "interaction",
                    self.source,
                    self.account,
                    self.thread,
                    self.timestamp,
                    self.content_ref,
                ),
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "source": self.source,
            "account": self.account,
            "thread": self.thread,
            "participants": list(self.participants),
            "timestamp": self.timestamp,
            "time": self.timestamp,
            "content_ref": self.content_ref,
            "content_reference": self.content_ref,
            "attachments": list(self.attachments),
            "observation_receipt": self.observation_receipt,
            "state": self.state,
            "record_id": self.record_id,
            "run_id": self.run_id,
            "obligation_id": self.obligation_id,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "InteractionEventV1":
        if value.get("schema", cls.schema) != cls.schema:
            raise ValueError("unsupported InteractionEventV1 schema")
        return cls(
            source=_required(value.get("source"), "source"),
            account=_required(value.get("account"), "account"),
            thread=_required(value.get("thread"), "thread"),
            participants=_list(value.get("participants"), "participants"),
            timestamp=_required(value.get("timestamp"), "timestamp"),
            content_ref=_required(value.get("content_ref"), "content_ref"),
            attachments=_list(value.get("attachments", []), "attachments"),
            observation_receipt=value.get("observation_receipt", ""),
            state=value.get("state", "observed"),
            record_id=str(value.get("record_id", "")),
            run_id=str(value.get("run_id", "")),
            obligation_id=str(value.get("obligation_id", "")),
        )


@dataclass(frozen=True)
class ObligationV1:
    """A derived action owed by an owner, linked back to observed evidence."""

    evidence_links: list[str]
    required_action: str
    recipient_target: str
    due_at: str
    risk_class: str
    owner: str
    state: str = "observed"
    schema: str = "limen.obligation.v1"
    record_id: str = ""
    not_before: str | None = None
    prerequisite_receipts: list[str] = field(default_factory=list)
    run_id: str = ""

    def __post_init__(self) -> None:
        _list(self.evidence_links, "evidence_links")
        if not self.evidence_links:
            raise ValueError("evidence_links must not be empty")
        _text(self.required_action, "required_action")
        _text(self.recipient_target, "recipient_target")
        _text(self.due_at, "due_at")
        _text(self.risk_class, "risk_class")
        _text(self.owner, "owner")
        _state(self.state)
        if self.not_before is not None:
            _text(self.not_before, "not_before")
        _list(self.prerequisite_receipts, "prerequisite_receipts")
        if not self.record_id:
            object.__setattr__(
                self,
                "record_id",
                _stable_id(
                    "obligation",
                    *self.evidence_links,
                    self.required_action,
                    self.recipient_target,
                    self.due_at,
                    self.owner,
                ),
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "evidence_links": list(self.evidence_links),
            "required_action": self.required_action,
            "recipient_target": self.recipient_target,
            "due_at": self.due_at,
            "risk_class": self.risk_class,
            "owner": self.owner,
            "state": self.state,
            "record_id": self.record_id,
            "not_before": self.not_before,
            "prerequisite_receipts": list(self.prerequisite_receipts),
            "run_id": self.run_id,
            # Canonical short names are included for owner adapters that do not
            # use Limen's compatibility names.
            "evidence": list(self.evidence_links),
            "action": self.required_action,
            "target": self.recipient_target,
            "due": self.due_at,
            "risk": self.risk_class,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ObligationV1":
        if value.get("schema", cls.schema) != cls.schema:
            raise ValueError("unsupported ObligationV1 schema")
        return cls(
            evidence_links=_list(_coalesce(value, "evidence_links", "evidence"), "evidence_links"),
            required_action=_required(_coalesce(value, "required_action", "action"), "required_action"),
            recipient_target=_required(_coalesce(value, "recipient_target", "target"), "recipient_target"),
            due_at=_required(_coalesce(value, "due_at", "due"), "due_at"),
            risk_class=_required(_coalesce(value, "risk_class", "risk"), "risk_class"),
            owner=_required(value.get("owner"), "owner"),
            state=value.get("state", "observed"),
            record_id=str(value.get("record_id", "")),
            not_before=value.get("not_before"),
            prerequisite_receipts=_list(value.get("prerequisite_receipts", []), "prerequisite_receipts"),
            run_id=str(value.get("run_id", "")),
        )


@dataclass(frozen=True)
class DeliveryReceiptV1:
    """Evidence about one attempted delivery; confirmation requires evidence."""

    exact_target: str
    attempted_action: str
    provider_response: str | dict[str, Any]
    timestamp: str
    confirmation_evidence: list[str | dict[str, Any]]
    failure_category: str | None = None
    state: str = "attempted"
    schema: str = "limen.delivery_receipt.v1"
    provider: str = "unknown"
    account: str = "unknown"
    run_id: str = ""
    obligation_id: str = ""
    receipt_id: str = ""

    def __post_init__(self) -> None:
        _text(self.exact_target, "exact_target")
        _text(self.attempted_action, "attempted_action")
        if not isinstance(self.provider_response, (str, dict)):
            raise ValueError("provider_response must be a string or object")
        _text(self.timestamp, "timestamp")
        _list(self.confirmation_evidence, "confirmation_evidence")
        if self.failure_category is not None:
            _text(self.failure_category, "failure_category")
        _text(self.provider, "provider")
        _text(self.account, "account")
        if self.run_id:
            _text(self.run_id, "run_id")
        if self.obligation_id:
            _text(self.obligation_id, "obligation_id")
        _state(self.state)
        if self.state == "confirmed" and not any(
            _confirmation_reference(item, self.exact_target) for item in self.confirmation_evidence
        ):
            raise ValueError("confirmed delivery requires confirmation_evidence")
        if self.state == "blocked" and not self.failure_category:
            raise ValueError("blocked delivery requires failure_category")
        if self.provider.lower() == "unknown":
            raise ValueError("provider is required")
        if self.account.lower() == "unknown":
            raise ValueError("account is required")
        if not self.run_id:
            raise ValueError("run_id is required")
        if not self.obligation_id:
            raise ValueError("obligation_id is required")
        if not self.receipt_id:
            object.__setattr__(
                self,
                "receipt_id",
                _stable_id(
                    "delivery",
                    self.provider,
                    self.account,
                    self.exact_target,
                    self.attempted_action,
                    self.timestamp,
                    self.run_id,
                    self.obligation_id,
                ),
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "exact_target": self.exact_target,
            "attempted_action": self.attempted_action,
            "action": self.attempted_action,
            "provider_response": self.provider_response,
            "response": self.provider_response,
            "timestamp": self.timestamp,
            "time": self.timestamp,
            "confirmation_evidence": list(self.confirmation_evidence),
            "evidence": list(self.confirmation_evidence),
            "failure_category": self.failure_category,
            "failure": self.failure_category,
            "state": self.state,
            "provider": self.provider,
            "account": self.account,
            "run_id": self.run_id,
            "obligation_id": self.obligation_id,
            "receipt_id": self.receipt_id,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DeliveryReceiptV1":
        if value.get("schema", cls.schema) != cls.schema:
            raise ValueError("unsupported DeliveryReceiptV1 schema")
        return cls(
            exact_target=_required(_coalesce(value, "exact_target", "target"), "exact_target"),
            attempted_action=_required(_coalesce(value, "attempted_action", "action"), "attempted_action"),
            provider_response=_string_or_object(_coalesce(value, "provider_response", "response"), "provider_response"),
            timestamp=_required(_coalesce(value, "timestamp", "time"), "timestamp"),
            confirmation_evidence=_evidence_list(
                _coalesce(value, "confirmation_evidence", "evidence", default=[]), "confirmation_evidence"
            ),
            failure_category=_coalesce(value, "failure_category", "failure"),
            state=value.get("state", "attempted"),
            provider=_required(value.get("provider", "unknown"), "provider"),
            account=_required(value.get("account", "unknown"), "account"),
            run_id=str(value.get("run_id", "")),
            obligation_id=str(value.get("obligation_id", "")),
            receipt_id=str(value.get("receipt_id", "")),
        )


def can_transition(current: str, new: str) -> bool:
    """Return whether a record may advance without skipping delivery evidence."""

    _state(current, "current")
    _state(new, "new")
    return new in ALLOWED_TRANSITIONS[current]


def transition_state(current: str, new: str) -> str:
    if not can_transition(current, new):
        raise ValueError(f"invalid lifecycle transition: {current} -> {new}")
    return new


def _root_from_env() -> Path:
    return Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[3])).expanduser().resolve()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _run_id(root: Path) -> str:
    """Return one stable run identity for the local calendar day.

    Dry and fire invocations deliberately share this identity.  A fire retry
    resumes the staged run instead of creating a second application day.
    """

    return _stable_id("daily", root.resolve(), _local_date().isoformat())


def _safe_tail(value: str, limit: int = 240) -> str:
    """Return only a diagnostic class/count, never provider output or message text."""

    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if not lines:
        return "no output"
    return f"{len(lines)} output line(s); last line suppressed"


def _parse_json_output(stdout: str) -> dict[str, Any]:
    try:
        value = json.loads(stdout)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    for line in reversed(stdout.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def _redact_step_summary(name: str, value: Mapping[str, Any]) -> dict[str, Any]:
    """Keep count/state fields from existing owners' machine output.

    Provider IDs and role names stay in the owner receipt ledger.  The daily
    report carries only counts and safe lifecycle categories.
    """

    def integer(key: str) -> int:
        try:
            return int(value.get(key, 0) or 0)
        except (TypeError, ValueError):
            return 0

    if name == "applications":
        summary: dict[str, Any] = {
            key: integer(key) for key in ("sourced", "qualified", "staged", "submitted", "attempted", "confirmed")
        } | {key: bool(value.get(key, False)) for key in ("armed", "launched", "cycle_completed", "retry_locked")}
        for key in ("ambiguous", "blocked", "superseded"):
            summary[key] = integer(key)
        notes = value.get("notes")
        if isinstance(notes, list):
            summary["notes"] = ["owner note suppressed" for note in notes if note]
        return summary
    if name == "followups":
        dispositions = value.get("by_disposition")
        safe_dispositions: dict[str, int] = {}
        if isinstance(dispositions, dict):
            for key, raw in dispositions.items():
                if isinstance(key, str) and isinstance(raw, (int, float)):
                    safe_dispositions[key] = int(raw)
        return {
            "reply_owed": integer("reply_owed"),
            "non_terminal": integer("non_terminal"),
            "needs_human": integer("needs_human"),
            "by_disposition": safe_dispositions,
            "fixed_point": bool(value.get("fixed_point", False)),
            "uma_available": bool(value.get("uma_available", False)),
            "attempted": integer("attempted"),
            "delivered": integer("delivered"),
            "confirmed": integer("confirmed"),
            "blocked": integer("blocked"),
            "superseded": integer("superseded"),
            "retry_locked": bool(value.get("retry_locked", False)),
        }
    # Opportunity review is count-only by contract; still retain only scalar counts.
    return {str(key): int(raw) for key, raw in value.items() if isinstance(key, str) and isinstance(raw, (int, float))}


def _run_step(
    *,
    name: str,
    args: Sequence[str],
    env: Mapping[str, str],
    cwd: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            list(args),
            cwd=str(cwd),
            env=dict(env),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError:
        return {"name": name, "status": "blocked", "failure_category": "missing_owner", "returncode": 127}
    except subprocess.TimeoutExpired:
        return {"name": name, "status": "blocked", "failure_category": "timeout", "returncode": 124}
    except OSError:
        return {"name": name, "status": "blocked", "failure_category": "unavailable", "returncode": 126}

    result: dict[str, Any] = {
        "name": name,
        "status": "completed" if completed.returncode == 0 else "blocked",
        "returncode": completed.returncode,
        "output": _safe_tail(completed.stdout or ""),
    }
    result["failure_category"] = None if completed.returncode == 0 else "provider_or_owner_failure"
    parsed = _parse_json_output(completed.stdout or "")
    if parsed:
        result["summary"] = _redact_step_summary(name, parsed)
    return result


def _receipt_path() -> Path:
    configured = os.environ.get("LIMEN_DAILY_EXECUTION_RECEIPT")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / "System" / "Reports" / "communications" / "daily-execution-latest.json"


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _delivery_ledger_configured() -> bool:
    """Whether a canonical delivery ledger is actually wired up.

    ``LIMEN_DELIVERY_RECEIPTS`` is optional by design, but when it is unset
    ``_canonical_delivery_rows()`` returns ``[]`` — and an empty ledger is then
    counted as *zero confirmations*, which is a measurement the coordinator never
    made. The two are not the same fact, and conflating them is what makes the daily
    shortage permanent: ``confirmed`` can never rise, so ``status`` is ``blocked`` on
    every run no matter how many applications genuinely succeeded.

    That is an exit condition no amount of retrying can satisfy. On 2026-08-04/05 an
    agent retried it for 27 hours straight and exhausted its entire quota. An
    unreachable predicate must announce itself as a configuration defect, not
    masquerade as a shortfall of work.
    """

    return bool(os.environ.get(DELIVERY_RECEIPT_ENV))


def _canonical_delivery_rows() -> list[dict[str, Any]]:
    """Read the one provider-owned delivery ledger.

    Older application-specific environment variables are intentionally not
    accepted.  A receipt is useful to the coordinator only when it is a
    valid DeliveryReceiptV1; labels and templates are not upgraded here.
    """

    configured = os.environ.get(DELIVERY_RECEIPT_ENV)
    if not configured:
        return []
    value = _load_json(Path(configured).expanduser())
    if isinstance(value, dict):
        value = value.get("receipts") or []
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in value:
        if not isinstance(row, dict):
            continue
        try:
            receipt = DeliveryReceiptV1.from_dict(row)
        except (TypeError, ValueError):
            continue
        if receipt.receipt_id in seen:
            continue
        seen.add(receipt.receipt_id)
        rows.append(receipt.as_dict())
    return rows


def _application_pipeline_census() -> dict[str, Any]:
    """Read the authoritative pipeline's state without treating labels as proof.

    The pipeline has historically contained rows labelled ``submitted`` whose
    portal state was only a filled form. This census is intentionally read-only:
    only a row explicitly carrying portal/mailbox confirmation evidence counts.
    """

    home = Path.home()
    override = os.environ.get("APPLICATION_PIPELINE")
    candidates = [
        Path(override).expanduser() if override else None,
        home / "Workspace" / "application-pipeline",
        home / "Workspace" / "4444J99" / "application-pipeline",
        home / "Workspace" / "organvm" / "application-pipeline",
        home / "application-pipeline",
    ]
    pipeline_root = next(
        (candidate for candidate in candidates if candidate is not None and (candidate / "pipeline").is_dir()),
        None,
    )
    if pipeline_root is None:
        return {"source_present": False, "claimed_submitted": 0, "unconfirmed_claims": 0, "confirmed": 0}

    try:
        import yaml
    except ImportError:
        return {"source_present": True, "claimed_submitted": 0, "unconfirmed_claims": 0, "confirmed": 0}

    try:
        rows = []
        for path in sorted((pipeline_root / "pipeline" / "submitted").glob("*.yaml")):
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
            rows.append(value if isinstance(value, dict) else {})
    except (OSError, yaml.YAMLError):
        return {"source_present": True, "claimed_submitted": 0, "unconfirmed_claims": 0, "confirmed": 0}

    claimed = 0
    confirmed = 0
    for row in rows:
        if str(row.get("status", "")).lower() not in {"submitted", "confirmed"}:
            continue
        claimed += 1
        submission: dict[str, Any] = {}
        submission_value = row.get("submission")
        if isinstance(submission_value, dict):
            submission = submission_value
        evidence = (
            submission.get("confirmation_evidence")
            or submission.get("portal_confirmation")
            or submission.get("mailbox_confirmation")
        )
        if str(row.get("status", "")).lower() == "confirmed" and evidence:
            confirmed += 1
    return {
        "source_present": True,
        "claimed_submitted": claimed,
        "unconfirmed_claims": claimed - confirmed,
        "confirmed": confirmed,
    }


def _is_application_action(action: str) -> bool:
    normalized = action.lower()
    return any(token in normalized for token in ("application", "apply", "ats", "submit"))


def _is_followup_action(action: str) -> bool:
    normalized = action.lower()
    return any(token in normalized for token in ("email", "mail", "linkedin", "follow-up", "followup"))


def _current_receipts(rows: Sequence[Mapping[str, Any]], run_id: str) -> list[dict[str, Any]]:
    today = _local_date().isoformat()
    return [
        dict(row)
        for row in rows
        if str(row.get("run_id", "")) == run_id and _local_date(str(row.get("timestamp", ""))).isoformat() == today
    ]


def _application_summary(
    application_step: Mapping[str, Any],
    *,
    run_id: str,
    delivery_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    summary = application_step.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    qualified = int(summary.get("qualified", 0) or 0)
    staged = int(summary.get("staged", 0) or 0)
    submitted = int(summary.get("submitted", 0) or 0)
    current_rows = [
        row
        for row in _current_receipts(delivery_rows, run_id)
        if _is_application_action(str(row.get("attempted_action", "")))
    ]
    confirmed_rows = [row for row in current_rows if row.get("state") == "confirmed"]
    pipeline_census = _application_pipeline_census()
    confirmed = len(confirmed_rows)
    eligible = max(qualified, staged)
    ledger_configured = _delivery_ledger_configured()
    shortage_reason: str | None
    if not ledger_configured:
        # Confirmations are UNMEASURED, not zero. Reporting a shortage here would
        # invite retry against a predicate that cannot move.
        shortage = 0
        shortage_reason = None
    elif eligible < DAILY_APPLICATION_TARGET:
        shortage = DAILY_APPLICATION_TARGET - eligible
        shortage_reason = "fewer than three live, nonduplicate eligible roles were verified"
    else:
        shortage = max(0, DAILY_APPLICATION_TARGET - confirmed)
        shortage_reason = "provider confirmation evidence is below the daily target" if shortage else None
    blockers: list[str] = []
    if not ledger_configured:
        blockers.append(
            f"delivery receipt ledger is not configured ({DELIVERY_RECEIPT_ENV}) — "
            "confirmation counts are unmeasured, not zero; retrying cannot change this"
        )
    attempted = sum(1 for row in current_rows if row.get("state") in {"attempted", "delivered"})
    ambiguous = sum(1 for row in current_rows if row.get("state") == "attempted")
    blocked_receipts = sum(1 for row in current_rows if row.get("state") == "blocked")
    superseded = sum(1 for row in current_rows if row.get("state") == "superseded")
    if (submitted or attempted) and not confirmed:
        # Never suppressed: an engine claiming submissions it cannot evidence is the
        # fabrication guard. Only the stated REASON changes, so that "we looked and
        # found none" is not confused with "there was nowhere to look".
        blockers.append(
            "application engine reported submitted, but the confirmation receipt ledger is not configured"
            if not ledger_configured
            else "application engine reported submitted, but no portal/mailbox confirmation receipt was found"
        )
    if ambiguous:
        blockers.append("ambiguous application attempts are retry-locked until provider state is reconciled")
    if summary.get("notes"):
        blockers.append("application pipeline reported an owner/runtime note")
    if shortage and shortage_reason:
        blockers.append(shortage_reason)
    return {
        "target": DAILY_APPLICATION_TARGET,
        "eligible": eligible,
        "staged": staged,
        "submitted": submitted,
        "attempted": attempted,
        "ambiguous": ambiguous,
        "blocked": blocked_receipts,
        "superseded": superseded,
        "confirmed": confirmed,
        "shortage": shortage,
        "shortage_reason": shortage_reason,
        "blockers": blockers,
        "confirmation_receipts": [
            {
                "state": "confirmed",
                "evidence_count": len(row.get("confirmation_evidence") or row.get("evidence") or []),
                "receipt_id": row.get("receipt_id", ""),
            }
            for row in confirmed_rows
        ],
        "historical_reconciliation": pipeline_census,
        "current_receipt_count": len(current_rows),
        # Lets a caller tell "we counted zero" from "we could not count" without
        # parsing prose, so a scheduler never retries an unreachable predicate.
        "confirmation_measured": ledger_configured,
    }


def _followup_summary(
    followup_step: Mapping[str, Any],
    *,
    run_id: str,
    delivery_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    summary = followup_step.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    by_disposition = summary.get("by_disposition")
    if not isinstance(by_disposition, dict):
        by_disposition = {}
    current_rows = [
        row
        for row in _current_receipts(delivery_rows, run_id)
        if _is_followup_action(str(row.get("attempted_action", "")))
    ]
    confirmed = sum(1 for row in current_rows if row.get("state") == "confirmed")
    blocked = int(by_disposition.get("held", 0) or 0) + int(by_disposition.get("needs-human", 0) or 0)
    blocked += int(summary.get("non_terminal", 0) or 0)
    blocked += sum(1 for row in current_rows if row.get("state") == "blocked")
    return {
        "due": int(summary.get("reply_owed", 0) or 0),
        "confirmed": confirmed,
        "blocked": blocked,
        "by_disposition": {str(k): int(v or 0) for k, v in by_disposition.items()},
        "fixed_point": bool(summary.get("fixed_point", False)),
        "provider_evidence": bool(summary.get("uma_available", False)),
        "attempted": sum(1 for row in current_rows if row.get("state") in {"attempted", "delivered"}),
        "delivered": sum(1 for row in current_rows if row.get("state") == "delivered"),
        "receipt_count": len(current_rows),
        "superseded": sum(1 for row in current_rows if row.get("state") == "superseded"),
        "retry_locked": any(row.get("state") == "attempted" for row in current_rows),
    }


def _provider_delivery_receipts() -> list[dict[str, Any]]:
    """Load exact-target receipts from the existing provider-owned receipt store.

    Count-only correspondence dispositions remain a reconciliation reference,
    not a fabricated per-recipient receipt. The owner can opt the canonical
    provider receipt ledger into the daily report with ``LIMEN_DELIVERY_RECEIPTS``.
    """

    return _canonical_delivery_rows()


def _stage_env(repo_root: Path, fire: bool, owner: str, run_id: str) -> dict[str, str]:
    """Give each owner only the valve it can exercise.

    In particular, ingestion and reconciliation do not inherit a send arm from
    the daemon's environment.  This is an allow-list, not a set-to-zero
    convention, so a provider cannot accidentally interpret a new variable.
    """

    env = {key: value for key, value in os.environ.items() if key not in OUTBOUND_ENV_NAMES}
    env["LIMEN_ROOT"] = str(repo_root)
    env["LIMEN_DAILY_RUN_ID"] = run_id
    if owner == "application":
        env["LIMEN_APPLY_FIRE"] = "1" if fire else "0"
    elif owner == "followup":
        env["LIMEN_CORRESPONDENCE_FIRE"] = "1" if fire else "0"
        env["LIMEN_LINKEDIN_FIRE"] = "1" if fire else "0"
        env["LIMEN_MAIL_SEND"] = "1" if fire else "0"
    return env


def _internal_stage(name: str, *, delivery_rows: Sequence[Mapping[str, Any]], run_id: str) -> dict[str, Any]:
    current = _current_receipts(delivery_rows, run_id)
    historical = [row for row in delivery_rows if row not in current]
    return {
        "name": name,
        "status": "completed",
        "returncode": 0,
        "failure_category": None,
        "summary": {
            "current_receipts": len(current),
            "historical_receipts": len(historical),
            "historical_confirmed": sum(1 for row in historical if row.get("state") == "confirmed"),
        }
        if name.startswith("provider_reconcile")
        else {"voice_reviewed": 0, "factual_reviewed": 0, "judgment": "no_outbound_prose"},
    }


def _checkpoint_reusable(checkpoint: Mapping[str, Any], *, owner: str, fire: bool) -> bool:
    if checkpoint.get("status") != "completed":
        return bool(checkpoint.get("retry_locked"))
    if owner in {"application", "followup"}:
        return bool(checkpoint.get("fire", False)) or not fire
    return True


def _write_receipt(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_daily_execution(
    *,
    fire: bool = False,
    root: Path | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    step_runner: Callable[..., dict[str, Any]] | None = None,
    write_receipt: bool = True,
) -> dict[str, Any]:
    """Run one persisted, resumable local-calendar-day execution.

    Successful stage checkpoints are reused on retry.  A later fire invocation
    may resume a dry run, but it gets a fresh checkpoint for each outbound owner;
    an already-attempted or ambiguous outbound checkpoint remains retry-locked.
    """

    repo_root = (root or _root_from_env()).expanduser().resolve()
    path = _receipt_path()
    run_id = _run_id(repo_root)
    prior = _load_json(path) if write_receipt else None
    if isinstance(prior, dict) and prior.get("run_id") == run_id:
        prior_fire = bool(prior.get("fire", False))
        if prior.get("status") == "confirmed" and (prior_fire or not fire):
            return prior

    started_at = str(prior.get("started_at")) if isinstance(prior, dict) and prior.get("started_at") else _now()
    checkpoints: dict[str, dict[str, Any]] = {}
    if isinstance(prior, dict) and isinstance(prior.get("stage_checkpoints"), dict):
        checkpoints = {
            str(name): dict(value) for name, value in prior["stage_checkpoints"].items() if isinstance(value, dict)
        }

    script = repo_root / "scripts"
    runner = step_runner or _run_step
    timeout = max(1, min(int(timeout_seconds), DEFAULT_TIMEOUT_SECONDS))
    stage_specs: tuple[tuple[str, Sequence[str] | None, str], ...] = (
        ("ingest", ("bash", str(script / "mail-beat.sh")), "read"),
        # The opportunity owner is also the obligations derivation owner.  Keep
        # its historical command name in the receipt for compatibility.
        ("opportunities", (sys.executable, str(script / "opportunity-review-delta.py"), "--json"), "read"),
        (
            "applications",
            (sys.executable, str(script / "application-funnel.py"), "--json", "--wait"),
            "application",
        ),
        ("voice_checks", None, "read"),
        ("application_confirmation", None, "read"),
        (
            "followups",
            (sys.executable, str(script / "correspondence-walk.py"), "--drain", "--json"),
            "followup",
        ),
    )

    logical_stage_order = [
        "ingest_transcribe",
        "provider_reconcile_before",
        "derive_obligations",
        "source_rank_evidence",
        "voice_factual_checks",
        "confirm_applications",
        "settle_professional_followups",
        "provider_reconcile_after",
    ]
    if "provider_reconcile_before" not in checkpoints:
        checkpoints["provider_reconcile_before"] = _internal_stage(
            "provider_reconcile_before", delivery_rows=_provider_delivery_receipts(), run_id=run_id
        )

    for name, args, owner in stage_specs:
        existing = checkpoints.get(name)
        if existing is not None and _checkpoint_reusable(existing, owner=owner, fire=fire):
            continue
        if args is None:
            delivery_rows = _provider_delivery_receipts()
            stage_result = _internal_stage(name, delivery_rows=delivery_rows, run_id=run_id)
        else:
            stage_result = runner(
                name=name,
                args=list(args),
                env=_stage_env(repo_root, fire, owner, run_id),
                cwd=repo_root,
                timeout_seconds=timeout,
            )
        stage_result = dict(stage_result)
        stage_result["name"] = name
        stage_result["fire"] = bool(fire) if owner in {"application", "followup"} else False
        if stage_result.get("status") == "blocked" and owner in {"application", "followup"}:
            stage_result["retry_locked"] = bool(
                stage_result.get("ambiguous")
                or stage_result.get("summary", {}).get("ambiguous")
                or stage_result.get("summary", {}).get("retry_locked")
            )
        checkpoints[name] = stage_result

    delivery_rows = _provider_delivery_receipts()
    if "voice_checks" not in checkpoints:
        checkpoints["voice_checks"] = {
            "name": "voice_checks",
            "status": "completed",
            "returncode": 0,
            "failure_category": None,
            "summary": {"voice_reviewed": 0, "factual_reviewed": 0, "judgment": "no_outbound_prose"},
            "fire": False,
        }
    if "application_confirmation" not in checkpoints:
        checkpoints["application_confirmation"] = {
            "name": "application_confirmation",
            "status": "completed",
            "returncode": 0,
            "failure_category": None,
            "summary": {"target": DAILY_APPLICATION_TARGET},
            "fire": False,
        }
    if "provider_reconcile_after" not in checkpoints:
        checkpoints["provider_reconcile_after"] = _internal_stage(
            "provider_reconcile_after", delivery_rows=delivery_rows, run_id=run_id
        )
    steps = [checkpoints[name] for name, _, _ in stage_specs if name in checkpoints]
    application_step = checkpoints.get("applications", {})
    followup_step = checkpoints.get("followups", {})
    applications = _application_summary(application_step, run_id=run_id, delivery_rows=delivery_rows)
    followups = _followup_summary(followup_step, run_id=run_id, delivery_rows=delivery_rows)
    blockers = list(applications["blockers"])
    blockers.extend(
        f"{step.get('name', 'unknown')} stage blocked: {step.get('failure_category', 'unknown')}"
        for step in steps
        if step.get("status") == "blocked" and not step.get("retry_locked")
    )
    blockers.extend(
        f"{step.get('name', 'unknown')} remains retry-locked pending provider reconciliation"
        for step in steps
        if step.get("retry_locked")
    )
    blockers.extend(
        [
            "professional follow-up reconciliation is not at a fixed point" if not followups["fixed_point"] else "",
            "follow-up provider evidence unavailable"
            if followups["due"] and not followups["provider_evidence"]
            else "",
        ]
    )
    blockers = list(dict.fromkeys(blocker for blocker in blockers if blocker))
    current_rows = _current_receipts(delivery_rows, run_id)
    historical_rows = [row for row in delivery_rows if row not in current_rows]
    result: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "run_id": run_id,
        "local_date": _local_date().isoformat(),
        "started_at": started_at,
        "completed_at": _now(),
        "fire": bool(fire or (isinstance(prior, dict) and prior.get("fire", False))),
        "stage_order": logical_stage_order,
        "stages": steps,
        "stage_checkpoints": checkpoints,
        "applications": applications,
        "follow_ups": followups,
        "delivery_receipts": delivery_rows,
        "reconciliation": {
            "current_run_receipts": len(current_rows),
            "historical_receipts": len(historical_rows),
            "historical_confirmed": sum(1 for row in historical_rows if row.get("state") == "confirmed"),
        },
        "blockers": blockers,
        "status": "confirmed" if not blockers else "blocked",
        "privacy": {"redacted": True, "content_bodies": False, "contact_data": False},
    }
    if write_receipt:
        try:
            result["receipt_path"] = str(path)
            if isinstance(prior, dict):
                replay = dict(prior)
                replay["completed_at"] = result["completed_at"]
                if replay == result:
                    # A replay that differs only by the clock read is the fixed point:
                    # keep the persisted receipt (state and bytes) instead of re-stamping.
                    return prior
            _write_receipt(path, result)
        except OSError:
            result["blockers"].append("daily receipt could not be written")
            result["status"] = "blocked"
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the bounded daily communications/application loop")
    parser.add_argument(
        "--fire", action="store_true", help="arm routine professional applications/follow-ups for this invocation"
    )
    parser.add_argument("--json", action="store_true", help="print the PII-clean machine receipt")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--receipt", type=Path, default=None, help="override the private receipt path")
    args = parser.parse_args(argv)
    prior = os.environ.get("LIMEN_DAILY_EXECUTION_RECEIPT")
    if args.receipt:
        os.environ["LIMEN_DAILY_EXECUTION_RECEIPT"] = str(args.receipt.expanduser())
    try:
        result = run_daily_execution(fire=args.fire, timeout_seconds=args.timeout)
    finally:
        if prior is None:
            os.environ.pop("LIMEN_DAILY_EXECUTION_RECEIPT", None)
        else:
            os.environ["LIMEN_DAILY_EXECUTION_RECEIPT"] = prior
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            f"daily-execute: {result['status']} · applications "
            f"{result['applications']['confirmed']}/{result['applications']['target']} confirmed · "
            f"follow-ups {result['follow_ups']['confirmed']} confirmed"
        )
        for blocker in result["blockers"]:
            print(f"  - {blocker}")
    return 0 if result["status"] != "blocked" else 3


if __name__ == "__main__":
    raise SystemExit(main())
