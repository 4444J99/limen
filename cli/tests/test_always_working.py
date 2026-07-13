from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import time
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


def _seed_cached_lifecycle(root: Path, *, debt: int = 0, reapable: int = 0, at_factory: bool = True) -> None:
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "cvstos-organ-state.json").write_text(
        json.dumps(
            {
                "at_factory": at_factory,
                "open_invariants": [] if at_factory else ["open"],
                "worktree_has_debt": debt != 0,
            }
        ),
        encoding="utf-8",
    )
    (logs / "session-lifecycle-pressure.json").write_text(
        json.dumps(
            {
                "worktrees": {
                    "debt": debt,
                    "complete": debt == 0,
                    "by_reason": {"clean+merged+idle": reapable} if reapable else {},
                    "error": "",
                }
            }
        ),
        encoding="utf-8",
    )


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
    _seed_cached_lifecycle(root)
    (root / "scripts" / "cvstos-organ.py").write_text("", encoding="utf-8")
    (root / "scripts" / "worktree-debt.py").write_text("", encoding="utf-8")
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
    monkeypatch.setattr(mod, "CVSTOS_STATE", root / "logs" / "cvstos-organ-state.json")
    monkeypatch.setattr(mod, "LIFECYCLE_PRESSURE_STATE", root / "logs" / "session-lifecycle-pressure.json")
    monkeypatch.setattr(
        mod,
        "github_profile_surface",
        lambda: {"checked": True, "verified": True, "readme_total_repos": "171", "account_profile_stale": False},
    )
    monkeypatch.setattr(
        mod, "disk_receipt", lambda: {"free_gib": 250.0, "used_pct": 50.0, "tmp_ok": True, "tmp_error": ""}
    )
    monkeypatch.setattr(
        mod,
        "estate_custody_receipt",
        lambda: {
            "id": "ESTATE-CUSTODY",
            "workstream": "estate-custody",
            "priority": 5,
            "status": mod.STATUS_DONE,
            "title": "estate",
            "verdict": "owned",
            "evidence": {},
            "assignment_packet": {},
        },
    )
    monkeypatch.setattr(
        mod,
        "contribution_balance_receipt",
        lambda: {
            "id": "PUBLIC-FACE-CONTRIBUTION-BALANCE",
            "workstream": "contribution-balance",
            "priority": 15,
            "status": mod.STATUS_DONE,
            "title": "balance",
            "verdict": "balanced",
            "evidence": {},
            "assignment_packet": {},
        },
    )
    monkeypatch.setattr(
        mod,
        "credential_wall_receipt",
        lambda: {
            "id": "CREDENTIAL-WALL-TOKEN-HYGIENE",
            "workstream": "credential-wall",
            "priority": 18,
            "status": mod.STATUS_DONE,
            "title": "credentials",
            "verdict": "owned",
            "evidence": {},
            "assignment_packet": {},
        },
    )
    monkeypatch.setattr(mod, "mail_census", lambda: {"ok": True, "account_count": 1, "obligation_count": 2})

    snapshot = mod.build_snapshot()
    by_id = {item["id"]: item for item in snapshot["items"]}

    assert by_id["PUBLIC-FACE-PROFILE"]["status"] == mod.STATUS_ASSIGNED
    assert by_id["ESTATE-CUSTODY"]["status"] == mod.STATUS_DONE
    assert by_id["MAIL-ACTIVE-FLAGGED"]["status"] == mod.STATUS_ASSIGNED
    assert by_id["MAIL-HISTORICAL-BACKLOG"]["status"] == mod.STATUS_ASSIGNED
    assert by_id["REPO-BOIL-UP"]["status"] == mod.STATUS_ASSIGNED
    assert by_id["PROMPT-PACKETS"]["status"] == mod.STATUS_DONE
    assert snapshot["next_item_id"] == "PUBLIC-FACE-PROFILE"
    assert snapshot["contract"]["first_run_forbidden"] is True
    assert mod._task_from_item({"id": "SUBSTRATE", "priority": 0, "workstream": "substrate"})["priority"] == "critical"


def test_substrate_receipt_reports_free_space_shortfall_after_reclaim(monkeypatch, tmp_path):
    mod = _load("always_working_substrate_shortfall_uut", ALWAYS_WORKING)
    root = tmp_path / "limen"
    (root / "scripts").mkdir(parents=True)
    (root / "logs").mkdir()
    (root / "logs" / "heartbeat.out.log").write_text("", encoding="utf-8")
    (root / "logs" / "reclaim-generated-state.jsonl").write_text(
        json.dumps(
            {
                "generated_at": "2026-07-10T00:00:00Z",
                "apply": True,
                "changed_roots": 113,
                "failed_roots": 0,
                "total_reclaimed_size": "26.6 GiB",
                "total_reclaimed_kib": 27892121,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "logs" / "reclaim-tool-caches.jsonl").write_text(
        json.dumps(
            {
                "generated_at": "2026-07-10T00:05:00Z",
                "apply": True,
                "existing_paths": 17,
                "failed_paths": 0,
                "total_reclaimed_size": "4.7 GiB",
                "total_reclaimed_kib": 4915200,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "logs" / "reclaim-ollama-models.jsonl").write_text(
        json.dumps(
            {
                "generated_at": "2026-07-10T00:06:00Z",
                "apply": True,
                "model_count": 2,
                "loaded_models": [],
                "blocked_reason": "",
                "failed": [],
                "reclaimed_size": "9.3 GiB",
                "reclaimed_kib": 9751756,
                "total_reclaimed_size": "9.3 GiB",
                "total_reclaimed_kib": 9751756,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _seed_cached_lifecycle(root)

    monkeypatch.setattr(mod, "ROOT", root)
    monkeypatch.setattr(
        mod,
        "SUBSTRATE_STORAGE_INDEX",
        root / ".limen-private" / "session-corpus" / "lifecycle" / "substrate-storage-pressure.json",
    )
    monkeypatch.setattr(mod, "GENERATED_STATE_RECLAIM_LOG", root / "logs" / "reclaim-generated-state.jsonl")
    monkeypatch.setattr(mod, "TOOL_CACHE_RECLAIM_LOG", root / "logs" / "reclaim-tool-caches.jsonl")
    monkeypatch.setattr(mod, "OLLAMA_MODEL_RECLAIM_LOG", root / "logs" / "reclaim-ollama-models.jsonl")
    monkeypatch.setattr(mod, "CVSTOS_STATE", root / "logs" / "cvstos-organ-state.json")
    monkeypatch.setattr(mod, "LIFECYCLE_PRESSURE_STATE", root / "logs" / "session-lifecycle-pressure.json")
    monkeypatch.setattr(
        mod, "disk_receipt", lambda: {"free_gib": 78.0, "used_pct": 82.0, "tmp_ok": True, "tmp_error": ""}
    )
    monkeypatch.setattr(
        mod,
        "run_command",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("hot path must use cached lifecycle state")),
    )
    receipt = mod.substrate_receipt()

    assert receipt["status"] == mod.STATUS_ASSIGNED
    assert receipt["evidence"]["shortfall_gib"] == 122.0
    assert receipt["evidence"]["lifecycle"]["predicate_ok"] is True
    assert receipt["evidence"]["lifecycle"]["generated_state_reclaim"]["cumulative_reclaimed_size"] == "26.6 GiB"
    assert receipt["evidence"]["lifecycle"]["tool_cache_reclaim"]["cumulative_reclaimed_size"] == "4.7 GiB"
    assert receipt["evidence"]["lifecycle"]["ollama_model_reclaim"]["cumulative_reclaimed_size"] == "9.3 GiB"
    assert "generated-state 26.6 GiB, tool-cache 4.7 GiB, ollama-models 9.3 GiB" in receipt["verdict"]


def test_substrate_receipt_blocks_when_storage_pressure_needs_owner_gates(monkeypatch, tmp_path):
    mod = _load("always_working_substrate_owner_gate_uut", ALWAYS_WORKING)
    root = tmp_path / "limen"
    private = root / ".limen-private" / "session-corpus"
    storage_index = private / "lifecycle" / "substrate-storage-pressure.json"
    storage_index.parent.mkdir(parents=True)
    storage_index.write_text(
        json.dumps(
            {
                "status": "needs-owner-gates",
                "internal_free_gib": 93.0,
                "target_free_gib": 200.0,
                "shortfall_gib": 107.0,
            }
        ),
        encoding="utf-8",
    )
    (root / "logs").mkdir()
    (root / "logs" / "reclaim-generated-state.jsonl").write_text(
        json.dumps({"apply": True, "total_reclaimed_size": "26.6 GiB"}) + "\n",
        encoding="utf-8",
    )
    _seed_cached_lifecycle(root)

    monkeypatch.setattr(mod, "ROOT", root)
    monkeypatch.setattr(mod, "PRIVATE_ROOT", private)
    monkeypatch.setattr(mod, "SUBSTRATE_STORAGE_INDEX", storage_index)
    monkeypatch.setattr(mod, "GENERATED_STATE_RECLAIM_LOG", root / "logs" / "reclaim-generated-state.jsonl")
    monkeypatch.setattr(mod, "TOOL_CACHE_RECLAIM_LOG", root / "logs" / "reclaim-tool-caches.jsonl")
    monkeypatch.setattr(mod, "OLLAMA_MODEL_RECLAIM_LOG", root / "logs" / "reclaim-ollama-models.jsonl")
    monkeypatch.setattr(mod, "CVSTOS_STATE", root / "logs" / "cvstos-organ-state.json")
    monkeypatch.setattr(mod, "LIFECYCLE_PRESSURE_STATE", root / "logs" / "session-lifecycle-pressure.json")
    monkeypatch.setattr(
        mod, "disk_receipt", lambda: {"free_gib": 93.0, "used_pct": 80.0, "tmp_ok": True, "tmp_error": ""}
    )
    receipt = mod.substrate_receipt()

    assert receipt["status"] == mod.STATUS_BLOCKED
    assert receipt["evidence"]["storage_pressure_status"] == "needs-owner-gates"
    assert "remaining bytes require owner gates" in receipt["verdict"]


def test_substrate_receipt_blocks_when_lifecycle_predicate_fails(monkeypatch, tmp_path):
    mod = _load("always_working_substrate_predicate_uut", ALWAYS_WORKING)
    root = tmp_path / "limen"
    monkeypatch.setattr(mod, "ROOT", root)
    monkeypatch.setattr(mod, "GENERATED_STATE_RECLAIM_LOG", root / "logs" / "reclaim-generated-state.jsonl")
    monkeypatch.setattr(mod, "TOOL_CACHE_RECLAIM_LOG", root / "logs" / "reclaim-tool-caches.jsonl")
    monkeypatch.setattr(mod, "OLLAMA_MODEL_RECLAIM_LOG", root / "logs" / "reclaim-ollama-models.jsonl")
    _seed_cached_lifecycle(root, debt=1)
    monkeypatch.setattr(mod, "CVSTOS_STATE", root / "logs" / "cvstos-organ-state.json")
    monkeypatch.setattr(mod, "LIFECYCLE_PRESSURE_STATE", root / "logs" / "session-lifecycle-pressure.json")
    monkeypatch.setattr(
        mod, "disk_receipt", lambda: {"free_gib": 250.0, "used_pct": 40.0, "tmp_ok": True, "tmp_error": ""}
    )

    receipt = mod.substrate_receipt()

    assert receipt["status"] == mod.STATUS_ASSIGNED
    assert receipt["verdict"] == "substrate lifecycle predicate is failing"
    assert receipt["evidence"]["lifecycle"]["worktree_debt"]["ok"] is False
    assert receipt["evidence"]["lifecycle"]["worktree_debt"]["debt"] == 1


def test_lifecycle_cache_stays_fresh_between_heartbeat_refreshes(monkeypatch, tmp_path):
    mod = _load("always_working_lifecycle_cadence_uut", ALWAYS_WORKING)
    root = tmp_path / "limen"
    _seed_cached_lifecycle(root)
    monkeypatch.setattr(mod, "CVSTOS_STATE", root / "logs" / "cvstos-organ-state.json")
    monkeypatch.setattr(mod, "LIFECYCLE_PRESSURE_STATE", root / "logs" / "session-lifecycle-pressure.json")
    monkeypatch.setenv("LIMEN_LOOP_MAX", "100")
    monkeypatch.setenv("LIMEN_BEAT_CVSTOS", "4")
    monkeypatch.setenv("LIMEN_BEAT_DRAIN", "3")
    monkeypatch.setenv("LIMEN_LIFECYCLE_PRESSURE_THROTTLE", "50")
    monkeypatch.setenv("LIMEN_RECLAIM_TIMEOUT", "20")

    # CVSTOS: 4*100+20=420s. Pressure: throttle 50+3*100+20=370s.
    now = time.time()
    os.utime(mod.CVSTOS_STATE, (now - 419, now - 419))
    os.utime(mod.LIFECYCLE_PRESSURE_STATE, (now - 369, now - 369))

    receipt = mod.substrate_lifecycle_receipt()

    assert receipt["cvstos"]["freshness_window_seconds"] == 420
    assert receipt["worktree_debt"]["freshness_window_seconds"] == 370
    assert receipt["predicate_ok"] is True


def test_lifecycle_cache_missing_invalid_or_past_scheduler_bound_fails_closed(monkeypatch, tmp_path):
    mod = _load("always_working_lifecycle_stale_uut", ALWAYS_WORKING)
    root = tmp_path / "limen"
    _seed_cached_lifecycle(root)
    monkeypatch.setattr(mod, "CVSTOS_STATE", root / "logs" / "cvstos-organ-state.json")
    monkeypatch.setattr(mod, "LIFECYCLE_PRESSURE_STATE", root / "logs" / "session-lifecycle-pressure.json")
    monkeypatch.setenv("LIMEN_LOOP_MAX", "100")
    monkeypatch.setenv("LIMEN_BEAT_CVSTOS", "4")
    monkeypatch.setenv("LIMEN_BEAT_DRAIN", "3")
    monkeypatch.setenv("LIMEN_LIFECYCLE_PRESSURE_THROTTLE", "50")
    monkeypatch.setenv("LIMEN_RECLAIM_TIMEOUT", "20")

    now = time.time()
    os.utime(mod.LIFECYCLE_PRESSURE_STATE, (now - 371, now - 371))
    stale = mod.substrate_lifecycle_receipt()
    assert stale["worktree_debt"]["fresh"] is False
    assert stale["predicate_ok"] is False

    # A fresh file with an incomplete producer schema cannot manufacture exact-zero authority.
    mod.LIFECYCLE_PRESSURE_STATE.write_text(json.dumps({"worktrees": {"debt": 0}}), encoding="utf-8")
    invalid = mod.substrate_lifecycle_receipt()
    assert invalid["worktree_debt"]["fresh"] is True
    assert invalid["worktree_debt"]["valid"] is False
    assert invalid["predicate_ok"] is False

    _seed_cached_lifecycle(root)
    mod.CVSTOS_STATE.write_text(
        json.dumps({"at_factory": True, "open_invariants": ["contradiction"], "worktree_has_debt": False}),
        encoding="utf-8",
    )
    invalid_cvstos = mod.substrate_lifecycle_receipt()
    assert invalid_cvstos["cvstos"]["fresh"] is True
    assert invalid_cvstos["cvstos"]["valid"] is False
    assert invalid_cvstos["predicate_ok"] is False

    mod.LIFECYCLE_PRESSURE_STATE.unlink()
    missing = mod.substrate_lifecycle_receipt()
    assert missing["worktree_debt"]["fresh"] is False
    assert missing["predicate_ok"] is False


def test_lifecycle_cache_sums_every_authoritative_reapable_reason(monkeypatch, tmp_path):
    mod = _load("always_working_lifecycle_reapable_uut", ALWAYS_WORKING)
    root = tmp_path / "limen"
    _seed_cached_lifecycle(root)
    pressure_path = root / "logs" / "session-lifecycle-pressure.json"
    pressure_path.write_text(
        json.dumps(
            {
                "worktrees": {
                    "debt": 0,
                    "complete": True,
                    "by_reason": {
                        "clean+pushed+idle": 1,
                        "receipt-remote-merged+clean+idle": 2,
                    },
                    "error": "",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "CVSTOS_STATE", root / "logs" / "cvstos-organ-state.json")
    monkeypatch.setattr(mod, "LIFECYCLE_PRESSURE_STATE", pressure_path)

    receipt = mod.substrate_lifecycle_receipt()

    assert receipt["worktree_debt"]["reapable"] == 3
    assert receipt["worktree_debt"]["reapable_by_reason"] == {
        "clean+merged+idle": 0,
        "clean+pushed+idle": 1,
        "receipt-remote-merged+clean+idle": 2,
    }
    assert receipt["worktree_debt"]["ok"] is False
    assert receipt["predicate_ok"] is False


def test_heartbeat_produces_lifecycle_pressure_off_dispatch_hot_path():
    heartbeat = (ROOT / "scripts" / "heartbeat-loop.sh").read_text(encoding="utf-8")

    assert 'if [ "${DRAIN_VOICE_DUE:-0}" = "1" ]; then' in heartbeat
    assert 'scripts/session-lifecycle-pressure.py" --write' in heartbeat
    assert '--throttle "${LIMEN_LIFECYCLE_PRESSURE_THROTTLE:-1800}"' in heartbeat
    assert heartbeat.index('scripts/reclaim-worktrees.py" "${reclaim_args[@]}"') < heartbeat.index(
        'scripts/session-lifecycle-pressure.py" --write'
    )


def test_profile_receipt_accepts_computed_laurel_positioning(monkeypatch, tmp_path):
    mod = _load("always_working_profile_receipt_uut", ALWAYS_WORKING)
    root = tmp_path / "limen"
    profile = tmp_path / "organvm" / "4444J99"
    corpvs = tmp_path / "organvm-corpvs-testamentvm"

    (profile / "data").mkdir(parents=True)
    (profile / "README.md").write_text(
        "# Anthony James Padavano\n\n"
        "**Top-tier Creative Technologist / Systems Architect**\n\n"
        "**Proof surface:** <!-- v:total_repos -->171<!-- /v --> canonical public non-fork repos, "
        "<!-- v:public_repos -->203<!-- /v --> public accessible repos, "
        "<!-- v:owned_ecosystem_repos -->301<!-- /v --> owned accessible repos, and "
        "<!-- v:contributed_repos -->321<!-- /v --> contributed repositories.\n\n"
        "**Now:** Shipping across <!-- v:total_repos -->171<!-- /v --> repos and "
        "<!-- v:total_words_short -->988K+<!-- /v --> words.\n\n"
        "[Portfolio](https://organvm.github.io/portfolio/)\n\n"
        "Computed laurels -- top 0.1% engineering throughput.\n",
        encoding="utf-8",
    )
    (profile / "data" / "ecosystem.yml").write_text("total_repos: 171\n", encoding="utf-8")
    corpvs.mkdir(parents=True)
    (corpvs / "system-metrics.json").write_text(
        json.dumps({"computed": {"total_repos": 171, "public_repos_all": 203, "total_words_numeric": 988148}}),
        encoding="utf-8",
    )
    (root / "docs" / "positioning").mkdir(parents=True)
    (root / "docs" / "positioning" / "_frontdoor.md").write_text("# Front door\n", encoding="utf-8")

    monkeypatch.setattr(mod, "ROOT", root)
    monkeypatch.setattr(mod, "PROFILE_REPO", profile)
    monkeypatch.setattr(mod, "CORPVS_ROOT", corpvs)
    monkeypatch.setattr(
        mod,
        "github_profile_surface",
        lambda: {
            "checked": True,
            "verified": True,
            "readme_total_repos": "171",
            "old_portfolio_link_count": 0,
            "top_engineer_claim_present": True,
            "account_profile_stale": False,
        },
    )

    receipt = mod.profile_receipt()

    assert receipt["status"] == mod.STATUS_DONE
    assert receipt["evidence"]["top_engineer_claim_present"] is True
    assert receipt["evidence"]["visible_profile"]["verified"] is True


def test_profile_receipt_blocks_stale_github_sidebar(monkeypatch, tmp_path):
    mod = _load("always_working_profile_sidebar_uut", ALWAYS_WORKING)
    root = tmp_path / "limen"
    profile = tmp_path / "organvm" / "4444J99"
    corpvs = tmp_path / "organvm-corpvs-testamentvm"

    (profile / "data").mkdir(parents=True)
    (profile / "README.md").write_text(
        "# Anthony James Padavano\n\n"
        "**Top-tier Creative Technologist / Systems Architect**\n\n"
        "**Now:** Shipping across <!-- v:total_repos -->171<!-- /v --> repos and "
        "<!-- v:total_words_short -->988K+<!-- /v --> words.\n\n"
        "[Portfolio](https://organvm.github.io/portfolio/)\n",
        encoding="utf-8",
    )
    (profile / "data" / "ecosystem.yml").write_text("total_repos: 171\n", encoding="utf-8")
    corpvs.mkdir(parents=True)
    (corpvs / "system-metrics.json").write_text(
        json.dumps({"computed": {"total_repos": 171, "public_repos_all": 203, "total_words_numeric": 988148}}),
        encoding="utf-8",
    )
    (root / "docs" / "positioning").mkdir(parents=True)
    (root / "docs" / "positioning" / "_frontdoor.md").write_text("# Front door\n", encoding="utf-8")

    monkeypatch.setattr(mod, "ROOT", root)
    monkeypatch.setattr(mod, "PROFILE_REPO", profile)
    monkeypatch.setattr(mod, "CORPVS_ROOT", corpvs)
    monkeypatch.setattr(
        mod,
        "github_profile_surface",
        lambda: {
            "checked": True,
            "verified": True,
            "readme_total_repos": "171",
            "old_portfolio_link_count": 0,
            "top_engineer_claim_present": True,
            "account_profile_stale": True,
            "account_bio": "Full-stack developer. 91 repos, 3,586 code files.",
        },
    )

    receipt = mod.profile_receipt()

    assert receipt["status"] == mod.STATUS_BLOCKED
    assert "sidebar bio" in receipt["verdict"]


def test_contribution_balance_receipt_assigns_review_first(monkeypatch):
    mod = _load("always_working_contribution_balance_uut", ALWAYS_WORKING)

    monkeypatch.setattr(
        mod,
        "run_command",
        lambda *args, **kwargs: {
            "returncode": 0,
            "stdout": json.dumps(
                {
                    "status": "needs_balance",
                    "login": "4444J99",
                    "counts": {"commits": 12885, "issues": 2097, "pull_requests": 2317, "reviews": 106},
                    "shares": {"commits": 0.7403, "issues": 0.1205, "pull_requests": 0.1331, "reviews": 0.0061},
                    "targets": {"commits_max_share": 0.6, "reviews_min_share": 0.1},
                    "next_action": "Review an existing PR with a substantive approval, request-change, or comment receipt before new feature work.",
                }
            ),
            "stderr": "",
            "timed_out": False,
        },
    )

    receipt = mod.contribution_balance_receipt()

    assert receipt["status"] == mod.STATUS_ASSIGNED
    assert receipt["id"] == "PUBLIC-FACE-CONTRIBUTION-BALANCE"
    assert receipt["evidence"]["shares"]["reviews"] == 0.0061
    assert "substantive PR review" in receipt["assignment_packet"]["task"]
    assert "~/Workspace/limen/docs/github-contribution-balance.md" in receipt["existing_receipts"]
    assert "https://github.com/organvm/limen/issues/687" in receipt["existing_receipts"]


def test_credential_wall_receipt_requires_historical_tombstone(monkeypatch, tmp_path):
    mod = _load("always_working_credential_wall_uut", ALWAYS_WORKING)
    tombstone = tmp_path / "docs" / "credential-token-tombstone-audit.md"
    monkeypatch.setattr(mod, "CREDENTIAL_TOMBSTONE_DOC", tombstone)

    def fake_run(args, **kwargs):
        if "--census" in args:
            return {
                "returncode": 0,
                "stdout": json.dumps(
                    {
                        "hydration_lanes": 8,
                        "ci_runtime_secrets": 5,
                        "homeless_secret_atoms": 0,
                    }
                ),
                "stderr": "",
                "timed_out": False,
            }
        return {
            "returncode": 0,
            "stdout": "credential-wall: all secret atoms registered",
            "stderr": "",
            "timed_out": False,
        }

    monkeypatch.setattr(mod, "run_command", fake_run)

    receipt = mod.credential_wall_receipt()

    assert receipt["status"] == mod.STATUS_ASSIGNED
    assert receipt["evidence"]["historical_token_tombstone_doc_present"] is False
    assert "Never record secret values" in receipt["assignment_packet"]["task"]


def test_estate_custody_receipt_requires_implementation_receipts(monkeypatch, tmp_path):
    mod = _load("always_working_estate_custody_uut", ALWAYS_WORKING)
    root = tmp_path / "limen"
    archive = tmp_path / "Archive4T"
    ingress = tmp_path / "Ingress"
    scratch = tmp_path / "Scratch"
    t7 = tmp_path / "T7Recovery"
    lifeboat = t7 / "CleanUnique-Lifeboat-2026-06-13"

    for path in (
        archive / "_OPERATIONS",
        ingress,
        scratch,
        lifeboat / "00_SUBSTRATE",
        lifeboat / "10_PROFILE",
        lifeboat / "20_TEXT",
        lifeboat / "30_CODE",
        lifeboat / "_MANIFESTS",
        root / "docs",
    ):
        path.mkdir(parents=True, exist_ok=True)
    storage_manual = archive / "_OPERATIONS" / "STORAGE-OPERATING-MANUAL-2026-06-15.md"
    disk_policy = archive / "_OPERATIONS" / "LOCAL-DISK-EXPULSION-POLICY-2026-06-15.md"
    for path in (
        storage_manual,
        disk_policy,
        root / "docs" / "vltima-absorb-cadence.md",
        root / "docs" / "vltima-prior-excavations.md",
        root / "docs" / "photos-universe-recovery-2026-06-29.md",
        root / "docs" / "estate-custody-primitives.md",
    ):
        path.write_text("# receipt\n", encoding="utf-8")

    monkeypatch.setattr(mod, "ROOT", root)
    monkeypatch.setattr(mod, "ARCHIVE4T_ROOT", archive)
    monkeypatch.setattr(mod, "INGRESS_ROOT", ingress)
    monkeypatch.setattr(mod, "SCRATCH_ROOT", scratch)
    monkeypatch.setattr(mod, "T7RECOVERY_ROOT", t7)
    monkeypatch.setattr(mod, "T7_LIFEBOAT_ROOT", lifeboat)
    monkeypatch.setattr(mod, "ESTATE_CUSTODY_DOC", root / "docs" / "estate-custody-primitives.md")
    monkeypatch.setattr(mod, "ESTATE_CUSTODY_RECEIPT", root / "docs" / "estate-custody-implementation-receipts.json")
    monkeypatch.setattr(mod, "STORAGE_OPERATING_MANUAL", storage_manual)
    monkeypatch.setattr(mod, "LOCAL_DISK_EXPULSION_POLICY", disk_policy)

    receipt = mod.estate_custody_receipt()

    assert receipt["status"] == mod.STATUS_ASSIGNED
    assert receipt["evidence"]["volumes"]["Archive4T"] is True
    assert receipt["evidence"]["implementation_receipt_complete"] is False
    assert "thin hot cache" in receipt["assignment_packet"]["task"]


def test_estate_custody_receipt_accepts_owner_receipts_complete(monkeypatch, tmp_path):
    mod = _load("always_working_estate_complete_uut", ALWAYS_WORKING)
    root = tmp_path / "limen"
    archive = tmp_path / "Archive4T"
    ingress = tmp_path / "Ingress"
    scratch = tmp_path / "Scratch"
    t7 = tmp_path / "T7Recovery"
    lifeboat = t7 / "CleanUnique-Lifeboat-2026-06-13"

    for path in (
        archive / "_OPERATIONS",
        ingress,
        scratch,
        lifeboat / "00_SUBSTRATE",
        lifeboat / "10_PROFILE",
        lifeboat / "20_TEXT",
        lifeboat / "30_CODE",
        lifeboat / "_MANIFESTS",
        root / "docs",
    ):
        path.mkdir(parents=True, exist_ok=True)
    storage_manual = archive / "_OPERATIONS" / "STORAGE-OPERATING-MANUAL-2026-06-15.md"
    disk_policy = archive / "_OPERATIONS" / "LOCAL-DISK-EXPULSION-POLICY-2026-06-15.md"
    for path in (
        storage_manual,
        disk_policy,
        root / "docs" / "vltima-absorb-cadence.md",
        root / "docs" / "vltima-prior-excavations.md",
        root / "docs" / "photos-universe-recovery-2026-06-29.md",
        root / "docs" / "estate-custody-primitives.md",
    ):
        path.write_text("# receipt\n", encoding="utf-8")
    (root / "docs" / "estate-custody-implementation-receipts.json").write_text(
        json.dumps(
            {
                "status": "owner_receipts_complete",
                "complete": True,
                "receipts": [{"type": "doctrine", "path": "docs/estate-custody-primitives.md"}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "ROOT", root)
    monkeypatch.setattr(mod, "ARCHIVE4T_ROOT", archive)
    monkeypatch.setattr(mod, "INGRESS_ROOT", ingress)
    monkeypatch.setattr(mod, "SCRATCH_ROOT", scratch)
    monkeypatch.setattr(mod, "T7RECOVERY_ROOT", t7)
    monkeypatch.setattr(mod, "T7_LIFEBOAT_ROOT", lifeboat)
    monkeypatch.setattr(mod, "ESTATE_CUSTODY_DOC", root / "docs" / "estate-custody-primitives.md")
    monkeypatch.setattr(mod, "ESTATE_CUSTODY_RECEIPT", root / "docs" / "estate-custody-implementation-receipts.json")
    monkeypatch.setattr(mod, "STORAGE_OPERATING_MANUAL", storage_manual)
    monkeypatch.setattr(mod, "LOCAL_DISK_EXPULSION_POLICY", disk_policy)

    receipt = mod.estate_custody_receipt()

    assert receipt["status"] == mod.STATUS_DONE
    assert receipt["evidence"]["implementation_receipt_status"] == "owner_receipts_complete"
    assert receipt["evidence"]["implementation_receipt_complete"] is True


def test_mail_active_flagged_done_when_story_ledger_covers_current_flags(monkeypatch, tmp_path):
    mod = _load("always_working_mail_story_uut", ALWAYS_WORKING)
    root = tmp_path / "limen"
    mail_index = tmp_path / "Envelope Index"
    log_path = root / "logs" / "mail-story-ledger.json"

    root.mkdir()
    log_path.parent.mkdir()
    _mail_index(mail_index)
    log_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-07-07T20:00:00Z",
                "atom_count": 2,
                "mode": {
                    "scope": "flagged",
                    "read_only": True,
                    "body_reads": False,
                    "mailbox_mutations": False,
                    "gmail_writes": False,
                },
                "stats": {"flagged_non_deleted": 2},
                "clusters": [
                    {
                        "cluster_id": "billing-continuity",
                        "atom_count": 2,
                        "next_actions": {"human_review": 2},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "ROOT", root)
    monkeypatch.setattr(mod, "MAIL_INDEX", mail_index)
    monkeypatch.setattr(mod, "MAIL_STORY_LOG", log_path)
    monkeypatch.setattr(mod, "mail_census", lambda: {"ok": True, "account_count": 1, "obligation_count": 2})

    receipts = {item["id"]: item for item in mod.mail_receipts()}

    assert receipts["MAIL-ACTIVE-FLAGGED"]["status"] == mod.STATUS_DONE
    assert receipts["MAIL-ACTIVE-FLAGGED"]["evidence"]["mail_story"]["classified_current"] is True
    assert "classified into 1 clusters" in receipts["MAIL-ACTIVE-FLAGGED"]["verdict"]


def test_mail_historical_done_when_bounded_batch_is_atomized(monkeypatch, tmp_path):
    mod = _load("always_working_mail_history_uut", ALWAYS_WORKING)
    root = tmp_path / "limen"
    mail_index = tmp_path / "Envelope Index"
    log_path = root / "logs" / "mail-story-ledger.json"

    root.mkdir()
    log_path.parent.mkdir()
    _mail_index(mail_index)
    log_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-07-07T20:00:00Z",
                "atom_count": 3,
                "mode": {
                    "scope": "all",
                    "limit": 500,
                    "read_only": True,
                    "body_reads": False,
                    "mailbox_mutations": False,
                    "gmail_writes": False,
                },
                "stats": {"not_deleted_messages": 3, "flagged_non_deleted": 2},
                "clusters": [
                    {
                        "cluster_id": "billing-continuity",
                        "atom_count": 3,
                        "next_actions": {"human_review": 3},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "ROOT", root)
    monkeypatch.setattr(mod, "MAIL_INDEX", mail_index)
    monkeypatch.setattr(mod, "MAIL_STORY_LOG", log_path)
    monkeypatch.setattr(mod, "mail_census", lambda: {"ok": True, "account_count": 1, "obligation_count": 2})

    receipts = {item["id"]: item for item in mod.mail_receipts()}

    assert receipts["MAIL-HISTORICAL-BACKLOG"]["status"] == mod.STATUS_DONE
    assert receipts["MAIL-HISTORICAL-BACKLOG"]["evidence"]["mail_story"]["classified_current"] is True
    assert "bounded batch" in receipts["MAIL-HISTORICAL-BACKLOG"]["verdict"]


def test_repo_surface_done_when_fresh_duplicates_are_recorded(monkeypatch, tmp_path):
    mod = _load("always_working_repo_surface_uut", ALWAYS_WORKING)
    root = tmp_path / "limen"
    lifecycle = root / ".limen-private" / "session-corpus" / "lifecycle"
    index = lifecycle / "repo-surface-ledger.json"

    lifecycle.mkdir(parents=True)
    index.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                "repo_count": 300,
                "duplicate_remotes": [{"remote_hash": "abc", "repos": ["r1", "r2"]}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "ROOT", root)
    monkeypatch.setattr(mod, "REPO_SURFACE_INDEX", index)

    receipt = mod.repo_surface_receipt()

    assert receipt["status"] == mod.STATUS_DONE
    assert "duplicate remote group(s) recorded" in receipt["verdict"]


def test_value_repos_done_when_fresh_product_ledger_has_owner_receipts(monkeypatch, tmp_path):
    mod = _load("always_working_value_repos_uut", ALWAYS_WORKING)
    root = tmp_path / "limen"
    lifecycle = root / ".limen-private" / "session-corpus" / "lifecycle"
    value_repos = root / "value-repos.json"
    product_index = lifecycle / "product-ledger.json"
    repos = [
        "organvm/a-i-chat--exporter",
        "organvm/my-knowledge-base",
        "organvm/public-record-data-scrapper",
        "organvm/peer-audited--behavioral-blockchain",
        "organvm/mirror-mirror",
        "organvm/universal-mail--automation",
    ]
    products = [
        {
            "source_kind": "repo",
            "owner": repo,
            "state": "ship",
            "disposition": "sell-ready",
            "outward_path": "seo-proof",
        }
        for repo in repos
    ]
    products.extend(
        {
            "source_kind": "task",
            "owner": repo,
            "state": "verify",
            "disposition": "verify",
            "outward_path": "revenue-path",
        }
        for repo in repos[:5]
    )

    lifecycle.mkdir(parents=True)
    value_repos.write_text(json.dumps({"repos": repos}), encoding="utf-8")
    product_index.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                "next_unblocked": [{"id": "p1"}],
                "products": products,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "ROOT", root)
    monkeypatch.setattr(mod, "VALUE_REPOS", value_repos)
    monkeypatch.setattr(mod, "PRODUCT_LEDGER_INDEX", product_index)

    receipt = mod.value_repo_receipt()

    assert receipt["status"] == mod.STATUS_DONE
    assert receipt["evidence"]["sell_ready_value_repo_count"] == len(repos)
    assert receipt["evidence"]["missing_top_value_receipts"] == []


def test_tabularius_status_writers_done_when_owner_recorded(monkeypatch, tmp_path):
    mod = _load("always_working_tabularius_owner_record_uut", ALWAYS_WORKING)
    root = tmp_path / "limen"
    docs = root / "docs"
    logs = root / "logs"
    docs.mkdir(parents=True)
    logs.mkdir()
    (docs / "tabularius-record-keeper.md").write_text(
        "- [x] Step 2.2 owner-recorded\n- [ ] Step 2.2A — convert async reserve/reap/heal transitions\n",
        encoding="utf-8",
    )
    (docs / "tabularius-writer-audit.md").write_text(
        "# Tabularius Writer Audit\n\n<!-- tabularius-writer-audit:owner-recorded -->\n\nUnclassified calls: `0`\n",
        encoding="utf-8",
    )
    (logs / "task-writer-audit.json").write_text(
        json.dumps(
            {
                "direct_writer_count": 22,
                "owner_packet_counts": {
                    "TAB-STATUS-ASYNC-HEAL": 4,
                    "TAB-UNCLASSIFIED-WRITER": 0,
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "ROOT", root)

    receipt = mod.tabularius_receipt()

    assert receipt["status"] == mod.STATUS_DONE
    assert receipt["evidence"]["writer_audit_owner_recorded"] is True
    assert receipt["evidence"]["step_2_2_open"] is False


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
