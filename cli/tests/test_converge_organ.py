"""converge-organ: the autonomic layer over the converge engine. The ORACLE finds multiverses
(one idea with ≥2 divergent PRs), and --apply emits the gap-finder's next_shots as bounded new
tasks. Offline (dry-run kit) — no network."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import yaml
from limen.tabularius import drain_once

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "converge-organ.py"


def _load(monkeypatch, root):
    monkeypatch.setenv("LIMEN_ROOT", str(root))
    spec = importlib.util.spec_from_file_location("converge_organ_uut", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_oracle_finds_only_multiverses(tmp_path, monkeypatch):
    m = _load(monkeypatch, tmp_path)
    tasks = [
        {
            "id": "MULTI",
            "title": "build the thing",
            "dispatch_log": [
                {"agent": "codex", "session_id": "https://github.com/o/r/pull/1", "output": "approach A"},
                {"agent": "claude", "session_id": "https://github.com/o/r/pull/2", "output": "approach B"},
            ],
        },
        {
            "id": "SINGLE",
            "title": "one shot",
            "dispatch_log": [{"agent": "codex", "session_id": "https://github.com/o/r/pull/3", "output": "only one"}],
        },
        {"id": "NONE", "title": "no pr", "dispatch_log": [{"agent": "codex", "session_id": "running"}]},
    ]
    mvs = m.find_multiverses(tasks)
    assert [x["id"] for x in mvs] == ["MULTI"]
    assert len(mvs[0]["shots"]) == 2


def test_apply_emits_gap_tasks(tmp_path, monkeypatch):
    (tmp_path / "logs").mkdir()
    created = "2026-06-20"
    board = {
        "tasks": [
            {
                "id": "MULTI",
                "title": "cats are fluffy pets",
                "created": created,
                "status": "done",
                "target_agent": "codex",
                "repo": "o/r",
                "dispatch_log": [
                    {
                        "timestamp": "2026-06-21T00:00:00+00:00",
                        "agent": "codex",
                        "session_id": "https://github.com/o/r/pull/1",
                        "status": "dispatched",
                        "output": "cats are great fluffy pets that purr",
                    },
                    {
                        "timestamp": "2026-06-21T00:01:00+00:00",
                        "agent": "claude",
                        "session_id": "https://github.com/o/r/pull/2",
                        "status": "dispatched",
                        "output": "completely unrelated text about quarterly taxes",
                    },
                ],
            }
        ]
    }
    (tmp_path / "tasks.yaml").write_text(yaml.safe_dump(board))
    env = dict(os.environ, LIMEN_ROOT=str(tmp_path), LIMEN_TASKS=str(tmp_path / "tasks.yaml"))
    r = subprocess.run([sys.executable, str(SCRIPT), "--apply"], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    # the full pipeline ran (oracle → distill → audit-write): a record for MULTI is logged
    log = tmp_path / "logs" / "converge-log.jsonl"
    assert log.exists(), f"no converge log; stdout={r.stdout} stderr={r.stderr}"
    assert "MULTI" in log.read_text()


def test_gap_writer_emits_bounded_idempotent_tasks(tmp_path, monkeypatch):
    m = _load(monkeypatch, tmp_path)
    (tmp_path / "logs").mkdir()
    (tmp_path / "tasks.yaml").write_text(yaml.safe_dump({"tasks": []}))
    monkeypatch.setenv("LIMEN_TASKS", str(tmp_path / "tasks.yaml"))
    added = m._emit_gaps(["support widget export", "support widget export"], "MULTI", apply=True)
    assert added == 1  # idempotent: the duplicate gap is collapsed
    drain_once(tmp_path / "tasks.yaml")
    out = yaml.safe_load((tmp_path / "tasks.yaml").read_text())
    conv = [t for t in out["tasks"] if t["id"].startswith("CONV-")]
    assert len(conv) == 1 and conv[0]["type"] == "converge-gap"
    # second run with the same gap adds nothing (id derived from text)
    assert m._emit_gaps(["support widget export"], "MULTI", apply=True) == 0
