import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "conducting-report.py"


def _load(monkeypatch, root: Path):
    monkeypatch.setenv("LIMEN_ROOT", str(root))
    monkeypatch.setenv("LIMEN_TASKS", str(root / "tasks.yaml"))
    spec = importlib.util.spec_from_file_location("conducting_report_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_census_is_counts_only(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "usage.json").write_text(
        json.dumps(
            {
                "generated": "2026-07-06T00:00:00Z",
                "vendors": {
                    "private-codex-name": {"headroom_pct": 10, "reserve_pct": 15, "consumed": 90},
                    "private-claude-name": {"headroom_pct": 100, "reserve_pct": 15, "consumed": 0},
                },
            }
        ),
        encoding="utf-8",
    )
    (logs / "ledger.json").write_text(json.dumps({"verdict": "private value verdict"}), encoding="utf-8")
    (tmp_path / "tasks.yaml").write_text(
        """
tasks:
  - id: DISCOVER-PRIVATE
    status: open
    title: private target
  - id: DISCOVER-DONE
    status: done
""",
        encoding="utf-8",
    )

    census = module.census()
    encoded = json.dumps(census, sort_keys=True)

    assert census == {
        "usage_present": True,
        "vendor_count": 2,
        "vendors_with_headroom": 2,
        "vendors_burned": 1,
        "vendors_idle": 1,
        "value_verdict_present": True,
        "open_value_discovery": 1,
        "state_present": False,
        "routing_reason": "keeper_unavailable",
    }
    assert "private-codex-name" not in encoded
    assert "private-claude-name" not in encoded
    assert "private value verdict" not in encoded
    assert "private target" not in encoded


def _handoff(
    logs: Path,
    *,
    admissible: int = 0,
    reasons: dict | None = None,
    provider_state: str = "ok",
    provider_states: dict[str, str] | None = None,
    blocked_providers: dict[str, int] | None = None,
    admissible_agents: dict[str, int] | None = None,
    admissible_any_agents: dict[str, int] | None = None,
    gated_tasks: list[dict[str, str]] | None = None,
):
    logs.mkdir(exist_ok=True)
    payload = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "dispatchable_next": {"id": "TASK-1"} if admissible else None,
        "dispatch_admission": {
            "schema_version": "limen.dispatch_admission.v1",
            "open_considered": max(admissible, sum((reasons or {}).values())),
            "admissible": admissible,
            "gated": sum((reasons or {}).values()),
            "reason_counts": reasons or {},
            "provider_health_reason_counts": (
                blocked_providers
                if blocked_providers is not None
                else (
                    {"codex": (reasons or {}).get("provider_health", 0)}
                    if (reasons or {}).get("provider_health")
                    else {}
                )
            ),
            "admissible_agent_counts": (
                admissible_agents if admissible_agents is not None else ({"codex": admissible} if admissible else {})
            ),
            "admissible_any_agent_counts": (admissible_any_agents if admissible_any_agents is not None else {}),
            "gated_tasks": gated_tasks or [],
            "dispatchable_next": {"id": "TASK-1", "target_agent": "codex"} if admissible else None,
        },
        "provider_headroom": {
            "generated": datetime.now(timezone.utc).isoformat(),
            "vendors": {
                name: {"state": state} for name, state in (provider_states or {"codex": provider_state}).items()
            },
        },
    }
    (logs / "handoff.json").write_text(json.dumps(payload), encoding="utf-8")


def test_corpus_refresh_is_reported_capacity_blocked_not_next_or_unroutable(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    logs = tmp_path / "logs"
    _handoff(
        logs,
        reasons={"provider_health": 1},
        provider_states={"claude": "exhausted"},
        blocked_providers={"claude": 1},
        gated_tasks=[
            {
                "id": "CONST-CORPUS-REFRESH",
                "agent": "claude",
                "reason": "provider_health",
            }
        ],
    )
    (logs / "usage.json").write_text(
        json.dumps(
            {
                "vendors": {
                    "claude": {
                        "headroom_pct": 100,
                        "reserve_pct": 15,
                        "consumed": 0,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "tasks.yaml").write_text("tasks: []\n", encoding="utf-8")

    headline, body, _day, reason = module.build_report()

    assert reason == "capacity_blocked"
    assert "CONST-CORPUS-REFRESH: capacity_blocked (claude; gate=provider_health)" in body
    assert "next" not in body.lower()
    assert "unroutable" not in headline.lower() + body.lower()


def test_admitted_work_can_never_be_reported_as_no_routable_work(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    logs = tmp_path / "logs"
    _handoff(logs, admissible=1)
    (logs / "usage.json").write_text(
        json.dumps({"vendors": {"codex": {"headroom_pct": 100, "consumed": 0}}}),
        encoding="utf-8",
    )

    headline, body, _day, reason = module.build_report()

    assert reason == "routable"
    assert headline.startswith("ROUTABLE WORK EXISTS")
    assert "no routable work" not in headline
    assert "routing: routable" in body


def test_session_value_gate_overrides_an_admissible_handoff(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    logs = tmp_path / "logs"
    _handoff(logs, admissible=1)

    reason, detail = module._routing_reason(
        session_value_gate={"status": "blocked", "reason": "switch to a higher-value lane"}
    )

    assert reason == "admission_blocked"
    assert "session value gate withheld dispatch" in detail
    assert "higher-value lane" in detail


def test_routable_report_reuses_the_canonical_always_working_gate(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    logs = tmp_path / "logs"
    _handoff(logs, admissible=1)
    monkeypatch.setattr(
        module,
        "_always_working_admission",
        lambda: {"status": "blocked", "reason": "owner ticket writer failed"},
    )

    reason, detail = module._routing_reason()

    assert reason == "admission_blocked"
    assert "always-working gate withheld dispatch" in detail
    assert "owner ticket writer failed" in detail


def test_routable_idle_work_overrides_burn_headline(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    logs = tmp_path / "logs"
    _handoff(
        logs,
        admissible=1,
        admissible_agents={"claude": 1},
        provider_states={"codex": "ok", "claude": "ok"},
    )
    (logs / "usage.json").write_text(
        json.dumps(
            {
                "vendors": {
                    "codex": {"headroom_pct": 10, "consumed": 9},
                    "claude": {"headroom_pct": 100, "consumed": 0},
                }
            }
        ),
        encoding="utf-8",
    )

    headline, _body, _day, reason = module.build_report()

    assert reason == "routable"
    assert headline.startswith("ROUTABLE WORK EXISTS")


def test_admitted_work_for_another_provider_does_not_accuse_idle_lane(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    logs = tmp_path / "logs"
    _handoff(logs, admissible=1, admissible_agents={"claude": 1})
    (logs / "usage.json").write_text(
        json.dumps({"vendors": {"codex": {"headroom_pct": 100, "consumed": 0}}}),
        encoding="utf-8",
    )

    headline, body, _day, reason = module.build_report()

    assert reason == "admission_blocked"
    assert headline.startswith("IDLED")
    assert "none target idle providers" in body


def test_any_admission_does_not_route_to_ineligible_idle_lane(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    logs = tmp_path / "logs"
    _handoff(
        logs,
        admissible=1,
        admissible_agents={"any": 1},
        admissible_any_agents={},
        provider_states={"jules": "ok"},
    )
    (logs / "usage.json").write_text(
        json.dumps({"vendors": {"jules": {"headroom_pct": 100, "consumed": 0}}}),
        encoding="utf-8",
    )

    headline, body, _day, reason = module.build_report()

    assert reason == "admission_blocked"
    assert headline.startswith("IDLED")
    assert "none target idle providers" in body


def test_zero_admission_filters_blockers_to_idle_provider(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    logs = tmp_path / "logs"
    _handoff(
        logs,
        reasons={"provider_health": 1},
        provider_states={"codex": "ok", "jules": "auth_needed"},
        blocked_providers={"jules": 1},
    )
    payload = json.loads((logs / "handoff.json").read_text())
    payload["dispatch_admission"]["reason_counts_by_agent"] = {"jules": {"auth_blocked": 1}}
    (logs / "handoff.json").write_text(json.dumps(payload), encoding="utf-8")
    (logs / "usage.json").write_text(
        json.dumps({"vendors": {"codex": {"headroom_pct": 100, "consumed": 0}}}),
        encoding="utf-8",
    )

    headline, body, _day, reason = module.build_report()

    assert reason == "admission_blocked"
    assert headline.startswith("IDLED")
    assert "auth_blocked" not in body


def test_main_refreshes_admission_before_building_report(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    logs = tmp_path / "logs"
    _handoff(logs, admissible=1)
    (logs / "usage.json").write_text(
        json.dumps(
            {
                "generated": datetime.now(timezone.utc).isoformat(),
                "vendors": {"codex": {"headroom_pct": 100, "consumed": 0}},
            }
        ),
        encoding="utf-8",
    )
    refreshed = []
    monkeypatch.setattr(module, "_refresh_admission", lambda: refreshed.append(True) or True)
    monkeypatch.setattr(module, "_session_value_admission", lambda: {"status": "allowed"})

    assert module.main(["--print"]) == 0
    assert refreshed == [True]


def test_settled_daily_report_skips_admission_refresh(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    module.STATE.parent.mkdir(parents=True)
    module.STATE.write_text(json.dumps({"last_day": module._local_day()}), encoding="utf-8")
    refreshed = []
    monkeypatch.setattr(module, "_refresh_admission", lambda: refreshed.append(True) or True)

    assert module.main([]) == 0
    assert refreshed == []


def test_session_value_admission_reports_lane_switch_as_blocked(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    module.ADMISSION_REFRESH_RECEIPT = tmp_path / "logs" / "refresh.jsonl"
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=10, stdout=b"", stderr=b"lane switch")

    monkeypatch.setattr(module, "_run_bounded_subprocess", fake_run)

    result = module._session_value_admission()

    assert result == {"status": "blocked", "reason": "lane switch"}
    assert calls[0][0][-4:] == ["--gate", "--hours", "1.5", "--no-record-gate"]
    assert calls[0][1]["stdout_ceiling"] == module.SESSION_VALUE_OUTPUT_LIMIT_BYTES
    assert calls[0][1]["stderr_ceiling"] == module.SESSION_VALUE_OUTPUT_LIMIT_BYTES
    receipts = [json.loads(line) for line in module.ADMISSION_REFRESH_RECEIPT.read_text().splitlines()]
    assert [(row["event"], row["step"]) for row in receipts] == [
        ("start", "session_value"),
        ("finish", "session_value"),
    ]
    assert receipts[-1]["outcome"] == "blocked"


def test_session_value_admission_stops_at_the_output_ceiling(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    module.ADMISSION_REFRESH_RECEIPT = tmp_path / "logs" / "refresh.jsonl"

    def verbose_gate(_args, **_kwargs):
        assert module._BoundedSubprocessError is not None
        raise module._BoundedSubprocessError("output")

    monkeypatch.setattr(module, "_run_bounded_subprocess", verbose_gate)

    result = module._session_value_admission()

    assert result["status"] == "unavailable"
    assert result["reason"] == "session value gate unavailable: exceeded output limit"
    receipts = [json.loads(line) for line in module.ADMISSION_REFRESH_RECEIPT.read_text().splitlines()]
    assert receipts[-1]["outcome"] == "output_limit"


def test_refresh_admission_is_bounded_and_writes_start_finish_receipts(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    module.ADMISSION_REFRESH_RECEIPT = tmp_path / "logs" / "refresh.jsonl"
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert module._refresh_admission() is True
    assert calls[0][0] == [module.sys.executable, str(SCRIPT.with_name("handoff-relay.py"))]
    assert calls[0][1]["timeout"] == module.ADMISSION_REFRESH_TIMEOUT_SECONDS
    assert calls[0][1]["stdout"] is module.subprocess.DEVNULL
    assert calls[0][1]["stderr"] is module.subprocess.DEVNULL
    receipts = [json.loads(line) for line in module.ADMISSION_REFRESH_RECEIPT.read_text().splitlines()]
    assert [receipt["event"] for receipt in receipts] == ["start", "finish"]
    assert receipts[-1]["outcome"] == "ok"


def test_refresh_admission_timeout_is_a_finite_failed_receipt(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    module.ADMISSION_REFRESH_RECEIPT = tmp_path / "logs" / "refresh.jsonl"
    monkeypatch.setenv("LIMEN_CONDUCTING_REFRESH_TIMEOUT", "1")

    def timeout(*_args, **_kwargs):
        raise module.subprocess.TimeoutExpired(["handoff-relay.py"], 1)

    monkeypatch.setattr(module.subprocess, "run", timeout)

    assert module._refresh_admission() is False
    receipts = [json.loads(line) for line in module.ADMISSION_REFRESH_RECEIPT.read_text().splitlines()]
    assert receipts[-1]["outcome"] == "timeout"


def test_refresh_admission_rejects_non_finite_timeout(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    module.ADMISSION_REFRESH_RECEIPT = tmp_path / "logs" / "refresh.jsonl"
    monkeypatch.setenv("LIMEN_CONDUCTING_REFRESH_TIMEOUT", "nan")
    calls = []
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda _args, **kwargs: calls.append(kwargs) or SimpleNamespace(returncode=0),
    )

    assert module._refresh_admission() is True
    assert calls[0]["timeout"] == module.ADMISSION_REFRESH_TIMEOUT_SECONDS


def test_routing_reason_is_a_canonical_enum(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    logs = tmp_path / "logs"

    _handoff(logs, reasons={"dependencies": 1})
    assert module._routing_reason()[0] == "admission_blocked"

    _handoff(logs, reasons={"budget_agent": 1})
    assert module._routing_reason()[0] == "capacity_blocked"

    _handoff(logs, reasons={"provider_health": 1}, provider_state="auth_needed")
    assert module._routing_reason()[0] == "auth_blocked"

    assert module.ROUTING_REASONS == {
        "routable",
        "admission_blocked",
        "capacity_blocked",
        "auth_blocked",
        "keeper_unavailable",
    }


def test_target_provider_names_are_normalized_once_across_admission_views(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    logs = tmp_path / "logs"
    _handoff(logs, admissible=1, admissible_agents={"claude_code": 1})

    reason, detail = module._routing_reason(target_providers={"Claude-Code"})

    assert reason == "routable"
    assert "admissible_for_idle=1" in detail


def test_unrelated_vendor_auth_does_not_override_keeper_gate(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    logs = tmp_path / "logs"
    _handoff(logs, reasons={"dependencies": 1}, provider_state="auth_needed")

    assert module._routing_reason()[0] == "admission_blocked"


def test_provider_auth_must_belong_to_the_provider_health_blocker(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    logs = tmp_path / "logs"
    _handoff(
        logs,
        reasons={"provider_health": 1},
        provider_states={"codex": "exhausted", "claude": "auth_needed"},
        blocked_providers={"codex": 1},
    )

    assert module._routing_reason()[0] == "capacity_blocked"


def test_routable_requires_fresh_provider_telemetry(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    logs = tmp_path / "logs"
    _handoff(logs, admissible=1)
    payload = json.loads((logs / "handoff.json").read_text())
    payload["provider_headroom"]["generated"] = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    (logs / "handoff.json").write_text(json.dumps(payload))

    assert module._routing_reason()[0] == "keeper_unavailable"


def test_provider_health_requires_fresh_provider_telemetry(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    logs = tmp_path / "logs"
    _handoff(logs, reasons={"provider_health": 1}, provider_state="auth_needed")
    payload = json.loads((logs / "handoff.json").read_text())
    payload["provider_headroom"]["generated"] = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    (logs / "handoff.json").write_text(json.dumps(payload))

    assert module._routing_reason()[0] == "keeper_unavailable"


def test_stale_continuity_is_not_presented_as_current(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    logs = tmp_path / "logs"
    _handoff(logs, admissible=1)
    (logs / "dispatch-continuity.json").write_text(
        json.dumps(
            {
                "generated": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
                "lanes": {"codex": {"verdict": "continuous"}},
            }
        )
    )

    reason, detail = module._routing_reason()

    assert reason == "routable"
    assert "unavailable or stale" in detail
    assert "continuous=1" not in detail


def test_malformed_admission_counts_do_not_crash_the_report(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    logs = tmp_path / "logs"
    _handoff(logs)
    payload = json.loads((logs / "handoff.json").read_text())
    payload["dispatch_admission"]["admissible"] = "not-a-count"
    payload["dispatch_admission"]["open_considered"] = object().__class__.__name__
    (logs / "handoff.json").write_text(json.dumps(payload))

    assert module._routing_reason()[0] == "admission_blocked"


def test_daily_key_uses_the_supplied_local_calendar_day(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    local = timezone(timedelta(hours=-4))
    before_local_midnight = datetime(2026, 8, 8, 23, 30, tzinfo=local)

    assert before_local_midnight.astimezone(timezone.utc).date().isoformat() == "2026-08-09"
    assert module._local_day(before_local_midnight) == "2026-08-08"


def test_stale_usage_cannot_emit_or_advance_the_daily_key(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "usage.json").write_text(
        json.dumps(
            {
                "generated": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
                "vendors": {"codex": {"headroom_pct": 100, "consumed": 0}},
            }
        ),
        encoding="utf-8",
    )
    delivered = []
    monkeypatch.setattr(module, "_refresh_admission", lambda: True)
    monkeypatch.setattr(module, "_session_value_admission", lambda: {"status": "allowed"})
    monkeypatch.setattr(module, "_notify_macos", lambda *_args: delivered.append("macos"))
    monkeypatch.setattr(module, "_notify_ntfy", lambda *_args: delivered.append("ntfy"))

    assert module.main([]) == 0
    assert delivered == []
    assert not module.STATE.exists()


def test_daily_state_advances_only_after_one_delivery_channel_succeeds(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    logs = tmp_path / "logs"
    _handoff(logs, admissible=1)
    (logs / "usage.json").write_text(
        json.dumps(
            {
                "generated": datetime.now(timezone.utc).isoformat(),
                "vendors": {"codex": {"headroom_pct": 100, "consumed": 0}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "_refresh_admission", lambda: True)
    monkeypatch.setattr(module, "_session_value_admission", lambda: {"status": "allowed"})
    macos_results = iter(
        (
            SimpleNamespace(status="delivery_failed", reserved=True, prior_status=None),
            SimpleNamespace(status="duplicate", reserved=False, prior_status="delivery_failed"),
        )
    )
    monkeypatch.setattr(module, "_notify_macos", lambda *_args, **_kwargs: next(macos_results))
    ntfy_results = iter((False, True))
    monkeypatch.setattr(module, "_notify_ntfy", lambda *_args: next(ntfy_results))

    assert module.main([]) == 0
    assert not module.STATE.exists()

    assert module.main([]) == 0
    assert json.loads(module.STATE.read_text())["last_day"] == module._local_day()


def test_withheld_duplicate_retries_ntfy_until_delivery_succeeds(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    logs = tmp_path / "logs"
    _handoff(logs, admissible=1)
    (logs / "usage.json").write_text(
        json.dumps(
            {
                "generated": datetime.now(timezone.utc).isoformat(),
                "vendors": {"codex": {"headroom_pct": 100, "consumed": 0}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "_refresh_admission", lambda: True)
    monkeypatch.setattr(module, "_session_value_admission", lambda: {"status": "allowed"})
    monkeypatch.setattr(module, "_always_working_admission", lambda: {"status": "allowed"})
    macos_results = iter(
        (
            SimpleNamespace(status="withheld", reserved=True, prior_status=None),
            SimpleNamespace(status="duplicate", reserved=False, prior_status="withheld"),
        )
    )
    monkeypatch.setattr(module, "_notify_macos", lambda *_args, **_kwargs: next(macos_results))
    ntfy_results = iter((False, True))
    monkeypatch.setattr(module, "_notify_ntfy", lambda *_args: next(ntfy_results))

    assert module.main([]) == 0
    assert not module.STATE.exists()

    assert module.main([]) == 0
    assert json.loads(module.STATE.read_text())["last_day"] == module._local_day()


def test_emitted_duplicate_rebuilds_state_after_transient_state_write_failure(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    logs = tmp_path / "logs"
    _handoff(logs, admissible=1)
    (logs / "usage.json").write_text(
        json.dumps(
            {
                "generated": datetime.now(timezone.utc).isoformat(),
                "vendors": {"codex": {"headroom_pct": 100, "consumed": 0}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "_refresh_admission", lambda: True)
    monkeypatch.setattr(module, "_session_value_admission", lambda: {"status": "allowed"})
    monkeypatch.setattr(module, "_always_working_admission", lambda: {"status": "allowed"})
    macos_results = iter(
        (
            SimpleNamespace(status="emitted", reserved=True, prior_status=None),
            SimpleNamespace(status="duplicate", reserved=False, prior_status="emitted"),
        )
    )
    monkeypatch.setattr(module, "_notify_macos", lambda *_args, **_kwargs: next(macos_results))
    ntfy_calls = []
    monkeypatch.setattr(module, "_notify_ntfy", lambda *_args: ntfy_calls.append(True) or False)

    # A directory cannot be written as the state file, reproducing the transient persistence
    # failure after the event ledger has already recorded an emitted notification.
    module.STATE = logs
    assert module.main([]) == 0

    module.STATE = logs / ".recovered-conducting-state.json"
    assert module.main([]) == 0

    assert json.loads(module.STATE.read_text())["last_day"] == module._local_day()
    assert ntfy_calls == [True]


def test_live_down_lanes_cannot_be_reported_as_routable(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    logs = tmp_path / "logs"
    _handoff(logs, admissible=1)
    payload = json.loads((logs / "handoff.json").read_text())
    payload["dispatch_admission"]["down_lanes"] = ["codex"]
    payload["provider_headroom"]["down_lanes"] = ["codex"]
    (logs / "handoff.json").write_text(json.dumps(payload))

    reason, detail = module._routing_reason()

    assert reason == "admission_blocked"
    assert "all admitted lanes are down" in detail


def test_delivery_callers_use_shared_ntfy_helper():
    conducting = SCRIPT.read_text(encoding="utf-8")
    events = SCRIPT.with_name("notify-events.py").read_text(encoding="utf-8")

    assert "urllib.request" not in conducting
    assert "urllib.request" not in events
    assert "notify_event(" in conducting
    assert "notify_event(" in events
    assert "notify_ntfy(ROOT" in conducting
    assert "notify_ntfy(ROOT" in events


def test_autonomy_pause_marker_blocks_routing_even_with_admitted_work(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    logs = tmp_path / "logs"
    _handoff(logs, admissible=1)
    (logs / "AUTONOMY_PAUSED").write_text("operator pause\n", encoding="utf-8")

    reason, detail = module._routing_reason()

    assert reason == "admission_blocked"
    assert detail == "autonomy pause marker is present"


def test_keeper_load_failure_cannot_render_as_empty_board(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    logs = tmp_path / "logs"
    _handoff(logs)
    payload = json.loads((logs / "handoff.json").read_text())
    payload["dispatch_admission"]["keeper_available"] = False
    payload["dispatch_admission"]["reason_counts"] = {"keeper_unavailable": 1}
    (logs / "handoff.json").write_text(json.dumps(payload), encoding="utf-8")

    reason, detail = module._routing_reason()

    assert reason == "keeper_unavailable"
    assert "board unavailable" in detail
