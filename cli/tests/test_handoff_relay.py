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
    # The fixture represents a healthy provider receipt without requiring host binaries.
    monkeypatch.setattr(mod, "agent_status", lambda _agent: {"reachable": True})
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
        "repo": "organvm/session-meta",
        "target_agent": agent,
        "priority": priority,
        "budget_cost": 1,
        "origin": "human_prompt",
        "horizon": "present",
        "value_case": f"Deliver the bounded handoff task {task_id}",
        "owner_surface": "organvm/limen",
        "predicate": "pytest -q cli/tests/test_handoff_relay.py",
        "receipt_target": f"github:organvm/limen:pull-request:{task_id}",
        "status": "open",
        "created": "2026-07-12",
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
    assert payload["next_action"] == payload["dispatchable_next"]
    assert payload["dispatch_admission"]["admissible"] == 1
    assert payload["dispatch_admission"]["reason_counts"] == {"provider_health": 1}
    assert payload["dispatch_admission"]["provider_health_reason_counts"] == {"gemini": 1}
    assert payload["dispatch_admission"]["admissible_agent_counts"] == {"codex": 1}
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


def test_dispatchable_next_skips_successor_required_open_row():
    mod = _load()
    tasks = [
        _task(
            "EXPIRED",
            priority="critical",
            labels=["workstream:successor-required"],
        ),
        _task("READY", priority="medium"),
    ]
    budget = {"remaining": 3, "per_agent": {"codex": {"remaining": 3}}}
    providers = {"generated": "now", "vendors": {"codex": {"remaining": 2}}}

    assert mod._dispatchable_next(tasks, budget, providers)["id"] == "READY"


def test_dispatchable_next_skips_operator_paused_open_row():
    mod = _load()
    tasks = [
        _task("PAUSED", priority="critical", labels=["operator-paused"]),
        _task("READY", priority="medium"),
    ]
    budget = {"remaining": 3, "per_agent": {"codex": {"remaining": 3}}}
    providers = {"generated": "now", "vendors": {"codex": {"remaining": 2}}}

    admission = mod._dispatch_admission(tasks, budget, providers)
    assert admission["dispatchable_next"]["id"] == "READY"
    assert admission["reason_counts"]["operator_paused"] == 1


def test_dispatchable_next_reports_stable_work_loan_denial() -> None:
    mod = _load()
    legacy = _task("LEGACY", priority="critical")
    for field in ("origin", "horizon", "value_case"):
        legacy.pop(field)
    tasks = [legacy, _task("READY", priority="medium")]
    budget = {"remaining": 3, "per_agent": {"codex": {"remaining": 3}}}
    providers = {"generated": "now", "vendors": {"codex": {"remaining": 2}}}

    admission = mod._dispatch_admission(tasks, budget, providers)

    assert admission["dispatchable_next"]["id"] == "READY"
    assert admission["reason_counts"] == {"task-not-underwritten:source_origin,horizon,value_case": 1}


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


def test_dispatch_admission_records_only_capable_lanes_for_any_control_host_task(monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "_eligible_any_agent", lambda *_args: False)
    task = _task("CONTROL", agent="any", labels=["execution:control-host"])
    budget = {"remaining": 3, "per_agent": {}}
    providers = {
        "generated": "now",
        "vendors": {"jules": {"remaining": 5, "health": "ok"}},
    }

    admission = mod._dispatch_admission([task], budget, providers)

    assert admission["admissible"] == 0
    assert admission["reason_counts"] == {"admission_blocked": 1}
    assert admission["admissible_agent_counts"] == {}
    assert admission["admissible_any_agent_counts"] == {}


def test_dispatch_admission_excludes_any_lane_over_per_agent_budget(monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "PAID_AGENT_ORDER", ("jules",))
    task = _task("ANY-EXPENSIVE", agent="any", budget_cost=2)
    budget = {"remaining": 3, "per_agent": {"jules": {"remaining": 1}}}
    providers = {
        "generated": "now",
        "vendors": {"jules": {"remaining": 5, "health": "ok"}},
    }

    admission = mod._dispatch_admission([task], budget, providers)

    assert admission["admissible_any_agent_counts"] == {}


def test_dispatch_admission_rejects_ineligible_explicit_lane():
    mod = _load()
    task = _task("CONTROL", agent="jules", labels=["execution:control-host"])
    budget = {"remaining": 3, "per_agent": {"jules": {"remaining": 3}}}
    providers = {
        "generated": "now",
        "vendors": {"jules": {"remaining": 5, "health": "ok"}},
    }

    admission = mod._dispatch_admission([task], budget, providers)

    assert admission["admissible"] == 0
    assert admission["reason_counts"] == {"admission_blocked": 1}
    assert admission["admissible_agent_counts"] == {}


def test_dispatch_admission_uses_effective_route_for_provider_health():
    mod = _load()
    routed = _task(
        "ROUTED",
        agent="codex",
        dispatch_log=[
            {
                "timestamp": "2026-07-12T12:00:00+00:00",
                "agent": "codex",
                "session_id": "route-receipt",
                "status": "open",
                "route_to": "claude",
            }
        ],
    )
    budget = {"remaining": 3, "per_agent": {"claude": {"remaining": 3}}}
    providers = {
        "generated": "now",
        "vendors": {
            "codex": {"remaining": 0, "health": "auth_needed"},
            "claude": {"remaining": 5, "health": "ok"},
        },
    }

    admission = mod._dispatch_admission([routed], budget, providers)

    assert admission["admissible"] == 1
    assert admission["admissible_agent_counts"] == {"claude": 1}


def test_dispatch_admission_names_auth_blocked_provider():
    mod = _load()
    tasks = [_task("LOGIN", priority="high", agent="jules"), _task("READY", agent="codex")]
    budget = {"remaining": 3, "per_agent": {}}
    providers = {
        "generated": "now",
        "vendors": {
            "jules": {"remaining": 5, "health": "auth_needed"},
            "codex": {"remaining": 5, "health": "ok"},
        },
    }

    admission = mod._dispatch_admission(tasks, budget, providers)

    assert admission["dispatchable_next"]["id"] == "READY"
    assert admission["reason_counts"] == {"auth_blocked": 1}
    assert admission["provider_health_reason_counts"] == {"jules": 1}


def test_dispatch_admission_projects_provider_outcome_auth_cooldown():
    mod = _load()
    task = _task("OPENCODE-LOGIN", agent="opencode")
    budget = {"remaining": 3, "per_agent": {"opencode": {"remaining": 3}}}
    providers = {
        "generated": "now",
        "vendors": {
            "opencode": {
                "remaining": 5,
                "health": "ok",
                "provider_outcome_health": "degraded",
                "provider_cooldown_count": 1,
                "provider_last_terminal_failure": "auth_failure",
                "provider_outcome_all_blocked": True,
            }
        },
    }

    admission = mod._dispatch_admission([task], budget, providers)

    assert admission["admissible"] == 0
    assert admission["reason_counts"] == {"auth_blocked": 1}
    assert admission["provider_health_reason_counts"] == {"opencode": 1}


def test_dispatch_admission_preserves_agy_weak_proxy_lane():
    mod = _load()
    task = _task("AGY-PROXY", agent="agy")
    budget = {"remaining": 3, "per_agent": {"agy": {"remaining": 3}}}
    providers = {
        "generated": "now",
        "vendors": {
            "agy": {
                "remaining": 0,
                "health": "low",
                "signal": "dispatch-count",
                "limit_source": "operator board cap",
            }
        },
    }

    admission = mod._dispatch_admission([task], budget, providers)

    assert admission["admissible"] == 1
    assert admission["reason_counts"] == {}


def test_dispatch_admission_filters_unreachable_any_lane(monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "PAID_AGENT_ORDER", ("github_actions", "codex"))
    monkeypatch.setattr(mod, "agent_status", lambda agent: {"reachable": agent == "codex"})
    monkeypatch.setattr(mod, "_eligible_any_agent", lambda *_args: True)
    task = _task("ANY-LIVE", agent="any")
    budget = {"remaining": 3, "per_agent": {}}
    providers = {"generated": "now", "vendors": {}}

    admission = mod._dispatch_admission([task], budget, providers)

    assert admission["admissible"] == 1
    assert admission["admissible_any_agent_counts"] == {"codex": 1}


def test_board_budget_preserves_active_per_agent_reset_window(monkeypatch):
    mod = _load()
    now = dt.datetime(2026, 7, 13, 2, 0, tzinfo=dt.timezone.utc)
    monkeypatch.setattr(mod, "_now", lambda: now)
    monkeypatch.setattr(mod, "_window_hours", lambda agent: 5.0 if agent == "codex" else 24.0)
    board = _board([])
    board["portal"]["budget"]["track"] = {
        "date": "2026-07-12",
        "spent": 9,
        "per_agent": {"codex": 2, "gemini": 7},
        "per_agent_reset": {
            "codex": "2026-07-13T00:00:00+00:00",
            "gemini": "2026-07-12T00:00:00+00:00",
        },
    }

    budget = mod._board_budget(board)

    assert budget["spent"] == 2
    assert budget["remaining"] == 8
    assert budget["per_agent"]["codex"]["spent"] == 2
    assert budget["per_agent"]["gemini"]["spent"] == 0


def test_dispatch_admission_discovers_unmetered_canonical_lane(monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "PAID_AGENT_ORDER", ("github_actions",))
    monkeypatch.setattr(mod, "_eligible_any_agent", lambda task, agent: agent == "github_actions")
    task = _task(
        "ANY-VERIFY",
        agent="any",
        type="verification",
        labels=["mode:verification-only"],
        depends_on=[],
    )
    budget = {"remaining": 3, "per_agent": {}}
    providers = {"generated": "now", "vendors": {}}

    admission = mod._dispatch_admission([task], budget, providers)

    assert admission["admissible"] == 1
    assert admission["admissible_any_agent_counts"] == {"github_actions": 1}


def test_dispatch_admission_preserves_any_budget_block(monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "PAID_AGENT_ORDER", ("jules",))
    monkeypatch.setattr(mod, "_eligible_any_agent", lambda *_args: True)
    task = _task("ANY-BUDGET", agent="any", budget_cost=2)
    budget = {"remaining": 3, "per_agent": {"jules": {"remaining": 1}}}
    providers = {"generated": "now", "vendors": {"jules": {"remaining": 5, "health": "ok"}}}

    admission = mod._dispatch_admission([task], budget, providers)

    assert admission["admissible"] == 0
    assert admission["reason_counts"] == {"budget_agent": 1}


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


def test_print_missing_file_is_loud_and_nonzero(monkeypatch, tmp_path, capsys):
    mod = _load()
    _configure(mod, monkeypatch, tmp_path, _board([]))
    assert mod.print_handoff() == 1
    assert "NO HANDOFF RECORDED" in capsys.readouterr().out


def test_print_corrupt_json_is_loud_and_nonzero(monkeypatch, tmp_path, capsys):
    mod = _load()
    _configure(mod, monkeypatch, tmp_path, _board([]))
    mod.HANDOFF.write_text("{not json", encoding="utf-8")
    assert mod.print_handoff() == 1
    assert "NO HANDOFF RECORDED" in capsys.readouterr().out


def test_print_empty_dict_is_loud_and_nonzero(monkeypatch, tmp_path, capsys):
    mod = _load()
    _configure(mod, monkeypatch, tmp_path, _board([]))
    mod.HANDOFF.write_text("{}", encoding="utf-8")
    assert mod.print_handoff() == 1
    out = capsys.readouterr().out
    assert "NO HANDOFF RECORDED" in out
    assert "0 open across 0 lanes" not in out


def test_print_fresh_handoff_renders_zero_exit(monkeypatch, tmp_path, capsys):
    mod = _load()
    _configure(mod, monkeypatch, tmp_path, _board([_task("READY")]))
    assert mod.write() == 0
    capsys.readouterr()
    assert mod.print_handoff() == 0
    out = capsys.readouterr().out
    assert "Resume from (handoff)" in out
    assert "NO HANDOFF RECORDED" not in out
    assert "seam may be cold" not in out


def test_print_stale_handoff_carries_staleness_note(monkeypatch, tmp_path, capsys):
    mod = _load()
    _configure(mod, monkeypatch, tmp_path, _board([_task("READY")]))
    assert mod.write() == 0
    payload = json.loads(mod.HANDOFF.read_text(encoding="utf-8"))
    payload["generated"] = "2026-07-12T09:05:00+00:00"
    mod.HANDOFF.write_text(json.dumps(payload), encoding="utf-8")
    capsys.readouterr()
    assert mod.print_handoff() == 0
    out = capsys.readouterr().out
    assert "seam may be cold" in out
    assert "Resume from (handoff)" in out


def test_handoff_refresh_is_wired_across_heartbeat_metabolize_and_breadcrumb_consumer():
    heartbeat = (ROOT / "scripts" / "heartbeat-loop.sh").read_text(encoding="utf-8")
    metabolize = (ROOT / "scripts" / "metabolize.sh").read_text(encoding="utf-8")
    session_end = (ROOT / "scripts" / "hooks" / "session-closeout.sh").read_text(encoding="utf-8")
    consumer = (ROOT / "scripts" / "consume-session-end-breadcrumbs.py").read_text(encoding="utf-8")

    # Observe-mode and normal dispatch beats both refresh; metabolize remains independently wired.
    assert heartbeat.count('python3 "$LIMEN_ROOT/scripts/handoff-relay.py"') >= 2
    assert 'python3 "$LIMEN_ROOT/scripts/handoff-relay.py"' in metabolize
    assert "consume-session-end-breadcrumbs.py" in heartbeat
    assert '"handoff-relay.py"' in consumer
    # SessionEnd itself never performs the slow refresh.
    assert "handoff-relay.py" not in session_end


def test_heartbeat_sh_drains_only_after_singleton_acquisition():
    heartbeat = (ROOT / "scripts" / "heartbeat.sh").read_text(encoding="utf-8")
    drain_call = heartbeat.index("\ndrain_session_end_breadcrumbs\n")

    assert heartbeat.index("flock -n 9") < drain_call
    assert heartbeat.index('mkdir "$LOCK.d"') < drain_call
    assert drain_call < heartbeat.index('MODE="$(python3 "$LIMEN_ROOT/scripts/autonomy-governor.py"')


def test_heartbeat_drains_resolve_timeout_with_direct_fail_open_fallback():
    scripts = {
        "heartbeat.sh": "SESSION_END_TIMEOUT_BIN",
        "heartbeat-loop.sh": "DISPATCH_TIMEOUT_BIN",
    }

    for filename, timeout_var in scripts.items():
        source = (ROOT / "scripts" / filename).read_text(encoding="utf-8")
        function_start = source.index("drain_session_end_breadcrumbs() {")
        function_end = source.index("\n}", function_start)
        function = source[function_start:function_end]
        bounded, direct = function.split("  else\n", 1)

        assert "command -v timeout || command -v gtimeout || true" in source
        assert f'if [ -n "${timeout_var}" ]; then' in bounded
        assert f'"${timeout_var}" "${{LIMEN_SESSION_END_CONSUMER_TIMEOUT:-90}}"' in bounded
        assert 'python3 "$LIMEN_ROOT/scripts/consume-session-end-breadcrumbs.py"' in direct
        assert f"${timeout_var}" not in direct
        assert "--runway-seconds" in bounded
        assert "--runway-seconds" in direct
        assert "|| true" in bounded
        assert "|| true" in direct


def test_heartbeat_loop_drains_before_paused_and_offline_early_continues_once():
    heartbeat = (ROOT / "scripts" / "heartbeat-loop.sh").read_text(encoding="utf-8")
    lines = [line.strip() for line in heartbeat.splitlines()]
    ownership = heartbeat.index('if [ "$(cat "$DAEMON_LOCK" 2>/dev/null)" != "$$" ]; then')
    drain_call = heartbeat.index("\n  drain_session_end_breadcrumbs\n")
    mode = heartbeat.index('  MODE="$(python3 "$LIMEN_ROOT/scripts/autonomy-governor.py"')
    paused_continue = heartbeat.index("\n    continue\n", mode)
    connectivity = heartbeat.index("  # CONNECTIVITY GATE", paused_continue)
    offline_continue = heartbeat.index("\n    continue\n", connectivity)

    assert heartbeat.index('echo $$ > "$DAEMON_LOCK"') < ownership < drain_call
    assert drain_call < mode < paused_continue < connectivity < offline_continue
    assert lines.count("drain_session_end_breadcrumbs") == 1
    assert "consume-session-end-breadcrumbs.py" not in heartbeat[drain_call:]


def test_dispatch_admission_keeps_opencode_route_when_one_provider_is_healthy():
    mod = _load()
    task = _task("OPENCODE-FALLBACK", agent="opencode")
    budget = {"remaining": 3, "per_agent": {"opencode": {"remaining": 3}}}
    providers = {
        "generated": "now",
        "vendors": {
            "opencode": {
                "remaining": 5,
                "health": "ok",
                "provider_outcome_health": "degraded",
                "provider_cooldown_count": 1,
                "provider_outcome_all_blocked": False,
            }
        },
    }

    admission = mod._dispatch_admission([task], budget, providers)

    assert admission["admissible"] == 1
    assert admission["reason_counts"] == {}
    assert admission["admissible_agent_counts"] == {"opencode": 1}


def test_dispatch_admission_honors_live_down_lane_snapshot():
    mod = _load()
    task = _task("AGY-DOWN", agent="agy")
    budget = {"remaining": 3, "per_agent": {"agy": {"remaining": 3}}}
    providers = {
        "generated": "now",
        "down_lanes": ["agy"],
        "vendors": {"agy": {"remaining": 5, "health": "ok"}},
    }

    admission = mod._dispatch_admission([task], budget, providers)

    assert admission["admissible"] == 0
    assert admission["reason_counts"] == {"provider_health": 1}
    assert admission["provider_health_reason_counts"] == {"agy": 1}
    assert admission["down_lanes"] == ["agy"]


def test_board_budget_discards_expired_track_counters(monkeypatch):
    mod = _load()
    board = _board([])
    monkeypatch.setattr(mod, "_now", lambda: dt.datetime(2026, 7, 13, tzinfo=dt.timezone.utc))

    budget = mod._board_budget(board)

    assert budget["track_date"] == "2026-07-12"
    assert budget["spent"] == 0
    assert budget["remaining"] == 10
    assert budget["per_agent"]["codex"]["spent"] == 0
    assert budget["per_agent"]["codex"]["remaining"] == 5