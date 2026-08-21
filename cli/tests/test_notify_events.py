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
    captured = {}
    monkeypatch.setattr(
        mod,
        "emit_event_v1",
        lambda *args, **kwargs: captured.update(kwargs) or SimpleNamespace(status="recorded"),
    )
    assert mod.main() == 0
    assert captured["stable_id"] == "limen.shipping.threshold"
    assert captured["facts"]["threshold"] == 10
    assert captured["facts"]["observed"] == 24
    assert "crossed 10; 24 observed at" in capsys.readouterr().out
    assert json.loads(state_path.read_text())["ship_bucket"] == 10
