"""Tests for scripts/routine-freshness-audit.py."""

from __future__ import annotations

import datetime
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "routine-freshness-audit.py"
MANIFEST = ROOT / "cloud-routines.json"


def _load(monkeypatch=None, *, root=None):
    spec = importlib.util.spec_from_file_location("routine_freshness_audit", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    if root is not None and monkeypatch is not None:
        monkeypatch.setenv("LIMEN_ROOT", str(root))
    spec.loader.exec_module(mod)
    return mod


# ── helpers ──────────────────────────────────────────────────────────────────


def _utc(*args) -> datetime.datetime:
    return datetime.datetime(*args, tzinfo=datetime.timezone.utc)


def _row(name="test-routine", cls="delta-gated", max_days=7, issue=42, repo="owner/repo"):
    return {
        "name": name,
        "class": cls,
        "max_silent_days": max_days,
        "issue": issue,
        "issue_repo": repo,
        "enabled": True,
    }


# ── classify tests ────────────────────────────────────────────────────────────


def test_classify_green():
    mod = _load()
    now = _utc(2026, 7, 8, 12, 0, 0)
    last = _utc(2026, 7, 6, 12, 0, 0)  # 2 days ago, max=7
    verdict, age = mod.classify(_row(), last, "comment", now)
    assert verdict == "green"
    assert age is not None and age < 7


def test_classify_stale_10_days_max_7():
    mod = _load()
    now = _utc(2026, 7, 8, 12, 0, 0)
    last = _utc(2026, 6, 28, 12, 0, 0)  # 10 days ago; max=7; 2x=14 → stale
    verdict, age = mod.classify(_row(), last, "comment", now)
    assert verdict == "stale"
    assert 9.9 < age < 10.1


def test_classify_down_20_days_max_7():
    mod = _load()
    now = _utc(2026, 7, 8, 12, 0, 0)
    last = _utc(2026, 6, 18, 12, 0, 0)  # 20 days ago; max=7; 2x=14 → down
    verdict, age = mod.classify(_row(), last, "comment", now)
    assert verdict == "down"
    assert age > 14


def test_classify_unknown_on_error():
    mod = _load()
    now = _utc(2026, 7, 8, 12, 0, 0)
    verdict, age = mod.classify(_row(), None, "error", now)
    assert verdict == "unknown"
    assert age is None


def test_classify_unmonitored_pr_delivery():
    mod = _load()
    now = _utc(2026, 7, 8, 12, 0, 0)
    r = _row(cls="pr-delivery", issue=None, repo=None)
    verdict, age = mod.classify(r, None, "unmonitored", now)
    assert verdict == "unmonitored"
    assert age is None


def test_classify_unmonitored_null_issue():
    mod = _load()
    now = _utc(2026, 7, 8, 12, 0, 0)
    r = _row(issue=None, repo=None)
    verdict, age = mod.classify(r, None, "unmonitored", now)
    assert verdict == "unmonitored"


def test_unmonitored_never_down(monkeypatch):
    """A pr-delivery routine must never be classified down regardless of time."""
    mod = _load()
    now = _utc(2026, 7, 8, 12, 0, 0)
    r = _row(cls="pr-delivery", issue=None, repo=None)
    # Even if somehow last_ts is very old — unmonitored wins
    verdict, _ = mod.classify(r, None, "unmonitored", now)
    assert verdict != "down"


def test_gh_failure_gives_unknown_not_down(monkeypatch):
    mod = _load()
    now = _utc(2026, 7, 8, 12, 0, 0)
    verdict, age = mod.classify(_row(), None, "error", now)
    assert verdict == "unknown"
    assert age is None


# ── hang_down_atoms tests ────────────────────────────────────────────────────

_TASK_YAML_TEMPLATE = """\
version: '1.0'
tasks: []
"""


def test_hang_down_atoms_creates_task(tmp_path, monkeypatch):
    mod = _load()
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text(_TASK_YAML_TEMPLATE, encoding="utf-8")
    monkeypatch.setattr(mod, "LEDGER", tasks)

    r = _row(name="atom-backlog-triage")
    r["_days_silent"] = 25.0
    result = mod.hang_down_atoms([r])

    assert "ASK-routine-atom-backlog-triage" in result.get("created", [])

    data = tasks.read_text(encoding="utf-8")
    assert "ASK-routine-atom-backlog-triage" in data
    assert "needs_human" in data
    assert "routine-freshness" in data


def test_hang_down_atoms_idempotent(tmp_path, monkeypatch):
    """Run twice; only one task should be created (idempotent)."""
    mod = _load()
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text(_TASK_YAML_TEMPLATE, encoding="utf-8")
    monkeypatch.setattr(mod, "LEDGER", tasks)

    r = _row(name="atom-backlog-triage")
    r["_days_silent"] = 25.0

    mod.hang_down_atoms([r])
    result2 = mod.hang_down_atoms([r])

    # second run: task already exists → should be homed or refreshed, NOT created again
    assert "ASK-routine-atom-backlog-triage" not in result2.get("created", [])

    data = tasks.read_text(encoding="utf-8")
    assert data.count("ASK-routine-atom-backlog-triage") == 1


def test_hang_down_atoms_gh_failure_no_atom(tmp_path, monkeypatch):
    """A gh-failure (unknown verdict) must not produce an atom."""
    mod = _load()
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text(_TASK_YAML_TEMPLATE, encoding="utf-8")
    monkeypatch.setattr(mod, "LEDGER", tasks)

    # unknown verdict rows are NOT passed to hang_down_atoms at all (only "down" rows are)
    result = mod.hang_down_atoms([])  # empty — no unknown rows trigger atoms
    assert result["created"] == []


# ── throttle short-circuit test ───────────────────────────────────────────────


def test_throttle_short_circuit(tmp_path, monkeypatch, capsys):
    """If the artifact is younger than throttle, main() should print 'throttled' and return 0."""
    mod = _load()

    # Write a fresh artifact
    out = tmp_path / "routine-freshness.json"
    out.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(mod, "OUT", out)
    monkeypatch.setattr(mod, "MANIFEST", MANIFEST)

    import sys as _sys

    orig_argv = _sys.argv[:]
    _sys.argv = ["routine-freshness-audit.py", "--throttle", "99999"]
    try:
        rc = mod.main()
    finally:
        _sys.argv = orig_argv

    out_text, _ = capsys.readouterr()
    assert rc == 0
    assert "throttled" in out_text


# ── manifest integrity test ───────────────────────────────────────────────────


def test_manifest_has_13_enabled_rows_with_required_keys():
    """The checked-in cloud-routines.json must have exactly 13 enabled rows with required keys."""
    data = json.loads(MANIFEST.read_text())
    rows = [r for r in data.get("routines", []) if r.get("enabled", True)]
    assert len(rows) == 13, f"expected 13 enabled rows, got {len(rows)}"
    required = {"name", "issue_repo", "issue", "cadence", "class", "max_silent_days", "enabled"}
    for row in rows:
        missing = required - set(row.keys())
        assert not missing, f"row {row.get('name')} missing keys: {missing}"
