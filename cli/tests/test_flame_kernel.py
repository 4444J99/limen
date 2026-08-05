"""Tests for the Continuity Kernel (dispatch._flame_preamble / _build_prompt) and the ollama
local floor lane (capacity.ollama_model / agent_status + dispatch cascade).

The kernel is the portable *self* prepended to EVERY lane's prompt so the identity + invariants
ride every dispatch regardless of which model runs the beat — Claude, codex, ollama, whatever.
It must fail OPEN: a missing/disabled kernel is the bare prompt (today's behavior), never a block.

ollama is the unmetered local floor: the LAST cascade lane, self-activating (reachable only once a
model is pulled), so the flame still produces when every metered/cloud vendor is spent.
"""

from __future__ import annotations

from datetime import date

import limen.capacity as C
import limen.dispatch as D
from limen.models import Task


def _task():
    return Task(id="T1", title="do a thing", repo="org/repo", target_agent="ollama", created=date(2026, 6, 23))


def _write_kernel(root, text="# FLAME\nYou are VLTIMA.\n"):
    (root / "FLAME.md").write_text(text)


def test_kernel_rides_every_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.delenv("LIMEN_FLAME_KERNEL", raising=False)
    _write_kernel(tmp_path)
    D._FLAME_CACHE.clear()
    p = D._build_prompt(_task())
    assert "You are VLTIMA." in p  # the self rides along
    assert "YOUR TASK THIS BEAT" in p  # divider separates identity from work
    assert "do a thing" in p  # the concrete task is still there
    assert "VALUE GATE" in p
    assert "VERIFICATION DISCIPLINE" in p
    assert "Do not run scripts/verify-whole.sh" in p


def test_value_gate_carries_task_statistics(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_FLAME_KERNEL", "0")
    monkeypatch.delenv("LIMEN_VALUE_REPOS", raising=False)
    monkeypatch.delenv("LIMEN_VALUE_REPOS_FILE", raising=False)
    (tmp_path / "value-repos.json").write_text('{"repos":["org/repo"]}', encoding="utf-8")
    D._FLAME_CACHE.clear()
    p = D._build_prompt(_task())
    assert "VALUE GATE" in p
    assert "priority=medium" in p
    assert "budget_cost=1" in p
    assert "repo_in_value_tier=true" in p
    assert "value_tier_repo_count=1" in p
    assert "warm leads" in p


def test_kernel_disabled_is_bare_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_FLAME_KERNEL", "0")
    _write_kernel(tmp_path)
    D._FLAME_CACHE.clear()
    p = D._build_prompt(_task())
    assert "VLTIMA" not in p
    assert p.startswith("Complete task T1")
    assert "VERIFICATION DISCIPLINE" in p


def test_missing_kernel_fails_open(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))  # no FLAME.md on disk
    monkeypatch.delenv("LIMEN_FLAME_KERNEL", raising=False)
    D._FLAME_CACHE.clear()
    p = D._build_prompt(_task())
    assert p.startswith("Complete task T1")  # bare prompt, never a blocked lane


def test_jules_prompt_leads_with_directive(tmp_path, monkeypatch):
    # The jules lane MUST lead with the hard "implement directly, do NOT ask for feedback"
    # directive — that is the proven anti-stall lever (the jules CLI has no approve/reply verb, so
    # a planner that stops to ask is a dead session). The task still leads the body (task-first)
    # under the directive, with the kernel riding after.
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.delenv("LIMEN_FLAME_KERNEL", raising=False)
    monkeypatch.delenv("LIMEN_JULES_DIRECTIVE", raising=False)
    _write_kernel(tmp_path)
    D._FLAME_CACHE.clear()
    p = D._build_jules_prompt(_task())
    assert p.startswith("Implement this directly")  # anti-stall lead dominates
    assert "Do NOT ask for feedback" in p
    assert "do a thing" in p  # the concrete task is present
    assert p.index("do a thing") < p.index("You are VLTIMA.")  # task before kernel


def test_jules_directive_disabled_is_task_first(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_JULES_DIRECTIVE", "0")
    monkeypatch.delenv("LIMEN_FLAME_KERNEL", raising=False)
    _write_kernel(tmp_path)
    D._FLAME_CACHE.clear()
    p = D._build_jules_prompt(_task())
    assert not p.startswith("Implement this directly")
    assert p.startswith("Complete task T1")  # bare task-first prompt


def test_call_jules_uses_remote_new(tmp_path, monkeypatch):
    # `jules remote new` (autonomous VM) — NOT `jules new` (web plan-approval → "Awaiting User
    # Feedback"). The task is fed via --session, and the directive leads the prompt.
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.delenv("LIMEN_FLAME_KERNEL", raising=False)
    monkeypatch.delenv("LIMEN_JULES_DIRECTIVE", raising=False)
    captured = {}

    def fake_run_cmd(cmd, task, dry_run, cwd=None):
        captured["cmd"] = cmd
        return "5450674856461095192"

    monkeypatch.setattr(D, "_run_cmd", fake_run_cmd)
    t = Task(id="T1", title="do a thing", repo="org/repo", target_agent="jules", created=date(2026, 6, 23))
    sid = D._call_jules(t, dry_run=False)
    cmd = captured["cmd"]
    assert cmd[:5] == ["jules", "remote", "new", "--repo", "org/repo"]
    assert cmd[5] == "--session"
    assert cmd[6].startswith("Implement this directly")  # directive-led prompt as the task
    assert sid == "5450674856461095192"  # session id flows back for dispatch_log


def test_run_cmd_captures_jules_session_id(monkeypatch):
    # The id must be captured from `jules remote new` stdout (ID: line) so it lands in dispatch_log
    # and harvest matches by id, never the truncated/directive-led session title.
    class _R:
        returncode = 0
        stdout = (
            "Session is created.\nID: 5450674856461095192\nURL: https://jules.google.com/session/5450674856461095192\n"
        )
        stderr = ""

    monkeypatch.setattr(D, "_run_capture", lambda *a, **k: _R())
    t = Task(id="T1", title="x", repo="org/repo", target_agent="jules", created=date(2026, 6, 23))
    out = D._run_cmd(["jules", "remote", "new", "--repo", "org/repo", "--session", "p"], t, dry_run=False)
    assert out == "5450674856461095192"


def test_ollama_is_cascade_floor(monkeypatch):
    monkeypatch.delenv("LIMEN_DISPATCH_LANES", raising=False)
    monkeypatch.setattr(D, "_down_lanes", lambda: set())
    assert "ollama" in C.PAID_AGENT_ORDER
    assert "ollama" in C.LOCAL_CHECKOUT_AGENTS
    assert D._LANE_CASCADE[-1] == "ollama"  # the very last resort
    monkeypatch.setattr(D, "select_lanes", lambda *a, **k: ["opencode", "agy", "jules"])
    assert D._next_lane("jules") is None  # floor is not used until a model makes it reachable
    monkeypatch.setattr(D, "select_lanes", lambda *a, **k: ["opencode", "agy", "jules", "ollama"])
    assert D._next_lane("jules") == "ollama"  # reached only after cloud-async too
    assert D._next_lane("ollama") is None  # nothing below the floor


def test_ollama_model_derived_and_argv(monkeypatch):
    monkeypatch.setenv("LIMEN_OLLAMA_MODEL", "qwen2.5-coder:7b")
    assert C.ollama_model() == "qwen2.5-coder:7b"  # explicit pin wins
    assert D._agent_argv("ollama") == ["run", "qwen2.5-coder:7b"]


def test_ollama_self_activates_on_model(monkeypatch):
    # No model + no binary on PATH → down, with the one-command path surfaced.
    monkeypatch.delenv("LIMEN_OLLAMA_MODEL", raising=False)
    monkeypatch.setenv("LIMEN_OLLAMA_BIN", "definitely-not-a-real-binary-xyz")
    assert C.ollama_model() is None
    # With a model pinned, the lane is reachable as soon as the binary resolves.
    monkeypatch.setenv("LIMEN_OLLAMA_MODEL", "llama3.2")
    assert C.ollama_model() == "llama3.2"
