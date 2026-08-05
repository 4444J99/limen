from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "disk-capacity.py"


def _module():
    spec = importlib.util.spec_from_file_location("disk_capacity_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_check_compares_live_free_space_to_resource_envelope(
    monkeypatch,
    capsys,
) -> None:
    module = _module()
    monkeypatch.setattr(module, "_free_gib", lambda: 12.0)
    monkeypatch.setattr(module, "current_required_free_gib", lambda: 10.0)
    assert module.check() == 0
    assert "12.000 GiB" in capsys.readouterr().out

    monkeypatch.setattr(module, "_free_gib", lambda: 9.0)
    assert module.check() == 1
    assert "BREACHED" in capsys.readouterr().out


def test_check_fails_closed_when_live_envelope_is_unavailable(
    monkeypatch,
    capsys,
) -> None:
    module = _module()
    monkeypatch.setattr(module, "_free_gib", lambda: 12.0)
    monkeypatch.setattr(
        module,
        "current_required_free_gib",
        lambda: (_ for _ in ()).throw(RuntimeError("telemetry")),
    )

    assert module.check() == 1
    assert "failed closed" in capsys.readouterr().out


def test_absent_non_host_volume_remains_a_portable_skip(
    monkeypatch,
    capsys,
) -> None:
    module = _module()
    monkeypatch.setattr(module, "_free_gib", lambda: None)

    assert module.check() == 0
    assert "not found" in capsys.readouterr().out
    assert module.check(strict=True) == 77
