"""Empirical Adversarial Challenge Suite for Milestone 1 Telemetry Components.

Stress-tests:
1. _alchemia_ok multi-tier probe under various hostile/failing environments
2. observation-feed & collector under subsystem failures, corruptions, and edge cases
3. Fail-open / graceful degradation invariants without crashing collector
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.observation import (  # noqa: E402
    SCHEMA_V1,
    build_feed_record,
    check_feed,
    collect_bifrons,
    collect_observatory,
    collect_vitals,
    emit_feed_record,
    validate_feed_record,
)

BIFRONS_SCRIPT = ROOT / "scripts" / "bifrons-organ.py"
FEED_SCRIPT = ROOT / "scripts" / "observation-feed.py"


def _load_bifrons_module():
    spec = importlib.util.spec_from_file_location("bifrons_module_challenge", BIFRONS_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ─────────────────────────────────────────────────────────────────────────────
# 1. Challenge _alchemia_ok under varying environment conditions
# ─────────────────────────────────────────────────────────────────────────────


class TestAlchemiaProbeStress:
    """Stress-test the 4-tier probe in _alchemia_ok()."""

    def test_tier1_direct_import_success(self, monkeypatch):
        mod = _load_bifrons_module()
        # Mock builtins.__import__ to allow 'alchemia'
        orig_import = __import__

        def custom_import(name, *args, **kwargs):
            if name == "alchemia":
                return MagicMock()
            return orig_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", custom_import)
        assert mod._alchemia_ok() is True

    def test_tier2_cli_success(self, monkeypatch):
        mod = _load_bifrons_module()
        # Disallow direct module import
        orig_import = __import__

        def failing_import(name, *args, **kwargs):
            if name == "alchemia":
                raise ImportError("No module named alchemia")
            return orig_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", failing_import)
        monkeypatch.setattr(mod.shutil, "which", lambda n: "/usr/local/bin/alchemia" if n == "alchemia" else None)

        def mock_run(cmd, **kwargs):
            if cmd[0] == "/usr/local/bin/alchemia" and "--help" in cmd:
                return subprocess.CompletedProcess(cmd, returncode=0, stdout=b"Alchemia CLI v1.0", stderr=b"")
            return subprocess.CompletedProcess(cmd, returncode=1, stdout=b"", stderr=b"error")

        monkeypatch.setattr(mod.subprocess, "run", mock_run)
        monkeypatch.setattr(mod.os.environ, "get", lambda k, d=None: None)
        assert mod._alchemia_ok() is True

    def test_tier2_cli_broken_returns_error_code(self, tmp_path, monkeypatch):
        """When CLI exits with non-zero (e.g. ModuleNotFoundError in shim), falls through."""
        mod = _load_bifrons_module()
        orig_import = __import__

        def failing_import(name, *args, **kwargs):
            if name == "alchemia":
                raise ImportError("No module named alchemia")
            return orig_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", failing_import)
        monkeypatch.setattr(mod.shutil, "which", lambda n: "/opt/homebrew/bin/alchemia" if n == "alchemia" else None)

        def broken_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, returncode=1, stdout=b"", stderr=b"ModuleNotFoundError: alchemia")

        monkeypatch.setattr(mod.subprocess, "run", broken_run)
        monkeypatch.setattr(mod.os.environ, "get", lambda k, d=None: None)
        monkeypatch.setattr(mod, "PORTAL_DB", tmp_path / "missing.db")

        assert mod._alchemia_ok() is False

    def test_tier2_cli_timeout_expired(self, tmp_path, monkeypatch):
        """When CLI hangs and triggers TimeoutExpired, handle cleanly and fall through."""
        mod = _load_bifrons_module()
        orig_import = __import__

        def failing_import(name, *args, **kwargs):
            if name == "alchemia":
                raise ImportError("No module named alchemia")
            return orig_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", failing_import)
        monkeypatch.setattr(mod.shutil, "which", lambda n: "/usr/bin/alchemia" if n == "alchemia" else None)

        def timeout_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=10)

        monkeypatch.setattr(mod.subprocess, "run", timeout_run)
        monkeypatch.setattr(mod.os.environ, "get", lambda k, d=None: None)
        monkeypatch.setattr(mod, "PORTAL_DB", tmp_path / "missing.db")

        assert mod._alchemia_ok() is False

    def test_tier2_cli_oserror_permission_denied(self, tmp_path, monkeypatch):
        """When CLI binary has corrupted permissions or cannot be executed."""
        mod = _load_bifrons_module()
        orig_import = __import__

        def failing_import(name, *args, **kwargs):
            if name == "alchemia":
                raise ImportError("No module named alchemia")
            return orig_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", failing_import)
        monkeypatch.setattr(mod.shutil, "which", lambda n: "/usr/bin/alchemia" if n == "alchemia" else None)

        def permission_run(cmd, **kwargs):
            raise PermissionError("[Errno 13] Permission denied: '/usr/bin/alchemia'")

        monkeypatch.setattr(mod.subprocess, "run", permission_run)
        monkeypatch.setattr(mod.os.environ, "get", lambda k, d=None: None)
        monkeypatch.setattr(mod, "PORTAL_DB", tmp_path / "missing.db")

        assert mod._alchemia_ok() is False

    def test_tier3_virtualenv_success(self, tmp_path, monkeypatch):
        mod = _load_bifrons_module()
        orig_import = __import__

        def failing_import(name, *args, **kwargs):
            if name == "alchemia":
                raise ImportError("No module named alchemia")
            return orig_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", failing_import)
        monkeypatch.setattr(mod.shutil, "which", lambda n: None)

        # Setup fake venv bin
        venv_bin_dir = tmp_path / "venv" / "bin"
        venv_bin_dir.mkdir(parents=True)
        venv_alchemia = venv_bin_dir / "alchemia"
        venv_alchemia.write_text("#!/bin/sh\nexit 0")
        venv_alchemia.chmod(0o755)

        monkeypatch.setattr(
            mod.os.environ, "get", lambda k, d=None: str(tmp_path / "venv") if k == "VIRTUAL_ENV" else d
        )

        def venv_run(cmd, **kwargs):
            if str(venv_alchemia) in cmd:
                return subprocess.CompletedProcess(cmd, returncode=0, stdout=b"OK", stderr=b"")
            return subprocess.CompletedProcess(cmd, returncode=1, stdout=b"", stderr=b"")

        monkeypatch.setattr(mod.subprocess, "run", venv_run)
        assert mod._alchemia_ok() is True

    def test_no_facade_fallback_when_alchemia_broken(self, tmp_path, monkeypatch):
        """When alchemia CLI is absent/broken, existence of organvm CLI and portal DB must NOT mask failure."""
        mod = _load_bifrons_module()
        orig_import = __import__

        def failing_import(name, *args, **kwargs):
            if name == "alchemia":
                raise ImportError("No module named alchemia")
            return orig_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", failing_import)
        # alchemia not on path, organvm is on path
        monkeypatch.setattr(mod.shutil, "which", lambda n: "/usr/local/bin/organvm" if n == "organvm" else None)
        monkeypatch.setattr(mod.os.environ, "get", lambda k, d=None: None)
        portal_db = tmp_path / "portal.db"
        portal_db.touch()
        monkeypatch.setattr(mod, "PORTAL_DB", portal_db)

        assert mod._alchemia_ok() is False

    def test_complete_probe_failure_returns_false_cleanly(self, tmp_path, monkeypatch):
        """When everything is missing or broken, _alchemia_ok returns False without raising exceptions."""
        mod = _load_bifrons_module()
        orig_import = __import__

        def failing_import(name, *args, **kwargs):
            if name == "alchemia":
                raise ImportError("No module named alchemia")
            return orig_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", failing_import)
        monkeypatch.setattr(mod.shutil, "which", lambda n: None)
        monkeypatch.setattr(mod.os.environ, "get", lambda k, d=None: None)
        monkeypatch.setattr(mod, "PORTAL_DB", tmp_path / "missing.db")

        assert mod._alchemia_ok() is False

    def test_doctor_reflects_probe_failure(self, tmp_path, monkeypatch, capsys):
        """Doctor fails closed (exit 1) when _alchemia_ok returns False."""
        mod = _load_bifrons_module()
        portal = tmp_path / "portal.db"
        with sqlite3.connect(portal) as conn:
            conn.execute("CREATE TABLE external_repo (id INTEGER PRIMARY KEY)")
        monkeypatch.setattr(mod, "PORTAL_DB", portal)
        monkeypatch.setattr(mod.shutil, "which", lambda n: f"/test-bin/{n}")
        monkeypatch.setattr(mod, "_alchemia_ok", lambda: False)

        exit_code = mod.doctor()
        out = capsys.readouterr().out
        assert exit_code == 1
        assert "alchemia=BROKEN (module not importable — absorption dead)" in out


# ─────────────────────────────────────────────────────────────────────────────
# 2. Challenge observation-feed.py & collector with edge cases
# ─────────────────────────────────────────────────────────────────────────────


class TestCollectorEdgeCases:
    """Stress-test telemetry collectors against corrupted state and subsystem failures."""

    def test_collect_vitals_hardware_sensor_failure(self, monkeypatch):
        """When vitals sensor raises unexpected exception (e.g. psutil/os error)."""
        import limen.vigilia.vitals as vitals_mod

        def failing_gate(**kwargs):
            raise RuntimeError("Kernel sensor memory bus timeout")

        monkeypatch.setattr(vitals_mod, "beat_gate", failing_gate)
        res = collect_vitals()
        assert res["level"] == 1
        assert res["action"] == "ok"
        assert res["load_per_core"] == 0.0
        assert "degraded: Kernel sensor memory bus timeout" in res["status"]

    def test_collect_bifrons_unreadable_corrupt_database(self, tmp_path, monkeypatch):
        """When portal.db exists but is 0-byte or corrupted binary garbage."""
        corrupt_db = tmp_path / "portal.db"
        corrupt_db.write_bytes(b"\x00\xff\xfeCORRUPT_SQLITE_HEADER")

        mod = _load_bifrons_module()
        monkeypatch.setattr(mod, "PORTAL_DB", corrupt_db)

        res = mod.portal_counts()
        assert res["present"] is False
        assert res["status"] == "unreadable"
        assert res["counts"]["external_repo"] == 0

    def test_collect_bifrons_missing_script(self, tmp_path):
        """When scripts/bifrons-organ.py is missing from repo root."""
        res = collect_bifrons(root=tmp_path)
        assert res["stars"] == 0
        assert res["dossiers"] == 0
        assert res["status"] == "absent"

    def test_collect_bifrons_exception_in_script(self, tmp_path):
        """When scripts/bifrons-organ.py exists but raises an exception during import."""
        script_dir = tmp_path / "scripts"
        script_dir.mkdir(parents=True)
        broken_script = script_dir / "bifrons-organ.py"
        broken_script.write_text("raise SyntaxError('unsupported syntax')")

        res = collect_bifrons(root=tmp_path)
        assert res["stars"] == 0
        assert "degraded:" in res["status"]

    def test_collect_observatory_corrupt_brief_latest(self, monkeypatch):
        """When brief-latest.json has corrupted structure."""
        import limen.observatory.brief as brief_mod

        monkeypatch.setattr(brief_mod, "config_latest", lambda _: {"hero": 12345, "mechanisms": "not-a-list"})
        monkeypatch.setattr(brief_mod, "_external_gaps", lambda: ["gap1", "gap2"])
        monkeypatch.setattr(brief_mod, "_internal_gaps", lambda: [])
        monkeypatch.setattr(brief_mod, "_top_mechanisms", lambda n: [])

        obs = collect_observatory()
        assert obs["hero"] == "12345"
        assert obs["external_gaps"] == 2
        assert obs["internal_gaps"] == 0
        assert obs["top_mechanism"] is None
        assert obs["status"] == "ok"

    def test_collect_observatory_total_subsystem_crash(self, monkeypatch):
        """When observatory module raises an unhandled exception."""
        import limen.observatory.brief as brief_mod

        def crashing_brief(*args, **kwargs):
            raise ConnectionResetError("Observatory RPC socket reset")

        monkeypatch.setattr(brief_mod, "config_latest", crashing_brief)
        obs = collect_observatory()
        assert obs["hero"] is None
        assert obs["external_gaps"] == 0
        assert obs["internal_gaps"] == 0
        assert obs["top_mechanism"] is None
        assert "degraded: Observatory RPC socket reset" in obs["status"]


# ─────────────────────────────────────────────────────────────────────────────
# 3. Validate fail-open & graceful degradation invariants
# ─────────────────────────────────────────────────────────────────────────────


class TestFailOpenInvariants:
    """Verify that errors degrade gracefully without crashing the feed collector."""

    def test_build_feed_record_under_full_subsystem_outage(self, monkeypatch):
        """When ALL THREE subsystems (vitals, bifrons, observatory) fail simultaneously."""
        # Force vitals failure
        import limen.vigilia.vitals as vitals_mod

        monkeypatch.setattr(
            vitals_mod, "beat_gate", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("vitals down"))
        )

        # Force observatory failure
        import limen.observatory.brief as brief_mod

        monkeypatch.setattr(
            brief_mod, "config_latest", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("obs down"))
        )

        # Force bifrons failure by passing nonexistent root
        fake_root = Path("/nonexistent/limen_root")

        # Build feed record
        record = build_feed_record(source="adversarial_test", root=fake_root)

        # Invariant 1: Record MUST still conform 100% to limen.observation.feed.v1 schema
        violations = validate_feed_record(record)
        assert violations == [], f"Feed record failed schema validation under full outage: {violations}"

        # Invariant 2: Status is accurately computed as 'degraded'
        assert record["status"] == "degraded"
        assert record["schema"] == SCHEMA_V1
        assert record["vitals"]["level"] == 1
        assert record["vitals"]["action"] == "ok"
        assert record["bifrons"]["stars"] == 0
        assert record["observatory"]["external_gaps"] == 0

    def test_build_feed_record_bifrons_degradation_propagates(self, tmp_path):
        """When Bifrons degrades, composite status is 'degraded'."""
        script_dir = tmp_path / "scripts"
        script_dir.mkdir(parents=True)
        broken_script = script_dir / "bifrons-organ.py"
        broken_script.write_text("raise RuntimeError('bifrons crash')")

        record = build_feed_record(source="bifrons_test", root=tmp_path)
        assert record["schema"] == SCHEMA_V1
        assert "degraded" in record["status"]

    def test_emit_feed_record_under_full_outage(self, tmp_path, monkeypatch):
        """Ensure emission to disk succeeds even under full outage."""
        import limen.vigilia.vitals as vitals_mod

        monkeypatch.setattr(
            vitals_mod, "beat_gate", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("vitals down"))
        )
        import limen.observatory.brief as brief_mod

        monkeypatch.setattr(
            brief_mod, "config_latest", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("obs down"))
        )

        record, jsonl_path, latest_path = emit_feed_record(base_dir=tmp_path)
        assert jsonl_path.exists()
        assert latest_path.exists()

        ok, errors = check_feed(base_dir=tmp_path)
        assert ok is True, f"Check failed on emitted degraded feed: {errors}"

    def test_cli_emit_under_hostile_environment(self, tmp_path):
        """Run observation-feed.py --emit in an isolated empty environment."""
        res = subprocess.run(
            [sys.executable, str(FEED_SCRIPT), "--emit", "--json", "--root", str(tmp_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res.returncode == 0, f"CLI crashed: {res.stderr}"
        data = json.loads(res.stdout)
        assert data["schema"] == SCHEMA_V1
        assert data["status"] in ("ok", "degraded", "shed")

    def test_cli_check_resilience_to_garbage_inputs(self, tmp_path):
        """Validate that corrupt feed files produce detailed stderr reports and exit code 1."""
        log_dir = tmp_path / "logs" / "observation"
        log_dir.mkdir(parents=True)
        latest_file = log_dir / "feed-latest.json"
        jsonl_file = log_dir / "feed.jsonl"

        # 1. Invalid JSON
        latest_file.write_text("<<<NOT JSON>>>", encoding="utf-8")
        jsonl_file.write_text('{"schema": "limen.observation.feed.v1"}\n', encoding="utf-8")

        res = subprocess.run(
            [sys.executable, str(FEED_SCRIPT), "--check", "--root", str(tmp_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res.returncode == 1
        assert "FAIL: observation feed check failed" in res.stderr
        assert "unreadable" in res.stderr

        # 2. Schema violations (e.g. negative numbers, bad action)
        bad_record = {
            "schema": SCHEMA_V1,
            "observed_at": "2026-08-22T00:00:00Z",
            "source": "composite",
            "status": "invalid_status",
            "vitals": {
                "level": "not_int",
                "action": "invalid_action",
                "load_per_core": -1.0,
                "swap_used_gib": "bad",
                "ram_gib": None,
            },
            "bifrons": {
                "stars": -10,
                "dossiers": "bad",
                "resonance_edges": -1,
                "awaiting_gate": -1,
            },
            "observatory": {
                "hero": 999,
                "external_gaps": -5,
                "internal_gaps": -1,
                "top_mechanism": 123,
            },
        }
        latest_file.write_text(json.dumps(bad_record), encoding="utf-8")
        jsonl_file.write_text(json.dumps(bad_record) + "\n", encoding="utf-8")

        ok, errors = check_feed(base_dir=tmp_path)
        assert ok is False
        assert len(errors) >= 8
        assert any("status" in e for e in errors)
        assert any("vitals.level" in e for e in errors)
        assert any("vitals.action" in e for e in errors)
        assert any("vitals.swap_used_gib" in e for e in errors)
        assert any("bifrons.stars" in e for e in errors)
        assert any("observatory.hero" in e for e in errors)

    def test_collect_vitals_malformed_types_fail_open(self, monkeypatch):
        """When vitals sensor returns non-coercible types (e.g. None for load_per_core)."""
        import limen.vigilia.vitals as vitals_mod

        monkeypatch.setattr(vitals_mod, "beat_gate", lambda **kwargs: {"load_per_core": None, "level": "bad"})
        res = collect_vitals()
        assert res["level"] == 1
        assert res["action"] == "ok"
        assert res["load_per_core"] == 0.0
        assert "degraded:" in res["status"]

    def test_collect_bifrons_malformed_returns_fail_open(self, tmp_path):
        """When bifrons script portal_counts returns None or invalid shape."""
        script_dir = tmp_path / "scripts"
        script_dir.mkdir(parents=True)
        script_file = script_dir / "bifrons-organ.py"
        script_file.write_text("def portal_counts(): return None")

        res = collect_bifrons(root=tmp_path)
        assert res["stars"] == 0
        assert res["dossiers"] == 0
        assert "degraded:" in res["status"]

    def test_bifrons_portal_counts_empty_db_fail_open(self, tmp_path, monkeypatch):
        """When portal.db is empty SQLite database with zero tables."""
        empty_db = tmp_path / "empty_portal.db"
        with sqlite3.connect(empty_db):
            pass  # Creates valid empty SQLite database

        mod = _load_bifrons_module()
        monkeypatch.setattr(mod, "PORTAL_DB", empty_db)
        res = mod.portal_counts()
        assert res["present"] is True
        assert res["status"] == "present"
        assert res["exchange_rows"] == 0
        assert res["counts"]["external_repo"] == 0

    def test_rapid_burst_emission_integrity(self, tmp_path):
        """Emit sequential telemetry packets and verify file formatting and stream integrity."""
        record = build_feed_record()
        for i in range(10):
            emit_feed_record(record=record, base_dir=tmp_path)

        ok, errors = check_feed(base_dir=tmp_path)
        assert ok is True, f"Check failed after burst emissions: {errors}"

        jsonl_path = tmp_path / "logs" / "observation" / "feed.jsonl"
        lines = [line.strip() for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(lines) == 10
        for line in lines:
            data = json.loads(line)
            assert data["schema"] == SCHEMA_V1
            assert data["status"] in ("ok", "degraded", "shed")
