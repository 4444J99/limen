from __future__ import annotations

import json
import plistlib
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OVERNIGHT_PLIST = ROOT / "container" / "launchd" / "com.limen.overnight-watch.plist"
PYPROJECT = ROOT / "cli" / "pyproject.toml"
STABLE_HOST = "/Users/4jp/Applications/DomusAgentHost.app/Contents/MacOS/DomusAgentHost"
CONTROL_PLISTS = (
    "com.limen.claude-stub-heal.plist",
    "com.limen.creds-hydrate.plist",
)


def test_overnight_watch_launchagent_remains_absent() -> None:
    assert not OVERNIGHT_PLIST.exists()


def test_overnight_watch_is_not_declared_as_a_background_item() -> None:
    registry = json.loads((ROOT / "spec" / "background-items.json").read_text(encoding="utf-8"))
    assert "com.limen.overnight-watch" not in registry["estate_agents"]


def test_remaining_limen_launchd_control_plane_enters_stable_host() -> None:
    launchd = ROOT / "container" / "launchd"

    for name in CONTROL_PLISTS:
        with (launchd / name).open("rb") as handle:
            payload = plistlib.load(handle)
        assert payload["ProgramArguments"][:3] == [
            STABLE_HOST,
            "run",
            "--",
        ]


def test_immutable_runtime_declares_trial_protocol_dependency() -> None:
    with PYPROJECT.open("rb") as handle:
        dependencies = tomllib.load(handle)["project"]["dependencies"]

    assert "rfc8785==0.1.4" in dependencies
