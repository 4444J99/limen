"""Focused unit tests for limen.capacity — the agent-status and census helpers.

Functions covered:
  canonical_agent, task_value, github_issue_ref, task_has_github_issue,
  _truthy, ollama_model, agent_status, format_capacity_census,
  capacity_census (edge cases: no board, budget_limit param, spent accounting).
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from limen.capacity import (
    PAID_AGENT_ORDER,
    _truthy,
    agent_status,
    canonical_agent,
    capacity_census,
    format_capacity_census,
    github_issue_ref,
    ollama_model,
    select_lanes,
    task_has_github_issue,
    task_value,
)
from limen.models import Task

# ---------------------------------------------------------------------------
# canonical_agent
# ---------------------------------------------------------------------------


def test_canonical_agent_resolves_known_aliases() -> None:
    assert canonical_agent("actions") == "github_actions"
    assert canonical_agent("gha") == "github_actions"
    assert canonical_agent("github-actions") == "github_actions"
    assert canonical_agent("antigravity") == "agy"


def test_canonical_agent_passthrough_for_real_names() -> None:
    for name in ("claude", "jules", "codex", "gemini", "ollama"):
        assert canonical_agent(name) == name


def test_canonical_agent_strips_whitespace() -> None:
    assert canonical_agent("  claude  ") == "claude"


def test_canonical_agent_handles_none() -> None:
    assert canonical_agent(None) == ""


def test_canonical_agent_handles_empty_string() -> None:
    assert canonical_agent("") == ""


# ---------------------------------------------------------------------------
# task_value
# ---------------------------------------------------------------------------


def test_task_value_from_dict_present_key() -> None:
    assert task_value({"title": "hello"}, "title") == "hello"


def test_task_value_from_dict_missing_key_default() -> None:
    assert task_value({"title": "x"}, "nonexistent", "fallback") == "fallback"


def test_task_value_from_dict_missing_key_none() -> None:
    assert task_value({}, "title") is None


def test_task_value_from_task_object_present_attr() -> None:
    task = Task(id="t1", title="Test task", target_agent="claude", created=date.today())
    assert task_value(task, "title") == "Test task"
    assert task_value(task, "target_agent") == "claude"


def test_task_value_from_task_object_missing_attr() -> None:
    task = Task(id="t1", title="x", target_agent="claude", created=date.today())
    assert task_value(task, "nonexistent_field", "sentinel") == "sentinel"


# ---------------------------------------------------------------------------
# github_issue_ref / task_has_github_issue
# ---------------------------------------------------------------------------


def test_github_issue_ref_from_urls_list() -> None:
    task = {"urls": ["https://github.com/organvm/limen/issues/42"]}
    assert github_issue_ref(task) == ("organvm/limen", "42")


def test_github_issue_ref_from_context() -> None:
    task = {"urls": [], "context": "See https://github.com/myorg/myrepo/issues/99 for details"}
    assert github_issue_ref(task) == ("myorg/myrepo", "99")


def test_github_issue_ref_from_description() -> None:
    task = {"description": "Tracked at github.com/foo/bar/issues/7"}
    assert github_issue_ref(task) == ("foo/bar", "7")


def test_github_issue_ref_from_title() -> None:
    task = {"title": "Fix github.com/a/b/issues/3"}
    assert github_issue_ref(task) == ("a/b", "3")


def test_github_issue_ref_returns_none_when_absent() -> None:
    assert github_issue_ref({"urls": [], "context": "no url here"}) is None
    assert github_issue_ref({}) is None


def test_github_issue_ref_with_task_object() -> None:
    task = Task(
        id="t2",
        title="issue task",
        target_agent="copilot",
        created=date.today(),
        urls=["https://github.com/org/repo/issues/10"],
    )
    assert github_issue_ref(task) == ("org/repo", "10")


def test_github_issue_ref_urls_not_a_list_is_ignored() -> None:
    task = {"urls": "not-a-list", "context": "github.com/o/r/issues/5"}
    assert github_issue_ref(task) == ("o/r", "5")


def test_task_has_github_issue_true() -> None:
    assert task_has_github_issue({"urls": ["https://github.com/organvm/limen/issues/1"]})


def test_task_has_github_issue_false() -> None:
    assert not task_has_github_issue({"urls": []})
    assert not task_has_github_issue({})


# ---------------------------------------------------------------------------
# _truthy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE", "YES", "ON", " 1 ", " True "])
def test_truthy_accepted(value: str) -> None:
    assert _truthy(value)


@pytest.mark.parametrize("value", [None, "", "0", "false", "no", "off", "nope", "2", "False"])
def test_truthy_rejected(value: str | None) -> None:
    assert not _truthy(value)


# ---------------------------------------------------------------------------
# ollama_model
# ---------------------------------------------------------------------------


def test_ollama_model_env_var_shortcircuits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIMEN_OLLAMA_MODEL", "llama3")
    assert ollama_model() == "llama3"


def test_ollama_model_binary_missing_returns_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LIMEN_OLLAMA_MODEL", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert ollama_model() is None


def test_ollama_model_binary_present_but_no_models(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LIMEN_OLLAMA_MODEL", raising=False)
    fake = tmp_path / "ollama"
    fake.write_text("#!/bin/sh\necho 'NAME  ID  SIZE  MODIFIED'\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert ollama_model() is None


def test_ollama_model_binary_present_with_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LIMEN_OLLAMA_MODEL", raising=False)
    fake = tmp_path / "ollama"
    fake.write_text("#!/bin/sh\necho 'NAME  ID  SIZE  MODIFIED'\necho 'qwen2.5-coder:7b  abc123  4.7GB  1 day ago'\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert ollama_model() == "qwen2.5-coder:7b"


# ---------------------------------------------------------------------------
# agent_status
# ---------------------------------------------------------------------------


def test_agent_status_unknown_agent_returns_down() -> None:
    status = agent_status("nonexistent_xyz")
    assert status["agent"] == "nonexistent_xyz"
    assert status["reachable"] is False
    assert status["kind"] == "unknown"
    assert status["command"] is None


def test_agent_status_alias_is_resolved(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    status = agent_status("antigravity")
    assert status["agent"] == "agy"


def test_agent_status_claude_not_in_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LIMEN_CLAUDE_DISPATCH_CMD", raising=False)
    monkeypatch.delenv("LIMEN_CLAUDE_BIN", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    status = agent_status("claude")
    assert status["agent"] == "claude"
    assert status["kind"] == "local-cli"
    assert status["reachable"] is False


def test_agent_status_claude_found(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = tmp_path / "claude"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.delenv("LIMEN_CLAUDE_DISPATCH_CMD", raising=False)
    monkeypatch.delenv("LIMEN_CLAUDE_BIN", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    status = agent_status("claude")
    assert status["reachable"] is True
    assert status["kind"] == "local-cli"
    assert status["command"] == ["claude"]


def test_agent_status_configured_command_overrides_binary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = tmp_path / "my-dispatch"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("LIMEN_CLAUDE_DISPATCH_CMD", "my-dispatch --flag")
    status = agent_status("claude")
    assert status["reachable"] is True
    assert status["command"] == ["my-dispatch", "--flag"]
    assert "configured command" in status["detail"]


def test_agent_status_configured_command_binary_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("LIMEN_CLAUDE_DISPATCH_CMD", "no-such-binary --flag")
    status = agent_status("claude")
    assert status["reachable"] is False


def test_agent_status_warp_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WARP_API_KEY", raising=False)
    status = agent_status("warp")
    assert status["reachable"] is False
    assert "WARP_API_KEY" in status["detail"]


def test_agent_status_warp_key_but_no_gh(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WARP_API_KEY", "test-key")
    monkeypatch.setenv("PATH", str(tmp_path))
    status = agent_status("warp")
    assert status["reachable"] is False
    assert "gh" in status["detail"]


def test_agent_status_warp_fully_configured(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WARP_API_KEY", "test-key")
    fake_gh = tmp_path / "gh"
    fake_gh.write_text("#!/bin/sh\n")
    fake_gh.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    status = agent_status("warp")
    assert status["reachable"] is True
    assert status["kind"] == "paid-service"
    assert status["command"] is not None


def test_agent_status_oz_same_path_as_warp(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("WARP_API_KEY", raising=False)
    status = agent_status("oz")
    assert status["reachable"] is False


def test_agent_status_gemini_binary_present_no_auth(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = tmp_path / "gemini"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))  # no .gemini/settings.json present
    status = agent_status("gemini")
    assert status["reachable"] is False
    assert "auth" in status["detail"]


def test_agent_status_gemini_with_api_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = tmp_path / "gemini"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("GEMINI_API_KEY", "key-abc")
    status = agent_status("gemini")
    assert status["reachable"] is True


def test_agent_status_ollama_binary_not_found(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LIMEN_OLLAMA_MODEL", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    status = agent_status("ollama")
    assert status["reachable"] is False


def test_agent_status_ollama_binary_present_no_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = tmp_path / "ollama"
    fake.write_text("#!/bin/sh\necho 'NAME  ID  SIZE  MODIFIED'\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.delenv("LIMEN_OLLAMA_MODEL", raising=False)
    status = agent_status("ollama")
    assert status["reachable"] is False
    assert "no model pulled" in status["detail"]


def test_agent_status_ollama_reachable_with_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = tmp_path / "ollama"
    fake.write_text("#!/bin/sh\necho 'NAME  ID  SIZE  MODIFIED'\necho 'qwen  abc  4GB  now'\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("LIMEN_OLLAMA_MODEL", "qwen")
    status = agent_status("ollama")
    assert status["reachable"] is True
    assert "model=qwen" in status["detail"]


def test_agent_status_github_actions_includes_workflow(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_gh = tmp_path / "gh"
    fake_gh.write_text("#!/bin/sh\n")
    fake_gh.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("LIMEN_GITHUB_ACTIONS_WORKFLOW", "custom-workflow.yml")
    status = agent_status("github_actions")
    assert status["reachable"] is True
    assert "custom-workflow.yml" in status["detail"]


def test_agent_status_copilot_enabled_via_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_gh = tmp_path / "gh"
    fake_gh.write_text("#!/bin/sh\n")
    fake_gh.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("LIMEN_COPILOT_ENABLED", "1")
    status = agent_status("copilot")
    assert status["reachable"] is True
    assert status["kind"] == "github-issue"


# ---------------------------------------------------------------------------
# format_capacity_census
# ---------------------------------------------------------------------------


def test_format_capacity_census_header() -> None:
    assert "-- capacity census" in format_capacity_census([])


def test_format_capacity_census_up_state() -> None:
    rows = [
        {
            "agent": "claude",
            "kind": "local-cli",
            "reachable": True,
            "detail": "found",
            "command": ["claude"],
            "limit": 50,
            "spent": 10,
            "remaining": 40,
        }
    ]
    text = format_capacity_census(rows)
    assert "up" in text
    assert "claude" in text
    assert "40/50" in text


def test_format_capacity_census_down_state() -> None:
    rows = [
        {
            "agent": "jules",
            "kind": "cloud-cli",
            "reachable": False,
            "detail": "not found",
            "command": None,
            "limit": 100,
            "spent": 0,
            "remaining": 100,
        }
    ]
    assert "down" in format_capacity_census(rows)


def test_format_capacity_census_unlimited_remaining() -> None:
    rows = [
        {
            "agent": "ollama",
            "kind": "local-cli",
            "reachable": True,
            "detail": "model=qwen",
            "command": ["ollama"],
            "limit": 0,
            "spent": 0,
            "remaining": None,
        }
    ]
    assert "unlimited" in format_capacity_census(rows)


# ---------------------------------------------------------------------------
# capacity_census — edge cases
# ---------------------------------------------------------------------------


def test_capacity_census_no_board_returns_all_lanes() -> None:
    rows = capacity_census(None)
    assert [r["agent"] for r in rows] == list(PAID_AGENT_ORDER)


def test_capacity_census_keys_present_on_every_row() -> None:
    rows = capacity_census(None)
    for row in rows:
        for key in ("agent", "kind", "reachable", "detail", "limit", "spent", "remaining"):
            assert key in row, f"missing {key!r} in row for {row.get('agent')}"


def test_capacity_census_budget_limit_param_caps_remaining(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    rows = capacity_census(None, budget_limit=3)
    for row in rows:
        if row["remaining"] is not None:
            assert row["remaining"] <= 3, f"agent {row['agent']} remaining {row['remaining']} exceeds cap"


def test_capacity_census_spent_reduces_remaining() -> None:
    board = {
        "portal": {
            "budget": {
                "daily": 100,
                "per_agent": {"claude": 10},
                "track": {"spent": 50, "per_agent": {"claude": 3}},
            }
        }
    }
    rows = capacity_census(board)
    claude_row = next(r for r in rows if r["agent"] == "claude")
    assert claude_row["spent"] == 3
    # daily_remaining = 100 - 50 = 50; claude cap = 10, spent = 3; min(50, 10-3) = 7
    assert claude_row["remaining"] == 7


def test_capacity_census_daily_overspent_clamps_remaining() -> None:
    board = {
        "portal": {
            "budget": {
                "daily": 10,
                "per_agent": {},
                "track": {"spent": 999, "per_agent": {}},
            }
        }
    }
    rows = capacity_census(board)
    for row in rows:
        if row["remaining"] is not None:
            assert row["remaining"] == 0, f"expected 0 remaining for {row['agent']}, got {row['remaining']}"


def test_capacity_census_agent_cap_overspent_clamps_remaining() -> None:
    board = {
        "portal": {
            "budget": {
                "daily": 1000,
                "per_agent": {"codex": 2},
                "track": {"spent": 0, "per_agent": {"codex": 99}},
            }
        }
    }
    rows = capacity_census(board)
    codex_row = next(r for r in rows if r["agent"] == "codex")
    assert codex_row["remaining"] == 0


def test_capacity_census_uses_current_live_meter_over_stale_board_spend(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "usage.json").write_text(
        json.dumps(
            {
                "generated": "2026-07-10T07:24:23+00:00",
                "vendors": {
                    "jules": {
                        "signal": "dispatch-count",
                        "unit": "runs",
                        "possible": 100,
                        "consumed": 89,
                        "remaining": 11,
                        "health": "throttle",
                        "headroom_pct": 11,
                    },
                    "opencode": {
                        "signal": "db-meter",
                        "unit": "tokens",
                        "possible": 50_000_000,
                        "consumed": 30_000_000,
                        "remaining": 20_000_000,
                        "health": "ok",
                        "headroom_pct": 40,
                    },
                },
            }
        )
    )
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "limen.capacity.agent_status",
        lambda agent: {
            "agent": agent,
            "kind": "cloud-cli",
            "reachable": True,
            "detail": "test binary",
            "command": ["test"],
        },
    )
    board = {
        "portal": {
            "budget": {
                "daily": 600,
                "per_agent": {"jules": 100, "opencode": 100},
                "track": {
                    "date": "2026-07-10",
                    "spent": 244,
                    "per_agent": {"jules": 122, "opencode": 122},
                },
            }
        }
    }

    rows = capacity_census(board)
    jules_row = next(r for r in rows if r["agent"] == "jules")

    assert jules_row["limit"] == 100
    assert jules_row["spent"] == 89
    assert jules_row["remaining"] == 11
    assert jules_row["reachable"] is True
    assert "live usage meter" in jules_row["detail"]
    opencode_row = next(r for r in rows if r["agent"] == "opencode")
    assert opencode_row["limit"] == 50_000_000
    assert opencode_row["spent"] == 30_000_000
    assert opencode_row["remaining"] == 20_000_000
    assert opencode_row["reachable"] is True
    auto = select_lanes("auto", board)
    assert "jules" in auto
    assert "opencode" in auto


def test_capacity_census_dict_board_shape() -> None:
    board = {
        "portal": {
            "budget": {
                "daily": 50,
                "per_agent": {},
                "track": {"spent": 5, "per_agent": {}},
            }
        }
    }
    rows = capacity_census(board)
    assert len(rows) == len(PAID_AGENT_ORDER)
    for row in rows:
        # daily_remaining = 45; cap = 50 (fallback); spent = 0; remaining = min(45, 50) = 45
        assert row["remaining"] == 45
