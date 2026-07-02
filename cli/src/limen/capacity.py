from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from collections.abc import Iterable
from typing import TypedDict, TypeVar

from limen import census
from limen.models import Task

T = TypeVar("T")


class AgentStatus(TypedDict):
    agent: str
    kind: str
    reachable: bool
    detail: str
    command: list[str] | None


class CapacityRow(AgentStatus):
    limit: int
    spent: int
    remaining: int | None


# These six were once hand-maintained literals here; they are now DERIVED VIEWS of the single
# vendor register in `census.py` (one record per vendor owns every fact). Editing a vendor — or
# recording that one went dark (see census: gemini) — is a one-record edit there, not six here.
# test_census locks each of these against its historical value so the derivation can never drift.
# (ollama is the LOCAL, UNMETERED floor of the cascade — the pilot light: no budget, no window, so
# when every metered/cloud vendor is spent the beat still has a lane that can produce. Reachable
# only once a model is pulled — see agent_status / census ollama record.)
PAID_AGENT_ORDER: tuple[str, ...] = census.paid_agent_order()

AGENT_ALIASES: dict[str, str] = census.agent_aliases()

LOCAL_CHECKOUT_AGENTS = census.local_checkout_agents()
ISSUE_ASSIGNMENT_AGENTS = census.issue_assignment_agents()

_DEFAULT_BINARIES: dict[str, str] = census.default_binaries()

_KINDS: dict[str, str] = census.kinds()

_ISSUE_RE = re.compile(r"github\.com/([^/\s]+/[^/\s]+)/issues/(\d+)")


def canonical_agent(agent: str | None) -> str:
    value = (agent or "").strip()
    return AGENT_ALIASES.get(value, value)


def task_value(task: Task | dict[str, object], key: str, default: T | None = None) -> T | object | None:
    if isinstance(task, dict):
        return task.get(key, default)
    return getattr(task, key, default)


def github_issue_ref(task: Task | dict[str, object]) -> tuple[str, str] | None:
    """Return (repo, issue_number) when a task already points at a GitHub issue."""
    fields: list[str] = []
    urls_val = task_value(task, "urls", []) or []
    urls = urls_val if isinstance(urls_val, list) else []
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


def task_has_github_issue(task: Task | dict[str, object]) -> bool:
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
    try:
        settings = Path.home() / ".gemini" / "settings.json"
        return settings.exists() and "auth" in settings.read_text(errors="ignore")
    except (PermissionError, OSError):
        return False


def ollama_model() -> str | None:
    """The local model that lights the pilot. DERIVED, never pinned: an explicit
    LIMEN_OLLAMA_MODEL wins; otherwise pick the first model `ollama list` reports. Returns None
    when the binary is missing or no model is pulled — that is the only thing standing between
    a fresh install and a live floor lane (one `ollama pull`). Fail-soft to None on any error."""
    env = os.environ.get("LIMEN_OLLAMA_MODEL")
    if env:
        return env
    binary = os.environ.get("LIMEN_OLLAMA_BIN", _DEFAULT_BINARIES["ollama"])
    if not shutil.which(binary):
        return None
    try:
        r = subprocess.run([binary, "list"], capture_output=True, text=True, timeout=10)
        for line in r.stdout.splitlines()[1:]:  # skip the "NAME  ID  SIZE …" header
            name = line.split()[0] if line.split() else ""
            if name:
                return name
    except Exception:
        pass
    return None


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _copilot_assignable(binary: str, repo: str, actor: str) -> bool:
    try:
        import json

        owner, name = repo.split("/", 1)
        query = """
        query($owner: String!, $name: String!, $actor: String!) {
          repository(owner: $owner, name: $name) {
            suggestedActors(query: $actor, capabilities: [CAN_BE_ASSIGNED], first: 10) {
              nodes { login }
            }
          }
        }
        """
        result = subprocess.run(
            [
                binary,
                "api",
                "graphql",
                "--silent",
                "-f",
                f"query={query}",
                "-F",
                f"owner={owner}",
                "-F",
                f"name={name}",
                "-F",
                f"actor={actor}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            nodes = data.get("data", {}).get("repository", {}).get("suggestedActors", {}).get("nodes", [])
            for n in nodes:
                if n.get("login", "").lower() == actor.lower():
                    return True
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass
    return False


def agent_status(agent: str) -> AgentStatus:
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
        warp_key = os.environ.get("WARP_API_KEY")
        gh_path = shutil.which("gh")
        workflow = os.environ.get("LIMEN_WARP_OZ_WORKFLOW", "limen-warp-oz.yml")
        dispatch_repo = os.environ.get("LIMEN_WARP_OZ_REPO", "organvm/limen")
        if not warp_key:
            return {
                "agent": agent,
                "kind": _KINDS[agent],
                "reachable": False,
                "detail": "WARP_API_KEY not set (set env var + add as org/repo Actions secret)",
                "command": None,
            }
        if not gh_path:
            return {
                "agent": agent,
                "kind": _KINDS[agent],
                "reachable": False,
                "detail": "gh CLI not found (needed to trigger workflow_dispatch)",
                "command": None,
            }
        return {
            "agent": agent,
            "kind": _KINDS[agent],
            "reachable": True,
            "detail": f"WARP_API_KEY set, gh at {gh_path}, workflow={workflow}@{dispatch_repo}",
            "command": [gh_path, "workflow", "run", workflow, "--repo", dispatch_repo],
        }

    binary = _binary_for(agent)
    ok, detail = _binary_status(binary)
    if agent == "gemini" and ok and not _gemini_auth_configured():
        ok = False
        detail = "gemini auth not configured"
    if agent == "ollama" and ok:
        # Self-activating floor: reachable ONLY once a model is pulled. Install present but no
        # model → down with the exact one-command path, so it joins the cascade automatically
        # the instant `ollama pull <model>` lands (no flag flip, mirrors lane auto-rejoin).
        model = ollama_model()
        if model:
            detail = f"{detail}; model={model} (local, unmetered floor)"
        else:
            ok = False
            detail = f"{detail}; no model pulled — run `ollama pull qwen2.5-coder:7b` to light the floor lane"
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


def _get(value: object, key: str, default: object = None) -> object:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _budget_from_board(board: object) -> object:
    if board is None:
        return {}
    portal = _get(board, "portal", {})
    return _get(portal, "budget", {})


def _int(value: object, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def capacity_census(board: object = None, budget_limit: int | None = None) -> list[CapacityRow]:
    budget = _budget_from_board(board)
    daily = _int(budget_limit if budget_limit is not None else _get(budget, "daily", 0))
    track = _get(budget, "track", {})
    total_spent = _int(_get(track, "spent", 0))
    per_agent_caps = _get(budget, "per_agent", {}) or {}
    per_agent_spent = _get(track, "per_agent", {}) or {}
    if not isinstance(per_agent_caps, dict):
        per_agent_caps = {}
    if not isinstance(per_agent_spent, dict):
        per_agent_spent = {}
    daily_remaining = max(0, daily - total_spent) if daily else None

    rows: list[CapacityRow] = []
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


def select_lanes(
    selector: str | None = "auto",
    board: object = None,
    *,
    down_lanes: Iterable[str] | None = None,
) -> list[str]:
    """Resolve a lane selector through the canonical capacity registry.

    ``auto`` means lanes that are reachable and have remaining board capacity.
    ``all`` means every registered lane except live-down lanes. Explicit comma
    lists normalize aliases and ignore unknown/down lanes.
    """
    raw = (selector or "auto").strip() or "auto"
    down = {canonical_agent(agent.strip()) for agent in (down_lanes or []) if str(agent).strip()}
    key = raw.lower()
    if key == "all":
        return [agent for agent in PAID_AGENT_ORDER if agent not in down]
    if key == "auto":
        rows = capacity_census(board)
        return [str(row["agent"]) for row in rows if row.get("reachable") and str(row["agent"]) not in down]

    lanes: list[str] = []
    for item in raw.split(","):
        agent = canonical_agent(item.strip())
        if agent and agent in PAID_AGENT_ORDER and agent not in down and agent not in lanes:
            lanes.append(agent)
    return lanes


def format_capacity_census(rows: list[CapacityRow]) -> str:
    lines = ["-- capacity census"]
    for row in rows:
        state = "up" if row["reachable"] else "down"
        remaining = "unlimited" if row["remaining"] is None else str(row["remaining"])
        limit = "unlimited" if row["limit"] is None else str(row["limit"])
        lines.append(
            f"  {state:4} {row['agent']:<14} {row['kind']:<14} remaining={remaining}/{limit} - {row['detail']}"
        )
    return "\n".join(lines)
