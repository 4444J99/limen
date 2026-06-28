import json
import os
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
USAGE = ROOT / "scripts" / "usage-telemetry.py"


def test_claude_rate_limit_in_recent_transcript_marks_lane_down(tmp_path):
    limen_root = tmp_path / "limen"
    home = tmp_path / "home"
    (limen_root / "logs").mkdir(parents=True)
    (home / ".claude" / "projects" / "proj").mkdir(parents=True)
    (limen_root / "tasks.yaml").write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "portal": {
                    "budget": {
                        "track": {"date": "2026-06-19", "spent": 0, "per_agent": {"jules": 0}},
                        "per_agent": {"jules": 100},
                    }
                },
                "tasks": [],
            }
        )
    )
    (home / ".claude" / "projects" / "proj" / "session.jsonl").write_text(
        json.dumps(
            {
                "type": "assistant",
                "error": "rate_limit",
                "message": {
                    "usage": {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0},
                    "content": [{"type": "text", "text": "You've hit your monthly spend limit"}],
                },
            }
        )
        + "\n"
    )

    env = os.environ.copy()
    env["HOME"] = str(home)
    env["LIMEN_ROOT"] = str(limen_root)
    proc = subprocess.run(
        [sys.executable, str(USAGE)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    data = json.loads((limen_root / "logs" / "usage.json").read_text())
    assert data["vendors"]["claude"]["health"] == "rate-limited"
    assert data["vendors"]["claude"]["rate_limit_events"] == 1


def _run_telemetry(tmp_path, jules_consumed, extra_env=None):
    """Run usage-telemetry.py with jules pre-consumed to `jules_consumed` (cap defaults to 100,
    24h window) and return the parsed usage.json vendors map."""
    limen_root = tmp_path / "limen"
    home = tmp_path / "home"
    (limen_root / "logs").mkdir(parents=True)
    (home / ".claude" / "projects").mkdir(parents=True)
    (home / ".codex" / "sessions").mkdir(parents=True)
    (limen_root / "tasks.yaml").write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "portal": {
                    "budget": {
                        "track": {"date": "2026-06-19", "spent": 0, "per_agent": {"jules": jules_consumed}},
                        "per_agent": {"jules": 100},
                    }
                },
                "tasks": [],
            }
        )
    )
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["LIMEN_ROOT"] = str(limen_root)
    env.pop("LIMEN_RESERVE_PCT", None)
    # Overriding HOME drops user-site (where PyYAML lives) from the subprocess sys.path, which
    # would make load_tasks_data fail open to {} and zero out track-derived consumption. Keep
    # yaml importable by pinning its dir onto PYTHONPATH — derived, not hardcoded.
    yaml_dir = os.path.dirname(os.path.dirname(yaml.__file__))
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [yaml_dir, env.get("PYTHONPATH", "")]))
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run([sys.executable, str(USAGE)], cwd=ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return json.loads((limen_root / "logs" / "usage.json").read_text())["vendors"]


def test_pacing_fields_are_emitted(tmp_path):
    v = _run_telemetry(tmp_path, jules_consumed=50)["jules"]
    assert v["window_hours"] == 24
    assert v["reserve_pct"] == 15.0
    assert v["burn_rate_per_h"] == round(50 / 24)  # consumed / window
    assert v["safe_rate_per_h"] == round(100 / 24)  # cap / window = steady-state ceiling
    assert v["runway_h"] == round(50 / round(50 / 24), 1)
    assert v["health"] == "ok"  # 50% headroom, burn <= safe


def test_health_throttle_between_reserve_and_2x(tmp_path):
    # consumed 80 -> 20% headroom, between reserve(15) and 2*reserve(30) -> throttle (still up)
    v = _run_telemetry(tmp_path, jules_consumed=80)["jules"]
    assert v["headroom_pct"] == 20
    assert v["health"] == "throttle"


def test_health_low_at_or_below_reserve(tmp_path):
    # consumed 90 -> 10% headroom, <= reserve(15) -> low (paced-out, stop before 0)
    v = _run_telemetry(tmp_path, jules_consumed=90)["jules"]
    assert v["headroom_pct"] == 10
    assert v["health"] == "low"


def test_reserve_pct_env_override(tmp_path):
    # raise reserve to 25 -> 20% headroom now falls at/below reserve -> low instead of throttle
    v = _run_telemetry(tmp_path, jules_consumed=80, extra_env={"LIMEN_RESERVE_PCT": "25"})["jules"]
    assert v["reserve_pct"] == 25.0
    assert v["health"] == "low"
