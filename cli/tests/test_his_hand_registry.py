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
    registry = json.loads((ROOT / "his-hand-levers.json").read_text(encoding="utf-8"))
    rows = [row for row in registry["levers"] if row.get("id") == "L-DOMUS-AGENT-HOST-TCC"]

    assert len(rows) == 1
    assert rows[0]["issue"] == 1703
    assert rows[0]["status"] == "discharged"
    assert "discharged" in rows[0]
    assert rows[0]["discharged"]["version"] == "2.1.222"

    # The discharge must pin an IMMUTABLE timestamped receipt whose met flag is
    # true on disk — never the closeout-latest.json alias, which the beat
    # rewrites and which later flipped to blocked under it (2026-08-05).
    receipt_rel = rows[0]["discharged"]["receipt"]
    assert receipt_rel != "docs/receipts/tcc-track-c-1703/closeout-latest.json"
    receipt_path = ROOT / receipt_rel
    assert receipt_path.name.startswith("closeout-2")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["track_c"]["met"] is True
    assert receipt["track_c"]["version_after"] == "2.1.222"

    assert rows[0]["owner"] == "engineering"
    assert "external vendor availability" in rows[0]["gate"]
    assert any("zero App Management path rows" in step for step in rows[0]["steps"])


def test_tcc_versioned_client_leak_lever_owns_post_discharge_regression():
    registry = json.loads((ROOT / "his-hand-levers.json").read_text(encoding="utf-8"))
    rows = [row for row in registry["levers"] if row.get("id") == "L-TCC-VERSIONED-CLIENT-LEAK-2-1-222"]

    assert len(rows) == 1
    assert rows[0]["owner"] == "yours"
    assert rows[0]["issue"] == 1703
    assert any("domus-agent-host run --" in step for step in rows[0]["steps"])
    assert any("tcc-identity-audit.py" in step for step in rows[0]["steps"])
