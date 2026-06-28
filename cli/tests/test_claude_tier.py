"""Tests for the Claude-lane earned-tier ladder (dispatch._claude_model & helpers).

Mirrors the _codex_model suite in test_accelerator.py: env override wins, derive at call
-time from task class, fail-open. Haiku-first for verifiable classes; a higher tier is
pre-assigned ONLY where failure is undetectable (ledger-DISCOVERED waste_classes → sonnet;
the reserved principled set → opus). Escalate-on-failure reuses the EXISTING machinery —
a 'tried:claude' retry bumps the tier one rung, and a failed lane cascades onward.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import limen.dispatch as D
from limen.models import Task


def _task(type_="code", labels=None, claude_tier=None):
    return Task(
        id="T1",
        title="t",
        target_agent="claude",
        type=type_,
        labels=labels or [],
        claude_tier=claude_tier,
        created=date(2026, 6, 22),
    )


def _write_ledger(root: Path, claude_classes: dict):
    (root / "logs").mkdir(parents=True, exist_ok=True)
    (root / "logs" / "ledger.json").write_text(json.dumps({"lanes": {"claude": claude_classes}}))


def _write_tiers(root: Path, mapping: dict):
    (root / "logs").mkdir(parents=True, exist_ok=True)
    (root / "logs" / "model-tiers.json").write_text(json.dumps({"claude": mapping}))


def _clear(monkeypatch):
    for k in (
        "LIMEN_CLAUDE_MODEL",
        "LIMEN_CLAUDE_TIER_SELECT",
        "LIMEN_CLAUDE_RETRY_BUMP",
        "LIMEN_CLAUDE_OPUS_CLASSES",
        "LIMEN_CLAUDE_HAIKU_MODEL",
        "LIMEN_CLAUDE_SONNET_MODEL",
        "LIMEN_CLAUDE_OPUS_MODEL",
    ):
        monkeypatch.delenv(k, raising=False)


def test_haiku_default_for_verifiable_class(tmp_path, monkeypatch):
    """A coding task (failure cheaply detectable via CI/PR) starts at haiku."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_ledger(tmp_path, {"waste_classes": ["research"]})
    assert D._claude_model(_task(type_="code")) == "haiku"


def test_sonnet_for_ledger_waste_class(tmp_path, monkeypatch):
    """A class the ledger DISCOVERED this lane wastes on → pre-assigned sonnet (failure not
    caught cheaply here). Derived, not pinned."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_ledger(tmp_path, {"waste_classes": ["research", "value-discovery"]})
    assert D._claude_model(_task(type_="research")) == "sonnet"
    assert D._claude_model(_task(type_="code", labels=["value-discovery"])) == "sonnet"


def test_opus_for_reserved_class(tmp_path, monkeypatch):
    """The reserved principled set (undetectable AND high-stakes) → opus; highest tier wins."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_ledger(tmp_path, {"waste_classes": ["research"]})
    assert D._claude_model(_task(type_="code", labels=["canon"])) == "opus"
    # opus wins even when the task ALSO matches a sonnet (waste) class.
    assert D._claude_model(_task(type_="research", labels=["synthesis"])) == "opus"


def test_env_override_wins(tmp_path, monkeypatch):
    """An explicit LIMEN_CLAUDE_MODEL pin always wins over class derivation."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_CLAUDE_MODEL", "claude-opus-4-8")
    _write_ledger(tmp_path, {"waste_classes": []})
    assert D._claude_model(_task(type_="code")) == "claude-opus-4-8"


def test_fail_open_on_missing_or_corrupt_ledger(tmp_path, monkeypatch):
    """No ledger / corrupt ledger → haiku-first default, never an exception or a blocked lane."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))  # no ledger.json written
    assert D._claude_model(_task(type_="research")) == "haiku"
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "logs" / "ledger.json").write_text("{ this is not json")
    assert D._claude_model(_task(type_="research")) == "haiku"


def test_feature_flag_off_is_bare_invocation(tmp_path, monkeypatch):
    """LIMEN_CLAUDE_TIER_SELECT=0 → None = today's bare `claude -p` (instant rollback)."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_CLAUDE_TIER_SELECT", "0")
    _write_ledger(tmp_path, {"waste_classes": ["research"]})
    assert D._claude_model(_task(type_="research")) is None


def test_agent_argv_injects_claude_model(tmp_path, monkeypatch):
    """_agent_argv threads the task through and injects -m for the claude lane; backward
    -compatible with the no-task call (codex/opencode callers stay valid)."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_ledger(tmp_path, {"waste_classes": ["research"]})
    argv = D._agent_argv("claude", _task(type_="research"))
    # claude CLI uses --model, NOT -m (codex/opencode use -m; claude rejects it).
    assert "--model" in argv and "sonnet" in argv, argv
    assert "-m" not in argv, argv  # regression guard: never emit -m for the claude lane
    assert "-p" in D._agent_argv("claude")  # no task → no crash, static flags intact


def test_retry_bump_on_tried_claude(tmp_path, monkeypatch):
    """A task that already failed on the claude lane (the cascade's 'tried:claude' breadcrumb)
    bumps one rung — the in-tier expression of escalate-on-failed-check. Capped at opus, gateable."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_ledger(tmp_path, {"waste_classes": ["research"]})
    assert D._claude_model(_task(type_="code", labels=["tried:claude"])) == "sonnet"  # haiku→sonnet
    assert D._claude_model(_task(type_="research", labels=["tried:claude"])) == "opus"  # sonnet→opus
    assert D._claude_model(_task(type_="code", labels=["canon", "tried:claude"])) == "opus"  # caps
    monkeypatch.setenv("LIMEN_CLAUDE_RETRY_BUMP", "0")
    assert D._claude_model(_task(type_="code", labels=["tried:claude"])) == "haiku"  # gated off


def test_per_task_pin_and_tier_aliases_resolve(tmp_path, monkeypatch):
    """The optional per-task claude_tier escape hatch overrides class derivation (env still wins);
    tier→model resolution prefers the bare CLI alias, env-overridable per tier."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_ledger(tmp_path, {"waste_classes": []})
    assert D._claude_model(_task(type_="code", claude_tier="opus")) == "opus"
    monkeypatch.setenv("LIMEN_CLAUDE_MODEL", "pinned-x")
    assert D._claude_model(_task(type_="code", claude_tier="opus")) == "pinned-x"  # env wins above pin
    monkeypatch.delenv("LIMEN_CLAUDE_MODEL")
    monkeypatch.setenv("LIMEN_CLAUDE_SONNET_MODEL", "claude-sonnet-4-6")
    assert D._resolve_claude_model("sonnet") == "claude-sonnet-4-6"
    assert D._resolve_claude_model("haiku") == "haiku"  # bare alias when unset (derive-never-pin)


def test_model_tiers_override_layers_on_ledger(tmp_path, monkeypatch):
    """The optional logs/model-tiers.json override promotes classes on top of the ledger default."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_ledger(tmp_path, {"waste_classes": []})  # ledger empty → would be haiku
    _write_tiers(tmp_path, {"opus": ["migration"], "sonnet": ["docs"]})
    assert D._claude_model(_task(type_="migration")) == "opus"
    assert D._claude_model(_task(type_="docs")) == "sonnet"


def test_failed_claude_escalates_via_existing_cascade():
    """Escalate-on-failure also rides the EXISTING lane cascade unchanged: a failed claude
    attempt re-routes to the next lane. Documents the cross-lane escalate rung (no new code)."""
    assert D._next_lane("claude") == "gemini"
