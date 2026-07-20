"""Pure Codex tool-action classification for host admission."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

_HEAVY_COMMAND = re.compile(
    r"""(?ix)
    \b(
      verify-whole(?:\.sh)? |
      verify-scoped(?:\.sh)? |
      governance-memory-cadence(?:\.py)? |
      estate-closeout-audit(?:\.py)? |
      npm\s+(?:ci|test|run\s+build) |
      (?:python(?:3(?:\.\d+)?)?\s+-m\s+)?pytest(?:\s+-q)?\s*(?:$|(?:cli/)?tests/?(?:\s|$))
    )
    """
)
_SHELL_MUTATION = re.compile(r"(?:^|[^\\])(?:>|<|`|\$\()|[\r\n]")
_SHELL_OPERATORS = frozenset({"&&", "||", ";", "|", "&"})
_READ_ONLY_COMMANDS = frozenset(
    {
        "[",
        "cat",
        "cut",
        "df",
        "du",
        "false",
        "head",
        "jq",
        "ls",
        "pgrep",
        "ps",
        "pwd",
        "readlink",
        "realpath",
        "rg",
        "sort",
        "stat",
        "tail",
        "test",
        "tr",
        "true",
        "type",
        "uname",
        "uniq",
        "wc",
        "which",
    }
)
_GIT_READ_ONLY = frozenset(
    {
        "branch",
        "cat-file",
        "config",
        "describe",
        "diff",
        "grep",
        "log",
        "ls-files",
        "merge-base",
        "remote",
        "rev-list",
        "rev-parse",
        "show",
        "show-ref",
        "status",
        "worktree",
    }
)
_SANCTIONED_LIMEN = frozenset(
    {"channels", "conduct", "dispatch", "fanout", "harvest", "host-admission", "progress", "status", "workstream"}
)
_SANCTIONED_SCRIPTS = frozenset(
    {
        "dispatch-async.py",
        "host-work-admission.py",
        "start-worktree-session.sh",
    }
)


class Action:
    """One mutually exclusive host-admission action class."""

    def __init__(self, category: str, reason: str = "", equivalent: str = "") -> None:
        self.category = category
        self.reason = reason
        self.equivalent = equivalent


def action_denial_supported() -> bool:
    """Probe the installed client; retain the legacy root lock if hooks are not stable."""

    override = os.environ.get("LIMEN_CODEX_PRETOOL_DENIAL_SUPPORTED")
    if override is not None and override.strip().lower() != "auto":
        return override.strip().lower() in {"1", "true", "yes", "on"}
    try:
        result = subprocess.run(
            ["codex", "features", "list"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and any(
        re.fullmatch(r"hooks\s+stable\s+true", line.strip()) for line in result.stdout.splitlines()
    )


def _tool_command(payload: dict[str, Any]) -> str:
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return ""
    return str(tool_input.get("command") or tool_input.get("cmd") or "")


def _tool_name(payload: dict[str, Any]) -> str:
    return str(payload.get("tool_name") or payload.get("tool") or "").strip()


def _strip_env_assignments(tokens: list[str]) -> list[str]:
    index = 0
    while index < len(tokens) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[index]):
        index += 1
    return tokens[index:]


def _git_read_only(tokens: list[str]) -> bool:
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token in {"-C", "--git-dir", "--work-tree", "-c"}:
            index += 2
            continue
        if token in {"--no-pager", "--literal-pathspecs"}:
            index += 1
            continue
        break
    if index >= len(tokens):
        return False
    subcommand = tokens[index]
    rest = tokens[index + 1 :]
    if subcommand not in _GIT_READ_ONLY:
        return False
    if subcommand == "branch" and any(
        token in {"-d", "-D", "-m", "-M", "-c", "-C", "--delete", "--move", "--copy", "--edit-description"}
        for token in rest
    ):
        return False
    if subcommand == "config" and not any(
        token in {"--get", "--get-all", "--get-regexp", "--list", "-l", "--show-origin", "--show-scope"}
        for token in rest
    ):
        return False
    if subcommand == "remote" and rest and rest[0] not in {"-v", "get-url", "show"}:
        return False
    if subcommand == "worktree" and (not rest or rest[0] != "list"):
        return False
    return True


def _gh_read_only(tokens: list[str]) -> bool:
    if len(tokens) < 2:
        return False
    if tokens[1] == "api":
        forbidden = ("--input", "--raw-field", "--field", "--method", "-F", "-X", "-f")
        return not any(token == flag or token.startswith(f"{flag}=") for token in tokens[2:] for flag in forbidden)
    if len(tokens) < 3:
        return tokens[1] == "status"
    allowed = {
        ("auth", "status"),
        ("issue", "list"),
        ("issue", "status"),
        ("issue", "view"),
        ("pr", "checks"),
        ("pr", "diff"),
        ("pr", "list"),
        ("pr", "status"),
        ("pr", "view"),
        ("repo", "view"),
        ("run", "list"),
        ("run", "view"),
        ("run", "watch"),
        ("search", "code"),
        ("search", "commits"),
        ("search", "issues"),
        ("search", "prs"),
        ("search", "repos"),
    }
    return (tokens[1], tokens[2]) in allowed


def _simple_read_only(tokens: list[str]) -> bool:
    tokens = _strip_env_assignments(tokens)
    if not tokens:
        return True
    command = Path(tokens[0]).name
    if command == "git":
        return _git_read_only(tokens)
    if command == "gh":
        return _gh_read_only(tokens)
    if command == "sed":
        return not any(token == "-i" or token.startswith("-i") for token in tokens[1:])
    if command == "find":
        mutators = {"-delete", "-exec", "-execdir", "-fprint", "-fprint0", "-ok", "-okdir"}
        return not any(token in mutators for token in tokens[1:])
    if command == "jq":
        return "--in-place" not in tokens and "-i" not in tokens
    if command == "command":
        return len(tokens) >= 2 and tokens[1] in {"-v", "-V"}
    return command in _READ_ONLY_COMMANDS


def _sanctioned_control(tokens: list[str]) -> bool:
    tokens = _strip_env_assignments(tokens)
    if not tokens:
        return False
    command = Path(tokens[0]).name
    if command == "limen":
        return len(tokens) >= 2 and tokens[1] in _SANCTIONED_LIMEN
    if command in {"bash", "python", "python3"} and len(tokens) >= 2:
        return Path(tokens[1]).name in _SANCTIONED_SCRIPTS
    return False


def _guarded_heavy(tokens: list[str]) -> bool:
    tokens = _strip_env_assignments(tokens)
    if not tokens:
        return False
    command = Path(tokens[0]).name
    return (
        command in {"bash", "sh"}
        and len(tokens) >= 2
        and Path(tokens[1]).name in {"verify-scoped.sh", "verify-whole.sh"}
    )


def classify_bash(command: str) -> Action:
    """Classify Bash from a narrow, explicit read-only allowlist."""

    if not command.strip():
        return Action("workspace_write", "empty-command")
    if _SHELL_MUTATION.search(command):
        return Action("workspace_write", "shell-redirection-or-expansion")
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return Action("workspace_write", "ambiguous-shell")
    if any(token in _SHELL_OPERATORS for token in tokens):
        return Action("workspace_write", "compound-shell")
    if _sanctioned_control(tokens):
        return Action("sanctioned_control")
    if _guarded_heavy(tokens):
        return Action("guarded_heavy")
    if _HEAVY_COMMAND.search(command):
        return Action("unguarded_heavy", "unguarded-heavy", "bash scripts/verify-scoped.sh")
    if _simple_read_only(tokens):
        return Action("observe")
    return Action("workspace_write", "unknown-or-mutation-capable-command")


def classify_action(payload: dict[str, Any]) -> Action:
    """Classify the tool action without inspecting or mutating lease state."""

    name = _tool_name(payload).lower()
    if name == "bash":
        return classify_bash(_tool_command(payload))
    if name in {"apply_patch", "applypatch", "edit", "write"}:
        return Action("workspace_write", f"{name}-is-write")
    return Action("workspace_write", "unknown-tool")


def target_paths(payload: dict[str, Any], cwd: Path) -> list[Path]:
    """Extract structured write targets for worktree containment checks."""

    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return []
    raw_path = tool_input.get("file_path") or tool_input.get("path")
    values = [str(raw_path)] if raw_path else []
    patch = str(tool_input.get("patch") or tool_input.get("input") or "")
    values.extend(
        match.group(1).strip()
        for match in re.finditer(r"^\*\*\* (?:Add|Delete|Update) File: (.+)$", patch, re.MULTILINE)
    )
    paths: list[Path] = []
    for value in values:
        candidate = Path(value).expanduser()
        paths.append((candidate if candidate.is_absolute() else cwd / candidate).resolve(strict=False))
    return paths


def path_within(path: Path, root: Path) -> bool:
    """Return whether one normalized path belongs to a worktree root."""

    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
