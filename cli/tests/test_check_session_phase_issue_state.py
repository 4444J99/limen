"""scripts/check-session-phase.py::_issue_state falls back to REST when `gh issue view` (GraphQL) fails.

In Claude Code cloud sessions every GraphQL call is HTTP 403, so the `--live` cross-check used to return
None (fail-open) and silently never run. The REST issue endpoint is the twin. gh is faked; no network.
"""

import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check-session-phase.py"
GRAPHQL_403 = "HTTP 403: GitHub GraphQL is not available from Claude Code sessions; use the REST API"


def _load():
    spec = importlib.util.spec_from_file_location("check_session_phase_uut", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_run(monkeypatch, mod, *, view, api):
    calls = []

    def run(argv, **kwargs):
        calls.append(argv[1:3])
        handler = view if argv[1] == "issue" else api
        if isinstance(handler, BaseException):
            raise handler
        return handler

    monkeypatch.setattr(mod.subprocess, "run", run)
    return calls


def test_graphql_success_is_used_and_rest_is_not_touched(monkeypatch):
    mod = _load()
    calls = _fake_run(
        monkeypatch,
        mod,
        view=SimpleNamespace(returncode=0, stdout="closed\n", stderr=""),
        api=AssertionError("no REST"),
    )
    assert mod._issue_state(12) == "CLOSED"
    assert calls == [["issue", "view"]]


def test_graphql_403_falls_back_to_the_rest_issue_endpoint(monkeypatch):
    mod = _load()
    calls = _fake_run(
        monkeypatch,
        mod,
        view=SimpleNamespace(returncode=1, stdout="", stderr=GRAPHQL_403),
        api=SimpleNamespace(returncode=0, stdout=json.dumps({"state": "closed"}), stderr=""),
    )
    assert mod._issue_state(12) == "CLOSED"
    assert calls == [["issue", "view"], ["api", "repos/{owner}/{repo}/issues/12"]]


def test_a_missing_gh_binary_still_tries_rest_then_fails_open(monkeypatch):
    mod = _load()
    _fake_run(monkeypatch, mod, view=FileNotFoundError("gh"), api=FileNotFoundError("gh"))
    assert mod._issue_state(12) is None


def test_both_paths_failing_fails_open_to_none(monkeypatch):
    mod = _load()
    _fake_run(
        monkeypatch,
        mod,
        view=SimpleNamespace(returncode=1, stdout="", stderr=GRAPHQL_403),
        api=SimpleNamespace(returncode=1, stdout="", stderr="gh: Not Found (HTTP 404)"),
    )
    assert mod._issue_state(12) is None


def test_a_hung_gh_fails_open_to_none(monkeypatch):
    mod = _load()
    _fake_run(
        monkeypatch,
        mod,
        view=subprocess.TimeoutExpired(["gh"], 15),
        api=subprocess.TimeoutExpired(["gh"], 15),
    )
    assert mod._issue_state(12) is None
