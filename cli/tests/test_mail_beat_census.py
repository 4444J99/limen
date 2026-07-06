import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_mail_beat_census_is_counts_only(tmp_path):
    limen = tmp_path / "limen"
    uma = tmp_path / "universal-mail--automation"
    home = tmp_path / "home"
    ledger = limen / "obligations-ledger.json"
    (limen / "logs" / ".voice").mkdir(parents=True)
    (limen / "web" / "app" / "public").mkdir(parents=True)
    uma.mkdir()
    home.mkdir()
    for name in ("inbox_sweep.py", "obligations_build.py", "draft_writer.py"):
        (uma / name).write_text("# placeholder\n", encoding="utf-8")
    (limen / "logs" / ".voice" / "mail").write_text("2026-07-06T00:00:00Z\n", encoding="utf-8")
    (limen / "web" / "app" / "public" / "obligations.html").write_text("private face\n", encoding="utf-8")
    ledger.write_text(
        json.dumps(
            {
                "obligations": [{"title": "Reply to private student", "account": "secret@example.com"}],
                "accounts": [{"account": "secret@example.com", "fires": 1}],
                "noise_killers": [{"name": "Confidential Vendor", "domain": "private.example"}],
                "levers": [{"id": "L-PRIVATE-MAIL", "label": "private mail gate"}],
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
            "LIMEN_OBLIGATIONS_LEDGER": str(ledger),
            "LIMEN_MAIL_SWEEP": "0",
            "LIMEN_MAIL_DRAFTS": "1",
        },
        check=True,
    )
    census = json.loads(proc.stdout)
    encoded = json.dumps(census, sort_keys=True)

    assert census["ledger_present"] is True
    assert census["ledger_readable"] is True
    assert census["obligation_count"] == 1
    assert census["account_count"] == 1
    assert census["noise_killer_count"] == 1
    assert census["lever_count"] == 1
    assert census["uma_present_script_count"] == 3
    assert census["voice_stamp_present"] is True
    assert census["web_face_count"] == 1
    assert census["sweep_enabled"] is False
    assert census["draft_persistence_enabled"] is True
    assert "Reply to private student" not in encoded
    assert "secret@example.com" not in encoded
    assert "Confidential Vendor" not in encoded
    assert "private.example" not in encoded
    assert "L-PRIVATE-MAIL" not in encoded
