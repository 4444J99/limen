from contextlib import nullcontext
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import mcp_claude_observer as observer


def status():
    return {
        "mcpServers": [
            {
                "name": "fixture",
                "status": "connected",
                "serverInfo": {"name": "fixture", "version": "1"},
                "config": {"type": "stdio", "command": "fixture", "env": {"TOKEN": "private-value"}},
                "tools": [{"name": "read"}],
                "scope": "project",
            }
        ]
    }


def context():
    return {
        "totalTokens": 10,
        "maxTokens": 100,
        "rawMaxTokens": 120,
        "categories": [{"name": "Skills", "tokens": 3}],
        "memoryFiles": [{"path": "/private/memory"}],
        "skills": {"totalTokens": 3, "entries": [{"name": "private-skill"}]},
    }


@pytest.mark.parametrize("failure", [None, "quiet", "version", "schema", "config_race", "context", "dependency"])
def test_owned_claude_native_collection_never_sends_model_turn_and_cleans(tmp_path, monkeypatch, failure):
    import limen.host_admission

    monkeypatch.setattr(
        observer, "require_live_run", lambda *a: {"run_id": "run-owned", "lease_id": "lease-owned", "generation": 1}
    )
    monkeypatch.setattr(observer.shutil, "which", lambda name: "/synthetic/claude")
    hashes = iter(["binary", "changed" if failure == "dependency" else "binary"])
    monkeypatch.setattr(observer, "file_digest", lambda path: next(hashes))
    monkeypatch.setattr(
        observer.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(stdout="unknown" if failure == "version" else "2.1.232 (Claude Code)"),
    )
    monkeypatch.setattr(limen.host_admission, "hold_lease", lambda *a, **kw: nullcontext())
    requests, closed, launched = [], [], []

    class Native:
        def __init__(self, spec, *args):
            launched.append(spec)
            self.process = SimpleNamespace(pid=1234)
            self.custody = SimpleNamespace(report=lambda: {"measurement": "sampled"})
            self.cleanup = "unmeasured"

        def start(self):
            pass

        def exchange(self, subtype):
            requests.append(subtype)
            if subtype == "initialize":
                return {"commands": [], "account": "private-account"}
            if subtype == "mcp_status":
                response = status()
                if failure == "schema":
                    response["mcpServers"] = {}
                if failure == "config_race" and requests.count("mcp_status") == 2:
                    response["mcpServers"][0]["config"]["env"]["TOKEN"] = "changed"
                return response
            if subtype == "get_context_usage":
                return {} if failure == "context" else context()
            raise AssertionError(subtype)

        def close(self):
            closed.append(True)
            self.cleanup = "pass"

    monkeypatch.setattr(observer, "ClaudeWire", Native)
    if failure:
        with pytest.raises(observer.ProtocolError):
            observer.collect_claude(None, "run-owned", tmp_path, include_mcp=failure != "quiet")
    else:
        result = observer.collect_claude(None, "run-owned", tmp_path, include_mcp=True)
        assert result["servers"][0]["server_version"] == "1"
        assert result["servers"][0]["functional"]["state"] == "unmeasured"
        assert result["skills"]["runtime_budget"] == 100
        assert result["skills"]["stripped_descriptions"] is None
        assert result["cleanup"] == "pass"
        for value in ("private-value", "private-account", "private-skill", "/private/memory"):
            assert value not in json.dumps(result)
    assert closed == ([] if failure in ("quiet", "version") else [True])
    assert set(requests) <= {"initialize", "mcp_status", "get_context_usage"}
    if launched:
        args = launched[0]["args"]
        assert args[args.index("--permission-mode") + 1] == "dontAsk"
        assert "--no-session-persistence" in args
        assert not {"--bare", "--strict-mcp-config", "--disable-slash-commands", "--safe-mode"}.intersection(args)


@pytest.mark.parametrize("subtype", ["mcp_authenticate", "mcp_reconnect", "mcp_toggle", "set_model", "mcp_message"])
def test_control_operation_allowlist(subtype):
    wire = observer.ClaudeWire({"transport": "stdio"}, 1, "native")
    with pytest.raises(observer.ProtocolError, match="outside collector"):
        wire.exchange(subtype)


@pytest.mark.parametrize("change", ["duplicate", "tools", "status", "version"])
def test_malformed_native_status_cannot_bind_receipt(change):
    response = status()
    if change == "duplicate":
        response["mcpServers"] *= 2
    elif change == "tools":
        response["mcpServers"][0]["tools"] = [False]
    elif change == "status":
        response["mcpServers"][0]["status"] = "unknown"
    else:
        response["mcpServers"][0]["serverInfo"] = "1"
    with pytest.raises(observer.ProtocolError):
        observer.status_index(response)


def test_missing_config_and_version_remain_unmeasured():
    response = status()
    server = response["mcpServers"][0]
    del server["config"], server["serverInfo"]
    servers, effective = observer.status_index(response)
    assert servers[0]["server_version"] is None
    assert effective["registrations"]["fixture"]["valid"] is False


def test_context_numerics_exclude_private_keys_and_unsupported_claims():
    response = context()
    response["skills"].update({"/private/path": 4, "nan": float("nan"), "negative": -1, "boolean": True})
    result = observer.context_evidence(response)
    assert result["skill_numeric_metrics"] == {"totalTokens": 3}
    assert result["fresh_native_loading_witness"] is False
    assert "/private/path" not in str(result)
