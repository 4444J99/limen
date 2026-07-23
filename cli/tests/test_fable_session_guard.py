"""Tests for scripts/fable-session-guard.py — the SessionStart guard that closes the interactive
Fable bypass. Clean no-op on a non-Fable model; hard-warn (exit 2) on Fable when over-cap or when
no live acceptance receipt is present.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / "scripts" / "fable-session-guard.py"


def _this_monday() -> str:
    now = datetime.now(UTC)
    return (now - timedelta(days=now.weekday())).date().isoformat()


def _run(payload: dict, env_extra: dict | None = None):
    env = {"PATH": os.environ.get("PATH", "")}
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )


def test_non_fable_model_is_noop(tmp_path):
    proc = _run({"model": "claude-opus-4-8"})
    assert proc.returncode == 0
    assert proc.stderr.strip() == ""


def test_fable_over_cap_hard_warns(tmp_path):
    bal = tmp_path / "fable-allotment.json"
    bal.write_text(
        json.dumps(
            {
                "week": _this_monday(),
                "spent_pct": 100.0,
                "deliberate_cap": 40,
                "hard_cap": 50,
                "over_cap": True,
            }
        )
    )
    proc = _run({"model": "claude-fable-5"}, {"LIMEN_FABLE_BALANCE_PATH": str(bal)})
    assert proc.returncode == 2
    assert "HARD WARNING" in proc.stderr
    assert "/model" in proc.stderr


def test_fable_no_receipt_hard_warns_even_under_cap(tmp_path):
    bal = tmp_path / "fable-allotment.json"
    bal.write_text(
        json.dumps(
            {
                "week": _this_monday(),
                "spent_pct": 5.0,
                "deliberate_cap": 40,
                "hard_cap": 50,
                "over_cap": False,
            }
        )
    )
    proc = _run({"model": "claude-fable-5"}, {"LIMEN_FABLE_BALANCE_PATH": str(bal)})
    assert proc.returncode == 2  # under cap but no live acceptance receipt
    assert "HARD WARNING" in proc.stderr


def test_fable_under_cap_with_receipt_is_clean(tmp_path):
    bal = tmp_path / "fable-allotment.json"
    bal.write_text(
        json.dumps(
            {
                "week": _this_monday(),
                "spent_pct": 5.0,
                "deliberate_cap": 40,
                "hard_cap": 50,
                "over_cap": False,
            }
        )
    )
    receipt = tmp_path / "accept.json"
    receipt.write_text(
        json.dumps({"schema": "limen.fable_acceptance.v1", "week": _this_monday(), "category": "governance"})
    )
    proc = _run(
        {"model": "claude-fable-5"},
        {"LIMEN_FABLE_BALANCE_PATH": str(bal), "LIMEN_FABLE_ACCEPTANCE": str(receipt)},
    )
    assert proc.returncode == 0, proc.stderr
