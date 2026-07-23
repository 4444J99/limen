import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ianva" / "src"))

from ianva.upstreams import load_upstreams


def test_load_upstreams_defensively_normalizes_registry_shapes(tmp_path):
    registry = tmp_path / "servers.json"
    registry.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "disabled-local": {
                        "command": ["node", "server.js"],
                        "args": "--flag value",
                        "env": "wrong-shape",
                        "enabled": "false",
                    },
                    "remote": {
                        "url": "https://example.test/mcp",
                        "transport": "streamablehttp",
                        "headers": {"X-Test": 1},
                        "oauth": "yes",
                        "enabled": "true",
                    },
                    "scalar-args": {
                        "command": "tool",
                        "args": 7,
                        "headers": ["wrong-shape"],
                    },
                }
            }
        )
    )

    enabled = {u.name: u for u in load_upstreams(registry=registry)}
    assert set(enabled) == {"remote", "scalar-args"}
    assert enabled["remote"].transport == "http"
    assert enabled["remote"].headers == {"X-Test": "1"}
    assert enabled["remote"].oauth is True
    assert enabled["scalar-args"].args == ["7"]
    assert enabled["scalar-args"].headers == {}

    all_upstreams = {u.name: u for u in load_upstreams(registry=registry, include_disabled=True)}
    assert all_upstreams["disabled-local"].enabled is False
    assert all_upstreams["disabled-local"].command == "node"
    assert all_upstreams["disabled-local"].args == ["server.js", "--flag", "value"]
    assert all_upstreams["disabled-local"].env == {}
