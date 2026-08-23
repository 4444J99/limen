"""Tests for the VIGILIA autonomic executive (build #1).

Hermetic: the real sysctl / codesign / ollama / transcript scans are monkeypatched
so the organs are exercised by logic, not by the host machine's current state.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from limen.vigilia import continuity, executive, integrity, params, vitals


# ---------------------------------------------------------------- params
def test_params_real_panel_loads():
    # the shipped panel must be readable and carry the VITALS thresholds.
    panel = params._load_panel()
    assert "VITALS_PRESSURE_WARN" in panel
    assert params.get("VITALS_PRESSURE_WARN", cast=int) == 2
    assert params.get("VITALS_PRESSURE_CRITICAL", cast=int) == 4


def test_params_env_override_wins(monkeypatch):
    monkeypatch.setenv("LIMEN_VITALS_WARN", "3")
    assert params.get("VITALS_PRESSURE_WARN", cast=int) == 3


def test_params_caller_default_for_unknown_key():
    assert params.get("NOPE_NOT_A_PARAM", default=7, cast=int) == 7


# ---------------------------------------------------------------- vitals
@pytest.mark.parametrize(
    "level,expected",
    [(1, vitals.OK), (2, vitals.THROTTLE), (3, vitals.THROTTLE), (4, vitals.SHED), (5, vitals.SHED)],
)
def test_vitals_assess(level, expected, monkeypatch):
    monkeypatch.setattr(
        params,
        "_load_panel",
        lambda: {"VITALS_PRESSURE_WARN": {"default": 2}, "VITALS_PRESSURE_CRITICAL": {"default": 4}},
    )
    assert vitals.assess(level) == expected


def test_vitals_read_pressure_parses_sysctl(monkeypatch):
    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout="2\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert vitals.read_pressure() == 2


def test_vitals_read_pressure_fail_open(monkeypatch):
    def boom(cmd, **kw):
        raise OSError("no sysctl")

    monkeypatch.setattr(subprocess, "run", boom)
    assert vitals.read_pressure() == 1  # normal — never blocks the beat


def test_vitals_beat_gate_sheds_only_at_critical(monkeypatch):
    monkeypatch.setattr(params, "_load_panel", lambda: {})  # use code defaults (warn 2, crit 4)
    shed_calls = []
    monkeypatch.setattr(vitals, "shed_ollama", lambda: shed_calls.append(True) or ["llama3"])
    monkeypatch.setattr(vitals, "read_load", lambda: 0.0)  # pin the load axis — memory only here
    monkeypatch.setattr(vitals, "read_swap", lambda: None)  # pin the swap axis too
    monkeypatch.setattr(vitals, "_update_warn_streak", lambda action, update: 0)  # no repo-side state

    monkeypatch.setattr(vitals, "read_pressure", lambda: 1)
    g = vitals.beat_gate(shed=True)
    assert g["action"] == "ok" and g["shed_ollama"] == [] and not shed_calls

    monkeypatch.setattr(vitals, "read_pressure", lambda: 2)
    g = vitals.beat_gate(shed=True)
    assert g["action"] == "throttle" and g["shed_ollama"] == [] and not shed_calls

    monkeypatch.setattr(vitals, "read_pressure", lambda: 4)
    g = vitals.beat_gate(shed=True)
    assert g["action"] == "shed" and g["shed_ollama"] == ["llama3"]


@pytest.mark.parametrize(
    "per_core,expected",
    [
        (0.0, vitals.OK),
        (1.49, vitals.OK),
        (1.5, vitals.THROTTLE),
        (2.9, vitals.THROTTLE),
        (3.0, vitals.SHED),
        (7.0, vitals.SHED),
    ],
)
def test_vitals_assess_load(per_core, expected, monkeypatch):
    monkeypatch.setattr(params, "_load_panel", lambda: {})  # code defaults: warn 1.5, crit 3.0
    assert vitals.assess_load(per_core) == expected


def test_vitals_read_load_fail_open(monkeypatch):
    def boom():
        raise OSError("no loadavg")

    monkeypatch.setattr(vitals.os, "getloadavg", boom)
    assert vitals.read_load() == 0.0  # normal — never blocks the beat


def test_vitals_beat_gate_combines_axes_by_max_severity(monkeypatch):
    monkeypatch.setattr(params, "_load_panel", lambda: {})
    monkeypatch.setattr(vitals, "shed_ollama", lambda: ["llama3"])
    monkeypatch.setattr(vitals, "read_swap", lambda: None)  # pin the swap axis
    monkeypatch.setattr(vitals, "_update_warn_streak", lambda action, update: 0)

    # memory ok + load critical -> SHED (a CPU-only storm sheds too; 2026-07-15 incident shape)
    monkeypatch.setattr(vitals, "read_pressure", lambda: 1)
    monkeypatch.setattr(vitals, "read_load", lambda: 5.0)
    g = vitals.beat_gate(shed=True)
    assert g["action"] == "shed" and g["memory_action"] == "ok" and g["load_action"] == "shed"
    assert g["shed_ollama"] == ["llama3"] and g["load_per_core"] == 5.0

    # memory warn + load ok -> THROTTLE (load axis never masks the memory axis)
    monkeypatch.setattr(vitals, "read_pressure", lambda: 2)
    monkeypatch.setattr(vitals, "read_load", lambda: 0.2)
    g = vitals.beat_gate(shed=True)
    assert g["action"] == "throttle" and g["load_action"] == "ok"

    # memory ok + load ok + swap crit -> SHED (2026-07-16 incident shape: swap axis can't be masked)
    monkeypatch.setattr(vitals, "read_pressure", lambda: 1)
    monkeypatch.setattr(vitals, "read_load", lambda: 0.2)
    gib = 2**30
    monkeypatch.setattr(
        vitals, "read_swap", lambda: {"total_bytes": 18 * gib, "used_bytes": 17 * gib, "ram_bytes": 16 * gib}
    )
    g = vitals.beat_gate(shed=True)
    assert g["action"] == "shed" and g["swap_action"] == "shed"
    assert g["swap_total_gib"] == 18.0 and g["ram_gib"] == 16.0


# ---------------------------------------------------------------- vitals: swap axis (2026-07-16)
_GIB = 2**30


def _swap(used_gib: float, total_gib: float, ram_gib: float = 16) -> dict:
    return {
        "used_bytes": int(used_gib * _GIB),
        "total_bytes": int(total_gib * _GIB),
        "ram_bytes": int(ram_gib * _GIB),
    }


@pytest.mark.parametrize(
    "swap,expected",
    [
        (None, vitals.OK),  # fail-open
        (_swap(0.5, 2), vitals.OK),  # healthy
        (_swap(11.5, 12), vitals.OK),  # 2026-07-16 POST-relief baseline: cold swap stock, modest estate
        (_swap(17.3, 18), vitals.SHED),  # 2026-07-16 thrash: estate 18 GiB >= RAM 16 GiB — OS overcommit
        (_swap(12.5, 14), vitals.THROTTLE),  # used 12.5 >= 0.75 x 16 = 12 — warn ramp
        (_swap(11.9, 14), vitals.OK),  # just under the warn ramp
    ],
)
def test_vitals_assess_swap(swap, expected, monkeypatch):
    monkeypatch.setattr(params, "_load_panel", lambda: {})  # code defaults: warn 0.75, crit 1.0
    assert vitals.assess_swap(swap) == expected


def test_vitals_read_swap_parses_sysctl(monkeypatch):
    outputs = {
        "vm.swapusage": "total = 18432.00M  used = 17280.88M  free = 1151.12M  (encrypted)\n",
        "hw.memsize": "17179869184\n",
    }

    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout=outputs[cmd[-1]], stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    swap = vitals.read_swap()
    assert swap["ram_bytes"] == 17179869184
    assert swap["total_bytes"] == 18432 * 1024 * 1024
    assert swap["used_bytes"] == int(17280.88 * 1024 * 1024)


def test_vitals_read_swap_fail_open(monkeypatch):
    def boom(cmd, **kw):
        raise OSError("no sysctl")

    monkeypatch.setattr(subprocess, "run", boom)
    assert vitals.read_swap() is None


def test_vitals_warn_streak_counts_resets_and_escalates(tmp_path, monkeypatch):
    monkeypatch.setattr(params, "_load_panel", lambda: {})
    monkeypatch.setattr(vitals, "_streak_path", lambda: tmp_path / "vitals-streak.json")
    clock = {"now": 1_000_000.0}
    monkeypatch.setattr(vitals.time, "time", lambda: clock["now"])

    # counts once per >=60s gate beat, not on rapid re-invocation
    assert vitals._update_warn_streak(vitals.THROTTLE, update=True) == 1
    assert vitals._update_warn_streak(vitals.THROTTLE, update=True) == 1  # <60s: no double-count
    clock["now"] += 61
    assert vitals._update_warn_streak(vitals.THROTTLE, update=True) == 2
    # read-only path never increments
    assert vitals._update_warn_streak(vitals.THROTTLE, update=False) == 2
    # ok resets
    clock["now"] += 61
    assert vitals._update_warn_streak(vitals.OK, update=True) == 0

    # sustained warn escalates the gate to shed (streak >= VITALS_WARN_SUSTAIN_BEATS)
    monkeypatch.setattr(vitals, "read_pressure", lambda: 2)  # warn
    monkeypatch.setattr(vitals, "read_load", lambda: 0.0)
    monkeypatch.setattr(vitals, "read_swap", lambda: None)
    monkeypatch.setattr(vitals, "shed_ollama", lambda: [])
    monkeypatch.setattr(vitals, "_update_warn_streak", lambda action, update: 3)
    g = vitals.beat_gate(shed=True)
    assert g["action"] == "shed" and g["sustained_warn"] is True and g["warn_streak"] == 3


def test_organ_health_vigilia_uses_fast_sample_clock(monkeypatch):
    script = Path(__file__).resolve().parents[2] / "scripts" / "organ-health.py"
    spec = importlib.util.spec_from_file_location("organ_health_vigilia_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    vigilia = next(row for row in module._registry() if row["key"] == "vigilia")
    assert vigilia["probe_first"] is True
    assert vigilia["interval_s"] == 300

    monkeypatch.setattr(module, "_loop_text", lambda: "")
    monkeypatch.setattr(
        module,
        "_doors",
        lambda _text: [dict(vigilia, probe=lambda: 200)],
    )
    monkeypatch.setattr(module, "_voice_stamp", lambda _voice: 100)
    monkeypatch.setattr(module.time, "time", lambda: 250)

    row = module.build()["organs"][0]

    assert row["source"] == "artifact"
    assert row["last_fired"] == datetime.fromtimestamp(200).isoformat(timespec="seconds")
    assert row["expected_h"] == 0.1


def test_heartbeat_vitals_leaves_provider_admission_to_the_campaign_supervisor():
    heartbeat = (Path(__file__).resolve().parents[2] / "scripts" / "heartbeat-loop.sh").read_text(encoding="utf-8")

    assert "canonical campaign wake remains live" in heartbeat
    assert 'scripts/campaign-heartbeat.py"' in heartbeat
    assert "campaign admission remains keeper-owned" in heartbeat
    assert "VITALS_THROTTLE" not in heartbeat


def test_launchd_heartbeat_generator_and_template_are_retired():
    root = Path(__file__).resolve().parents[2]
    assert not (root / "scripts/gen-launchd-plist.sh").exists()
    assert not (root / "container/launchd/com.limen.heartbeat.plist.tmpl").exists()


# ---------------------------------------------------------------- continuity
def test_continuity_parse_rows_skips_garbage(tmp_path):
    f = tmp_path / "t.jsonl"
    f.write_text('{"a":1}\nNOT JSON\n\n{"b":2}\n')
    rows = continuity.parse_rows(f)
    assert rows == [{"a": 1}, {"b": 2}]


def test_continuity_row_text_from_blocks():
    row = {
        "message": {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "hello"},
                {"type": "tool_use", "name": "Bash"},
            ],
        }
    }
    role, text = continuity._row_text(row)
    assert role == "assistant"
    assert "hello" in text and "Bash" in text


def test_continuity_is_degenerate():
    assert continuity.is_degenerate("tiny", 400) is True
    assert continuity.is_degenerate("x" * 500, 400) is False
    assert continuity.is_degenerate(None, 400) is False


def test_continuity_reconstruct_uses_last_good_summary_then_tail():
    rows = [
        {"isCompactSummary": True, "message": {"role": "user", "content": "G" * 500}},
        {"message": {"role": "user", "content": [{"type": "text", "text": "next question"}]}},
        {"message": {"role": "assistant", "content": [{"type": "text", "text": "the answer"}]}},
    ]
    out = continuity.reconstruct(rows, min_chars=400)
    assert "Recovered base summary" in out
    assert "next question" in out and "the answer" in out


def test_continuity_beat_reconstructs_degenerate_handoff(tmp_path, monkeypatch):
    proj = tmp_path / "projects" / "sess"
    proj.mkdir(parents=True)
    transcript = proj / "abc.jsonl"
    rows = [
        {"isCompactSummary": True, "message": {"role": "user", "content": "G" * 500}},
        {"message": {"role": "assistant", "content": [{"type": "text", "text": "did work"}]}},
        # the degenerate auto-handoff: a tiny final summary
        {"isCompactSummary": True, "message": {"role": "user", "content": "Summary:\n1."}},
    ]
    transcript.write_text("\n".join(json.dumps(r) for r in rows))

    monkeypatch.setenv("LIMEN_CONTINUITY_TRANSCRIPTS", str(tmp_path / "projects" / "*" / "*.jsonl"))
    out_dir = tmp_path / "out"
    monkeypatch.setattr(continuity, "_out_dir", lambda: out_dir.mkdir(exist_ok=True) or out_dir)

    res = continuity.beat()
    assert res["degenerate"] is True
    assert res["status"] == "reconstructed"
    written = Path(res["reconstruction"]).read_text()
    assert "did work" in written


# ---------------------------------------------------------------- integrity
def test_integrity_as_list_handles_string_and_list():
    assert integrity._as_list(["/a", "/b"]) == ["/a", "/b"]
    assert integrity._as_list("/a,/b") == ["/a", "/b"]
    assert integrity._as_list("") == []


def test_integrity_assess_flags_signature_drift():
    bad = [{"valid": False}]
    good = [{"valid": True}]
    assert integrity.assess(bad, intended_enabled=True, disabled_controls=[]) is True
    assert integrity.assess(good, intended_enabled=True, disabled_controls=[]) is False
    assert (
        integrity.assess(
            good,
            intended_enabled=True,
            disabled_controls=["DISABLE_UPDATES"],
        )
        is True
    )
    assert integrity.assess(good, intended_enabled=False, disabled_controls=[]) is True
    assert (
        integrity.assess(
            [{"exists": False, "valid": None, "required": True}],
            intended_enabled=True,
            disabled_controls=[],
        )
        is True
    )
    assert (
        integrity.assess(
            [{"exists": False, "valid": None, "required": False}],
            intended_enabled=True,
            disabled_controls=[],
        )
        is False
    )


def test_integrity_check_no_drift_when_signed_and_updates_enabled(monkeypatch):
    monkeypatch.setattr(
        params,
        "_load_panel",
        lambda: {
            "INTEGRITY_VERIFY_TARGETS": {"default": ["/Applications/Claude.app"]},
            "INTEGRITY_AUTOUPDATER": {"default": "enabled", "env": "LIMEN_INTEGRITY_AUTOUPDATER"},
        },
    )
    monkeypatch.setattr(integrity, "verify_target", lambda t: {"target": t, "exists": True, "valid": True})
    for key in ("DISABLE_AUTOUPDATER", "DISABLE_UPDATES", "HOMEBREW_NO_AUTO_UPDATE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("LIMEN_INTEGRITY_AUTOUPDATER", raising=False)
    res = integrity.check()
    assert res["autoupdater_intended"] == "enabled"
    assert res["autoupdater_actual"] == "enabled"
    assert res["update_disable_controls"] == []
    assert res["drift"] is False and res["status"] == "ok"


def test_integrity_check_flags_active_update_disabling_control(monkeypatch):
    monkeypatch.setattr(
        params,
        "_load_panel",
        lambda: {
            "INTEGRITY_VERIFY_TARGETS": {"default": ["/Applications/Claude.app"]},
            "INTEGRITY_AUTOUPDATER": {
                "default": "enabled",
                "env": "LIMEN_INTEGRITY_AUTOUPDATER",
            },
        },
    )
    monkeypatch.setattr(
        integrity,
        "verify_target",
        lambda target: {"target": target, "exists": True, "valid": True},
    )
    monkeypatch.delenv("DISABLE_AUTOUPDATER", raising=False)
    monkeypatch.delenv("DISABLE_UPDATES", raising=False)
    monkeypatch.setenv("HOMEBREW_NO_AUTO_UPDATE", " true ")

    result = integrity.check()

    assert result["autoupdater_actual"] == "disabled"
    assert result["update_disable_controls"] == ["HOMEBREW_NO_AUTO_UPDATE"]
    assert result["drift"] is True


def test_integrity_check_flags_missing_required_host(monkeypatch):
    host = str(Path("~/Applications/DomusAgentHost.app").expanduser())
    monkeypatch.delenv("LIMEN_AGENT_HOST_BIN", raising=False)
    monkeypatch.setattr(
        params,
        "_load_panel",
        lambda: {
            "INTEGRITY_VERIFY_TARGETS": {
                "default": [
                    "~/Applications/DomusAgentHost.app",
                    "/Applications/Claude.app",
                ]
            },
            "INTEGRITY_AUTOUPDATER": {
                "default": "enabled",
                "env": "LIMEN_INTEGRITY_AUTOUPDATER",
            },
        },
    )
    monkeypatch.setattr(
        integrity,
        "verify_target",
        lambda target: {
            "target": str(Path(target).expanduser()),
            "exists": str(Path(target).expanduser()) != host,
            "valid": None if str(Path(target).expanduser()) == host else True,
        },
    )
    for key in (
        "DISABLE_AUTOUPDATER",
        "DISABLE_UPDATES",
        "HOMEBREW_NO_AUTO_UPDATE",
    ):
        monkeypatch.delenv(key, raising=False)

    result = integrity.check(platform_name="Darwin")

    assert result["drift"] is True
    assert result["status"] == "drift"
    assert next(item for item in result["targets"] if item["target"] == host)["required"] is True


def test_integrity_check_does_not_require_macos_host_on_linux(monkeypatch):
    host = str(Path("~/Applications/DomusAgentHost.app").expanduser())
    monkeypatch.delenv("LIMEN_AGENT_HOST_BIN", raising=False)
    monkeypatch.setattr(
        params,
        "_load_panel",
        lambda: {
            "INTEGRITY_VERIFY_TARGETS": {
                "default": [
                    "~/Applications/DomusAgentHost.app",
                    "/Applications/Claude.app",
                ]
            },
            "INTEGRITY_AUTOUPDATER": {
                "default": "enabled",
                "env": "LIMEN_INTEGRITY_AUTOUPDATER",
            },
        },
    )
    monkeypatch.setattr(
        integrity,
        "verify_target",
        lambda target: {
            "target": str(Path(target).expanduser()),
            "exists": str(Path(target).expanduser()) != host,
            "valid": None if str(Path(target).expanduser()) == host else True,
        },
    )
    for key in (
        "DISABLE_AUTOUPDATER",
        "DISABLE_UPDATES",
        "HOMEBREW_NO_AUTO_UPDATE",
    ):
        monkeypatch.delenv(key, raising=False)

    result = integrity.check(platform_name="Linux")

    assert result["platform"] == "Linux"
    assert result["drift"] is False
    assert result["status"] == "ok"
    assert next(item for item in result["targets"] if item["target"] == host)["required"] is False


# ---------------------------------------------------------------- executive
def test_executive_run_beat_aggregates_and_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(executive, "_status_dir", lambda: tmp_path)
    monkeypatch.setattr(vitals, "beat_gate", lambda shed=False: {"organ": "vitals", "level": 1, "action": "ok"})
    monkeypatch.setattr(continuity, "beat", lambda: {"organ": "continuity", "status": "ok"})
    monkeypatch.setattr(integrity, "check", lambda: {"organ": "integrity", "status": "ok"})

    status = executive.run_beat()
    assert set(status) >= {"institution", "sampled_at", "completed_at", "vitals", "continuity", "integrity"}
    assert set(status) >= {"boot_identity", "sampled_monotonic_seconds", "wake_state"}
    assert "ts" not in status
    assert (tmp_path / "status.json").exists()
    assert "vitals=L1/ok" in executive.summary_line(status)


def test_slow_full_beat_keeps_the_early_sample_clock(tmp_path, monkeypatch):
    clock = {"now": datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(executive, "_status_dir", lambda: tmp_path)
    monkeypatch.setattr(executive, "_now", lambda: clock["now"])
    monkeypatch.setattr(vitals, "beat_gate", lambda shed=False: {"organ": "vitals", "level": 1, "action": "ok"})

    def slow_continuity():
        clock["now"] += timedelta(hours=4)
        return {"organ": "continuity", "status": "ok"}

    monkeypatch.setattr(continuity, "beat", slow_continuity)
    monkeypatch.setattr(integrity, "check", lambda: {"organ": "integrity", "status": "ok"})

    status = executive.run_beat()

    assert status["sampled_at"] == "2026-08-08T12:00:00+00:00"
    assert status["completed_at"] == "2026-08-08T16:00:00+00:00"


def test_full_beat_preserves_early_sample_error(tmp_path, monkeypatch):
    monkeypatch.setattr(executive, "_status_dir", lambda: tmp_path)
    monkeypatch.setattr(
        vitals,
        "beat_gate",
        lambda shed=False: (_ for _ in ()).throw(RuntimeError("sample unavailable")),
    )
    monkeypatch.setattr(continuity, "beat", lambda: {"organ": "continuity", "status": "ok"})
    monkeypatch.setattr(integrity, "check", lambda: {"organ": "integrity", "status": "ok"})

    status = executive.run_beat()

    assert status["sample_error"]["status"] == "error"
    assert status["vitals"]["status"] == "error"


def test_later_successful_sample_supersedes_early_error(tmp_path, monkeypatch):
    clock = {"now": datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)}
    probes = iter(
        [
            RuntimeError("early sample unavailable"),
            {"organ": "vitals", "status": "ok", "action": "ok"},
        ]
    )
    monkeypatch.setattr(executive, "_status_dir", lambda: tmp_path)
    monkeypatch.setattr(executive, "_now", lambda: clock["now"])

    def probe(shed=False):
        result = next(probes)
        if isinstance(result, Exception):
            raise result
        return result

    def continuity_with_fast_sample():
        clock["now"] += timedelta(seconds=1)
        executive.sample_vitals()
        return {"organ": "continuity", "status": "ok"}

    monkeypatch.setattr(vitals, "beat_gate", probe)
    monkeypatch.setattr(continuity, "beat", continuity_with_fast_sample)
    monkeypatch.setattr(integrity, "check", lambda: {"organ": "integrity", "status": "ok"})

    status = executive.run_beat()

    assert status["vitals"]["status"] == "ok"
    assert "sample_error" not in status


def test_heartbeat_resident_sleep_uses_interruptible_helper():
    source = (Path(__file__).resolve().parents[2] / "scripts" / "heartbeat-loop.sh").read_text(encoding="utf-8")

    assert "_interruptible_sleep()" in source
    watchdog = source[
        source.index("stale_watchdog_loop()") : source.index(
            "\n\nfast_wave_loop()", source.index("stale_watchdog_loop()")
        )
    ]
    fast_wave = source[source.index("fast_wave_loop()") : source.index("\n\n# ", source.index("fast_wave_loop()"))]
    assert '\\n  sleep "$FAST_WAVE_SECONDS"' not in watchdog
    assert '\\n  sleep "$_fw_wait"' not in fast_wave


def test_interruptible_sleep_uses_one_timer_without_per_second_churn():
    source = (Path(__file__).resolve().parents[2] / "scripts" / "heartbeat-loop.sh").read_text(encoding="utf-8")
    helper = source[source.index("_interruptible_sleep()") : source.index("\n}\n\n_fast_wave_due_beat")]
    assert 'sleep "$_sleep_remaining"' in helper
    assert "sleep 1" not in helper


def test_heartbeat_fast_wave_is_independent_of_the_slow_main_loop():
    heartbeat = (Path(__file__).resolve().parents[2] / "scripts" / "heartbeat-loop.sh").read_text(encoding="utf-8")

    launch = heartbeat.index('fast_wave_loop "$$" &')
    main_loop = heartbeat.index("while true; do", launch)
    fast_body = heartbeat[heartbeat.index("fast_wave_bounded()") : launch]

    assert launch < main_loop
    assert "python3 -m limen.vigilia sample" in fast_body
    assert "fast_wave_aux_once diurnal" in fast_body
    assert "fast_wave_aux_once health" in fast_body
    assert "_fw_diurnal_pending" in fast_body
    assert "_fw_health_pending" in fast_body
    assert "beat-sensors.py" in fast_body and "--source fast-wave" in fast_body
    assert "scripts/organ-health.py" in fast_body
    assert 'python3 - "$_fw_timeout" "$@"' in fast_body
    assert "BASHPID" not in fast_body
    assert '[ "$FAST_WAVE_SECONDS" -ge 60 ]' not in heartbeat
    assert "${LIMEN_BEAT_DERIVE:-1}" in fast_body
    assert "signal.signal(signal.SIGTERM, terminate_group)" in fast_body
    assert "_fast_wave_cleanup" in fast_body
    assert "_fw_sample_rc=125" in fast_body
    assert "running without capture" in fast_body
    assert "_fast_wave_kill_tree" in fast_body
    assert "pgrep -P" in fast_body
    watchdog_launch = heartbeat.index('stale_watchdog_loop "$$" &')
    assert watchdog_launch < main_loop
    assert "scripts/host-pressure-stale.py" in heartbeat[heartbeat.index("stale_watchdog_loop()") : launch]
    assert "HOST_PRESSURE_WATCHDOG_PID" in heartbeat[heartbeat.index("cleanup()") : main_loop]


def test_fast_wave_prefers_due_pending_visits():
    heartbeat = (Path(__file__).resolve().parents[2] / "scripts" / "heartbeat-loop.sh").read_text(encoding="utf-8")
    diurnal_start = heartbeat.index('    if [ -n "$_fw_diurnal_pid" ]')
    health_start = heartbeat.index('    if [ -n "$_fw_health_pid" ]')
    diurnal = heartbeat[diurnal_start:health_start]

    assert "_fast_wave_due_beat" in heartbeat
    assert 'if _fast_wave_due_beat "${LIMEN_BEAT_DIURNAL:-1}" "$FAST_WAVE_BEAT"; then' in diurnal
    assert '_fw_diurnal_pending="$FAST_WAVE_BEAT"' in diurnal
    assert '[ -n "$_fw_diurnal_pending" ] || _fw_diurnal_pending="$FAST_WAVE_BEAT"' in diurnal
    assert '[ -n "$_fw_health_pending" ] || _fw_health_pending="$FAST_WAVE_BEAT"' in heartbeat[health_start:]
    assert '_fw_diurnal_beat="${_fw_diurnal_pending:-$FAST_WAVE_BEAT}"' in heartbeat
    assert 'if _fast_wave_due_beat "${LIMEN_BEAT_DIURNAL:-1}" "$FAST_WAVE_BEAT"; then' in heartbeat
    assert '_fw_diurnal_beat="$FAST_WAVE_BEAT"' in heartbeat
    assert 'case "$_fw_cadence" in' in heartbeat
    assert "fast-wave: watchdog log unavailable" in heartbeat
    assert '_fw_health_beat="${_fw_health_pending:-$FAST_WAVE_BEAT}"' in heartbeat


def test_metabolize_host_pressure_probe_is_read_only():
    sensors = (Path(__file__).resolve().parents[2] / "institutio" / "governance" / "sensors.yaml").read_text(
        encoding="utf-8"
    )
    start = sensors.index("  host-pressure-stale:")
    end = sensors.index("\n  runtime-lag:", start)
    assert "source: [metabolize]" in sensors[start:end]
    assert "host-pressure-stale.py --read-only" in sensors[start:end]


def test_overlapping_samples_cannot_replace_a_newer_timestamp(tmp_path, monkeypatch):
    old_time = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    new_time = old_time + timedelta(seconds=1)
    old_started = threading.Event()
    release_old = threading.Event()
    monkeypatch.setattr(executive, "_status_dir", lambda: tmp_path)
    monkeypatch.setattr(
        executive,
        "_now",
        lambda: old_time if threading.current_thread().name == "old-sample" else new_time,
    )

    def gate(shed=False):
        if threading.current_thread().name == "old-sample":
            old_started.set()
            assert release_old.wait(timeout=5)
            return {"organ": "vitals", "status": "old"}
        return {"organ": "vitals", "status": "new"}

    monkeypatch.setattr(vitals, "beat_gate", gate)
    old = threading.Thread(target=executive.sample_vitals, name="old-sample")
    old.start()
    assert old_started.wait(timeout=5)
    executive.sample_vitals()
    release_old.set()
    old.join(timeout=5)

    status = json.loads((tmp_path / "status.json").read_text())
    assert status["sampled_at"] == new_time.isoformat()
    assert status["vitals"]["status"] == "new"


def test_new_early_sample_survives_transient_seat_write_failure(tmp_path, monkeypatch):
    old = {
        "institution": "VIGILIA",
        "sampled_at": "2026-08-08T12:00:00+00:00",
        "completed_at": "2026-08-08T12:01:00+00:00",
        "vitals": {"organ": "vitals", "status": "old", "action": "ok"},
    }
    early = {
        "institution": "VIGILIA",
        "sampled_at": "2026-08-08T12:02:00+00:00",
        "vitals": {"organ": "vitals", "status": "new", "action": "ok"},
    }
    monkeypatch.setattr(executive, "sample_vitals", lambda: early)
    monkeypatch.setattr(executive, "_status_dir", lambda: tmp_path)
    monkeypatch.setattr(
        executive, "continuity", type("Continuity", (), {"beat": staticmethod(lambda: {"status": "ok"})})
    )
    monkeypatch.setattr(
        executive, "integrity", type("Integrity", (), {"check": staticmethod(lambda: {"status": "ok"})})
    )
    monkeypatch.setattr(executive, "_update_status", lambda mutator: mutator(old))

    status = executive.run_beat()

    assert status["sampled_at"] == early["sampled_at"]
    assert status["vitals"] == early["vitals"]


def test_failed_vitals_probe_does_not_refresh_a_valid_sample(tmp_path, monkeypatch):
    previous = {
        "institution": "VIGILIA",
        "sampled_at": "2026-08-08T12:00:00+00:00",
        "completed_at": "2026-08-08T12:01:00+00:00",
        "vitals": {"organ": "vitals", "status": "ok", "action": "ok"},
    }
    (tmp_path / "status.json").write_text(json.dumps(previous), encoding="utf-8")
    monkeypatch.setattr(executive, "_status_dir", lambda: tmp_path)
    monkeypatch.setattr(
        vitals,
        "beat_gate",
        lambda shed=False: (_ for _ in ()).throw(RuntimeError("probe failed")),
    )

    status = executive.sample_vitals()

    assert status["sampled_at"] == previous["sampled_at"]
    assert status["vitals"] == previous["vitals"]
    assert status["sample_error"]["status"] == "error"


def test_executive_one_organ_fault_does_not_break_the_beat(tmp_path, monkeypatch):
    monkeypatch.setattr(executive, "_status_dir", lambda: tmp_path)
    monkeypatch.setattr(vitals, "beat_gate", lambda shed=False: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(continuity, "beat", lambda: {"organ": "continuity", "status": "ok"})
    monkeypatch.setattr(integrity, "check", lambda: {"organ": "integrity", "status": "ok"})

    status = executive.run_beat()
    assert status["vitals"]["status"] == "error"  # captured, not raised
    assert status["continuity"]["status"] == "ok"


def test_early_sample_error_survives_transient_seat_write(tmp_path, monkeypatch):
    monkeypatch.setattr(executive, "_status_dir", lambda: tmp_path)
    (tmp_path / "status.json").write_text(
        json.dumps(
            {
                "sampled_at": "2026-08-08T11:59:00+00:00",
                "vitals": {"organ": "vitals", "level": 1, "action": "ok"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        vitals,
        "beat_gate",
        lambda shed=False: (_ for _ in ()).throw(RuntimeError("sample unavailable")),
    )
    monkeypatch.setattr(continuity, "beat", lambda: {"organ": "continuity", "status": "ok"})
    monkeypatch.setattr(integrity, "check", lambda: {"organ": "integrity", "status": "ok"})

    real_update = executive._update_status
    calls = {"count": 0}

    def flaky_update(mutator):
        calls["count"] += 1
        if calls["count"] == 1:
            return mutator({})
        return real_update(mutator)

    monkeypatch.setattr(executive, "_update_status", flaky_update)
    status = executive.run_beat()

    assert status["sample_error"]["error"] == "sample unavailable"
    assert status["sample_error_at"]


def test_sample_reports_unpersisted_receipt(tmp_path, monkeypatch):
    monkeypatch.setattr(executive, "_status_dir", lambda: tmp_path)
    monkeypatch.setattr(
        vitals,
        "beat_gate",
        lambda shed=False: {"organ": "vitals", "status": "ok", "action": "ok"},
    )
    monkeypatch.setattr(
        executive,
        "_update_status",
        lambda mutator: {**mutator({}), "_persistence_error": "disk full"},
    )

    status = executive.sample_vitals()

    assert status["sample_persisted"] is False
    assert status["_persistence_error"] == "disk full"
