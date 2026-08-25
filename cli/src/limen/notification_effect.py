"""Bounded NotificationEventV1 delivery through the machine-global Domus broker.

The adapter deliberately reports transport *submission*, not user-visible delivery.
Domus cannot prove that Notification Center or a remote ntfy client displayed an
accepted message, so legacy ``delivered`` receipts are retained only as the explicit
compatibility state ``submitted_unverified``.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Literal, Mapping


BROKER_RECEIPT_SCHEMA_V2 = "domus.notification_delivery_receipt.v2"
BrokerStatus = Literal[
    "submitted",
    "submitted_unverified",
    "deduped",
    "recorded",
    "withheld",
    "cleared",
    "failed",
]
ACCEPTED_BROKER_STATUSES = frozenset({"submitted", "submitted_unverified", "deduped", "recorded", "cleared"})


@dataclass(frozen=True)
class DeliveryReceipt:
    """Normalized broker result without overstating end-user delivery."""

    status: BrokerStatus
    stable_id: str
    event_id: str
    channels: dict[str, str]
    reason: str | None = None
    broker_schema: str | None = None
    broker_invoked: bool = True

    @property
    def accepted(self) -> bool:
        return self.status in ACCEPTED_BROKER_STATUSES


def notifications_enabled(enabled: bool | None, environ: Mapping[str, str] | None = None) -> bool:
    """Return the explicit effect gate before any broker process is created."""

    if enabled is not None:
        return enabled
    source = os.environ if environ is None else environ
    return source.get("LIMEN_NOTIFY", "1") not in {"0", "false", "False"}


def _normalized_channels(value: Any, *, legacy_delivered: bool) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, str] = {}
    for channel, status in value.items():
        if not isinstance(channel, str) or not isinstance(status, str):
            continue
        normalized[channel] = "submitted_unverified" if legacy_delivered and status == "delivered" else status
    return normalized


def normalize_broker_receipt(
    payload: Any,
    *,
    stable_id: str,
    event_id: str,
    broker_invoked: bool = True,
) -> DeliveryReceipt:
    """Normalize Domus v2 and the bounded legacy receipt vocabulary."""

    if not isinstance(payload, dict):
        return DeliveryReceipt(
            "failed",
            stable_id,
            event_id,
            {},
            "invalid Domus broker response",
            broker_invoked=broker_invoked,
        )
    schema_value = payload.get("schema")
    schema = schema_value if isinstance(schema_value, str) and schema_value else None
    raw_status = payload.get("status")
    if schema not in {None, BROKER_RECEIPT_SCHEMA_V2}:
        return DeliveryReceipt(
            "failed",
            stable_id,
            event_id,
            {},
            f"unsupported Domus broker receipt schema: {schema}",
            schema,
            broker_invoked,
        )
    legacy_delivered = raw_status == "delivered"
    status = "submitted_unverified" if legacy_delivered else raw_status
    allowed = {
        "submitted",
        "submitted_unverified",
        "deduped",
        "recorded",
        "withheld",
        "cleared",
        "failed",
    }
    if status not in allowed:
        status = "failed"
    reason = payload.get("reason")
    return DeliveryReceipt(
        status,  # type: ignore[arg-type]
        stable_id,
        event_id,
        _normalized_channels(payload.get("channels"), legacy_delivered=legacy_delivered),
        reason if isinstance(reason, str) else None,
        schema,
        broker_invoked,
    )


def emit_notification_event(
    event: Mapping[str, Any],
    *,
    registry: Path,
    enabled: bool | None = None,
    level: str | None = None,
    broker: str | None = None,
    environ: Mapping[str, str] | None = None,
    timeout_seconds: float = 15,
) -> DeliveryReceipt:
    """Submit one NotificationEventV1, or short-circuit before spawn when disabled."""

    stable_id = str(event.get("stable_id") or "")
    event_id = str(event.get("event_id") or "")
    source_env = dict(os.environ if environ is None else environ)
    if not notifications_enabled(enabled, source_env):
        return DeliveryReceipt(
            "withheld",
            stable_id,
            event_id,
            {},
            "notifications disabled",
            BROKER_RECEIPT_SCHEMA_V2,
            False,
        )
    executable = broker or source_env.get("DOMUS_NOTIFY_BIN", str(Path.home() / ".local" / "bin" / "domus-notify"))
    command = [executable, "emit", "--event-json", "-"]
    if level:
        command.extend(["--level", level])
    source_env["DOMUS_NOTIFY_REGISTRY"] = str(registry)
    if source_env.get("LIMEN_NTFY_TOPIC") and not source_env.get("DOMUS_NOTIFY_NTFY_URL"):
        base = source_env.get("LIMEN_NTFY_URL", "https://ntfy.sh").rstrip("/")
        source_env["DOMUS_NOTIFY_NTFY_URL"] = f"{base}/{source_env['LIMEN_NTFY_TOPIC']}"
    try:
        completed = subprocess.run(
            command,
            input=json.dumps(dict(event), sort_keys=True, separators=(",", ":")),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            env=source_env,
        )
        if completed.returncode != 0:
            return DeliveryReceipt(
                "failed",
                stable_id,
                event_id,
                {},
                f"Domus broker exited {completed.returncode}",
                broker_invoked=True,
            )
        try:
            payload = json.loads(completed.stdout or "{}")
        except ValueError:
            payload = None
        return normalize_broker_receipt(
            payload,
            stable_id=stable_id,
            event_id=event_id,
            broker_invoked=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return DeliveryReceipt(
            "failed",
            stable_id,
            event_id,
            {},
            f"Domus broker unavailable ({exc})",
            broker_invoked=True,
        )
