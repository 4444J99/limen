"""Tests for scripts/fable-session-guard.py — the SessionStart guard that closes the interactive
Fable bypass. Clean no-op on a non-Fable model; hard-warn (exit 2) on Fable when over-cap or when
no live acceptance receipt is present.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / "scripts" / "fable-session-guard.py"


def _this_monday() -> str:
    now = datetime.now(timezone.utc)
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


def test_model_at_the_cadence_ceiling_is_noop(tmp_path):
    """Sonnet is the declared opening tier, so it is the clean case."""
    proc = _run({"model": "claude-sonnet-5"})
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr.strip() == ""


def test_model_above_the_cadence_ceiling_warns(tmp_path):
    """THE BLIND SPOT, pinned. The guard asked `"fable" in model` — ONE rung of a four-rung
    ladder — so every tier between the cadence floor and Fable was unguarded and a saved Opus
    default (~15x sonnet) opened every session with the guard reporting a clean no-op. This case
    used to be `returncode == 0` with an empty stderr; asserting that WAS asserting the defect.
    """
    proc = _run({"model": "claude-opus-4-8"})
    assert proc.returncode == 4, proc.stderr
    assert "ABOVE THE CADENCE CEILING" in proc.stderr
    assert "opus" in proc.stderr and "sonnet" in proc.stderr


def test_cadence_ceiling_is_registry_tunable(tmp_path):
    """The tuning knob is the declared ceiling, never a narrowing of the code."""
    proc = _run({"model": "claude-opus-4-8"}, {"LIMEN_CLAUDE_SESSION_OPEN_MAX_TIER": "opus"})
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr.strip() == ""


def test_cadence_ceiling_cannot_be_raised_to_fable(tmp_path):
    """The cap belongs to the VALUE: no env setting can declare Fable an acceptable OPENING tier,
    because Fable is reserved behind a written acceptance receipt and a default is not one."""
    proc = _run({"model": "claude-opus-4-8"}, {"LIMEN_CLAUDE_SESSION_OPEN_MAX_TIER": "fable"})
    assert proc.returncode == 0, proc.stderr  # capped to opus → opus is at the ceiling
    # …and the cap does not thereby bless Fable itself.
    fable = _run({"model": "claude-fable-5"}, {"LIMEN_CLAUDE_SESSION_OPEN_MAX_TIER": "fable"})
    assert fable.returncode == 2, fable.stderr
    assert "HARD WARNING" in fable.stderr


def test_unclassifiable_model_is_unverified_not_cheap(tmp_path):
    """A pin matching no rung cannot be placed against the ceiling — that is 'I could not
    establish this', which must never resolve to the cheapest rung."""
    proc = _run({"model": "some-other-vendor-model-9"})
    assert proc.returncode == 3, proc.stderr
    assert "UNVERIFIED" in proc.stderr


def test_unresolved_model_is_a_third_state_that_speaks(tmp_path):
    """THE DEFECT, pinned. `_resolve_model` used to return "" for an unresolvable session model;
    `_is_fable("")` is False, so the guard took the clean-no-op branch and exited 0 with ZERO
    bytes on stderr — byte-identical to a session confirmed to be running on a cheap tier. The
    guard's most consequential input had a failure mode that looked exactly like success.
    """
    proc = _run({})  # no --model, no payload model, and _run() passes only PATH in the env
    assert proc.returncode == 3, proc.stderr
    assert "UNRESOLVED" in proc.stderr
    # It must not be byte-identical to the confirmed-cheap case — that equality WAS the bug.
    cheap = _run({"model": "claude-opus-4-8"})
    assert (proc.returncode, proc.stderr) != (cheap.returncode, cheap.stderr)
    # And it must not be the HARD WARNING either: "I could not see" is a different finding from
    # "I saw something bad", and printing them the same way drains the loud case of signal.
    assert "HARD WARNING" not in proc.stderr


def test_unresolved_model_resolves_from_env(tmp_path):
    """The notice names LIMEN_SESSION_MODEL as the remedy; that remedy must actually work."""
    proc = _run({}, {"LIMEN_SESSION_MODEL": "claude-sonnet-5"})
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr.strip() == ""


def test_unresolved_takes_precedence_over_a_missing_meter(tmp_path):
    """An unresolvable model is answered BEFORE any meter question — the guard cannot report on a
    Fable cap for a session whose tier it never established."""
    proc = _run({}, {"LIMEN_FABLE_BALANCE_PATH": str(tmp_path / "nope.json")})
    assert proc.returncode == 3, proc.stderr
    assert "UNRESOLVED" in proc.stderr


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
