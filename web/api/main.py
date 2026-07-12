import os
import base64
import json
import re
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from math import ceil
from pathlib import Path
import shutil
from typing import Any

import yaml
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

VALID_STATUSES = {"open", "dispatched", "in_progress", "done", "failed", "failed_blocked", "needs_human", "archived"}
VALID_PRIORITIES = {"critical", "high", "medium", "low", "backlog"}
VALID_AGENTS = {
    "jules",
    "claude",
    "gemini",
    "opencode",
    "codex",
    "copilot",
    "agy",
    "warp",
    "oz",
    "github_actions",
    "any",
}
VALID_DISPATCH_AGENTS = VALID_AGENTS - {"any"}
MAX_TASK_LIST_LENGTH = 20
TASK_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._/-]*$"
TASK_ID_RE = re.compile(TASK_ID_PATTERN)
LABEL_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._/-]*$"
LABEL_RE = re.compile(LABEL_PATTERN)
REPO_PATTERN = r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?$"
REPO_RE = re.compile(REPO_PATTERN)


def reject_control_chars(value: str, field_name: str) -> str:
    if any((ord(ch) < 32 and ch not in "\t\n\r") or ord(ch) == 127 for ch in value):
        raise ValueError(f"{field_name} must not contain control characters")
    return value


def validate_repo_value(value: str) -> str:
    if not value:
        return value
    if not REPO_RE.match(value):
        raise ValueError("repo must be a repository name or owner/repo slug")
    return value


def validate_label_list(value: list[str] | None) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("labels must be a list")
    if len(value) > MAX_TASK_LIST_LENGTH:
        raise ValueError(f"labels must have at most {MAX_TASK_LIST_LENGTH} items")
    for label in value:
        if not isinstance(label, str):
            raise ValueError("each label must be a string")
        if len(label) > 64 or not LABEL_RE.match(label):
            raise ValueError("labels must be 1-64 characters and contain only letters, numbers, '.', '_', '-', or '/'")
    return value


def reject_bool_integer(value: Any, field_name: str) -> Any:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer, not a boolean")
    return value


def validate_url_list(value: list[str] | None) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("urls must be a list")
    if len(value) > MAX_TASK_LIST_LENGTH:
        raise ValueError(f"urls must have at most {MAX_TASK_LIST_LENGTH} items")
    for url in value:
        if not isinstance(url, str):
            raise ValueError("each url must be a string")
        if not is_valid_url(url):
            raise ValueError(f"invalid URL format: {url}")
    return value


def get_cors_origins() -> list[str]:
    cors_env = os.environ.get("LIMEN_CORS_ORIGINS", "")
    if not cors_env or cors_env == "*":
        return ["http://localhost:*", "http://localhost:3000", "http://localhost:8000"]
    return [origin.strip() for origin in cors_env.split(",") if origin.strip()]


app = FastAPI(
    title="Limen API",
    description="Universal agent task intake backend",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)

LIMEN_ROOT = Path(os.environ.get("LIMEN_ROOT", str(Path.home() / "limen")))
LIMEN_TOKEN = os.environ.get("LIMEN_API_TOKEN", "")
GITHUB_API = os.environ.get("LIMEN_GITHUB_API", "https://api.github.com")
GITHUB_REPO = os.environ.get("LIMEN_GITHUB_REPO", "")
GITHUB_BRANCH = os.environ.get("LIMEN_GITHUB_BRANCH", "main")
GITHUB_PATH = os.environ.get("LIMEN_GITHUB_PATH", "tasks.yaml")
GITHUB_TOKEN = os.environ.get("LIMEN_GITHUB_TOKEN", "")


def is_valid_url(url: str) -> bool:
    url_pattern = re.compile(
        r"^https?://"
        r"(?:(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?|"
        r"localhost|"
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
        r"\[(?:[0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}\])"
        r"(?::\d+)?"
        r"(?:/[a-zA-Z0-9._~:/?#[\]@!$&\'()*+,;=-]*)?$",
        re.UNICODE,
    )
    return bool(url_pattern.match(url)) and len(url) <= 2048


class TaskCreate(BaseModel):
    id: str = Field(min_length=1, max_length=128, pattern=TASK_ID_PATTERN)
    title: str = Field(min_length=1, max_length=512)
    repo: str = Field(default="", max_length=256)
    type: str = Field(default="code", max_length=64, pattern=LABEL_PATTERN)
    target_agent: str = Field(default="jules", pattern=r"^[a-z][a-z_]*$")
    priority: str = "medium"
    budget_cost: int = Field(default=1, ge=1, le=100)
    status: str = "open"
    labels: list[str] = Field(default_factory=list, max_length=MAX_TASK_LIST_LENGTH)
    urls: list[str] = Field(default_factory=list, max_length=MAX_TASK_LIST_LENGTH)
    context: str = Field(default="", max_length=10000)

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        if v not in VALID_PRIORITIES:
            raise ValueError(f"priority must be one of {', '.join(sorted(VALID_PRIORITIES))}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"status must be one of {', '.join(sorted(VALID_STATUSES))}")
        return v

    @field_validator("budget_cost", mode="before")
    @classmethod
    def validate_budget_cost(cls, v: Any) -> Any:
        return reject_bool_integer(v, "budget_cost")

    @field_validator("target_agent")
    @classmethod
    def validate_target_agent(cls, v: str) -> str:
        if v not in VALID_AGENTS:
            raise ValueError(f"target_agent must be one of {', '.join(sorted(VALID_AGENTS))}")
        return v

    @field_validator("title", "context")
    @classmethod
    def validate_text(cls, v: str) -> str:
        return reject_control_chars(v, "text")

    @field_validator("repo")
    @classmethod
    def validate_repo(cls, v: str) -> str:
        return validate_repo_value(v)

    @field_validator("labels", mode="before")
    @classmethod
    def validate_labels(cls, v: list[str]) -> list[str]:
        return validate_label_list(v) or []

    @field_validator("urls", mode="before")
    @classmethod
    def validate_urls(cls, v: list[str]) -> list[str]:
        return validate_url_list(v)


class TaskUpdate(BaseModel):
    status: str | None = None
    output: str | None = Field(default=None, max_length=10000)
    agent: str | None = Field(default=None, max_length=128)
    session_id: str | None = Field(default=None, max_length=128)
    context: str | None = Field(default=None, max_length=10000)
    urls: list[str] | None = Field(default=None, max_length=MAX_TASK_LIST_LENGTH)
    labels: list[str] | None = Field(default=None, max_length=MAX_TASK_LIST_LENGTH)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_STATUSES:
            raise ValueError(f"status must be one of {', '.join(sorted(VALID_STATUSES))}")
        return v

    @field_validator("output", "agent", "session_id", "context")
    @classmethod
    def validate_text(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return reject_control_chars(v, "text")

    @field_validator("labels", mode="before")
    @classmethod
    def validate_labels(cls, v: list[str] | None) -> list[str] | None:
        return validate_label_list(v)

    @field_validator("urls", mode="before")
    @classmethod
    def validate_urls(cls, v: list[str] | None) -> list[str] | None:
        return validate_url_list(v)


class AssignmentRequest(BaseModel):
    target_agent: str | None = None
    priority: str | None = None
    budget_cost: int | None = Field(default=None, ge=1, le=100)
    status: str | None = "open"
    note: str = Field(default="", max_length=2000)
    session_id: str = Field(default="assignment", max_length=128)

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_PRIORITIES:
            raise ValueError(f"priority must be one of {', '.join(sorted(VALID_PRIORITIES))}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_STATUSES:
            raise ValueError(f"status must be one of {', '.join(sorted(VALID_STATUSES))}")
        return v

    @field_validator("budget_cost", mode="before")
    @classmethod
    def validate_budget_cost(cls, v: Any) -> Any:
        if v is None:
            return None
        return reject_bool_integer(v, "budget_cost")

    @field_validator("target_agent")
    @classmethod
    def validate_target_agent(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_AGENTS:
            raise ValueError(f"target_agent must be one of {', '.join(sorted(VALID_AGENTS))}")
        return v

    @field_validator("note", "session_id")
    @classmethod
    def validate_text(cls, v: str) -> str:
        return reject_control_chars(v, "text")


class ArchiveRequest(BaseModel):
    note: str = Field(default="", max_length=2000)
    session_id: str = Field(default="archive", max_length=128)

    @field_validator("note", "session_id")
    @classmethod
    def validate_text(cls, v: str) -> str:
        return reject_control_chars(v, "text")


class VerifyRequest(BaseModel):
    status: str = Field(default="done", pattern="^(done|needs_human|failed|failed_blocked)$")
    note: str = Field(default="", max_length=2000)
    session_id: str = Field(default="qa-verify", max_length=128)

    @field_validator("note", "session_id")
    @classmethod
    def validate_text(cls, v: str) -> str:
        return reject_control_chars(v, "text")


class DispatchRequest(BaseModel):
    agent: str = "jules"
    limit: int = Field(default=1, ge=1, le=100)
    live: bool = False
    task_id: str | None = Field(default=None, max_length=128, pattern=TASK_ID_PATTERN)
    session_id: str = Field(default="api", max_length=128)

    @field_validator("agent")
    @classmethod
    def validate_agent(cls, v: str) -> str:
        if v not in VALID_DISPATCH_AGENTS:
            raise ValueError(f"agent must be one of {', '.join(sorted(VALID_DISPATCH_AGENTS))}")
        return v

    @field_validator("limit", mode="before")
    @classmethod
    def validate_limit(cls, v: Any) -> Any:
        return reject_bool_integer(v, "limit")

    @field_validator("session_id")
    @classmethod
    def validate_text(cls, v: str) -> str:
        return reject_control_chars(v, "session_id")


@dataclass
class LoadedBoard:
    data: dict[str, Any]
    sha: str | None = None
    storage: str = "file"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def tasks_path() -> Path:
    return Path(os.environ.get("LIMEN_TASKS", str(LIMEN_ROOT / "tasks.yaml")))


def storage_mode() -> str:
    return "github" if GITHUB_REPO else "file"


def storage_status() -> dict[str, Any]:
    if storage_mode() == "github":
        return {
            "mode": "github",
            "repo": GITHUB_REPO,
            "branch": GITHUB_BRANCH,
            "path": GITHUB_PATH,
            "configured": bool(GITHUB_REPO and GITHUB_TOKEN),
        }
    return {"mode": "file", "path": str(tasks_path()), "configured": True}


def empty_board(message: str) -> dict[str, Any]:
    return {
        "version": "1.0",
        "portal": {
            "name": "no portal",
            "description": message,
            "budget": {"daily": 100, "unit": "runs", "track": {"date": "", "spent": 0, "per_agent": {}}},
        },
        "tasks": [],
    }


def github_contents_url() -> str:
    if "/" not in GITHUB_REPO:
        raise HTTPException(status_code=500, detail="LIMEN_GITHUB_REPO must be owner/repo")
    path = urllib.parse.quote(GITHUB_PATH, safe="/")
    return f"{GITHUB_API.rstrip('/')}/repos/{GITHUB_REPO}/contents/{path}"


def github_request(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if not GITHUB_TOKEN:
        raise HTTPException(status_code=500, detail="LIMEN_GITHUB_TOKEN is required for GitHub storage")
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Content-Type": "application/json"} if payload is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise HTTPException(
            status_code=502, detail=f"GitHub storage request failed ({exc.code}): {detail[:500]}"
        ) from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=f"GitHub storage request failed: {exc.reason}") from exc


def load_github_board() -> LoadedBoard:
    url = f"{github_contents_url()}?ref={urllib.parse.quote(GITHUB_BRANCH)}"
    raw = github_request("GET", url)
    content = raw.get("content", "")
    encoding = raw.get("encoding", "")
    if encoding != "base64":
        raise HTTPException(status_code=502, detail=f"GitHub content encoding is unsupported: {encoding}")
    decoded = base64.b64decode(content).decode("utf-8")
    return LoadedBoard(yaml.safe_load(decoded) or {"portal": {}, "tasks": []}, raw.get("sha"), "github")


def save_github_board(data: dict[str, Any], sha: str | None = None) -> None:
    if sha is None:
        sha = load_github_board().sha
    message = os.environ.get("LIMEN_GITHUB_COMMIT_MESSAGE", "Update Limen task board")
    payload: dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(yaml.safe_dump(data, sort_keys=False, allow_unicode=True).encode("utf-8")).decode(
            "ascii"
        ),
        "branch": GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha
    github_request("PUT", github_contents_url(), payload)


def load_board_doc() -> LoadedBoard:
    if storage_mode() == "github":
        return load_github_board()
    path = tasks_path()
    if not path.exists():
        return LoadedBoard(empty_board(f"Missing task file at {path}"))
    with path.open() as handle:
        return LoadedBoard(yaml.safe_load(handle) or {"portal": {}, "tasks": []})


def load_board() -> dict[str, Any]:
    return load_board_doc().data


def save_board(data: dict[str, Any], sha: str | None = None) -> None:
    if storage_mode() == "github":
        save_github_board(data, sha)
        return
    path = tasks_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=path.parent) as handle:
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True)
        tmp = Path(handle.name)
    tmp.replace(path)


def configured_persona_tokens() -> dict[str, set[str]]:
    owner_tokens = {
        token
        for token in (
            LIMEN_TOKEN,
            os.environ.get("LIMEN_API_TOKEN", ""),
            os.environ.get("LIMEN_OWNER_TOKEN", ""),
        )
        if token
    }
    client_tokens = {token for token in (os.environ.get("LIMEN_CLIENT_TOKEN", ""),) if token}
    return {"owner": owner_tokens, "client": client_tokens}


def resolve_persona(authorization: str | None = None, allow_public: bool = False) -> str:
    tokens = configured_persona_tokens()
    if not tokens["owner"] and not tokens["client"]:
        return "owner"
    if not authorization:
        if allow_public:
            return "public"
        raise HTTPException(status_code=401, detail="missing Authorization header")
    scheme, _, token = authorization.partition(" ")  # allow-secret
    if scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="invalid token")
    if token in tokens["owner"]:
        return "owner"
    if token in tokens["client"]:
        return "client"
    raise HTTPException(status_code=401, detail="invalid token")


def require_persona(authorization: str | None, allowed: set[str]) -> str:
    persona = resolve_persona(authorization, allow_public="public" in allowed)
    if persona not in allowed:
        raise HTTPException(status_code=403, detail=f"{persona} persona is not sanctioned for this endpoint")
    return persona


def verify_token(authorization: str | None = None) -> None:
    require_persona(authorization, {"owner"})


def budget(data: dict[str, Any]) -> dict[str, Any]:
    portal = data.setdefault("portal", {})
    raw = portal.setdefault("budget", {"daily": 100, "unit": "runs"})
    raw.setdefault("daily", 100)
    raw.setdefault("unit", "runs")
    raw.setdefault("per_agent", {})
    raw.setdefault("track", {"date": "", "spent": 0, "per_agent": {}})
    raw["track"].setdefault("per_agent", {})
    return raw


def maybe_reset_budget(data: dict[str, Any]) -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    track = budget(data)["track"]
    if track.get("date") != today:
        track["date"] = today
        track["spent"] = 0
        track["per_agent"] = {agent: 0 for agent in budget(data).get("per_agent", {})}


def spend_budget(data: dict[str, Any], agent: str, cost: int) -> None:
    maybe_reset_budget(data)
    track = budget(data)["track"]
    track["spent"] = int(track.get("spent", 0)) + cost
    per_agent = track.setdefault("per_agent", {})
    per_agent[agent] = int(per_agent.get(agent, 0)) + cost


def remaining_budget(data: dict[str, Any], agent: str) -> int:
    maybe_reset_budget(data)
    raw = budget(data)
    track = raw["track"]
    daily_remaining = int(raw.get("daily", 100)) - int(track.get("spent", 0))
    agent_limit = raw.get("per_agent", {}).get(agent)
    if agent_limit is None:
        return max(0, daily_remaining)
    agent_spent = int(track.get("per_agent", {}).get(agent, 0))
    return max(0, min(daily_remaining, int(agent_limit) - agent_spent))


def summary(data: dict[str, Any]) -> dict[str, Any]:
    tasks = data.get("tasks", [])
    by_status: dict[str, int] = {}
    by_agent: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    by_repo: dict[str, int] = {}
    for task in tasks:
        by_status[task.get("status", "unknown")] = by_status.get(task.get("status", "unknown"), 0) + 1
        by_agent[task.get("target_agent", "unknown")] = by_agent.get(task.get("target_agent", "unknown"), 0) + 1
        by_priority[task.get("priority", "unknown")] = by_priority.get(task.get("priority", "unknown"), 0) + 1
        repo = task.get("repo") or "limen"
        by_repo[repo] = by_repo.get(repo, 0) + 1
    return {
        "generated_at": now_iso(),
        "total": len(tasks),
        "by_status": by_status,
        "by_agent": by_agent,
        "by_priority": by_priority,
        "by_repo": by_repo,
        "budget": budget(data),
        "throughput": throughput(data),
    }


def throughput(data: dict[str, Any]) -> dict[str, Any]:
    tasks = data.get("tasks", [])
    current_date = datetime.now(timezone.utc).date()
    created_dates = [created for task in tasks if (created := parse_date(task.get("created")))]
    first_created = min(created_dates) if created_dates else current_date
    age_days = max(1, (current_date - first_created).days + 1)
    raw_budget = budget(data)
    daily_capacity = int(raw_budget.get("daily", 100))
    by_status: dict[str, int] = {}
    by_event_status: dict[str, int] = {}
    by_event_agent: dict[str, int] = {}
    by_event_date: dict[str, int] = {}
    for task in tasks:
        status = task.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        for entry in task.get("dispatch_log", []) or []:
            event_status = entry.get("status", "unknown")
            by_event_status[event_status] = by_event_status.get(event_status, 0) + 1
            agent = entry.get("agent", "unknown")
            by_event_agent[agent] = by_event_agent.get(agent, 0) + 1
            event_date = parse_date(entry.get("timestamp"))
            if event_date:
                key = event_date.isoformat()
                by_event_date[key] = by_event_date.get(key, 0) + 1
    done = by_status.get("done", 0) + by_status.get("archived", 0)
    expected_capacity_runs = daily_capacity * age_days
    recorded_events = sum(by_event_status.values())
    recorded_starts = sum(by_event_status.get(status, 0) for status in ("dispatched", "in_progress"))
    recorded_finishes = sum(
        by_event_status.get(status, 0) for status in ("done", "failed", "failed_blocked", "archived")
    )
    unrecorded_capacity_runs = max(0, expected_capacity_runs - recorded_starts)
    return {
        "first_created": first_created.isoformat(),
        "current_date": current_date.isoformat(),
        "age_days": age_days,
        "daily_capacity": daily_capacity,
        "expected_capacity_runs": expected_capacity_runs,
        "task_burndown_target_per_day": ceil(len(tasks) / age_days) if tasks else 0,
        "recorded_events": recorded_events,
        "recorded_starts": recorded_starts,
        "recorded_finishes": recorded_finishes,
        "done": done,
        "not_done": len(tasks) - done,
        "unrecorded_capacity_runs": unrecorded_capacity_runs,
        "by_event_status": by_event_status,
        "by_event_agent": by_event_agent,
        "by_event_date": by_event_date,
    }


def public_summary(data: dict[str, Any]) -> dict[str, Any]:
    raw = summary(data)
    done = raw["by_status"].get("done", 0) + raw["by_status"].get("archived", 0)
    return {
        "portal": {
            "name": data.get("portal", {}).get("name", "Universal Task Intake"),
            "description": data.get("portal", {}).get("description", ""),
        },
        "total": raw["total"],
        "completed": done,
        "completion_rate": round(done / max(1, raw["total"]), 3),
        "active": raw["by_status"].get("dispatched", 0) + raw["by_status"].get("in_progress", 0),
        "by_status": raw["by_status"],
        "generated_at": now_iso(),
        "throughput": raw["throughput"],
    }


def client_summary(data: dict[str, Any]) -> dict[str, Any]:
    raw = public_summary(data)
    stale = release_stale_candidates(data, hours=24)
    stale_ids = {task["id"] for task in stale}
    lifecycle = {"recover": 0, "verify": 0, "assign": 0, "archive": 0, "archived": 0}
    for task in data.get("tasks", []):
        phase = task_lifecycle(task, stale_ids)["phase"]
        lifecycle[phase] = lifecycle.get(phase, 0) + 1
    raw["stale_count"] = len(stale)
    raw["lifecycle"] = lifecycle
    raw["budget"] = budget(data)
    raw["top_repos"] = sorted(summary(data)["by_repo"].items(), key=lambda item: item[1], reverse=True)[:10]
    active_tasks = []
    for task in data.get("tasks", []):
        if task.get("status") not in ("dispatched", "in_progress") and task.get("id") not in stale_ids:
            continue
        lifecycle = task_lifecycle(task, stale_ids)
        active_tasks.append(
            {
                "id": task.get("id"),
                "title": task.get("title"),
                "repo": task.get("repo") or "",
                "target_agent": task.get("target_agent") or "unknown",
                "status": task.get("status") or "unknown",
                "priority": task.get("priority") or "medium",
                "stale": task.get("id") in stale_ids,
                "phase": lifecycle["phase"],
                "next_gate": lifecycle["next_gate"],
            }
        )
    raw["active_tasks"] = active_tasks[:25]
    return raw


def task_events(task: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for entry in task.get("dispatch_log", []):
        timestamp = entry.get("timestamp")
        if not timestamp:
            continue
        try:
            timestamp_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        events.append({"timestamp": timestamp, "timestamp_dt": timestamp_dt})
    return sorted(events, key=lambda event: event["timestamp_dt"], reverse=True)


def task_lifecycle(task: dict[str, Any], stale_ids: set[str]) -> dict[str, Any]:
    latest = task_events(task)[0] if task_events(task) else None
    urls = task.get("urls", []) or []
    stale = task.get("id") in stale_ids
    has_pr = any("/pull/" in url for url in urls)
    has_issue = any("/issues/" in url for url in urls)
    status = task.get("status", "unknown")
    if status == "archived":
        phase = "archived"
    elif status == "done":
        phase = "archive"
    elif stale or status in ("failed", "failed_blocked", "needs_human"):
        phase = "recover"
    elif has_pr or status in ("dispatched", "in_progress"):
        phase = "verify"
    else:
        phase = "assign"
    if phase == "archived":
        next_gate = "suppressed from active steering"
    elif phase == "archive":
        next_gate = "archive evidence and suppress from active steering"
    elif phase == "recover":
        next_gate = "release stale claim or reassign with failure note"
    elif phase == "verify":
        next_gate = "verify PR/runtime evidence, then close or return"
    else:
        next_gate = "assign to agent with budget and acceptance gate"
    return {
        "id": task.get("id"),
        "title": task.get("title"),
        "repo": task.get("repo", ""),
        "status": status,
        "priority": task.get("priority", "medium"),
        "assignee": task.get("target_agent") or "unassigned",
        "phase": phase,
        "next_gate": next_gate,
        "stale": stale,
        "has_issue": has_issue,
        "has_pr": has_pr,
        "latest_event_at": latest["timestamp"] if latest else task.get("updated") or task.get("created"),
    }


def qa_status(data: dict[str, Any], agent: str = "jules") -> dict[str, Any]:
    stale_ids = {candidate["id"] for candidate in release_stale_candidates(data, 24)}
    items = [task_lifecycle(task, stale_ids) for task in data.get("tasks", [])]
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "backlog": 4}
    phase_order = {"recover": 0, "verify": 1, "assign": 2, "archive": 3, "archived": 4}
    steering = sorted(
        [item for item in items if item["phase"] not in ("archive", "archived")],
        key=lambda item: (
            phase_order.get(item["phase"], 99),
            priority_order.get(item["priority"], 99),
            str(item["id"]),
        ),
    )
    qa_items = [item for item in items if item["phase"] == "verify"]
    recover_items = [item for item in items if item["phase"] == "recover"]
    assign_items = [item for item in items if item["phase"] == "assign"]
    archive_ready = [item for item in items if item["phase"] == "archive"]
    archived_items = [item for item in items if item["phase"] == "archived"]
    return {
        "status": "degraded" if recover_items else "ok",
        "surface": "qa",
        "generated_at": now_iso(),
        "lifecycle": {
            "total": len(items),
            "assign": len(assign_items),
            "verify": len(qa_items),
            "recover": len(recover_items),
            "archive_ready": len(archive_ready),
            "archived": len(archived_items),
        },
        "steering": {
            "principle": "Every visible item is a portal into one task lifecycle; closed work is archived out of active steering.",
            "next_batch": steering[:24],
            "qa_queue": qa_items[:24],
            "recovery_queue": recover_items[:24],
            "assignment_queue": assign_items[:24],
            "archive_queue": archive_ready[:24],
        },
        "mechanisms": [
            {
                "id": "release-stale",
                "label": "Release stale claims",
                "agent": agent,
                "command": "POST /api/release-stale?hours=24&dry_run=false",
                "mode": "human-approved apply",
                "count": len(recover_items),
            },
            {
                "id": "qa-verify",
                "label": "Verify PR and runtime evidence",
                "agent": "qa",
                "command": "POST /api/tasks/{task_id}/verify",
                "mode": "human-approved evidence gate",
                "count": len(qa_items),
            },
            {
                "id": "assign-next",
                "label": "Assign or reassign next task",
                "agent": "steering",
                "command": "POST /api/tasks/{task_id}/assign",
                "mode": "human-approved assignment",
                "count": len(assign_items),
            },
            {
                "id": "archive-done",
                "label": "Archive closed evidence",
                "agent": "system",
                "command": "POST /api/tasks/{task_id}/archive",
                "mode": "human-approved archive",
                "count": len(archive_ready),
            },
        ],
    }


def surface_manifest(data: dict[str, Any], persona: str = "owner") -> dict[str, Any]:
    raw = summary(data)
    stale_count = len(release_stale_candidates(data, 24))
    manifest: dict[str, Any] = {
        "status": "ok",
        "persona": persona,
        "generated_at": now_iso(),
        "source": {
            "type": "api-runtime",
            "task_file": GITHUB_PATH if storage_mode() == "github" else str(tasks_path()),
            "api_runtime": "connected",
            "api_url_configured": True,
            "blocker": None,
            "storage": storage_status(),
        },
        "surfaces": [
            {
                "id": "internal",
                "title": "Internal operations",
                "route": "/",
                "contract": "/api/status",
                "persona": "owner",
                "sanctioned_personas": ["owner"],
                "disclosure": "full task board, dispatch controls, PR health, and operational logs",
            },
            {
                "id": "client",
                "title": "Client status",
                "route": "/client",
                "contract": "/api/client-status",
                "persona": "client",
                "sanctioned_personas": ["owner", "client"],
                "disclosure": "redacted active task rows, delivery metrics, budget, and repo distribution",
            },
            {
                "id": "public",
                "title": "Public status",
                "route": "/public",
                "contract": "/api/public-status",
                "persona": "public",
                "sanctioned_personas": ["owner", "client", "public"],
                "disclosure": "aggregate task health only",
            },
            {
                "id": "qa",
                "title": "QA and steering",
                "route": "/qa",
                "contract": "/api/qa-status",
                "persona": "owner",
                "sanctioned_personas": ["owner"],
                "disclosure": "lifecycle gates, assignment queues, verification queues, and archive suppression",
            },
        ],
        "contracts": {
            "internal": {"path": "/api/status", "total": raw["total"], "stale_count": stale_count},
            "client": {
                "path": "/api/client-status",
                "total": raw["total"],
                "stale_count": stale_count,
                "max_active_tasks": 25,
                "includes_dispatch_logs": False,
            },
            "public": {
                "path": "/api/public-status",
                "total": raw["total"],
                "includes_tasks": False,
                "includes_dispatch_logs": False,
            },
            "qa": {
                "path": "/api/qa-status",
                "total": raw["total"],
                "stale_count": stale_count,
                "verify_endpoint": "/api/tasks/{task_id}/verify",
                "assignment_endpoint": "/api/tasks/{task_id}/assign",
                "archive_endpoint": "/api/tasks/{task_id}/archive",
                "includes_dispatch_logs": False,
                "includes_task_context": False,
                "includes_task_urls": False,
            },
            "readiness": {
                "path": "/api/readiness",
                "includes_dispatch_logs": False,
            },
        },
    }
    manifest["surfaces"] = [
        surface for surface in manifest["surfaces"] if persona in surface.get("sanctioned_personas", [])
    ]
    sanctioned_ids = {surface["id"] for surface in manifest["surfaces"]}
    manifest["contracts"] = {
        key: value
        for key, value in manifest["contracts"].items()
        if key in sanctioned_ids or (key == "readiness" and persona == "owner")
    }
    return manifest


def readiness(data: dict[str, Any], agent: str = "jules") -> dict[str, Any]:
    raw = summary(data)
    stale = release_stale_candidates(data, 24)
    open_tasks = [
        task
        for task in data.get("tasks", [])
        if task.get("status") == "open" and task.get("target_agent", "any") in (agent, "any")
    ]
    raw_budget = budget(data)
    agent_limit = int(raw_budget.get("per_agent", {}).get(agent, raw_budget.get("daily", 100)))
    agent_spent = int(raw_budget.get("track", {}).get("per_agent", {}).get(agent, 0))
    remaining = remaining_budget(data, agent)
    agent_bin = (
        os.environ.get("LIMEN_JULES_BIN", "jules")
        if agent == "jules"
        else os.environ.get("LIMEN_DISPATCH_CMD", "agent-dispatch")
    )
    agent_path = shutil.which(agent_bin)
    checks = [
        {
            "id": "storage",
            "status": "pass" if storage_status().get("configured") else "fail",
            "detail": storage_status().get("mode", "unknown"),
        },
        {"id": "task_count", "status": "pass" if raw["total"] else "warn", "detail": f"{raw['total']} tasks"},
        {
            "id": "stale_claims",
            "status": "warn" if stale else "pass",
            "detail": f"{len(stale)} stale {agent} active tasks",
        },
        {
            "id": "open_queue",
            "status": "pass" if open_tasks else "warn",
            "detail": f"{len(open_tasks)} open {agent} tasks",
        },
        {
            "id": "budget",
            "status": "pass" if remaining > 0 else "fail",
            "detail": f"{remaining}/{agent_limit} {agent} runs remaining",
        },
        {
            "id": "agent_cli",
            "status": "pass" if agent_path else "fail",
            "detail": agent_path or f"{agent_bin} not found",
        },
        {"id": "api_runtime", "status": "pass", "detail": "connected"},
    ]
    if any(check["status"] == "fail" for check in checks):
        status = "blocked"
    elif any(check["status"] == "warn" for check in checks):
        status = "degraded"
    else:
        status = "ready"
    next_actions: list[str] = []
    if stale:
        next_actions.append("POST /api/release-stale?hours=24&dry_run=false")
    if open_tasks and remaining > 0 and agent_path:
        next_actions.append(f"POST /api/dispatch live=true limit={min(len(open_tasks), remaining)}")
    if not agent_path:
        next_actions.append(f"Install or configure {agent} dispatch CLI")
    if remaining <= 0:
        next_actions.append(f"Wait for {agent} budget reset or lower dispatch volume")
    return {
        "status": status,
        "agent": agent,
        "generated_at": now_iso(),
        "counts": {
            "total": raw["total"],
            "active": raw["by_status"].get("dispatched", 0) + raw["by_status"].get("in_progress", 0),
            "stale": len(stale),
            "open": len(open_tasks),
        },
        "budget": {
            "daily": raw_budget.get("daily", 100),
            "agent_limit": agent_limit,
            "agent_spent": agent_spent,
            "remaining": remaining,
        },
        "checks": checks,
        "next_actions": next_actions or ["No immediate action required"],
    }


def validate_task_id(task_id: str) -> None:
    if not isinstance(task_id, str) or len(task_id) < 1 or len(task_id) > 128:
        raise HTTPException(status_code=400, detail="invalid task_id format")
    if not TASK_ID_RE.match(task_id):
        raise HTTPException(status_code=400, detail="invalid task_id format")


def find_task(data: dict[str, Any], task_id: str) -> dict[str, Any]:
    validate_task_id(task_id)
    for task in data.get("tasks", []):
        if task.get("id") == task_id:
            return task
    raise HTTPException(status_code=404, detail=f"task {task_id} not found")


def append_log(task: dict[str, Any], agent: str, session_id: str, status: str, output: str = "") -> None:
    task.setdefault("dispatch_log", []).append(
        {
            "timestamp": now_iso(),
            "agent": agent,
            "session_id": session_id,
            "status": status,
            **({"output": output} if output else {}),
        }
    )
    task["updated"] = now_iso()


def build_prompt(task: dict[str, Any]) -> str:
    parts = [f"Complete task {task.get('id')}: {task.get('title')}"]
    if task.get("repo"):
        parts.append(f" in repository {task['repo']}")
    if task.get("context"):
        parts.append(f"\nContext: {task['context']}")
    if task.get("urls"):
        parts.append(f"\nReferences: {', '.join(task['urls'])}")
    return "".join(parts)


def dispatch_command(agent: str, task: dict[str, Any]) -> list[str]:
    prompt = build_prompt(task)
    if agent == "jules":
        repo = task.get("repo") or str(LIMEN_ROOT)
        return [os.environ.get("LIMEN_JULES_BIN", "jules"), "new", "--repo", repo, prompt]
    return [os.environ.get("LIMEN_DISPATCH_CMD", "agent-dispatch"), agent, prompt]


def run_dispatch_command(command: list[str]) -> tuple[bool, str]:
    timeout = int(os.environ.get("LIMEN_DISPATCH_TIMEOUT_SEC", "600"))
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError:
        return False, f"dispatch command not found: {command[0]}"
    except subprocess.TimeoutExpired:
        return False, f"dispatch command timed out after {timeout}s"

    output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
    if result.returncode != 0:
        return False, f"dispatch command exited {result.returncode}" + (f"\n{output}" if output else "")
    return True, output[:2000]


def dispatch_candidates(data: dict[str, Any], req: DispatchRequest) -> list[dict[str, Any]]:
    if req.task_id:
        task = find_task(data, req.task_id)
        if task.get("status") != "open":
            return []
        return [task] if task.get("target_agent", "any") in (req.agent, "any") else []

    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "backlog": 4}
    candidates = [
        task
        for task in data.get("tasks", [])
        if task.get("status") == "open" and task.get("target_agent", "any") in (req.agent, "any")
    ]
    candidates.sort(key=lambda task: priority_order.get(task.get("priority", "medium"), 99))
    return candidates


def release_stale_candidates(data: dict[str, Any], hours: int) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    candidates: list[dict[str, Any]] = []
    for task in data.get("tasks", []):
        if task.get("status") not in ("dispatched", "in_progress"):
            continue
        events = []
        for entry in task.get("dispatch_log", []):
            timestamp = entry.get("timestamp")
            if not timestamp:
                continue
            try:
                events.append(datetime.fromisoformat(timestamp.replace("Z", "+00:00")))
            except ValueError:
                continue
        latest = max(events) if events else None
        if latest is None or latest < cutoff:
            candidates.append(
                {
                    "id": task.get("id", "unknown"),
                    "title": task.get("title", ""),
                    "agent": task.get("target_agent", "unknown"),
                    "status": task.get("status", "unknown"),
                    "latest": latest.isoformat() if latest else None,
                }
            )
    return candidates


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "time": now_iso(), "storage": storage_status()}


@app.get("/api/status")
def get_status(authorization: str | None = Header(None)) -> dict[str, Any]:
    require_persona(authorization, {"owner"})
    data = load_board()
    return {
        "status": "ok",
        "surface": "internal",
        "portal": data.get("portal", {}),
        "summary": summary(data),
        "storage": storage_status(),
    }


@app.get("/api/client-status")
def get_client_status(authorization: str | None = Header(None)) -> dict[str, Any]:
    require_persona(authorization, {"owner", "client"})
    data = load_board()
    return {"status": "ok", "surface": "client", "summary": client_summary(data), "storage": storage_status()}


@app.get("/api/public-status")
def get_public_status() -> dict[str, Any]:
    data = load_board()
    return {"status": "ok", "surface": "public", "summary": public_summary(data)}


@app.get("/api/qa-status")
def get_qa_status(authorization: str | None = Header(None), agent: str = Query("jules")) -> dict[str, Any]:
    require_persona(authorization, {"owner"})
    if agent not in VALID_AGENTS:
        raise HTTPException(status_code=400, detail=f"agent must be one of {', '.join(sorted(VALID_AGENTS))}")
    return qa_status(load_board(), agent=agent)


@app.get("/api/surface-manifest")
def get_surface_manifest(authorization: str | None = Header(None)) -> dict[str, Any]:
    return surface_manifest(load_board(), persona=resolve_persona(authorization, allow_public=True))


@app.get("/api/readiness")
def get_readiness(authorization: str | None = Header(None), agent: str = Query("jules")) -> dict[str, Any]:
    require_persona(authorization, {"owner"})
    if agent not in VALID_AGENTS:
        raise HTTPException(status_code=400, detail=f"agent must be one of {', '.join(sorted(VALID_AGENTS))}")
    return readiness(load_board(), agent=agent)


@app.get("/api/tasks")
def list_tasks(
    authorization: str | None = Header(None),
    status: str | None = Query(None, max_length=64),
    agent: str | None = Query(None, max_length=64),
    repo: str | None = Query(None, max_length=256),
) -> dict[str, Any]:
    require_persona(authorization, {"owner"})
    if status is not None and status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {', '.join(sorted(VALID_STATUSES))}")
    if agent is not None and agent not in VALID_AGENTS:
        raise HTTPException(status_code=400, detail=f"agent must be one of {', '.join(sorted(VALID_AGENTS))}")
    if repo is not None:
        try:
            validate_repo_value(repo)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    tasks = load_board().get("tasks", [])
    if status:
        tasks = [task for task in tasks if task.get("status") == status]
    if agent:
        tasks = [task for task in tasks if task.get("target_agent") == agent]
    if repo:
        tasks = [task for task in tasks if task.get("repo") == repo]
    return {"tasks": tasks, "count": len(tasks)}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    require_persona(authorization, {"owner"})
    return find_task(load_board(), task_id)


@app.post("/api/tasks")
def create_task(req: TaskCreate, authorization: str | None = Header(None)) -> dict[str, Any]:
    require_persona(authorization, {"owner"})
    doc = load_board_doc()
    data = doc.data
    if any(task.get("id") == req.id for task in data.get("tasks", [])):
        raise HTTPException(status_code=409, detail=f"task {req.id} already exists")
    task = req.model_dump()
    task["created"] = now_iso()
    task["updated"] = task["created"]
    task["dispatch_log"] = []
    data.setdefault("tasks", []).append(task)
    save_board(data, doc.sha)
    return {"status": "created", "task": task}


@app.patch("/api/tasks/{task_id}")
def update_task(task_id: str, req: TaskUpdate, authorization: str | None = Header(None)) -> dict[str, Any]:
    require_persona(authorization, {"owner"})
    doc = load_board_doc()
    data = doc.data
    task = find_task(data, task_id)
    update = req.model_dump(exclude_none=True)
    status = update.pop("status", None)
    output = update.pop("output", "")
    agent = update.pop("agent", task.get("target_agent", "api"))
    session_id = update.pop("session_id", "api")
    for key, value in update.items():
        task[key] = value
    if status:
        task["status"] = status
        append_log(task, agent, session_id, status, output)
    else:
        task["updated"] = now_iso()
    save_board(data, doc.sha)
    return {"status": "updated", "task": task}


@app.post("/api/tasks/{task_id}/assign")
def assign_task(task_id: str, req: AssignmentRequest, authorization: str | None = Header(None)) -> dict[str, Any]:
    require_persona(authorization, {"owner"})
    doc = load_board_doc()
    data = doc.data
    task = find_task(data, task_id)
    before = {
        "target_agent": task.get("target_agent"),
        "priority": task.get("priority"),
        "budget_cost": task.get("budget_cost"),
        "status": task.get("status"),
    }
    if req.target_agent is not None:
        task["target_agent"] = req.target_agent
    if req.priority is not None:
        task["priority"] = req.priority
    if req.budget_cost is not None:
        task["budget_cost"] = req.budget_cost
    if req.status is not None:
        task["status"] = req.status
    after = {
        "target_agent": task.get("target_agent"),
        "priority": task.get("priority"),
        "budget_cost": task.get("budget_cost"),
        "status": task.get("status"),
    }
    changed = [key for key, value in after.items() if before.get(key) != value]
    output = req.note or f"Assigned via steering controls: {', '.join(changed) if changed else 'no field changes'}"
    append_log(task, "api", req.session_id, "assigned", output)
    save_board(data, doc.sha)
    return {
        "status": "assigned",
        "task": task,
        "changed": changed,
    }


@app.post("/api/tasks/{task_id}/archive")
def archive_task(task_id: str, req: ArchiveRequest, authorization: str | None = Header(None)) -> dict[str, Any]:
    require_persona(authorization, {"owner"})
    doc = load_board_doc()
    data = doc.data
    task = find_task(data, task_id)
    if task.get("status") not in ("done", "archived"):
        raise HTTPException(status_code=409, detail="only done tasks can be archived")
    if task.get("status") != "archived":
        task["status"] = "archived"
        append_log(task, "api", req.session_id, "archived", req.note or "Archived from QA steering")
        save_board(data, doc.sha)
    return {
        "status": "archived",
        "task": task,
    }


@app.post("/api/tasks/{task_id}/verify")
def verify_task(task_id: str, req: VerifyRequest, authorization: str | None = Header(None)) -> dict[str, Any]:
    require_persona(authorization, {"owner"})
    doc = load_board_doc()
    data = doc.data
    task = find_task(data, task_id)
    if task.get("status") not in ("dispatched", "in_progress", "needs_human", "failed", "failed_blocked", "done"):
        raise HTTPException(status_code=409, detail="only active, attention, or done tasks can be verified")
    task["status"] = req.status
    append_log(task, "qa", req.session_id, req.status, req.note or f"QA verified task as {req.status}")
    save_board(data, doc.sha)
    return {
        "status": "verified",
        "task": task,
        "verified_status": req.status,
    }


@app.post("/api/dispatch")
def dispatch(req: DispatchRequest, authorization: str | None = Header(None)) -> dict[str, Any]:
    require_persona(authorization, {"owner"})
    doc = load_board_doc()
    data = doc.data
    maybe_reset_budget(data)
    remaining = remaining_budget(data, req.agent)
    selected: list[dict[str, Any]] = []
    for task in dispatch_candidates(data, req):
        cost = int(task.get("budget_cost", 1))
        if cost > remaining:
            continue
        selected.append(task)
        remaining -= cost
        if len(selected) >= max(1, min(req.limit, 100)):
            break

    previews = [
        {
            "id": task.get("id"),
            "title": task.get("title"),
            "repo": task.get("repo"),
            "budget_cost": int(task.get("budget_cost", 1)),
            "command": dispatch_command(req.agent, task),
        }
        for task in selected
    ]

    if not req.live:
        return {
            "status": "dry_run",
            "agent": req.agent,
            "remaining_budget": remaining_budget(data, req.agent),
            "candidates": previews,
            "count": len(previews),
            "live": False,
        }

    dispatched: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for task in selected:
        command = dispatch_command(req.agent, task)
        ok, output = run_dispatch_command(command)
        if ok:
            task["status"] = "dispatched"
            append_log(task, req.agent, req.session_id, "dispatched", output or "Dispatched via Limen API")
            spend_budget(data, req.agent, int(task.get("budget_cost", 1)))
            dispatched.append(task)
        else:
            task["status"] = "failed"
            append_log(task, req.agent, req.session_id, "failed", output)
            failed.append({"id": task.get("id"), "title": task.get("title"), "error": output})

    save_board(data, doc.sha)
    return {
        "status": "ok" if not failed else "partial_failure",
        "agent": req.agent,
        "dispatched": dispatched,
        "failed": failed,
        "count": len(dispatched),
        "live": True,
        "remaining_budget": remaining_budget(data, req.agent),
    }


@app.post("/api/release-stale")
def release_stale(
    authorization: str | None = Header(None),
    hours: int = Query(24, ge=0, le=8760),
    dry_run: bool = True,
) -> dict[str, Any]:
    require_persona(authorization, {"owner"})
    doc = load_board_doc()
    data = doc.data
    candidates = release_stale_candidates(data, hours)
    # The deployed API image intentionally has no Jules CLI.  Without a successful remote catalog
    # it cannot prove a Jules session absent, so it must fail closed and leave those claims for the
    # CLI heartbeat's shared remote-aware release/harvest/recover path.
    routed_candidates = [
        {
            **candidate,
            "action": "hold" if candidate.get("agent") == "jules" else "release",
            "remote_status": "cli_unavailable" if candidate.get("agent") == "jules" else "not_jules",
        }
        for candidate in candidates
    ]
    release_ids = {candidate["id"] for candidate in routed_candidates if candidate.get("action") == "release"}
    held = [candidate["id"] for candidate in routed_candidates if candidate.get("action") == "hold"]
    if not dry_run and release_ids:
        for task in data.get("tasks", []):
            if task.get("id") in release_ids:
                task["status"] = "open"
                append_log(task, "api", "release-stale", "open", f"Released stale claim after {hours}h")
        save_board(data, doc.sha)
    return {
        "status": "dry_run" if dry_run else "released",
        "released": sorted(release_ids),
        "held": held,
        "harvest_ready": [],
        "recover_ready": [],
        "remote_probe": {
            "status": "unavailable" if held else "not_requested",
            "session_count": 0,
        },
        "candidates": routed_candidates,
        "candidate_count": len(routed_candidates),
        "count": len(routed_candidates) if dry_run else len(release_ids),
        "dry_run": dry_run,
    }
