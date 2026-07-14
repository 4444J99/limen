"""Hermetic contract tests for the cross-session handoff relay."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "handoff-relay.py"


def _load():
    spec = importlib.util.spec_from_file_location("handoff_relay", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _configure(mod, monkeypatch, tmp_path, board):
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text(yaml.safe_dump(board, sort_keys=False), encoding="utf-8")
    logs = tmp_path / "logs"
    logs.mkdir()
    usage = logs / "usage.json"
    usage.write_text(
        json.dumps(
            {
                "generated": "2026-07-12T12:00:00+00:00",
                "vendors": {
                    "codex": {
                        "remaining": 3,
                        "health": "ok",
                        "headroom_pct": 30,
                        "resets_at": 1783885841,
                    },
                    "gemini": {"remaining": 0, "health": "exhausted"},
                },
            }
        ),
        encoding="utf-8",
    )
    overnight = logs / "overnight-watch.out.log"
    overnight.write_text("watch ok spent=1/100\n", encoding="utf-8")
    monkeypatch.setattr(mod, "TASKS", tasks)
    monkeypatch.setattr(mod, "HANDOFF", logs / "handoff.json")
    monkeypatch.setattr(mod, "USAGE", usage)
    monkeypatch.setattr(mod, "OVERNIGHT", overnight)
    monkeypatch.setattr(mod, "SELF_HEAL", logs / "self-heal.log")
    monkeypatch.setattr(mod, "_now", lambda: dt.datetime(2026, 7, 12, 12, 5, tzinfo=dt.timezone.utc))
    return logs


def _board(tasks):
    return {
        "version": "1.0",
        "portal": {
            "budget": {
                "daily": 10,
                "unit": "runs",
                "per_agent": {"codex": 5, "gemini": 10},
                "track": {
                    "date": "2026-07-12",
                    "spent": 3,
                    "per_agent": {"codex": 2, "gemini": 1},
                    "per_agent_reset": {"codex": "2026-07-12T10:00:00+00:00"},
                },
            }
        },
        "tasks": tasks,
    }


def _task(task_id, *, priority="medium", agent="codex", **extra):
    return {
        "id": task_id,
        "title": task_id,
        "repo": "organvm/limen",
        "target_agent": agent,
        "priority": priority,
        "budget_cost": 1,
        "status": "open",
        "labels": [],
        "depends_on": [],
        "dispatch_log": [],
        **extra,
    }


def test_build_splits_ostensible_from_dispatchable_and_preserves_aliases(monkeypatch, tmp_path):
    mod = _load()
    blocked = _task("BLOCKED", priority="high", agent="gemini")
    ready = _task("READY", priority="medium", agent="codex", budget_cost=2)
    _configure(mod, monkeypatch, tmp_path, _board([blocked, ready]))

    payload = mod.build()

    assert payload["ostensible_next"]["id"] == "BLOCKED"
    assert payload["dispatchable_next"]["id"] == "READY"
    assert payload["next_action"] == payload["ostensible_next"]
    assert payload["board_budget"] == {
        "daily": 10,
        "unit": "runs",
        "track_date": "2026-07-12",
        "spent": 3,
        "remaining": 7,
        "per_agent": {
            "codex": {
                "cap": 5,
                "spent": 2,
                "remaining": 3,
                "reset_at": "2026-07-12T10:00:00+00:00",
            },
            "gemini": {"cap": 10, "spent": 1, "remaining": 7, "reset_at": None},
        },
    }
    assert payload["provider_headroom"]["generated"] == "2026-07-12T12:00:00+00:00"
    assert payload["provider_headroom"]["vendors"]["gemini"]["remaining"] == 0
    assert payload["provider_headroom"]["vendors"]["gemini"]["health"] == "exhausted"
    assert payload["provider_headroom"]["vendors"]["codex"]["resets_at"] == 1783885841
    assert payload["budget_remaining"]["overnight_spent"] == 1
    assert payload["budget_remaining"]["overnight_cap"] == 100


def test_dispatchable_next_applies_terminal_dependency_budget_and_human_gates():
    mod = _load()
    dependency = _task(
        "DEP",
        status="done",
        dispatch_log=[{"status": "done", "output": "PR merged into main"}],
    )
    tasks = [
        _task("TERMINAL", priority="critical", dispatch_log=[{"status": "done"}]),
        _task("HUMAN", priority="critical", labels=["needs-human"]),
        _task("TOO-COSTLY", priority="high", budget_cost=5),
        _task("WAITING", priority="high", depends_on=["MISSING"]),
        _task("READY", priority="medium", depends_on=["DEP"]),
        dependency,
    ]
    budget = {"remaining": 3, "per_agent": {"codex": {"remaining": 3}}}
    providers = {"generated": "now", "vendors": {"codex": {"remaining": 2}}}

    assert mod._dispatchable_next(tasks, budget, providers)["id"] == "READY"


def test_dispatchable_next_rejects_live_low_health_even_with_remaining_capacity():
    mod = _load()
    tasks = [_task("LOW", priority="high", agent="jules"), _task("READY", agent="codex")]
    budget = {"remaining": 3, "per_agent": {}}
    providers = {
        "generated": "now",
        "vendors": {
            "jules": {"remaining": 5, "health": "low"},
            "codex": {"remaining": 5, "health": "ok"},
        },
    }

    assert mod._dispatchable_next(tasks, budget, providers)["id"] == "READY"


def test_dispatchable_next_skips_task_with_unavailable_explicit_mount(tmp_path):
    mod = _load()
    unavailable = tmp_path / "not-a-mount"
    unavailable.mkdir()
    tasks = [
        _task(
            "MOUNT-GATED",
            priority="critical",
            execution_requirements=[{"kind": "mount", "path": str(unavailable)}],
        ),
        _task("READY", priority="medium"),
    ]
    budget = {"remaining": 3, "per_agent": {"codex": {"remaining": 3}}}
    providers = {"generated": "now", "vendors": {"codex": {"remaining": 2, "health": "ok"}}}

    assert mod._ostensible_next(tasks)["id"] == "MOUNT-GATED"
    assert mod._dispatchable_next(tasks, budget, providers)["id"] == "READY"


def test_dispatchable_next_fails_closed_on_raw_requirement_extra_key(monkeypatch):
    mod = _load()
    monkeypatch.setattr("limen.runtime_requirements.os.path.ismount", lambda _path: True)
    tasks = [
        _task(
            "MALFORMED",
            priority="critical",
            execution_requirements=[{"kind": "mount", "path": "/runtime/mounted", "unexpected": "value"}],
        ),
        _task("READY", priority="medium"),
    ]
    budget = {"remaining": 3, "per_agent": {"codex": {"remaining": 3}}}
    providers = {"generated": "now", "vendors": {"codex": {"remaining": 2, "health": "ok"}}}

    assert mod._ostensible_next(tasks)["id"] == "MALFORMED"
    assert mod._dispatchable_next(tasks, budget, providers)["id"] == "READY"


def test_check_requires_fresh_truthful_schema(monkeypatch, tmp_path, capsys):
    mod = _load()
    _configure(mod, monkeypatch, tmp_path, _board([_task("READY")]))
    assert mod.write() == 0
    assert mod.check() == 0
    assert "warm resume ready" in capsys.readouterr().out

    payload = json.loads(mod.HANDOFF.read_text(encoding="utf-8"))
    payload.pop("board_budget")
    mod.HANDOFF.write_text(json.dumps(payload), encoding="utf-8")
    assert mod.check() == 1
    assert "missing 'board_budget'" in capsys.readouterr().out


def test_check_rejects_missing_or_stale_provider_truth(monkeypatch, tmp_path, capsys):
    mod = _load()
    _configure(mod, monkeypatch, tmp_path, _board([_task("READY")]))
    assert mod.write() == 0
    payload = json.loads(mod.HANDOFF.read_text(encoding="utf-8"))

    payload["provider_headroom"]["generated"] = None
    mod.HANDOFF.write_text(json.dumps(payload), encoding="utf-8")
    assert mod.check() == 1
    assert "timestamp missing or unparseable" in capsys.readouterr().out

    payload["provider_headroom"]["generated"] = "2026-07-12T08:00:00+00:00"
    mod.HANDOFF.write_text(json.dumps(payload), encoding="utf-8")
    assert mod.check() == 1
    assert "provider headroom stale" in capsys.readouterr().out


def test_handoff_refresh_is_wired_across_heartbeat_metabolize_and_session_end():
    heartbeat = (ROOT / "scripts" / "heartbeat-loop.sh").read_text(encoding="utf-8")
    metabolize = (ROOT / "scripts" / "metabolize.sh").read_text(encoding="utf-8")
    session_end = (ROOT / "scripts" / "hooks" / "session-closeout.sh").read_text(encoding="utf-8")

    # Observe-mode and normal dispatch beats both refresh; metabolize remains independently wired.
    assert heartbeat.count('python3 "$LIMEN_ROOT/scripts/handoff-relay.py"') >= 2
    assert 'python3 "$LIMEN_ROOT/scripts/handoff-relay.py"' in metabolize
    # Every SessionEnd refreshes before the worktree-only early return.
    assert session_end.index('python3 "$HANDOFF_ROOT/scripts/handoff-relay.py"') < session_end.index('case "$CWD" in')
