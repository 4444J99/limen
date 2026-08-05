"""Offline unit tests for the application-funnel beat driver (scripts/application-funnel.py).

Hermetic — no orchestrator launch, no network. Mirrors the importlib load pattern of the
other scripts/ tests.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "application-funnel.py"


def load(monkeypatch, state_dir: Path):
    """Load the driver with its state directory pointed at a temp path."""
    monkeypatch.setenv("LIMEN_APPLICATION_STATE_DIR", str(state_dir))
    spec = importlib.util.spec_from_file_location("application_funnel", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_absent_result_is_not_a_defect(tmp_path, monkeypatch):
    """Before the first cycle there is no file — quiet, and no defect reported."""
    mod = load(monkeypatch, tmp_path)

    result, defect = mod._last_result()

    assert result is None
    assert defect is None


def test_valid_result_is_returned_without_defect(tmp_path, monkeypatch):
    mod = load(monkeypatch, tmp_path)
    (tmp_path / "funnel-last-result.json").write_text('{"scan": {"total_fetched": 93}}', encoding="utf-8")

    result, defect = mod._last_result()

    assert defect is None
    assert result == {"scan": {"total_fetched": 93}}


def test_corrupt_result_is_named_rather_than_read_as_zero(tmp_path, monkeypatch):
    """A garbage state file must not be indistinguishable from "never ran".

    On 2026-08-05 this file held the literal five-byte string ``test``. Every read
    swallowed the parse error, returned ``None``, and reported an all-zero summary
    with the note "no completed cycle yet" — a silent zero from a broken sensor,
    which reads exactly like a true zero.
    """
    mod = load(monkeypatch, tmp_path)
    (tmp_path / "funnel-last-result.json").write_text("test", encoding="utf-8")

    result, defect = mod._last_result()

    assert result is None
    assert defect is not None
    assert "unreadable" in defect
    assert "NOT a true zero" in defect


def test_non_object_result_is_named(tmp_path, monkeypatch):
    """Valid JSON that is not an object is still unusable state."""
    mod = load(monkeypatch, tmp_path)
    (tmp_path / "funnel-last-result.json").write_text("[1, 2, 3]", encoding="utf-8")

    result, defect = mod._last_result()

    assert result is None
    assert defect is not None
    assert "not an object" in defect


def test_corrupt_state_suppresses_the_reassuring_first_cycle_note(tmp_path, monkeypatch):
    """ "No completed cycle yet" is a claim about history, not about a broken file."""
    mod = load(monkeypatch, tmp_path)
    (tmp_path / "funnel-last-result.json").write_text("test", encoding="utf-8")
    monkeypatch.setattr(mod, "_find_orchestrator", lambda: None)

    summary = mod.run()

    assert not any("no completed cycle yet" in note for note in summary["notes"])
