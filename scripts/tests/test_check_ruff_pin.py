from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "check_ruff_pin", Path(__file__).resolve().parents[1] / "check-ruff-pin.py"
)
assert SPEC is not None and SPEC.loader is not None
pin = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pin)


@pytest.mark.parametrize(
    ("stdout", "returncode", "expected"),
    [
        ("ruff 0.15.8\n", 0, "0.15.8"),
        ("ruff 0.16.9\n", 0, "0.16.9"),
        ("", 0, None),
        ("other 0.15.8", 0, None),
        ("ruff 0.15.8\nextra", 0, None),
        ("ruff 0.15.8", 1, None),
    ],
)
def test_version_is_the_executed_module_command(monkeypatch, stdout, returncode, expected):
    def run(args, **kwargs):
        assert args == [sys.executable, "-m", "ruff", "--version"]
        assert kwargs["timeout"] == 10
        assert kwargs["stdin"] == subprocess.DEVNULL
        return subprocess.CompletedProcess(args, returncode, stdout, "")

    monkeypatch.setattr(pin.subprocess, "run", run)
    assert pin.installed_version() == expected


@pytest.mark.parametrize("error", [OSError("unavailable"), subprocess.TimeoutExpired("ruff", 10)])
def test_unavailable_binary_fails_closed(monkeypatch, error):
    def unavailable(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(pin.subprocess, "run", unavailable)
    assert pin.installed_version() is None


@pytest.mark.parametrize(("executed", "expected_exit"), [("0.15.8", 0), ("0.16.9", 1), (None, 1)])
def test_main_requires_actual_binary_parity(monkeypatch, executed, expected_exit):
    monkeypatch.setattr(pin, "pinned_version", lambda: "0.15.8")
    monkeypatch.setattr(pin, "installed_version", lambda: executed)
    assert pin.main() == expected_exit
