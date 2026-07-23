"""Lane-neutral, side-effect-free tool action policy for host admission."""

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
_COMMAND_SUBSTITUTION = re.compile(r"`|\$\(|[\r\n]")
_SHELL_OPERATORS = frozenset({"&&", "||", ";", "|", "&"})
_OUTPUT_REDIRECTS = frozenset({">", ">>"})
_INPUT_REDIRECTS = frozenset({"<"})
_UNSUPPORTED_REDIRECTS = frozenset({"<<", "<<<"})
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
_GIT_ADMIN_ENV = frozenset(
    {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_DIR",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_WORK_TREE",
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
        "worktree-abandonment.py",
    }
)


class AdmissionInputError(ValueError):
    """A mutation payload cannot be resolved to one canonical action scope."""


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


def _tool_input(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("tool_input") or {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return {"input": value}
    return {}


def _tool_command(payload: dict[str, Any]) -> str:
    tool_input = _tool_input(payload)
    return str(tool_input.get("command") or tool_input.get("cmd") or "")


def _tool_name(payload: dict[str, Any]) -> str:
    return str(payload.get("tool_name") or payload.get("tool") or "").strip()


def _shell_tokens(command: str) -> list[str]:
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>")
        lexer.whitespace_split = True
        lexer.commenters = ""
        return list(lexer)
    except ValueError as exc:
        raise AdmissionInputError("ambiguous-shell") from exc


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


def _background_operator(tokens: list[str]) -> bool:
    for index, token in enumerate(tokens):
        if token != "&":
            continue
        if index > 0 and tokens[index - 1] in _OUTPUT_REDIRECTS and index + 1 < len(tokens):
            if tokens[index + 1].isdigit():
                continue
        return True
    return False


def _supported_cd_prefix(tokens: list[str]) -> tuple[list[str], str | None]:
    if tokens.count("&&") != 1:
        return tokens, None
    split = tokens.index("&&")
    prefix = _strip_env_assignments(tokens[:split])
    suffix = tokens[split + 1 :]
    if len(prefix) == 2 and prefix[0] == "cd":
        return suffix, prefix[1]
    if len(prefix) == 3 and prefix[:2] == ["cd", "--"]:
        return suffix, prefix[2]
    return tokens, None


def _strip_redirections(tokens: list[str]) -> tuple[list[str], list[str], bool]:
    command: list[str] = []
    outputs: list[str] = []
    saw_output = False
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in _UNSUPPORTED_REDIRECTS:
            raise AdmissionInputError("unsupported-shell-redirection")
        if token in _OUTPUT_REDIRECTS | _INPUT_REDIRECTS:
            if command and command[-1].isdigit():
                command.pop()
            if index + 1 >= len(tokens):
                raise AdmissionInputError("missing-shell-redirection-target")
            target = tokens[index + 1]
            if target == "&":
                if index + 2 >= len(tokens) or not tokens[index + 2].isdigit():
                    raise AdmissionInputError("unsupported-shell-redirection")
                if token in _OUTPUT_REDIRECTS:
                    saw_output = True
                index += 3
                continue
            if target in _SHELL_OPERATORS or target in _OUTPUT_REDIRECTS | _INPUT_REDIRECTS:
                raise AdmissionInputError("unsupported-shell-redirection")
            if token in _OUTPUT_REDIRECTS:
                outputs.append(target)
                saw_output = True
            index += 2
            continue
        command.append(token)
        index += 1
    return command, outputs, saw_output


def _compound_is_read_only(tokens: list[str]) -> bool:
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token in _SHELL_OPERATORS:
            if token == "&" or not segments[-1]:
                return False
            segments.append([])
            continue
        segments[-1].append(token)
    if not segments[-1]:
        return False
    try:
        for segment in segments:
            command, _outputs, saw_output = _strip_redirections(segment)
            if saw_output or not _simple_read_only(command):
                return False
    except AdmissionInputError:
        return False
    return True


def classify_bash(command: str) -> Action:
    """Classify Bash through a narrow parser and fail closed on opaque mutation."""

    if not command.strip():
        return Action("deny", "empty-command")
    if _COMMAND_SUBSTITUTION.search(command):
        return Action("deny", "command-substitution-or-multiline")
    try:
        tokens = _shell_tokens(command)
    except AdmissionInputError as exc:
        return Action("deny", str(exc))
    if _background_operator(tokens):
        return Action("deny", "background-command")

    command_tokens, cd_target = _supported_cd_prefix(tokens)
    remaining_operators = [token for token in command_tokens if token in _SHELL_OPERATORS]
    if remaining_operators:
        if cd_target is None and _compound_is_read_only(tokens):
            return Action("observe")
        return Action("deny", "unparseable-mutation-capable-compound")

    try:
        command_tokens, _outputs, saw_output = _strip_redirections(command_tokens)
    except AdmissionInputError as exc:
        return Action("deny", str(exc))
    if not command_tokens:
        return Action("deny", "empty-command")
    if saw_output:
        return Action("workspace_write", "shell-output-redirection")
    if _sanctioned_control(command_tokens):
        return Action("sanctioned_control")
    if _guarded_heavy(command_tokens):
        return Action("guarded_heavy")
    if _HEAVY_COMMAND.search(command):
        return Action("unguarded_heavy", "unguarded-heavy", "bash scripts/verify-scoped.sh")
    if _simple_read_only(command_tokens):
        return Action("observe")
    return Action("workspace_write", "unknown-or-mutation-capable-command")


def classify_action(payload: dict[str, Any]) -> Action:
    """Classify one tool action without inspecting or mutating lease state."""

    name = _tool_name(payload).lower()
    if name == "bash":
        return classify_bash(_tool_command(payload))
    if name in {
        "apply_patch",
        "applypatch",
        "edit",
        "multiedit",
        "notebookedit",
        "write",
    }:
        return Action("workspace_write", f"{name}-is-write")
    return Action("workspace_write", "unknown-tool")


def mutation_build_allowed(payload: dict[str, Any]) -> tuple[bool, str]:
    """Enforce explicit plan-only profiles while preserving direct human builds."""

    if str(payload.get("permission_mode") or "").strip().lower() == "plan":
        return False, "plan-only-mutation"
    tool_input = _tool_input(payload)
    profiles = [value for value in (payload.get("execution_profile"), tool_input.get("execution_profile")) if value]
    if not profiles:
        return True, ""
    if len(profiles) > 1 and profiles[0] != profiles[1]:
        return False, "conflicting-execution-profile"
    profile = profiles[0]
    if not isinstance(profile, dict):
        return False, "invalid-execution-profile"
    planning_only = profile.get("planning_only")
    build_allowed = profile.get("build_allowed")
    if not isinstance(planning_only, bool) or not isinstance(build_allowed, bool):
        return False, "invalid-execution-profile"
    if planning_only or not build_allowed:
        return False, "plan-only-mutation"
    return True, ""


def _canonical_path(raw: object, *, base: Path | None, label: str) -> Path:
    value = str(raw or "").strip()
    if not value:
        raise AdmissionInputError(f"{label}-unavailable")
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        if base is None:
            raise AdmissionInputError(f"{label}-relative-without-session-cwd")
        candidate = base / candidate
    return candidate.resolve(strict=False)


def _existing_directory(path: Path, *, label: str) -> Path:
    if not path.exists() or not path.is_dir():
        raise AdmissionInputError(f"{label}-not-directory")
    return path.resolve(strict=True)


def _git_cwd(tokens: list[str], cwd: Path) -> Path:
    assignment_index = 0
    while assignment_index < len(tokens) and re.fullmatch(
        r"[A-Za-z_][A-Za-z0-9_]*=.*",
        tokens[assignment_index],
    ):
        name, _separator, _value = tokens[assignment_index].partition("=")
        if name in _GIT_ADMIN_ENV:
            raise AdmissionInputError("unsupported-git-admin-target")
        assignment_index += 1
    tokens = tokens[assignment_index:]
    if not tokens or Path(tokens[0]).name != "git":
        return cwd
    current = cwd
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token == "-C":
            if index + 1 >= len(tokens):
                raise AdmissionInputError("git-c-missing-target")
            current = _existing_directory(
                _canonical_path(tokens[index + 1], base=current, label="git-c-target"),
                label="git-c-target",
            )
            index += 2
            continue
        if token in {"--git-dir", "--work-tree"} or token.startswith(("--git-dir=", "--work-tree=")):
            raise AdmissionInputError("unsupported-git-admin-target")
        if token == "-c":
            if index + 1 >= len(tokens):
                raise AdmissionInputError("git-config-missing-value")
            index += 2
            continue
        if token in {"--no-pager", "--literal-pathspecs"}:
            index += 1
            continue
        break
    return current


def resolve_effective_cwd(payload: dict[str, Any]) -> Path:
    """Resolve structured tool cwd first, then shell-local ``cd``/``git -C``."""

    tool_input = _tool_input(payload)
    session_raw = str(payload.get("cwd") or "").strip()
    session = _canonical_path(session_raw, base=None, label="session-cwd") if session_raw else None
    structured_raw = [value for value in (tool_input.get("workdir"), tool_input.get("cwd")) if str(value or "").strip()]
    if structured_raw:
        structured = [_canonical_path(value, base=session, label="tool-cwd") for value in structured_raw]
        if any(value != structured[0] for value in structured[1:]):
            raise AdmissionInputError("conflicting-tool-cwd")
        cwd = structured[0]
    elif session is not None:
        cwd = session
    else:
        raise AdmissionInputError("effective-cwd-unavailable")
    cwd = _existing_directory(cwd, label="effective-cwd")

    if _tool_name(payload).lower() != "bash":
        return cwd
    tokens = _shell_tokens(_tool_command(payload))
    command_tokens, cd_target = _supported_cd_prefix(tokens)
    if cd_target is not None:
        cwd = _existing_directory(
            _canonical_path(cd_target, base=cwd, label="cd-target"),
            label="cd-target",
        )
    command_tokens, _outputs, _saw_output = _strip_redirections(command_tokens)
    return _git_cwd(command_tokens, cwd)


def _looks_like_path(token: str) -> bool:
    return token.startswith(("/", "./", "../", "~/")) or "/" in token


def target_paths(payload: dict[str, Any], cwd: Path) -> list[Path]:
    """Extract canonical structured and supported Bash write targets."""

    tool_input = _tool_input(payload)
    values: list[str] = []
    for field in ("file_path", "notebook_path", "path"):
        raw_path = tool_input.get(field)
        if raw_path:
            values.append(str(raw_path))
    patch = str(tool_input.get("patch") or tool_input.get("input") or "")
    values.extend(
        value.strip()
        for match in re.finditer(
            r"^\*\*\* (?:Add|Delete|Update) File: (.+)$|^\*\*\* Move to: (.+)$",
            patch,
            re.MULTILINE,
        )
        for value in match.groups()
        if value
    )

    if _tool_name(payload).lower() == "bash":
        tokens = _shell_tokens(_tool_command(payload))
        command_tokens, _cd_target = _supported_cd_prefix(tokens)
        command_tokens, outputs, _saw_output = _strip_redirections(command_tokens)
        values.extend(outputs)
        stripped = _strip_env_assignments(command_tokens)
        if stripped and Path(stripped[0]).name != "git":
            values.extend(token for token in stripped[1:] if not token.startswith("-") and _looks_like_path(token))

    paths: list[Path] = []
    for value in values:
        candidate = Path(value).expanduser()
        resolved = (candidate if candidate.is_absolute() else cwd / candidate).resolve(strict=False)
        if resolved not in paths:
            paths.append(resolved)
    return paths


def path_within(path: Path, root: Path) -> bool:
    """Return whether one normalized path belongs to a worktree root."""

    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


__all__ = [
    "Action",
    "AdmissionInputError",
    "action_denial_supported",
    "classify_action",
    "classify_bash",
    "mutation_build_allowed",
    "path_within",
    "resolve_effective_cwd",
    "target_paths",
]
