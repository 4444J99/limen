"""Tests for the processless notification schedule editor."""

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "notification-schedule.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("notification_schedule", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_replace_block_preserves_unrelated_crontab_and_is_idempotent():
    module = _load_module()
    original = "# existing owner\n5 4 * * * /usr/bin/true\n"
    block = f"{module.BEGIN}\n*/10 * * * * /usr/bin/true\n{module.END}"

    first = module.replace_block(original, block)
    second = module.replace_block(first, block)

    assert first == second
    assert first.startswith(original)
    assert first.count(module.BEGIN) == 1
    assert first.count(module.END) == 1


def test_replace_block_refuses_corrupt_markers():
    module = _load_module()
    with pytest.raises(ValueError, match="markers are corrupt"):
        module.replace_block(f"{module.BEGIN}\n", "replacement")


def test_expected_block_propagates_state_root_and_explicit_apply(tmp_path, monkeypatch):
    module = _load_module()
    runtime = tmp_path / ("a" * 40)
    live_root = tmp_path / "live"
    state_root = tmp_path / "private state"
    monkeypatch.setattr(module, "STATE_ROOT", state_root)
    monkeypatch.setattr(module, "_paths", lambda: (runtime, live_root))
    monkeypatch.setenv("LIMEN_SESSION_ID", "notification-scheduler")
    monkeypatch.setenv("LIMEN_CONDUCT_ENV_FILE", str(tmp_path / "private.env"))

    block = module.expected_block()

    assert f"LIMEN_NOTIFICATION_STATE_DIR='{state_root}'" in block
    assert "notification-one-shot.py --apply" in block
    assert "--fresh-lease --conduct-env-file" in block
    assert "LIMEN_SESSION_ID=notification-scheduler" in block
    assert "LIMEN_LEASE_TOKEN=" not in block
    assert "LIMEN_CONDUCT_TOKEN=" not in block


def test_status_rejects_duplicate_managed_blocks(tmp_path, monkeypatch):
    module = _load_module()
    runtime = tmp_path / ("b" * 40)
    live_root = tmp_path / "live"
    (runtime / "venv/bin").mkdir(parents=True)
    (runtime / "source/scripts").mkdir(parents=True)
    (runtime / "venv/bin/python").touch()
    (runtime / "source/scripts/notification-one-shot.py").touch()
    monkeypatch.setattr(module, "_paths", lambda: (runtime, live_root))
    block = module.expected_block()
    monkeypatch.setattr(module, "_read_crontab", lambda: f"{block}\n{block}\n")

    assert module._status() == 1


def test_status_accepts_exactly_one_managed_block(tmp_path, monkeypatch):
    module = _load_module()
    runtime = tmp_path / ("c" * 40)
    live_root = tmp_path / "live"
    (runtime / "venv/bin").mkdir(parents=True)
    (runtime / "source/scripts").mkdir(parents=True)
    (runtime / "venv/bin/python").touch()
    (runtime / "source/scripts/notification-one-shot.py").touch()
    monkeypatch.setattr(module, "_paths", lambda: (runtime, live_root))
    cache = tmp_path / "conduct.env"
    cache.write_text("# private credential owner\n", encoding="utf-8")
    cache.chmod(0o600)
    monkeypatch.setenv("LIMEN_CONDUCT_ENV_FILE", str(cache))
    monkeypatch.setenv("LIMEN_SESSION_ID", "notification-scheduler")
    block = module.expected_block()
    monkeypatch.setattr(module, "_read_crontab", lambda: f"# unrelated\n{block}\n")

    assert module._status() == 0


def test_activation_requires_credential_and_session_configuration(tmp_path, monkeypatch):
    module = _load_module()
    monkeypatch.setenv("LIMEN_CONDUCT_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.delenv("LIMEN_SESSION_ID", raising=False)
    monkeypatch.setattr(module, "_read_crontab", lambda: "")
    monkeypatch.setattr(
        module.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("crontab activated without owning executor")
    )
    plan = module._plan()

    with pytest.raises(ValueError, match="registered LIMEN_SESSION_ID"):
        module._apply(plan["plan_sha256"])
    assert plan["execution_readiness"]["configured"] is False
