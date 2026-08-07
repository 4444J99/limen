"""Tests for the per-lane session-opening floor census (F6 of the 2026-08-07 cadence-guard arc).

The operator's framing was "all providers, not just Claude": the Claude cadence had three
enforcement layers while `~/.codex/config.toml` sat at `ultra` effort and `~/.gemini/settings.json`
declared no model at all — both facts reachable only by hand, because no predicate could read them.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import limen.census as C
import limen.model_selection as M

ROOT = Path(__file__).resolve().parents[2]


def _script():
    path = ROOT / "scripts" / "session-opening-floor.py"
    spec = importlib.util.spec_from_file_location("_sof_under_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_sof_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_every_vendor_declares_an_opening_floor():
    """Completeness against the canonical register. A new vendor must land RED rather than
    silently inheriting 'no cadence applies' — the self-surfacing shape armed-valve-audit's
    UNCLASSIFIED uses, so the registry can never quietly lag the register."""
    assert C.undeclared_opening_floors() == (), C.undeclared_opening_floors()
    assert set(C.OPENING_FLOORS) == {v.name for v in C.VENDORS}


def test_no_opening_floor_row_is_a_bare_na():
    """Rule #1: an N/A is a vacuum, never a resting state. Every row states a REASON."""
    allowed = {"config-file", "hook-armed", "unresolved", "not-interactive", "not-metered"}
    for name, floor in C.OPENING_FLOORS.items():
        assert floor.kind in allowed, f"{name} has an unclassified kind {floor.kind!r}"
        assert floor.note or floor.kind == "config-file", f"{name} states no reason"
        if floor.kind == "config-file":
            assert floor.config_path and floor.pointer, f"{name} declares no readable location"
            assert floor.ladder or floor.ladder_ref, f"{name} declares no ladder"
        if floor.kind == "hook-armed":
            # Design decision D8: exactly ONE reader of settings.json arming state. A hook-armed
            # row delegates by valve id; it must never carry its own probe.
            assert floor.arming_valve, f"{name} is hook-armed but delegates to no valve"


def test_hook_armed_rows_delegate_to_a_classified_valve():
    """The delegate target must actually exist in the armed-valve registry, or the row silently
    reports nothing — the exact 'declared but unwired' class this estate already has a precedent
    for (PREC-2026-07-10-declared-but-unwired-is-a-defect)."""
    registry = json.loads((ROOT / "spec" / "armed-valves.json").read_text())
    known = {e.get("id") for e in registry.get("deliverable", [])}
    for name, floor in C.OPENING_FLOORS.items():
        if floor.kind == "hook-armed":
            assert floor.arming_valve in known, f"{name} delegates to unclassified valve {floor.arming_valve}"


def test_opening_verdict_caps_within_the_LADDER_IT_WAS_GIVEN():
    """THE BUG the first census run found. `_cap_tier` hardcodes the Claude ladder and its
    unknown-value fallback (haiku), so a codex ceiling of 'high' came back as 'haiku' — an
    unclassifiable value resolving to the cheapest rung, which is this arc's own defect wearing a
    different hat."""
    codex = ("minimal", "low", "medium", "high", "ultra")
    v = M.opening_verdict("ultra", "high", codex)
    assert v["ceiling"] == "high", v
    assert v["state"] == "above-ceiling", v
    assert v["rung"] == "ultra", v

    ok = M.opening_verdict("medium", "high", codex)
    assert ok["state"] == "ok" and ok["ceiling"] == "high", ok


def test_opening_verdict_hard_caps_fable_only_on_the_claude_ladder():
    """No declaration may make Fable an acceptable OPENING default (it is reserved behind a
    written receipt); a foreign ladder has no equivalent reserved rung, so its top is usable."""
    assert M.opening_verdict("claude-fable-5", "fable")["ceiling"] == "opus"
    codex = ("minimal", "low", "medium", "high", "ultra")
    assert M.opening_verdict("ultra", "ultra", codex)["ceiling"] == "ultra"


def test_rung_of_is_dearest_first_and_says_when_it_cannot_classify():
    assert M._rung_of("claude-opus-5") == "opus"
    assert M._rung_of("claude-3-5-haiku-20241022") == "haiku"
    # Ambiguous strings fail toward caution, never toward the cheap reading.
    assert M._rung_of("sonnet-with-opus-fallback") == "opus"
    # Unclassifiable is "" — an explicit "I cannot place this", never the cheapest rung.
    assert M._rung_of("some-other-vendor-model-9") == ""


def test_read_pin_is_provider_neutral(tmp_path):
    """One probe for json and toml alike — no per-vendor branch."""
    sof = _script()

    j = tmp_path / "settings.json"
    j.write_text(json.dumps({"model": "flash-2"}))
    assert sof._read_pin(j, "model") == ("flash-2", "")

    t = tmp_path / "config.toml"
    t.write_text('model = "gpt-5.6-sol"\nmodel_reasoning_effort = "ultra"\n')
    assert sof._read_pin(t, "model_reasoning_effort") == ("ultra", "")

    # A missing key is UNSET with a reason — never a value, and never assumed cheap.
    value, detail = sof._read_pin(j, "nope")
    assert value is None and "nope" in detail

    # An absent file and an unreadable one are distinct findings.
    value, detail = sof._read_pin(tmp_path / "gone.json", "model")
    assert value is None and "absent" in detail
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json")
    value, detail = sof._read_pin(bad, "model")
    assert value is None and "unreadable" in detail


def test_ladder_ref_resolves_to_live_code_not_a_snapshot():
    """The Claude ladder must not be re-typed in the census, or it can drift from the real one."""
    sof = _script()
    floor = C.OPENING_FLOORS["claude"]
    assert floor.ladder == (), "the claude row must reference the ladder, never copy it"
    assert sof._resolve_ladder(floor, M) == M._CLAUDE_TIER_ORDER


def test_check_mode_fails_only_on_uncited_breaches_and_undeclared_lanes():
    """A breach the lever owns is PARKED (exit 0); an uncited one is red. Same owned-vs-dropped
    distinction armed-valve-audit draws, so a filed atom never holds a gate hostage."""
    sof = _script()
    rows = sof.rows(levers_text="L-LANE-OPENING-FLOOR", registry_path=ROOT / "spec" / "armed-valves.json")
    assert not [r for r in rows if r["verdict"] == "UNDECLARED"], rows
    assert not [r for r in rows if r["verdict"] == "ABOVE-CEILING"], "a cited breach must report PARKED"

    uncited = sof.rows(levers_text="", registry_path=ROOT / "spec" / "armed-valves.json")
    # Every row still classifies; nothing silently disappears when the lever text is empty.
    assert len(uncited) == len(rows)
    assert all(r.get("verdict") for r in uncited)
