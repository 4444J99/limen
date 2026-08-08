import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


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
                else ({"codex": (reasons or {}).get("provider_health", 0)} if (reasons or {}).get("provider_health") else {})
            ),
            "dispatchable_next": {"id": "TASK-1"} if admissible else None,
        },
        "provider_headroom": {
            "generated": datetime.now(timezone.utc).isoformat(),
            "vendors": {
                name: {"state": state}
                for name, state in (provider_states or {"codex": provider_state}).items()
            },
        },
    }
    (logs / "handoff.json").write_text(json.dumps(payload), encoding="utf-8")


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
    monkeypatch.setattr(module, "_notify_macos", lambda *_args: delivered.append("macos"))
    monkeypatch.setattr(module, "_notify_ntfy", lambda *_args: delivered.append("ntfy"))

    assert module.main([]) == 0
    assert delivered == []
    assert not module.STATE.exists()
