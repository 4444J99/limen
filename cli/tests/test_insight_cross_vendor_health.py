"""Tests for the cross-vendor health sensor (insight-cross-vendor-ingest.py --health).

Every check runs against a synthetic packet/index estate under tmp_path (never the
live stores). The two load-bearing wiring tests are the deliverables the plan named:
the health packet must actually be CONSUMED by insight-cadence with its declared
owner/severity (else every finding strands below the issue-opening threshold), and
the ring-buffer state file must live in a SUBDIR so the packet glob never reads it
as a vendor packet.
"""

import importlib.util
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"

NOW = datetime.now(timezone.utc)
WINDOW = NOW - timedelta(days=30)


def _load(script: str, alias: str, limen_root: Path, monkeypatch):
    """Load a fresh module instance with LIMEN_ROOT pinned to a tmp estate —
    OUT_DIR/LOGS are computed at import time, so a shared instance would leak
    the real estate into a hermetic test."""
    monkeypatch.setenv("LIMEN_ROOT", str(limen_root))
    spec = importlib.util.spec_from_file_location(alias, _SCRIPTS / script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_packet(root: Path, vendor: str, *, run_at=None, sessions_seen=1, oldest=None, extra=None):
    out = root / "logs" / "insight-cross-vendor"
    out.mkdir(parents=True, exist_ok=True)
    packet = {
        "vendor": vendor,
        "description": "fixture",
        "run_at_iso": (run_at or NOW).isoformat(timespec="seconds"),
        "sessions_seen": sessions_seen,
        "friction_signals": [],
        "notable_patterns": [],
        "data_quality_notes": [],
    }
    if oldest is not None:
        packet["oldest_record_iso"] = oldest.isoformat(timespec="seconds")
    if extra:
        packet.update(extra)
    (out / f"{vendor}.json").write_text(json.dumps(packet))
    return out


def _health_doc(root: Path) -> dict:
    return json.loads((root / "logs" / "insight-cross-vendor" / "health.json").read_text())


def test_fresh_healthy_estate_is_quiet(tmp_path, monkeypatch):
    _write_packet(tmp_path, "codex", oldest=NOW - timedelta(days=400))
    monkeypatch.setenv("LIMEN_VENDOR_INSIGHTS_DIR", str(tmp_path / "logs" / "vendor-insights"))
    ingest = _load("insight-cross-vendor-ingest.py", "icvi_h1", tmp_path, monkeypatch)
    assert ingest.cmd_health() == 0
    doc = _health_doc(tmp_path)
    assert doc["friction_signals"] == []
    assert doc["data_quality_notes"] == ["all checks clean"]


def test_packet_stale_fires(tmp_path, monkeypatch):
    _write_packet(tmp_path, "gemini", run_at=NOW - timedelta(days=10), oldest=NOW - timedelta(days=400))
    monkeypatch.setenv("LIMEN_VENDOR_INSIGHTS_DIR", str(tmp_path / "logs" / "vendor-insights"))
    ingest = _load("insight-cross-vendor-ingest.py", "icvi_h2", tmp_path, monkeypatch)
    ingest.cmd_health()
    doc = _health_doc(tmp_path)
    assert any("gemini: packet_stale" in n for n in doc["data_quality_notes"])
    assert doc["friction_signals"][0]["count"] == 1


def test_store_reset_fires_against_ring_buffer_max(tmp_path, monkeypatch):
    out = _write_packet(tmp_path, "opencode", sessions_seen=5, oldest=NOW - timedelta(days=400))
    state_dir = out / "state"
    state_dir.mkdir()
    (state_dir / "health-state.json").write_text(
        json.dumps({"runs": [{"at": "2026-08-01T00:00:00+00:00", "sessions": {"opencode": 40}}]})
    )
    monkeypatch.setenv("LIMEN_VENDOR_INSIGHTS_DIR", str(tmp_path / "logs" / "vendor-insights"))
    ingest = _load("insight-cross-vendor-ingest.py", "icvi_h3", tmp_path, monkeypatch)
    ingest.cmd_health()
    doc = _health_doc(tmp_path)
    assert any("opencode: store_reset — sessions_seen 5 vs recent max 40" in n for n in doc["data_quality_notes"])


def test_store_reset_respects_min_base(tmp_path, monkeypatch):
    # A 10-session lane collapsing to 1 is noise, not a reset — below the base floor.
    out = _write_packet(tmp_path, "cline", sessions_seen=1, oldest=NOW - timedelta(days=400))
    state_dir = out / "state"
    state_dir.mkdir()
    (state_dir / "health-state.json").write_text(
        json.dumps({"runs": [{"at": "2026-08-01T00:00:00+00:00", "sessions": {"cline": 10}}]})
    )
    monkeypatch.setenv("LIMEN_VENDOR_INSIGHTS_DIR", str(tmp_path / "logs" / "vendor-insights"))
    ingest = _load("insight-cross-vendor-ingest.py", "icvi_h4", tmp_path, monkeypatch)
    ingest.cmd_health()
    doc = _health_doc(tmp_path)
    assert not any("store_reset" in n for n in doc["data_quality_notes"])


def test_retention_horizon_fires_for_young_oldest_record(tmp_path, monkeypatch):
    _write_packet(tmp_path, "antigravity", sessions_seen=60, oldest=NOW - timedelta(days=5))
    monkeypatch.setenv("LIMEN_VENDOR_INSIGHTS_DIR", str(tmp_path / "logs" / "vendor-insights"))
    ingest = _load("insight-cross-vendor-ingest.py", "icvi_h5", tmp_path, monkeypatch)
    ingest.cmd_health()
    doc = _health_doc(tmp_path)
    assert any("antigravity: retention_horizon" in n for n in doc["data_quality_notes"])


def test_retention_horizon_skips_empty_lanes(tmp_path, monkeypatch):
    # A dormant/empty lane has no history to lose — a young mtime there is registration, not pruning.
    _write_packet(tmp_path, "jules", sessions_seen=0, oldest=NOW - timedelta(days=1))
    monkeypatch.setenv("LIMEN_VENDOR_INSIGHTS_DIR", str(tmp_path / "logs" / "vendor-insights"))
    ingest = _load("insight-cross-vendor-ingest.py", "icvi_h6", tmp_path, monkeypatch)
    ingest.cmd_health()
    doc = _health_doc(tmp_path)
    assert not any("retention_horizon" in n for n in doc["data_quality_notes"])


def test_capsule_churn_fires_from_index_meta(tmp_path, monkeypatch):
    _write_packet(tmp_path, "codex", oldest=NOW - timedelta(days=400))
    vi_root = tmp_path / "logs" / "vendor-insights"
    codex_dir = vi_root / "codex"
    codex_dir.mkdir(parents=True)
    (codex_dir / "index.json").write_text(
        json.dumps({"meta": {"capsule_churn": {"mean_files_per_session": 4.38, "max_files_in_one_session": 35}}})
    )
    (codex_dir / "narrative.json").write_text("{}")
    monkeypatch.setenv("LIMEN_VENDOR_INSIGHTS_DIR", str(vi_root))
    ingest = _load("insight-cross-vendor-ingest.py", "icvi_h7", tmp_path, monkeypatch)
    ingest.cmd_health()
    doc = _health_doc(tmp_path)
    assert any("codex: capsule_churn — mean 4.38" in n for n in doc["data_quality_notes"])


def test_index_ahead_of_narrative_fires_when_never_narrated(tmp_path, monkeypatch):
    _write_packet(tmp_path, "copilot", oldest=NOW - timedelta(days=400))
    vi_root = tmp_path / "logs" / "vendor-insights"
    lane = vi_root / "copilot"
    lane.mkdir(parents=True)
    (lane / "index.json").write_text(json.dumps({"meta": {}}))
    monkeypatch.setenv("LIMEN_VENDOR_INSIGHTS_DIR", str(vi_root))
    ingest = _load("insight-cross-vendor-ingest.py", "icvi_h8", tmp_path, monkeypatch)
    ingest.cmd_health()
    doc = _health_doc(tmp_path)
    assert any("copilot: index_ahead_of_narrative" in n and "never narrated" in n for n in doc["data_quality_notes"])


def test_fresh_narrative_keeps_lane_quiet(tmp_path, monkeypatch):
    _write_packet(tmp_path, "claude", oldest=NOW - timedelta(days=400))
    vi_root = tmp_path / "logs" / "vendor-insights"
    lane = vi_root / "claude"
    lane.mkdir(parents=True)
    (lane / "index.json").write_text(json.dumps({"meta": {}}))
    (lane / "narrative.json").write_text("{}")
    now = time.time()
    os.utime(lane / "index.json", (now, now))
    os.utime(lane / "narrative.json", (now, now))
    monkeypatch.setenv("LIMEN_VENDOR_INSIGHTS_DIR", str(vi_root))
    ingest = _load("insight-cross-vendor-ingest.py", "icvi_h9", tmp_path, monkeypatch)
    ingest.cmd_health()
    doc = _health_doc(tmp_path)
    assert not any("index_ahead_of_narrative" in n for n in doc["data_quality_notes"])


def test_one_aggregate_signal_counts_affected_vendors(tmp_path, monkeypatch):
    _write_packet(tmp_path, "gemini", run_at=NOW - timedelta(days=10), oldest=NOW - timedelta(days=400))
    _write_packet(tmp_path, "antigravity", sessions_seen=60, oldest=NOW - timedelta(days=5))
    monkeypatch.setenv("LIMEN_VENDOR_INSIGHTS_DIR", str(tmp_path / "logs" / "vendor-insights"))
    ingest = _load("insight-cross-vendor-ingest.py", "icvi_h10", tmp_path, monkeypatch)
    ingest.cmd_health()
    doc = _health_doc(tmp_path)
    assert len(doc["friction_signals"]) == 1
    sig = doc["friction_signals"][0]
    assert sig["signal"] == "vendor_health"
    assert sig["count"] == 2
    assert doc["owner"] == "censor"
    assert doc["severity"] == "warning"
    assert doc["vendor"] == "cross-vendor-health"


def test_health_state_file_is_not_globbed_as_a_packet(tmp_path, monkeypatch):
    # The consumer (and cmd_health itself) glob logs/insight-cross-vendor/*.json —
    # a top-level state file would be read as a vendor packet named 'health-state'.
    out = _write_packet(tmp_path, "codex", oldest=NOW - timedelta(days=400))
    monkeypatch.setenv("LIMEN_VENDOR_INSIGHTS_DIR", str(tmp_path / "logs" / "vendor-insights"))
    ingest = _load("insight-cross-vendor-ingest.py", "icvi_h11", tmp_path, monkeypatch)
    ingest.cmd_health()
    state_path = out / "state" / "health-state.json"
    assert state_path.is_file()
    top_level = {p.name for p in out.glob("*.json")}
    assert "health-state.json" not in top_level
    # Second run: the ring buffer accumulated, and no 'health-state' vendor appeared.
    ingest.cmd_health()
    doc = _health_doc(tmp_path)
    assert not any("health-state" in n for n in doc["data_quality_notes"])
    assert len(json.loads(state_path.read_text())["runs"]) == 2


def test_health_packet_is_consumed_by_insight_cadence(tmp_path, monkeypatch):
    # The no-parallel-loop claim: health rides the EXISTING packet lane, and the
    # cadence organ honors the packet-declared owner/severity — without that,
    # every health finding strands at the organ inbox as info-owned-by-nobody.
    _write_packet(tmp_path, "gemini", run_at=NOW - timedelta(days=10), oldest=NOW - timedelta(days=400))
    monkeypatch.setenv("LIMEN_VENDOR_INSIGHTS_DIR", str(tmp_path / "logs" / "vendor-insights"))
    ingest = _load("insight-cross-vendor-ingest.py", "icvi_h12", tmp_path, monkeypatch)
    ingest.cmd_health()
    cadence = _load("insight-cadence.py", "icad_h12", tmp_path, monkeypatch)
    insights = cadence._gather_insights()
    health_insights = [i for i in insights if i["source"] == "insight-cross-vendor/health.json"]
    assert len(health_insights) == 1
    assert health_insights[0]["owner"] == "censor"
    assert health_insights[0]["severity"] == "warning"


def test_oldest_record_probe_seam(tmp_path, monkeypatch):
    ingest = _load("insight-cross-vendor-ingest.py", "icvi_h13", tmp_path, monkeypatch)
    ws = tmp_path / "cline-data" / "workspaces" / "ws-old"
    ws.mkdir(parents=True)
    old = (NOW - timedelta(days=90)).timestamp()
    os.utime(ws, (old, old))
    monkeypatch.setitem(ingest.VENDOR_REGISTRY["cline"], "path", tmp_path / "cline-data")
    iso = ingest._oldest_record_iso("cline")
    assert iso is not None and iso.startswith((NOW - timedelta(days=90)).date().isoformat())
    # No probe registered → None, never a crash.
    assert ingest._oldest_record_iso("jules") is None
    # A raising probe degrades to None (fail-open), never a crashed ingest.
    monkeypatch.setitem(ingest.OLDEST_PROBES, "cline", lambda: 1 / 0)
    assert ingest._oldest_record_iso("cline") is None
