import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import mcp_estate as estate


def test_opencode_native_environment_is_bound_and_not_exported():
    response = {
        "mcp": {"fixture": {"type": "local", "command": ["synthetic"], "environment": {"KEY": "private-value"}}}
    }
    native = estate.native_configuration_index("opencode", response)
    expected = estate.normalize({"command": "synthetic", "env": {"KEY": "private-value"}})
    assert native["registrations"]["fixture"]["launch_fingerprint"] == estate.fingerprint(expected)
    assert "private-value" not in json.dumps(native)
    assert estate.normalize({"command": "synthetic", "environment": {}, "env": {"KEY": "conflict"}}, "opencode")[
        "invalid"
    ]


@pytest.mark.parametrize("response", [{}, {"config": {}}, {"config": {"mcp_servers": False}}, {"config": []}])
def test_missing_native_config_is_not_empty_success(response):
    assert estate.native_configuration_index("codex", response)["state"] == "unmeasured"


@pytest.mark.parametrize("variant", ["matching", "different_environment", "disabled", "missing", "invalid"])
def test_native_receipt_requires_effective_launch_identity(variant):
    policy = {"services": {"fixture": {}}}
    declaration = {"command": "synthetic", "env": {"KEY": "current"}}
    row = {
        "client": "codex",
        "name": "fixture",
        "route": "standalone",
        "service": "fixture",
        "fingerprint": "source",
        "launch_fingerprint": estate.fingerprint(estate.normalize(declaration)),
    }
    native_declaration = dict(declaration)
    if variant == "different_environment":
        native_declaration["env"] = {"KEY": "other"}
    elif variant == "disabled":
        native_declaration["enabled"] = False
    elif variant == "invalid":
        native_declaration["args"] = False
    effective = estate.native_configuration_index(
        "codex", {"config": {"mcp_servers": {} if variant == "missing" else {"fixture": native_declaration}}}
    )
    observation = {
        "schema_version": "limen.native_observation.v1",
        "client": "codex",
        "binary_fingerprint": "binary",
        "configuration_fingerprint": "configuration",
        "effective_configuration": effective,
        "run_id": "run-owned",
        "native_session_id": "native-owned",
        "client_version": "1",
        "observed_at": 100,
        "servers": [{"name": "fixture", "server_version": "1", "runtime_status": "connected"}],
    }
    receipts, witnesses = estate.native_receipts([row], policy, observation)
    assert bool(receipts) == bool(witnesses) == (variant == "matching")


def test_default_claude_settings_and_plugin_root_are_inside_dot_claude(tmp_path, monkeypatch):
    monkeypatch.setattr(estate, "MCP_VENDOR_KEYS", ("claude",))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / ".claude.json").write_text("{}")
    settings = tmp_path / ".claude/settings.json"
    settings.parent.mkdir()
    settings.write_text(json.dumps({"enabledPlugins": {"fixture@market": True}}))
    root = settings.parent / "plugins/cache/market/fixture/1"
    root.mkdir(parents=True)
    (root / ".mcp.json").write_text(json.dumps({"mcpServers": {"fixture": {"command": "synthetic"}}}))
    policy = {"services": {"fixture": {}}, "registrations": []}
    records, _, _, _ = estate.inventory(policy, client_environments={"claude": {"HOME": str(tmp_path)}})
    plugin = next(row for row in records if row["route"] == "fixture@market")
    assert plugin["spec"]["command"] == "synthetic"
    assert not plugin["spec"]["disabled"]


@pytest.mark.parametrize("bad", [False, [], "bad"])
def test_malformed_registration_container_remains_a_coverage_gap(tmp_path, bad):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"mcpServers": bad}))
    _, issues, _, _ = estate.inventory({"services": {}, "registrations": []}, [("codex", path)])
    assert any(issue["reason"] == "registration_table_unmeasured" for issue in issues)
