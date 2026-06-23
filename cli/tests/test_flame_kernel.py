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
    return Task(id="T1", title="do a thing", repo="org/repo",
                target_agent="ollama", created=date(2026, 6, 23))


def _write_kernel(root, text="# FLAME\nYou are VLTIMA.\n"):
    (root / "FLAME.md").write_text(text)


def test_kernel_rides_every_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.delenv("LIMEN_FLAME_KERNEL", raising=False)
    _write_kernel(tmp_path)
    D._FLAME_CACHE.clear()
    p = D._build_prompt(_task())
    assert "You are VLTIMA." in p            # the self rides along
    assert "YOUR TASK THIS BEAT" in p        # divider separates identity from work
    assert "do a thing" in p                 # the concrete task is still there


def test_kernel_disabled_is_bare_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_FLAME_KERNEL", "0")
    _write_kernel(tmp_path)
    D._FLAME_CACHE.clear()
    p = D._build_prompt(_task())
    assert "VLTIMA" not in p
    assert p.startswith("Complete task T1")


def test_missing_kernel_fails_open(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))  # no FLAME.md on disk
    monkeypatch.delenv("LIMEN_FLAME_KERNEL", raising=False)
    D._FLAME_CACHE.clear()
    p = D._build_prompt(_task())
    assert p.startswith("Complete task T1")  # bare prompt, never a blocked lane


def test_ollama_is_cascade_floor():
    assert "ollama" in C.PAID_AGENT_ORDER
    assert "ollama" in C.LOCAL_CHECKOUT_AGENTS
    assert D._LANE_CASCADE[-1] == "ollama"          # the very last resort
    assert D._next_lane("jules") == "ollama"        # reached only after cloud-async too
    assert D._next_lane("ollama") is None           # nothing below the floor


def test_ollama_model_derived_and_argv(monkeypatch):
    monkeypatch.setenv("LIMEN_OLLAMA_MODEL", "qwen2.5-coder:7b")
    assert C.ollama_model() == "qwen2.5-coder:7b"   # explicit pin wins
    assert D._agent_argv("ollama") == ["run", "qwen2.5-coder:7b"]


def test_ollama_self_activates_on_model(monkeypatch):
    # No model + no binary on PATH → down, with the one-command path surfaced.
    monkeypatch.delenv("LIMEN_OLLAMA_MODEL", raising=False)
    monkeypatch.setenv("LIMEN_OLLAMA_BIN", "definitely-not-a-real-binary-xyz")
    assert C.ollama_model() is None
    # With a model pinned, the lane is reachable as soon as the binary resolves.
    monkeypatch.setenv("LIMEN_OLLAMA_MODEL", "llama3.2")
    assert C.ollama_model() == "llama3.2"
