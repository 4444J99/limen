from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "heartbeat-paused-receipt.py"


def load_module():
    spec = importlib.util.spec_from_file_location("heartbeat_paused_receipt_uut", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_paused_receipt_reaches_byte_and_mtime_fixed_point(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "logs" / "heartbeat-paused.json"
    assert module.write_paused(path, 300) is True
    first = path.read_bytes()
    first_mtime = path.stat().st_mtime_ns

    assert module.write_paused(path, 300) is False
    assert path.read_bytes() == first
    assert path.stat().st_mtime_ns == first_mtime
    payload = json.loads(first)
    assert payload == {
        "cadence_seconds": 300,
        "mode": "paused",
        "resume": "autonomy governor leaves paused mode",
        "schema": "limen.heartbeat_pause.v1",
        "substantive_probes": False,
    }


def test_resume_clears_receipt_idempotently(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "paused.json"
    module.write_paused(path, 300)
    assert module.clear_paused(path) is True
    assert module.clear_paused(path) is False


def test_invalid_pause_cadence_fails_closed() -> None:
    module = load_module()
    try:
        module.receipt_bytes(59)
    except ValueError as exc:
        assert "between 60 and 86400" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("unsafe cadence was accepted")


def test_heartbeat_sleeps_in_place_instead_of_exiting() -> None:
    text = (ROOT / "scripts" / "heartbeat-loop.sh").read_text(encoding="utf-8")
    start = text.index('if [ "$MODE" = "paused" ]; then')
    end = text.index("# CONNECTIVITY GATE", start)
    paused = text[start:end]
    assert "heartbeat-paused-receipt.py" in paused
    assert 'sleep "$PAUSED_BEAT"' in paused
    assert "continue" in paused
    assert "exit 0" not in paused
