"""heal-dispatch chronic escalation: a chronic task (reopened >=3x, never a PR — surfaced by
verify-dispatch into dispatch-verify.json) must be escalated to needs_human, NOT silently re-looped.
Reversible status flip; a non-chronic open task is left untouched."""

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "heal-dispatch.py"


def test_chronic_open_task_escalated_to_needs_human(tmp_path):
    root = tmp_path
    (root / "logs").mkdir()
    created = "2026-06-20T00:00:00+00:00"
    board = {
        "tasks": [
            {
                "id": "CHRONIC1",
                "title": "chronic task",
                "created": created,
                "status": "open",
                "target_agent": "codex",
                "repo": "x/y",
                "dispatch_log": [
                    {"timestamp": "2026-06-21T00:00:00+00:00", "agent": "limen", "session_id": "heal", "status": "open"}
                ],
            },
            {
                "id": "FRESH1",
                "title": "fresh task",
                "created": created,
                "status": "open",
                "target_agent": "codex",
                "repo": "x/y",
                "dispatch_log": [],
            },
        ]
    }
    (root / "tasks.yaml").write_text(yaml.safe_dump(board))
    (root / "logs" / "dispatch-verify.json").write_text(
        json.dumps(
            {
                "counts": {"CHRONIC": 1},
                "detail": {},
                "chronic": [{"id": "CHRONIC1", "agent": "codex", "reopens": 3, "repo": "x/y"}],
            }
        )
    )
    env = dict(os.environ, LIMEN_ROOT=str(root), LIMEN_TASKS=str(root / "tasks.yaml"))
    r = subprocess.run([sys.executable, str(SCRIPT), "--apply"], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = {t["id"]: t for t in yaml.safe_load((root / "tasks.yaml").read_text())["tasks"]}
    assert out["CHRONIC1"]["status"] == "needs_human", out["CHRONIC1"]
    assert out["FRESH1"]["status"] == "open", out["FRESH1"]  # non-chronic untouched
