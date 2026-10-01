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


def test_control_plane_launchd_consumers_have_no_editable_source_paths() -> None:
    paths = [ROOT / "container/launchd" / name for name in CONTROL_PLISTS]
    paths.append(ROOT / "ianva/deploy/com.ianva.gateway.plist")

    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for child in value.values():
                yield from strings(child)
        elif isinstance(value, list):
            for child in value:
                yield from strings(child)

    for path in paths:
        payload = plistlib.loads(path.read_bytes())
        values = list(strings(payload))
        assert not any("/Workspace/limen" in value for value in values)
        assert not any("/Workspace/domus-genoma" in value for value in values)
        assert not any("__IANVA_DIR__" in value for value in values)
        for key in ("StandardOutPath", "StandardErrorPath"):
            assert payload[key].startswith("/Users/4jp/.local/state/limen/launchd/")


def test_credential_job_and_gateway_use_installed_interpreter() -> None:
    credentials = plistlib.loads((ROOT / "container/launchd/com.limen.creds-hydrate.plist").read_bytes())
    command = credentials["ProgramArguments"][-1]
    assert "$HOME/.local/share/limen/current/venv/bin/python3" in command
    assert ".venv/bin" not in command
    assert "command -v python3" not in command
    gateway = plistlib.loads((ROOT / "ianva/deploy/com.ianva.gateway.plist").read_bytes())
    assert gateway["EnvironmentVariables"]["PATH"].split(":")[0].endswith("/.local/share/limen/current/venv/bin")
