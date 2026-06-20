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
        yaml.safe_dump({
            "version": "1.0",
            "portal": {
                "budget": {
                    "track": {"date": "2026-06-19", "spent": 0, "per_agent": {"jules": 0}},
                    "per_agent": {"jules": 100},
                }
            },
            "tasks": [],
        })
    )
    (home / ".claude" / "projects" / "proj" / "session.jsonl").write_text(
        json.dumps({
            "type": "assistant",
            "error": "rate_limit",
            "message": {
                "usage": {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0},
                "content": [{"type": "text", "text": "You've hit your monthly spend limit"}],
            },
        }) + "\n"
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
