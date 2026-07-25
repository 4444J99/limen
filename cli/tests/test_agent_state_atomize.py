from __future__ import annotations

import sqlite3
from pathlib import Path

from limen.agent_state.atomize import atomize_opencode, decode_value


def _database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE session (id TEXT PRIMARY KEY, title TEXT NOT NULL);
            CREATE TABLE event (
              id TEXT PRIMARY KEY,
              aggregate_id TEXT NOT NULL,
              seq INTEGER NOT NULL,
              type TEXT NOT NULL,
              data TEXT NOT NULL
            );
            INSERT INTO session VALUES ('s1', 'private title');
            INSERT INTO event VALUES ('e1', 's1', 1, 'message', '{"same":true}');
            INSERT INTO event VALUES ('e2', 's1', 2, 'message', '{"same":true}');
            INSERT INTO event VALUES ('e3', 's1', 3, 'message', '{"other":true}');
            """
        )


def test_opencode_atomization_deduplicates_event_payloads(tmp_path: Path) -> None:
    source = tmp_path / "opencode.db"
    _database(source)
    envelopes: list[dict[str, object]] = []
    result = atomize_opencode(source, lambda envelope, _line: envelopes.append(envelope))

    records = [envelope["record"] for envelope in envelopes]
    payloads = [record for record in records if record["kind"] == "event_payload"]
    event_rows = [record for record in records if record["kind"] == "sqlite_row" and record["table"] == "event"]
    assert len(payloads) == 2
    assert len(event_rows) == 3
    assert result.duplicate_payloads == 1
    assert result.table_counts == {"event": 3, "session": 1}
    assert result.source.stable
    assert len(result.source.sha256) == 64
    assert len(result.logical_sha256) == 64
    assert event_rows[0]["values"][-1]["$event_payload"] == event_rows[1]["values"][-1]["$event_payload"]


def test_binary_sqlite_values_round_trip(tmp_path: Path) -> None:
    source = tmp_path / "opencode.db"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE blob_data (id INTEGER PRIMARY KEY, value BLOB)")
        connection.execute("INSERT INTO blob_data VALUES (1, ?)", (b"\x00\xffprivate",))
    records: list[dict[str, object]] = []
    atomize_opencode(source, lambda envelope, _line: records.append(envelope["record"]))
    row = next(record for record in records if record["kind"] == "sqlite_row")
    assert decode_value(row["values"][1]) == b"\x00\xffprivate"


def test_source_mutation_is_visible_in_proof(tmp_path: Path) -> None:
    source = tmp_path / "opencode.db"
    _database(source)
    mutated = False

    def sink(_envelope: dict[str, object], _line: bytes) -> None:
        nonlocal mutated
        if not mutated:
            source.touch()
            mutated = True

    result = atomize_opencode(source, sink, hash_source=False)
    assert not result.source.stable
