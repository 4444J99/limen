import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_mail_beat_census_reads_uma_status_only(tmp_path):
    limen = tmp_path / "limen"
    uma = tmp_path / "universal-mail--automation"
    home = tmp_path / "home"
    status_path = limen / "logs" / "uma-mail-status.json"
    ops_report = home / "System" / "Reports" / "mail-triage" / "latest.json"
    history_report = home / "System" / "Reports" / "mail-history" / "latest.json"

    (limen / "logs").mkdir(parents=True)
    uma.mkdir()
    home.mkdir()
    ops_report.parent.mkdir(parents=True)
    history_report.parent.mkdir(parents=True)
    (uma / "cli.py").write_text("# placeholder\n", encoding="utf-8")
    ops_report.write_text("{}", encoding="utf-8")
    history_report.write_text("{}", encoding="utf-8")
    status_path.write_text(
        json.dumps(
            {
                "schema": "uma.mail.status.v1",
                "status": "open",
                "mode": {"read_only": True, "mailbox_mutations": False, "sends": False},
                "current_ops": {"available": True, "kpis": {"inbox_total": 3}},
                "historical_crosswalk": {
                    "available": True,
                    "kpis": {"reconciled": True, "source_messages": 41415},
                },
                "next_queue": [{"id": "redacted"}],
                "blockers": [{"surface": "history", "status": "blocked"}],
            }
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        ["bash", str(ROOT / "scripts" / "mail-beat.sh"), "--census"],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "HOME": str(home),
            "LIMEN_ROOT": str(limen),
            "UMA_ROOT": str(uma),
            "LIMEN_MAIL_STATUS_OUT": str(status_path),
            "UMA_OPS_REPORT_PATH": str(ops_report),
            "UMA_HISTORICAL_MAIL_PATH": str(history_report),
        },
        check=True,
    )
    census = json.loads(proc.stdout)
    encoded = json.dumps(census, sort_keys=True)

    assert census["status_receipt_present"] is True
    assert census["status_schema"] == "uma.mail.status.v1"
    assert census["status_value"] == "open"
    assert census["current_ops_available"] is True
    assert census["historical_crosswalk_available"] is True
    assert census["historical_reconciled"] is True
    assert census["historical_source_messages"] == 41415
    assert census["next_queue_count"] == 1
    assert census["blocker_count"] == 1
    assert census["mailbox_mutations_allowed"] is False
    assert census["sends_allowed"] is False
    assert census["wrapper"] is True
    assert "private" not in encoded.lower()


def test_mail_status_timeout_emits_blocked_receipt_and_returns(tmp_path):
    limen = tmp_path / "limen"
    uma = tmp_path / "universal-mail--automation"
    home = tmp_path / "home"
    status_path = limen / "logs" / "uma-mail-status.json"
    (limen / "logs").mkdir(parents=True)
    uma.mkdir()
    home.mkdir()
    (uma / "cli.py").write_text(
        "import time\ntime.sleep(30)\n",
        encoding="utf-8",
    )

    started = time.monotonic()
    subprocess.run(
        ["bash", str(ROOT / "scripts" / "mail-beat.sh")],
        capture_output=True,
        text=True,
        timeout=5,
        env={
            **os.environ,
            "HOME": str(home),
            "LIMEN_ROOT": str(limen),
            "UMA_ROOT": str(uma),
            "LIMEN_MAIL_STATUS_OUT": str(status_path),
            "LIMEN_MAIL_STATUS_TIMEOUT": "1",
            "LIMEN_MAIL_SWEEP": "0",
            "LIMEN_MAIL_ARCHIVED_SCAN": "0",
            "LIMEN_MAIL_UMA_SYNC": "0",
            "LIMEN_CORRESPONDENCE_WALK": "0",
        },
        check=True,
    )

    assert time.monotonic() - started < 5
    receipt = json.loads(status_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "blocked"
    assert receipt["mode"] == {"mailbox_mutations": False, "read_only": True, "sends": False}
    assert "timeout" in receipt["blockers"][0]["detail"]
