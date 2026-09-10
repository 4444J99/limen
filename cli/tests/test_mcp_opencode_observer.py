from contextlib import nullcontext
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import mcp_opencode_observer as observer


@pytest.mark.parametrize("failure", [None, "version", "schema", "scope", "status", "config_race", "session"])
def test_native_opencode_uses_own_versioned_session_and_always_cleans(tmp_path, monkeypatch, failure):
    import limen.host_admission

    monkeypatch.setattr(
        observer, "require_live_run", lambda *a: {"run_id": "run-owned", "lease_id": "lease-owned", "generation": 1}
    )
    monkeypatch.setattr(observer.shutil, "which", lambda name: "/synthetic/opencode")
    monkeypatch.setattr(observer, "file_digest", lambda path: "binary")
    monkeypatch.setattr(observer.subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout="1.18.20"))
    monkeypatch.setattr(limen.host_admission, "hold_lease", lambda *a, **kw: nullcontext())
    requests, closed = [], []

    class Native:
        def __init__(self, *args):
            self.session_id = None
            self.process = SimpleNamespace(pid=1234)
            self.custody = SimpleNamespace(report=lambda: {"measurement": "sampled"})
            self.cleanup = self.session_cleanup = "unmeasured"

        def start(self):
            pass

        def ready(self):
            return {"healthy": True, "version": "wrong" if failure == "version" else "1.18.20"}

        def request(self, path, method="GET", body=None):
            requests.append((method, path))
            if path == "/doc":
                return {
                    "paths": {}
                    if failure == "schema"
                    else {
                        "/config": {"get": {}},
                        "/path": {"get": {}},
                        "/mcp": {"get": {}},
                        "/session": {"post": {}},
                        "/session/{sessionID}": {"delete": {}},
                    }
                }
            if path == "/config":
                return {
                    "mcp": {},
                    "private": "never-export",
                    "generation": requests.count(("GET", "/config")) if failure == "config_race" else 1,
                }
            if path == "/path":
                return {"directory": str(tmp_path / "other") if failure == "scope" else str(tmp_path)}
            if path == "/session":
                return {"id": "bad" if failure == "session" else "ses_owned"}
            if path == "/mcp":
                return {"fixture": False if failure == "status" else {"status": "connected"}}
            raise AssertionError(path)

        def close(self):
            closed.append(True)
            self.cleanup = self.session_cleanup = "pass"

    monkeypatch.setattr(observer, "NativeHTTP", Native)
    if failure:
        with pytest.raises(observer.ProtocolError):
            observer.collect_opencode(None, "run-owned", tmp_path, include_mcp=True)
    else:
        result = observer.collect_opencode(None, "run-owned", tmp_path, include_mcp=True)
        assert result["native_session_id"] == "ses_owned"
        assert result["client"] == "opencode"
        assert result["servers"][0]["runtime_status"] == "connected"
        assert result["servers"][0]["server_version"] is None
        assert "never-export" not in str(result)
        assert result["cleanup"] == result["session_cleanup"] == "pass"
    assert closed == [True]
    assert all(method == "GET" or (method, path) == ("POST", "/session") for method, path in requests)


@pytest.mark.parametrize(
    "path,method",
    [
        ("/provider/x/oauth/authorize", "POST"),
        ("/config", "PATCH"),
        ("/session/foreign", "DELETE"),
        ("/session/owned/message", "POST"),
    ],
)
def test_native_http_refuses_login_config_edits_messages_and_foreign_cleanup(path, method, tmp_path):
    native = observer.NativeHTTP("synthetic", tmp_path, 1)
    native.session_id = "ses_owned"
    with pytest.raises(observer.ProtocolError, match="outside collector"):
        native.request(path, method)


def test_native_session_cleanup_failure_still_reaps_owned_runtime(tmp_path, monkeypatch):
    native = observer.NativeHTTP("synthetic", tmp_path, 1)
    native.session_id = "ses_owned"

    def fail(*a, **kw):
        raise OSError("synthetic request failure")

    monkeypatch.setattr(native, "request", fail)
    native.custody = SimpleNamespace(close=lambda: "pass")
    native.close()
    assert native.session_cleanup == "fail"
    assert native.cleanup == "pass"
