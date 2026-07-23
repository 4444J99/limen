"""Read-only native session-corpus adapters used by agent-neutral fanout.

The adapters normalize only the small role/content/timestamp envelope needed by
the fanout planner.  Raw transcript bodies remain in their native stores.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PRIMARY_SESSION_AGENTS = frozenset({"agy", "claude", "codex", "copilot", "opencode"})


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
                row = db.execute(
                    "SELECT id, time_updated FROM session ORDER BY time_updated DESC, id DESC LIMIT 1"
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
        "opencode": _sqlite_latest(home / ".local" / "share" / "opencode" / "opencode.db", "opencode"),
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
    path = Path(source.locator.split("#", 1)[0])
    records: list[dict[str, Any]] = []
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            rows = db.execute(
                "SELECT m.id, m.data, p.data "
                "FROM message AS m LEFT JOIN part AS p ON p.message_id = m.id "
                "WHERE m.session_id = ? ORDER BY m.time_created, m.id, p.time_created, p.id",
                (source.session_id,),
            ).fetchall()
    except sqlite3.Error:
        return records
    grouped: dict[str, dict[str, Any]] = {}
    for message_id, message_raw, part_raw in rows:
        try:
            message = json.loads(message_raw)
        except (TypeError, json.JSONDecodeError):
            message = {}
        record = grouped.setdefault(
            str(message_id),
            {
                "timestamp": (message.get("time") or {}).get("created"),
                "role": message.get("role"),
                "content": [],
            },
        )
        try:
            part = json.loads(part_raw) if part_raw else {}
        except (TypeError, json.JSONDecodeError):
            part = {}
        record["content"].extend(_content_text(part))
    records.extend(grouped.values())
    return records


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
