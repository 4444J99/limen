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


def test_autonomy_declares_standing_grants_when_no_pause_marker(tmp_path, monkeypatch):
    """No marker used to mean SILENCE, so the grants existed nowhere the session could read.

    An authorization that surfaces only when the operator corrects a deferral
    mid-session is not an authorization.
    """
    rendered = _load(monkeypatch, tmp_path).section_autonomy()

    assert "ACTIVE" in rendered
    assert "merge-policy.sh" in rendered
    assert "human-gated" in rendered
    assert "PAUSED" not in rendered


def test_autonomy_still_surfaces_a_live_pause_over_the_grants(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "AUTONOMY_PAUSED").write_text("reason: keeper incident\nprohibitions: merges\n")

    rendered = _load(monkeypatch, tmp_path).section_autonomy()

    assert "PAUSED" in rendered
    assert "keeper incident" in rendered
    assert "Standing grants" not in rendered


def test_lifecycle_pressure_never_regenerates_inline(tmp_path, monkeypatch):
    """A cold cache must not shell out — the whole banner runs under `timeout 5`.

    The generator's owner is the SessionEnd breadcrumb drain; a banner reports
    state rather than producing it.
    """
    module = _load(monkeypatch, tmp_path)

    def _explode(*_args, **_kwargs):  # pragma: no cover - the assertion is that this never runs
        raise AssertionError("section_lifecycle_pressure spawned a subprocess on a cold cache")

    monkeypatch.setattr(module.subprocess, "run", _explode)

    assert module.section_lifecycle_pressure() == ""


def test_git_section_states_the_sha_and_whether_refs_are_fresh(tmp_path, monkeypatch):
    """Ahead/behind against a never-fetched origin/main reads identically to parity.

    Two sessions ran gates against a 19-commits-behind checkout and reported a
    verdict about the wrong code, so the freshness label is the load-bearing half.
    """
    module = _load(monkeypatch, tmp_path)
    monkeypatch.setenv("LIMEN_ORIENT_FETCH", "0")  # force the degraded path

    calls: list[tuple[str, ...]] = []

    class _Result:
        returncode = 0

        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    def _fake_run(cmd, **_kwargs):
        calls.append(tuple(cmd))
        args = tuple(cmd)
        if "fetch" in args:
            raise AssertionError("fetch ran while LIMEN_ORIENT_FETCH=0")
        if "--abbrev-ref" in args and "HEAD" in args:
            return _Result("feat/example")
        if "--porcelain" in args:
            return _Result("")
        if "rev-parse" in args and "--short" in args:
            return _Result("abc1234" if "HEAD" in args else "def5678")
        if "rev-list" in args:
            return _Result("7 2")
        return _Result("")

    monkeypatch.setattr(module.subprocess, "run", _fake_run)
    rendered = module.section_git()

    assert "abc1234" in rendered, "HEAD sha must be stated"
    assert "def5678" in rendered, "the origin/main sha being compared against must be stated"
    assert "behind 7" in rendered
    assert "STALE" in rendered, "an unfetched read must announce itself, never look like parity"
