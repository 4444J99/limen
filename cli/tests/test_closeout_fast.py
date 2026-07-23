from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_closeout_fast_keeps_lifecycle_regressions_opt_in():
    script = (ROOT / "scripts" / "closeout-fast.sh").read_text(encoding="utf-8")

    assert "LIMEN_CLOSEOUT_RUN_LIFECYCLE_TESTS" in script
    assert "LIMEN_CLOSEOUT_LIFECYCLE_TEST_TIMEOUT" in script
    default_path, _opt_in = script.split('if [[ "${LIMEN_CLOSEOUT_RUN_LIFECYCLE_TESTS:-0}" == "1" ]]', 1)
    assert "test_session_lifecycle_pressure.py" not in default_path


def test_closeout_fast_requires_live_root_ready_status():
    script = (ROOT / "scripts" / "closeout-fast.sh").read_text(encoding="utf-8")

    assert 'run_and_require_ready "live-root-gate" python3 scripts/live-root-gate.py' in script
    assert "Status: `ready`" in script
