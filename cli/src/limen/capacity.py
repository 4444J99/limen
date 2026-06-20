from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any


PAID_AGENT_ORDER: tuple[str, ...] = (
    "codex",
    "claude",
    "opencode",
    "agy",
    "gemini",
    "jules",
    "copilot",
    "warp",
    "oz",
    "github_actions",
)

AGENT_ALIASES: dict[str, str] = {
    "actions": "github_actions",
    "gha": "github_actions",
    "github-actions": "github_actions",
    "antigravity": "agy",
}

LOCAL_CHECKOUT_AGENTS = frozenset({"codex", "claude", "opencode", "agy", "gemini"})
ISSUE_ASSIGNMENT_AGENTS = frozenset({"copilot"})

_DEFAULT_BINARIES: dict[str, str] = {
    "codex": "codex",
    "claude": "claude",
    "opencode": "opencode",
    "agy": "agy",
    "gemini": "gemini",
    "jules": "jules",
    "copilot": "gh",
    "warp": "warp",
    "oz": "oz",
    "github_actions": "gh",
}

_KINDS: dict[str, str] = {
    "codex": "local-cli",
    "claude": "local-cli",
    "opencode": "local-cli",
    "agy": "local-cli",
    "gemini": "local-cli",
    "jules": "cloud-cli",
    "copilot": "github-issue",
    "warp": "paid-service",
    "oz": "paid-service",
    "github_actions": "github-actions",
}

_ISSUE_RE = re.compile(r"github\.com/([^/\s]+/[^/\s]+)/issues/(\d+)")


def canonical_agent(agent: str | None) -> str:
    value = (agent or "").strip()
    return AGENT_ALIASES.get(value, value)


def task_value(task: Any, key: str, default: Any = None) -> Any:
    if isinstance(task, dict):
        return task.get(key, default)
    return getattr(task, key, default)


def github_issue_ref(task: Any) -> tuple[str, str] | None:
    """Return (repo, issue_number) when a task already points at a GitHub issue."""
    fields: list[str] = []
    urls = task_value(task, "urls", []) or []
    fields.extend(str(url) for url in urls)
    for key in ("context", "description", "title"):
        value = task_value(task, key)
        if value:
            fields.append(str(value))
    for value in fields:
        match = _ISSUE_RE.search(value)
        if match:
            return match.group(1), match.group(2)
    return None


def task_has_github_issue(task: Any) -> bool:
    return github_issue_ref(task) is not None


def _env_name(agent: str, suffix: str) -> str:
    return f"LIMEN_{agent.upper()}_{suffix}"


def _configured_command(agent: str) -> list[str] | None:
    raw = os.environ.get(_env_name(agent, "DISPATCH_CMD"))
    if not raw:
        return None
    try:
        return shlex.split(raw)
    except ValueError:
        return None


def _binary_for(agent: str) -> str:
    return os.environ.get(_env_name(agent, "BIN"), _DEFAULT_BINARIES[agent])


def _binary_status(binary: str) -> tuple[bool, str]:
    path = shutil.which(binary)
    if path:
        return True, path
    return False, f"{binary} not found"


def _gemini_auth_configured() -> bool:
    if os.environ.get("GEMINI_API_KEY"):
        return True
    settings = Path.home() / ".gemini" / "settings.json"
    return settings.exists() and "auth" in settings.read_text(errors="ignore")


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _copilot_assignable(binary: str, repo: str, actor: str) -> bool:
    try:
        result = subprocess.run(
            [binary, "api", "--silent", f"repos/{repo}/assignees/{actor}"],
            capture_output=True,
            text=True,
            timeout=10,
            stdin=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def agent_status(agent: str) -> dict[str, Any]:
    agent = canonical_agent(agent)
    if agent not in PAID_AGENT_ORDER:
        return {
            "agent": agent,
            "kind": "unknown",
            "reachable": False,
            "detail": "not in paid lane catalog",
            "command": None,
        }

    configured = _configured_command(agent)
    if configured:
        ok, detail = _binary_status(configured[0])
        return {
            "agent": agent,
            "kind": _KINDS[agent],
            "reachable": ok,
            "detail": f"configured command: {detail}",
            "command": configured,
        }

    if agent in {"warp", "oz"}:
        dispatch_cmd = os.environ.get("LIMEN_DISPATCH_CMD", "agent-dispatch")
        ok, detail = _binary_status(dispatch_cmd)
        if ok:
            return {
                "agent": agent,
                "kind": _KINDS[agent],
                "reachable": True,
                "detail": f"generic dispatch adapter: {detail}",
                "command": [dispatch_cmd, agent],
            }

    binary = _binary_for(agent)
    ok, detail = _binary_status(binary)
    if agent == "gemini" and ok and not _gemini_auth_configured():
        ok = False
        detail = "gemini auth not configured"
    if agent == "github_actions" and ok:
        workflow = os.environ.get("LIMEN_GITHUB_ACTIONS_WORKFLOW", "limen-agent.yml")
        detail = f"{detail}; workflow={workflow}"
    if agent == "copilot" and ok:
        actor = os.environ.get("LIMEN_COPILOT_ACTOR", "copilot-swe-agent")
        if _truthy(os.environ.get("LIMEN_COPILOT_ENABLED")):
            detail = f"{detail}; assigns {actor} to issue"
        else:
            health_repo = os.environ.get("LIMEN_COPILOT_HEALTH_REPO", "")
            if health_repo and _copilot_assignable(binary, health_repo, actor):
                detail = f"{detail}; {actor} assignable on {health_repo}"
            else:
                ok = False
                detail = (
                    f"{detail}; {actor} not confirmed assignable "
                    "(set LIMEN_COPILOT_ENABLED=1 after enabling Copilot coding agent)"
                )
    return {
        "agent": agent,
        "kind": _KINDS[agent],
        "reachable": ok,
        "detail": detail,
        "command": [binary],
    }


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _budget_from_board(board: Any) -> Any:
    if board is None:
        return {}
    portal = _get(board, "portal", {})
    return _get(portal, "budget", {})


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def capacity_census(board: Any = None, budget_limit: int | None = None) -> list[dict[str, Any]]:
    budget = _budget_from_board(board)
    daily = _int(budget_limit if budget_limit is not None else _get(budget, "daily", 0))
    track = _get(budget, "track", {})
    total_spent = _int(_get(track, "spent", 0))
    per_agent_caps = _get(budget, "per_agent", {}) or {}
    per_agent_spent = _get(track, "per_agent", {}) or {}
    daily_remaining = max(0, daily - total_spent) if daily else None

    rows: list[dict[str, Any]] = []
    for agent in PAID_AGENT_ORDER:
        status = agent_status(agent)
        cap = _int(per_agent_caps.get(agent), daily)
        spent = _int(per_agent_spent.get(agent), 0)
        if daily_remaining is None:
            remaining = max(0, cap - spent) if cap else None
        else:
            remaining = max(0, min(daily_remaining, cap - spent))
        reachable = bool(status["reachable"]) and (remaining is None or remaining > 0)
        rows.append(
            {
                **status,
                "limit": cap,
                "spent": spent,
                "remaining": remaining,
                "reachable": reachable,
            }
        )
    return rows


def format_capacity_census(rows: list[dict[str, Any]]) -> str:
    lines = ["-- capacity census"]
    for row in rows:
        state = "up" if row["reachable"] else "down"
        remaining = "unlimited" if row["remaining"] is None else str(row["remaining"])
        limit = "unlimited" if row["limit"] is None else str(row["limit"])
        lines.append(
            f"  {state:4} {row['agent']:<14} {row['kind']:<14} "
            f"remaining={remaining}/{limit} - {row['detail']}"
        )
    return "\n".join(lines)
