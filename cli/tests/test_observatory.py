"""Tests for the OBSERVATORY scaffold spine (build #1).

Hermetic: the ``gh`` boundary and the data directory are redirected to a temp tree
so the organ is exercised by logic, never by the host's network or checkout state.
"""

from __future__ import annotations

import json

import pytest

from limen.observatory import config, doctor, executive, gh, ledger
from limen.observatory import __main__ as obs_main


@pytest.fixture
def obs_root(tmp_path, monkeypatch):
    """Redirect the organ's whole footprint (reads + writes) into tmp_path."""
    monkeypatch.setattr(config, "repo_root", lambda: tmp_path)
    return tmp_path


# ---------------------------------------------------------------- config
def test_value_repos_fail_closed(obs_root):
    # No registry present → empty hero list (fail-CLOSED), never a fabricated target.
    assert config.value_repos() == []


def test_value_repos_reads_registry(obs_root):
    (obs_root / "value-repos.json").write_text(json.dumps({"repos": ["o/a", "o/b"]}))
    assert config.value_repos() == ["o/a", "o/b"]


def test_params_passthrough_default():
    # Unknown key resolves to the caller's default via the shared panel accessor.
    assert config.get("OBSERVATORY_NOPE_NOT_A_PARAM", 5, cast=int) == 5


def test_competitor_seeds_split(monkeypatch):
    monkeypatch.setenv("OBSERVATORY_COMPETITOR_SEEDS", "o/a, o/b ,, o/c")
    assert config.competitor_seeds() == ["o/a", "o/b", "o/c"]


# ---------------------------------------------------------------- gh (fail-open)
def test_gh_offline_fails_open(monkeypatch, obs_root):
    monkeypatch.setenv("LIMEN_OFFLINE", "1")
    assert gh.token() is None
    assert gh.online(None) is False
    assert gh.search_repos("stars:>50", None) == []
    assert gh.repo("o/a", None) is None
    assert gh.releases("o/a", None) == []
    assert gh.rate_headroom_pct(None) is None


# ---------------------------------------------------------------- ledger
def test_jsonl_round_trip(obs_root):
    ledger.append_jsonl("snapshots.jsonl", {"id": "S1", "owner_repo": "o/a"})
    ledger.append_jsonl("snapshots.jsonl", {"id": "S2", "owner_repo": "o/b"})
    rows = ledger.read_jsonl("snapshots.jsonl")
    assert [r["id"] for r in rows] == ["S1", "S2"]
    assert all("ts" in r for r in rows)  # ts stamped on append


def test_read_jsonl_absent_is_empty(obs_root):
    assert ledger.read_jsonl("nope.jsonl") == []


def test_write_latest_is_deterministic(obs_root):
    obj = {"b": 2, "a": 1, "nested": {"y": 9, "x": 8}}
    ledger.write_latest("gap-latest.json", obj)
    first = (obs_root / "logs" / "observatory" / "gap-latest.json").read_text()
    ledger.write_latest("gap-latest.json", obj)  # re-run, same input
    second = (obs_root / "logs" / "observatory" / "gap-latest.json").read_text()
    assert first == second  # idempotent fixed point
    assert json.loads(first) == obj


# ---------------------------------------------------------------- executive
def test_run_beat_scaffold_stages_pending(obs_root):
    # In the scaffold only the spine exists; the pipeline stages report 'pending', never crash.
    status = executive.run_beat(apply=False)
    labels = {s["stage"]: s["status"] for s in status["stages"]}
    assert labels == {"collect": "pending", "analyze": "pending", "reconcile": "pending", "brief": "pending"}
    assert status["apply"] is False
    # status.json + the stamp are written under the redirected data dir.
    assert (obs_root / "logs" / "observatory" / "status.json").exists()
    assert (obs_root / "logs" / "observatory" / "observatory.json").exists()


def test_summary_line(obs_root):
    status = executive.run_beat()
    line = executive.summary_line(status)
    assert line.startswith("observatory:") and "collect=pending" in line


# ---------------------------------------------------------------- doctor
def test_doctor_offline_green(obs_root):
    report = doctor.run(offline=True)
    assert report["ok"] is True
    rungs = {r["rung"]: r for r in report["rungs"]}
    assert rungs["wiring"]["ok"] and not rungs["wiring"]["missing"]
    assert "online" not in rungs  # offline skips the live probe entirely
    assert (obs_root / "logs" / "observatory" / "doctor-latest.json").exists()


def test_doctor_online_probe_skips_when_offline(monkeypatch, obs_root):
    monkeypatch.setenv("LIMEN_OFFLINE", "1")
    report = doctor.run(offline=False)
    online = next(r for r in report["rungs"] if r["rung"] == "online")
    assert online["ok"] and online["status"] == "SKIP"


# ---------------------------------------------------------------- __main__ (always exit 0)
def test_main_doctor_exits_zero(obs_root):
    assert obs_main.main(["doctor", "--offline"]) == 0


def test_main_run_exits_zero(obs_root):
    assert obs_main.main(["run"]) == 0


def test_main_pending_stage_exits_zero(obs_root):
    assert obs_main.main(["reconcile"]) == 0  # stage not built yet → clean, exit 0
