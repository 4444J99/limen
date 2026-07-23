from __future__ import annotations

import importlib.util
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "codex-quicken.py"


def _load():
    spec = importlib.util.spec_from_file_location("codex_quicken", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_session(path: Path, records: list[dict], *, mtime_offset: int = 3600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    old = time.time() - mtime_offset
    os.utime(path, (old, old))


def _session_records(session_id: str, prompt: str, *, complete: bool = False) -> list[dict]:
    records = [
        {
            "type": "session_meta",
            "timestamp": "2026-06-27T00:00:00Z",
            "payload": {"session_id": session_id, "cwd": f"/tmp/{session_id}"},
        },
        {
            "type": "event_msg",
            "timestamp": "2026-06-27T00:01:00Z",
            "payload": {"type": "user_message", "message": prompt},
        },
    ]
    if complete:
        records.append(
            {
                "type": "event_msg",
                "timestamp": "2026-06-27T00:02:00Z",
                "payload": {"type": "task_complete", "completed_at": "2026-06-27T00:02:00Z"},
            }
        )
    return records


def test_classifies_codex_sessions_without_raw_prompt_leakage(tmp_path: Path):
    cq = _load()
    cq.ROOT = tmp_path
    cq.SESSIONS = tmp_path / "sessions"
    cq.HISTORY = tmp_path / "history.jsonl"
    cq.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    cq.PRIVATE_INDEX = cq.PRIVATE_ROOT / "lifecycle" / "codex-session-lifecycle.json"
    cq.JOURNAL = tmp_path / "logs" / "codex-session-lifecycle.jsonl"
    cq.DIGEST_OUT = tmp_path / "docs" / "CODEX-SESSION-LIFECYCLE.md"
    cq.STALE_MIN = 1
    marker = "fixture" + "-private" + "-marker"

    _write_session(
        cq.SESSIONS / "2026" / "06" / "27" / "auth.jsonl",
        _session_records("auth", f"login with {marker} credential"),
    )
    _write_session(
        cq.SESSIONS / "2026" / "06" / "27" / "ci.jsonl",
        _session_records("ci", "fix technical debt and pytest failures"),
    )
    _write_session(
        cq.SESSIONS / "2026" / "06" / "27" / "closed.jsonl",
        _session_records("closed", "review session lifecycle and worktree receipts", complete=True),
    )
    cq.HISTORY.write_text(
        json.dumps({"session_id": "auth", "ts": 1782583930, "text": f"login with {marker} credential"}),
        encoding="utf-8",
    )

    snapshot = cq.build_snapshot(None)
    markdown = cq.render_markdown(snapshot)
    cq.write_outputs(snapshot, markdown)

    assert snapshot["by_state"]["PARKED"] == 1
    assert snapshot["by_state"]["STALLED"] == 1
    assert snapshot["by_state"]["CLOSED"] == 1
    assert snapshot["by_family"]["auth_credentials"] == 1
    assert snapshot["by_family"]["technical_debt_ci"] == 1
    assert snapshot["history"]["events"] == 1

    digest = cq.DIGEST_OUT.read_text(encoding="utf-8")
    private_index = cq.PRIVATE_INDEX.read_text(encoding="utf-8")
    assert marker not in digest
    assert marker not in private_index
    assert "auth_credentials" in digest
    assert cq.JOURNAL.exists()


def test_malformed_stale_env_falls_back(monkeypatch):
    monkeypatch.setenv("LIMEN_CODEX_QUICKEN_STALE_MIN", "not-an-int")
    assert _load().STALE_MIN == 20

    monkeypatch.setenv("LIMEN_CODEX_QUICKEN_STALE_MIN", "0")
    assert _load().STALE_MIN == 20

    monkeypatch.setenv("LIMEN_CODEX_QUICKEN_STALE_MIN", "7")
    assert _load().STALE_MIN == 7


def test_parse_ts_ignores_nonfinite_numbers():
    cq = _load()

    assert cq.parse_ts(float("nan")) is None
    assert cq.parse_ts(float("inf")) is None
    assert cq.parse_ts("-infinity") is None
