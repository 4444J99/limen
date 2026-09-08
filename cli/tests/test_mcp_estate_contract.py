from __future__ import annotations

import json
from pathlib import Path
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import mcp_estate as estate
import mcp_protocol as protocol


def policy():
    return {
        "schema_version": 1,
        "services": {"serena": {"source_owner": "domus-genoma", "availability": "enabled"}},
        "registrations": [{"client": "codex", "name": "serena", "service": "serena"}],
    }


def test_missing_stays_in_denominator(tmp_path):
    records, issues, _, _ = estate.inventory(policy(), [("codex", tmp_path / "missing.toml")])
    result = estate.measure(policy(), records, issues, inventory_only=True)
    assert result["denominator"] == {"services": 1, "registrations": 1}
    assert result["distance"]["missing_capabilities"] == 1
    assert result["exit"] == 77


def test_disabled_and_malformed_are_not_success(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[mcp_servers.serena]\nenabled=false\ncommand="false"\n')
    records, issues, _, _ = estate.inventory(policy(), [("codex", path)])
    result = estate.measure(policy(), records, issues, inventory_only=True)
    assert result["servers"][0]["observed_state"] == "disabled"
    assert result["distance"]["missing_capabilities"] == 1
    path.write_text("[broken")
    records, issues, _, _ = estate.inventory(policy(), [("codex", path)])
    assert len(records) == 1
    assert issues[0]["reason"] == "configuration_unreadable"


def test_plugin_route_conflict_and_opt_out(tmp_path):
    cache = tmp_path / "plugins/cache/market/serena/1"
    cache.mkdir(parents=True)
    (cache / ".mcp.json").write_text(json.dumps({"mcpServers": {"serena": {"command": "false"}}}))
    path = tmp_path / "config.toml"
    raw = '[mcp_servers.serena]\ncommand="false"\n[plugins."serena@market"]\nenabled=true\n'
    path.write_text(raw)
    records, issues, _, _ = estate.inventory(policy(), [("codex", path)])
    result = estate.measure(policy(), records, issues, inventory_only=True)
    assert result["distance"]["ownership_conflicts"] == 2
    path.write_text(raw + '[plugins."serena@market".mcp_servers.serena]\nenabled=false\n')
    records, issues, _, _ = estate.inventory(policy(), [("codex", path)])
    assert estate.measure(policy(), records, issues, inventory_only=True)["distance"]["ownership_conflicts"] == 0


def stdio(code):
    return {"transport": "stdio", "command": sys.executable, "args": ["-u", "-c", code]}


@pytest.mark.parametrize(
    "code",
    [
        "pass",
        "import time; time.sleep(20)",
        "import sys,time; sys.stdout.write('{'); sys.stdout.flush(); time.sleep(20)",
    ],
)
def test_silent_clean_exit_and_partial_line_fail(code):
    result = protocol.verify(stdio(code), timeout=0.15)
    assert result["dimensions"]["protocol"] == "fail"
    assert result["dimensions"]["cleanup"] == "pass"
    assert result["latency_ms"] < 2000


SERVER = """import sys,json
for line in sys.stdin:
 q=json.loads(line)
 if 'id' not in q: continue
 if q['method'] in ('initialize','server/discover'):
  result={'protocolVersion':'2025-11-25','capabilities':{'tools':{}},'serverInfo':{'name':'fixture','version':'1'}}
 else: result={'tools':[{'name':'open_dashboard'}]}
 print(json.dumps({'jsonrpc':'2.0','id':q['id'],'result':result}),flush=True)
"""


@pytest.mark.parametrize("version", ["2025-11-25", "2026-07-28"])
def test_protocol_adapters_discover_capabilities(version):
    result = protocol.verify(stdio(SERVER), expected={"tools": ["open_dashboard"]}, version=version)
    assert result["dimensions"]["protocol"] == "pass"
    assert result["dimensions"]["capabilities"] == "pass"


def test_missing_tool_and_unsupported_protocol():
    result = protocol.verify(stdio(SERVER), expected={"tools": ["absent"]})
    assert result["missing_capabilities"] == 1
    assert result["dimensions"]["capabilities"] == "fail"
    result = protocol.verify(stdio("raise Exception('must not launch')"), version="future")
    assert result["reason"] == "unsupported_protocol"


@pytest.mark.parametrize("status,auth", [(200, "unmeasured"), (401, "required")])
def test_http_listener_is_not_mcp_and_auth_is_distinct(status, auth):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(status)
            self.end_headers()
            self.wfile.write(b"not MCP")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = protocol.verify({"transport": "http", "url": f"http://127.0.0.1:{server.server_port}/mcp"}, timeout=1)
        assert result["dimensions"]["transport"] == "pass"
        assert result["dimensions"]["protocol"] != "pass"
        assert result["dimensions"]["authentication"] == auth
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_expired_or_changed_receipt_cannot_supply_evidence():
    row = {
        "client": "codex",
        "name": "serena",
        "route": "standalone",
        "service": "serena",
        "fingerprint": "current",
        "dimensions": dict.fromkeys(estate.DIMENSIONS, "unmeasured"),
    }
    receipt = {
        "schema_version": "limen.mcp_client_canary.v1",
        "client": "codex",
        "name": "serena",
        "route": "standalone",
        "fingerprint": "current",
        "contract_fingerprint": estate.fingerprint(policy()["services"]["serena"]),
        "client_version": "1",
        "server_version": "1",
        "observed_at": 100,
        "dimensions": {"startup_ui": "pass", "explicit_ui": "pass", "isolation": "pass", "client_route": "pass"},
    }
    assert not estate.apply_client_receipts([row], [receipt], policy(), now=4000)
    assert estate.apply_client_receipts([row], [receipt], policy(), now=101) == {"codex"}
    receipt["fingerprint"] = "old"
    assert not estate.apply_client_receipts([row], [receipt], policy(), now=102)


def test_report_does_not_leak_config_values(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[mcp_servers.serena]\ncommand="private-command"\n[mcp_servers.serena.env]\nTOKEN="secret-value"\n')
    records, issues, _, _ = estate.inventory(policy(), [("codex", path)])
    raw = json.dumps(estate.measure(policy(), records, issues, inventory_only=True))
    assert "secret-value" not in raw and "private-command" not in raw
