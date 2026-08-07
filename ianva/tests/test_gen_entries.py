from __future__ import annotations

import tomllib
import unittest
from pathlib import Path

from ianva.agents import by_key
from ianva.config import GatewayConfig
from ianva.gen import Endpoint, build_entries


class CopilotEntryTests(unittest.TestCase):
    """Copilot must get a direct http entry — the stdio mcp-proxy shim it once used broke
    whenever the uv-cached mcp-proxy/mcp SDK pair drifted incompatible (ImportError on
    request_ctx → 'connection closed: initialize response' in Copilot's log)."""

    def _copilot_payload(self, ep: Endpoint | None = None) -> dict:
        entries = build_entries(ep)
        entry = next(e for e in entries if e.key == "copilot")
        return entry.payload["mcpServers"]["ianva"]

    def test_copilot_target_is_http(self) -> None:
        self.assertEqual(by_key("copilot").transport, "http")

    def test_copilot_renders_direct_http_shape(self) -> None:
        payload = self._copilot_payload()
        self.assertEqual(
            payload,
            {"type": "http", "url": "http://127.0.0.1:7666/mcp", "tools": ["*"]},
        )

    def test_copilot_bearer_adds_authorization_header(self) -> None:
        payload = self._copilot_payload(Endpoint(bearer="sentinel-token"))
        self.assertEqual(payload["type"], "http")
        self.assertEqual(payload["headers"], {"Authorization": "Bearer sentinel-token"})

    def test_no_agent_entry_regresses_to_local_type(self) -> None:
        for entry in build_entries():
            if entry.payload is None:
                continue
            server = entry.payload.get("mcpServers", {}).get("ianva", {})
            self.assertNotEqual(server.get("type"), "local", msg=entry.key)

    def test_stdio_entries_pin_a_compatible_mcp_sdk(self) -> None:
        stdio = [e for e in build_entries() if e.transport == "stdio"]
        self.assertTrue(stdio)
        for entry in stdio:
            args = entry.payload["mcpServers"]["ianva"]["args"]
            self.assertLess(args.index("--with"), args.index("mcp-proxy"), msg=entry.key)
            self.assertEqual(args[args.index("--with") + 1], "mcp<1.17", msg=entry.key)

    def test_proxy_args_carriers_agree(self) -> None:
        """proxy_args lives in three places (Endpoint, GatewayConfig, ianva.toml); the toml is
        loaded first and OVERRIDES the code defaults, so drift there silently un-pins the shim."""
        code_default = Endpoint().proxy_args
        self.assertEqual(GatewayConfig().proxy_args, code_default)
        toml_path = Path(__file__).resolve().parents[1] / "ianva.toml"
        bridge = tomllib.loads(toml_path.read_text()).get("bridge", {})
        self.assertEqual(bridge.get("proxy_args", code_default), code_default)


if __name__ == "__main__":
    unittest.main()
