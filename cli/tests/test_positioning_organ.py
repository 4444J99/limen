"""positioning-organ: the gated daemon lane (C_POSITIONING) that refreshes the inbound-magnet
surfaces on cadence. Offline — reads the organ registry + the loop source; no daemon run, no
network. The lane is gated OFF by default (LIMEN_POSITIONING=1 is his knob): generation alone
never publishes."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ORGAN = ROOT / "scripts" / "organ-health.py"
LOOP = ROOT / "scripts" / "heartbeat-loop.sh"


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
    assert entry["gate_default"] == "0"          # OFF unless he arms it
    assert entry["voice"] == "positioning"        # reads logs/.voice/positioning ground truth
    assert entry["cadence_key"] == "POSITIONING"  # parsed from C_POSITIONING in the loop


def test_loop_defines_cadence_and_gates_the_lane():
    text = LOOP.read_text()
    # cadence constant in the exact shape organ-health.py's _parse_cadences regex expects
    assert 'C_POSITIONING="${LIMEN_BEAT_POSITIONING:-' in text
    # the lane is gated OFF by default and invokes the generator's three surfaces, then stamps
    assert 'LIMEN_POSITIONING:-0' in text
    assert "scripts/generate-positioning.py" in text
    assert "--frontdoor" in text
    assert "--discoverability" in text
    assert "stamp positioning" in text
    # no --fetch on the lane: the daemon stays offline/deterministic (no stuck-API timeout risk)
    assert "generate-positioning.py --fetch" not in text
