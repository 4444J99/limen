"""Read-only native session-corpus adapters used by agent-neutral fanout.

The adapters normalize only the small role/content/timestamp envelope needed by
the fanout planner.  Raw transcript bodies remain in their native stores.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

PRIMARY_SESSION_AGENTS = frozenset({"agy", "claude", "codex", "copilot", "opencode"})


def resolve_opencode_db(home: Path | None = None, env: Mapping[str, str] | None = None) -> Path:
    """Return the live OpenCode database path.

    OpenCode keeps its data root inside the shared agent runtime, so the live store is
    ``<runtime>/opencode/data/opencode/opencode.db``; ``~/.local/share/opencode`` is a symlink to a frozen
    ``legacy-share`` copy. A reader pinned to the legacy path measures a different, far smaller database and
    reports it as the real one. Order: explicit ``LIMEN_OPENCODE_DB``, the runtime store, then the legacy home
    path (returned even when absent so callers report it as missing, never as empty).

    An explicit ``home`` makes the result a pure function of that tree: the process environment is consulted
    only when neither ``home`` nor ``env`` is given, so a test with a fake home can never reach the real store.
    """

    env = os.environ if (env is None and home is None) else (env or {})
    home = (home or Path.home()).expanduser()
    explicit = env.get("LIMEN_OPENCODE_DB")
    if explicit:
        return Path(explicit).expanduser()
    runtime = Path(env.get("LIMEN_AGENT_RUNTIME_ROOT") or home / "Workspace" / "limen" / ".agent-runtime").expanduser()
    live = runtime / "opencode" / "data" / "opencode" / "opencode.db"
    if live.is_file():
        return live
    return home / ".local" / "share" / "opencode" / "opencode.db"


OPENCODE_V2_TABLES = frozenset({"session_v2", "session_message"})


def opencode_session_table(db: sqlite3.Connection) -> str:
    """Return the table holding every session of this OpenCode store.

    OpenCode 2.x moved sessions to ``session_v2`` / ``session_message`` on 2026-10-01 and froze the legacy
    ``session`` / ``message`` / ``part`` tables. ``session_v2`` is a strict superset of ``session`` (the same ids
    plus every session since the freeze), so a reader on a v2 store that queries ``session`` silently drops recent
    work. Stores without both v2 tables (older copies, fixtures) keep the legacy table.
    """

    return "session_v2" if OPENCODE_V2_TABLES <= _opencode_table_names(db) else "session"


def _opencode_table_names(db: sqlite3.Connection) -> set[str]:
    return {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def opencode_has_legacy_messages(db: sqlite3.Connection) -> bool:
    """Whether the frozen ``message`` / ``part`` tables are still present in this store."""

    return {"message", "part"} <= _opencode_table_names(db)


@dataclass(frozen=True)
class SessionSource:
    agent: str
    locator: str
    session_id: str
    format: str
    updated_ns: int


def _latest_jsonl(root: Path, *, exclude_parts: frozenset[str] = frozenset()) -> SessionSource | None:
    if not root.is_dir():
        return None
    candidates: list[Path] = []
    try:
        for path in root.rglob("*.jsonl"):
            if path.is_file() and not exclude_parts.intersection(path.parts):
                candidates.append(path)
    except OSError:
        return None
    if not candidates:
        return None
    path = max(candidates, key=lambda item: item.stat().st_mtime_ns)
    return SessionSource("", str(path), path.stem, "jsonl", path.stat().st_mtime_ns)


def _sqlite_latest(path: Path, agent: str) -> SessionSource | None:
    if not path.is_file():
        return None
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            if agent == "opencode":
                table = opencode_session_table(db)  # a constant from the helper above, never user input
                row = db.execute(
                    f"SELECT id, time_updated FROM {table} ORDER BY time_updated DESC, id DESC LIMIT 1"
                ).fetchone()
                if row:
                    return SessionSource(
                        agent,
                        f"{path}#session:{row[0]}",
                        str(row[0]),
                        "opencode-sqlite",
                        int(row[1]) * 1_000_000,
                    )
            if agent == "agy":
                row = db.execute(
                    "SELECT conversation_id, CAST(strftime('%s', last_modified_time) AS INTEGER) "
                    "FROM conversation_summaries "
                    "ORDER BY last_modified_time DESC, conversation_id DESC LIMIT 1"
                ).fetchone()
                if row:
                    return SessionSource(
                        agent,
                        f"{path}#conversation:{row[0]}",
                        str(row[0]),
                        "agy-sqlite",
                        int(row[1] or 0) * 1_000_000_000,
                    )
    except (OSError, sqlite3.Error):
        return None
    return None


def discover_sources(home: Path | None = None) -> dict[str, SessionSource | None]:
    """Return the newest native session for each primary interactive agent."""

    explicit_home = home
    home = (home or Path.home()).expanduser()
    codex = _latest_jsonl(home / ".codex" / "sessions")
    claude = _latest_jsonl(home / ".claude" / "projects", exclude_parts=frozenset({"subagents"}))
    copilot = _latest_jsonl(home / ".copilot" / "session-state")
    return {
        "codex": None
        if codex is None
        else SessionSource("codex", codex.locator, codex.session_id, codex.format, codex.updated_ns),
        "claude": (
            None
            if claude is None
            else SessionSource("claude", claude.locator, claude.session_id, claude.format, claude.updated_ns)
        ),
        "copilot": (
            None
            if copilot is None
            else SessionSource("copilot", copilot.locator, copilot.session_id, copilot.format, copilot.updated_ns)
        ),
        "agy": _sqlite_latest(home / ".gemini" / "antigravity-cli" / "conversation_summaries.db", "agy"),
        "opencode": _sqlite_latest(resolve_opencode_db(explicit_home), "opencode"),
    }


def infer_agent(locator: str) -> str | None:
    parts = Path(locator.split("#", 1)[0]).expanduser().parts
    markers = {
        ".codex": "codex",
        ".claude": "claude",
        ".copilot": "copilot",
        "antigravity-cli": "agy",
        "opencode": "opencode",
    }
    for part in parts:
        if part in markers:
            return markers[part]
    return None


def resolve_session(
    locator: str | None,
    *,
    source_agent: str = "auto",
    home: Path | None = None,
) -> SessionSource:
    """Resolve an explicit native locator or the newest corpus across agents."""

    sources = discover_sources(home)
    if source_agent != "auto" and source_agent not in PRIMARY_SESSION_AGENTS:
        raise ValueError(f"unsupported session source agent: {source_agent}")
    if locator:
        agent = source_agent if source_agent != "auto" else infer_agent(locator)
        if agent is None:
            raise ValueError("cannot infer session source; pass --source-agent")
        path_text, separator, fragment = locator.partition("#")
        path = Path(path_text).expanduser()
        if not path.exists():
            raise FileNotFoundError(path)
        if agent == "opencode":
            session_id = fragment.removeprefix("session:") if separator else ""
            if not session_id:
                latest = _sqlite_latest(path, agent)
                if latest is None:
                    raise FileNotFoundError(f"no OpenCode session in {path}")
                return latest
            return SessionSource(
                agent, f"{path}#session:{session_id}", session_id, "opencode-sqlite", path.stat().st_mtime_ns
            )
        if agent == "agy":
            session_id = fragment.removeprefix("conversation:") if separator else ""
            if not session_id:
                latest = _sqlite_latest(path, agent)
                if latest is None:
                    raise FileNotFoundError(f"no Agy conversation in {path}")
                return latest
            return SessionSource(
                agent, f"{path}#conversation:{session_id}", session_id, "agy-sqlite", path.stat().st_mtime_ns
            )
        return SessionSource(agent, str(path), path.stem, "jsonl", path.stat().st_mtime_ns)
    if source_agent != "auto":
        selected = sources[source_agent]
        if selected is None:
            raise FileNotFoundError(f"no {source_agent} native session corpus found")
        return selected
    available = [source for source in sources.values() if source is not None]
    if not available:
        raise FileNotFoundError("no native session corpus found")
    return max(available, key=lambda item: item.updated_ns)


def _content_text(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [text for item in value for text in _content_text(item)]
    if isinstance(value, dict):
        return [
            text
            for key in ("text", "content", "message", "input", "transformedContent")
            if key in value
            for text in _content_text(value[key])
        ]
    return []


def _normalize_jsonl(agent: str, objects: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for obj in objects:
        if agent == "claude" and isinstance(obj.get("message"), dict):
            message = obj["message"]
            records.append(
                {
                    "timestamp": obj.get("timestamp"),
                    "role": message.get("role"),
                    "content": message.get("content"),
                }
            )
            continue
        if agent == "copilot" and isinstance(obj.get("data"), dict):
            data = obj["data"]
            records.append(
                {
                    "timestamp": data.get("timestamp") or data.get("time"),
                    "role": data.get("role"),
                    "content": data.get("content") or data.get("message"),
                }
            )
            continue
        records.append(obj)
    return records


def _read_jsonl(source: SessionSource) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    path = Path(source.locator)
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            value = json.loads(line)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            objects.append(value)
    return _normalize_jsonl(source.agent, objects)


def _read_opencode(source: SessionSource) -> list[dict[str, Any]]:
    """Keep legacy history authoritative and append only previously unavailable v2 turns."""

    path = Path(source.locator.split("#", 1)[0])
    rows: list[tuple[Any, ...]] = []
    tail: list[dict[str, Any]] = []
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            has_legacy = opencode_has_legacy_messages(db)
            if has_legacy:
                rows = db.execute(
                    "SELECT m.id, m.time_created, m.data, p.data "
                    "FROM message AS m LEFT JOIN part AS p ON p.message_id = m.id "
                    "WHERE m.session_id = ? ORDER BY m.time_created, m.id, p.time_created, p.id",
                    (source.session_id,),
                ).fetchall()
            if opencode_session_table(db) == "session_v2":
                if not rows:
                    # Metadata alone cannot stand in for missing message/part history.
                    tail = opencode_v2_turns(db, source.session_id)
                elif (
                    "session" not in _opencode_table_names(db)
                    or not db.execute("SELECT 1 FROM session WHERE id = ?", (source.session_id,)).fetchone()
                ):
                    # A partial store can retain messages without its session freeze marker.
                    tail = opencode_v2_turns(db, source.session_id, after=max(row[1] for row in rows))
                else:
                    tail = opencode_v2_tail(db, source.session_id)
    except sqlite3.Error:
        return []
    grouped: dict[str, dict[str, Any]] = {}
    for message_id, created, message_raw, part_raw in rows:
        try:
            message = json.loads(message_raw)
        except (TypeError, json.JSONDecodeError):
            message = {}
        if not isinstance(message, dict):
            message = {}
        time = message.get("time")
        timestamp = time.get("created") if isinstance(time, dict) else None
        record = grouped.setdefault(
            str(message_id),
            {
                "timestamp": created if timestamp is None else timestamp,
                "role": message.get("role"),
                "content": [],
            },
        )
        try:
            part = json.loads(part_raw) if part_raw else {}
        except (TypeError, json.JSONDecodeError):
            part = {}
        if isinstance(part, dict):
            record["content"].extend(_content_text(part))
    return list(grouped.values()) + [
        {"timestamp": turn["time_created"], "role": turn["role"], "content": _content_text(turn["parts"])}
        for turn in tail
    ]


def opencode_v2_turns(db: sqlite3.Connection, session_id: str, after: int | None = None) -> list[dict[str, Any]]:
    """The user and assistant turns of one ``session_v2`` session, in order, created after ``after`` (ms).

    Each turn is ``{"role", "time_created", "parts"}``. ``parts`` are dicts shaped like the legacy ``part`` rows
    (``{"type": "text", "text": ...}``; assistant ``text``/``reasoning``/``tool`` blocks as stored), so a reader
    written against ``message``/``part`` keeps its per-part logic. Other row types (``idle``, ``system``,
    ``compaction``, ``synthetic``, ...) are not turns and are not returned.
    """

    turns: list[dict[str, Any]] = []
    for kind, created, raw in db.execute(
        "SELECT type, time_created, data FROM session_message "
        "WHERE session_id = ? AND type IN ('user', 'assistant') AND time_created > ? ORDER BY seq, time_created, id",
        (session_id, -1 if after is None else after),
    ):
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        if kind == "user":
            text = data.get("text")
            parts = [{"type": "text", "text": text}] if isinstance(text, str) else []
        else:
            blocks = data.get("content")
            parts = [block for block in blocks if isinstance(block, dict)] if isinstance(blocks, list) else []
        turns.append({"role": kind, "time_created": created, "parts": parts})
    return turns


def opencode_v2_tail(db: sqlite3.Connection, session_id: str) -> list[dict[str, Any]]:
    """The v2 turns of a session that the frozen legacy tables do not already hold.

    The v2 migration is not lossless. Across the sessions both generations hold, the legacy ``message``/``part``
    rows still carry assistant text, reasoning, user-side synthetic text and ``patch`` parts that
    ``session_message`` lacks, and nothing exists only in v2 for them. So legacy rows stay authoritative for what
    they cover and v2 supplies the rest: every turn of a v2-only session, and the turns created after a migrated
    session's last legacy update.
    """

    cutoff = None
    if "session" in _opencode_table_names(db):
        row = db.execute("SELECT time_updated FROM session WHERE id = ?", (session_id,)).fetchone()
        cutoff = row[0] if row else None
    return opencode_v2_turns(db, session_id, after=cutoff)


def _read_agy(source: SessionSource) -> list[dict[str, Any]]:
    path = Path(source.locator.split("#", 1)[0])
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            row = db.execute(
                "SELECT title, preview, last_user_input_time FROM conversation_summaries WHERE conversation_id = ?",
                (source.session_id,),
            ).fetchone()
    except sqlite3.Error:
        return []
    if not row:
        return []
    text = "\n\n".join(item for item in (str(row[0] or ""), str(row[1] or "")) if item)
    return [{"timestamp": row[2], "role": "user", "content": text}]


def read_session_records(source: SessionSource) -> list[dict[str, Any]]:
    if source.format == "jsonl":
        return _read_jsonl(source)
    if source.format == "opencode-sqlite":
        return _read_opencode(source)
    if source.format == "agy-sqlite":
        return _read_agy(source)
    raise ValueError(f"unsupported session source format: {source.format}")


def child_identity_environment(
    *,
    executor_agent: str,
    initiator_agent: str,
    conductor_agent: str,
    root_run_id: str,
    parent_run_id: str,
    run_id: str,
    task_id: str | None = None,
    lease_id: str | None = None,
    lease_generation: int | None = None,
    execution_hash: str | None = None,
    capability_token: str | None = None,
) -> dict[str, str]:
    """Build a child identity envelope without inheriting the caller's lane."""

    environment = {
        "LIMEN_AGENT": executor_agent,
        "LIMEN_INITIATOR_AGENT": initiator_agent,
        "LIMEN_CONDUCTOR_AGENT": conductor_agent,
        "LIMEN_ROOT_RUN_ID": root_run_id,
        "LIMEN_PARENT_RUN_ID": parent_run_id,
        "LIMEN_RUN_ID": run_id,
    }
    optional = {
        "LIMEN_TASK_ID": task_id,
        "LIMEN_LEASE_ID": lease_id,
        "LIMEN_LEASE_GENERATION": (str(lease_generation) if lease_generation is not None else None),
        "LIMEN_EXECUTION_HASH": execution_hash,
        "LIMEN_LEASE_TOKEN": capability_token,
    }
    environment.update({key: value for key, value in optional.items() if value})
    return environment
