import json
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel

app = FastAPI(
    title="limen API",
    description="Universal agent task intake — SaaS backend",
    version="0.1.0",
)

LIMEN_ROOT = Path(os.environ.get("LIMEN_ROOT", str(Path.home() / "limen")))
LIMEN_TOKEN = os.environ.get("LIMEN_API_TOKEN", "")


def _tasks_path() -> Path:
    p = os.environ.get("LIMEN_TASKS", str(LIMEN_ROOT / "tasks.yaml"))
    return Path(p)


def _load_tasks() -> dict:
    path = _tasks_path()
    if not path.exists():
        return {"portal": {"name": "no portal"}, "tasks": []}
    with open(path) as f:
        return yaml.safe_load(f)


def _save_tasks(data: dict) -> None:
    path = _tasks_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def _verify_token(authorization: str | None = None) -> None:
    if not LIMEN_TOKEN:
        return
    if not authorization:
        raise HTTPException(401, "missing Authorization header")
    scheme, _, token = authorization.partition(" ")  # allow-secret
    if scheme.lower() != "bearer" or token != LIMEN_TOKEN:
        raise HTTPException(401, "invalid token")


# ── Models ─────────────────────────────────────────────────────────────────


class DispatchRequest(BaseModel):
    agent: str
    task_id: str
    repo: str = ""
    title: str
    context: str = ""
    urls: list[str] = []


class StatusResponse(BaseModel):
    portal: dict
    tasks: list
    summary: dict


# ── Routes ─────────────────────────────────────────────────────────────────


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@app.get("/api/status", response_model=StatusResponse)
def get_status(authorization: str | None = Header(None)):
    _verify_token(authorization)
    data = _load_tasks()
    tasks = data.get("tasks", [])
    by_status: dict[str, int] = {}
    by_agent: dict[str, int] = {}
    for t in tasks:
        s = t.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1
        a = t.get("target_agent", "unknown")
        by_agent[a] = by_agent.get(a, 0) + 1
    return StatusResponse(
        portal=data.get("portal", {}),
        tasks=tasks,
        summary={"total": len(tasks), "by_status": by_status, "by_agent": by_agent},
    )


@app.post("/api/dispatch")
def dispatch_task(req: DispatchRequest, authorization: str | None = Header(None)):
    _verify_token(authorization)
    data = _load_tasks()
    tasks = data.get("tasks", [])
    existing = [t for t in tasks if t["id"] == req.task_id]
    if existing:
        task = existing[0]
        if task.get("status") in ("dispatched", "in_progress", "done"):
            raise HTTPException(409, f"task {req.task_id} is already {task['status']}")
        task["status"] = "dispatched"
        task["updated"] = datetime.now(timezone.utc).isoformat()
    else:
        tasks.append(
            {
                "id": req.task_id,
                "title": req.title,
                "repo": req.repo,
                "target_agent": req.agent,
                "status": "dispatched",
                "context": req.context,
                "urls": req.urls,
                "labels": [],
                "created": datetime.now(timezone.utc).isoformat(),
            }
        )
        data["tasks"] = tasks
    _save_tasks(data)
    return {"status": "dispatched", "task_id": req.task_id, "agent": req.agent}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str, authorization: str | None = Header(None)):
    _verify_token(authorization)
    data = _load_tasks()
    for t in data.get("tasks", []):
        if t["id"] == task_id:
            return t
    raise HTTPException(404, f"task {task_id} not found")
