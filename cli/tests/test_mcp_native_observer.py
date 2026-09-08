from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import mcp_native_observer as observer


def broker(state="active", expires=200, heartbeat=100, agent="codex"):
    def stamp(value):
        return datetime.fromtimestamp(value, timezone.utc).isoformat()

    node = {
        "run_id": "run-fixture",
        "executor_session_id": "session-fixture",
        "packet": {"authority": {"actions": ["read"]}},
        "lease": {
            "state": state,
            "hard_deadline": stamp(expires),
            "heartbeat_at": stamp(heartbeat),
            "executor": {"agent": agent},
            "lease_id": "lease-fixture",
            "generation": 1,
        },
    }
    return SimpleNamespace(graph=lambda _: {"nodes": [node]})


@pytest.mark.parametrize(
    "kwargs", [{"state": "reserved"}, {"state": "released"}, {"expires": 99}, {"heartbeat": -300}, {"agent": "claude"}]
)
def test_native_observer_rejects_unowned_or_expired_runs(kwargs):
    with pytest.raises(observer.ProtocolError):
        observer.require_live_run(broker(**kwargs), "run-fixture", 100)


def test_native_observer_binds_live_run():
    assert observer.require_live_run(broker(), "run-fixture", 101)["generation"] == 1


def test_native_skill_catalog_does_not_claim_rendered_budget():
    catalog = observer.native_skills(
        {
            "data": [
                {
                    "cwd": "/private/project",
                    "errors": [],
                    "skills": [
                        {
                            "name": "fixture",
                            "path": "/private/skill/SKILL.md",
                            "description": "private fixture description",
                            "scope": "repo",
                            "enabled": True,
                        }
                    ],
                }
            ]
        }
    )
    assert catalog["native_skills"] == 1
    assert catalog["runtime_budget"] is None
    assert catalog["stripped_descriptions"] is None
    assert not catalog["fresh_native_loading_witness"]
    assert "/private/" not in str(catalog)
    assert "private fixture description" not in str(catalog)


@pytest.mark.parametrize("response", [{}, {"data": {}}, {"data": [{"skills": [], "errors": None}]}])
def test_native_malformed_catalog_refuses_success(response):
    with pytest.raises(observer.ProtocolError):
        observer.native_skills(response)


def test_native_wire_rejects_login_or_elicitation_request():
    # Keep the fixture leader alive until collector cleanup, so this contract
    # tests refusal and owned cleanup rather than racing an unrelated EOF exit.
    code = "import sys,json; q=json.loads(sys.stdin.readline()); print(json.dumps({'id':q['id'],'method':'login','params':{}}),flush=True); sys.stdin.read()"
    wire = observer.NativeWire({"transport": "stdio", "command": sys.executable, "args": ["-c", code]}, 2, "native")
    try:
        wire.start()
        with pytest.raises(observer.ProtocolError, match="unexpected client request"):
            wire.exchange("initialize")
    finally:
        wire.close()
    assert wire.cleanup == "pass"


@pytest.mark.parametrize("failure", [None, "changed_config", "version", "pagination", "wrong_route"])
def test_collector_observes_native_route_and_refuses_dependency_races(monkeypatch, tmp_path, failure):
    from contextlib import nullcontext
    import limen.host_admission
    import mcp_estate as estate

    calls = []
    declaration = {"command": "synthetic"}
    safe_calls = [
        {
            "method": "tools/call",
            "server": "fixture",
            "params": {"name": "health", "arguments": {}},
            "read_only": True,
            "launch_fingerprint": "wrong"
            if failure == "wrong_route"
            else estate.fingerprint(estate.normalize(declaration)),
        }
    ]
    monkeypatch.setattr(observer.time, "time", lambda: 101)
    monkeypatch.setattr(observer.shutil, "which", lambda _: "/fixture/codex")
    monkeypatch.setattr(observer, "file_digest", lambda _: "binary-content")
    monkeypatch.setattr(observer.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="codex-cli 1"))
    monkeypatch.setattr(limen.host_admission, "hold_lease", lambda *a, **k: nullcontext())

    class Native:
        def __init__(self, *args):
            self.cleanup = "unmeasured"
            self.process = SimpleNamespace(pid=12345)
            self.config_reads = 0

        def start(self):
            calls.append("start")

        def close(self):
            calls.append("close")
            self.cleanup = "pass"

        def exchange(self, method, *args, **kwargs):
            calls.append(method)
            if method == "initialize":
                return {"userAgent": "codex/2" if failure == "version" else "codex/1"}
            if method == "initialized":
                return {}
            if method == "config/read":
                self.config_reads += 1
                return {
                    "config": {
                        "fixture": self.config_reads if failure == "changed_config" else 1,
                        "mcp_servers": {"fixture": declaration},
                    }
                }
            if method == "skills/list":
                return {"data": [{"skills": [], "errors": []}]}
            if method == "thread/start":
                assert args[0]["ephemeral"] is True
                return {"thread": {"id": "native-fixture-thread"}}
            if method == "mcpServer/tool/call":
                assert args[0] == {
                    "threadId": "native-fixture-thread",
                    "server": "fixture",
                    "tool": "health",
                    "arguments": {},
                }
                return {"content": [{"type": "text", "text": "private functional response"}]}
            if method == "mcpServerStatus/list":
                return {
                    "data": [
                        {
                            "name": "fixture",
                            "serverInfo": {"version": "server-1"},
                            "tools": {"health": {}},
                            "runtimeStatus": "connected",
                        }
                    ],
                    "nextCursor": "repeated" if failure == "pagination" else None,
                }
            pytest.fail("unexpected native request")

    monkeypatch.setattr(observer, "NativeWire", Native)
    if failure:
        with pytest.raises(observer.ProtocolError):
            observer.collect_codex(broker(), "run-fixture", tmp_path, include_mcp=True, safe_calls=safe_calls)
        assert "mcpServer/tool/call" not in calls
    else:
        result = observer.collect_codex(broker(), "run-fixture", tmp_path, include_mcp=True, safe_calls=safe_calls)
        assert result["servers"][0]["server_version"] == "server-1"
        assert result["run_id"] == "run-fixture"
        assert result["native_session_id"]
        assert result["cleanup"] == "pass"
        assert result["native_session_id"] == "native-fixture-thread"
        assert result["functional"] == {"attempted": 1, "passed": 1, "state": "pass"}
        assert "private functional response" not in str(result)
    assert calls[-1] == "close"
    assert not any("login" in method or "turn/" in method for method in calls)


@pytest.mark.parametrize(
    "call", [{}, {"method": "tools/call", "read_only": False}, {"method": "login", "read_only": True}]
)
def test_native_functional_contract_refuses_unowned_effects(call):
    with pytest.raises(observer.ProtocolError):
        observer.native_call_contract([call])
