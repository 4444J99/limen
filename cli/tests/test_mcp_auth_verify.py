"""mcp-auth-verify — the MCP-connector consent predicate (Lane B of the credential estate).

Pins that the missing `--verify` for the claude.ai hosted-MCP lane: parses the daemon's needs-auth
cache + `claude mcp list` without leaking internal ids, is FAIL-OPEN/non-fatal by default (a lapsed
optional connector never breaks the beat — the whole point of moving the nag out of chat), and gates
nonzero only under --strict or a --required lapse. Mirrors test_credential_wall.py's import pattern.
"""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _mod(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _mcp():
    return _mod("mcp_auth_verify", "scripts/mcp-auth-verify.py")


CACHE_FIXTURE = {
    "claude.ai Sentry": {"timestamp": 1, "id": "mcpsrv_secretlookingid"},
    "claude.ai Jam": {"timestamp": 2, "id": "mcpsrv_another"},
}

MCP_LIST_FIXTURE = """Checking MCP server health…

claude.ai Three.js 3D Viewer: https://example.modelcontextprotocol.io/threejs/mcp - ✔ Connected
claude.ai Sentry: https://mcp.sentry.dev/mcp - ! Needs authentication
ianva: http://127.0.0.1:7666/mcp (HTTP) - ✔ Connected
"""


def test_parse_needs_auth_cache_names_only():
    m = _mcp()
    names = m.parse_needs_auth_cache(CACHE_FIXTURE)
    assert names == ["claude.ai Jam", "claude.ai Sentry"]  # sorted, names only
    assert all("mcpsrv" not in n for n in names)  # internal server ids never surface


def test_parse_needs_auth_cache_tolerates_nondict():
    m = _mcp()
    assert m.parse_needs_auth_cache(None) == []
    assert m.parse_needs_auth_cache([1, 2]) == []


def test_parse_mcp_list_status_and_url_robustness():
    m = _mcp()
    parsed = m.parse_mcp_list(MCP_LIST_FIXTURE)
    assert parsed["claude.ai Sentry"] == "needs_auth"
    assert parsed["claude.ai Three.js 3D Viewer"] == "connected"  # name with dots/spaces
    assert parsed["ianva"] == "connected"  # localhost url with :port still parses
    assert not any(k.lower().startswith("checking") for k in parsed)  # header ignored


def test_verdict_default_is_failopen_with_orphans():
    m = _mcp()
    v = m.verdict(["claude.ai Sentry"], None, set(), strict=False)
    assert v["exit"] == 0  # non-fatal by default
    assert v["needs_auth"] == ["claude.ai Sentry"]


def test_verdict_strict_gates_nonzero():
    m = _mcp()
    assert m.verdict(["claude.ai Sentry"], None, set(), strict=True)["exit"] == 1
    assert m.verdict([], None, set(), strict=True)["exit"] == 0


def test_verdict_required_lapse_gates_nonzero_by_substring():
    m = _mcp()
    v = m.verdict(["claude.ai Sentry", "claude.ai Jam"], None, {"sentry"}, strict=False)
    assert v["exit"] == 1
    assert v["required_lapsed"] == ["claude.ai Sentry"]


def test_verdict_required_absent_stays_failopen():
    m = _mcp()
    v = m.verdict(["claude.ai Sentry"], None, {"doesnotexist"}, strict=False)
    assert v["exit"] == 0
    assert v["required_lapsed"] == []


def test_main_failopen_when_no_source(monkeypatch, capsys):
    m = _mcp()
    monkeypatch.setattr(m, "run_mcp_list", lambda *a, **k: None)
    monkeypatch.setattr(m, "load_cache", lambda *a, **k: None)
    assert m.main([]) == 0
    assert "fail-open" in capsys.readouterr().out


def test_main_surfaces_cure_non_fatal_no_id_leak(monkeypatch, capsys):
    m = _mcp()
    monkeypatch.setattr(m, "load_cache", lambda *a, **k: CACHE_FIXTURE)
    rc = m.main([])
    out = capsys.readouterr().out
    assert rc == 0  # the whole point: surfaced, never blocks the beat
    assert "L-IANVA-CLOUD" in out  # points at the one permanent cure
    assert "never recited in chat" in out
    assert "mcpsrv" not in out  # internal ids never printed


def test_main_strict_gates_nonzero(monkeypatch):
    m = _mcp()
    monkeypatch.setattr(m, "load_cache", lambda *a, **k: CACHE_FIXTURE)
    assert m.main(["--strict"]) == 1


def test_main_json_shape(monkeypatch, capsys):
    m = _mcp()
    monkeypatch.setattr(m, "load_cache", lambda *a, **k: CACHE_FIXTURE)
    rc = m.main(["--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["cure"] == "L-IANVA-CLOUD (#263)"
    assert sorted(payload["needs_auth"]) == ["claude.ai Jam", "claude.ai Sentry"]
