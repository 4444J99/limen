"""Tests for the Claude-lane earned-tier ladder (dispatch._claude_model & helpers).

Mirrors the _codex_model suite in test_accelerator.py: env override wins, derive at call
-time from task class, fail-open. Haiku-first for verifiable classes; a higher tier is
pre-assigned ONLY where failure is undetectable (ledger-DISCOVERED waste_classes → sonnet;
the reserved principled set → opus). Escalate-on-failure reuses the EXISTING machinery —
a 'tried:claude' retry bumps the tier one rung, and a failed lane cascades onward.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import limen.dispatch as D
from limen.model_selection import _CLAUDE_TIER_ORDER
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


def _write_fable_acceptance(root: Path) -> Path:
    now = datetime.now(timezone.utc)
    monday = (now - timedelta(days=now.weekday())).date().isoformat()
    path = root / "fable-acceptance.json"
    path.write_text(
        json.dumps(
            {
                "schema": "limen.fable_acceptance.v1",
                "week": monday,
                "category": "adversarial-review",
                "percent": 5,
                "sources": ["docs/fable-allotment.md"],
                "verification": ["python3 scripts/fable-allotment.py audit"],
            }
        )
    )
    return path


def _clear(monkeypatch):
    for k in (
        "LIMEN_CLAUDE_MODEL",
        "LIMEN_CLAUDE_TIER_SELECT",
        "LIMEN_CLAUDE_RETRY_BUMP",
        "LIMEN_CLAUDE_OPUS_CLASSES",
        "LIMEN_CLAUDE_FABLE_CLASSES",
        "LIMEN_CLAUDE_HAIKU_MODEL",
        "LIMEN_CLAUDE_SONNET_MODEL",
        "LIMEN_CLAUDE_OPUS_MODEL",
        "LIMEN_CLAUDE_FABLE_MODEL",
        "LIMEN_CLAUDE_RETRY_BUMP_TO_FABLE",
        "LIMEN_FABLE_ACCEPTANCE",
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


def test_fable_is_reserved_above_opus_and_requires_acceptance(tmp_path, monkeypatch):
    """Fable is a top rung, but it is not reached unless the run carries written acceptance."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_ledger(tmp_path, {"waste_classes": []})
    assert _CLAUDE_TIER_ORDER[-1] == "fable"

    _write_tiers(tmp_path, {"fable": ["final-canonical-decision"]})
    task = _task(type_="final-canonical-decision")
    assert D._claude_model(task) == "opus"

    acceptance = _write_fable_acceptance(tmp_path)
    monkeypatch.setenv("LIMEN_FABLE_ACCEPTANCE", str(acceptance))
    assert D._claude_model(task) == "fable"

    monkeypatch.setenv("LIMEN_CLAUDE_FABLE_MODEL", "claude-fable-5")
    assert D._resolve_claude_model("fable") == "claude-fable-5"


def test_env_override_wins(tmp_path, monkeypatch):
    """An explicit LIMEN_CLAUDE_MODEL pin always wins over class derivation."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_CLAUDE_MODEL", "claude-opus-4-8")
    _write_ledger(tmp_path, {"waste_classes": []})
    assert D._claude_model(_task(type_="code")) == "claude-opus-4-8"


def test_env_fable_pin_is_guarded_by_acceptance(tmp_path, monkeypatch):
    """A model-name env pin cannot route Fable around the written acceptance receipt."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_ledger(tmp_path, {"waste_classes": []})
    monkeypatch.setenv("LIMEN_CLAUDE_MODEL", "claude-fable-5")
    assert D._claude_model(_task(type_="code")) == "opus"
    monkeypatch.setenv("LIMEN_FABLE_ACCEPTANCE", str(_write_fable_acceptance(tmp_path)))
    assert D._claude_model(_task(type_="code")) == "claude-fable-5"


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
    acceptance = _write_fable_acceptance(tmp_path)
    monkeypatch.setenv("LIMEN_FABLE_ACCEPTANCE", str(acceptance))
    assert D._claude_model(_task(type_="code", labels=["canon", "tried:claude"])) == "opus"
    monkeypatch.setenv("LIMEN_CLAUDE_RETRY_BUMP_TO_FABLE", "1")
    assert D._claude_model(_task(type_="code", labels=["canon", "tried:claude"])) == "fable"
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


def test_failed_claude_escalates_via_existing_cascade(monkeypatch):
    """Escalate-on-failure also rides the EXISTING lane cascade unchanged: a failed claude
    attempt re-routes to the next lane. Documents the cross-lane escalate rung (no new code)."""
    monkeypatch.delenv("LIMEN_DISPATCH_LANES", raising=False)
    # Pin the cascade to its STATIC order: this documents the escalation *ordering*
    # (claude → gemini), not live provider health. _lane_cascade() legitimately drops
    # lanes that are `down` (e.g. gemini when CONSUMER_SUSPENDED) or absent from the
    # auto-selected live set (no creds in CI) — which would make claude the last live
    # lane and _next_lane return None. That real-world filtering is a separate concern;
    # here we assert the ordering rung is intact regardless of who happens to be up.
    monkeypatch.setattr(D, "_lane_cascade", lambda: list(D._LANE_CASCADE))
    assert D._next_lane("claude") == "gemini"


# ── The .claude/agents/ tier floor is a PROJECTION of the same brain, bound by parity ──────────
# In-harness subagents (Task tool + Workflow agent()) default to inheriting the session model, so a
# fan-out of trivial workers silently rides the session's Opus. The .claude/agents/ type files carry
# a `model:` FLOOR (a per-call model still escalates). These tests bind those pins to the earned-tier
# ladder so the two projections cannot drift. ([[fleet-model-floor-bleed]] [[derive-never-pin-hardcodes]])

# Each agent TYPE → the brain job class it serves. Its pinned model MUST equal the tier the ladder
# derives for that class (verify/scan are default-cheap; synth's "synthesis" is reserved-Opus).
_AGENT_TYPE_JOB_CLASS = {"verify": "verify", "scan": "scan", "synth": "synthesis"}


def _agents_dir() -> Path:
    return Path(__file__).resolve().parents[2] / ".claude" / "agents"


def _frontmatter_model(md: Path) -> str | None:
    text = md.read_text()
    block = re.search(r"^---\s*$(.*?)^---\s*$", text, re.MULTILINE | re.DOTALL)
    scope = block.group(1) if block else text
    hit = re.search(r"^model:\s*(\S+)\s*$", scope, re.MULTILINE)
    return hit.group(1) if hit else None


def test_agent_type_pins_match_the_earned_tier_ladder(tmp_path, monkeypatch):
    """A pinned agent-type model MUST equal the tier the earned-tier ladder derives for the job
    class it serves — so dropping "synthesis" from the reserved set (or changing the default rung)
    breaks THIS test, not production. This is the anti-drift binding, mapping-aware not set-only."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_ledger(tmp_path, {"waste_classes": []})  # empty ledger → only reserved classes lift to opus
    agents = _agents_dir()
    for type_name, job_class in _AGENT_TYPE_JOB_CLASS.items():
        md = agents / f"{type_name}.md"
        assert md.exists(), f"missing agent type file: {md}"
        pinned = _frontmatter_model(md)
        expected = D._claude_model(_task(type_=job_class))
        assert pinned == expected, (
            f"{type_name}.md pins model={pinned!r} but the earned-tier ladder maps job class "
            f"{job_class!r} → {expected!r}; the agent-type floor drifted from the brain"
        )


def test_all_agent_type_models_are_valid_tier_aliases():
    """Every .claude/agents/ pin is a bare tier alias (or `inherit`) drawn from the one vocabulary —
    never a dated model id (derive-never-pin). The membership assert on a known rung kills a vacuous
    import that silently empties the tier set."""
    valid = set(_CLAUDE_TIER_ORDER) | {"inherit"}
    assert "haiku" in valid and "opus" in valid and "fable" in valid, "tier vocabulary failed to load"
    files = sorted(_agents_dir().glob("*.md"))
    assert files, "no .claude/agents/*.md type files found"
    for md in files:
        pinned = _frontmatter_model(md)
        assert pinned in valid, (
            f"{md.name} pins model={pinned!r} ∉ {sorted(valid)} — use a bare tier alias so "
            f"_resolve_claude_model resolves it to today's model (derive-never-pin)"
        )
