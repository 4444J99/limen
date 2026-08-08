from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "mcp-server-boot.py"
VERIFY = Path(__file__).resolve().parents[2] / "scripts" / "verify-mcp-estate.sh"


def _load_module(monkeypatch: pytest.MonkeyPatch, codex_home: Path):
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    spec = importlib.util.spec_from_file_location("mcp_server_boot_test", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _http_server(name: str, *, agent: str = "codex") -> dict:
    return {
        "agent": agent,
        "name": name,
        "transport": "http",
        "url": f"https://example.test/{name}",
    }


def test_codex_config_discovery_honors_relocated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    codex_home = tmp_path / "relocated-codex"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(
        '[mcp_servers.launchdarkly]\nurl = "https://mcp.launchdarkly.com/mcp/launchdarkly"\n'
    )

    module = _load_module(monkeypatch, codex_home)

    codex_config = next(path for agent, path, _ in module.CONFIG_PATHS if agent == "codex")
    discovered = [
        server for server in module.discover() if server["agent"] == "codex" and server["name"] == "launchdarkly"
    ]
    assert codex_config == codex_home / "config.toml"
    assert discovered[0]["config"] == str(codex_config)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {
                "servers": [
                    {"name": "launchdarkly", "auth_status": "auth needed"},
                    {
                        "name": "authenticated-server",
                        "authentication": {"status": "logged_in"},
                    },
                    {"name": "unknown-server", "status": "enabled"},
                ]
            },
            {
                "launchdarkly": "auth_needed",
                "authenticated-server": "authenticated",
            },
        ),
        (
            {
                "mcp_servers": {
                    "LaunchDarkly": {"status": "login-required"},
                    "ready-server": {"authStatus": "ready"},
                }
            },
            {
                "launchdarkly": "auth_needed",
                "ready-server": "authenticated",
            },
        ),
        (
            [
                {"name": "login", "auth_status": "notLoggedIn"},
                {"name": "token", "auth_status": "bearerToken"},
                {"name": "oauth", "auth_status": "oAuth"},
                {"name": "unsupported", "auth_status": "unsupported"},
            ],
            {
                "login": "auth_needed",
                "token": "authenticated",
                "oauth": "authenticated",
            },
        ),
    ],
)
def test_codex_status_parser_tolerates_known_envelopes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    payload: object,
    expected: dict[str, str],
) -> None:
    module = _load_module(monkeypatch, tmp_path / "codex")

    assert module.parse_codex_mcp_statuses(payload) == expected


def test_probe_all_distinguishes_oauth_from_reachability(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = _load_module(monkeypatch, tmp_path / "codex")
    monkeypatch.setattr(
        module,
        "_codex_mcp_statuses",
        lambda: {
            "launchdarkly": "auth_needed",
            "authenticated-server": "authenticated",
        },
    )
    monkeypatch.setattr(module, "_probe_http", lambda _url, _timeout: (True, "reachable"))

    auth_needed, authenticated = module.probe_all(
        [_http_server("launchdarkly"), _http_server("authenticated-server")],
        timeout=1,
    )

    assert (auth_needed["ok"], auth_needed["state"]) == (False, "auth_needed")
    assert "OAuth authentication required" in auth_needed["detail"]
    assert (authenticated["ok"], authenticated["state"]) == (True, "authenticated")


def test_non_codex_http_probe_remains_transport_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = _load_module(monkeypatch, tmp_path / "codex")
    monkeypatch.setattr(module, "_probe_http", lambda _url, _timeout: (True, "reachable"))

    [result] = module.probe_all([_http_server("remote", agent="gemini")], timeout=1)

    assert (result["ok"], result["state"]) == (True, "reachable")


def test_estate_ownership_scan_honors_relocated_codex_home() -> None:
    shell = VERIFY.read_text(encoding="utf-8")

    assert '"${CODEX_HOME:-$HOME/.codex}/config.toml"' in shell
    assert '"$HOME/.codex/config.toml"' not in shell
