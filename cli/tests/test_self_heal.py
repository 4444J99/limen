"""Tests for the SELF-HEAL organ (scripts/self-heal.py): the CI-RED / CONFLICT classifier and the
SAFE, IDEMPOTENT heal-task emitter. gh is mocked so no network. Asserts the safety properties that
matter because it runs autonomously in the heartbeat:
(1) it classifies stuck PRs exactly like merge-drain (CI-RED → cifix, CONFLICT → rebase),
(2) --dry-run makes ZERO writes (file untouched, no queue-lock dir),
(3) a live pass appends validated tasks via the atomic shared-append path (load → append → save),
(4) it is IDEMPOTENT — a second run emits no duplicate for a PR that already has a heal task,
(5) it respects the per-run --limit cap.
"""
import importlib.util
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "self-heal.py"


def _load(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    (tmp_path / "logs").mkdir(exist_ok=True)
    spec = importlib.util.spec_from_file_location("self_heal_uut", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _board(path):
    path.write_text(yaml.safe_dump(
        {"version": "1.0", "portal": {"name": "t"}, "tasks": []}, sort_keys=False))


# canned PR universe: one CI-RED, one CONFLICT, one READY, one CI-PENDING.
_PRS = [
    {"number": 54, "repository": {"nameWithOwner": "organvm/exporter"}, "url": "u/54"},
    {"number": 6, "repository": {"nameWithOwner": "organvm/scale"}, "url": "u/6"},
    {"number": 9, "repository": {"nameWithOwner": "organvm/ready"}, "url": "u/9"},
    {"number": 7, "repository": {"nameWithOwner": "organvm/pending"}, "url": "u/7"},
]
_VIEW = {
    54: {"state": "OPEN", "isDraft": False, "mergeable": "MERGEABLE",
         "statusCheckRollup": [{"conclusion": "FAILURE"}]},                 # CI-RED
    6: {"state": "OPEN", "isDraft": False, "mergeable": "CONFLICTING",
        "statusCheckRollup": [{"conclusion": "SUCCESS"}]},                  # CONFLICT
    9: {"state": "OPEN", "isDraft": False, "mergeable": "MERGEABLE",
        "statusCheckRollup": [{"conclusion": "SUCCESS"}]},                  # READY
    7: {"state": "OPEN", "isDraft": False, "mergeable": "MERGEABLE",
        "statusCheckRollup": [{"conclusion": None, "state": "PENDING"}]},   # CI-PENDING
}


class _R:
    def __init__(self, out):
        self.returncode = 0
        self.stdout = out
        self.stderr = ""


def _fake_gh(args, timeout=60):
    # `gh search prs …`  → the PR list ;  `gh pr view <n> …` → that PR's detail
    if args[:2] == ["search", "prs"]:
        return _R(json.dumps(_PRS))
    if args[:2] == ["pr", "view"]:
        return _R(json.dumps(_VIEW[int(args[2])]))
    return _R("[]")


def _run(m, monkeypatch, tasks_path, *argv):
    monkeypatch.setattr(m, "gh", _fake_gh)
    monkeypatch.setattr(sys, "argv", ["self-heal", "--tasks", str(tasks_path), *argv])
    return m.main()


def test_classifies_and_emits_cifix_and_rebase(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    p = tmp_path / "tasks.yaml"
    _board(p)
    rc = _run(m, monkeypatch, p)
    assert rc == 0
    doc = yaml.safe_load(p.read_text())
    ids = {t["id"] for t in doc["tasks"]}
    # CI-RED PR → cifix task ; CONFLICT PR → rebase task ; READY/PENDING → nothing.
    assert "HEAL-cifix-organvm-exporter-54" in ids
    assert "HEAL-rebase-organvm-scale-6" in ids
    assert len(ids) == 2, "only the CI-RED and CONFLICT PRs should produce heal tasks"
    cifix = next(t for t in doc["tasks"] if t["id"] == "HEAL-cifix-organvm-exporter-54")
    assert "cifix" in cifix["labels"] and "self-heal" in cifix["labels"]
    assert cifix["target_agent"] == "any" and cifix["status"] == "open"


def test_dry_run_makes_zero_writes(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    p = tmp_path / "tasks.yaml"
    _board(p)
    before = p.read_text()
    rc = _run(m, monkeypatch, p, "--dry-run")
    assert rc == 0
    assert p.read_text() == before, "dry-run must not mutate tasks.yaml"
    assert not (tmp_path / "logs" / ".queue.lock.d").exists(), "dry-run must not touch the queue lock"


def test_idempotent_no_duplicate_on_rerun(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    p = tmp_path / "tasks.yaml"
    _board(p)
    _run(m, monkeypatch, p)
    first = len(yaml.safe_load(p.read_text())["tasks"])
    _run(m, monkeypatch, p)  # second pass, same sick PRs
    second = len(yaml.safe_load(p.read_text())["tasks"])
    assert first == second == 2, "re-running must not emit duplicate heal tasks"


def test_respects_limit_cap(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    p = tmp_path / "tasks.yaml"
    _board(p)
    _run(m, monkeypatch, p, "--limit", "1")
    assert len(yaml.safe_load(p.read_text())["tasks"]) == 1, "must emit at most --limit tasks"


def test_releases_queue_lock_after_live_pass(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    p = tmp_path / "tasks.yaml"
    _board(p)
    _run(m, monkeypatch, p)
    assert not (tmp_path / "logs" / ".queue.lock.d").exists(), "live pass must release the lock"
