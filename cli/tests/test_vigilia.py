"""Tests for the VIGILIA autonomic executive (build #1).

Hermetic: the real sysctl / codesign / ollama / transcript scans are monkeypatched
so the organs are exercised by logic, not by the host machine's current state.
"""

from __future__ import annotations

import json
import subprocess
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
    monkeypatch.setattr(params, "_load_panel", dict)  # use code defaults (warn 2, crit 4)
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
    monkeypatch.setattr(params, "_load_panel", dict)  # code defaults: warn 1.5, crit 3.0
    assert vitals.assess_load(per_core) == expected


def test_vitals_read_load_fail_open(monkeypatch):
    def boom():
        raise OSError("no loadavg")

    monkeypatch.setattr(vitals.os, "getloadavg", boom)
    assert vitals.read_load() == 0.0  # normal — never blocks the beat


def test_vitals_beat_gate_combines_axes_by_max_severity(monkeypatch):
    monkeypatch.setattr(params, "_load_panel", dict)
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
    monkeypatch.setattr(params, "_load_panel", dict)  # code defaults: warn 0.75, crit 1.0
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
    monkeypatch.setattr(params, "_load_panel", dict)
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
    monkeypatch.setattr(vitals, "shed_ollama", list)
    monkeypatch.setattr(vitals, "_update_warn_streak", lambda action, update: 3)
    g = vitals.beat_gate(shed=True)
    assert g["action"] == "shed" and g["sustained_warn"] is True and g["warn_streak"] == 3


def test_heartbeat_vitals_preserves_remote_dispatch_and_throttles_both_local_modes():
    heartbeat = (Path(__file__).resolve().parents[2] / "scripts" / "heartbeat-loop.sh").read_text(encoding="utf-8")

    assert "vitals-pressure: dispatch skipped" not in heartbeat
    assert "local admission shed; remote dispatch remains live" in heartbeat
    assert '_async_max="$HOST_LOCAL_CEILING"' in heartbeat
    assert '_sync_workers="${LIMEN_WORKERS:-$HOST_LOCAL_CEILING}"' in heartbeat
    assert '--workers "$_sync_workers"' in heartbeat


def test_launchd_local_ceiling_has_no_literal_fleet_cap():
    generator = (Path(__file__).resolve().parents[2] / "scripts" / "gen-launchd-plist.sh").read_text(encoding="utf-8")

    assert 'ASYNC_MAX_DERIVED="$NCPU"' in generator
    assert "NCPU > 12" not in generator


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
    assert integrity.assess(bad, intended_disabled=True, actually_disabled=True) is True
    assert integrity.assess(good, intended_disabled=True, actually_disabled=True) is False
    # lever drift: intended disabled but actually enabled
    assert integrity.assess(good, intended_disabled=True, actually_disabled=False) is True


def test_integrity_check_no_drift_when_signed_and_lever_set(monkeypatch):
    monkeypatch.setattr(
        params,
        "_load_panel",
        lambda: {
            "INTEGRITY_VERIFY_TARGETS": {"default": ["/Applications/Claude.app"]},
            "INTEGRITY_AUTOUPDATER": {"default": "disabled", "env": "LIMEN_INTEGRITY_AUTOUPDATER"},
        },
    )
    monkeypatch.setattr(integrity, "verify_target", lambda t: {"target": t, "exists": True, "valid": True})
    monkeypatch.setenv("DISABLE_AUTOUPDATER", "1")
    monkeypatch.delenv("LIMEN_INTEGRITY_AUTOUPDATER", raising=False)
    res = integrity.check()
    assert res["autoupdater_intended"] == "disabled"
    assert res["autoupdater_actual"] == "disabled"
    assert res["drift"] is False and res["status"] == "ok"


# ---------------------------------------------------------------- executive
def test_executive_run_beat_aggregates_and_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(executive, "_status_dir", lambda: tmp_path)
    monkeypatch.setattr(vitals, "beat_gate", lambda shed=False: {"organ": "vitals", "level": 1, "action": "ok"})
    monkeypatch.setattr(continuity, "beat", lambda: {"organ": "continuity", "status": "ok"})
    monkeypatch.setattr(integrity, "check", lambda: {"organ": "integrity", "status": "ok"})

    status = executive.run_beat()
    assert set(status) >= {"institution", "vitals", "continuity", "integrity"}
    assert (tmp_path / "status.json").exists()
    assert "vitals=L1/ok" in executive.summary_line(status)


def test_executive_one_organ_fault_does_not_break_the_beat(tmp_path, monkeypatch):
    monkeypatch.setattr(executive, "_status_dir", lambda: tmp_path)
    monkeypatch.setattr(vitals, "beat_gate", lambda shed=False: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(continuity, "beat", lambda: {"organ": "continuity", "status": "ok"})
    monkeypatch.setattr(integrity, "check", lambda: {"organ": "integrity", "status": "ok"})

    status = executive.run_beat()
    assert status["vitals"]["status"] == "error"  # captured, not raised
    assert status["continuity"]["status"] == "ok"
