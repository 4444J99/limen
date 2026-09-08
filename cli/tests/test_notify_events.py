"""Tests for the push notifier (scripts/notify-events.py).

Regression pin for the 2026-07-09 notification storm: four revenue-ladder products share
repo organvm/limen, and a state dict keyed by bare repo let them overwrite each other every
beat — so one product's 'deploy-ready' compared against a sibling's 'building' and re-fired
the same YOUR MOVE push on every heartbeat. State must be keyed per product, migrate quietly
from the old bare-repo format, and re-runs must be a fixed point (no events).
"""

import importlib.util
import json
import subprocess
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "notify-events.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("notify_events", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _setup(tmp_path, monkeypatch, products, state=None):
    mod = _load_module()
    view = tmp_path / "money-view.json"
    state_path = tmp_path / ".notify-state.json"
    view.write_text(json.dumps({"products": products}))
    if state is not None:
        state_path.write_text(json.dumps(state))
    monkeypatch.setattr(mod, "VIEW", view)
    monkeypatch.setattr(mod, "STATE", state_path)
    monkeypatch.setattr(mod, "BASELINE", tmp_path / "missing-baseline.json")
    emitted = []
    monkeypatch.setattr(
        mod,
        "_emit",
        lambda title, msg: emitted.append((title, msg)) or SimpleNamespace(status="emitted", reserved=True),
    )
    return mod, emitted, state_path


PRODUCTS = [
    {"repo": "organvm/limen", "product": "PR-Repair Factory", "stage": "building", "whose_hand": "fleet"},
    {
        "repo": "organvm/limen",
        "product": "MONETA",
        "stage": "deploy-ready",
        "whose_hand": "yours",
        "next_action": "deploy",
    },
    {"repo": "organvm/limen", "product": "Enactment Audit", "stage": "building", "whose_hand": "fleet"},
]


def test_old_bare_repo_state_migrates_without_refiring(tmp_path, monkeypatch):
    """The storm scenario: old state keyed by bare repo must NOT look like a transition."""
    mod, emitted, _ = _setup(tmp_path, monkeypatch, PRODUCTS, state={"stages": {"organvm/limen": "building"}})
    assert mod.main(["--apply"]) == 0
    assert emitted == []


def test_state_is_keyed_per_product(tmp_path, monkeypatch):
    mod, _, state_path = _setup(tmp_path, monkeypatch, PRODUCTS, state={"stages": {}})
    mod.main(["--apply"])
    stages = json.loads(state_path.read_text())["stages"]
    assert stages["organvm/limen::MONETA"] == "deploy-ready"
    assert stages["organvm/limen::Enactment Audit"] == "building"


def test_genuine_transition_fires_exactly_once_then_quiet(tmp_path, monkeypatch):
    state = {"stages": {f"organvm/limen::{p['product']}": "building" for p in PRODUCTS}}
    mod, emitted, _ = _setup(tmp_path, monkeypatch, PRODUCTS, state=state)
    mod.main(["--apply"])
    assert len(emitted) == 1
    assert "YOUR MOVE" in emitted[0][0] and "MONETA" in emitted[0][1]
    emitted.clear()
    mod.main(["--apply"])  # fixed point: identical feed, no events
    assert emitted == []


def test_first_run_with_no_state_is_quiet(tmp_path, monkeypatch):
    mod, emitted, _ = _setup(tmp_path, monkeypatch, PRODUCTS, state=None)
    assert mod.main(["--apply"]) == 0
    assert emitted == []


def test_unreserved_event_does_not_advance_source_state(tmp_path, monkeypatch):
    state = {"stages": {f"organvm/limen::{p['product']}": "building" for p in PRODUCTS}}
    mod, _, state_path = _setup(tmp_path, monkeypatch, PRODUCTS, state=state)
    monkeypatch.setattr(
        mod,
        "_emit",
        lambda *_args: SimpleNamespace(status="withheld", reserved=False),
    )

    assert mod.main(["--apply"]) == 0
    assert json.loads(state_path.read_text(encoding="utf-8")) == state


def test_duplicate_event_allows_source_state_to_advance(tmp_path, monkeypatch):
    state = {"stages": {f"organvm/limen::{p['product']}": "building" for p in PRODUCTS}}
    mod, _, state_path = _setup(tmp_path, monkeypatch, PRODUCTS, state=state)
    monkeypatch.setattr(
        mod,
        "_emit",
        lambda *_args: SimpleNamespace(status="duplicate", reserved=False),
    )

    assert mod.main(["--apply"]) == 0
    assert json.loads(state_path.read_text(encoding="utf-8"))["stages"]["organvm/limen::MONETA"] == "deploy-ready"


def test_shipping_24_crosses_10_with_truthful_observation(tmp_path, monkeypatch, capsys):
    mod, _, state_path = _setup(tmp_path, monkeypatch, [], state={"stages": {}, "ship_bucket": 0})
    mod.VIEW.write_text(json.dumps({"products": [], "ships_24h": {"total": 24}}))
    monkeypatch.setattr(
        mod,
        "read_ships_24h_status",
        lambda _root: {"available": True, "complete": True, "total": 24, "by_repo": {}, "recent": []},
    )
    captured = []
    monkeypatch.setattr(
        mod,
        "emit_event_v1",
        lambda *args, **kwargs: captured.append(kwargs) or SimpleNamespace(status="recorded"),
    )
    assert mod.main(["--apply"]) == 0
    shipping = next(row for row in captured if row["stable_id"] == "limen.shipping.threshold")
    assert shipping["facts"]["threshold"] == 10
    assert shipping["facts"]["observed"] == 24
    assert "crossed 10; 24 observed at" in capsys.readouterr().out
    assert json.loads(state_path.read_text())["ship_bucket"] == 10


def test_status_reports_missing_counts_and_absent_ntfy_as_configuration_state(tmp_path, monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "BASELINE", tmp_path / "missing-baseline.json")
    monkeypatch.setattr(mod, "CANARY_RECEIPT", tmp_path / "missing-canary.json")
    monkeypatch.delenv("LIMEN_NTFY_TOPIC", raising=False)

    payload = mod._status_payload()

    assert payload["census"]["status"] == "unavailable"
    assert payload["census"]["counts"]["stable_repositories"] is None
    assert payload["census"]["metrics"]["stable_repositories"]["complete"] is False
    assert payload["census"]["count_display"] == "per-metric completeness; null means unavailable/incomplete"
    assert payload["transports"]["ntfy"] == "not_configured"
    assert payload["transports"]["macos"] == "submission_only_visible_delivery_unverified"


def test_missing_baseline_still_emits_integrity_with_unavailable_counts(tmp_path, monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "BASELINE", tmp_path / "missing-baseline.json")

    status = mod._baseline_status()
    specs = mod._estate_event_specs(status)

    assert {row["stable_id"] for row in specs} == {
        "limen.estate.integrity",
        "limen.estate.progress",
    }
    progress = next(row for row in specs if row["stable_id"] == "limen.estate.progress")
    assert progress["facts"]["total_repositories"] == "count unavailable/incomplete"
    integrity = next(row for row in specs if row["stable_id"] == "limen.estate.integrity")
    assert integrity["transition"] == "onset"
    assert integrity["facts"]["census_status"] == "unavailable"


def test_partial_estate_event_never_translates_missing_counts_to_zero(tmp_path, monkeypatch):
    mod = _load_module()
    from limen.universe_recovery import UniverseBaselineReceiptV1, UniversePartitionV1

    kinds = (
        "repositories",
        "pull_requests",
        "branches",
        "local_roots",
        "worktrees",
        "protections",
        "terminal_dispositions",
    )
    partitions = []
    for kind in kinds:
        if kind == "repositories":
            partitions.append(
                UniversePartitionV1(
                    kind=kind, total=2, terminal=1, protected=0, blocked=1, unaccounted=0, complete=True
                )
            )
        else:
            partitions.append(
                UniversePartitionV1(
                    kind=kind, total=0, terminal=0, protected=0, blocked=0, unaccounted=0, complete=True
                )
            )
    receipt = UniverseBaselineReceiptV1(
        observed_at="2026-08-27T12:00:00Z",
        source_generation="1" * 64,
        census_digest="2" * 64,
        repository_denominator=2,
        stable_count=1,
        partitions=tuple(partitions),
        failure_count=1,
        unaccounted=0,
        complete=False,
    )
    baseline = tmp_path / "baseline.json"
    baseline.write_text(receipt.model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(mod, "BASELINE", baseline)

    status = mod._baseline_status(now=receipt.observed_at)
    specs = mod._estate_event_specs(status)

    assert status["state"] == "incomplete-observation"
    progress = next(spec for spec in specs if spec["stable_id"] == "limen.estate.progress")
    assert progress["facts"]["stable_repositories"] == 1
    assert progress["facts"]["open_or_blocked_prs"] == 0


def test_canary_receipt_separates_submission_from_visible_acceptance(tmp_path, monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "CANARY_RECEIPT", tmp_path / "canary.json")
    monkeypatch.setattr(
        mod,
        "emit_event_v1",
        lambda *_args, **_kwargs: SimpleNamespace(
            status="submitted",
            channels={"macos": "submitted"},
            broker_invoked=True,
            reason=None,
        ),
    )

    assert mod._run_canary("macos") == 0
    payload = json.loads(mod.CANARY_RECEIPT.read_text(encoding="utf-8"))

    assert payload["broker_status"] == "submitted"
    assert payload["broker_accepted"] is True
    assert payload["recording_accepted"] is None
    assert payload["visible_acceptance"] == "pending_operator"
    assert payload["visible_observed_at"] is None
    assert mod.CANARY_RECEIPT.stat().st_mode & 0o777 == 0o600


def test_recording_canary_selects_recording_backend_and_verifies_event(tmp_path, monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "RECORDING_CANARY_RECEIPT", tmp_path / "recording-canary.json")
    monkeypatch.setattr(mod, "CANARY_RECORDING", tmp_path / "recording.jsonl")
    monkeypatch.setattr(mod, "CANARY_RECORDING_LEDGER", tmp_path / "recording-ledger.json")

    def fake_emit(*_args, **kwargs):
        environ = kwargs["environ"]
        assert environ["DOMUS_NOTIFY"] == "0"
        assert environ["DOMUS_NOTIFY_RECORDING"] == str(mod.CANARY_RECORDING)
        assert kwargs["transition"] == "milestone"
        assert kwargs["level"] == "normal"
        mod.CANARY_RECORDING.write_text(
            json.dumps({"event": {"event_id": kwargs["event_id"]}}) + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            status="recorded",
            channels={"macos": "recorded"},
            broker_invoked=True,
            reason=None,
        )

    monkeypatch.setattr(mod, "emit_event_v1", fake_emit)

    assert mod._run_canary("recording") == 0
    payload = json.loads(mod.RECORDING_CANARY_RECEIPT.read_text(encoding="utf-8"))

    assert payload["broker_status"] == "recorded"
    assert payload["recording_accepted"] is True
    assert payload["recording_evidence"] == str(mod.CANARY_RECORDING)


def test_recording_canary_refuses_receipt_without_recorded_event(tmp_path, monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "RECORDING_CANARY_RECEIPT", tmp_path / "recording-canary.json")
    monkeypatch.setattr(mod, "CANARY_RECORDING", tmp_path / "missing.jsonl")
    monkeypatch.setattr(mod, "CANARY_RECORDING_LEDGER", tmp_path / "recording-ledger.json")
    monkeypatch.setattr(
        mod,
        "emit_event_v1",
        lambda *_args, **_kwargs: SimpleNamespace(
            status="recorded",
            channels={"macos": "recorded"},
            broker_invoked=True,
            reason=None,
        ),
    )

    assert mod._run_canary("recording") == 1
    payload = json.loads(mod.RECORDING_CANARY_RECEIPT.read_text(encoding="utf-8"))
    assert payload["recording_accepted"] is False


def test_dry_run_never_invokes_an_effector_or_advances_state(tmp_path, monkeypatch, capsys):
    products = [dict(PRODUCTS[1], stage="live")]
    state = {"stages": {"organvm/limen::MONETA": "deploy-ready"}, "ship_bucket": 0}
    mod, _, state_path = _setup(tmp_path, monkeypatch, products, state=state)
    mod.VIEW.write_text(json.dumps({"products": products, "ships_24h": {"total": 12}}), encoding="utf-8")
    monkeypatch.setattr(
        mod,
        "read_ships_24h_status",
        lambda _root: {"available": True, "complete": True, "total": 12, "by_repo": {}, "recent": []},
    )
    monkeypatch.setattr(
        mod,
        "emit_event_v1",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("structured effector invoked")),
    )
    monkeypatch.setattr(
        mod,
        "_emit",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("legacy effector invoked")),
    )

    assert mod.main(["--dry-run"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["events"]
    assert any(row["stable_id"] == "limen.shipping.threshold" for row in payload["structured_events"])
    assert json.loads(state_path.read_text(encoding="utf-8")) == state


def test_canary_cli_requires_apply_before_any_effect(tmp_path, monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(
        mod,
        "_run_canary",
        lambda _mode: (_ for _ in ()).throw(AssertionError("canary effect invoked")),
    )

    assert mod.main(["--macos-canary"]) == 2


def test_confirmation_refuses_a_canary_the_broker_did_not_accept(tmp_path, monkeypatch):
    mod = _load_module()
    receipt = tmp_path / "canary.json"
    receipt.write_text(
        json.dumps(
            {
                "event_id": "notification-canary-macos-example",
                "mode": "macos",
                "broker_accepted": False,
                "visible_acceptance": "pending_operator",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "CANARY_RECEIPT", receipt)

    assert mod._confirm_macos_canary("notification-canary-macos-example") == 1
    assert json.loads(receipt.read_text(encoding="utf-8"))["visible_acceptance"] == "pending_operator"


def test_unavailable_shipping_cache_preserves_prior_bucket(tmp_path, monkeypatch):
    today = datetime.now().strftime("%Y-%m-%d")
    state = {"stages": {}, "ship_bucket": 50, "ship_date": today}
    mod, _, state_path = _setup(tmp_path, monkeypatch, [], state=state)
    monkeypatch.setattr(
        mod,
        "read_ships_24h_status",
        lambda _root: {"available": False, "complete": False, "reason": "cache-stale"},
    )
    monkeypatch.setattr(
        mod,
        "emit_event_v1",
        lambda *_args, **_kwargs: SimpleNamespace(status="recorded", accepted=True),
    )

    assert mod.main(["--apply"]) == 0
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["ship_bucket"] == 50
    assert payload["ship_date"] == today


@pytest.mark.parametrize("reserved", [False, True])
def test_legacy_delivery_failure_makes_the_one_shot_fail(tmp_path, monkeypatch, reserved):
    products = [dict(PRODUCTS[1], stage="live")]
    state = {"stages": {"organvm/limen::MONETA": "deploy-ready"}, "ship_bucket": 0}
    mod, _, state_path = _setup(tmp_path, monkeypatch, products, state=state)
    monkeypatch.setattr(
        mod,
        "read_ships_24h_status",
        lambda _root: {"available": False, "complete": False, "reason": "cache-unavailable"},
    )
    monkeypatch.setattr(
        mod,
        "emit_event_v1",
        lambda *_args, **_kwargs: SimpleNamespace(status="recorded", accepted=True),
    )
    result = mod.NotificationResult("delivery_failed", "event-key", "2026-09-08", "event-id", reserved)
    monkeypatch.setattr(mod, "_emit", lambda *_args: result)

    assert mod.main(["--apply"]) == 1
    if not reserved:
        assert json.loads(state_path.read_text(encoding="utf-8")) == state


@pytest.mark.parametrize("mode", [["--recording-canary"], ["--macos-canary"], ["--confirm-macos-canary", "event-id"]])
def test_canary_dry_run_overrides_apply_without_effects(tmp_path, monkeypatch, capsys, mode):
    mod = _load_module()
    receipt = tmp_path / "canary.json"
    receipt.write_text('{"existing":true}', encoding="utf-8")
    monkeypatch.setattr(mod, "CANARY_RECEIPT", receipt)

    def unexpected(*_args, **_kwargs):
        raise AssertionError("dry-run invoked a canary effector")

    monkeypatch.setattr(mod, "_run_canary", unexpected)
    monkeypatch.setattr(mod, "_confirm_macos_canary", unexpected)

    assert mod.main([*mode, "--apply", "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True
    assert receipt.read_text(encoding="utf-8") == '{"existing":true}'
    assert list(tmp_path.iterdir()) == [receipt]


def test_canary_reaches_broker_with_registered_renderable_transition(tmp_path, monkeypatch):
    mod = _load_module()
    import _notify

    monkeypatch.setattr(mod, "RECORDING_CANARY_RECEIPT", tmp_path / "canary.json")
    monkeypatch.setattr(mod, "CANARY_RECORDING", tmp_path / "recording.jsonl")
    monkeypatch.setattr(mod, "CANARY_RECORDING_LEDGER", tmp_path / "ledger.json")
    monkeypatch.setattr(_notify, "_enabled", lambda _enabled: True)
    monkeypatch.setattr(_notify, "_root_may_speak", lambda _root: True)
    captured = []

    def broker_edge(command, *, input, env, **_kwargs):
        event = json.loads(input)
        registry = json.loads(Path(env["DOMUS_NOTIFY_REGISTRY"]).read_text(encoding="utf-8"))
        definition = registry["events"][event["stable_id"]]
        # Domus deliberately withholds diagnostic transitions, and its renderer
        # falls back to the stable ID when no matching/default template exists.
        assert event["transition"] == "milestone"
        template = definition["templates"].get(event["transition"], "{stable_id}")
        message = template.format_map(event["facts"] | {"stable_id": event["stable_id"]})
        assert message.startswith("Notification recording canary submitted at ")
        assert env["DOMUS_NOTIFY"] == "0"
        captured.append(message)
        Path(env["DOMUS_NOTIFY_RECORDING"]).write_text(json.dumps({"event": event}) + "\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, json.dumps({"status": "recorded", "channels": {}}), "")

    monkeypatch.setattr(_notify.subprocess, "run", broker_edge)

    assert mod.main(["--recording-canary", "--apply"]) == 0
    assert len(captured) == 1
    receipt = json.loads(mod.RECORDING_CANARY_RECEIPT.read_text(encoding="utf-8"))
    assert receipt["broker_status"] == "recorded"
    assert receipt["recording_accepted"] is True


def test_legacy_and_structured_delivery_resolve_the_broker_parameter(tmp_path, monkeypatch):
    import _notify

    monkeypatch.setattr(_notify, "_root_may_speak", lambda _root: True)
    monkeypatch.setattr(_notify, "_enabled", lambda _enabled: True)
    monkeypatch.delenv("DOMUS_NOTIFY_BIN", raising=False)
    monkeypatch.setattr(
        _notify,
        "_PARAMS_MODULE",
        SimpleNamespace(
            _load_panel=lambda: {"DOMUS_NOTIFY_BIN": {"default": "/parameter/broker", "env": "DOMUS_NOTIFY_BIN"}}
        ),
    )
    commands = []

    def broker_edge(command, **_kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 9, '{"status":"submitted","channels":{"macos":"submitted"}}', "")

    monkeypatch.setattr(_notify.subprocess, "run", broker_edge)
    assert _notify._deliver("test", "test") is False
    receipt = _notify.emit_event_v1(
        tmp_path,
        stable_id="limen.notification.canary",
        transition="milestone",
        subject_key="test",
        event_id="test",
        facts={},
        evidence_ref="test",
        producer="test",
    )
    assert isinstance(receipt, _notify.DeliveryReceipt)
    assert receipt.status == "failed"
    assert commands[0][0] == commands[1][0] == "/parameter/broker"
    monkeypatch.setenv("DOMUS_NOTIFY_BIN", "/ambient/broker")
    assert _notify._broker_binary({}) == "/parameter/broker"
    assert _notify._broker_binary({"DOMUS_NOTIFY_BIN": "/explicit/broker"}) == "/explicit/broker"


def test_active_conditions_include_broker_ci_state_and_drop_cleared_ids(tmp_path, monkeypatch):
    import _notify

    ledger = tmp_path / "notification-ledger.json"
    monkeypatch.setenv("DOMUS_NOTIFY_LEDGER", str(ledger))
    monkeypatch.setenv("DOMUS_NOTIFY", "1")
    monkeypatch.setenv("DOMUS_NOTIFY_BACKEND", "live")
    monkeypatch.setattr(_notify, "_root_may_speak", lambda _root: False)
    _notify._save(tmp_path, {"legacy-onset": "observed"})
    state = {
        "schema_version": 1,
        "conditions": {
            "limen.ci.code_failure:main": {"active": True, "submitted_channels": ["macos"]},
            "limen.ci.quota:main": {"active": False},
            "foreign.alert:subject": {"active": True},
        },
    }
    ledger.write_text(json.dumps(state), encoding="utf-8")
    before = ledger.read_bytes()

    assert _notify.active_conditions(tmp_path) == ["legacy-onset", "limen.ci.code_failure"]
    assert ledger.read_bytes() == before
    state["conditions"]["limen.ci.code_failure:main"]["active"] = False
    ledger.write_text(json.dumps(state), encoding="utf-8")
    assert _notify.active_conditions(tmp_path) == ["legacy-onset"]


def test_recording_active_conditions_do_not_borrow_live_ledger(tmp_path, monkeypatch):
    import _notify

    live = tmp_path / "live.json"
    recording = tmp_path / "recording-ledger.json"
    live.write_text(
        json.dumps({"schema_version": 1, "conditions": {"limen.ci.code_failure:main": {"active": True}}}),
        encoding="utf-8",
    )
    recording.write_text(
        json.dumps({"schema_version": 1, "conditions": {"limen.ci.quota:main": {"active": True}}}), encoding="utf-8"
    )
    monkeypatch.setenv("DOMUS_NOTIFY", "0")
    monkeypatch.setenv("DOMUS_NOTIFY_RECORDING", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("DOMUS_NOTIFY_RECORDING_LEDGER", str(recording))
    monkeypatch.setenv("DOMUS_NOTIFY_LEDGER", str(live))

    assert _notify.active_conditions(tmp_path) == ["limen.ci.quota"]
