"""The executable predicate for the NON-BYPASSABLE Claude model chokepoint.

Two layers, both proven here:

  1. ``limen.model_selection.model_for_argv`` — the per-spawn SORT (unit-level): a bare ``-p``
     spawn floors to haiku; an already-declared ``--model`` is left alone; a non-print
     invocation is never touched; the env gate / pin / floor-tune all flow through.
  2. ``scripts/shims/claude`` — the SHIM (end-to-end, via subprocess against a stub "real claude"):
     it actually splices ``--model`` and execs, it passes declared spawns through unchanged, and it
     FAILS OPEN to the original argv when the sorter can't load.

Together these are the proof that nothing the fleet spawns can silently inherit the account-default
Opus: a spawn either declares its tier (passed through) or gets floored (injected). ([[fleet-model-floor-bleed]])
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from limen.model_selection import model_for_argv

REPO = Path(__file__).resolve().parents[2]
SHIM = REPO / "scripts" / "shims" / "claude"

_TIER_ENV = (
    "LIMEN_CLAUDE_MODEL",
    "LIMEN_CLAUDE_TIER_SELECT",
    "LIMEN_CLAUDE_SHIM_FLOOR",
    "LIMEN_CLAUDE_MAX_INHERITED_TIER",
    "LIMEN_CLAUDE_FABLE_FALLBACK_TIER",
    "LIMEN_CLAUDE_HAIKU_MODEL",
    "LIMEN_CLAUDE_SONNET_MODEL",
    "LIMEN_CLAUDE_OPUS_MODEL",
    "LIMEN_CLAUDE_FABLE_MODEL",
    "LIMEN_FABLE_ACCEPTANCE",
    "LIMEN_ALLOW_EXPENSIVE_CLAUDE_MODEL_PIN",
    "LIMEN_ALLOW_CLAUDE_1M_CONTEXT",
)


def _clear(monkeypatch):
    for k in _TIER_ENV:
        monkeypatch.delenv(k, raising=False)


# ── Layer 1: the sorter ──────────────────────────────────────────────────────────────────


def test_bare_print_spawn_floors_to_haiku(monkeypatch):
    """A `-p` spawn with no --model gets the ladder's own default-for-unclassed: haiku."""
    _clear(monkeypatch)
    assert model_for_argv(["-p", "hello"]) == "haiku"
    assert model_for_argv(["--print", "hello"]) == "haiku"
    assert (
        model_for_argv(["--resume", "S1", "-p", "breathe"]) == "haiku"
    )  # resume still floors (claude ignores it, harmless)


def test_declared_model_is_left_alone(monkeypatch):
    """A spawn that already carries --model was sorted at its declaration site — never re-touch it."""
    _clear(monkeypatch)
    assert model_for_argv(["-p", "--model", "opus", "x"]) is None
    assert model_for_argv(["-p", "--model=opus", "x"]) is None
    assert model_for_argv(["--model", "sonnet", "-p", "x"]) is None


def test_non_print_is_never_touched(monkeypatch):
    """`claude mcp add …`, an interactive launch, --version, etc. carry no -p → never re-tiered."""
    _clear(monkeypatch)
    assert model_for_argv(["mcp", "add", "--scope", "user", "ianva", "https://x"]) is None
    assert model_for_argv(["--version"]) is None
    assert model_for_argv([]) is None


def test_pin_wins(monkeypatch):
    """An explicit cheap LIMEN_CLAUDE_MODEL pin wins (mirrors dispatch._claude_model)."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_CLAUDE_MODEL", "pinned-x")
    assert model_for_argv(["-p", "hi"]) == "pinned-x"


def test_tiering_gated_off_yields_no_injection(monkeypatch):
    """LIMEN_CLAUDE_TIER_SELECT=0 → bare invocation (the operator opted out)."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_CLAUDE_TIER_SELECT", "0")
    assert model_for_argv(["-p", "hi"]) is None


def test_floor_is_tunable_and_capped(monkeypatch):
    """LIMEN_CLAUDE_SHIM_FLOOR tunes the floor; Opus/Fable are never inherited floors."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_CLAUDE_SHIM_FLOOR", "sonnet")
    assert model_for_argv(["-p", "hi"]) == "sonnet"
    monkeypatch.setenv("LIMEN_CLAUDE_SHIM_FLOOR", "opus")
    assert model_for_argv(["-p", "hi"]) == "sonnet"
    monkeypatch.setenv("LIMEN_CLAUDE_SHIM_FLOOR", "fable")
    assert model_for_argv(["-p", "hi"]) == "sonnet"
    monkeypatch.setenv("LIMEN_FABLE_ACCEPTANCE", "1")
    assert model_for_argv(["-p", "hi"]) == "sonnet"
    monkeypatch.setenv("LIMEN_CLAUDE_SHIM_FLOOR", "nonsense")
    assert model_for_argv(["-p", "hi"]) == "haiku"


def test_tier_alias_resolves_via_env_pin(monkeypatch):
    """The floor tier resolves through LIMEN_CLAUDE_<TIER>_MODEL (derive-never-pin)."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_CLAUDE_HAIKU_MODEL", "claude-haiku-4-5")
    assert model_for_argv(["-p", "hi"]) == "claude-haiku-4-5"


def test_fable_model_pins_require_acceptance(monkeypatch):
    """Model-name pins cannot route Fable around the receipt-backed tier gate."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_CLAUDE_MODEL", "claude-fable-5")
    assert model_for_argv(["-p", "hi"]) == "sonnet"
    monkeypatch.setenv("LIMEN_FABLE_ACCEPTANCE", "1")
    assert model_for_argv(["-p", "hi"]) == "claude-fable-5"


def test_global_opus_and_1m_pins_require_explicit_override(monkeypatch):
    """A global model pin is inherited by unrelated fan-out, so expensive pins are gated."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_CLAUDE_MODEL", "claude-opus-4-8[1m]")
    assert model_for_argv(["-p", "hi"]) == "sonnet"

    monkeypatch.setenv("LIMEN_ALLOW_EXPENSIVE_CLAUDE_MODEL_PIN", "1")
    assert model_for_argv(["-p", "hi"]) == "sonnet"

    monkeypatch.setenv("LIMEN_ALLOW_CLAUDE_1M_CONTEXT", "1")
    assert model_for_argv(["-p", "hi"]) == "claude-opus-4-8[1m]"


# ── Layer 2: the shim (end-to-end, against a stub "real claude") ───────────────────────────


@pytest.fixture()
def stub_claude(tmp_path):
    """A fake `claude` that just prints its argv, one per line — so a test can see EXACTLY what the
    shim exec'd."""
    stub = tmp_path / "real-claude"
    stub.write_text('#!/bin/sh\nfor a in "$@"; do printf "%s\\n" "$a"; done\n')
    stub.chmod(0o755)
    return stub


def _run_shim(stub, args, **env_overrides):
    env = {k: v for k, v in os.environ.items() if k not in _TIER_ENV}
    env.update({"LIMEN_REAL_CLAUDE": str(stub), "LIMEN_ROOT": str(REPO)})
    env.update(env_overrides)
    proc = subprocess.run(
        [sys.executable, str(SHIM), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.splitlines()


def test_shim_is_executable():
    assert SHIM.exists(), f"shim missing at {SHIM}"
    assert os.access(SHIM, os.X_OK), "shim must be executable (the exec bit is tracked in git)"


def test_shim_injects_floor_for_bare_spawn(stub_claude):
    """End-to-end: a bare `-p` fleet spawn reaches the real claude WITH --model haiku spliced in."""
    out = _run_shim(stub_claude, ["-p", "hello"])
    assert out == ["--model", "haiku", "-p", "hello"]


def test_shim_passes_declared_spawn_through_untouched(stub_claude):
    """A spawn that already declared --model rides through with no second --model."""
    out = _run_shim(stub_claude, ["-p", "--model", "opus", "do canon work"])
    assert out == ["-p", "--model", "opus", "do canon work"]
    assert out.count("--model") == 1


def test_shim_never_touches_non_print(stub_claude):
    """`claude mcp add …` reaches the real claude byte-for-byte — the chokepoint only floors -p runs."""
    args = ["mcp", "add", "--scope", "user", "ianva", "https://x"]
    assert _run_shim(stub_claude, args) == args


def test_shim_honors_pin_and_floor_tune(stub_claude):
    assert _run_shim(stub_claude, ["-p", "hi"], LIMEN_CLAUDE_MODEL="pinned-x")[:2] == ["--model", "pinned-x"]
    assert _run_shim(stub_claude, ["-p", "hi"], LIMEN_CLAUDE_SHIM_FLOOR="sonnet")[:2] == ["--model", "sonnet"]
    assert _run_shim(stub_claude, ["-p", "hi"], LIMEN_CLAUDE_SHIM_FLOOR="opus")[:2] == ["--model", "sonnet"]
    assert _run_shim(stub_claude, ["-p", "hi"], LIMEN_CLAUDE_TIER_SELECT="0") == ["-p", "hi"]


def test_shim_fails_open_when_sorter_unavailable(stub_claude, tmp_path):
    """If model_selection.py can't be loaded, the shim still execs the real claude with the ORIGINAL
    argv — it can change which model a spawn uses, never block the spawn."""
    out = _run_shim(stub_claude, ["-p", "hello"], LIMEN_ROOT=str(tmp_path / "nonexistent"))
    assert out == ["-p", "hello"]
