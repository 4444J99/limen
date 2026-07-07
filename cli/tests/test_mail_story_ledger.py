import importlib.util
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "mail-story-ledger.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("mail_story_ledger_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _ts(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, 12, 0, tzinfo=timezone.utc).timestamp())


def _mail_index(tmp_path: Path) -> Path:
    db = tmp_path / "Envelope Index"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE messages (
            ROWID INTEGER PRIMARY KEY,
            global_message_id INTEGER NOT NULL,
            conversation_id INTEGER NOT NULL,
            date_received INTEGER,
            flagged INTEGER NOT NULL DEFAULT 0,
            flag_color INTEGER,
            read INTEGER NOT NULL DEFAULT 0,
            deleted INTEGER NOT NULL DEFAULT 0,
            sender INTEGER,
            subject INTEGER,
            summary INTEGER,
            mailbox INTEGER
        );
        CREATE TABLE addresses (
            ROWID INTEGER PRIMARY KEY,
            address TEXT NOT NULL,
            comment TEXT NOT NULL
        );
        CREATE TABLE subjects (
            ROWID INTEGER PRIMARY KEY,
            subject TEXT NOT NULL
        );
        CREATE TABLE summaries (
            ROWID INTEGER PRIMARY KEY,
            summary TEXT NOT NULL
        );
        CREATE TABLE mailboxes (
            ROWID INTEGER PRIMARY KEY,
            url TEXT NOT NULL
        );
        CREATE TABLE message_global_data (
            ROWID INTEGER PRIMARY KEY,
            message_id_header TEXT
        );
        """
    )
    conn.executemany(
        "INSERT INTO addresses VALUES (?, ?, ?)",
        [
            (1, "notifications@stripe.example.test", "Stripe Private"),
            (2, "no_reply@email.apple.com", "Apple"),
            (3, "alerts@nelnet.studentaid.gov", "Nelnet"),
            (4, "friend@gmail.com", "Private Friend"),
        ],
    )
    conn.executemany(
        "INSERT INTO subjects VALUES (?, ?)",
        [
            (1, "Action required private client subject should not leak"),
            (2, "Billing Problem"),
            (3, "Student Loan Default Notice"),
            (4, "Security alert should not be processed in flagged scope"),
            (5, "Deleted flagged notice should not count"),
        ],
    )
    conn.executemany(
        "INSERT INTO summaries VALUES (?, ?)",
        [
            (1, "private body-ish summary should stay private"),
            (2, "Your payment method needs attention."),
            (3, "Your student loan needs review."),
        ],
    )
    conn.executemany(
        "INSERT INTO mailboxes VALUES (?, ?)",
        [
            (1, "imap://fixture/%5BGmail%5D/All%20Mail"),
            (2, "imap://fixture/INBOX"),
        ],
    )
    conn.executemany(
        "INSERT INTO message_global_data VALUES (?, ?)",
        [
            (101, "<stripe-private@example.test>"),
            (102, "<apple-billing@example.test>"),
            (103, "<nelnet-default@example.test>"),
            (104, "<friend-security@example.test>"),
            (105, "<deleted@example.test>"),
        ],
    )
    conn.executemany(
        """
        INSERT INTO messages (
            ROWID, global_message_id, conversation_id, date_received, flagged,
            flag_color, read, deleted, sender, subject, summary, mailbox
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (1, 101, 1001, _ts(2026, 7, 6), 1, 1, 1, 0, 1, 1, 1, 1),
            (2, 102, 1002, _ts(2026, 7, 5), 1, 1, 0, 0, 2, 2, 2, 2),
            (3, 103, 1003, _ts(2025, 6, 1), 1, 1, 1, 0, 3, 3, 3, 1),
            (4, 104, 1004, _ts(2024, 3, 1), 0, None, 1, 0, 4, 4, None, 1),
            (5, 105, 1005, _ts(2023, 1, 1), 1, 1, 1, 1, 4, 5, None, 1),
        ],
    )
    conn.commit()
    conn.close()
    return db


def test_build_snapshot_uses_unix_dates_and_classifies_flagged_atoms(tmp_path):
    module = _load_module()
    db = _mail_index(tmp_path)

    snapshot, atoms = module.build_snapshot(db)

    assert snapshot["stats"]["total_messages"] == 5
    assert snapshot["stats"]["not_deleted_messages"] == 4
    assert snapshot["stats"]["flagged_non_deleted"] == 3
    assert snapshot["stats"]["last_received_at"].startswith("2026-07-06")
    assert not snapshot["stats"]["last_received_at"].startswith("2057")
    assert snapshot["atom_count"] == 3
    assert {atom["cluster_id"] for atom in atoms} == {
        "identity-compliance",
        "billing-continuity",
        "debt-default-navigation",
    }
    assert all(atom["evidence_scope"] in {"metadata", "metadata_summary"} for atom in atoms)


def test_connect_readonly_rejects_sqlite_writes(tmp_path):
    module = _load_module()
    db = _mail_index(tmp_path)

    with module.connect_readonly(db) as conn:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("CREATE TABLE should_fail (id INTEGER)")


def test_markdown_is_redacted_while_private_atoms_keep_source(tmp_path):
    module = _load_module()
    db = _mail_index(tmp_path)
    doc = tmp_path / "docs" / "mail-story-ledger.md"
    log = tmp_path / "logs" / "mail-story-ledger.json"
    private_atoms = tmp_path / ".limen-private" / "mail-story" / "inventory" / "atoms.jsonl"
    private_snapshot = tmp_path / ".limen-private" / "mail-story" / "inventory" / "snapshot.json"

    snapshot, atoms = module.build_snapshot(db)
    markdown = module.render_markdown(snapshot)
    module.write_outputs(
        snapshot,
        atoms,
        markdown,
        doc_path=doc,
        log_path=log,
        private_atoms=private_atoms,
        private_snapshot=private_snapshot,
    )

    public_text = doc.read_text(encoding="utf-8")
    private_text = private_atoms.read_text(encoding="utf-8")
    log_payload = json.loads(log.read_text(encoding="utf-8"))
    scoped_log = log.with_name("mail-story-ledger-flagged.json")
    scoped_atoms = private_atoms.with_name("atoms-flagged.jsonl")
    scoped_snapshot = private_snapshot.with_name("snapshot-flagged.json")

    for forbidden in (
        "notifications@stripe.example.test",
        "Stripe Private",
        "private client subject should not leak",
        "private body-ish summary",
        "friend@gmail.com",
    ):
        assert forbidden not in markdown
        assert forbidden not in public_text

    assert "stripe.example.test" in public_text
    assert "notifications@stripe.example.test" in private_text
    assert "private body-ish summary should stay private" in private_text
    assert log_payload["privacy"]["raw_mail_in_git"] is False
    assert json.loads(scoped_log.read_text(encoding="utf-8"))["mode"]["scope"] == "flagged"
    assert scoped_atoms.read_text(encoding="utf-8") == private_text
    assert json.loads(scoped_snapshot.read_text(encoding="utf-8"))["mode"]["scope"] == "flagged"
