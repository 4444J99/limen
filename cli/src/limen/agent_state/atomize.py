"""Deterministic, bounded-memory atomization of vendor state."""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import SourceProof

AtomEmitter = Callable[[dict[str, Any], bytes], None]


@dataclass(frozen=True)
class AtomizationResult:
    source: SourceProof
    atom_count: int
    logical_sha256: str
    duplicate_payloads: int
    table_counts: dict[str, int]


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def encode_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"$bytes_b64": base64.b64encode(value).decode("ascii")}
    return value


def decode_value(value: Any) -> Any:
    if isinstance(value, dict) and set(value) == {"$bytes_b64"}:
        return base64.b64decode(value["$bytes_b64"])
    return value


def sha256_file(path: Path, *, block_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def stat_identity(path: Path) -> tuple[int, int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, stat.st_ino


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _tables(connection: sqlite3.Connection) -> list[tuple[str, str]]:
    rows = connection.execute(
        "SELECT name, sql FROM sqlite_schema WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [(str(name), str(sql or "")) for name, sql in rows]


def _columns(connection: sqlite3.Connection, table: str) -> list[tuple[str, int]]:
    rows = connection.execute(f"PRAGMA table_info({quote_identifier(table)})")
    return [(str(row[1]), int(row[5])) for row in rows]


def _rows(connection: sqlite3.Connection, table: str, columns: list[tuple[str, int]]) -> Iterator[tuple[Any, ...]]:
    names = [name for name, _pk in columns]
    selected = ", ".join(quote_identifier(name) for name in names)
    primary = [name for name, pk in sorted(columns, key=lambda item: item[1]) if pk]
    order = ", ".join(quote_identifier(name) for name in primary)
    query = f"SELECT {selected} FROM {quote_identifier(table)}"
    if order:
        query += f" ORDER BY {order}"
    else:
        try:
            yield from connection.execute(query + " ORDER BY rowid")
            return
        except sqlite3.OperationalError:
            pass
    yield from connection.execute(query)


class LogicalEmitter:
    """Attach atom identities and compute one ordered logical digest."""

    def __init__(self, sink: AtomEmitter):
        self._sink = sink
        self._digest = hashlib.sha256()
        self.count = 0

    @property
    def hexdigest(self) -> str:
        return self._digest.hexdigest()

    def emit(self, record: dict[str, Any]) -> None:
        body = canonical_bytes(record)
        atom_sha256 = hashlib.sha256(body).hexdigest()
        envelope = {"atom_sha256": atom_sha256, "record": record}
        line = canonical_bytes(envelope) + b"\n"
        self._digest.update(line)
        self.count += 1
        self._sink(envelope, line)


def atomize_opencode(
    source: Path,
    sink: AtomEmitter,
    *,
    spill_dir: Path | None = None,
    hash_source: bool = True,
) -> AtomizationResult:
    """Stream a consistent SQLite snapshot without copying the database.

    Event payloads are emitted once as content-addressed atoms. Event rows retain
    exact ordering and reference the payload digest, so restoration is lossless.
    The source must have an unchanged stat identity across capture and hashing.
    """

    source = source.expanduser().resolve()
    before = stat_identity(source)
    emitter = LogicalEmitter(sink)
    table_counts: dict[str, int] = {}
    duplicates = 0
    temp_parent = str(spill_dir.expanduser().resolve()) if spill_dir else None
    with tempfile.TemporaryDirectory(prefix="limen-agent-state-", dir=temp_parent) as temporary:
        seen = sqlite3.connect(str(Path(temporary) / "event-payloads.sqlite3"))
        seen.execute("PRAGMA journal_mode=OFF")
        seen.execute("PRAGMA synchronous=OFF")
        seen.execute("CREATE TABLE payload (sha256 TEXT PRIMARY KEY) WITHOUT ROWID")
        uri = f"file:{source}?mode=ro&immutable=0"
        with sqlite3.connect(uri, uri=True) as connection:
            connection.execute("PRAGMA query_only=ON")
            connection.execute("BEGIN")
            for table, create_sql in _tables(connection):
                columns = _columns(connection, table)
                names = [name for name, _pk in columns]
                emitter.emit(
                    {
                        "kind": "sqlite_schema",
                        "table": table,
                        "columns": names,
                        "create_sql": create_sql,
                    }
                )
                count = 0
                data_index = names.index("data") if table == "event" and "data" in names else None
                for row in _rows(connection, table, columns):
                    values = [encode_value(value) for value in row]
                    if data_index is not None:
                        payload = values[data_index]
                        payload_body = canonical_bytes(payload)
                        payload_sha = hashlib.sha256(b"opencode:event-payload:v1\0" + payload_body).hexdigest()
                        inserted = seen.execute(
                            "INSERT OR IGNORE INTO payload (sha256) VALUES (?)", (payload_sha,)
                        ).rowcount
                        if inserted:
                            emitter.emit(
                                {
                                    "kind": "event_payload",
                                    "payload_sha256": payload_sha,
                                    "value": payload,
                                }
                            )
                        else:
                            duplicates += 1
                        values[data_index] = {"$event_payload": payload_sha}
                    emitter.emit({"kind": "sqlite_row", "table": table, "values": values})
                    count += 1
                table_counts[table] = count
            connection.rollback()
        seen.close()
    source_sha256 = sha256_file(source) if hash_source else "not-computed"
    after = stat_identity(source)
    proof = SourceProof(
        path=str(source),
        kind="opencode-sqlite",
        bytes=after[0],
        sha256=source_sha256,
        stat_before=before,
        stat_after=after,
    )
    return AtomizationResult(
        source=proof,
        atom_count=emitter.count,
        logical_sha256=emitter.hexdigest,
        duplicate_payloads=duplicates,
        table_counts=table_counts,
    )
