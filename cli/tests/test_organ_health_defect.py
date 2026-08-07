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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "organ-health.py"


def _load():
    spec = importlib.util.spec_from_file_location("organ_health", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fresh_logs(mod, tmp_path: Path, *, escalation: dict[str, Any] | None, artifact_age_h: float = 0.0) -> None:
    """A logs dir where routine-freshness looks maximally healthy on every age-based signal.

    `artifact_age_h` ages the ARTIFACT independently of the voice stamp. Writing both together
    (the only shape this helper had) makes the two clocks indistinguishable, so no test could
    observe which one a row reports. In production the audit writes them in the same `try` with
    the same timestamp, but the reader must not depend on that: they are separate signals, and
    `defect_recorded_h` is defined as the artifact's, never the stamp's.
    """
    logs = tmp_path / "logs"
    voice = logs / ".voice"
    voice.mkdir(parents=True)
    # UTC, matching the producer: routine-freshness-audit writes `generated` from
    # datetime.now(timezone.utc) with a trailing Z. Building it from a LOCAL clock and appending
    # Z anyway is precisely the skew the reader was fixed for — the fixture must not re-introduce
    # it, or the tests pass on an offset that cancels itself out.
    now = datetime.now(timezone.utc).replace(microsecond=0)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    generated = (now - timedelta(hours=artifact_age_h)).strftime("%Y-%m-%dT%H:%M:%SZ")

    artifact: dict[str, Any] = {
        "generated": generated,
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
    assert mod._json_nested_error(path, trail) == ("escalation.error: boom", None)


def test_a_recorded_failure_with_no_generated_stamp_is_still_a_defect(tmp_path: Path) -> None:
    """Degrade the CLOCK, never the verdict.

    The recording time is a nicety for the operator; the failure is the finding. An artifact
    missing or mangling `generated` must still report `down` — softening that would hand every
    format drift a way to silence the channel.
    """
    mod = _load()
    path = tmp_path / "a.json"
    path.write_text(json.dumps({"escalation": {"error": "boom"}, "generated": "not-a-timestamp"}))
    assert mod._json_nested_error(path, ("escalation", "error")) == ("escalation.error: boom", None)


def test_the_first_recorded_failure_wins_in_trail_order(tmp_path: Path) -> None:
    """Deterministic reporting: one note, chosen by declared order, not by dict iteration."""
    mod = _load()
    path = tmp_path / "a.json"
    path.write_text(json.dumps({"escalation": {"error": "first"}, "retire": {"error": "second"}}))
    assert mod._json_nested_error(path, ("escalation", "error"), ("retire", "error"))[0] == "escalation.error: first"
    assert mod._json_nested_error(path, ("retire", "error"), ("escalation", "error"))[0] == "retire.error: second"


def test_a_utc_artifact_stamp_is_not_read_as_local_time(tmp_path: Path) -> None:
    """The reader must not be the thing that manufactures freshness.

    Producers write UTC — routine-freshness-audit stamps `generated` from
    `datetime.now(timezone.utc)`, trailing `Z`. Parsing that naive means local, which lands one
    UTC-offset in the past; every consumer subtracts from `time.time()`, so the organ reports
    itself one offset YOUNGER than it is (4h in EDT). It surfaced as a live 3.9h disagreement
    between `age_h` (voice-stamp mtime, correct) and `defect_recorded_h` (artifact, skewed) on
    one and the same run.

    Naive strings stay local: some artifacts write local time, and assuming UTC for them would
    invent the same error mirrored.
    """
    mod = _load()
    path = tmp_path / "a.json"
    utc = datetime.now(timezone.utc).replace(microsecond=0)

    path.write_text(json.dumps({"generated": utc.strftime("%Y-%m-%dT%H:%M:%SZ")}))
    assert abs(mod._json_field_ts(path, "generated") - utc.timestamp()) < 2

    local = datetime.now().replace(microsecond=0)
    path.write_text(json.dumps({"generated": local.strftime("%Y-%m-%dT%H:%M:%S")}))
    assert abs(mod._json_field_ts(path, "generated") - local.timestamp()) < 2


def test_the_freshness_budget_is_the_organs_own_cadence_not_one_beat(tmp_path: Path) -> None:
    """The live regression this fix landed for.

    routine-freshness-audit is invoked at `--throttle 21600`, so it writes its artifact at most
    every 6h by design. The rung used to declare no interval, and the fallback derives
    beats(1) x loop_max(1800s) = 30min — measured live as `age_h 5.7 / expected_h 0.5 /
    status down` against an artifact whose escalation and retire were both clean.

    Two things rode on that number, which is why it is asserted rather than left to the eye:
    avtopoiesis maps down -> 0.0, so a healthy organ contributed a floor score as its STEADY
    state; and the defect channel became near-unobservable, able only to add `down` to a row
    that was already down.
    """
    mod = _load()
    _fresh_logs(mod, tmp_path, escalation={"created": []}, artifact_age_h=5.7)
    (mod.VOICED / "routines").unlink()  # no stamp -> the artifact probe is the signal, as after a restart

    row = _routines_row(mod)
    assert row["expected_h"] == 6.0, "the budget must track the sensor's --throttle, not one beat"
    assert row["status"] == "green", "a healthy organ inside its own cadence is not down"


def test_the_defect_clock_is_the_artifacts_not_the_voice_stamps(tmp_path: Path) -> None:
    """`down` alone cannot separate "failing now" from "failed hours ago, already repaired".

    The row carries two clocks and they answer different questions: `age_h` is "when did it last
    run" (the voice stamp wins that race), `defect_recorded_h` is "when was this failure
    written". A throttled organ keeps serving an old record until its next real run, so a note
    that borrows the stamp's age reports 0.0h for a failure that may be long since fixed.
    """
    mod = _load()
    _fresh_logs(
        mod,
        tmp_path,
        escalation={"error": "keeper sync failed (409 already exists); ledger unchanged this beat"},
        artifact_age_h=4.0,
    )

    row = _routines_row(mod)
    assert row["status"] == "down"
    assert row["age_h"] < 1, "the stamp is fresh — the organ really did fire"
    assert 3.9 <= row["defect_recorded_h"] <= 4.1, "the defect's clock is the artifact's"
    assert "recorded 4.0h ago" in row["note"]


def test_a_healthy_row_reports_no_defect_clock(tmp_path: Path) -> None:
    """The field is a defect attribute, not a second freshness reading. Absent means no defect."""
    mod = _load()
    _fresh_logs(mod, tmp_path, escalation={"created": ["ASK-routine-x"]}, artifact_age_h=4.0)

    row = _routines_row(mod)
    assert row["status"] == "green"
    assert row["defect_recorded_h"] is None
