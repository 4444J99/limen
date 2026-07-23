"""Tests for the OBSERVATORY unified brief + human-gated proposal (build #4).

Hermetic: the organ footprint is redirected to a temp tree; evidence is seeded directly.
"""

from __future__ import annotations

import json

import pytest
from limen.observatory import brief, config, ledger, lever


@pytest.fixture
def obs_root(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "repo_root", lambda: tmp_path)
    return tmp_path


def _seed_evidence(root):
    """Seed a gap doc (external), a reconcile doc (internal), mechanisms, and cohorts."""
    ledger.write_latest(
        "gap-latest.json",
        {
            "hero": "organvm/hero",
            "gaps": [
                {"mechanism": "demo_above_fold", "priority": 1.5, "target_component": "activation", "we_have": False}
            ],
        },
    )
    ledger.write_latest(
        "reconcile-latest.json",
        {
            "sensor": "vvltvs",
            "gaps": [
                {"kind": "severed_pipe", "register": "system-vars", "detail": "build_vars dropped", "advisory": False},
                {"kind": "claim_drift", "face": "profile-bio", "metric": "repos", "advisory": False},
            ],
        },
    )
    ledger.append_jsonl("mechanisms.jsonl", {"mechanism": "demo_above_fold", "priority": 1.5, "winner": "o/w"})
    ledger.append_jsonl("mechanisms.jsonl", {"mechanism": "names_user", "priority": 0.9, "winner": "o/w"})
    ledger.append_jsonl(
        "cohorts.jsonl",
        {"winner": "o/w", "confounders": [{"kind": "existing_audience", "evidence": "20k followers", "weight": 0.8}]},
    )


# ---------------------------------------------------------------- selector
def test_internal_severed_pipe_outranks_weak_external(obs_root):
    _seed_evidence(obs_root)
    b = brief.build_brief()
    # severed_pipe (priority 3.6) beats the external demo_above_fold (1.5) → it's the experiment.
    assert b["experiment"]["kind"] == "severed_pipe"
    assert "system-vars" in b["experiment"]["change"]


def test_brief_shape_is_complete(obs_root):
    _seed_evidence(obs_root)
    b = brief.build_brief()
    assert b["hero"] == "organvm/hero"
    assert len(b["mechanisms"]) == 2 and b["mechanisms"][0]["mechanism"] == "demo_above_fold"  # ranked
    assert len(b["confounders"]) == 1 and b["confounders"][0]["kind"] == "existing_audience"
    assert b["experiment"] and b["measurement_contract"]
    mc = b["measurement_contract"]
    assert "reversal_path" in mc and "failure_criterion" in mc and mc["observation_window_days"] >= 1


def test_no_gaps_yields_no_experiment(obs_root):
    ledger.write_latest("gap-latest.json", {"hero": None, "gaps": []})
    ledger.write_latest("reconcile-latest.json", {"gaps": []})
    b = brief.build_brief()
    assert b["experiment"] is None
    md = brief.render_markdown(b)
    assert "no experiment" in md.lower()


def test_external_gap_selected_when_no_internal(obs_root):
    ledger.write_latest(
        "gap-latest.json",
        {"hero": "organvm/hero", "gaps": [{"mechanism": "names_user", "priority": 5.0, "we_have": False}]},
    )
    ledger.write_latest("reconcile-latest.json", {"gaps": []})
    b = brief.build_brief()
    assert b["experiment"]["face"] if "face" in b["experiment"] else True
    assert "names_user" in b["experiment"]["change"]
    # An external gap carries no VVLTVS kind — the experiment self-describes as a transfer.
    assert b["experiment"]["kind"] == "mechanism_transfer"


def test_brief_date_defaults_to_today(obs_root):
    _seed_evidence(obs_root)
    assert brief.build_brief()["date"] == lever._today()
    assert brief.build_brief(date="2026-01-01")["date"] == "2026-01-01"  # the test seam still wins


# ---------------------------------------------------------------- lever (human-gated proposal)
def test_propose_dry_writes_only_proposals_ledger(obs_root):
    _seed_evidence(obs_root)
    b = brief.build_brief()
    result = lever.propose(b, apply=False)
    assert result["proposed"] and result["armed"] is False and result["lever_homed"] is False
    # only the organ-owned proposals ledger is written; no his-hand-levers.json created/touched.
    assert (obs_root / "logs" / "observatory" / "proposals.jsonl").exists()
    assert not (obs_root / "his-hand-levers.json").exists()


def test_propose_apply_homes_lever_idempotently(obs_root):
    (obs_root / "his-hand-levers.json").write_text(json.dumps({"levers": []}))
    _seed_evidence(obs_root)
    b = brief.build_brief()
    first = lever.propose(b, apply=True)
    assert first["armed"] and first["lever_homed"] is True
    doc = json.loads((obs_root / "his-hand-levers.json").read_text())
    assert any(x["id"] == "L-OBS-EXP" for x in doc["levers"])  # homed
    # second apply is idempotent — same id, no duplicate append
    second = lever.propose(b, apply=True)
    assert second["lever_homed"] is False
    doc2 = json.loads((obs_root / "his-hand-levers.json").read_text())
    assert sum(1 for x in doc2["levers"] if x["id"] == "L-OBS-EXP") == 1


def test_run_brief_writes_face_and_proposes(obs_root):
    _seed_evidence(obs_root)
    summary = brief.run(apply=False)
    assert summary["has_experiment"] and summary["proposed"] and summary["armed"] is False
    d = obs_root / "logs" / "observatory"
    assert (d / "brief-latest.json").exists() and (d / "brief-latest.md").exists()
    assert (d / "briefs.jsonl").exists()
    md = (d / "brief-latest.md").read_text()
    assert "OBSERVATORY — daily brief" in md
