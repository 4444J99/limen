"""Fixture-backed idempotency tests for the private channel capture owner."""

import importlib.util
import json
import sqlite3
from pathlib import Path


def _module():
    path = Path(__file__).parents[1] / "capture-threads.py"
    spec = importlib.util.spec_from_file_location("capture_threads", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(seq: int) -> dict:
    return {
        "seq": seq,
        "ts": {"utc": f"2026-08-03 12:00:{seq:02d}", "et": "2026-08-03 08:00:00 EDT"},
        "direction": "received",
        "kind": "message",
        "text": f"fixture {seq}",
        "attachment_hashes": [],
    }


def _chatdb(tmp_path: Path) -> str:
    """A minimal chat.db in the shape macOS actually writes it.

    The load-bearing detail: a SENT message carries handle_id = 0 and is tied to the counterparty
    only through chat_message_join -> chat. A capture that joins message -> handle therefore keeps
    every received message and silently drops the sent side, producing a tape that reads as
    complete while holding one half of the conversation.
    """
    path = tmp_path / "chat.db"
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE handle (ROWID INTEGER PRIMARY KEY, id TEXT);
        CREATE TABLE chat (ROWID INTEGER PRIMARY KEY, chat_identifier TEXT);
        CREATE TABLE chat_message_join (chat_id INTEGER, message_id INTEGER);
        CREATE TABLE message (
            ROWID INTEGER PRIMARY KEY, date INTEGER, is_from_me INTEGER, text TEXT,
            attributedBody BLOB, associated_message_type INTEGER,
            cache_has_attachments INTEGER, handle_id INTEGER
        );
        INSERT INTO handle VALUES (7, '+15550001111');
        INSERT INTO chat  VALUES (3, '+15550001111');
        -- received: handle_id points at the counterparty AND it is in the chat
        INSERT INTO message VALUES (100, 1000000000, 0, 'from them', NULL, 0, 0, 7);
        -- sent: handle_id = 0 -- reachable ONLY through the chat join
        INSERT INTO message VALUES (101, 2000000000, 1, 'from me',   NULL, 0, 0, 0);
        -- orphan: attached to the handle but in NO chat -- reachable ONLY through the handle join
        INSERT INTO message VALUES (102, 3000000000, 0, 'orphan',    NULL, 0, 0, 7);
        INSERT INTO chat_message_join VALUES (3, 100), (3, 101);
        """
    )
    db.commit()
    db.close()
    return str(path)


def test_capture_imessage_keeps_sent_messages_and_orphans(tmp_path):
    """Regression: the tape must hold BOTH sides plus chat-less orphans.

    Guards a real defect -- on one 66,427-row thread the handle-only join returned 34,638 rows,
    missing 31,789, of which 31,745 were sent.
    """
    module = _module()
    rows = module.capture_imessage(_chatdb(tmp_path), ["+15550001111"])

    by_seq = {r["seq"]: r for r in rows}
    assert set(by_seq) == {100, 101, 102}, "sent messages and orphans must both survive capture"
    assert by_seq[101]["direction"] == "sent"
    assert by_seq[101]["text"] == "from me"
    # every row is attributed to the counterparty even when handle_id was 0
    assert {r["handle"] for r in rows} == {"+15550001111"}
    # a message in several chats must not fan out into duplicate rows
    assert len(rows) == len(by_seq)
    assert [r["seq"] for r in rows] == [100, 101, 102], "rows stay in date order"


def test_normalized_observation_has_stable_private_id_and_receipt():
    module = _module()
    first = module.normalize_observations([_row(1)], person="fixture", channel="imessage")
    second = module.normalize_observations([_row(1)], person="fixture", channel="imessage")

    assert first[0]["source_message_id"] == second[0]["source_message_id"]
    assert first[0]["observation_receipt"] == {
        "schema": "limen.interaction_event.v1",
        "source": "imessage",
        "source_message_id": first[0]["source_message_id"],
        "state": "observed",
    }


def test_append_jsonl_is_idempotent_and_checkpoint_is_atomic(tmp_path):
    module = _module()
    tape = tmp_path / "imessage.jsonl"
    rows = module.normalize_observations([_row(1), _row(2)], person="fixture", channel="imessage")

    assert module.append_jsonl(str(tape), rows, person="fixture", channel="imessage") == 2
    assert module.append_jsonl(str(tape), rows, person="fixture", channel="imessage") == 0
    assert len(tape.read_text().splitlines()) == 2

    module.write_checkpoint(str(tmp_path), "fixture", "imessage", rows, appended=0)
    checkpoint = json.loads((tmp_path / "fixture" / "tape" / ".checkpoints" / "imessage.json").read_text())
    assert checkpoint["schema"] == "limen.capture_checkpoint.v1"
    assert checkpoint["last_source_message_id"] == rows[-1]["source_message_id"]
