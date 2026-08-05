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
    path.write_text(yaml.safe_dump({"version": "1.0", "portal": {"name": "t"}, "tasks": []}, sort_keys=False))


# canned PR universe: one CI-RED, one CONFLICT, one READY, one CI-PENDING.
_PRS = [
    {"number": 54, "repository": {"nameWithOwner": "organvm/exporter"}, "url": "u/54"},
    {"number": 6, "repository": {"nameWithOwner": "organvm/scale"}, "url": "u/6"},
    {"number": 9, "repository": {"nameWithOwner": "organvm/ready"}, "url": "u/9"},
    {"number": 7, "repository": {"nameWithOwner": "organvm/pending"}, "url": "u/7"},
]
_VIEW = {
    54: {
        "state": "OPEN",
        "isDraft": False,
        "mergeable": "MERGEABLE",
        "statusCheckRollup": [{"name": "e2e", "conclusion": "FAILURE"}],
    },  # CI-RED
    6: {
        "state": "OPEN",
        "isDraft": False,
        "mergeable": "CONFLICTING",
        "statusCheckRollup": [{"conclusion": "SUCCESS"}],
    },  # CONFLICT
    9: {
        "state": "OPEN",
        "isDraft": False,
        "mergeable": "MERGEABLE",
        "statusCheckRollup": [{"conclusion": "SUCCESS"}],
    },  # READY
    7: {
        "state": "OPEN",
        "isDraft": False,
        "mergeable": "MERGEABLE",
        "statusCheckRollup": [{"conclusion": None, "state": "PENDING"}],
    },  # CI-PENDING
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


def test_malformed_numeric_env_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_HEAL_SCAN", "bad")
    monkeypatch.setenv("LIMEN_HEAL_SCAN_MAX", "bad")
    monkeypatch.setenv("LIMEN_HEAL_LIMIT", "bad")
    m = _load(tmp_path, monkeypatch)
    p = tmp_path / "tasks.yaml"
    _board(p)

    rc = _run(m, monkeypatch, p, "--dry-run")

    assert rc == 0
    assert not (tmp_path / "logs" / ".queue.lock.d").exists()


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


def test_fresh_live_chronic_repo_check_freezes_repeat_heal(tmp_path, monkeypatch, capsys):
    m = _load(tmp_path, monkeypatch)
    p = tmp_path / "tasks.yaml"
    _board(p)
    m.HEAL_CONVERGENCE.write_text(
        json.dumps(
            {
                "timestamp": m.datetime.datetime.now(m.datetime.timezone.utc).isoformat(),
                "chronic": [{"repo": "organvm/exporter", "check": "e2e", "prs": ["u/1", "u/2", "u/3"]}],
            }
        ),
        encoding="utf-8",
    )

    assert _run(m, monkeypatch, p) == 0
    ids = {task["id"] for task in yaml.safe_load(p.read_text())["tasks"]}
    assert "HEAL-cifix-organvm-exporter-54" not in ids
    assert "HEAL-rebase-organvm-scale-6" in ids
    assert "chronic-frozen=1" in capsys.readouterr().out


def test_stale_chronic_receipt_cannot_freeze_current_work(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    p = tmp_path / "tasks.yaml"
    _board(p)
    stale = m.datetime.datetime.now(m.datetime.timezone.utc) - m.datetime.timedelta(days=1)
    m.HEAL_CONVERGENCE.write_text(
        json.dumps({"timestamp": stale.isoformat(), "chronic": [{"repo": "organvm/exporter", "check": "e2e"}]}),
        encoding="utf-8",
    )

    assert _run(m, monkeypatch, p) == 0
    ids = {task["id"] for task in yaml.safe_load(p.read_text())["tasks"]}
    assert "HEAL-cifix-organvm-exporter-54" in ids


def test_future_dated_chronic_receipt_cannot_freeze_current_work(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    p = tmp_path / "tasks.yaml"
    _board(p)
    future = m.datetime.datetime.now(m.datetime.timezone.utc) + m.datetime.timedelta(days=1)
    m.HEAL_CONVERGENCE.write_text(
        json.dumps({"timestamp": future.isoformat(), "chronic": [{"repo": "organvm/exporter", "check": "e2e"}]}),
        encoding="utf-8",
    )

    assert _run(m, monkeypatch, p) == 0
    ids = {task["id"] for task in yaml.safe_load(p.read_text())["tasks"]}
    assert "HEAL-cifix-organvm-exporter-54" in ids


def test_chronic_check_cannot_hide_a_distinct_new_failure(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    p = tmp_path / "tasks.yaml"
    _board(p)
    monkeypatch.setitem(
        _VIEW,
        54,
        {
            "state": "OPEN",
            "isDraft": False,
            "mergeable": "MERGEABLE",
            "statusCheckRollup": [
                {"name": "e2e", "conclusion": "FAILURE"},
                {"name": "lint", "conclusion": "FAILURE"},
            ],
        },
    )
    m.HEAL_CONVERGENCE.write_text(
        json.dumps(
            {
                "timestamp": m.datetime.datetime.now(m.datetime.timezone.utc).isoformat(),
                "chronic": [{"repo": "organvm/exporter", "check": "e2e"}],
            }
        ),
        encoding="utf-8",
    )

    assert _run(m, monkeypatch, p) == 0
    ids = {task["id"] for task in yaml.safe_load(p.read_text())["tasks"]}
    assert "HEAL-cifix-organvm-exporter-54" in ids


def test_explicit_pr_bypasses_rotating_search_window(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    p = tmp_path / "tasks.yaml"
    _board(p)

    def fake_gh(args, timeout=60):
        if args[:2] == ["search", "prs"]:
            raise AssertionError("explicit --pr must not enumerate the rotating search window")
        return _fake_gh(args, timeout=timeout)

    monkeypatch.setattr(m, "gh", fake_gh)
    monkeypatch.setattr(sys, "argv", ["self-heal", "--tasks", str(p), "--pr", "organvm/scale#6"])

    assert m.main() == 0
    ids = {t["id"] for t in yaml.safe_load(p.read_text())["tasks"]}
    assert ids == {"HEAL-rebase-organvm-scale-6"}


def test_conflict_wins_over_stale_failing_checks(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    p = tmp_path / "tasks.yaml"
    _board(p)

    def fake_gh(args, timeout=60):
        if args[:2] == ["search", "prs"]:
            raise AssertionError("explicit --pr must not enumerate the rotating search window")
        if args[:2] == ["pr", "view"]:
            return _R(
                json.dumps(
                    {
                        "state": "OPEN",
                        "isDraft": False,
                        "mergeable": "CONFLICTING",
                        "statusCheckRollup": [{"conclusion": "FAILURE"}],
                    }
                )
            )
        return _R("[]")

    monkeypatch.setattr(m, "gh", fake_gh)
    monkeypatch.setattr(sys, "argv", ["self-heal", "--tasks", str(p), "--pr", "organvm/domus-genoma#185"])

    assert m.main() == 0
    ids = {t["id"] for t in yaml.safe_load(p.read_text())["tasks"]}
    assert ids == {"HEAL-rebase-organvm-domus-genoma-185"}


def test_releases_queue_lock_after_live_pass(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    p = tmp_path / "tasks.yaml"
    _board(p)
    _run(m, monkeypatch, p)
    assert not (tmp_path / "logs" / ".queue.lock.d").exists(), "live pass must release the lock"


# ── STALE-BASE GATE (the #111 guard) ────────────────────────────────────────────────────────────
# A mergeable+green PR that touches the daemon body from a STALE base must NOT be treated as READY —
# it would silently revert work (#111). self-heal reroutes it to a rebase-onto-current task.
_STALE_PRS = [
    {"number": 11, "repository": {"nameWithOwner": "organvm/limen"}, "url": "u/11"},
]
_STALE_VIEW = {
    11: {
        "state": "OPEN",
        "isDraft": False,
        "mergeable": "MERGEABLE",
        "statusCheckRollup": [{"conclusion": "SUCCESS"}],  # green + mergeable …
        "files": [{"path": "cli/src/limen/dispatch.py", "additions": 1, "deletions": 375}],
        "baseRefName": "main",
        "headRefOid": "deadbeef",
    },  # … but touches the body
}


def _fake_gh_stale(args, timeout=60):
    if args[:2] == ["search", "prs"]:
        return _R(json.dumps(_STALE_PRS))
    if args[:2] == ["pr", "view"]:
        return _R(json.dumps(_STALE_VIEW[int(args[2])]))
    if args and args[0] == "api":  # gh api …compare… --jq .behind_by  → 5 commits behind
        return _R("5")
    return _R("[]")


def test_stale_core_pr_emits_rebase_not_merged(tmp_path, monkeypatch):
    for k in ("LIMEN_PROTECTED_PATHS", "LIMEN_CONDUCTOR_REPOS", "LIMEN_STALE_BASE_MAX"):
        monkeypatch.delenv(k, raising=False)
    m = _load(tmp_path, monkeypatch)
    p = tmp_path / "tasks.yaml"
    _board(p)
    monkeypatch.setattr(m, "gh", _fake_gh_stale)
    monkeypatch.setattr(sys, "argv", ["self-heal", "--tasks", str(p)])
    assert m.main() == 0
    doc = yaml.safe_load(p.read_text())
    ids = {t["id"] for t in doc["tasks"]}
    assert ids == {"HEAL-rebase-stale-organvm-limen-11"}, "stale-core PR → one rebase-stale heal task"
    t = doc["tasks"][0]
    assert "stale-base" in t["labels"] and "core" in t["labels"]
    assert "REVERT" in t["context"] and "force-with-lease" in t["context"]
    assert "unique work" in t["context"], "the heal must preserve all unique work (absorb, not drop)"


def test_stale_core_pr_with_active_queue_emits_no_rebase(tmp_path, monkeypatch):
    """A positive queue capability routes stale exact heads to merge-drain, not branch churn."""
    for k in ("LIMEN_PROTECTED_PATHS", "LIMEN_CONDUCTOR_REPOS", "LIMEN_STALE_BASE_MAX"):
        monkeypatch.delenv(k, raising=False)
    m = _load(tmp_path, monkeypatch)
    p = tmp_path / "tasks.yaml"
    _board(p)
    monkeypatch.setattr(m, "gh", _fake_gh_stale)
    monkeypatch.setattr(m, "merge_queue_capability", lambda repo, branch, gh_fn: "active")
    monkeypatch.setattr(sys, "argv", ["self-heal", "--tasks", str(p)])

    assert m.main() == 0
    assert yaml.safe_load(p.read_text())["tasks"] == []


# ── TRUNK-REPAIR GATE (limen#895) ───────────────────────────────────────────────────────────────────
# When a HEAL-mainred-{repo} task is active, self-heal must NOT emit individual HEAL-cifix tasks for
# that same repo — the trunk-level repair addresses the root cause and heals all PRs at once.


def test_skips_cifix_when_trunk_repair_active(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    p = tmp_path / "tasks.yaml"
    # Pre-seed an active HEAL-mainred task for organvm/exporter (same repo as PR #54)
    board = {
        "version": "1.0",
        "portal": {"name": "t"},
        "tasks": [
            {
                "id": "HEAL-mainred-organvm-exporter",
                "title": "Restore main to green — organvm/exporter CI is RED",
                "repo": "organvm/exporter",
                "status": "open",
                "target_agent": "any",
                "priority": "critical",
                "labels": ["lifecycle", "ci", "mainred"],
                "urls": [],
                "context": "main CI is red",
                "depends_on": [],
                "created": "2026-07-12",
                "dispatch_log": [],
            }
        ],
    }
    p.write_text(yaml.safe_dump(board, sort_keys=False))
    rc = _run(m, monkeypatch, p)
    assert rc == 0
    doc = yaml.safe_load(p.read_text())
    ids = {t["id"] for t in doc["tasks"]}
    # PR #54 (organvm/exporter, CI-RED) must NOT get a cifix task — trunk repair covers it
    assert "HEAL-cifix-organvm-exporter-54" not in ids, (
        "must skip PR-level CI fix when trunk-level HEAL-mainred is active"
    )
    # The HEAL-mainred task must still be present
    assert "HEAL-mainred-organvm-exporter" in ids
    # Non-exporter PRs should still get their heal tasks
    assert "HEAL-rebase-organvm-scale-6" in ids


def test_emits_cifix_when_trunk_repair_done(tmp_path, monkeypatch):
    """When the prior HEAL-mainred task is done (healed), a new CI-RED PR should still get a cifix."""
    m = _load(tmp_path, monkeypatch)
    p = tmp_path / "tasks.yaml"
    board = {
        "version": "1.0",
        "portal": {"name": "t"},
        "tasks": [
            {
                "id": "HEAL-mainred-organvm-exporter",
                "title": "Restore main to green — organvm/exporter CI is RED",
                "repo": "organvm/exporter",
                "status": "done",
                "target_agent": "any",
                "priority": "critical",
                "labels": ["lifecycle", "ci", "mainred"],
                "urls": [],
                "context": "previous red episode healed",
                "depends_on": [],
                "created": "2026-07-11",
                "dispatch_log": [],
            }
        ],
    }
    p.write_text(yaml.safe_dump(board, sort_keys=False))
    rc = _run(m, monkeypatch, p)
    assert rc == 0
    doc = yaml.safe_load(p.read_text())
    ids = {t["id"] for t in doc["tasks"]}
    # PR #54 should get a cifix even though old HEAL-mainred exists — it's done
    assert "HEAL-cifix-organvm-exporter-54" in ids, (
        "must still emit PR-level CI fix when prior trunk-level HEAL is done"
    )
    assert "HEAL-mainred-organvm-exporter" in ids
