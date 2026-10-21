"""Tests for scripts/residue-census.py — the measurable half of the Meeseeks law.

The census exists because the hot-cache court could not see the residue it deliberately steps over.
Two properties keep it honest:

1. It is READ-ONLY. A measurement organ that can delete is a reaper wearing a census's name, and
   the destructive relief here (archive-then-delete of 10 GiB, the remote-reap lever) is
   human-gated for good reasons. `test_census_is_read_only` is the guard.
2. An UNMEASURABLE class is never a breach. The census runs on hosts where a path may be absent
   (a worktree, a fresh clone, CI); reading "absent" as "over cap" would make it cry wolf exactly
   where it knows least.
"""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("residue_census", ROOT / "scripts" / "residue-census.py")
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)


def _rows(monkeypatch, rows):
    monkeypatch.setattr(rc, "classes", lambda: rows)


def test_within_cap_is_not_a_breach(monkeypatch):
    _rows(monkeypatch, [{"id": "x", "unit": "count", "what": "w", "value": 3, "cap": 8, "owner": "o"}])
    r = rc.census()
    assert r["breaches"] == 0
    assert r["rows"][0]["state"] == "within"


def test_over_cap_is_a_breach(monkeypatch):
    _rows(monkeypatch, [{"id": "x", "unit": "count", "what": "w", "value": 39, "cap": 8, "owner": "o"}])
    r = rc.census()
    assert r["breaches"] == 1
    assert r["rows"][0]["state"] == "BREACH"


def test_unmeasured_is_never_a_breach(monkeypatch):
    """A path this host does not have is unknown, not over budget — the census must not cry wolf
    where it knows least (worktrees, fresh clones and CI all lack .agent-runtime)."""
    _rows(monkeypatch, [{"id": "x", "unit": "MiB", "what": "w", "value": None, "cap": 128, "owner": "o"}])
    r = rc.census()
    assert r["breaches"] == 0
    assert r["unmeasured"] == 1
    assert r["rows"][0]["state"] == "unmeasured"


def test_report_only_counts_but_never_breaches(monkeypatch):
    """Remote branches are over cap by 16x and their relief is double-dark behind a filed lever.
    A predicate permanently red on something it may not act on is a predicate nobody reads."""
    _rows(
        monkeypatch,
        [{"id": "remote", "unit": "count", "what": "w", "value": 1616, "cap": 100, "owner": "o", "report_only": True}],
    )
    r = rc.census()
    assert r["breaches"] == 0
    assert r["rows"][0]["state"] == "over-report-only"


def test_caps_are_env_overridable(monkeypatch):
    """Caps live in the parameter panel, so tightening one is a registry edit, not a code edit."""
    monkeypatch.setenv("LIMEN_RESIDUE_WORKTREES", "999")
    cap = next(c["cap"] for c in rc.classes() if c["id"] == "worktrees")
    assert cap == 999


def test_bad_env_falls_back_to_the_declared_default(monkeypatch):
    monkeypatch.setenv("LIMEN_RESIDUE_WORKTREES", "not-a-number")
    assert next(c["cap"] for c in rc.classes() if c["id"] == "worktrees") == 8


# --- the read-only guarantee -------------------------------------------------
def test_census_is_read_only():
    """No delete/move/write verb may appear in the source. Relief belongs to the reap organs, and
    where it is destructive it belongs to his hand — this organ only ever knows."""
    src = (ROOT / "scripts" / "residue-census.py").read_text(encoding="utf-8")
    body = src.split('"""', 2)[-1]  # skip the module docstring, which discusses deleting
    for verb in ("shutil.rmtree", "os.remove", "os.unlink", ".write_text(", ".unlink(", "rm -rf"):
        assert verb not in body, f"the census must not {verb} — it measures, it does not reap"


def test_subprocess_calls_are_measurement_only():
    src = (ROOT / "scripts" / "residue-census.py").read_text(encoding="utf-8")
    body = src.split('"""', 2)[-1]
    assert "subprocess.run" in body
    for arg in ('"worktree", "remove"', '"branch", "-D"', '"push"', '"reset"'):
        assert arg not in body


# --- every declared class is well-formed -------------------------------------
@pytest.mark.parametrize("field", ["id", "unit", "what", "cap", "owner"])
def test_every_class_declares_its_shape(field):
    for c in rc.classes():
        assert c.get(field) not in (None, ""), f"{c.get('id')} is missing {field}"


def test_every_breach_names_an_owner():
    """The whole point is that a breach routes somewhere. An ownerless breach is a chat list."""
    for c in rc.classes():
        assert len(c["owner"]) > 10, f"{c['id']} owner is too thin to route to"


# --- the measured root is the live tree, never the runtime the code runs from ---
def test_explicit_limen_root_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    assert rc.measured_root() == tmp_path


def test_git_checkout_measures_itself(monkeypatch, tmp_path):
    """Development, CI and worktree runs keep measuring the checkout they run from."""
    monkeypatch.delenv("LIMEN_ROOT", raising=False)
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(rc, "CODE_ROOT", tmp_path)
    assert rc.measured_root() == tmp_path


def test_immutable_runtime_measures_the_live_checkout(monkeypatch, tmp_path):
    """The heartbeat runs from a worktree-free runtime source with no .git. Measuring that tree
    reported 'nothing is sprawling' while the live checkout held 29 worktrees (2026-10-17)."""
    monkeypatch.delenv("LIMEN_ROOT", raising=False)
    runtime_source = tmp_path / "runtimes" / "abc" / "source"
    runtime_source.mkdir(parents=True)
    live = tmp_path / "live"
    monkeypatch.setattr(rc, "CODE_ROOT", runtime_source)
    monkeypatch.setattr(rc, "LIVE_ROOT_DEFAULT", live)
    assert rc.measured_root() == live


def test_blind_census_is_reported_not_clean(monkeypatch, tmp_path):
    """A root with no git state cannot count worktrees or branches; that is blindness, and --check
    must fail rather than print 'every cap holds'."""
    _rows(monkeypatch, [{"id": "x", "unit": "count", "what": "w", "value": None, "cap": 8, "owner": "o"}])
    monkeypatch.setattr(rc, "ROOT", tmp_path)
    r = rc.census()
    assert r["blind"] is True
    assert r["breaches"] == 0
    monkeypatch.setattr(rc.sys, "argv", ["residue-census.py", "--check"])
    assert rc.main() == 1


def test_sighted_census_without_breach_passes_check(monkeypatch, tmp_path):
    _rows(monkeypatch, [{"id": "x", "unit": "count", "what": "w", "value": 1, "cap": 8, "owner": "o"}])
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(rc, "ROOT", tmp_path)
    assert rc.census()["blind"] is False
    monkeypatch.setattr(rc.sys, "argv", ["residue-census.py", "--check"])
    assert rc.main() == 0


def test_du_walks_fit_inside_the_heartbeat_probe_timeout():
    """Three du walks at the default per-walk timeout must stay under the contract's 90s probe
    timeout; a probe timeout is a system failure that feeds the heartbeat kill switch."""
    import json

    contracts = json.loads((ROOT / "spec" / "scheduled-process-contracts.json").read_text(encoding="utf-8"))
    probe = next(p for p in contracts["processes"]["com.limen.heartbeat"]["probes"] if p["name"] == "residue-census")
    du_classes = sum(1 for c in rc.classes() if c["unit"] == "MiB")
    assert du_classes * rc._env_int("LIMEN_RESIDUE_DU_TIMEOUT", 25) < probe["timeout_seconds"]


def test_du_timeout_is_unmeasured_not_a_breach(monkeypatch, tmp_path):
    def slow(*_args, **_kwargs):
        raise rc.subprocess.TimeoutExpired(cmd="du", timeout=1)

    monkeypatch.setattr(rc.subprocess, "run", slow)
    assert rc._du_kb(tmp_path) is None


def test_live_census_runs_and_classifies_everything():
    r = rc.census()
    assert r["rows"], "no residue classes declared"
    assert all(row["state"] in {"within", "BREACH", "over-report-only", "unmeasured"} for row in r["rows"])
