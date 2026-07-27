from __future__ import annotations

import plistlib
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLIST = ROOT / "container" / "launchd" / "com.limen.overnight-watch.plist"
PYPROJECT = ROOT / "cli" / "pyproject.toml"
IMMUTABLE_ROOT = "/Users/4jp/.local/share/limen/current"


def test_overnight_watch_launchd_uses_signed_immutable_runtime() -> None:
    with PLIST.open("rb") as handle:
        payload = plistlib.load(handle)

    assert payload["ProgramArguments"] == [
        f"{IMMUTABLE_ROOT}/venv/bin/python",
        f"{IMMUTABLE_ROOT}/source/scripts/overnight-watch.py",
    ]
    assert payload["EnvironmentVariables"]["LIMEN_ROOT"] == "/Users/4jp/Workspace/limen"
    assert payload["EnvironmentVariables"]["PYTHONPATH"] == (f"{IMMUTABLE_ROOT}/source/cli/src")
    assert payload["StartInterval"] == 300

    command = " ".join(payload["ProgramArguments"])
    assert "/Workspace/limen/.venv/" not in command
    assert "/bin/bash" not in command
    assert "$" not in command


def test_immutable_runtime_declares_trial_protocol_dependency() -> None:
    with PYPROJECT.open("rb") as handle:
        dependencies = tomllib.load(handle)["project"]["dependencies"]

    assert "rfc8785==0.1.4" in dependencies
