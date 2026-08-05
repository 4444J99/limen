"""The ledger must carry the judgment the evening makes, not just the fact that it ran.

A separate file from test_diurnal.py on purpose. That file is organised as a growing tail —
`# ── section ──` blocks appended at the bottom — which makes a textual conflict certain between
any two sibling branches that both add a case, and this workstream ran three at once. One file per
concern means different concerns add different FILES.

What is under test: the cut runway is denominated in ENGAGED days, and the evening is the only
phase that knows whether a day was engaged. Before this, `engaged` was computed in emit(), passed
to apply_cuts(), and dropped — so the runway was unmeasurable and the predicate that measured it
read a key with no writer.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "diurnal.py"
REGISTRY = ROOT / "institutio" / "governance" / "diurnal.yaml"


@pytest.fixture()
def mod():
    spec = importlib.util.spec_from_file_location("diurnal", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["diurnal"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    (tmp_path / "logs" / ".voice").mkdir(parents=True)
    (tmp_path / "logs" / ".voice" / "drain").write_text("")
    (tmp_path / "institutio" / "governance").mkdir(parents=True)
    (tmp_path / "institutio" / "governance" / "diurnal.yaml").write_text(
        REGISTRY.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return tmp_path


def _rows(root: Path) -> list[dict]:
    path = root / "logs" / "diurnal" / "ledger.jsonl"
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def test_evening_records_whether_the_day_was_engaged(mod, root, monkeypatch):
    """The evening's own verdict on the day must survive the run that produced it."""
    monkeypatch.setattr(mod, "engaged_today", lambda _root: True)
    assert mod.emit(root, "evening", dry_run=False) == 0

    evening = [r for r in _rows(root) if r["phase"] == "evening"]
    assert len(evening) == 1
    assert evening[0]["engaged"] is True


def test_an_unengaged_evening_is_recorded_as_such_not_omitted(mod, root, monkeypatch):
    """A day with no commits still emits — and the row must say so.

    This is the case the live data hit on 2026-08-01: a full evening pass, zero commits, streaks
    correctly frozen. If the row simply lacked the key, a reader counting the runway could not tell
    that day apart from a morning row and would have counted it.
    """
    monkeypatch.setattr(mod, "engaged_today", lambda _root: False)
    assert mod.emit(root, "evening", dry_run=False) == 0

    evening = [r for r in _rows(root) if r["phase"] == "evening"]
    assert evening[0]["engaged"] is False


def test_morning_carries_no_engaged_key_because_morning_does_not_score(mod, root):
    """Absence is the signal, not a default.

    Writing `engaged: False` on a morning row would make "this phase cannot score" look identical
    to "this day earned nothing" — and the runway counter reads exactly that distinction.
    """
    assert mod.emit(root, "morning", dry_run=False) == 0

    morning = [r for r in _rows(root) if r["phase"] == "morning"]
    assert morning, "morning must still append a ledger row"
    assert "engaged" not in morning[0]


def test_dry_run_appends_nothing(mod, root):
    """A rehearsal that moves the runway is not a rehearsal."""
    assert mod.emit(root, "evening", dry_run=True) == 0
    assert not (root / "logs" / "diurnal" / "ledger.jsonl").exists()
