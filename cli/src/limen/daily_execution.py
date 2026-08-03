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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


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
DEFAULT_TIMEOUT_SECONDS = 300


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


def _state(value: Any, field_name: str = "state") -> str:
    if value not in LIFECYCLE_STATES:
        raise ValueError(f"{field_name} must be one of {', '.join(LIFECYCLE_STATES)}")
    return str(value)


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
        _state(self.state)
        if self.state != "observed":
            raise ValueError("an InteractionEventV1 is created in observed state")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "source": self.source,
            "account": self.account,
            "thread": self.thread,
            "participants": list(self.participants),
            "timestamp": self.timestamp,
            "content_ref": self.content_ref,
            "attachments": list(self.attachments),
            "observation_receipt": self.observation_receipt,
            "state": self.state,
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
        )


@dataclass(frozen=True)
class ObligationV1:
    """A derived action owed by an owner, linked back to observed evidence."""

    evidence_links: list[str]
    required_action: str
    recipient_target: str
    due_at: str | None
    risk_class: str
    owner: str
    state: str = "observed"
    schema: str = "limen.obligation.v1"

    def __post_init__(self) -> None:
        _list(self.evidence_links, "evidence_links")
        if not self.evidence_links:
            raise ValueError("evidence_links must not be empty")
        _text(self.required_action, "required_action")
        _text(self.recipient_target, "recipient_target")
        if self.due_at is not None:
            _text(self.due_at, "due_at")
        _text(self.risk_class, "risk_class")
        _text(self.owner, "owner")
        _state(self.state)

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
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ObligationV1":
        if value.get("schema", cls.schema) != cls.schema:
            raise ValueError("unsupported ObligationV1 schema")
        return cls(
            evidence_links=_list(value.get("evidence_links"), "evidence_links"),
            required_action=_required(value.get("required_action"), "required_action"),
            recipient_target=_required(value.get("recipient_target"), "recipient_target"),
            due_at=value.get("due_at"),
            risk_class=_required(value.get("risk_class"), "risk_class"),
            owner=_required(value.get("owner"), "owner"),
            state=value.get("state", "observed"),
        )


@dataclass(frozen=True)
class DeliveryReceiptV1:
    """Evidence about one attempted delivery; confirmation requires evidence."""

    exact_target: str
    attempted_action: str
    provider_response: str | dict[str, Any]
    timestamp: str
    confirmation_evidence: list[str]
    failure_category: str | None = None
    state: str = "attempted"
    schema: str = "limen.delivery_receipt.v1"

    def __post_init__(self) -> None:
        _text(self.exact_target, "exact_target")
        _text(self.attempted_action, "attempted_action")
        if not isinstance(self.provider_response, (str, dict)):
            raise ValueError("provider_response must be a string or object")
        _text(self.timestamp, "timestamp")
        _list(self.confirmation_evidence, "confirmation_evidence")
        if self.failure_category is not None:
            _text(self.failure_category, "failure_category")
        _state(self.state)
        if self.state == "confirmed" and not self.confirmation_evidence:
            raise ValueError("confirmed delivery requires confirmation_evidence")
        if self.state == "blocked" and not self.failure_category:
            raise ValueError("blocked delivery requires failure_category")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "exact_target": self.exact_target,
            "attempted_action": self.attempted_action,
            "provider_response": self.provider_response,
            "timestamp": self.timestamp,
            "confirmation_evidence": list(self.confirmation_evidence),
            "failure_category": self.failure_category,
            "state": self.state,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DeliveryReceiptV1":
        if value.get("schema", cls.schema) != cls.schema:
            raise ValueError("unsupported DeliveryReceiptV1 schema")
        return cls(
            exact_target=_required(value.get("exact_target"), "exact_target"),
            attempted_action=_required(value.get("attempted_action"), "attempted_action"),
            provider_response=_string_or_object(value.get("provider_response"), "provider_response"),
            timestamp=_required(value.get("timestamp"), "timestamp"),
            confirmation_evidence=_list(value.get("confirmation_evidence", []), "confirmation_evidence"),
            failure_category=value.get("failure_category"),
            state=value.get("state", "attempted"),
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


def _run_id(root: Path, fire: bool) -> str:
    day = datetime.now(timezone.utc).date().isoformat()
    material = f"{root.resolve()}|{day}|{'fire' if fire else 'stage'}".encode()
    return hashlib.sha256(material).hexdigest()[:20]


def _safe_tail(value: str, limit: int = 240) -> str:
    """Return only a diagnostic class/count, never provider output or message text."""

    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if not lines:
        return "no output"
    return f"{len(lines)} output line(s); last line suppressed"


def _parse_json_output(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def _redact_step_summary(name: str, value: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only count/state fields from existing owners' machine output."""

    def integer(key: str) -> int:
        try:
            return int(value.get(key, 0) or 0)
        except (TypeError, ValueError):
            return 0

    if name == "applications":
        return {
            key: integer(key)
            for key in ("sourced", "qualified", "staged", "submitted")
        } | {key: bool(value.get(key, False)) for key in ("armed", "launched")}
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
        }
    # Opportunity review is count-only by contract; still retain only scalar counts.
    return {
        str(key): int(raw)
        for key, raw in value.items()
        if isinstance(key, str) and isinstance(raw, (int, float))
    }


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


def _confirmation_receipts() -> list[dict[str, Any]]:
    configured = os.environ.get("LIMEN_APPLICATION_CONFIRMATION_RECEIPT") or os.environ.get(
        "LIMEN_APPLICATION_RECEIPTS"
    )
    if not configured:
        return []
    value = _load_json(Path(configured).expanduser())
    if isinstance(value, dict):
        value = value.get("receipts") or value.get("applications") or []
    if not isinstance(value, list):
        return []
    confirmed: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, dict):
            continue
        state = str(row.get("state") or row.get("status") or "").lower()
        evidence = row.get("confirmation_evidence") or row.get("evidence") or []
        if state in {"confirmed", "portal_confirmed", "mailbox_confirmed"} and evidence:
            confirmed.append(row)
    return confirmed


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
        import yaml  # type: ignore[import-untyped]
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
        evidence = submission.get("confirmation_evidence") or submission.get("portal_confirmation") or submission.get(
            "mailbox_confirmation"
        )
        if str(row.get("status", "")).lower() == "confirmed" and evidence:
            confirmed += 1
    return {
        "source_present": True,
        "claimed_submitted": claimed,
        "unconfirmed_claims": claimed - confirmed,
        "confirmed": confirmed,
    }


def _application_summary(application_step: Mapping[str, Any]) -> dict[str, Any]:
    summary = application_step.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    qualified = int(summary.get("qualified", 0) or 0)
    staged = int(summary.get("staged", 0) or 0)
    submitted = int(summary.get("submitted", 0) or 0)
    confirmed_rows = _confirmation_receipts()
    pipeline_census = _application_pipeline_census()
    confirmed = len(confirmed_rows) + int(pipeline_census["confirmed"])
    eligible = max(qualified, staged)
    shortage_reason: str | None
    if eligible < DAILY_APPLICATION_TARGET:
        shortage = DAILY_APPLICATION_TARGET - eligible
        shortage_reason = "fewer than three live, nonduplicate eligible roles were verified"
    else:
        shortage = max(0, DAILY_APPLICATION_TARGET - confirmed)
        shortage_reason = "provider confirmation evidence is below the daily target" if shortage else None
    blockers: list[str] = []
    if submitted and not confirmed:
        blockers.append("application engine reported submitted, but no portal/mailbox confirmation receipt was found")
    if summary.get("notes"):
        blockers.append("application pipeline reported an owner/runtime note")
    if shortage and shortage_reason:
        blockers.append(shortage_reason)
    return {
        "target": DAILY_APPLICATION_TARGET,
        "eligible": eligible,
        "staged": staged,
        "submitted": submitted,
        "confirmed": confirmed,
        "shortage": shortage,
        "shortage_reason": shortage_reason,
        "blockers": blockers,
        "confirmation_receipts": [
            {
                "state": "confirmed",
                "evidence_count": len(row.get("confirmation_evidence") or row.get("evidence") or []),
            }
            for row in confirmed_rows
        ],
        "historical_reconciliation": pipeline_census,
    }


def _followup_summary(followup_step: Mapping[str, Any]) -> dict[str, Any]:
    summary = followup_step.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    by_disposition = summary.get("by_disposition")
    if not isinstance(by_disposition, dict):
        by_disposition = {}
    confirmed = int(by_disposition.get("sent", 0) or 0) + int(by_disposition.get("awaiting-them", 0) or 0)
    blocked = int(by_disposition.get("held", 0) or 0) + int(by_disposition.get("needs-human", 0) or 0)
    blocked += int(summary.get("non_terminal", 0) or 0)
    return {
        "due": int(summary.get("reply_owed", 0) or 0),
        "confirmed": confirmed,
        "blocked": blocked,
        "by_disposition": {str(k): int(v or 0) for k, v in by_disposition.items()},
        "fixed_point": bool(summary.get("fixed_point", False)),
        "provider_evidence": bool(summary.get("uma_available", False)),
    }


def _provider_delivery_receipts() -> list[dict[str, Any]]:
    """Load exact-target receipts from the existing provider-owned receipt store.

    Count-only correspondence dispositions remain a reconciliation reference,
    not a fabricated per-recipient receipt. The owner can opt the canonical
    provider receipt ledger into the daily report with ``LIMEN_DELIVERY_RECEIPTS``.
    """

    configured = os.environ.get("LIMEN_DELIVERY_RECEIPTS")
    if not configured:
        return []
    value = _load_json(Path(configured).expanduser())
    if isinstance(value, dict):
        value = value.get("receipts") or []
    if not isinstance(value, list):
        return []
    receipts: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, dict):
            continue
        try:
            receipt = DeliveryReceiptV1.from_dict(row)
        except (TypeError, ValueError):
            continue
        if receipt.state in {"delivered", "confirmed", "blocked", "superseded"}:
            receipts.append(receipt.as_dict())
    return receipts


def run_daily_execution(
    *,
    fire: bool = False,
    root: Path | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    step_runner: Callable[..., dict[str, Any]] | None = None,
    write_receipt: bool = True,
) -> dict[str, Any]:
    """Run the existing daily owners once and return a PII-clean bounded receipt.

    ``fire`` is an invocation-local valve. It never persists credentials or arms a
    global environment file. With the valve off, applications stage and follow-ups
    remain drafts/holds. The coordinator still performs the same idempotent reads
    and reconciliation so a dry run is useful evidence.
    """

    repo_root = (root or _root_from_env()).expanduser().resolve()
    started_at = _now()
    run_id = _run_id(repo_root, fire)
    env = dict(os.environ)
    env.update(
        {
            "LIMEN_ROOT": str(repo_root),
            "LIMEN_APPLY_FIRE": "1" if fire else "0",
            "LIMEN_CORRESPONDENCE_FIRE": "1" if fire else "0",
            "LIMEN_MAIL_SEND": "1" if fire else "0",
        }
    )
    script = repo_root / "scripts"
    runner = step_runner or _run_step

    steps: list[dict[str, Any]] = []
    commands = (
        ("ingest", ["bash", str(script / "mail-beat.sh")]),
        ("opportunities", [sys.executable, str(script / "opportunity-review-delta.py"), "--json"]),
        ("applications", [sys.executable, str(script / "application-funnel.py"), "--json"]),
        ("followups", [sys.executable, str(script / "correspondence-walk.py"), "--drain", "--json"]),
    )
    for name, args in commands:
        result = runner(
            name=name,
            args=args,
            env=env,
            cwd=repo_root,
            timeout_seconds=max(1, min(int(timeout_seconds), 1800)),
        )
        steps.append(result)

    application_step = next((step for step in steps if step.get("name") == "applications"), {})
    followup_step = next((step for step in steps if step.get("name") == "followups"), {})
    applications = _application_summary(application_step)
    followups = _followup_summary(followup_step)
    timestamp = _now()
    blockers = list(applications["blockers"])
    blockers.extend(
        f"{step.get('name', 'unknown')} stage blocked: {step.get('failure_category', 'unknown')}"
        for step in steps
        if step.get("status") == "blocked"
    )
    blockers.extend(
        [
            "professional follow-up reconciliation is not at a fixed point"
            if not followups["fixed_point"]
            else "",
            "follow-up provider evidence unavailable"
            if followups["due"] and not followups["provider_evidence"]
            else "",
        ]
    )
    blockers = [blocker for blocker in blockers if blocker]
    receipts = _provider_delivery_receipts()
    result = {
        "schema": RECEIPT_SCHEMA,
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": timestamp,
        "fire": bool(fire),
        "stages": steps,
        "applications": applications,
        "follow_ups": followups,
        "delivery_receipts": receipts,
        "blockers": blockers,
        "status": "blocked" if blockers else "confirmed",
        "privacy": {"redacted": True, "content_bodies": False, "contact_data": False},
    }
    if write_receipt:
        path = _receipt_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            result["receipt_path"] = str(path)
        except OSError:
            result["blockers"].append("daily receipt could not be written")
            result["status"] = "blocked"
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the bounded daily communications/application loop")
    parser.add_argument("--fire", action="store_true", help="arm routine professional applications/follow-ups for this invocation")
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
