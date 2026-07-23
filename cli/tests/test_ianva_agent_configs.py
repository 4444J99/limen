"""Golden and registry-drift tests for every primary ianva peer-conductor adapter."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IANVA_SRC = ROOT / "ianva" / "src"
if str(IANVA_SRC) not in sys.path:
    sys.path.insert(0, str(IANVA_SRC))

from ianva.agents import AGENTS, SERVER_NAME, by_key
from ianva.gen import BEARER_ENV, Endpoint, build_entries, write_golden
from limen import census

PRIMARY = frozenset({"codex", "claude", "copilot", "agy", "opencode"})


def _entry_map():
    return {entry.key: entry for entry in build_entries(Endpoint(bearer="test-bearer"))}


def test_ianva_primary_target_transport_drift_guard_against_census():
    targets = {target.key: target for target in AGENTS}
    assert PRIMARY <= targets.keys()
    assert len(targets) == len(AGENTS)

    profiles = census.execution_profiles()
    for name in PRIMARY:
        assert profiles[name].transport == f"ianva-{targets[name].transport}"


def test_authenticated_primary_entries_use_native_config_shapes():
    entries = _entry_map()
    assert PRIMARY <= entries.keys()
    assert all(entry.transport in {"http", "stdio"} for entry in entries.values())

    codex = entries["codex"]
    assert f"[mcp_servers.{SERVER_NAME}]" in codex.rendered
    assert f'bearer_token_env_var = "{BEARER_ENV}"' in codex.rendered

    claude = entries["claude"]
    assert f"mcp add --transport http --scope user {SERVER_NAME}" in claude.rendered
    assert "Authorization: Bearer test-bearer" in claude.rendered

    for name in ("agy", "copilot"):
        server = entries[name].payload["mcpServers"][SERVER_NAME]
        assert server["command"]
        assert server["args"][-1] == "http://127.0.0.1:7666/mcp"
        header = server["args"][server["args"].index("Authorization") + 1]
        assert header == "Bearer test-bearer"

    copilot = entries["copilot"].payload["mcpServers"][SERVER_NAME]
    assert copilot["type"] == "local"
    assert copilot["tools"] == ["*"]


def test_opencode_generation_matches_native_remote_contract_without_secret_materialization():
    target = by_key("opencode")
    assert target is not None
    assert target.path.name == "opencode.jsonc"
    assert target.fmt == "json_opencode"
    assert target.transport == "http"
    assert target.creates_file is True

    entry = _entry_map()["opencode"]
    server = entry.payload["mcp"][SERVER_NAME]
    assert server == {
        "type": "remote",
        "url": "http://127.0.0.1:7666/mcp",
        "headers": {"Authorization": f"Bearer {{env:{BEARER_ENV}}}"},
    }
    assert "test-bearer" not in entry.rendered


def test_authenticated_primary_goldens_are_complete_and_loopback_only(tmp_path: Path):
    entries = list(_entry_map().values())
    write_golden(entries, tmp_path)

    install = (tmp_path / "INSTALL.md").read_text()
    for name in PRIMARY:
        entry = next(entry for entry in entries if entry.key == name)
        golden = (tmp_path / entry.filename).read_text()
        assert entry.label in install
        assert "ianva" in golden
        assert "127.0.0.1:7666/mcp" in golden
        assert "https://" not in golden
        if entry.payload is not None:
            assert json.loads(entry.rendered)
