from __future__ import annotations

import importlib.util
import time
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "session-walk-census.py"


def _load():
    spec = importlib.util.spec_from_file_location("session_walk_census", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_stale_codex_resume_display_is_blocked():
    census = _load()
    today_start = census.local_day_start_ts(time.time())
    stale = {
        "vendor": "codex",
        "sid": "019f379d-dead-beef",
        "mtime": today_start - 1,
        "resume": "codex exec resume 019f379d-dead-beef",
    }
    current = {
        "vendor": "codex",
        "sid": "current-session",
        "mtime": today_start + 60,
        "resume": "codex exec resume current-session",
    }

    assert census.stale_codex_resume_blocked(stale) is True
    assert "codex exec resume" not in census.resume_display(stale)
    assert census.stale_codex_resume_blocked(current) is False
    assert census.resume_display(current) == "codex exec resume current-session"


def test_walk_skips_stale_codex_without_override(tmp_path, monkeypatch, capsys):
    census = _load()
    monkeypatch.setattr(census, "WALK_JOURNAL", tmp_path / "session-walk.jsonl")
    today_start = census.local_day_start_ts(time.time())
    rows = [
        {
            "vendor": "codex",
            "sid": "019f379d-dead-beef",
            "mtime": today_start - 1,
            "cwd": str(tmp_path),
            "purpose": "stale codex",
        },
        {
            "vendor": "claude",
            "sid": "claude-current",
            "mtime": today_start - 1,
            "cwd": str(tmp_path),
            "purpose": "claude stale is still resumable by this rule",
        },
    ]

    census.walk(rows, cap=2, dry=True)

    out = capsys.readouterr().out
    assert "SKIP stale codex 019f379d" in out
    assert "DRY would walk codex 019f379d" not in out
    assert "DRY would walk claude claude-c" in out
