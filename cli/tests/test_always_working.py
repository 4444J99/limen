from __future__ import annotations

import importlib.util
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ALWAYS_WORKING = ROOT / "scripts" / "always-working.py"
DISPATCH_HEALTH = ROOT / "scripts" / "dispatch-health.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _mail_index(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE messages (
            ROWID INTEGER PRIMARY KEY,
            date_received INTEGER,
            flagged INTEGER NOT NULL DEFAULT 0,
            deleted INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    ts = int(datetime(2026, 7, 7, 12, tzinfo=timezone.utc).timestamp())
    conn.executemany(
        "INSERT INTO messages (ROWID, date_received, flagged, deleted) VALUES (?, ?, ?, ?)",
        [(1, ts, 1, 0), (2, ts, 1, 0), (3, ts, 0, 0)],
    )
    conn.commit()
    conn.close()


def test_always_working_reconciles_existing_work_before_assignment(monkeypatch, tmp_path):
    mod = _load("always_working_uut", ALWAYS_WORKING)
    root = tmp_path / "limen"
    profile = tmp_path / "organvm" / "4444J99"
    corpvs = tmp_path / "organvm-corpvs-testamentvm"
    private = root / ".limen-private" / "session-corpus"
    mail_index = tmp_path / "Envelope Index"

    (profile / "data").mkdir(parents=True)
    (profile / "README.md").write_text(
        "# Anthony\n"
        "Across <!-- v:total_repos -->148<!-- /v --> repos.\n"
        "[Portfolio](https://4444j99.github.io/portfolio/)\n",
        encoding="utf-8",
    )
    (profile / "data" / "ecosystem.yml").write_text("total_repos: 148\n", encoding="utf-8")
    corpvs.mkdir(parents=True)
    (corpvs / "system-metrics.json").write_text(
        json.dumps({"computed": {"total_repos": 171, "public_repos_all": 200, "total_words_numeric": 988148}}),
        encoding="utf-8",
    )
    (root / "docs" / "positioning").mkdir(parents=True)
    (root / "docs" / "positioning" / "_frontdoor.md").write_text("# Front door\n", encoding="utf-8")
    (root / "docs" / "consolidation").mkdir(parents=True)
    (root / "docs" / "consolidation" / "GATES.md").write_text("# Gates\n", encoding="utf-8")
    (root / "docs" / "consolidation" / "EXECUTION-MANIFEST.md").write_text("# Manifest\n", encoding="utf-8")
    (root / "docs" / "tabularius-record-keeper.md").write_text("- [ ] Step 2.2\n", encoding="utf-8")
    (root / "his-hand-levers.json").write_text("{}", encoding="utf-8")
    (root / "face-ownership.json").write_text("{}", encoding="utf-8")
    (root / "obligations-ledger.json").write_text("{}", encoding="utf-8")
    (root / "value-repos.json").write_text(json.dumps({"repos": ["organvm/a-i-chat--exporter"]}), encoding="utf-8")
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "product-ledger.md").write_text("# Product Ledger\n", encoding="utf-8")
    (root / "docs" / "mail-story-ledger.md").write_text("# Mail Story\n", encoding="utf-8")
    (root / "docs" / "his-hand-registry-mail-a290329e.md").write_text("# Mail\n", encoding="utf-8")
    (root / "scripts").mkdir(exist_ok=True)
    for script in ("mail-story-ledger.py", "mail-beat.sh", "repo-surface-ledger.py", "salvage-yard-map.py"):
        (root / "scripts" / script).write_text("", encoding="utf-8")
    (root / "cli" / "src" / "limen").mkdir(parents=True)
    (root / "cli" / "src" / "limen" / "tabularius.py").write_text("", encoding="utf-8")
    (root / "logs").mkdir()
    (root / "logs" / "heartbeat.out.log").write_text("", encoding="utf-8")
    (root / "scripts" / "cvstos-organ.py").write_text("", encoding="utf-8")
    (root / "scripts" / "dispatch-health.py").write_text("", encoding="utf-8")
    _mail_index(mail_index)

    lifecycle = private / "lifecycle"
    lifecycle.mkdir(parents=True)
    (lifecycle / "repo-surface-ledger.json").write_text(
        json.dumps({"generated_at": "2026-06-30T00:00:00+00:00", "repo_count": 249, "duplicate_remotes": []}),
        encoding="utf-8",
    )
    (lifecycle / "prompt-packet-ledger.json").write_text(
        json.dumps({"open_packets": [], "recorded_packets": [{"id": "p1"}]}),
        encoding="utf-8",
    )
    (lifecycle / "product-ledger.json").write_text(json.dumps({"next_unblocked": [{"id": "v1"}]}), encoding="utf-8")

    monkeypatch.setattr(mod, "ROOT", root)
    monkeypatch.setattr(mod, "PRIVATE_ROOT", private)
    monkeypatch.setattr(mod, "PRIVATE_INDEX", lifecycle / "always-working.json")
    monkeypatch.setattr(mod, "DOC_PATH", root / "docs" / "always-working.md")
    monkeypatch.setattr(mod, "PROFILE_REPO", profile)
    monkeypatch.setattr(mod, "CORPVS_ROOT", corpvs)
    monkeypatch.setattr(mod, "MAIL_INDEX", mail_index)
    monkeypatch.setattr(mod, "PROMPT_PACKET_INDEX", lifecycle / "prompt-packet-ledger.json")
    monkeypatch.setattr(mod, "REPO_SURFACE_INDEX", lifecycle / "repo-surface-ledger.json")
    monkeypatch.setattr(mod, "PRODUCT_LEDGER_INDEX", lifecycle / "product-ledger.json")
    monkeypatch.setattr(mod, "VALUE_REPOS", root / "value-repos.json")
    monkeypatch.setattr(
        mod, "disk_receipt", lambda: {"free_gib": 100.0, "used_pct": 50.0, "tmp_ok": True, "tmp_error": ""}
    )
    monkeypatch.setattr(mod, "mail_census", lambda: {"ok": True, "account_count": 1, "obligation_count": 2})

    snapshot = mod.build_snapshot()
    by_id = {item["id"]: item for item in snapshot["items"]}

    assert by_id["PUBLIC-FACE-PROFILE"]["status"] == mod.STATUS_ASSIGNED
    assert by_id["MAIL-ACTIVE-FLAGGED"]["status"] == mod.STATUS_ASSIGNED
    assert by_id["MAIL-HISTORICAL-BACKLOG"]["status"] == mod.STATUS_ASSIGNED
    assert by_id["REPO-BOIL-UP"]["status"] == mod.STATUS_ASSIGNED
    assert by_id["PROMPT-PACKETS"]["status"] == mod.STATUS_DONE
    assert snapshot["next_item_id"] == "PUBLIC-FACE-PROFILE"
    assert snapshot["contract"]["first_run_forbidden"] is True


def test_dispatch_health_blocks_when_always_working_required_items_are_open(tmp_path):
    mod = _load("dispatch_health_always_working_uut", DISPATCH_HEALTH)
    index = tmp_path / "always-working.json"
    mod.ALWAYS_WORKING_INDEX = index
    mod.ALWAYS_WORKING_DOC = tmp_path / "always-working.md"
    index.write_text(
        json.dumps(
            {
                "status": "needs-work",
                "required_open_count": 2,
                "blocked_count": 0,
                "done_count": 1,
                "next_item_id": "PUBLIC-FACE-PROFILE",
                "next_item_status": "assigned_from_existing_work",
                "items": [
                    {
                        "id": "PUBLIC-FACE-PROFILE",
                        "workstream": "public-face",
                        "status": "assigned_from_existing_work",
                        "verdict": "profile stale",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    always = mod.always_working_snapshot()
    snapshot = {
        "heartbeat_plist": {"present": True, "keep_alive": True, "env": {}},
        "launchd": {"running": True, "state": "running", "env": {}},
        "live_root_git": {"present": False, "matches_origin_main": True, "dirty_entries": 0},
        "watchdog": {"healthy": True},
        "async_probe": {"requested": False},
        "prompt_packets": {"conductor_required_packets": 0},
        "always_working": always,
    }

    blockers = mod.derive_blockers(snapshot)

    assert any(blocker["id"] == "always-working-required-work-open" for blocker in blockers)
