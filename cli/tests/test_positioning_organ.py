"""positioning-organ: the gated daemon lane (C_POSITIONING) that refreshes the inbound-magnet
surfaces on cadence. Offline — reads the organ registry + the loop source; no daemon run, no
network. The lane is gated OFF by default (LIMEN_POSITIONING=1 is his knob): generation alone
never publishes.

Also guards organ-health's NON-SOLID property: its door-list is DISCOVERED from the heartbeat (the
same contract AVTOPOIESIS reads), not a hand-roster, so no beat can silently drift out of view."""

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ORGAN = ROOT / "scripts" / "organ-health.py"
LOOP = ROOT / "scripts" / "heartbeat-loop.sh"
CANON = ROOT / "spec" / "avtopoiesis" / "canon.yaml"


def _load(monkeypatch, root):
    monkeypatch.setenv("LIMEN_ROOT", str(root))
    spec = importlib.util.spec_from_file_location("organ_health_uut", ORGAN)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_positioning_organ_registered_and_gated_off(tmp_path, monkeypatch):
    monkeypatch.delenv("LIMEN_POSITIONING", raising=False)
    m = _load(monkeypatch, tmp_path)
    entry = next((o for o in m._registry() if o["key"] == "positioning"), None)
    assert entry is not None, "positioning organ must be registered in organ-health.py"
    assert entry["gate"] == "LIMEN_POSITIONING"
    assert entry["gate_default"] == "0"  # OFF unless he arms it
    assert entry["voice"] == "positioning"  # reads logs/.voice/positioning ground truth
    assert entry["cadence_key"] == "POSITIONING"  # parsed from C_POSITIONING in the loop


def test_loop_defines_cadence_and_gates_the_lane():
    text = LOOP.read_text()
    # cadence constant in the exact shape organ-health.py's _parse_cadences regex expects
    assert 'C_POSITIONING="${LIMEN_BEAT_POSITIONING:-' in text
    # the lane is gated OFF by default and invokes the generator's three surfaces, then stamps
    assert "LIMEN_POSITIONING:-0" in text
    assert "scripts/generate-positioning.py" in text
    assert "--frontdoor" in text
    assert "--discoverability" in text
    assert "stamp positioning" in text
    # no --fetch on the lane: the daemon stays offline/deterministic (no stuck-API timeout risk)
    assert "generate-positioning.py --fetch" not in text


# ── convergence: organ-health feels EVERY heartbeat beat (the door-list is not a solid) ─────────
def test_organ_health_feels_every_heartbeat_beat(monkeypatch):
    """No silent drift: every C_<NAME> beat the heartbeat declares must appear in the fused
    door-list. Independently re-parse the loop here (a different regex than the SUT) as the oracle."""
    m = _load(monkeypatch, ROOT)
    beat_keys = {n.lower() for n in re.findall(r'C_([A-Z][A-Z_]*)="\$\{LIMEN_BEAT_', LOOP.read_text())}
    assert beat_keys, "loop must declare at least one beat"
    doors = m._doors(m._loop_text())
    door_keys = {o["key"] for o in doors}
    # a beat is FELT if a door directly is it (key) or a ladder rung claims it (cadence_key) — the
    # same join _doors() uses. A beat in neither is silently dropped: the drift we forbid.
    covered = door_keys | {o["cadence_key"].lower() for o in doors if o.get("cadence_key")}
    missing = beat_keys - covered
    assert not missing, f"organ-health silently omits heartbeat beats: {sorted(missing)}"
    # beats organ-health used to ignore are now first-class doors …
    assert {"drain", "web", "censor", "quicken", "avtopoiesis"} <= door_keys
    # … and the conceptual rungs with no C_ beat (synthetic) still survive
    assert {"sustain", "merge", "improve"} <= door_keys


def test_orphaned_ladder_rung_is_flagged_not_silently_kept(monkeypatch):
    """The other drift direction: a ladder rung naming a beat the heartbeat NO LONGER declares is
    flagged (_absent), never silently shown as fine. Synthetic rungs (no cadence_key) are exempt."""
    m = _load(monkeypatch, ROOT)
    fused = {o["key"]: o for o in m._doors("# a heartbeat with no beats at all\n")}
    assert fused["positioning"].get("_absent"), "a beat-backed rung with no live beat must flag drift"
    assert not fused["sustain"].get("_absent"), "a synthetic rung (no cadence_key) must not flag drift"


def test_organ_health_discovers_arbitrarily_renamed_scheduled_sensor(tmp_path, monkeypatch):
    governance = tmp_path / "institutio" / "governance"
    scripts = tmp_path / "scripts"
    governance.mkdir(parents=True)
    scripts.mkdir(parents=True)
    (governance / "sensors.yaml").write_text(
        """\
sensors:
  arbitrary.future.id:
    section: heartbeat
    title: arbitrary future sensor
    source: [heartbeat]
    gate: TEST_ARBITRARY_GATE
    default: "1"
    cadence: {env: TEST_ARBITRARY_CADENCE, default: 5}
    steps:
      - command: "python3 scripts/arbitrary.py"
        severity: silent
        escalation: skipped
""",
        encoding="utf-8",
    )
    loop = (
        'if [ "${LIMEN_BEAT_DERIVE:-0}" = "1" ]; then\n'
        '  python3 "$LIMEN_ROOT/scripts/beat-sensors.py" --run --source heartbeat --scheduled-only\n'
        "fi\n"
    )
    (scripts / "heartbeat-loop.sh").write_text(loop, encoding="utf-8")
    monkeypatch.delenv("LIMEN_BEAT_DERIVE", raising=False)
    m = _load(monkeypatch, tmp_path)

    discovered = {door["key"]: door for door in m._discover_doors(loop)}
    door = discovered["arbitrary.future.id"]
    assert door["cadence"] == 5
    assert door["dormant"] is True
    fused = {door["key"]: door for door in m._doors(loop)}
    assert fused["arbitrary.future.id"]["cadence_beats"] == 5
    assert fused["arbitrary.future.id"]["voice"] == "arbitrary.future.id"


def test_fallback_patterns_mirror_canon(monkeypatch):
    """derive-never-pin: the degraded-mode inline patterns must equal the canon's — else the two
    discovery paths could silently diverge (a solid sneaking back in)."""
    m = _load(monkeypatch, ROOT)
    import yaml

    disc = (yaml.safe_load(CANON.read_text()) or {})["discovery"]
    assert m._BEAT_PATTERN_FALLBACK == disc["beat_pattern"]
    assert m._GATE_PATTERN_FALLBACK == disc["gate_pattern"]
