"""Executable contracts for agent-CLI config path resolution.

The defect these pin down (measured 2026-08-12): every surface that wanted an agent CLI's config
composed it from ``Path.home()``, so on a host exporting ``CLAUDE_CONFIG_DIR`` / ``GEMINI_CLI_HOME``
they read files the CLIs had abandoned. Because an abandoned config keeps its last contents and
still parses, the read *succeeded* and returned plausible data — the MCP-boot sensor reported four
claude servers and two boot failures while ``claude mcp list`` returned zero.

Both directions are asserted throughout. A relocation-only test would pass against a resolver that
ignored ``$HOME`` entirely, and hosts without these variables are the common case.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("agent_config_paths", ROOT / "scripts/agent_config_paths.py")
assert SPEC and SPEC.loader
ACP = importlib.util.module_from_spec(SPEC)
# Register BEFORE executing: @dataclass resolves its own module through sys.modules[__module__],
# which is None for a spec-loaded module that was never registered. Same ordering as the `_load`
# helper in scripts/session-opening-floor.py, for the same reason.
sys.modules["agent_config_paths"] = ACP
SPEC.loader.exec_module(ACP)

HOME = "/tmp/limen-test-home"
RUNTIME = "/tmp/limen-test-home/Workspace/limen/.agent-runtime"

RELOCATED = {
    "HOME": HOME,
    "CLAUDE_CONFIG_DIR": f"{RUNTIME}/claude",
    "GEMINI_CLI_HOME": f"{RUNTIME}/gemini/home",
    "CODEX_HOME": f"{RUNTIME}/codex",
}
BARE = {"HOME": HOME}


def test_relocation_variables_move_every_vendor_that_declares_one():
    """The regression itself: each relocatable vendor follows its own environment variable."""
    assert ACP.active_config_path("claude", RELOCATED) == Path(f"{RUNTIME}/claude/.claude.json")
    assert ACP.active_config_path("gemini", RELOCATED) == Path(f"{RUNTIME}/gemini/home/.gemini/settings.json")
    assert ACP.active_config_path("agy", RELOCATED) == Path(f"{RUNTIME}/gemini/home/.gemini/config/mcp_config.json")
    assert ACP.active_config_path("codex", RELOCATED) == Path(f"{RUNTIME}/codex/config.toml")
    assert ACP.active_config_path("claude-settings", RELOCATED) == Path(f"{RUNTIME}/claude/settings.json")


def test_unrelocated_host_keeps_the_home_defaults():
    """The fallback must not regress: most hosts export none of these."""
    assert ACP.active_config_path("claude", BARE) == Path(f"{HOME}/.claude.json")
    assert ACP.active_config_path("gemini", BARE) == Path(f"{HOME}/.gemini/settings.json")
    assert ACP.active_config_path("agy", BARE) == Path(f"{HOME}/.gemini/config/mcp_config.json")
    assert ACP.active_config_path("codex", BARE) == Path(f"{HOME}/.codex/config.toml")
    assert ACP.active_config_path("claude-settings", BARE) == Path(f"{HOME}/.claude/settings.json")


def test_codex_home_replaces_the_dot_directory_not_the_home():
    """CODEX_HOME *is* the ``~/.codex`` directory; the other two stand in for ``$HOME``.

    Getting this backwards yields ``$CODEX_HOME/.codex/config.toml``, which does not exist, so the
    sensor silently contributes zero codex servers instead of erroring.
    """
    assert ACP.active_config_path("codex", {"HOME": HOME, "CODEX_HOME": "/x/codex"}) == Path("/x/codex/config.toml")
    assert ACP.active_config_path("gemini", {"HOME": HOME, "GEMINI_CLI_HOME": "/x/g"}) == Path(
        "/x/g/.gemini/settings.json"
    )


def test_vendors_without_a_relocation_variable_are_always_home_relative():
    for vendor, relative in (
        ("copilot", ".copilot/mcp-config.json"),
        ("cline", ".cline/data/settings/cline_mcp_settings.json"),
        ("opencode", ".config/opencode/opencode.jsonc"),
    ):
        assert ACP.active_config_path(vendor, RELOCATED) == Path(HOME) / relative
        assert ACP.active_config_path(vendor, BARE) == Path(HOME) / relative


def test_active_path_never_probes_existence():
    """An unwritten config under an explicit root is still THE active path.

    Falling back to ``$HOME`` because the relocated file does not exist yet is precisely the bug:
    it would send a write to the file the CLI stopped reading.
    """
    resolved = ACP.active_config_path("claude", {"HOME": HOME, "CLAUDE_CONFIG_DIR": "/nonexistent/root"})
    assert resolved == Path("/nonexistent/root/.claude.json")
    assert not resolved.exists()


def test_empty_relocation_variable_is_treated_as_unset():
    """``CLAUDE_CONFIG_DIR=`` in the environment must not resolve to ``/.claude.json``."""
    assert ACP.active_config_path("claude", {"HOME": HOME, "CLAUDE_CONFIG_DIR": ""}) == Path(f"{HOME}/.claude.json")
    assert ACP.active_config_path("claude", {"HOME": HOME, "CLAUDE_CONFIG_DIR": "   "}) == Path(f"{HOME}/.claude.json")


def test_candidates_lead_with_the_active_path_and_cover_the_stale_roots():
    """The audit reducer: every root a setting might be read from, active first, deduplicated."""
    candidates = ACP.candidate_config_paths("claude", RELOCATED)
    assert candidates[0] == Path(f"{RUNTIME}/claude/.claude.json")
    assert Path(f"{HOME}/.claude.json") in candidates
    assert len(candidates) == len(set(candidates))


def test_candidates_collapse_to_one_entry_when_the_roots_coincide():
    """On an unrelocated host the runtime root is still a candidate, but duplicates are not."""
    candidates = ACP.candidate_config_paths("claude", BARE)
    assert candidates[0] == Path(f"{HOME}/.claude.json")
    assert len(candidates) == len(set(candidates))


def test_agent_runtime_root_accepts_either_spelling():
    """``~/.zshenv`` exports LIMEN_AGENT_RUNTIME_ROOT; the older code derived it from LIMEN_ROOT."""
    explicit = ACP.agent_runtime_root({"HOME": HOME, "LIMEN_AGENT_RUNTIME_ROOT": "/srv/runtime"})
    derived = ACP.agent_runtime_root({"HOME": HOME, "LIMEN_ROOT": "/srv/limen"})
    assert explicit == Path("/srv/runtime")
    assert derived == Path("/srv/limen/.agent-runtime")


def test_unknown_vendor_raises_rather_than_guessing():
    try:
        ACP.active_config_path("nosuchvendor", BARE)
    except KeyError as exc:
        assert "nosuchvendor" in str(exc)
    else:  # pragma: no cover - the assertion is the point
        raise AssertionError("an unknown vendor must not resolve to a plausible-looking path")


def test_mcp_vendor_keys_exclude_the_settings_document():
    """``claude-settings`` is a settings file, not an MCP config; scanning it for servers is wrong."""
    assert "claude-settings" in ACP.VENDORS
    assert "claude-settings" not in ACP.MCP_VENDOR_KEYS
    assert set(ACP.MCP_VENDOR_KEYS) <= set(ACP.VENDORS)
