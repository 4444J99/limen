"""Durable human-gate registry corrections that must survive formatting rewrites."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_arca_key_escrow_gate_has_one_canonical_owner_receipt():
    registry = json.loads((ROOT / "his-hand-levers.json").read_text(encoding="utf-8"))
    rows = [row for row in registry["levers"] if row.get("id") == "L-ARCA-KEY-ESCROW"]

    assert len(rows) == 1
    assert rows[0]["issue"] == 719
    assert rows[0]["owner"] == "yours"
    assert rows[0]["source_task"] == "ARCA build 2026-07-08"


def test_tcc_app_management_cutover_stays_open_for_real_vendor_update():
    """The lever's status is DERIVED, never a version-pinned claim written into it.

    This test previously asserted the opposite — `status == "discharged"` with
    `discharged.version == "2.1.222"` — added by bd33c1ce, whose subject was
    "align his-hand discharge test with discharged lever". The test was edited to
    match the lever instead of the lever being held to the test, and its own NAME
    (`stays_open_for_real_vendor_update`) is the surviving record of the contract
    that was overwritten.

    #1833 then re-pinned that discharge to an IMMUTABLE timestamped receipt,
    correctly fixing a separate defect (latest_met_receipt() reverse-globbed to the
    beat-rewritten closeout-latest.json alias, which flipped to blocked under the
    lever's own pointer). That invariant is preserved below — it now guards the
    RETRACTED discharge. But the evidence it pins is itself vacuous: the receipt
    records `automatic_updates_enabled: true` while `autoUpdates` was false in both
    .claude.json roots, because `_disabled_updates()` never read that field. With
    updates off the version could not advance — `update_attempted: false`,
    version_before == version_after. See docs/IDEAL-FORMS-LEDGER.md → IF-AGENT-IDENTITY.
    """
    registry = json.loads((ROOT / "his-hand-levers.json").read_text(encoding="utf-8"))
    rows = [row for row in registry["levers"] if row.get("id") == "L-DOMUS-AGENT-HOST-TCC"]

    assert len(rows) == 1
    row = rows[0]
    assert row["issue"] == 1703
    assert row["owner"] == "engineering"
    assert row["status"] == "open"
    assert "discharged" not in row

    # The status lives in the ideal-forms registry, where there is no field to lie in.
    assert "IF-AGENT-IDENTITY" in row["derived_status"]
    ideals = (ROOT / "institutio/governance/ideal-forms.yaml").read_text(encoding="utf-8")
    assert "IF-AGENT-IDENTITY:" in ideals

    # #1833's invariant, retained: the retracted discharge still cites an IMMUTABLE
    # timestamped receipt whose met flag is true on disk — never the mutable alias.
    retracted = row["retracted_discharge"]
    assert retracted["version"] == "2.1.222"
    assert retracted["retracted_at"] == "2026-08-05"
    receipt_rel = retracted["receipt"]
    assert receipt_rel != "docs/receipts/tcc-track-c-1703/closeout-latest.json"
    receipt_path = ROOT / receipt_rel
    assert receipt_path.name.startswith("closeout-2")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["track_c"]["met"] is True

    # ...and that receipt is exactly why the discharge was retracted: it claims
    # updates were enabled, and records that no update was ever attempted.
    assert receipt["normalized_inventory"]["automatic_updates_enabled"] is True
    assert receipt["track_c"]["update_attempted"] is False
    assert receipt["track_c"]["version_before"] == receipt["track_c"]["version_after"]

    # The remaining distance is named, and the operator's atom is one click — not one per version.
    assert "macOS TCC" in row["gate"]
    assert any("Open (operator" in step for step in row["steps"])
    assert any("Open (engineering" in step for step in row["steps"])


def test_tcc_versioned_client_leak_lever_owns_post_discharge_regression():
    registry = json.loads((ROOT / "his-hand-levers.json").read_text(encoding="utf-8"))
    rows = [row for row in registry["levers"] if row.get("id") == "L-TCC-VERSIONED-CLIENT-LEAK-2-1-222"]

    assert len(rows) == 1
    assert rows[0]["owner"] == "yours"
    assert rows[0]["issue"] == 1703
    assert any("domus-agent-host run --" in step for step in rows[0]["steps"])
    # The lever must name the audit INSTRUMENT so the operator can verify the removal — that is
    # the invariant, and it holds. What this line used to pin was a SPELLING: `tcc-identity-audit.py`.
    # #1864 rewrote the verify step to `scripts/tcc-identity-audit --strict`, the POSIX wrapper
    # that execs the same module and additionally handles the no-python3 and non-Darwin cases the
    # bare module does not — a strictly better citation, and the test went red on it.
    # Pin the path both spellings share, so choosing the wrapper or the module is free and a lever
    # that stops naming the instrument at all still fails here.
    audit = "scripts/tcc-identity-audit"
    assert (ROOT / audit).exists(), "the cited instrument must exist on disk, not merely be spelled"
    assert any(audit in step for step in rows[0]["steps"])
