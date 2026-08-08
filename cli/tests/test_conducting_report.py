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


def _handoff(logs: Path, *, admissible: int = 0, reasons: dict | None = None, provider_state: str = "ok"):
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
            "dispatchable_next": {"id": "TASK-1"} if admissible else None,
        },
        "provider_headroom": {"vendors": {"codex": {"state": provider_state}}},
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
    assert headline.startswith("ROUTABLE BUT IDLE")
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


def test_daily_key_uses_the_supplied_local_calendar_day(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    local = timezone(timedelta(hours=-4))
    before_local_midnight = datetime(2026, 8, 8, 23, 30, tzinfo=local)

    assert before_local_midnight.astimezone(timezone.utc).date().isoformat() == "2026-08-09"
    assert module._local_day(before_local_midnight) == "2026-08-08"
