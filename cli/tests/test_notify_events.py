"""Tests for the push notifier (scripts/notify-events.py).

Regression pin for the 2026-07-09 notification storm: four revenue-ladder products share
repo organvm/limen, and a state dict keyed by bare repo let them overwrite each other every
beat — so one product's 'deploy-ready' compared against a sibling's 'building' and re-fired
the same YOUR MOVE push on every heartbeat. State must be keyed per product, migrate quietly
from the old bare-repo format, and re-runs must be a fixed point (no events).
"""

import importlib.util
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "notify-events.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("notify_events", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _setup(tmp_path, monkeypatch, products, state=None, ships_24h=None):
    mod = _load_module()
    view = tmp_path / "money-view.json"
    state_path = tmp_path / ".notify-state.json"
    payload = {"products": products}
    if ships_24h is not None:
        payload["ships_24h"] = ships_24h
    view.write_text(json.dumps(payload))
    if state is not None:
        state_path.write_text(json.dumps(state))
    monkeypatch.setattr(mod, "VIEW", view)
    monkeypatch.setattr(mod, "STATE", state_path)
    emitted = []
    monkeypatch.setattr(
        mod,
        "_emit",
        lambda title, msg, *, stable_id: (
            emitted.append((title, msg, stable_id)) or SimpleNamespace(status="emitted", reserved=True)
        ),
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


def test_same_display_payload_from_distinct_products_has_distinct_event_identity(tmp_path, monkeypatch):
    products = [
        {"repo": "organvm/one", "product": "Launch", "stage": "live", "whose_hand": "fleet"},
        {"repo": "organvm/two", "product": "Launch", "stage": "live", "whose_hand": "fleet"},
    ]
    state = {"stages": {f"{product['repo']}::Launch": "building" for product in products}}
    mod, emitted, _ = _setup(tmp_path, monkeypatch, products, state=state)

    assert mod.main() == 0
    assert len(emitted) == 2
    assert emitted[0][:2] == emitted[1][:2]
    assert {event[2] for event in emitted} == {
        "organvm/one::Launch@live",
        "organvm/two::Launch@live",
    }


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
        lambda *_args, **_kwargs: SimpleNamespace(status="withheld", reserved=False),
    )

    assert mod.main() == 0
    assert json.loads(state_path.read_text(encoding="utf-8")) == state


def test_ship_milestone_fires_on_new_bucket_then_quiet(tmp_path, monkeypatch):
    """Regression pin for the 2026-08-15 blackout: money-view.py now feeds ships_24h.total from a
    real gh-backed cache (scripts/_ships_24h.py) instead of the always-zero merge-drain.log scrape.
    Crossing a SHIP_BUCKETS threshold must fire exactly once, then go quiet at a fixed point."""
    state = {"stages": {f"organvm/limen::{p['product']}": p["stage"] for p in PRODUCTS}}
    mod, emitted, state_path = _setup(
        tmp_path, monkeypatch, PRODUCTS, state=state, ships_24h={"total": 63, "by_repo": {}, "recent": []}
    )
    mod.main()
    assert len(emitted) == 1
    assert emitted[0][0] == "LIMEN shipping"
    assert "63 PRs shipped" in emitted[0][1]

    emitted.clear()
    mod.main()  # fixed point: same ships_24h feed, same day -> no re-fire
    assert emitted == []
    assert json.loads(state_path.read_text())["ship_bucket"] == 50  # max(b for b in [10,25,50,100] if 63>=b)


def test_ship_milestone_refires_on_higher_bucket_same_day(tmp_path, monkeypatch):
    state = {
        "stages": {f"organvm/limen::{p['product']}": p["stage"] for p in PRODUCTS},
        "ship_bucket": 50,
        "ship_date": datetime.now().strftime("%Y-%m-%d"),
    }
    mod, emitted, _ = _setup(
        tmp_path, monkeypatch, PRODUCTS, state=state, ships_24h={"total": 144, "by_repo": {}, "recent": []}
    )
    mod.main()
    assert len(emitted) == 1
    assert "144 PRs shipped" in emitted[0][1]


def test_ship_milestone_no_fire_below_first_bucket(tmp_path, monkeypatch):
    state = {"stages": {f"organvm/limen::{p['product']}": p["stage"] for p in PRODUCTS}}
    mod, emitted, _ = _setup(
        tmp_path, monkeypatch, PRODUCTS, state=state, ships_24h={"total": 5, "by_repo": {}, "recent": []}
    )
    mod.main()
    assert emitted == []


def test_duplicate_event_allows_source_state_to_advance(tmp_path, monkeypatch):
    state = {"stages": {f"organvm/limen::{p['product']}": "building" for p in PRODUCTS}}
    mod, _, state_path = _setup(tmp_path, monkeypatch, PRODUCTS, state=state)
    monkeypatch.setattr(
        mod,
        "_emit",
        lambda *_args, **_kwargs: SimpleNamespace(status="duplicate", reserved=False),
    )

    assert mod.main() == 0
    assert json.loads(state_path.read_text(encoding="utf-8"))["stages"]["organvm/limen::MONETA"] == "deploy-ready"
