"""Freshness answers "did it run". It cannot answer "did it work".

`organ-health.py` judged every organ by age alone: the voice stamp first, the artifact's
`generated` timestamp as fallback. Both are written at the END of a run that completed —
including a run whose effector half failed and swallowed the error to stay fail-open.

routine-freshness is the organ that proved this hurts. It ran for 50 consecutive days at
`severity: silent` while a keeper 409 killed its atom-hanging half on every pass. The repair
(#1999) made that rejection non-fatal and recorded it in the artifact, which moved the defect
from "crashes silently" to "records silently" — nobody read the record. These tests hold the
reader in place.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "organ-health.py"


def _load():
    spec = importlib.util.spec_from_file_location("organ_health", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fresh_logs(mod, tmp_path: Path, *, escalation: dict[str, Any] | None) -> None:
    """A logs dir where routine-freshness looks maximally healthy on every age-based signal."""
    logs = tmp_path / "logs"
    voice = logs / ".voice"
    voice.mkdir(parents=True)
    now = datetime.now().replace(microsecond=0)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    artifact: dict[str, Any] = {
        "generated": stamp,
        "routines": [{"name": "atom-backlog-triage", "verdict": "down", "days_silent": 31.0}],
        "summary": {"green": 12, "down": 1},
        "retire": {"retired": []},
    }
    if escalation is not None:
        artifact["escalation"] = escalation
    (logs / "routine-freshness.json").write_text(json.dumps(artifact))
    # The voice stamp is consulted BEFORE the artifact probe and is ground truth for "it fired".
    # Writing it fresh is the whole point: the organ really did run.
    (voice / "routines").write_text(stamp)

    mod.LOGS = logs
    mod.VOICED = voice


def _routines_row(mod) -> dict[str, Any]:
    rows = mod.build()["organs"]
    row = next((r for r in rows if r["key"] == "routines"), None)
    assert row is not None, "the routines rung is no longer discovered from the heartbeat"
    return row


def test_a_fresh_organ_whose_effector_failed_is_reported_down_not_green(tmp_path: Path) -> None:
    """The regression this exists for: fresh stamp, recorded failure, and a green light.

    Everything age-based here is deliberately perfect — the voice stamp is seconds old and the
    artifact's `generated` is seconds old. Only the recorded escalation error says otherwise.
    Before the defect channel, this exact artifact read `green`.
    """
    mod = _load()
    _fresh_logs(
        mod,
        tmp_path,
        escalation={
            "created": [],
            "error": "keeper sync failed (task ASK-routine-x already exists); ledger unchanged this beat",
        },
    )

    row = _routines_row(mod)
    assert row["status"] == "down"
    # The reason travels with the verdict — a "down" nobody can explain gets re-derived by hand.
    assert "self-reported defect" in row["note"]
    assert "escalation.error" in row["note"]
    assert "keeper sync failed" in row["note"]
    # Freshness itself is untouched: the organ DID fire, and the record still says so.
    assert row["age_h"] is not None and row["age_h"] < 1


def test_the_same_organ_with_no_recorded_failure_stays_green(tmp_path: Path) -> None:
    """The control. Without this, a defect channel that hard-codes "down" would also pass."""
    mod = _load()
    _fresh_logs(mod, tmp_path, escalation={"created": ["ASK-routine-x"], "refreshed": []})

    row = _routines_row(mod)
    assert row["status"] == "green"
    assert "self-reported defect" not in (row["note"] or "")


def test_the_retire_half_is_read_too(tmp_path: Path) -> None:
    """Both halves hang atoms. `retire` closing is as load-bearing as `escalation` opening —
    a stuck retire leaves resolved false-positives in the operator's needs_human queue forever."""
    mod = _load()
    _fresh_logs(mod, tmp_path, escalation={"created": []})
    artifact = json.loads((mod.LOGS / "routine-freshness.json").read_text())
    artifact["retire"] = {"retired": [], "error": "queue busy; skipped this beat (self-corrects)"}
    (mod.LOGS / "routine-freshness.json").write_text(json.dumps(artifact))

    row = _routines_row(mod)
    assert row["status"] == "down"
    assert "retire.error" in row["note"]


def test_nested_error_reader_is_quiet_on_everything_that_is_not_a_recorded_failure(tmp_path: Path) -> None:
    """Fail-open in the reader too: an unreadable or oddly-shaped artifact is NOT a defect.

    A parse failure means "no signal", which the age-based path already reports as unknown/down
    on its own terms. Manufacturing a defect from a malformed file would turn every artifact
    format change into a false operator atom.
    """
    mod = _load()
    trail = ("escalation", "error")
    path = tmp_path / "a.json"

    assert mod._json_nested_error(tmp_path / "absent.json", trail) is None
    path.write_text("{not json")
    assert mod._json_nested_error(path, trail) is None
    path.write_text(json.dumps([1, 2, 3]))
    assert mod._json_nested_error(path, trail) is None
    path.write_text(json.dumps({"escalation": "not-a-dict"}))
    assert mod._json_nested_error(path, trail) is None
    path.write_text(json.dumps({"escalation": {"error": "   "}}))
    assert mod._json_nested_error(path, trail) is None, "whitespace is not a reported failure"
    path.write_text(json.dumps({"escalation": {}}))
    assert mod._json_nested_error(path, trail) is None

    path.write_text(json.dumps({"escalation": {"error": "boom"}}))
    assert mod._json_nested_error(path, trail) == "escalation.error: boom"


def test_the_first_recorded_failure_wins_in_trail_order(tmp_path: Path) -> None:
    """Deterministic reporting: one note, chosen by declared order, not by dict iteration."""
    mod = _load()
    path = tmp_path / "a.json"
    path.write_text(json.dumps({"escalation": {"error": "first"}, "retire": {"error": "second"}}))
    assert mod._json_nested_error(path, ("escalation", "error"), ("retire", "error")) == "escalation.error: first"
    assert mod._json_nested_error(path, ("retire", "error"), ("escalation", "error")) == "retire.error: second"
