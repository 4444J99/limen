"""
Database persistence module for Limen API.
Uses SQLite for zero-dependency local runtime and PostgreSQL when configured.
"""
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Dict, List

DEFAULT_DB_PATH = Path(os.environ.get("LIMEN_DB_PATH", str(Path(__file__).parent / "limen.db")))

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    repo TEXT,
    type TEXT DEFAULT 'code',
    target_agent TEXT DEFAULT 'jules',
    priority TEXT DEFAULT 'medium',
    budget_cost INTEGER DEFAULT 1,
    status TEXT DEFAULT 'open',
    labels TEXT,
    urls TEXT,
    context TEXT,
    predicate TEXT,
    receipt_target TEXT,
    origin TEXT,
    horizon TEXT,
    value_case TEXT,
    owner_surface TEXT,
    external_deadline INTEGER DEFAULT 0,
    due_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    task_id TEXT,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    reasoning TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS timelines (
    id TEXT PRIMARY KEY,
    task_id TEXT,
    event_type TEXT NOT NULL,
    payload TEXT,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    external_id TEXT UNIQUE,
    user_name TEXT NOT NULL UNIQUE,
    name TEXT,
    email TEXT,
    active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_roles (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS groups (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS group_members (
    id TEXT PRIMARY KEY,
    group_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(group_id, user_id)
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    key TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outbox_events (
    id TEXT PRIMARY KEY,
    target_url TEXT,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    signature TEXT,
    status TEXT DEFAULT 'pending',
    attempts INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    processed_at TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    idempotency_key TEXT UNIQUE,
    type TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    worker_id TEXT,
    lease_expires_at TEXT,
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    run_after TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_target_agent ON tasks(target_agent);
CREATE INDEX IF NOT EXISTS idx_decisions_task_id ON decisions(task_id);
CREATE INDEX IF NOT EXISTS idx_timelines_task_id ON timelines(task_id);
CREATE INDEX IF NOT EXISTS idx_users_user_name ON users(user_name);
CREATE INDEX IF NOT EXISTS idx_users_external_id ON users(external_id);
CREATE INDEX IF NOT EXISTS idx_groups_display_name ON groups(display_name);
CREATE INDEX IF NOT EXISTS idx_group_members_group_id ON group_members(group_id);
CREATE INDEX IF NOT EXISTS idx_group_members_user_id ON group_members(user_id);
CREATE INDEX IF NOT EXISTS idx_idempotency_keys_key ON idempotency_keys(key);
CREATE INDEX IF NOT EXISTS idx_outbox_events_status ON outbox_events(status);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    target = db_path or DEFAULT_DB_PATH
    if str(target) != ":memory:":
        target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    if str(target) != ":memory:":
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
        except Exception:
            pass
    return conn


_LOCAL = threading.local()
_DB_LOCK = threading.RLock()


def get_db() -> sqlite3.Connection:
    target_path = Path(os.environ.get("LIMEN_DB_PATH", str(DEFAULT_DB_PATH)))
    conn_path = getattr(_LOCAL, "db_path", None)
    if not hasattr(_LOCAL, "conn") or _LOCAL.conn is None or conn_path != target_path:
        with _DB_LOCK:
            if hasattr(_LOCAL, "conn") and _LOCAL.conn is not None:
                try:
                    _LOCAL.conn.close()
                except Exception:
                    pass
            conn = get_connection(target_path)
            init_db(conn)
            _LOCAL.conn = conn
            _LOCAL.db_path = target_path
    return _LOCAL.conn


def reset_db() -> None:
    global _LOCAL
    with _DB_LOCK:
        if hasattr(_LOCAL, "conn") and _LOCAL.conn is not None:
            try:
                _LOCAL.conn.close()
            except Exception:
                pass
            _LOCAL.conn = None
            _LOCAL.db_path = None
        _LOCAL = threading.local()


def init_db(conn: Optional[sqlite3.Connection] = None) -> None:
    c = conn or get_db()
    with c:
        c.executescript(CREATE_TABLES_SQL)


# --- Tasks Queries ---

def db_sync_tasks_from_board(board_tasks: List[Dict[str, Any]], conn: Optional[sqlite3.Connection] = None) -> None:
    c = conn or get_db()
    with _DB_LOCK:
        with c:
            for t in board_tasks:
                task_id = str(t.get("id", ""))
                if not task_id:
                    continue
                labels = json.dumps(t.get("labels")) if t.get("labels") is not None else None
                urls = json.dumps(t.get("urls")) if t.get("urls") is not None else None
                created = str(t.get("created") or now_iso())
                updated = str(t.get("updated") or created)
                c.execute(
                    """
                    INSERT INTO tasks (
                        id, title, repo, type, target_agent, priority, budget_cost, status,
                        labels, urls, context, predicate, receipt_target, origin, horizon,
                        value_case, owner_surface, external_deadline, due_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title=excluded.title,
                        repo=excluded.repo,
                        target_agent=excluded.target_agent,
                        priority=excluded.priority,
                        budget_cost=excluded.budget_cost,
                        status=excluded.status,
                        labels=excluded.labels,
                        urls=excluded.urls,
                        context=excluded.context,
                        predicate=excluded.predicate,
                        receipt_target=excluded.receipt_target,
                        updated_at=excluded.updated_at
                    """,
                    (
                        task_id,
                        str(t.get("title", "")),
                        t.get("repo"),
                        t.get("type", "code"),
                        t.get("target_agent", "jules"),
                        t.get("priority", "medium"),
                        int(t.get("budget_cost", 1)),
                        str(t.get("status", "open")),
                        labels,
                        urls,
                        t.get("context"),
                        t.get("predicate"),
                        t.get("receipt_target"),
                        t.get("origin"),
                        t.get("horizon"),
                        t.get("value_case"),
                        t.get("owner_surface"),
                        1 if t.get("external_deadline") else 0,
                        t.get("due_at"),
                        created,
                        updated,
                    ),
                )


def db_list_tasks(
    status: Optional[str] = None,
    target_agent: Optional[str] = None,
    repo: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    conn: Optional[sqlite3.Connection] = None,
) -> List[Dict[str, Any]]:
    c = conn or get_db()
    query = "SELECT * FROM tasks WHERE 1=1"
    params: list = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if target_agent and target_agent != "any":
        query += " AND target_agent = ?"
        params.append(target_agent)
    if repo:
        query += " AND repo = ?"
        params.append(repo)
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with _DB_LOCK:
        rows = c.execute(query, params).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        if d.get("labels"):
            try:
                d["labels"] = json.loads(d["labels"])
            except Exception:
                pass
        if d.get("urls"):
            try:
                d["urls"] = json.loads(d["urls"])
            except Exception:
                pass
        d["external_deadline"] = bool(d.get("external_deadline"))
        result.append(d)
    return result


def db_get_task(task_id: str, conn: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
    c = conn or get_db()
    with _DB_LOCK:
        row = c.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    if d.get("labels"):
        try:
            d["labels"] = json.loads(d["labels"])
        except Exception:
            pass
    if d.get("urls"):
        try:
            d["urls"] = json.loads(d["urls"])
        except Exception:
            pass
    d["external_deadline"] = bool(d.get("external_deadline"))
    return d


def db_create_task(task: Dict[str, Any], conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    c = conn or get_db()
    task_id = str(task.get("id") or f"task-{uuid.uuid4().hex[:8]}")
    created = str(task.get("created") or now_iso())
    updated = str(task.get("updated") or created)
    labels = json.dumps(task.get("labels")) if task.get("labels") is not None else None
    urls = json.dumps(task.get("urls")) if task.get("urls") is not None else None

    with _DB_LOCK:
        with c:
            c.execute(
                """
                INSERT INTO tasks (
                    id, title, repo, type, target_agent, priority, budget_cost, status,
                    labels, urls, context, predicate, receipt_target, origin, horizon,
                    value_case, owner_surface, external_deadline, due_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    str(task.get("title", "")),
                    task.get("repo"),
                    task.get("type", "code"),
                    task.get("target_agent", "jules"),
                    task.get("priority", "medium"),
                    int(task.get("budget_cost", 1)),
                    str(task.get("status", "open")),
                    labels,
                    urls,
                    task.get("context"),
                    task.get("predicate"),
                    task.get("receipt_target"),
                    task.get("origin"),
                    task.get("horizon"),
                    task.get("value_case"),
                    task.get("owner_surface"),
                    1 if task.get("external_deadline") else 0,
                    task.get("due_at"),
                    created,
                    updated,
                ),
            )
            # Create timeline event for task creation
            c.execute(
                """
                INSERT INTO timelines (id, task_id, event_type, payload, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    f"evt-{uuid.uuid4().hex[:8]}",
                    task_id,
                    "task.created",
                    json.dumps({"status": task.get("status", "open"), "title": task.get("title")}),
                    created,
                ),
            )

    return db_get_task(task_id, c)  # type: ignore


ALLOWED_TASK_COLUMNS = {
    "title", "repo", "type", "target_agent", "priority", "budget_cost",
    "status", "labels", "urls", "context", "predicate", "receipt_target",
    "origin", "horizon", "value_case", "owner_surface", "external_deadline", "due_at"
}


def db_update_task(task_id: str, updates: Dict[str, Any], conn: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
    c = conn or get_db()
    existing = db_get_task(task_id, c)
    if not existing:
        return None

    updated_at = now_iso()
    fields = []
    params = []
    for k, v in updates.items():
        if k not in ALLOWED_TASK_COLUMNS:
            continue
        if k in ("labels", "urls") and isinstance(v, list):
            v = json.dumps(v)
        elif k == "external_deadline":
            v = 1 if v else 0
        fields.append(f"{k} = ?")
        params.append(v)

    if not fields and "status" not in updates:
        return existing

    fields.append("updated_at = ?")
    params.append(updated_at)
    params.append(task_id)

    with _DB_LOCK:
        with c:
            c.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", params)
            if "status" in updates:
                c.execute(
                    """
                    INSERT INTO timelines (id, task_id, event_type, payload, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        f"evt-{uuid.uuid4().hex[:8]}",
                        task_id,
                        f"task.{updates['status']}",
                        json.dumps(updates),
                        updated_at,
                    ),
                )

    return db_get_task(task_id, c)


# --- Decisions Queries ---

def db_list_decisions(
    task_id: Optional[str] = None,
    limit: int = 50,
    conn: Optional[sqlite3.Connection] = None,
) -> List[Dict[str, Any]]:
    c = conn or get_db()
    query = "SELECT * FROM decisions WHERE 1=1"
    params: list = []
    if task_id:
        query += " AND task_id = ?"
        params.append(task_id)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    with _DB_LOCK:
        rows = c.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def db_create_decision(decision: Dict[str, Any], conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    c = conn or get_db()
    decision_id = str(decision.get("id") or f"dec-{uuid.uuid4().hex[:8]}")
    created_at = str(decision.get("created_at") or now_iso())

    with _DB_LOCK:
        with c:
            c.execute(
                """
                INSERT INTO decisions (id, task_id, title, status, reasoning, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    decision_id,
                    decision.get("task_id"),
                    str(decision.get("title", "")),
                    str(decision.get("status", "proposed")),
                    decision.get("reasoning"),
                    created_at,
                ),
            )
    return {"id": decision_id, "task_id": decision.get("task_id"), "title": decision.get("title"), "status": decision.get("status"), "reasoning": decision.get("reasoning"), "created_at": created_at}


# --- Timelines Queries ---

def db_list_timelines(
    task_id: Optional[str] = None,
    limit: int = 50,
    conn: Optional[sqlite3.Connection] = None,
) -> List[Dict[str, Any]]:
    c = conn or get_db()
    query = "SELECT * FROM timelines WHERE 1=1"
    params: list = []
    if task_id:
        query += " AND task_id = ?"
        params.append(task_id)
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    with _DB_LOCK:
        rows = c.execute(query, params).fetchall()
    res = []
    for r in rows:
        d = dict(r)
        if d.get("payload"):
            try:
                d["payload"] = json.loads(d["payload"])
            except Exception:
                pass
        res.append(d)
    return res


def db_create_timeline(timeline: Dict[str, Any], conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    c = conn or get_db()
    evt_id = str(timeline.get("id") or f"evt-{uuid.uuid4().hex[:8]}")
    ts = str(timeline.get("timestamp") or now_iso())
    payload = json.dumps(timeline.get("payload")) if isinstance(timeline.get("payload"), (dict, list)) else timeline.get("payload")

    with _DB_LOCK:
        with c:
            c.execute(
                """
                INSERT INTO timelines (id, task_id, event_type, payload, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    evt_id,
                    timeline.get("task_id"),
                    str(timeline.get("event_type", "custom")),
                    payload,
                    ts,
                ),
            )
    return {"id": evt_id, "task_id": timeline.get("task_id"), "event_type": timeline.get("event_type"), "payload": timeline.get("payload"), "timestamp": ts}


# --- Users and SCIM Queries ---

def db_list_users(
    user_name: Optional[str] = None,
    external_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    conn: Optional[sqlite3.Connection] = None,
) -> List[Dict[str, Any]]:
    c = conn or get_db()
    query = "SELECT * FROM users WHERE 1=1"
    params: list = []
    if user_name:
        query += " AND user_name = ?"
        params.append(user_name)
    if external_id:
        query += " AND external_id = ?"
        params.append(external_id)
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with _DB_LOCK:
        rows = c.execute(query, params).fetchall()
        res = []
        for r in rows:
            d = dict(r)
            d["active"] = bool(d["active"])
            roles_rows = c.execute("SELECT role FROM user_roles WHERE user_id = ?", (d["id"],)).fetchall()
            d["roles"] = [rr["role"] for rr in roles_rows]
            res.append(d)
    return res


def db_get_user(user_id: str, conn: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
    c = conn or get_db()
    with _DB_LOCK:
        row = c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["active"] = bool(d["active"])
        roles_rows = c.execute("SELECT role FROM user_roles WHERE user_id = ?", (d["id"],)).fetchall()
        d["roles"] = [rr["role"] for rr in roles_rows]
        return d


def db_create_user(user: Dict[str, Any], conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    c = conn or get_db()
    user_id = str(user.get("id") or f"usr-{uuid.uuid4().hex[:8]}")
    created_at = now_iso()
    updated_at = created_at

    with _DB_LOCK:
        with c:
            c.execute(
                """
                INSERT INTO users (id, external_id, user_name, name, email, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    user.get("external_id"),
                    str(user.get("user_name")),
                    user.get("name"),
                    user.get("email"),
                    1 if user.get("active", True) else 0,
                    created_at,
                    updated_at,
                ),
            )
            for role in user.get("roles", ["client"]):
                c.execute(
                    "INSERT INTO user_roles (id, user_id, role, created_at) VALUES (?, ?, ?, ?)",
                    (f"ur-{uuid.uuid4().hex[:8]}", user_id, role, created_at),
                )

    return db_get_user(user_id, c)  # type: ignore


def db_update_user(user_id: str, updates: Dict[str, Any], conn: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
    c = conn or get_db()
    existing = db_get_user(user_id, c)
    if not existing:
        return None

    updated_at = now_iso()
    fields = []
    params = []
    for k in ("name", "email", "active", "external_id", "user_name"):
        if k in updates:
            val = updates[k]
            if k == "active":
                val = 1 if val else 0
            fields.append(f"{k} = ?")
            params.append(val)

    with _DB_LOCK:
        if fields:
            fields.append("updated_at = ?")
            params.append(updated_at)
            params.append(user_id)
            with c:
                c.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", params)

        if "roles" in updates and isinstance(updates["roles"], list):
            with c:
                c.execute("DELETE FROM user_roles WHERE user_id = ?", (user_id,))
                for role in updates["roles"]:
                    c.execute(
                        "INSERT INTO user_roles (id, user_id, role, created_at) VALUES (?, ?, ?, ?)",
                        (f"ur-{uuid.uuid4().hex[:8]}", user_id, role, updated_at),
                    )

    return db_get_user(user_id, c)


def db_deactivate_user(user_id: str, conn: Optional[sqlite3.Connection] = None) -> bool:
    c = conn or get_db()
    existing = db_get_user(user_id, c)
    if not existing:
        return False
    db_update_user(user_id, {"active": False}, c)
    return True


# --- Outbox & Webhooks Queries ---

def db_create_outbox_event(
    event_type: str,
    payload: Any,
    target_url: Optional[str] = None,
    signature: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, Any]:
    c = conn or get_db()
    evt_id = f"outbox-{uuid.uuid4().hex[:8]}"
    payload_str = json.dumps(payload) if isinstance(payload, (dict, list)) else str(payload)
    created_at = now_iso()

    with _DB_LOCK:
        with c:
            c.execute(
                """
                INSERT INTO outbox_events (id, target_url, event_type, payload, signature, status, attempts, created_at)
                VALUES (?, ?, ?, ?, ?, 'pending', 0, ?)
                """,
                (evt_id, target_url, event_type, payload_str, signature, created_at),
            )
    return {"id": evt_id, "target_url": target_url, "event_type": event_type, "payload": payload_str, "signature": signature, "status": "pending", "attempts": 0, "created_at": created_at}


def db_list_outbox_events(status: str = "pending", limit: int = 50, conn: Optional[sqlite3.Connection] = None) -> List[Dict[str, Any]]:
    c = conn or get_db()
    with _DB_LOCK:
        rows = c.execute("SELECT * FROM outbox_events WHERE status = ? ORDER BY created_at ASC LIMIT ?", (status, limit)).fetchall()
    return [dict(r) for r in rows]


# --- SCIM Groups Queries ---

def db_list_groups(
    display_name: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    conn: Optional[sqlite3.Connection] = None,
) -> List[Dict[str, Any]]:
    c = conn or get_db()
    query = "SELECT * FROM groups WHERE 1=1"
    params: list = []
    if display_name:
        query += " AND display_name = ?"
        params.append(display_name)
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with _DB_LOCK:
        rows = c.execute(query, params).fetchall()
        res = []
        for r in rows:
            d = dict(r)
            members_rows = c.execute(
                """
                SELECT gm.user_id, u.user_name
                FROM group_members gm
                LEFT JOIN users u ON gm.user_id = u.id
                WHERE gm.group_id = ?
                """,
                (d["id"],),
            ).fetchall()
            d["members"] = [
                {"value": mr["user_id"], "display": mr["user_name"] or mr["user_id"]}
                for mr in members_rows
            ]
            res.append(d)
    return res


def db_get_group(group_id: str, conn: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
    c = conn or get_db()
    with _DB_LOCK:
        row = c.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        members_rows = c.execute(
            """
            SELECT gm.user_id, u.user_name
            FROM group_members gm
            LEFT JOIN users u ON gm.user_id = u.id
            WHERE gm.group_id = ?
            """,
            (d["id"],),
        ).fetchall()
        d["members"] = [
            {"value": mr["user_id"], "display": mr["user_name"] or mr["user_id"]}
            for mr in members_rows
        ]
        return d


def db_create_group(group: Dict[str, Any], conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    c = conn or get_db()
    group_id = str(group.get("id") or f"grp-{uuid.uuid4().hex[:8]}")
    display_name = str(group.get("displayName") or group.get("display_name") or "")
    created_at = now_iso()
    updated_at = created_at

    with _DB_LOCK:
        with c:
            c.execute(
                "INSERT INTO groups (id, display_name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (group_id, display_name, created_at, updated_at),
            )
            members = group.get("members") or []
            for m in members:
                u_id = m.get("value") if isinstance(m, dict) else str(m)
                if u_id:
                    c.execute(
                        "INSERT INTO group_members (id, group_id, user_id, created_at) VALUES (?, ?, ?, ?)",
                        (f"gm-{uuid.uuid4().hex[:8]}", group_id, u_id, created_at),
                    )

    return db_get_group(group_id, c)  # type: ignore


def db_delete_group(group_id: str, conn: Optional[sqlite3.Connection] = None) -> bool:
    c = conn or get_db()
    existing = db_get_group(group_id, c)
    if not existing:
        return False
    with _DB_LOCK:
        with c:
            c.execute("DELETE FROM group_members WHERE group_id = ?", (group_id,))
            c.execute("DELETE FROM groups WHERE id = ?", (group_id,))
    return True


# --- Idempotency Key Persistence ---

def db_check_and_register_idempotency_key(key: str, conn: Optional[sqlite3.Connection] = None) -> bool:
    c = conn or get_db()
    try:
        with _DB_LOCK:
            with c:
                c.execute(
                    "INSERT INTO idempotency_keys (key, created_at) VALUES (?, ?)",
                    (key, now_iso()),
                )
        return True
    except sqlite3.IntegrityError:
        return False

