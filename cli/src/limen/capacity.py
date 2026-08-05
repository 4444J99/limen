from __future__ import annotations

import os
import json
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from collections.abc import Iterable
from datetime import datetime, timezone
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


class CapacityFillRow(TypedDict):
    agent: str
    target: int
    expected_now: int
    productive: int
    attempts: int
    observed: int
    open_work: int
    active_work: int
    remaining: int
    reachable: bool
    status: str
    evidence: str
    action: str


class CapacityFillSnapshot(TypedDict):
    generated_at: str
    status: str
    rows: list[CapacityFillRow]
    blockers: list[dict[str, str]]


# These structures were once hand-maintained literals here; they are now DERIVED VIEWS of the single
# vendor register in `census.py` (one record per vendor owns every fact). Editing a vendor — or
# recording that one went dark (see census: gemini) — is a one-record edit there, not six here.
# test_census locks the compatibility projections against their historical values and derives the
# daily-fill subset from execution-profile eligibility so those views cannot silently drift.
# (ollama is the LOCAL, UNMETERED floor of the cascade — the pilot light: no budget, no window, so
# when every metered/cloud vendor is spent the beat still has a lane that can produce. Reachable
# only once a model is pulled — see agent_status / census ollama record.)
PAID_AGENT_ORDER: tuple[str, ...] = census.paid_agent_order()

DEFAULT_FILL_AGENTS: tuple[str, ...] = census.default_fill_agents()
DEFAULT_DAILY_TASK_TARGETS: dict[str, int] = {
    # Human contract: Claude should get a deliberately programmed/check-up batch daily.
    "claude": 15,
    # Vendor quota: jules.google.com grants 100 tasks/day that expire unused at reset.
    # Operator mandate (2026-07-23): consume the full daily quota autonomously — underuse
    # is a defect the jules-quota sensor surfaces, never a chore to remember.
    "jules": 100,
}
DEFAULT_GITHUB_ACTIONS_WORKFLOW = "limen-agent.yml"
BAD_USAGE_HEALTH = {"exhausted", "rate-limited", "low"}

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


_LOCAL_FLOOR_CLASSES_DEFAULT = ("scan", "verify", "link-check", "classify", "summarize")


def local_floor_classes() -> set[str]:
    """Job classes the local ollama floor may absorb — env-pinned (LIMEN_LOCAL_FLOOR_CLASSES,
    comma-separated) with a conservative mechanical-grade default; mirrors the
    LIMEN_CLAUDE_OPUS_CLASSES pattern in model_selection."""
    raw = os.environ.get("LIMEN_LOCAL_FLOOR_CLASSES", "")
    if raw.strip():
        return {c.strip() for c in raw.split(",") if c.strip()}
    return set(_LOCAL_FLOOR_CLASSES_DEFAULT)


def local_floor_enabled() -> bool:
    """The local-floor arm switch — DARK by default (operator rule 2026-07-09: nothing switches
    over until the math maths). Arm with LIMEN_LOCAL_FLOOR=1 only after the parity gate passes
    each class (`parity gate --model <floor> --class <c> --threshold 0.9`, organvm/manumissio)."""
    return os.environ.get("LIMEN_LOCAL_FLOOR", "0").strip() == "1"


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
                # NO --silent: it suppresses the response body we parse below (json.loads on
                # empty stdout → the actor is never found → the lane can never health-activate).
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


def _github_actions_workflow_status(binary: str, workflow: str, repo: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            [binary, "workflow", "view", workflow, "--repo", repo],
            capture_output=True,
            text=True,
            timeout=10,
            stdin=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        return False, f"workflow={workflow}@{repo} unavailable ({exc})"
    if result.returncode == 0:
        return True, f"workflow={workflow}@{repo}"
    detail = (result.stderr or result.stdout or "").strip().splitlines()
    suffix = f": {detail[0]}" if detail else ""
    return False, f"workflow={workflow}@{repo} unavailable{suffix}"


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
        workflow = os.environ.get("LIMEN_GITHUB_ACTIONS_WORKFLOW", DEFAULT_GITHUB_ACTIONS_WORKFLOW)
        health_repo = os.environ.get(
            "LIMEN_GITHUB_ACTIONS_HEALTH_REPO",
            os.environ.get("LIMEN_GITHUB_ACTIONS_REPO", "organvm/limen"),
        )
        workflow_ok, workflow_detail = _github_actions_workflow_status(binary, workflow, health_repo)
        ok = ok and workflow_ok
        detail = f"{detail}; {workflow_detail}"
    if agent == "copilot" and ok:
        actor = os.environ.get("LIMEN_COPILOT_ACTOR", "copilot-swe-agent")
        if _truthy(os.environ.get("LIMEN_COPILOT_ENABLED")):
            detail = f"{detail}; assigns {actor} to issue"
        else:
            # Copilot Max active 2026-07-17: the coding agent (copilot-swe-agent) is provably
            # assignable estate-wide (4444J99 owns organvm). Default the health repo like the
            # github_actions (l.332) and ollama (l.318) lanes so this lane is HEALTH-DERIVED:
            # reachable when the actor is assignable, self-down if the seat lapses — no manual
            # LIMEN_COPILOT_ENABLED arming (which the persistence classifier blocks anyway).
            health_repo = os.environ.get("LIMEN_COPILOT_HEALTH_REPO", "organvm/limen")
            if health_repo and _copilot_assignable(binary, health_repo, actor):
                detail = f"{detail}; {actor} assignable on {health_repo}"
            else:
                ok = False
                detail = (
                    f"{detail}; {actor} not confirmed assignable "
                    "(Copilot coding agent unavailable — check the Max seat and repo access)"
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


def _usage_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _usage_generated_date(usage: dict[str, object]) -> str:
    generated = usage.get("generated")
    if not generated:
        return ""
    return str(generated)[:10]


def _live_usage_capacity(
    agent: str,
    info: dict[str, object],
    usage: dict[str, object],
    track_date: str,
) -> tuple[int, int, int] | None:
    """Return (cap, spent, remaining) from a current live meter.

    ``capacity_census`` answers whether a lane has provider headroom. Task launch volume is still
    bounded separately by dispatch's local slot caps and per-lane limits, so token/percent meters are
    valid reachability gates even though task ``budget_cost`` is not measured in tokens.
    """
    if not track_date or _usage_generated_date(usage) != track_date:
        return None
    cap = _usage_int(info.get("possible"))
    remaining = _usage_int(info.get("remaining"))
    if cap is None or cap <= 0 or remaining is None:
        return None
    consumed = _usage_int(info.get("consumed"))
    spent = consumed if consumed is not None else max(0, cap - remaining)
    return cap, max(0, spent), max(0, remaining)


def capacity_census(board: object = None, budget_limit: int | None = None) -> list[CapacityRow]:
    budget = _budget_from_board(board)
    daily = _int(budget_limit if budget_limit is not None else _get(budget, "daily", 0))
    track = _get(budget, "track", {})
    track_date = str(_get(track, "date", "") or "")
    total_spent = _int(_get(track, "spent", 0))
    per_agent_caps = _get(budget, "per_agent", {}) or {}
    per_agent_spent = _get(track, "per_agent", {}) or {}
    if not isinstance(per_agent_caps, dict):
        per_agent_caps = {}
    if not isinstance(per_agent_spent, dict):
        per_agent_spent = {}
    daily_remaining = max(0, daily - total_spent) if daily else None
    usage = _load_usage()

    rows: list[CapacityRow] = []
    for agent in PAID_AGENT_ORDER:
        status = agent_status(agent)
        cap = _int(per_agent_caps.get(agent), daily)
        spent = _int(per_agent_spent.get(agent), 0)
        usage_info = _usage_vendor(agent, usage)
        live_usage_capacity = _live_usage_capacity(agent, usage_info, usage, track_date)
        weak_proxy = _weak_proxy_exhaustion(agent, usage_info)
        detail = str(status["detail"])
        remaining: int | None  # unified across branches: live meter (int), daily runway, or None
        if live_usage_capacity is not None:
            cap, spent, remaining = live_usage_capacity
            meter = f"live usage meter: remaining={remaining}/{cap}, consumed={spent}"
            detail = f"{detail}; {meter}" if detail else meter
        elif weak_proxy:
            remaining = daily_remaining
            if detail:
                detail = f"{detail}; weak dispatch-count proxy, using daily budget runway"
            else:
                detail = "weak dispatch-count proxy, using daily budget runway"
        elif daily_remaining is None:
            remaining = max(0, cap - spent) if cap else None
        else:
            remaining = max(0, min(daily_remaining, cap - spent))
        reachable = bool(status["reachable"]) and (remaining is None or remaining > 0)
        rows.append(
            {
                **status,
                "detail": detail,
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


def _root() -> Path:
    return Path(os.environ.get("LIMEN_ROOT", str(Path.home() / "Workspace" / "limen")))


def _load_usage(root: Path | None = None) -> dict[str, object]:
    try:
        data = json.loads(((root or _root()) / "logs" / "usage.json").read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _usage_vendor(agent: str, usage: dict[str, object]) -> dict[str, object]:
    vendors = usage.get("vendors") if isinstance(usage, dict) else {}
    info = vendors.get(agent) if isinstance(vendors, dict) else {}
    return info if isinstance(info, dict) else {}


def _weak_proxy_exhaustion(agent: str, info: dict[str, object]) -> bool:
    """Agy's dispatch-count proxy is not a hard provider quota meter."""
    if agent != "agy":
        return False
    if info.get("health") == "rate-limited" or info.get("recent_rate_limit"):
        return False
    signal = str(info.get("signal") or "")
    source = str(info.get("limit_source") or "")
    return signal in {"dispatch-count", "count", "runs"} and "operator board cap" in source


def _parse_dt(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _window_hours_from_usage(agent: str, usage: dict[str, object]) -> float:
    vendors = usage.get("vendors") if isinstance(usage, dict) else {}
    info = vendors.get(agent) if isinstance(vendors, dict) else {}
    if isinstance(info, dict):
        hours = info.get("window_hours")
        if isinstance(hours, (int, float)) and hours > 0:
            return float(hours)
        window = str(info.get("window") or "")
    else:
        window = ""
    match = re.search(r"(\d+(?:\.\d+)?)\s*h", window)
    if match:
        return float(match.group(1))
    if "today" in window or "day" in window or "24" in window:
        return 24.0
    return 24.0


def _progress_from_usage(agent: str, usage: dict[str, object], reset_at: datetime | None, now: datetime) -> float:
    vendors = usage.get("vendors") if isinstance(usage, dict) else {}
    info = vendors.get(agent) if isinstance(vendors, dict) else {}
    if isinstance(info, dict):
        time_left = info.get("time_left_frac")
        if isinstance(time_left, (int, float)):
            return max(0.0, min(1.0, 1.0 - float(time_left)))
    if reset_at is None:
        return 1.0
    hours = _window_hours_from_usage(agent, usage)
    elapsed = max(0.0, (now - reset_at).total_seconds() / 3600.0)
    return max(0.0, min(1.0, elapsed / hours))


def derived_floor_from_budget(agent: str, per_agent: dict[str, object]) -> int:
    """Derive a daily task floor for *agent* from its per-agent budget cap.

    Precedence (mirrors derived_daily_floor but accepts the budget map directly so
    callers that already hold it — e.g. route.py — avoid re-reading the board):
      (a) env ``LIMEN_<AGENT>_DAILY_TASKS`` (same convention as _daily_task_target)
      (b) ``DEFAULT_DAILY_TASK_TARGETS[agent]``
      (c) ``ceil(per_agent[agent] × frac)`` where frac = env LIMEN_LANE_FLOOR_FRAC
          (default 0.25, clamped to (0, 1]; result floored at 1 when a budget exists)
      (d) 0 (agent has no budget entry)
    """
    import math

    env_name = f"LIMEN_{agent.upper()}_DAILY_TASKS"
    env_val = os.environ.get(env_name)
    if env_val:
        return _int(env_val, 0)
    if agent in DEFAULT_DAILY_TASK_TARGETS:
        return DEFAULT_DAILY_TASK_TARGETS[agent]
    if not isinstance(per_agent, dict) or agent not in per_agent:
        return 0
    cap = _int(per_agent.get(agent), 0)
    if cap <= 0:
        return 0
    raw_frac = os.environ.get("LIMEN_LANE_FLOOR_FRAC", "0.25")
    try:
        frac = float(raw_frac)
    except (TypeError, ValueError):
        frac = 0.25
    frac = max(1e-9, min(1.0, frac))  # clamp to (0, 1]
    return max(1, math.ceil(cap * frac))


def derived_daily_floor(agent: str, board: object) -> int:
    """Derive a daily task floor for *agent* from its budget config on *board*.

    Precedence:
      (a) env ``LIMEN_<AGENT>_DAILY_TASKS``
      (b) ``DEFAULT_DAILY_TASK_TARGETS[agent]``
      (c) ``ceil(per_agent[agent] × frac)`` where frac = LIMEN_LANE_FLOOR_FRAC (default 0.25)
      (d) 0 (no budget entry for agent)
    """
    budget = _budget_from_board(board)
    per_agent = _get(budget, "per_agent", {}) or {}
    if not isinstance(per_agent, dict):
        per_agent = {}
    return derived_floor_from_budget(agent, per_agent)


def _daily_task_target(agent: str, board: object) -> int:
    """Return the daily task target for *agent*.

    Delegates to ``derived_daily_floor`` so that agents without an explicit
    DEFAULT_DAILY_TASK_TARGETS entry (e.g. codex, jules) get a meaningful floor
    derived from their per-agent budget cap rather than the raw cap itself.
    This fixes the capacity-fill reporter: codex with a 100-task budget and
    LIMEN_LANE_FLOOR_FRAC=0.25 targets 25/day instead of 100, so the
    "underfilled" signal is honest when the lane has only processed 5.
    """
    return derived_daily_floor(agent, board)


def _task_agent(task: Task | dict[str, object]) -> str:
    return canonical_agent(str(task_value(task, "target_agent", "") or ""))


def _task_status(task: Task | dict[str, object]) -> str:
    return str(task_value(task, "status", "") or "")


def _task_cost_int(task: Task | dict[str, object]) -> int:
    return _int(task_value(task, "budget_cost", 1), 1)


def _usage_consumed_runs(agent: str, usage: dict[str, object]) -> int:
    vendors = usage.get("vendors") if isinstance(usage, dict) else {}
    info = vendors.get(agent) if isinstance(vendors, dict) else {}
    if not isinstance(info, dict):
        return 0
    signal = str(info.get("signal") or "")
    if signal in {"count", "dispatch-count", "runs"}:
        return _int(info.get("consumed"), 0)
    return 0


def _usage_health(agent: str, usage: dict[str, object]) -> str:
    vendors = usage.get("vendors") if isinstance(usage, dict) else {}
    info = vendors.get(agent) if isinstance(vendors, dict) else {}
    return str(info.get("health") or "") if isinstance(info, dict) else ""


def _lane_work_counts(board: object, agent: str) -> tuple[int, int]:
    tasks = _get(board, "tasks", []) or []
    if not isinstance(tasks, list):
        return 0, 0
    open_work = 0
    active_work = 0
    for task in tasks:
        if not isinstance(task, (dict, Task)):
            continue
        status = _task_status(task)
        task_agent = _task_agent(task)
        cost = _task_cost_int(task)
        if status == "open" and task_agent in {agent, "any"}:
            open_work += cost
        elif status in {"dispatched", "in_progress"} and task_agent == agent:
            active_work += cost
    return open_work, active_work


def _dispatch_event_attempts(board: object, agent: str, day: str) -> int:
    tasks = _get(board, "tasks", []) or []
    if not isinstance(tasks, list):
        return 0
    touched: set[str] = set()
    for task in tasks:
        if not isinstance(task, (dict, Task)):
            continue
        task_id = str(task_value(task, "id", "") or "")
        log = task_value(task, "dispatch_log", []) or []
        if not isinstance(log, list):
            continue
        for event in log:
            event_agent = canonical_agent(str(_get(event, "agent", "") or ""))
            if event_agent != agent:
                continue
            timestamp = _get(event, "timestamp", "")
            if day and not str(timestamp).startswith(day):
                continue
            status = str(_get(event, "status", "") or "")
            if status == "open":
                continue
            if task_id:
                touched.add(task_id)
    return len(touched)


def capacity_fill_snapshot(
    board: object,
    *,
    now: datetime | None = None,
    usage: dict[str, object] | None = None,
    down_lanes: set[str] | None = None,
    agents: tuple[str, ...] | None = None,
) -> CapacityFillSnapshot:
    """Compare paid-lane fill against each lane's current reset window.

    The key distinction is productive board spend vs. attempted dispatches. Failed/rerouted
    attempts prove the lane was touched, but they do not satisfy the daily fill contract.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    usage = usage if usage is not None else _load_usage()
    down_lanes = down_lanes or set()
    budget = _budget_from_board(board)
    track = _get(budget, "track", {}) or {}
    day = str(_get(track, "date", "") or now.date().isoformat())
    per_agent_spent = _get(track, "per_agent", {}) or {}
    per_agent_reset = _get(track, "per_agent_reset", {}) or {}
    if not isinstance(per_agent_spent, dict):
        per_agent_spent = {}
    if not isinstance(per_agent_reset, dict):
        per_agent_reset = {}

    census = {row["agent"]: row for row in capacity_census(board)}
    rows: list[CapacityFillRow] = []
    blockers: list[dict[str, str]] = []
    for agent in agents or DEFAULT_FILL_AGENTS:
        target = _daily_task_target(agent, board)
        if target <= 0:
            continue
        reset_at = _parse_dt(per_agent_reset.get(agent))
        progress = _progress_from_usage(agent, usage, reset_at, now)
        expected_now = min(target, int(round(target * progress)))
        if progress > 0 and expected_now == 0:
            expected_now = 1
        productive = _int(per_agent_spent.get(agent), 0)
        attempts = max(_dispatch_event_attempts(board, agent, day), _usage_consumed_runs(agent, usage))
        observed = max(productive, attempts)
        open_work, active_work = _lane_work_counts(board, agent)
        remaining = max(0, target - productive)
        row_census = census.get(agent)
        reachable = bool(row_census and row_census["reachable"]) and agent not in down_lanes
        usage_health = _usage_health(agent, usage)

        if agent in down_lanes:
            status = "blocked"
            evidence = "lane is down by the live dispatch gate"
            action = "clear the lane-down/auth/rate-limit gate, then route and dispatch this lane"
        elif usage_health in BAD_USAGE_HEALTH and observed > 0:
            status = "depleted"
            evidence = f"usage meter health={usage_health}; observed={observed}, productive={productive}"
            action = "wait for this lane's meter to refresh or fail over before feeding it again"
        elif expected_now > 0 and productive < expected_now:
            if attempts >= expected_now:
                status = "unproductive"
                evidence = (
                    f"attempted {attempts}/{expected_now}, but productive board spend is {productive}/{expected_now}"
                )
                action = "heal failed/rerouted dispatches so attempts become done/dispatched work"
            elif reachable and open_work > 0:
                status = "underfilled"
                evidence = f"productive {productive}/{expected_now}; attempts {attempts}/{expected_now}"
                action = "route open work to this lane and dispatch before the window resets"
            elif open_work <= 0:
                status = "no_work"
                evidence = f"productive {productive}/{expected_now}, but no open/any work is available"
                action = "generate or route appropriate open work for this lane"
            else:
                status = "blocked"
                evidence = f"productive {productive}/{expected_now}, but the lane is not reachable"
                action = "fix lane reachability/auth/budget before routing more work"
        else:
            status = "healthy"
            evidence = f"productive {productive}/{expected_now}; attempts {attempts}/{expected_now}"
            action = "keep pacing normally"

        row: CapacityFillRow = {
            "agent": agent,
            "target": target,
            "expected_now": expected_now,
            "productive": productive,
            "attempts": attempts,
            "observed": observed,
            "open_work": open_work,
            "active_work": active_work,
            "remaining": remaining,
            "reachable": reachable,
            "status": status,
            "evidence": evidence,
            "action": action,
        }
        rows.append(row)
        if status in {"underfilled", "unproductive", "blocked", "no_work"}:
            blockers.append({"id": f"lane-fill-{agent}", "evidence": f"{agent}: {evidence}"})

    overall = "healthy" if not blockers else "blocked"
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "status": overall,
        "rows": rows,
        "blockers": blockers,
    }


def format_capacity_fill(snapshot: CapacityFillSnapshot) -> str:
    lines = [
        "# Capacity Fill",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        "",
        f"Status: `{snapshot['status']}`",
        "",
        "| Lane | Status | Productive | Attempts | Expected now | Target | Open work | Active | Action |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in snapshot["rows"]:
        lines.append(
            "| "
            f"`{row['agent']}` | `{row['status']}` | {row['productive']} | {row['attempts']} | "
            f"{row['expected_now']} | {row['target']} | {row['open_work']} | {row['active_work']} | "
            f"{row['action']} |"
        )
    lines.extend(["", "## Evidence", ""])
    for row in snapshot["rows"]:
        lines.append(f"- `{row['agent']}`: {row['evidence']}")
    return "\n".join(lines) + "\n"
