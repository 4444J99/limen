from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "mcp-server-boot.py"
VERIFY = Path(__file__).resolve().parents[2] / "scripts" / "verify-mcp-estate.sh"


def _load_module(monkeypatch: pytest.MonkeyPatch, codex_home: Path | str):
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


def test_empty_codex_home_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """An exported-but-empty relocation variable must not resolve to `/config.toml`.

    Asserted through CONFIG_PATHS rather than a module constant: the resolution moved into
    scripts/agent_config_paths.py so all three relocation variables get the same treatment, and
    a test pinned to the old `CODEX_HOME` constant would pass while claude and gemini stayed broken.
    """
    module = _load_module(monkeypatch, "")

    codex_config = next(path for agent, path, _ in module.CONFIG_PATHS if agent == "codex")
    assert codex_config == Path.home() / ".codex" / "config.toml"


def test_codex_status_probe_honors_registered_executable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_module(monkeypatch, tmp_path / "codex-home")
    codex_bin = tmp_path / "fixed" / "codex"
    codex_bin.parent.mkdir()
    codex_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    codex_bin.chmod(0o755)
    monkeypatch.setenv("LIMEN_CODEX_BIN", str(codex_bin))
    invocations: list[list[str]] = []

    def fake_run(argv: list[str], **_kwargs: object):
        invocations.append(argv)
        return module.subprocess.CompletedProcess(argv, 0, "[]", "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert module._codex_mcp_statuses() == ({}, None)
    assert invocations == [[str(codex_bin), "mcp", "list", "--json"]]


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
                {
                    "name": "token",
                    "auth_status": "bearerToken",
                    "bearer_token_env_var": "TEST_MCP_TOKEN",
                },
                {"name": "oauth", "auth_status": "oAuth"},
                {"name": "unsupported", "auth_status": "unsupported"},
            ],
            {
                "login": "auth_needed",
                "token": "authenticated",
                "oauth": "authenticated",
                "unsupported": "reachable",
            },
        ),
    ],
)
def test_codex_status_parser_tolerates_known_envelopes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    payload: object,
    expected: dict[str, object],
) -> None:
    module = _load_module(monkeypatch, tmp_path / "codex")
    monkeypatch.setenv("TEST_MCP_TOKEN", "present")

    assert module.parse_codex_mcp_statuses(payload) == expected


def test_probe_all_distinguishes_oauth_from_reachability(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = _load_module(monkeypatch, tmp_path / "codex")
    monkeypatch.setattr(
        module,
        "_codex_mcp_statuses",
        lambda: (
            {
                "launchdarkly": "auth_needed",
                "authenticated-server": "authenticated",
            },
            None,
        ),
    )
    monkeypatch.setattr(module, "_probe_http", lambda _url, _timeout: (True, "reachable"))

    auth_needed, authenticated = module.probe_all(
        [_http_server("launchdarkly"), _http_server("authenticated-server")],
        timeout=1,
    )

    assert (auth_needed["ok"], auth_needed["state"]) == (False, "auth_needed")
    assert "Codex OAuth authentication required" in auth_needed["detail"]
    assert (authenticated["ok"], authenticated["state"]) == (True, "authenticated")


def test_open_loopback_ianva_does_not_inherit_hosted_oauth_semantics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_module(monkeypatch, tmp_path / "codex")
    monkeypatch.setattr(module, "_codex_mcp_statuses", lambda: ({"ianva": "auth_needed"}, None))
    monkeypatch.setattr(module, "_probe_http", lambda _url, _timeout: (True, "reachable"))
    server = {
        "agent": "codex",
        "name": "ianva",
        "transport": "http",
        "url": "http://127.0.0.1:7666/mcp",
        "bearer_token_env_var": None,
    }

    [result] = module.probe_all([server], timeout=1)

    assert (result["ok"], result["state"]) == (True, "reachable")


def test_stdio_probe_resolves_relative_command_against_declared_cwd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_module(monkeypatch, tmp_path / "codex")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    client = runtime / "client"
    client.write_text("#!/bin/sh\nexit 0\n")
    client.chmod(0o755)
    server = {
        "agent": "codex",
        "name": "computer-use",
        "transport": "stdio",
        "command": "./client",
        "args": [],
        "env": {},
        "cwd": str(runtime),
    }

    ok, detail = module._probe_stdio(server, timeout=1)

    assert ok is True
    assert detail == "boots (clean start, no handshake)"


def test_bearer_status_requires_the_named_environment_value(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_module(monkeypatch, tmp_path / "codex")
    row = {
        "name": "token",
        "auth_status": "bearerToken",
        "transport": {"bearer_token_env_var": "ABSENT_MCP_TOKEN"},
    }
    monkeypatch.delenv("ABSENT_MCP_TOKEN", raising=False)

    assert module.parse_codex_mcp_statuses([row]) == {
        "token": {"state": "auth_needed", "missing_env": "ABSENT_MCP_TOKEN"}
    }
    assert module.parse_codex_mcp_statuses([{"name": "token", "auth_status": "bearerToken"}]) == {
        "token": "auth_unknown"
    }

    monkeypatch.setenv("ABSENT_MCP_TOKEN", "present")
    assert module.parse_codex_mcp_statuses([row]) == {"token": "authenticated"}


def test_codex_status_probe_failure_is_not_transport_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_module(monkeypatch, tmp_path / "codex")
    monkeypatch.setattr(
        module,
        "_codex_mcp_statuses",
        lambda: ({}, "Codex status probe timed out"),
    )
    monkeypatch.setattr(module, "_probe_http", lambda _url, _timeout: (True, "reachable"))

    [result] = module.probe_all([_http_server("launchdarkly")], timeout=1)

    assert (result["ok"], result["state"]) == (False, "auth_unknown")
    assert "timed out" in result["detail"]


def test_auth_failures_are_not_sent_to_the_boot_healer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_module(monkeypatch, tmp_path / "codex")
    results = [
        {"state": "auth_needed"},
        {"state": "auth_unknown"},
        {"state": "boot_failed"},
        {"state": "unreachable"},
    ]

    assert module._healable_failures(results) == results[2:]


def test_failure_cures_match_the_failure_semantics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_module(monkeypatch, tmp_path / "codex")
    failed = [
        {
            "agent": "codex",
            "name": "launchdarkly",
            "state": "auth_needed",
            "detail": "reachable; Codex OAuth authentication required",
        },
        {
            "agent": "codex",
            "name": "token-server",
            "state": "auth_needed",
            "detail": "reachable; missing bearer environment TEST_MCP_TOKEN",
        },
        {"agent": "codex", "name": "unknown", "state": "auth_unknown", "detail": "timed out"},
        {"agent": "cline", "name": "local", "state": "boot_failed", "detail": "exited"},
    ]

    assert module._failure_cures(failed) == [
        "codex mcp login launchdarkly",
        "populate TEST_MCP_TOKEN through the credential organ",
        "codex mcp list --json (restore semantic auth telemetry)",
        "arm LIMEN_MCP_BOOT_HEAL=1 (re-land config and clear corrupt npx caches)",
    ]


def test_non_codex_http_probe_remains_transport_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = _load_module(monkeypatch, tmp_path / "codex")
    monkeypatch.setattr(module, "_probe_http", lambda _url, _timeout: (True, "reachable"))

    [result] = module.probe_all([_http_server("remote", agent="gemini")], timeout=1)

    assert (result["ok"], result["state"]) == (True, "reachable")


def test_estate_ownership_scan_hardcodes_no_agent_config_path() -> None:
    """The ownership invariant must scan the configs the CLIs actually read.

    Honouring CODEX_HOME alone was not enough: the array still spelled out the claude and gemini
    paths, so on this host it audited files those CLIs abandoned on 2026-08-05. A placeholder
    secret in the live config was therefore invisible while a stale copy passed the check. The
    array is now derived from scripts/agent_config_paths.py, which owns the fact for the estate.
    """
    shell = VERIFY.read_text(encoding="utf-8")

    assert "agent_config_paths.py" in shell
    for hardcoded in (
        '"$HOME/.codex/config.toml"',
        '"${CODEX_HOME:-$HOME/.codex}/config.toml"',
        '"$HOME/.claude.json"',
        '"$HOME/.gemini/settings.json"',
        '"$HOME/.gemini/config/mcp_config.json"',
    ):
        assert hardcoded not in shell, f"{hardcoded} is hardcoded; derive it instead"
