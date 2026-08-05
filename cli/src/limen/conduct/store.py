"""Transactional local state stores used by the deterministic conduct kernel."""

from __future__ import annotations

import copy
import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Protocol


def empty_state() -> dict[str, Any]:
    return {
        "schema_version": "limen.conduct_state.v1",
        "sessions": {},
        "session_principals": {},
        "runs": {},
        "leases": {},
        "work_index": {},
        "work_key_index": {},
        "receipt_index": {},
        "resource_generations": {},
        "local_board_projection": None,
        "next_generation": 0,
        "events": [],
    }


class StateStore(Protocol):
    @contextmanager
    def transaction(self) -> Iterator[dict[str, Any]]: ...


class MemoryStateStore:
    """Thread-safe test/local store with commit-on-success semantics."""

    def __init__(self, state: dict[str, Any] | None = None):
        self._state = copy.deepcopy(state or empty_state())
        self._lock = threading.RLock()

    @contextmanager
    def transaction(self) -> Iterator[dict[str, Any]]:
        with self._lock:
            working = copy.deepcopy(self._state)
            yield working
            self._state = working

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._state)


class SQLiteStateStore:
    """One-row SQLite event/graph projection with an atomic BEGIN IMMEDIATE keeper lock."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS conduct_state ("
                "id INTEGER PRIMARY KEY CHECK (id = 1), document TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT OR IGNORE INTO conduct_state (id, document) VALUES (1, ?)",
                (json.dumps(empty_state(), sort_keys=True),),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[dict[str, Any]]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT document FROM conduct_state WHERE id = 1").fetchone()
            state = json.loads(row[0]) if row else empty_state()
            yield state
            encoded = json.dumps(state, sort_keys=True, separators=(",", ":"))
            connection.execute("UPDATE conduct_state SET document = ? WHERE id = 1", (encoded,))
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def snapshot(self) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT document FROM conduct_state WHERE id = 1").fetchone()
        return json.loads(row[0]) if row else empty_state()
