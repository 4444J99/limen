from __future__ import annotations

import json
import subprocess

from limen import notification_effect


EVENT = {
    "event_id": "evt-1",
    "transition": "onset",
    "subject_key": "probe",
    "observed_at": "2026-08-25T12:00:00Z",
    "stable_id": "limen.heartbeat.finding",
    "facts": {"probe": "probe"},
    "evidence_ref": "heartbeat-observation:abc",
    "producer": "limen.heartbeat",
    "owner": "limen",
}


def test_disabled_effect_short_circuits_before_broker_spawn(tmp_path, monkeypatch):
    monkeypatch.setattr(
        notification_effect.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("broker spawned")),
    )

    receipt = notification_effect.emit_notification_event(
        EVENT,
        registry=tmp_path / "registry.json",
        enabled=False,
    )

    assert receipt.status == "withheld"
    assert receipt.broker_invoked is False
    assert receipt.accepted is False


def test_domus_v2_submitted_receipt_is_accepted(tmp_path, monkeypatch):
    payload = {
        "schema": "domus.notification_delivery_receipt.v2",
        "status": "submitted",
        "channels": {"macos": "submitted", "ntfy": "submitted"},
    }
    monkeypatch.setattr(
        notification_effect.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, 0, json.dumps(payload), ""),
    )

    receipt = notification_effect.emit_notification_event(
        EVENT,
        registry=tmp_path / "registry.json",
        enabled=True,
        broker="domus-notify",
    )

    assert receipt.status == "submitted"
    assert receipt.broker_schema == "domus.notification_delivery_receipt.v2"
    assert receipt.channels == {"macos": "submitted", "ntfy": "submitted"}
    assert receipt.accepted is True


def test_legacy_delivered_receipt_is_only_submitted_unverified():
    receipt = notification_effect.normalize_broker_receipt(
        {"status": "delivered", "channels": {"macos": "delivered"}},
        stable_id="limen.heartbeat.finding",
        event_id="evt-legacy",
    )

    assert receipt.status == "submitted_unverified"
    assert receipt.channels == {"macos": "submitted_unverified"}
    assert receipt.accepted is True
