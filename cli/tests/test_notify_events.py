"""Tests for the push notifier (scripts/notify-events.py).

Regression pin for the 2026-07-09 notification storm: four revenue-ladder products share
repo organvm/limen, and a state dict keyed by bare repo let them overwrite each other every
beat — so one product's 'deploy-ready' compared against a sibling's 'building' and re-fired
the same YOUR MOVE push on every heartbeat. State must be keyed per product, migrate quietly
from the old bare-repo format, and re-runs must be a fixed point (no events).
"""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

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
    assert mod.main() == 0
    assert emitted == []


def test_state_is_keyed_per_product(tmp_path, monkeypatch):
    mod, _, state_path = _setup(tmp_path, monkeypatch, PRODUCTS, state={"stages": {}})
    mod.main()
    stages = json.loads(state_path.read_text())["stages"]
    assert stages["organvm/limen::MONETA"] == "deploy-ready"
    assert stages["organvm/limen::Enactment Audit"] == "building"


def test_genuine_transition_fires_exactly_once_then_quiet(tmp_path, monkeypatch):
    state = {"stages": {f"organvm/limen::{p['product']}": "building" for p in PRODUCTS}}
    mod, emitted, _ = _setup(tmp_path, monkeypatch, PRODUCTS, state=state)
    mod.main()
    assert len(emitted) == 1
    assert "YOUR MOVE" in emitted[0][0] and "MONETA" in emitted[0][1]
    emitted.clear()
    mod.main()  # fixed point: identical feed, no events
    assert emitted == []


def test_first_run_with_no_state_is_quiet(tmp_path, monkeypatch):
    mod, emitted, _ = _setup(tmp_path, monkeypatch, PRODUCTS, state=None)
    assert mod.main() == 0
    assert emitted == []


def test_unreserved_event_does_not_advance_source_state(tmp_path, monkeypatch):
    state = {"stages": {f"organvm/limen::{p['product']}": "building" for p in PRODUCTS}}
    mod, _, state_path = _setup(tmp_path, monkeypatch, PRODUCTS, state=state)
    monkeypatch.setattr(
        mod,
        "_emit",
        lambda *_args: SimpleNamespace(status="withheld", reserved=False),
    )

    assert mod.main() == 0
    assert json.loads(state_path.read_text(encoding="utf-8")) == state


def test_duplicate_event_allows_source_state_to_advance(tmp_path, monkeypatch):
    state = {"stages": {f"organvm/limen::{p['product']}": "building" for p in PRODUCTS}}
    mod, _, state_path = _setup(tmp_path, monkeypatch, PRODUCTS, state=state)
    monkeypatch.setattr(
        mod,
        "_emit",
        lambda *_args: SimpleNamespace(status="duplicate", reserved=False),
    )

    assert mod.main() == 0
    assert json.loads(state_path.read_text(encoding="utf-8"))["stages"]["organvm/limen::MONETA"] == "deploy-ready"


def test_shipping_24_crosses_10_with_truthful_observation(tmp_path, monkeypatch, capsys):
    mod, _, state_path = _setup(tmp_path, monkeypatch, [], state={"stages": {}, "ship_bucket": 0})
    mod.VIEW.write_text(json.dumps({"products": [], "ships_24h": {"total": 24}}))
    monkeypatch.setattr(mod, "read_ships_24h", lambda _root: (24, {}, []))
    captured = []
    monkeypatch.setattr(
        mod,
        "emit_event_v1",
        lambda *args, **kwargs: captured.append(kwargs) or SimpleNamespace(status="recorded"),
    )
    assert mod.main() == 0
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
    assert payload["census"]["counts"] is None
    assert payload["census"]["count_display"] == "count unavailable/incomplete"
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

    assert status["state"] == "incomplete"
    progress = next(spec for spec in specs if spec["stable_id"] == "limen.estate.progress")
    assert progress["facts"]["stable_repositories"] == "count unavailable/incomplete"
    assert progress["facts"]["open_or_blocked_prs"] == "count unavailable/incomplete"


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
    monkeypatch.setattr(mod, "read_ships_24h", lambda _root: (12, {}, []))
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
