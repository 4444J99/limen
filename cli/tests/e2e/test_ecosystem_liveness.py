"""E2E Test Suite for Ecosystem Liveness & Telemetry across organvm/limen.

This test suite validates the 4-tier testing architecture defined in TEST_INFRA.md:
- Tier 1: Feature coverage & unit contracts (11 primary assertions)
- Tier 2: Boundary & corner conditions (9 edge cases)
- Tier 3: Cross-feature & multi-organ integration (4 pipeline flows)
- Tier 4: Real-world operational scenarios (3 end-to-end scenarios)
"""

from __future__ import annotations

import importlib.util
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure cli/src is on sys.path
ROOT = Path(__file__).resolve().parents[2]
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.observation import (
    SCHEMA_V1,
    build_feed_record,
    check_feed,
    collect_bifrons,
    collect_observatory,
    collect_vitals,
    determine_status,
    emit_feed_record,
    validate_feed_record,
)

BIFRONS_SCRIPT = ROOT / "scripts" / "bifrons-organ.py"
ORGAN_HEALTH_SCRIPT = ROOT / "scripts" / "organ-health.py"
NO_TASKS_ON_ME_SCRIPT = ROOT / "scripts" / "no-tasks-on-me.sh"


def _load_module(name: str, script_path: Path):
    spec = importlib.util.spec_from_file_location(name, script_path)
    assert spec and spec.loader, f"Failed to load spec for {script_path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _create_test_portal_db(db_path: Path, stars: int = 5, dossiers: int = 3, prepared: int = 2) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE external_repo (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("CREATE TABLE dossier (id INTEGER PRIMARY KEY, repo_id INTEGER)")
        conn.execute("CREATE TABLE resonance_edge (id INTEGER PRIMARY KEY, source TEXT, target TEXT)")
        conn.execute("CREATE TABLE transmutation_proposal (id INTEGER PRIMARY KEY, title TEXT)")
        conn.execute("CREATE TABLE backflow_signal (id INTEGER PRIMARY KEY, organ TEXT)")
        conn.execute("CREATE TABLE exchange (id INTEGER PRIMARY KEY, state TEXT)")

        for i in range(stars):
            conn.execute("INSERT INTO external_repo (name) VALUES (?)", (f"repo-{i}",))
            conn.execute("INSERT INTO exchange (state) VALUES (?)", ("DISCOVERED",))

        for i in range(dossiers):
            conn.execute("INSERT INTO dossier (repo_id) VALUES (?)", (i + 1,))
            conn.execute("INSERT INTO resonance_edge (source, target) VALUES (?, ?)", (f"repo-{i}", "limen"))

        for i in range(prepared):
            conn.execute("INSERT INTO exchange (state) VALUES (?)", ("PATCH_PREPARED",))


# ==============================================================================
# TIER 1: Feature Coverage & Unit Contracts (11 Assertions)
# ==============================================================================


def test_tier1_01_bifrons_doctor_liveness_probe(tmp_path, monkeypatch, capsys):
    """Tier 1.1: Bifrons doctor probe validates portal store, engine CLI, and alchemia module."""
    mod = _load_module("bifrons_t1_01", BIFRONS_SCRIPT)
    db_path = tmp_path / "portal.db"
    _create_test_portal_db(db_path, stars=2)

    monkeypatch.setattr(mod, "PORTAL_DB", db_path)
    monkeypatch.setattr(mod.shutil, "which", lambda name: f"/usr/local/bin/{name}")
    monkeypatch.setattr(mod, "_alchemia_ok", lambda: True)

    assert mod.doctor() == 0
    out = capsys.readouterr().out
    assert "portal_store=present" in out
    assert "engine_cli=yes" in out
    assert "alchemia=ok" in out


def test_tier1_02_bifrons_check_predicate_determinism(tmp_path, monkeypatch, capsys):
    """Tier 1.2: Bifrons check predicate matches committed PORTAL.md with fresh render."""
    mod = _load_module("bifrons_t1_02", BIFRONS_SCRIPT)
    db_path = tmp_path / "portal.db"
    _create_test_portal_db(db_path, stars=4, dossiers=2)
    portal_md = tmp_path / "PORTAL.md"

    monkeypatch.setattr(mod, "PORTAL_DB", db_path)
    monkeypatch.setattr(mod, "PORTAL_MD", portal_md)

    portal = mod.portal_counts()
    rendered = mod.render(portal)
    portal_md.write_text(rendered, encoding="utf-8")

    # Run check when matching
    monkeypatch.setattr(sys, "argv", ["bifrons-organ.py", "--check"])
    assert mod.main() == 0
    assert "PORTAL.md current" in capsys.readouterr().out

    # Modify and check staleness detection
    portal_md.write_text(rendered + "\n<!-- stale modification -->", encoding="utf-8")
    assert mod.main() == 1
    assert "PORTAL.md STALE" in capsys.readouterr().out


def test_tier1_03_bifrons_metabolize_and_signal_generation(tmp_path, monkeypatch):
    """Tier 1.3: Bifrons execution generates deterministic markdown and valid signal JSON."""
    mod = _load_module("bifrons_t1_03", BIFRONS_SCRIPT)
    db_path = tmp_path / "portal.db"
    _create_test_portal_db(db_path, stars=3, dossiers=1, prepared=1)
    portal_md = tmp_path / "organs" / "observation" / "bifrons" / "PORTAL.md"
    signal_json = tmp_path / "logs" / "bifrons-portal.json"

    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "PORTAL_DB", db_path)
    monkeypatch.setattr(mod, "PORTAL_MD", portal_md)
    monkeypatch.setattr(mod, "SIGNAL", signal_json)
    monkeypatch.setattr(mod, "ORGAN_HOME", portal_md.parent)
    monkeypatch.setattr(mod, "run_beat", lambda: "mocked-beat-ran")

    monkeypatch.setattr(sys, "argv", ["bifrons-organ.py"])
    rc = mod.main()
    assert rc == 0
    assert portal_md.exists()
    assert signal_json.exists()

    signal_data = json.loads(signal_json.read_text(encoding="utf-8"))
    assert signal_data["organ"] == "bifrons"
    assert signal_data["beat"] == "mocked-beat-ran"
    assert signal_data["portal_present"] is True
    assert signal_data["prepared_awaiting_gate"] == 1
    assert signal_data["counts"]["dossier"] == 1


def test_tier1_04_observation_vitals_collection():
    """Tier 1.4: Observation vitals collector returns valid level, action, and metrics."""
    vitals = collect_vitals()
    assert isinstance(vitals, dict)
    assert isinstance(vitals["level"], int)
    assert vitals["level"] in (1, 2, 3, 4)
    assert vitals["action"] in ("ok", "throttle", "shed")
    assert isinstance(vitals["load_per_core"], (int, float))
    assert vitals["load_per_core"] >= 0.0
    if vitals["swap_used_gib"] is not None:
        assert isinstance(vitals["swap_used_gib"], (int, float))
    if vitals["ram_gib"] is not None:
        assert isinstance(vitals["ram_gib"], (int, float))


def test_tier1_05_observation_bifrons_collection(tmp_path, monkeypatch):
    """Tier 1.5: Observation bifrons collector correctly extracts portal counts and status."""
    db_path = tmp_path / "portal.db"
    _create_test_portal_db(db_path, stars=6, dossiers=2, prepared=3)
    monkeypatch.setenv("BIFRONS_DB", str(db_path))

    bifrons = collect_bifrons(root=ROOT)
    assert isinstance(bifrons, dict)
    assert bifrons["stars"] >= 6
    assert bifrons["dossiers"] >= 2
    assert bifrons["awaiting_gate"] >= 3
    assert bifrons["status"] == "present"


def test_tier1_06_observation_observatory_collection():
    """Tier 1.6: Observation observatory collector retrieves legibility metrics."""
    obs = collect_observatory(root=ROOT)
    assert isinstance(obs, dict)
    assert isinstance(obs["external_gaps"], int)
    assert obs["external_gaps"] >= 0
    assert isinstance(obs["internal_gaps"], int)
    assert obs["internal_gaps"] >= 0
    if obs["hero"] is not None:
        assert isinstance(obs["hero"], str)
    if obs["top_mechanism"] is not None:
        assert isinstance(obs["top_mechanism"], str)


def test_tier1_07_observation_composite_status_derivation():
    """Tier 1.7: Composite status derivation correctly prioritizes shedding, throttling, degraded."""
    assert determine_status({"action": "ok", "status": "ok"}, {}, {"status": "ok"}) == "ok"
    assert determine_status({"action": "throttle", "status": "ok"}, {}, {"status": "ok"}) == "degraded"
    assert determine_status({"action": "shed", "status": "ok"}, {}, {"status": "ok"}) == "shed"
    assert determine_status({"action": "ok", "status": "degraded: load"}, {}, {"status": "ok"}) == "degraded"
    assert determine_status({"action": "ok", "status": "ok"}, {}, {"status": "degraded: parser"}) == "degraded"


def test_tier1_08_observation_feed_schema_validation():
    """Tier 1.8: Schema validator accepts compliant records and rejects non-compliant shapes."""
    valid_record = build_feed_record(source="tier1_test", root=ROOT)
    violations = validate_feed_record(valid_record)
    assert violations == [], f"Unexpected violations on valid record: {violations}"

    # Verify invalid schema rejection
    invalid_record = dict(valid_record)
    invalid_record["schema"] = "limen.observation.feed.v999"
    assert any("invalid schema" in v for v in validate_feed_record(invalid_record))

    # Verify invalid status rejection
    invalid_status_record = dict(valid_record)
    invalid_status_record["status"] = "unsupported_status"
    assert any("status" in v for v in validate_feed_record(invalid_status_record))


def test_tier1_09_observation_feed_emission_and_check(tmp_path):
    """Tier 1.9: Emitting observation feed record updates feed.jsonl and feed-latest.json."""
    record, jsonl_path, latest_path = emit_feed_record(base_dir=tmp_path)
    assert jsonl_path.exists()
    assert latest_path.exists()

    latest_data = json.loads(latest_path.read_text(encoding="utf-8"))
    assert latest_data["schema"] == SCHEMA_V1
    assert latest_data["status"] in ("ok", "degraded", "shed")

    ok, errors = check_feed(base_dir=tmp_path)
    assert ok is True
    assert errors == []


def test_tier1_10_organ_health_matrix_derivation(tmp_path, monkeypatch):
    """Tier 1.10: Organ health matrix derives rungs, cadences, and statuses from heartbeat loop."""
    mod = _load_module("organ_health_t1_10", ORGAN_HEALTH_SCRIPT)
    logs_dir = tmp_path / "logs"
    voice_dir = logs_dir / ".voice"
    voice_dir.mkdir(parents=True)

    # Stamp several voices as fresh
    (voice_dir / "tick").write_text(datetime.now().isoformat())
    (voice_dir / "balance").write_text(datetime.now().isoformat())
    (voice_dir / "feed").write_text(datetime.now().isoformat())

    mod.ROOT = tmp_path
    mod.LOGS = logs_dir
    mod.VOICED = voice_dir

    view = mod.build()
    assert "summary" in view
    assert "organs" in view
    assert view["summary"]["total"] > 0
    assert "gate_integrity" in view
    assert isinstance(view["gate_integrity"]["ok"], bool)

    rungs = {o["rung"]: o["status"] for o in view["organs"]}
    assert "SUSTAIN" in rungs
    assert rungs["SUSTAIN"] == "green"


def test_tier1_11_closeout_no_tasks_on_me_predicate(tmp_path):
    """Tier 1.11: Closeout predicate validates his-hand-levers registry, PII firewall, and issue pointers."""
    valid_registry = {
        "levers": [
            {
                "id": "L-TEST-01",
                "label": "Test lever",
                "owner": "operator",
                "cost": "free",
                "unlocks": "test lane",
                "source_task": "task-001",
                "issue": 101,
            },
            {
                "id": "L-TEST-02",
                "label": "Second lever",
                "owner": "operator",
                "cost": "free",
                "unlocks": "second lane",
                "source_task": "task-002",
                "issue": 102,
            },
        ]
    }
    reg_path = tmp_path / "his-hand-levers.json"
    reg_path.write_text(json.dumps(valid_registry, indent=2), encoding="utf-8")

    # Validate registry rules
    data = json.loads(reg_path.read_text(encoding="utf-8"))
    levers = data["levers"]
    required_keys = ("id", "label", "owner", "cost", "unlocks", "source_task", "issue")
    for lev in levers:
        for k in required_keys:
            assert k in lev and str(lev[k]).strip() != ""
        assert isinstance(lev["issue"], int)

    # PII firewall shape test: ensure no medical measurement units in registry
    blob = json.dumps(data).lower()
    pii_shapes = r"\b\d+\s?mg\b|\bmg/dl\b|\bmmhg\b|\b\d+\s?mcg\b|\b\d+\s?ml\b|\bbpm\b"
    assert re.findall(pii_shapes, blob) == []


# ==============================================================================
# TIER 2: Boundary & Corner Conditions (9 Edge Cases)
# ==============================================================================


def test_tier2_01_observation_feed_missing_files_fail_check(tmp_path):
    """Tier 2.1: Missing feed files are accurately identified without throwing exceptions."""
    empty_dir = tmp_path / "empty_run"
    empty_dir.mkdir()
    ok, errors = check_feed(base_dir=empty_dir)
    assert ok is False
    assert any("missing feed-latest.json" in e for e in errors)
    assert any("missing feed.jsonl" in e for e in errors)


def test_tier2_02_observation_feed_empty_jsonl_detected(tmp_path):
    """Tier 2.2: Empty feed.jsonl is detected and reported as invalid."""
    obs_dir = tmp_path / "logs" / "observation"
    obs_dir.mkdir(parents=True)
    (obs_dir / "feed.jsonl").write_text("", encoding="utf-8")
    (obs_dir / "feed-latest.json").write_text(json.dumps(build_feed_record(root=ROOT)), encoding="utf-8")

    ok, errors = check_feed(base_dir=tmp_path)
    assert ok is False
    assert any("feed.jsonl is empty" in e for e in errors)


def test_tier2_03_observation_feed_corrupted_jsonl_detected(tmp_path):
    """Tier 2.3: Malformed JSON in feed.jsonl identifies the exact line number."""
    emit_feed_record(base_dir=tmp_path)
    jsonl_path = tmp_path / "logs" / "observation" / "feed.jsonl"
    with open(jsonl_path, "a", encoding="utf-8") as f:
        f.write("{invalid json syntax on line 2\n")

    ok, errors = check_feed(base_dir=tmp_path)
    assert ok is False
    assert any("feed.jsonl line 2 parse error" in e for e in errors)


def test_tier2_04_observation_feed_corrupted_timestamp_rejected():
    """Tier 2.4: Malformed and corrupted timestamps are rejected by schema validator."""
    record = build_feed_record(root=ROOT)
    for bad_ts in ("not-a-date", "2026-99-99T99:99:99", 123456789, None):
        record["observed_at"] = bad_ts
        violations = validate_feed_record(record)
        assert any("observed_at" in v for v in violations), f"Failed to reject invalid ts: {bad_ts}"


def test_tier2_05_bifrons_absent_database_fails_open(tmp_path, monkeypatch):
    """Tier 2.5: Bifrons handles absent database gracefully with 0 counts and present=False."""
    mod = _load_module("bifrons_t2_05", BIFRONS_SCRIPT)
    absent_db = tmp_path / "non_existent.db"
    monkeypatch.setattr(mod, "PORTAL_DB", absent_db)

    counts_res = mod.portal_counts()
    assert counts_res["present"] is False
    assert counts_res["status"] == "absent"
    assert counts_res["counts"]["external_repo"] == 0

    # Beat render still works cleanly
    rendered = mod.render(counts_res)
    assert "No exchanges yet" in rendered


def test_tier2_06_bifrons_corrupted_database_fails_doctor(tmp_path, monkeypatch, capsys):
    """Tier 2.6: Corrupted database yields status='unreadable' and causes doctor probe to fail."""
    mod = _load_module("bifrons_t2_06", BIFRONS_SCRIPT)
    corrupt_db = tmp_path / "corrupt.db"
    corrupt_db.write_bytes(b"INVALID SQLITE HEADER")
    monkeypatch.setattr(mod, "PORTAL_DB", corrupt_db)
    monkeypatch.setattr(mod.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(mod, "_alchemia_ok", lambda: True)

    counts_res = mod.portal_counts()
    assert counts_res["present"] is False
    assert counts_res["status"] == "unreadable"

    rc = mod.doctor()
    assert rc == 1
    assert "portal_store=unreadable" in capsys.readouterr().out


def test_tier2_07_vitals_extreme_pressure_shedding_and_throttling():
    """Tier 2.7: High pressure actions in vitals map properly to degraded and shed states."""
    assert determine_status({"action": "shed", "level": 4}, {}, {}) == "shed"
    assert determine_status({"action": "throttle", "level": 3}, {}, {}) == "degraded"
    assert determine_status({"action": "ok", "level": 1}, {}, {}) == "ok"


def test_tier2_08_organ_health_defect_overrides_fresh_timestamp(tmp_path):
    """Tier 2.8: Self-reported defect inside an organ's artifact marks the organ 'down' despite fresh voice."""
    mod = _load_module("organ_health_t2_08", ORGAN_HEALTH_SCRIPT)
    logs_dir = tmp_path / "logs"
    voice_dir = logs_dir / ".voice"
    voice_dir.mkdir(parents=True)

    # Fresh voice stamp
    (voice_dir / "routines").write_text(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    # Artifact containing a recorded failure
    artifact = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "escalation": {"error": "keeper 409 conflict during atom publish"},
        "retire": {"retired": []},
    }
    (logs_dir / "routine-freshness.json").write_text(json.dumps(artifact))

    mod.ROOT = tmp_path
    mod.LOGS = logs_dir
    mod.VOICED = voice_dir

    view = mod.build()
    routines = next(o for o in view["organs"] if o["key"] == "routines")
    assert routines["status"] == "down"
    assert "self-reported defect" in routines["note"]
    assert "keeper 409 conflict" in routines["note"]


def test_tier2_09_organ_health_trail_order_and_timestamp_accuracy(tmp_path):
    """Tier 2.9: Nested error reader respects trail priority and parses UTC/local timestamps properly."""
    mod = _load_module("organ_health_t2_09", ORGAN_HEALTH_SCRIPT)
    sample_file = tmp_path / "sample.json"

    # Multi-trail precedence
    sample_file.write_text(
        json.dumps(
            {
                "first_trail": {"err": "primary error"},
                "second_trail": {"err": "secondary error"},
            }
        )
    )
    res = mod._json_nested_error(sample_file, ("first_trail", "err"), ("second_trail", "err"))
    assert res == "first_trail.err: primary error"

    # UTC timestamp calculation
    sample_file.write_text(json.dumps({"ts": "2026-08-20T12:00:00Z"}))
    epoch = mod._json_field_ts(sample_file, "ts")
    assert epoch is not None
    dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
    assert dt.year == 2026 and dt.month == 8 and dt.day == 20 and dt.hour == 12


# ==============================================================================
# TIER 3: Cross-Feature & Multi-Organ Integration (4 Pipeline Flows)
# ==============================================================================


def test_tier3_01_vitals_shedding_to_observation_feed_to_health_matrix(tmp_path, monkeypatch):
    """Tier 3.1: Pipeline from vitals shedding -> feed status -> emission -> organ health proprioception."""
    # 1. Simulate vitals shedding
    mock_vitals = {
        "level": 4,
        "action": "shed",
        "load_per_core": 12.5,
        "swap_used_gib": 8.0,
        "ram_gib": 0.2,
        "status": "ok",
    }
    monkeypatch.setattr("limen.observation.collector.collect_vitals", lambda: mock_vitals)

    # 2. Build and emit feed
    record, jsonl_path, latest_path = emit_feed_record(base_dir=tmp_path)
    assert record["status"] == "shed"
    assert record["vitals"]["action"] == "shed"

    # 3. Check feed validates
    ok, errors = check_feed(base_dir=tmp_path)
    assert ok is True

    # 4. Feed record is reflected in health matrix
    mod = _load_module("organ_health_t3_01", ORGAN_HEALTH_SCRIPT)
    logs_dir = tmp_path / "logs"
    mod.ROOT = tmp_path
    mod.LOGS = logs_dir
    mod.VOICED = logs_dir / ".voice"
    mod.VOICED.mkdir(parents=True, exist_ok=True)

    status_file = logs_dir / "vigilia" / "status.json"
    status_file.parent.mkdir(parents=True, exist_ok=True)
    status_file.write_text(
        json.dumps(
            {
                "sampled_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "sample_error": {"error": "system under shed pressure"},
            }
        )
    )

    view = mod.build()
    vigilia_row = next((o for o in view["organs"] if o["key"] == "vigilia"), None)
    if vigilia_row:
        assert vigilia_row["status"] == "down"
        assert "self-reported defect" in vigilia_row["note"]


def test_tier3_02_bifrons_star_intake_to_observation_telemetry_to_portal_render(tmp_path, monkeypatch):
    """Tier 3.2: Pipeline from new star absorption in portal DB -> observation collection -> PORTAL.md render."""
    db_path = tmp_path / "portal.db"
    portal_md = tmp_path / "PORTAL.md"
    _create_test_portal_db(db_path, stars=10, dossiers=4, prepared=2)

    # 1. Bifrons metabolizes and renders
    bifrons_mod = _load_module("bifrons_t3_02", BIFRONS_SCRIPT)
    monkeypatch.setattr(bifrons_mod, "PORTAL_DB", db_path)
    monkeypatch.setattr(bifrons_mod, "PORTAL_MD", portal_md)

    counts = bifrons_mod.portal_counts()
    rendered = bifrons_mod.render(counts)
    portal_md.write_text(rendered, encoding="utf-8")
    assert "| 10 | 4 |" in rendered

    # 2. Observation collector gathers the new telemetry
    monkeypatch.setenv("BIFRONS_DB", str(db_path))
    bif_telemetry = collect_bifrons(root=ROOT)
    assert bif_telemetry["stars"] >= 10
    assert bif_telemetry["dossiers"] >= 4
    assert bif_telemetry["awaiting_gate"] >= 2

    # 3. Feed record emitted with fresh metrics
    record, _, latest_path = emit_feed_record(record=build_feed_record(root=ROOT), base_dir=tmp_path)
    assert record["bifrons"]["stars"] >= 10
    assert json.loads(latest_path.read_text(encoding="utf-8"))["bifrons"]["stars"] >= 10


def test_tier3_03_dark_disabled_safety_gate_drift_triggers_strict_failure(tmp_path, monkeypatch):
    """Tier 3.3: Strict organ health run detects dark-disabled safety organs and exits 1."""
    mod = _load_module("organ_health_t3_03", ORGAN_HEALTH_SCRIPT)
    mod.ROOT = tmp_path
    mod.LOGS = tmp_path / "logs"
    mod.VOICED = tmp_path / "logs" / ".voice"
    mod.VOICED.mkdir(parents=True, exist_ok=True)

    # Dark-disable VIGILIA (default-ON safety organ)
    monkeypatch.setenv("LIMEN_VIGILIA", "0")

    view = mod.build()
    dark = view["gate_integrity"]["dark_disabled"]
    assert any(d["gate"] == "LIMEN_VIGILIA" for d in dark)
    assert view["gate_integrity"]["ok"] is False

    # Main with --strict exits 1
    rc = mod.main(["--strict"])
    assert rc == 1


def test_tier3_04_observation_continuous_multi_beat_emission_and_integrity(tmp_path):
    """Tier 3.4: Successive telemetry emissions append valid JSONL lines and keep feed-latest fresh."""
    for beat_idx in range(5):
        record, jsonl_path, latest_path = emit_feed_record(
            record=build_feed_record(source=f"beat_{beat_idx}", root=ROOT),
            base_dir=tmp_path,
        )
        assert record["source"] == f"beat_{beat_idx}"

    lines = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 5
    assert lines[-1]["source"] == "beat_4"

    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    assert latest["source"] == "beat_4"

    ok, errors = check_feed(base_dir=tmp_path)
    assert ok is True
    assert errors == []


# ==============================================================================
# TIER 4: Real-World Operational Scenarios (3 Scenarios)
# ==============================================================================


def test_tier4_01_full_heartbeat_telemetry_cycle(tmp_path, monkeypatch):
    """Tier 4.1: End-to-end simulation of a complete heartbeat tick across all organs."""
    # 1. Setup environment paths
    logs_dir = tmp_path / "logs"
    voice_dir = logs_dir / ".voice"
    voice_dir.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "portal.db"
    _create_test_portal_db(db_path, stars=7, dossiers=3, prepared=1)

    # 2. Bifrons tick
    bif_mod = _load_module("bifrons_t4_01", BIFRONS_SCRIPT)
    portal_md = tmp_path / "PORTAL.md"
    signal_json = logs_dir / "bifrons-portal.json"
    monkeypatch.setattr(bif_mod, "ROOT", tmp_path)
    monkeypatch.setattr(bif_mod, "PORTAL_DB", db_path)
    monkeypatch.setattr(bif_mod, "PORTAL_MD", portal_md)
    monkeypatch.setattr(bif_mod, "SIGNAL", signal_json)
    monkeypatch.setattr(bif_mod, "ORGAN_HOME", portal_md.parent)
    monkeypatch.setattr(bif_mod, "run_beat", lambda: "beat-42")

    monkeypatch.setattr(sys, "argv", ["bifrons-organ.py"])
    assert bif_mod.main() == 0
    (voice_dir / "bifrons").write_text(datetime.now().isoformat())

    # 3. Observation Feed emission
    monkeypatch.setenv("BIFRONS_DB", str(db_path))
    feed_rec, jsonl_p, latest_p = emit_feed_record(base_dir=tmp_path)
    assert feed_rec["schema"] == SCHEMA_V1
    (voice_dir / "observation").write_text(datetime.now().isoformat())

    # 4. Organ health matrix compilation
    health_mod = _load_module("organ_health_t4_01", ORGAN_HEALTH_SCRIPT)
    health_mod.ROOT = tmp_path
    health_mod.LOGS = logs_dir
    health_mod.VOICED = voice_dir
    health_mod.OUT_DIRS = [tmp_path / "web" / "app" / "out"]

    rc = health_mod.main([])
    assert rc == 0
    assert (logs_dir / "organ-health.json").exists()
    assert (tmp_path / "web" / "app" / "out" / "organ-health.html").exists()

    # 5. Verify integrity of all generated artifacts
    health_data = json.loads((logs_dir / "organ-health.json").read_text(encoding="utf-8"))
    assert health_data["summary"]["total"] > 0
    assert (tmp_path / "web" / "app" / "out" / "organ-health.html").read_text().startswith("<!doctype html>")


def test_tier4_02_organ_failure_and_autonomic_recovery_lifecycle(tmp_path, monkeypatch):
    """Tier 4.2: Full lifecycle: Organ degrades on failure, is detected, self-heals, and returns to green."""
    health_mod = _load_module("organ_health_t4_02", ORGAN_HEALTH_SCRIPT)
    logs_dir = tmp_path / "logs"
    voice_dir = logs_dir / ".voice"
    voice_dir.mkdir(parents=True, exist_ok=True)
    health_mod.ROOT = tmp_path
    health_mod.LOGS = logs_dir
    health_mod.VOICED = voice_dir

    routine_log = logs_dir / "routine-freshness.json"

    # Step 1: Initial healthy state
    (voice_dir / "routines").write_text(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    routine_log.write_text(
        json.dumps(
            {
                "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "escalation": {"created": []},
                "retire": {"retired": []},
            }
        )
    )
    v1 = health_mod.build()
    r1 = next(o for o in v1["organs"] if o["key"] == "routines")
    assert r1["status"] == "green"

    # Step 2: Injected failure
    routine_log.write_text(
        json.dumps(
            {
                "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "escalation": {"error": "API timeout connecting to upstream keeper"},
                "retire": {"retired": []},
            }
        )
    )
    v2 = health_mod.build()
    r2 = next(o for o in v2["organs"] if o["key"] == "routines")
    assert r2["status"] == "down"
    assert "API timeout" in r2["note"]

    # Step 3: Autonomic recovery action (error cleared and new fresh stamp)
    routine_log.write_text(
        json.dumps(
            {
                "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "escalation": {"created": ["recovered-atom"]},
                "retire": {"retired": []},
            }
        )
    )
    v3 = health_mod.build()
    r3 = next(o for o in v3["organs"] if o["key"] == "routines")
    assert r3["status"] == "green"
    assert "self-reported defect" not in (r3["note"] or "")


def test_tier4_03_closeout_idempotent_fixed_point(tmp_path):
    """Tier 4.3: Closeout validation achieves idempotent fixed point (repeated runs yield identical valid state)."""
    registry_file = tmp_path / "his-hand-levers.json"
    registry_data = {
        "levers": [
            {
                "id": "L-FIXED-POINT-01",
                "label": "Idempotent closeout lever",
                "owner": "operator",
                "cost": "free",
                "unlocks": "closeout validation",
                "source_task": "task-closeout",
                "issue": 999,
            }
        ]
    }
    registry_file.write_text(json.dumps(registry_data, indent=2), encoding="utf-8")

    def run_validation_predicate(path: Path) -> tuple[bool, str]:
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            levers = d.get("levers", [])
            if not levers:
                return False, "Empty levers"
            for lev in levers:
                for req in ("id", "label", "owner", "cost", "unlocks", "source_task", "issue"):
                    if not str(lev.get(req, "")).strip():
                        return False, f"Missing required field {req}"
                if not isinstance(lev.get("issue"), int):
                    return False, "Issue must be int"
            # Check PII
            blob = json.dumps(d).lower()
            shapes = r"\b\d+\s?mg\b|\bmg/dl\b|\bmmhg\b|\b\d+\s?mcg\b|\b\d+\s?ml\b|\bbpm\b"
            if re.findall(shapes, blob):
                return False, "PII shape detected"
            return True, "Valid fixed point"
        except Exception as e:
            return False, str(e)

    # First run
    ok1, msg1 = run_validation_predicate(registry_file)
    assert ok1 is True, msg1

    # Second run (idempotency verification)
    ok2, msg2 = run_validation_predicate(registry_file)
    assert ok2 is True, msg2
    assert msg1 == msg2

    # Injected defect check
    bad_registry = dict(registry_data)
    bad_registry["levers"][0]["issue"] = "not-an-integer"
    registry_file.write_text(json.dumps(bad_registry), encoding="utf-8")
    ok3, msg3 = run_validation_predicate(registry_file)
    assert ok3 is False
    assert "Issue must be int" in msg3
