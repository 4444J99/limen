from __future__ import annotations

import importlib.util
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ORGAN = ROOT / "scripts" / "organ-health.py"
LOOP = ROOT / "scripts" / "heartbeat-loop.sh"


def _load(monkeypatch, root):
    monkeypatch.setenv("LIMEN_ROOT", str(root))
    spec = importlib.util.spec_from_file_location("organ_health_vltima_uut", ORGAN)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_vltima_organ_registered_and_gated_off(tmp_path, monkeypatch):
    monkeypatch.delenv("LIMEN_VLTIMA", raising=False)
    m = _load(monkeypatch, tmp_path)
    entry = next((o for o in m._registry() if o["key"] == "vltima"), None)

    assert entry is not None
    assert entry["gate"] == "LIMEN_VLTIMA"
    assert entry["gate_default"] == "0"
    assert entry["voice"] == "vltima"
    assert entry["cadence_key"] == "VLTIMA"


def test_loop_defines_vltima_cadence_and_gates_lane():
    text = LOOP.read_text()

    assert 'C_VLTIMA="${LIMEN_BEAT_VLTIMA:-' in text
    assert "LIMEN_VLTIMA:-0" in text
    assert "scripts/vltima-organ.py\" --write" in text
    assert "stamp vltima" in text
    assert "--materialize-private" not in re.search(r"if due_voice vltima.*?fi", text, re.S).group(0)

