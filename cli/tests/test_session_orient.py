from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "session-orient.py"


def _load(monkeypatch, root: Path):
    monkeypatch.setenv("LIMEN_ROOT", str(root))
    spec = importlib.util.spec_from_file_location("session_orient_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_section_levers_only_renders_open_lifecycles(tmp_path, monkeypatch):
    terminal_statuses = ("discharged", "retired", "done", "closed")
    levers = [
        {"id": "MISSING-STATUS"},
        {"id": "NONTERMINAL-STATUS", "status": "open — keep this free text"},
        {"id": "FALSE-LEGACY-FLAG", "discharged": False},
        {"id": "LEGACY-DISCHARGED", "discharged": "yes"},
    ]
    levers.extend(
        {"id": f"TERMINAL-{status.upper()}", "status": f"  {status.upper()}  "} for status in terminal_statuses
    )
    (tmp_path / "his-hand-levers.json").write_text(json.dumps({"levers": levers}))

    rendered = _load(monkeypatch, tmp_path).section_levers()

    assert "3 open" in rendered
    assert "MISSING-STATUS" in rendered
    assert "NONTERMINAL-STATUS" in rendered
    assert "FALSE-LEGACY-FLAG" in rendered
    assert "LEGACY-DISCHARGED" not in rendered
    for status in terminal_statuses:
        assert f"TERMINAL-{status.upper()}" not in rendered
