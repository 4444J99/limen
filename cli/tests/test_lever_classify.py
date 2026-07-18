"""lever-classify.py — the sovereignty classifier + dissolution predicate.

Pins the invariant `no-tasks-on-me.sh` §11 relies on: every OPEN lever must be a
proven sovereignty boundary (irreducibly his) OR converted to design_debt (the
beat owes it). A bare/automatable lever must RED — his head is not a backlog.
Pure + offline (no registry file, no network).
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _mod():
    spec = importlib.util.spec_from_file_location("lever_classify", ROOT / "scripts" / "lever-classify.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _lever(**kw):
    base = {"id": "L-X", "label": "", "owner": "yours", "cost": "0", "unlocks": "u", "source_task": "t"}
    base.update(kw)
    return base


def test_derives_each_sovereignty_reason_from_prose():
    c = _mod().classify
    cases = {
        "a phone call only you can place to your bank (Santander fraud hold)": "bank",
        "escrow the ARCA vault key in Keychain Access": "wallet_custody",
        "mount an external backup drive and run migrate.sh": "physical_act",
        "grant Screen Recording via macOS TCC (GUI approval)": "device_grant",
        "run rclone authorize and OAuth-consent in the browser": "vendor_mint",
        "publish the launch post under your own name": "identity",
        "set LIMEN_OBSERVATORY=1 in ~/.limen.env (classifier-blocked for the agent)": "governance_choice",
    }
    for prose, want in cases.items():
        got = c(_lever(label=prose))
        assert got["kind"] == "sovereignty", f"{prose!r} -> {got}"
        assert got["reason"] == want, f"{prose!r} -> {got['reason']} (want {want})"


def test_fails_closed_on_prose_with_no_sovereignty_signal():
    # pure automatable work, no irreducible signal -> must NOT be waved through as his
    got = _mod().classify(_lever(label="run the nightly report generator and email the summary"))
    assert got["kind"] == "UNCLASSIFIED", got


def test_explicit_field_overrides_derivation():
    m = _mod()
    # explicit design_debt wins even when the prose would derive sovereignty ("your click")
    lev = _lever(label="your click to publish", design_debt={
        "organ": "scripts/apply-visibility.py", "status": "built",
        "dissolves_when": "true"})
    got = m.classify(lev)
    assert got["kind"] == "design_debt" and got["organ"].endswith("apply-visibility.py"), got
    # explicit sovereignty with a valid reason is honored
    got2 = m.classify(_lever(sovereignty={"reason": "biometric"}))
    assert got2["kind"] == "sovereignty" and got2["reason"] == "biometric" and got2["source"] == "explicit"


def test_check_reds_unclassified_and_malformed():
    m = _mod()
    good = _lever(id="L-GOOD", label="publish under your own name")
    bad_unc = _lever(id="L-UNC", label="regenerate and email the report")
    bad_reason = _lever(id="L-BADR", sovereignty={"reason": "vibes"})
    bad_dd = _lever(id="L-BADDD", label="x", design_debt={"organ": "scripts/x.py"})  # no dissolves_when
    assert m.cmd_check([good]) == 0
    assert m.cmd_check([good, bad_unc]) == 1
    assert m.cmd_check([bad_reason]) == 1
    assert m.cmd_check([bad_dd]) == 1


def test_discharged_levers_are_skipped():
    m = _mod()
    # a discharged (pulled) lever is not OPEN, so it never needs classification
    dead = _lever(id="L-DEAD", label="regenerate and email the report", discharged="2026-07-18 done")
    assert m.is_open(dead) is False
    assert m.cmd_check([dead]) == 0


def test_every_sovereign_reason_is_a_boundary_not_a_task():
    # guards against a reason being renamed/removed without updating the enum contract
    m = _mod()
    assert m.SOVEREIGN_REASONS == {
        "identity", "bank", "wallet_custody", "legal_body", "biometric",
        "vendor_mint", "physical_act", "device_grant", "governance_choice",
    }
