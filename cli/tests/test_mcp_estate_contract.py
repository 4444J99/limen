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


def test_apply_entrypoint_reuses_episode_without_certifying_cached_evidence(tmp_path, monkeypatch, capsys):
    from types import SimpleNamespace

    settings = tmp_path / ".serena/serena_config.yml"
    settings.parent.mkdir()
    settings.write_text("web_dashboard_open_on_launch: true\n")
    launcher = tmp_path / ".local/bin/domus-mcp-repair"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("fixture")
    config = tmp_path / "config.toml"
    config.write_text('[mcp_servers.serena]\ncommand="false"\n')
    desired = policy()
    desired["services"]["serena"]["repair"] = "serena-partial-config"
    inventory = estate.inventory(desired, [("codex", config)])
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(estate, "load_policy", lambda path: (desired, "a" * 64))
    monkeypatch.setattr(estate, "inventory", lambda *args, **kwargs: inventory)
    monkeypatch.setattr(estate, "gateway_reconciliation", lambda: {})
    calls = []

    def repair(*args, **kwargs):
        calls.append("repair")
        return SimpleNamespace(returncode=0, stdout=json.dumps({"outcome": "unchanged", "episode": "rollback"}))

    monkeypatch.setattr(estate.subprocess, "run", repair)
    assert estate.main(["--apply", "--json"]) == 77
    first = json.loads(capsys.readouterr().out)
    assert estate.main(["--apply", "--json"]) == 77
    second = json.loads(capsys.readouterr().out)
    assert calls == ["repair"]
    assert first["repair"]["reused"] is False
    assert second["repair"]["reused"] is True
    assert second["denominator"] == {"services": 1, "registrations": 1}
    assert second["distance"]["unmeasured_integrations"] > 0


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
        "run_id": "run-observed",
        "native_session_id": "native-observed",
        "dimensions": {"startup_ui": "pass", "explicit_ui": "pass", "isolation": "pass", "client_route": "pass"},
    }
    assert not estate.apply_client_receipts([row], [receipt], policy(), now=4000)
    assert not estate.apply_client_receipts([row], [receipt], policy(), now=101)
    receipt["dependency_fingerprint"] = "independent-current-dependencies"
    witness = {
        ("codex", "serena", "standalone"): {
            "receipt_fingerprint": estate.fingerprint(receipt),
            "dependency_fingerprint": receipt["dependency_fingerprint"],
            "client_version": "1",
            "server_version": "1",
            "run_id": "run-observed",
            "native_session_id": "native-observed",
            "observed_at": 100,
        }
    }
    assert estate.apply_client_receipts([row], [receipt], policy(), now=101, observations=witness) == {"codex"}
    receipt["fingerprint"] = "old"
    assert not estate.apply_client_receipts([row], [receipt], policy(), now=102)


def test_filtered_check_cannot_certify_estate(tmp_path):
    p = policy()
    p["registrations"][0]["availability"] = "disabled"
    path = tmp_path / "config.toml"
    path.write_text('[mcp_servers.serena]\nenabled=false\ncommand="false"\n')
    records, issues, _, _ = estate.inventory(p, [("codex", path)])
    assert estate.measure(p, records, issues, service=["serena"])["exit"] == 77


def test_duplicate_configuration_retains_sanitized_provenance(tmp_path):
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    for path in (first, second):
        path.write_text(json.dumps({"mcpServers": {"serena": {"command": str(path)}}}))
    records, issues, _, _ = estate.inventory(policy(), [("codex", first), ("codex", second)])
    result = estate.measure(policy(), records, issues, inventory_only=True)
    assert len(result["servers"][0]["provenance"]) == 2
    assert str(tmp_path) not in json.dumps(result)


@pytest.mark.parametrize("cursor", [0, False, "", [], {}])
def test_malformed_pagination_cannot_look_complete(cursor):
    code = SERVER.replace(
        "else: result={'tools':[{'name':'open_dashboard'}]}",
        "else: result={'tools':[{'name':'open_dashboard'}], 'nextCursor': " + repr(cursor) + "}",
    )
    result = protocol.verify(stdio(code), expected={"tools": ["open_dashboard"]})
    assert result["dimensions"]["protocol"] == "fail"


def test_report_does_not_leak_config_values(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[mcp_servers.serena]\ncommand="private-command"\n[mcp_servers.serena.env]\nTOKEN="secret-value"\n')
    records, issues, _, _ = estate.inventory(policy(), [("codex", path)])
    raw = json.dumps(estate.measure(policy(), records, issues, inventory_only=True))
    assert "secret-value" not in raw and "private-command" not in raw


def test_native_status_returns_identical_inventory_without_probe(monkeypatch):
    import importlib.util
    from types import SimpleNamespace

    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "mcp/src"))
    spec = importlib.util.spec_from_file_location("estate_native_status_test", root / "mcp/src/limen_mcp/server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    payload = {"schema_version": "limen.mcp_estate.v1", "exit": 77, "scope": "filtered", "distance": {}}

    def observe(argv, **kwargs):
        assert "--inventory-only" in argv
        assert "--apply" not in argv
        assert argv[-2:] == ["--service", "serena"]
        return SimpleNamespace(stdout=json.dumps(payload), returncode=77)

    monkeypatch.setattr(module.subprocess, "run", observe)
    assert module.mcp_estate_status("serena") == payload


def test_codex_inline_manifest_honors_disabled_plugin(tmp_path):
    cache = tmp_path / "plugins/cache/market/serena/1/.codex-plugin"
    cache.mkdir(parents=True)
    (cache / "plugin.json").write_text(json.dumps({"mcpServers": {"serena": {"command": "false"}}}))
    path = tmp_path / "config.toml"
    path.write_text('[plugins."serena@market"]\nenabled=false\n')
    records, _, _, _ = estate.inventory(policy(), [("codex", path)])
    plugin = next(r for r in records if r["route"] == "serena@market")
    assert plugin["spec"]["disabled"] is True


def test_inactive_project_is_counted_but_never_launched(tmp_path, monkeypatch):
    path = tmp_path / "claude.json"
    path.write_text(
        json.dumps(
            {
                "projects": {
                    "/unselected/private-project": {
                        "mcpServers": {"serena": {"command": "false", "args": ["--open-web-dashboard", "false"]}}
                    }
                }
            }
        )
    )
    records, issues, _, _ = estate.inventory(policy(), [("claude", path)])
    monkeypatch.setattr(estate, "verify", lambda *args: pytest.fail("inactive project launched"))
    result = estate.measure(policy(), records, issues)
    row = next(r for r in result["servers"] if r["client"] == "claude")
    assert row["reason"] == "outside_active_client_scope"
    assert row["dimensions"]["protocol"] == "unmeasured"


def test_functional_calls_require_explicit_read_only_contract():
    calls = [{"method": "tools/call", "params": {"name": "health", "arguments": {}}}]
    result = protocol.verify(stdio(SERVER), expected={"tools": ["open_dashboard"]}, safe_calls=calls)
    assert result["dimensions"]["protocol"] == "fail"
    assert "functional_calls" not in result


def test_safe_functional_result_is_checked_and_content_is_not_reported():
    code = SERVER.replace(
        "else: result={'tools':[{'name':'open_dashboard'}]}",
        "elif q['method']=='tools/call': result={'content':[{'type':'text','text':'private probe data'}]}\n else: result={'tools':[{'name':'open_dashboard'}]}",
    )
    calls = [{"method": "tools/call", "params": {"name": "health", "arguments": {}}, "read_only": True}]
    result = protocol.verify(stdio(code), expected={"tools": ["open_dashboard"]}, safe_calls=calls)
    assert result["dimensions"]["functional"] == "pass"
    assert result["functional_calls"] == {"attempted": 1, "passed": 1}
    assert "private probe data" not in json.dumps(result)


@pytest.mark.parametrize("spec", [None, False, "bad", [], 3])
def test_invalid_undeclared_registration_remains_counted(tmp_path, spec):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"mcpServers": {"unknown": spec}}))
    records, issues, _, _ = estate.inventory(policy(), [("codex", path)])
    row = next(r for r in records if r["name"] == "unknown")
    assert row["spec"]["invalid"]
    result = estate.measure(policy(), records, issues, inventory_only=True)
    assert result["denominator"]["registrations"] == 2
    assert result["exit"] == 77


def test_duplicate_json_keys_are_unavailable(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"mcpServers":{},"mcpServers":{"serena":{}}}')
    with pytest.raises(ValueError, match="duplicate"):
        estate.read_config(path)


@pytest.mark.parametrize("field", ["plugins", "projects"])
def test_malformed_optional_tables_do_not_hide_registration(tmp_path, field):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({field: [False], "mcpServers": {"serena": {"command": "false"}}}))
    records, issues, _, _ = estate.inventory(policy(), [("claude", path)])
    assert any(r["name"] == "serena" and r["client"] == "claude" for r in records)
    assert issues


def test_installed_plugin_version_wins_over_old_cache(tmp_path):
    for version in ("1", "2"):
        root = tmp_path / "plugins/cache/market/serena" / version
        root.mkdir(parents=True)
        (root / ".mcp.json").write_text(json.dumps({"mcpServers": {"serena": {"command": version}}}))
    (tmp_path / "plugins/installed_plugins.json").write_text(
        json.dumps({"plugins": {"serena@market": [{"scope": "user", "installPath": str(root), "version": "2"}]}})
    )
    path = tmp_path / "config.toml"
    path.write_text('[plugins."serena@market"]\nenabled=true\n')
    records, issues, _, _ = estate.inventory(policy(), [("codex", path)])
    plugin = next(r for r in records if r["route"] == "serena@market")
    assert plugin["spec"]["command"] == "2"
    assert plugin["plugin_selection"] == "installed_registry"
    assert plugin["provenance"][0]["source"] == "overridden-plugin-cache"
    assert not plugin["provenance"][0]["active"]
    assert not issues


def test_installed_project_plugin_cannot_override_another_project(tmp_path):
    roots = []
    for version in ("1", "2"):
        root = tmp_path / "plugins/cache/market/serena" / version
        root.mkdir(parents=True)
        roots.append(root)
    (tmp_path / "plugins/installed_plugins.json").write_text(
        json.dumps(
            {
                "plugins": {
                    "serena@market": [
                        {"scope": "user", "installPath": str(roots[0]), "version": "1"},
                        {
                            "scope": "project",
                            "projectPath": str(tmp_path / "project"),
                            "installPath": str(roots[1]),
                            "version": "2",
                        },
                    ]
                }
            }
        )
    )
    path = tmp_path / "config.toml"
    assert estate.installed_plugin_roots(path, "serena@market", tmp_path / "other")[0] == [roots[0]]
    assert estate.installed_plugin_roots(path, "serena@market", tmp_path / "project")[0] == [roots[1]]


def test_observed_client_environments_do_not_share_shell_roots(tmp_path, monkeypatch):
    monkeypatch.setattr(estate, "MCP_VENDOR_KEYS", ("codex",))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    observed = tmp_path / "native/config.toml"
    observed.parent.mkdir()
    observed.write_text('[mcp_servers.serena]\ncommand="native"\n')
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "shell"))
    records, _, _, _ = estate.inventory(policy(), client_environments={"codex": {"CODEX_HOME": str(observed.parent)}})
    row = next(r for r in records if r["client"] == "codex" and r["name"] == "serena" and r["route"] == "standalone")
    assert row["spec"]["command"] == "native"


def test_quiet_serena_requires_explicit_false_even_with_probe_policy():
    record = {
        "service": "serena",
        "policy": {"verification": {"quiet_probe": True}},
        "spec": estate.normalize({"command": "serena", "args": []}),
    }
    assert not estate.quiet_probe_allowed(record)
    record["spec"]["args"] = ["--open-web-dashboard", "false"]
    assert estate.quiet_probe_allowed(record)


@pytest.mark.parametrize(
    "field,value", [("enabled", "false"), ("disabled", 0), ("cwd", []), ("bearer_token_env_var", {})]
)
def test_malformed_launch_fields_are_not_coerced(field, value):
    assert estate.normalize({"command": "false", field: value})["invalid"]
