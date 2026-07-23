from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "bifrons-organ.py"


def _load():
    spec = importlib.util.spec_from_file_location("bifrons_organ_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_portal(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE external_repo (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO external_repo DEFAULT VALUES")


def test_doctor_passes_with_readable_store_and_engine_cli(tmp_path, monkeypatch, capsys):
    module = _load()
    portal = tmp_path / "portal.db"
    _write_portal(portal)
    monkeypatch.setattr(module, "PORTAL_DB", portal)
    monkeypatch.setattr(module.shutil, "which", lambda name: f"/test-bin/{name}")
    # Stub alchemia as functional so the test is not host-environment-dependent.
    monkeypatch.setattr(module, "_alchemia_ok", lambda: True)

    assert module.doctor() == 0
    out = capsys.readouterr().out
    assert "portal_store=present" in out
    assert "engine_cli=yes" in out
    assert "alchemia=ok" in out


def test_doctor_fails_when_store_is_absent(tmp_path, monkeypatch, capsys):
    module = _load()
    monkeypatch.setattr(module, "PORTAL_DB", tmp_path / "missing.db")
    monkeypatch.setattr(module.shutil, "which", lambda name: f"/test-bin/{name}")
    monkeypatch.setattr(module, "_alchemia_ok", lambda: True)

    assert module.doctor() == 1
    assert "portal_store=absent" in capsys.readouterr().out


def test_doctor_fails_when_engine_cli_is_missing(tmp_path, monkeypatch, capsys):
    module = _load()
    portal = tmp_path / "portal.db"
    _write_portal(portal)
    monkeypatch.setattr(module, "PORTAL_DB", portal)
    monkeypatch.setattr(module.shutil, "which", lambda _name: None)
    monkeypatch.setattr(module, "_alchemia_ok", lambda: True)

    assert module.doctor() == 1
    assert "portal_store=present  engine_cli=no" in capsys.readouterr().out


def test_doctor_fails_when_store_is_corrupt(tmp_path, monkeypatch, capsys):
    module = _load()
    portal = tmp_path / "portal.db"
    portal.write_bytes(b"not a sqlite database")
    monkeypatch.setattr(module, "PORTAL_DB", portal)
    monkeypatch.setattr(module.shutil, "which", lambda name: f"/test-bin/{name}")
    monkeypatch.setattr(module, "_alchemia_ok", lambda: True)

    assert module.doctor() == 1
    assert "portal_store=unreadable" in capsys.readouterr().out


def test_doctor_fails_when_alchemia_broken(tmp_path, monkeypatch, capsys):
    """A broken alchemia module (on PATH but unimportable) must fail the liveness probe."""
    module = _load()
    portal = tmp_path / "portal.db"
    _write_portal(portal)
    monkeypatch.setattr(module, "PORTAL_DB", portal)
    monkeypatch.setattr(module.shutil, "which", lambda name: f"/test-bin/{name}")
    monkeypatch.setattr(module, "_alchemia_ok", lambda: False)

    assert module.doctor() == 1
    out = capsys.readouterr().out
    assert "alchemia=BROKEN" in out
