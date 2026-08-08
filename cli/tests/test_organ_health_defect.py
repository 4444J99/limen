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

    `artifact_age_h` backdates the ARTIFACT only, leaving the voice stamp current. That is not a
    contrived shape: the voice stamps every beat regardless of exit code while the audit is
    throttled at 21600s and skips without rewriting, so the two clocks routinely disagree by
    hours in production.
    """
    logs = tmp_path / "logs"
    voice = logs / ".voice"
    voice.mkdir(parents=True)
    # UTC, matching the producer: routine-freshness-audit writes `generated` from
    # datetime.now(timezone.utc) with a trailing Z. This built it from a LOCAL clock and appended
    # Z anyway — the same skew the reader carried, so the two errors cancelled and the suffix
    # assertions below passed on a number that was wrong by one UTC offset in production.
    now = datetime.now(timezone.utc).replace(microsecond=0)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    art_stamp = (now - timedelta(hours=artifact_age_h)).strftime("%Y-%m-%dT%H:%M:%SZ")

    artifact: dict[str, Any] = {
        "generated": art_stamp,
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


def test_a_stale_artifact_under_a_fresh_voice_names_its_own_age(tmp_path: Path) -> None:
    """The row's `age_h` measures the VOICE. The defect came from the artifact. They diverge.

    beat-sensors stamps the voice unconditionally after a sensor's steps, while the audit runs at
    `--throttle 21600` and skips without rewriting — so a real, long-since-repaired failure can sit
    beside `0.0h ago` and read as happening right now. The verdict stays `down` (last known state
    of the effector half IS failed); only the false immediacy goes away.
    """
    mod = _load()
    _fresh_logs(
        mod,
        tmp_path,
        escalation={"created": [], "error": "keeper sync failed; long since repaired"},
        artifact_age_h=5.0,
    )

    row = _routines_row(mod)
    assert row["status"] == "down"
    # The voice is still current — that is the whole trap, and it must stay true.
    assert row["age_h"] is not None and row["age_h"] < 1
    assert "recorded 5.0h ago" in row["note"], row["note"]


def test_a_freshly_recorded_failure_is_not_labelled_stale(tmp_path: Path) -> None:
    """The control for the age suffix: it reports a real measurement, not a constant."""
    mod = _load()
    _fresh_logs(mod, tmp_path, escalation={"created": [], "error": "keeper sync failed just now"})

    row = _routines_row(mod)
    assert row["status"] == "down"
    assert "recorded 0.0h ago" in row["note"], row["note"]


def test_the_age_suffix_is_opt_in_and_absent_without_a_stamp_field(tmp_path: Path) -> None:
    """A caller that names no stamp field gets the bare message — and an artifact with no usable
    timestamp is not an error, so the reader stays fail-open on shape."""
    mod = _load()
    path = tmp_path / "a.json"
    path.write_text(json.dumps({"generated": "2026-08-07T10:00:00Z", "escalation": {"error": "boom"}}))
    assert mod._json_nested_error(path, ("escalation", "error")) == "escalation.error: boom"

    path.write_text(json.dumps({"escalation": {"error": "boom"}}))
    assert mod._json_nested_error(path, ("escalation", "error"), stamp="generated") == "escalation.error: boom"

    path.write_text(json.dumps({"generated": "not a timestamp", "escalation": {"error": "boom"}}))
    assert mod._json_nested_error(path, ("escalation", "error"), stamp="generated") == "escalation.error: boom"


def test_a_utc_artifact_stamp_is_not_read_as_local_time(tmp_path: Path) -> None:
    """The reader must not be the thing that manufactures freshness.

    Producers write UTC — routine-freshness-audit stamps `generated` from
    `datetime.now(timezone.utc)`, trailing `Z`. Parsing that naive means LOCAL, which lands one
    UTC-offset in the past; every consumer subtracts from `time.time()`, so the organ reports
    itself one offset YOUNGER than it is (4h in EDT).

    Two things rode on it. Freshness probes that fall back to an artifact published a
    manufactured youth. And the `(recorded Xh ago)` suffix is computed from this helper, so a
    defect recorded 6.1h ago was published as "recorded 2.1h ago" — measured live, against the
    same run whose voice stamp read 6.1h.

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
    """The live regression: a healthy organ reporting `down` most of the time.

    routine-freshness-audit is invoked at `--throttle 21600`, so it rewrites its artifact at most
    every 6h by design. The rung declared no interval, and the fallback derives
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
