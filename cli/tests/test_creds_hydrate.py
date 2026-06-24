"""Credential durability: a credential minted ONCE (into ~/.limen.env / 1Password) must reach the
agent subprocess env — so a SET key never reads as 'auth not configured' again, and a one-time login
is never repeated. Covers dispatch._load_limen_env() (the propagation fix) and the creds-hydrate
organ's --dry-run/--check (no `op`, no secret reads, no writes)."""
import os
import subprocess
import sys
from pathlib import Path

from limen.dispatch import _load_limen_env

HYDRATE = Path(__file__).resolve().parents[2] / "scripts" / "creds-hydrate.py"


def test_load_limen_env_fills_missing_keys(tmp_path, monkeypatch):
    env_file = tmp_path / ".limen.env"
    env_file.write_text('export GEMINI_API_KEY=abc123\nOPENAI_API_KEY="def456"\n# a comment\n\n')
    monkeypatch.setenv("LIMEN_ENV", str(env_file))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    n = _load_limen_env()

    assert n == 2
    assert os.environ["GEMINI_API_KEY"] == "abc123"
    assert os.environ["OPENAI_API_KEY"] == "def456"  # quotes stripped, no `export` prefix needed


def test_load_limen_env_never_overwrites_explicit(tmp_path, monkeypatch):
    """An explicitly-exported var wins — the cache only fills what's MISSING (no clobber)."""
    env_file = tmp_path / ".limen.env"
    env_file.write_text("export GH_TOKEN=from_file\n")
    monkeypatch.setenv("LIMEN_ENV", str(env_file))
    monkeypatch.setenv("GH_TOKEN", "from_real_env")

    _load_limen_env()

    assert os.environ["GH_TOKEN"] == "from_real_env"


def test_load_limen_env_fail_open_when_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ENV", str(tmp_path / "does-not-exist.env"))
    assert _load_limen_env() == 0  # no file → loads nothing, never raises


def test_hydrate_dry_run_reads_nothing_writes_nothing(tmp_path, monkeypatch):
    """--dry-run prints the op://→target plan without touching `op` or the env file."""
    env_file = tmp_path / ".limen.env"
    monkeypatch.setenv("LIMEN_ENV", str(env_file))
    r = subprocess.run(
        [sys.executable, str(HYDRATE), "--dry-run"],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "LIMEN_ENV": str(env_file)},
    )
    assert r.returncode == 0
    assert "plan:" in r.stdout or "op:" not in r.stdout  # plan lines, no secret material
    assert not env_file.exists()  # dry-run wrote nothing


def test_hydrate_map_override(tmp_path, monkeypatch):
    """The map is a named, tweakable param — an override file is honored over the built-in default."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("creds_hydrate", HYDRATE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    map_file = tmp_path / "map.json"
    map_file.write_text('[{"lane":"x","ref":"op://V/I/credential","env":["X_KEY"]}]')
    monkeypatch.setenv("LIMEN_CREDS_MAP", str(map_file))
    loaded = mod.load_map()
    assert loaded == [{"lane": "x", "ref": "op://V/I/credential", "env": ["X_KEY"]}]


def test_hydrate_write_env_idempotent(tmp_path, monkeypatch):
    """write_env is add-or-replace: re-running yields exactly ONE line per key (no duplication)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("creds_hydrate2", HYDRATE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    env_file = tmp_path / ".limen.env"
    monkeypatch.setenv("LIMEN_ENV", str(env_file))
    mod.ENV_FILE = env_file  # the module bound ENV_FILE at import from the old env; point it at tmp

    mod.write_env("FOO", "v1")
    mod.write_env("FOO", "v2")
    lines = [ln for ln in env_file.read_text().splitlines() if ln.startswith("export FOO=")]
    assert lines == ["export FOO=v2"]
    assert oct(env_file.stat().st_mode)[-3:] == "600"
