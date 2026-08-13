"""Regression guard for the vendor-health meter — the 'utilize all lanes forever' invariant.

The meter once falsely benched claude (a transcript that merely MENTIONED 'rate limit' tripped a
text regex) and gemini (a one-time 'RATE-LIMIT gemini' marker in the heartbeat log stuck forever).
These tests pin the fix: a lane is gated ONLY by a real, RECENT rate-limit — a lane with full
headroom and no fresh signal is never benched.
"""

import importlib.util
import json
import os
import subprocess
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "usage-telemetry.py"


def _load_module(monkeypatch, root: Path):
    monkeypatch.setenv("LIMEN_ROOT", str(root))
    spec = importlib.util.spec_from_file_location("usage_telemetry_provider_denominator", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _provider_failures(
    module,
    provider: str,
    catalog: str,
    profile: str,
    terminal: str = "auth_failure",
) -> list[dict[str, object]]:
    rows = []
    for retry in range(2):
        finished = module.NOW - timedelta(seconds=2 - retry)
        rows.append(
            {
                "schema": "limen.provider_outcome.v1",
                "provider": provider,
                "runtime_model": f"{provider}/runtime",
                "catalog_hash": catalog,
                "execution_profile_hash": profile,
                "terminal_class": terminal,
                "started_at": (finished - timedelta(seconds=1)).isoformat(),
                "finished_at": finished.isoformat(),
                "retry_count": retry,
                "receipt_reference": f"task:{provider}-fixture",
            }
        )
    return rows


def _provider_success(module, provider: str, catalog: str, profile: str) -> dict[str, object]:
    finished = module.NOW
    return {
        "schema": "limen.provider_outcome.v1",
        "provider": provider,
        "runtime_model": f"{provider}/runtime",
        "catalog_hash": catalog,
        "execution_profile_hash": profile,
        "terminal_class": "success",
        "started_at": (finished - timedelta(seconds=1)).isoformat(),
        "finished_at": finished.isoformat(),
        "retry_count": 0,
        "receipt_reference": f"task:{provider}-recovery-fixture",
    }


def test_optional_terminal_constant_does_not_disable_compatible_provider_apis(monkeypatch):
    provider_health = types.ModuleType("limen.provider_health")
    sentinels = {
        "load_provider_outcomes": lambda *_args: "loaded",
        "project_provider_health": lambda *_args: "projected",
        "provider_health_policy": lambda *_args: "policy",
        "provider_outcome_ledger_path": lambda *_args: "ledger",
    }
    for name, value in sentinels.items():
        setattr(provider_health, name, value)
    monkeypatch.setitem(sys.modules, "limen.provider_health", provider_health)
    spec = importlib.util.spec_from_file_location("usage_telemetry_mixed_version", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None

    spec.loader.exec_module(module)

    assert module._load_provider_outcomes is sentinels["load_provider_outcomes"]
    assert module._project_provider_health is sentinels["project_provider_health"]
    assert module._provider_health_policy is sentinels["provider_health_policy"]
    assert module._provider_outcome_ledger_path is sentinels["provider_outcome_ledger_path"]
    assert module._PROVIDER_TERMINALS == frozenset({"auth_failure", "rate_limit"})


def test_all_blocked_uses_every_provider_in_the_live_catalog(tmp_path, monkeypatch):
    root = tmp_path / "root"
    (root / "logs").mkdir(parents=True)
    module = _load_module(monkeypatch, root)
    catalog = "a" * 64
    profile = "b" * 64
    (root / "logs" / "provider-outcomes.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in _provider_failures(module, "provider-a", catalog, profile))
    )
    monkeypatch.setattr(
        module,
        "_discover_opencode_models",
        lambda *_args, **_kwargs: [
            types.SimpleNamespace(model_id="provider-a/runtime", active=True),
            types.SimpleNamespace(model_id="provider-b/runtime", active=True),
        ],
    )
    monkeypatch.setattr(module, "_catalog_hash", lambda _models: catalog)

    projection = module._provider_outcome_projection()

    assert projection["provider_outcome_all_blocked"] is False
    assert projection["provider_outcome_provider_count"] == 2
    assert projection["provider_outcome_blocked_provider_count"] == 1
    assert projection["provider_outcome_execution_profile_hash"] == profile


def test_provider_scoped_failures_fold_across_execution_profiles(tmp_path, monkeypatch):
    root = tmp_path / "root"
    (root / "logs").mkdir(parents=True)
    module = _load_module(monkeypatch, root)
    catalog = "c" * 64
    rows = [
        *_provider_failures(module, "provider-a", catalog, "d" * 64),
        *_provider_failures(module, "provider-b", catalog, "e" * 64),
    ]
    (root / "logs" / "provider-outcomes.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    monkeypatch.setattr(
        module,
        "_discover_opencode_models",
        lambda *_args, **_kwargs: [
            types.SimpleNamespace(model_id="provider-a/runtime", active=True),
            types.SimpleNamespace(model_id="provider-b/runtime", active=True),
        ],
    )
    monkeypatch.setattr(module, "_catalog_hash", lambda _models: catalog)

    projection = module._provider_outcome_projection()

    assert projection["provider_outcome_all_blocked"] is True
    assert projection["provider_outcome_provider_count"] == 2
    assert projection["provider_outcome_blocked_provider_count"] == 2
    assert projection["provider_outcome_execution_profile_hash"] is None
    assert projection["provider_outcome_matching_outcome_count"] == 4


def test_later_profile_success_recovers_older_profile_failures(tmp_path, monkeypatch):
    root = tmp_path / "root"
    (root / "logs").mkdir(parents=True)
    module = _load_module(monkeypatch, root)
    catalog = "6" * 64
    failed_profile = "7" * 64
    recovered_profile = "8" * 64
    rows = [
        *_provider_failures(module, "provider-a", catalog, failed_profile),
        *_provider_failures(module, "provider-b", catalog, failed_profile),
        _provider_success(module, "provider-a", catalog, recovered_profile),
        _provider_success(module, "provider-b", catalog, recovered_profile),
    ]
    (root / "logs" / "provider-outcomes.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    monkeypatch.setattr(
        module,
        "_discover_opencode_models",
        lambda *_args, **_kwargs: [
            types.SimpleNamespace(model_id="provider-a/runtime", active=True),
            types.SimpleNamespace(model_id="provider-b/runtime", active=True),
        ],
    )
    monkeypatch.setattr(module, "_catalog_hash", lambda _models: catalog)

    projection = module._provider_outcome_projection()

    assert projection["provider_outcome_all_blocked"] is False
    assert projection["provider_outcome_blocked_provider_count"] == 0


def test_all_blocked_requires_one_matching_catalog_and_profile(tmp_path, monkeypatch):
    root = tmp_path / "root"
    (root / "logs").mkdir(parents=True)
    module = _load_module(monkeypatch, root)
    live_catalog = "f" * 64
    profile = "1" * 64
    rows = [
        *_provider_failures(module, "provider-a", live_catalog, profile),
        *_provider_failures(module, "provider-b", live_catalog, profile),
        *_provider_failures(module, "provider-c", "0" * 64, profile),
    ]
    (root / "logs" / "provider-outcomes.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    monkeypatch.setattr(
        module,
        "_discover_opencode_models",
        lambda *_args, **_kwargs: [
            types.SimpleNamespace(model_id="provider-a/runtime", active=True),
            types.SimpleNamespace(model_id="provider-b/runtime", active=True),
        ],
    )
    monkeypatch.setattr(module, "_catalog_hash", lambda _models: live_catalog)

    projection = module._provider_outcome_projection()

    assert projection["provider_outcome_all_blocked"] is True
    assert projection["provider_outcome_provider_count"] == 2
    assert projection["provider_outcome_blocked_provider_count"] == 2
    assert projection["provider_outcome_catalog_hash"] == live_catalog
    assert projection["provider_outcome_execution_profile_hash"] == profile
    assert projection["provider_outcome_matching_outcome_count"] == 4


def test_terminal_classes_use_the_live_catalog_profile_health_group(tmp_path, monkeypatch):
    root = tmp_path / "root"
    (root / "logs").mkdir(parents=True)
    module = _load_module(monkeypatch, root)
    live_catalog = "2" * 64
    profile = "3" * 64
    rows = [
        *_provider_failures(module, "provider-a", live_catalog, profile, "rate_limit"),
        *_provider_failures(module, "provider-b", live_catalog, profile, "rate_limit"),
        *_provider_failures(module, "retired-provider", "4" * 64, profile, "auth_failure"),
    ]
    (root / "logs" / "provider-outcomes.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    monkeypatch.setattr(
        module,
        "_discover_opencode_models",
        lambda *_args, **_kwargs: [
            types.SimpleNamespace(model_id="provider-a/runtime", active=True),
            types.SimpleNamespace(model_id="provider-b/runtime", active=True),
        ],
    )
    monkeypatch.setattr(module, "_catalog_hash", lambda _models: live_catalog)

    projection = module._provider_outcome_projection()

    assert projection["provider_outcome_all_blocked"] is True
    assert projection["provider_last_terminal_failure_class"] == "rate_limit"
    assert projection["provider_terminal_failure_classes"] == {
        "provider-a": "rate_limit",
        "provider-b": "rate_limit",
    }
    assert projection["provider_outcome_observed_terminal_failure_classes"]["retired-provider"] == "auth_failure"


def _run(tmp_path, heartbeat_lines, opencode_clock=None, extra_env=None, provider_outcomes=None):
    """Run usage-telemetry.py against an isolated root + empty HOME (so claude/codex read 0 tokens)."""
    root = tmp_path / "root"
    home = tmp_path / "home"
    (root / "logs").mkdir(parents=True)
    (home / ".claude" / "projects").mkdir(parents=True)
    (home / ".codex" / "sessions").mkdir(parents=True)
    (root / "logs" / "usage-limits.json").write_text(
        json.dumps(
            {
                "gemini": {"limit": 200, "unit": "runs", "window": "24h"},
            }
        )
    )
    (root / "logs" / "heartbeat.out.log").write_text("\n".join(heartbeat_lines))
    (root / "tasks.yaml").write_text("tasks: []\nportal: {}\n")
    if provider_outcomes is not None:
        (root / "logs" / "provider-outcomes.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in provider_outcomes)
        )
    if opencode_clock is not None:
        clock_path = home / ".local" / "share" / "opencode" / "clock.json"
        clock_path.parent.mkdir(parents=True)
        clock_path.write_text(json.dumps(opencode_clock))
    env = dict(os.environ, LIMEN_ROOT=str(root), HOME=str(home))
    if extra_env:
        env.update(extra_env)
    subprocess.run([sys.executable, str(SCRIPT)], env=env, check=True, capture_output=True)
    return json.loads((root / "logs" / "usage.json").read_text())["vendors"]


def test_stale_ratelimit_marker_does_not_bench_a_headroom_lane(tmp_path):
    # an OLD 'RATE-LIMIT gemini' marker buried far above the tail window must NOT gate gemini —
    # gemini has 0/200 consumed (100% headroom), so it must come back 'ok'.
    lines = ["RATE-LIMIT gemini"] + [f"beat {i} ok" for i in range(600)]
    vendors = _run(tmp_path, lines)
    assert vendors["gemini"]["health"] == "ok", vendors["gemini"]
    assert vendors["gemini"]["headroom_pct"] == 100


def test_recent_ratelimit_marker_does_gate(tmp_path):
    # a FRESH marker inside the tail window is a real signal → gemini is rate-limited (time-boxed).
    lines = [f"beat {i} ok" for i in range(50)] + ["RATE-LIMIT gemini"]
    vendors = _run(tmp_path, lines)
    assert vendors["gemini"]["health"] == "rate-limited", vendors["gemini"]


def test_headroom_lane_with_no_signal_is_ok(tmp_path):
    # no markers at all → every healthy-headroom lane is 'ok', never benched.
    vendors = _run(tmp_path, [f"beat {i} ok" for i in range(20)])
    for name in ("gemini",):
        assert vendors[name]["health"] == "ok", (name, vendors[name])


def test_opencode_prefers_internal_clock_when_present(tmp_path):
    vendors = _run(
        tmp_path,
        ["beat ok"],
        {
            "heavy_used": 120,
            "cache_read_used": 30,
            "cap_tokens": 1000,
            "used_pct": 15,
            "health": "ok",
        },
    )

    assert vendors["opencode"]["signal"] == "db-meter"
    assert vendors["opencode"]["consumed"] == 150
    assert vendors["opencode"]["possible"] == 1000
    assert vendors["opencode"]["clock_used_pct"] == 15


def test_opencode_clock_accepts_string_numerics(tmp_path):
    vendors = _run(
        tmp_path,
        ["beat ok"],
        {
            "heavy_used": "120",
            "cache_read_used": "30",
            "cap_tokens": "1000",
            "used_pct": "15",
            "health": "ok",
        },
    )

    assert vendors["opencode"]["signal"] == "db-meter"
    assert vendors["opencode"]["consumed"] == 150
    assert vendors["opencode"]["possible"] == 1000
    assert vendors["opencode"]["clock_used_pct"] == 15


def test_opencode_clock_malformed_numerics_do_not_crash(tmp_path):
    vendors = _run(
        tmp_path,
        ["beat ok"],
        {
            "heavy_used": "bad",
            "cache_read_used": 30,
            "cap_tokens": "nan",
            "used_pct": False,
            "health": "ok",
        },
    )

    assert vendors["opencode"]["signal"] == "db-meter"
    assert vendors["opencode"]["consumed"] == 30
    assert vendors["opencode"]["possible"] == 0
    assert vendors["opencode"]["clock_used_pct"] == 0


def test_opencode_usage_includes_provider_outcome_health(tmp_path):
    now = datetime.now(timezone.utc)
    rows = []
    for index, terminal in enumerate(("stream_failure", "timeout")):
        finished = now - timedelta(seconds=5 - index)
        rows.append(
            {
                "schema": "limen.provider_outcome.v1",
                "provider": "provider-z",
                "runtime_model": "provider-z/arbitrary-runtime",
                "catalog_hash": "a" * 64,
                "execution_profile_hash": "b" * 64,
                "terminal_class": terminal,
                "started_at": (finished - timedelta(seconds=1)).isoformat(),
                "finished_at": finished.isoformat(),
                "retry_count": index,
                "receipt_reference": "task:fixture",
            }
        )

    vendors = _run(tmp_path, ["beat ok"], provider_outcomes=rows)

    assert vendors["opencode"]["provider_outcome_health"] == "degraded"
    assert vendors["opencode"]["provider_cooldown_count"] >= 1
    assert vendors["opencode"]["provider_last_terminal_failure"]
    assert len(vendors["opencode"]["provider_health_snapshot_hash"]) == 64


def test_opencode_usage_preserves_provider_auth_terminal_class(tmp_path):
    now = datetime.now(timezone.utc)
    rows = []
    for index in range(2):
        finished = now - timedelta(seconds=5 - index)
        rows.append(
            {
                "schema": "limen.provider_outcome.v1",
                "provider": "opencode",
                "runtime_model": "opencode/arbitrary-runtime",
                "catalog_hash": "a" * 64,
                "execution_profile_hash": "b" * 64,
                "terminal_class": "auth_failure",
                "started_at": (finished - timedelta(seconds=1)).isoformat(),
                "finished_at": finished.isoformat(),
                "retry_count": index,
                "receipt_reference": "task:auth-fixture",
            }
        )

    vendors = _run(tmp_path, ["beat ok"], provider_outcomes=rows)

    assert vendors["opencode"]["provider_last_terminal_failure_class"] is None
    assert vendors["opencode"]["provider_outcome_observed_last_terminal_failure_class"] == "auth_failure"


def test_opencode_usage_derives_terminal_class_from_actual_provider_id(tmp_path):
    now = datetime.now(timezone.utc)
    finished = now - timedelta(seconds=1)
    rows = [
        {
            "schema": "limen.provider_outcome.v1",
            "provider": "openrouter",
            "runtime_model": "openrouter/hosted-runtime",
            "catalog_hash": "a" * 64,
            "execution_profile_hash": "b" * 64,
            "terminal_class": "auth_failure",
            "started_at": (finished - timedelta(seconds=1)).isoformat(),
            "finished_at": finished.isoformat(),
            "retry_count": 0,
            "receipt_reference": "task:hosted-auth-fixture",
        }
    ]

    vendors = _run(tmp_path, ["beat ok"], provider_outcomes=rows)

    assert vendors["opencode"]["provider_last_terminal_failure_class"] is None
    assert vendors["opencode"]["provider_terminal_failure_classes"] == {}
    assert vendors["opencode"]["provider_outcome_observed_terminal_failure_classes"] == {"openrouter": "auth_failure"}


def test_malformed_cooldown_env_does_not_crash(tmp_path):
    vendors = _run(
        tmp_path,
        ["beat ok"],
        extra_env={"LIMEN_RL_COOLDOWN_MIN": "not-a-number"},
    )

    assert vendors["gemini"]["health"] == "ok"


def test_malformed_reserve_env_does_not_poison_pacing(tmp_path):
    vendors = _run(
        tmp_path,
        ["beat ok"],
        extra_env={"LIMEN_RESERVE_PCT": "nan", "LIMEN_RESERVE_FLOOR_PCT": "200"},
    )

    assert vendors["gemini"]["reserve_pct"] == 15.0
    assert vendors["gemini"]["effective_reserve_pct"] == 15.0
    assert vendors["gemini"]["health"] == "ok"
