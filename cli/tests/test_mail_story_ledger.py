import importlib.util
import json
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "mail-story-ledger.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("mail_story_ledger_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _status_payload():
    return {
        "schema": "uma.mail.status.v1",
        "status": "open",
        "mode": {"read_only": True, "mailbox_mutations": False, "sends": False},
        "privacy": {"redacted": True, "public_safe": True},
        "current_ops": {"available": True, "kpis": {"inbox_total": 12, "changed_count": 0}},
        "historical_crosswalk": {
            "available": True,
            "kpis": {"source_messages": 41415, "reconciled": True},
            "terminal_status_counts": {
                "resolved": 40000,
                "represented_in_ops": 1000,
                "stale_noop": 300,
                "open": 100,
                "blocked": 10,
                "needs_human": 5,
            },
        },
        "answers": {
            "what_ran": "daily UMA status",
            "what_changed": "no mailbox changes",
            "what_remains_open": "100 redacted items",
            "what_is_blocked": "10 redacted blockers",
            "historical_backlog_accounted_for": "yes",
        },
        "next_queue": [
            {
                "id": "redacted-action-1",
                "terminal_status": "open",
                "processing_state": "queued",
                "surface": "current_ops",
                "reason_code": "needs_reply",
                "subject": "private subject must not leak",
                "email": "secret@example.com",
            }
        ],
        "blockers": [{"surface": "history", "status": "blocked"}],
    }


def test_wrapper_snapshot_and_markdown_are_redacted():
    module = _load_module()

    snapshot, atoms = module.build_snapshot(_status_payload())
    markdown = module.render_markdown(snapshot)

    assert snapshot["schema"] == "limen.mail_story.wrapper.v1"
    assert snapshot["classification_owner"] == "organvm/universal-mail--automation"
    assert snapshot["mode"]["mailbox_mutations"] is False
    assert snapshot["mode"]["sends"] is False
    assert snapshot["source_receipt"]["schema"] == "uma.mail.status.v1"
    assert snapshot["stats"]["historical_messages"] == 41415
    assert snapshot["stats"]["historical_reconciled"] is True
    assert atoms[0]["classification_owner"] == "organvm/universal-mail--automation"
    assert "UMA wrapper" in markdown
    assert "private subject" not in json.dumps(snapshot)
    assert "secret@example.com" not in json.dumps(atoms)


def test_wrapper_writes_existing_limen_surfaces_without_raw_mail(tmp_path):
    module = _load_module()
    doc = tmp_path / "docs" / "mail-story-ledger.md"
    log = tmp_path / "logs" / "mail-story-ledger.json"
    private_atoms = tmp_path / ".limen-private" / "mail-story" / "inventory" / "atoms.jsonl"
    private_snapshot = tmp_path / ".limen-private" / "mail-story" / "inventory" / "snapshot.json"

    snapshot, atoms = module.build_snapshot(_status_payload())
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

    assert "private subject" not in public_text
    assert "secret@example.com" not in public_text
    assert "secret@example.com" not in private_text
    assert log_payload["privacy"]["raw_mail_in_git"] is False
    assert json.loads(scoped_log.read_text(encoding="utf-8"))["mode"]["scope"] == "flagged"
    assert scoped_atoms.read_text(encoding="utf-8") == private_text
    assert json.loads(scoped_snapshot.read_text(encoding="utf-8"))["mode"]["scope"] == "flagged"


def test_wrapper_cli_can_render_from_status_fixture(tmp_path):
    status = tmp_path / "uma-status.json"
    doc = tmp_path / "doc.md"
    log = tmp_path / "log.json"
    atoms = tmp_path / "atoms.jsonl"
    snapshot = tmp_path / "snapshot.json"
    status.write_text(json.dumps(_status_payload()), encoding="utf-8")

    proc = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--status",
            str(status),
            "--write",
            "--doc",
            str(doc),
            "--log",
            str(log),
            "--private-atoms",
            str(atoms),
            "--private-snapshot",
            str(snapshot),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert "UMA wrapper wrote" in proc.stdout
    assert json.loads(log.read_text(encoding="utf-8"))["source_receipt"]["schema"] == "uma.mail.status.v1"
