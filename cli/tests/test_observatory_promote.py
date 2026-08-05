"""Tests for OBSERVATORY P-PROMOTE — experiment→board via the tabularius single-writer (lever.py).

Hermetic: temp repo root; the ticket inbox is asserted directly. Confirms the reversible-prep task
validates as a real Task, lands as an inbox ticket ONLY when armed, and never writes tasks.yaml.
"""

from __future__ import annotations

import glob
import json

import pytest

from limen.models import Task
from limen.observatory import config, lever


def _brief():
    return {
        "hero": "o/hero",
        "experiment": {
            "id": "L-OBS-EXP",
            "task_id": "OBS-EXP",
            "change": "Add names_outcome to the hero's first screen.",
            "revert": "git revert",
            "measure_hint": "activation proxy over the window vs baseline",
            "measurement_contract": {"metric_vector": ["activation", "reach"], "observation_window_days": 14},
        },
    }


@pytest.fixture
def obs_root(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "repo_root", lambda: tmp_path)
    (tmp_path / "logs" / "observatory").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _inbox(root):
    return glob.glob(str(root / "logs" / "tickets" / "inbox" / "*.json"))


def test_to_task_validates_as_a_real_task():
    task = lever.to_task(_brief()["experiment"], "o/hero")
    t = Task.model_validate(task)  # must not raise
    assert t.id == "OBS-EXP" and t.target_agent == "any" and t.status == "open"


def test_promote_writes_one_ticket_when_armed(obs_root):
    r = lever.propose(_brief(), apply=True)
    assert r["task_promoted"] is True
    tickets = _inbox(obs_root)
    assert len(tickets) == 1
    ticket = json.loads(open(tickets[0]).read())
    assert ticket.get("task_id") == "OBS-EXP" or ticket.get("patch", {}).get("id") == "OBS-EXP"
    # the board file itself is never written by the organ (single-writer invariant)
    assert not (obs_root / "tasks.yaml").exists()


def test_no_ticket_when_not_armed(obs_root):
    r = lever.propose(_brief(), apply=False)
    assert r["task_promoted"] is False
    assert not _inbox(obs_root)


def test_promote_fail_open_on_invalid_task(obs_root):
    assert lever._promote_task({"id": ""}) is False  # invalid task → caught, no crash, no ticket
    assert not _inbox(obs_root)
