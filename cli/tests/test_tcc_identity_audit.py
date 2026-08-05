"""Executable contracts for the stable-host TCC inventory."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/tcc-identity-audit.py"
WRAPPER = ROOT / "scripts/tcc-identity-audit"
SPEC = importlib.util.spec_from_file_location("tcc_identity_audit", SCRIPT)
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def _database(path: Path, rows: list[tuple]) -> Path:
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE access ("
        "service TEXT NOT NULL, client TEXT NOT NULL, "
        "client_type INTEGER NOT NULL, auth_value INTEGER NOT NULL DEFAULT 2, "
        "last_modified INTEGER NOT NULL)"
    )
    normalized = []
    for row in rows:
        if len(row) == 4:
            client, client_type, service, modified = row
            normalized.append((client, client_type, service, 2, modified))
        elif len(row) == 5:
            normalized.append(row)
        else:
            raise ValueError("TCC fixture rows must have four or five fields")
    connection.executemany(
        "INSERT INTO access(client, client_type, service, auth_value, last_modified) VALUES (?, ?, ?, ?, ?)",
        normalized,
    )
    connection.commit()
    connection.close()
    return path


def _environment(
    tmp_path: Path,
    rows: list[tuple],
    *,
    host_app_management: bool = True,
) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir()
    normalized_rows = list(rows)
    if host_app_management:
        normalized_rows.append(
            (
                "org.organvm.domus.agent-host",
                0,
                "kTCCServiceSystemPolicyAppBundles",
                2,
                1000,
            )
        )
    database = _database(tmp_path / "TCC.db", normalized_rows)
    status = tmp_path / "host-status.json"
    status.write_text(
        json.dumps(
            {
                "schema": "domus.agent_host_status.v1",
                "ok": True,
                "bundle_id": "org.organvm.domus.agent-host",
                "stable_path": True,
                "signature_valid": True,
                "designated_requirement": 'cdhash H"' + "a" * 40 + '"',
                "cdhash": "a" * 40,
            }
        )
    )
    launch_services = tmp_path / "lsregister.txt"
    launch_services.write_text("")
    env = {
        "HOME": str(home),
        "PATH": "/usr/bin:/bin",
        "LIMEN_TCC_DB": str(database),
        "LIMEN_TCC_HOST_STATUS_JSON": str(status),
        "LIMEN_TCC_LSREGISTER_DUMP": str(launch_services),
    }
    clients, _ = AUDIT._read_clients(
        (database,),
        baseline_identities=None,
        application=home / "Applications/DomusAgentHost.app",
        env=env,
    )
    baseline = tmp_path / "identity-baseline.json"
    baseline.write_text(json.dumps(AUDIT._identity_baseline_document(clients)))
    env["LIMEN_TCC_IDENTITY_BASELINE"] = str(baseline)
    return env


def _host_status_json() -> str:
    return json.dumps(
        {
            "schema": "domus.agent_host_status.v1",
            "ok": True,
            "bundle_id": "org.organvm.domus.agent-host",
            "stable_path": True,
            "signature_valid": True,
            "designated_requirement": 'cdhash H"' + "a" * 40 + '"',
            "cdhash": "a" * 40,
        }
    )


def test_disabled_baseline_versions_are_visible_but_not_active_leaks(tmp_path: Path):
    home = tmp_path / "home"
    rows = [
        (
            str(home / ".local/share/claude/versions/release-alpha"),
            1,
            "kTCCServiceSystemPolicyDownloadsFolder",
            0,
            900,
        ),
        (
            "/opt/homebrew/Cellar/python@next/build-alpha/bin/python",
            1,
            "kTCCServiceSystemPolicyDocumentsFolder",
            0,
            901,
        ),
        (
            "org.organvm.domus.agent-host",
            0,
            "kTCCServiceSystemPolicyDownloadsFolder",
            1001,
        ),
        ("com.example.unrelated", 0, "kTCCServiceMicrophone", 999),
    ]
    payload = AUDIT.audit(
        _environment(tmp_path, rows),
        platform_name="Darwin",
    )
    assert payload["schema"] == "limen.tcc_identity_audit.v2"
    assert payload["ok"] is True
    assert payload["summary"] == {
        "stable_host": 1,
        "baseline_managed": 2,
        "managed_unbaselined": 0,
        "new_managed": 0,
        "active_leaks": 0,
        "visible_app_management_path_rows": 0,
        "unhosted_configured_ingresses": 0,
        # Revoked (auth_value 0) version-path grants are not future re-prompts.
        "rotating_identity_active_grants": 0,
        "unrelated": 1,
    }
    assert {item["classification"] for item in payload["clients"]} == {
        "stable_host",
        "baseline_managed",
        "unrelated",
    }
    assert (
        next(item for item in payload["clients"] if item["classification"] == "unrelated")["client"]
        == "com.example.unrelated"
    )


def test_live_inventory_merges_user_and_system_tcc_databases(tmp_path: Path):
    home = tmp_path / "home"
    application = home / "Applications/DomusAgentHost.app"
    user_database = _database(
        tmp_path / "user-TCC.db",
        [
            (
                str(home / ".local/share/claude/versions/release-alpha"),
                1,
                "kTCCServiceSystemPolicyDocumentsFolder",
                900,
            ),
            ("com.example.shared", 0, "kTCCServiceMicrophone", 800),
        ],
    )
    system_database = _database(
        tmp_path / "system-TCC.db",
        [
            (
                "org.organvm.domus.agent-host",
                0,
                "kTCCServiceSystemPolicyAllFiles",
                1001,
            ),
            ("com.example.shared", 0, "kTCCServiceSystemPolicyAllFiles", 1002),
        ],
    )

    clients, unrelated = AUDIT._read_clients(
        (user_database, system_database),
        baseline_identities=frozenset(
            {
                AUDIT._identity_id(
                    str(home / ".local/share/claude/versions/release-alpha"),
                    1,
                )
            }
        ),
        application=application,
        env={"HOME": str(home)},
    )

    assert sum(item["classification"] == "stable_host" for item in clients) == 1
    assert sum(item["classification"] == "baseline_managed" for item in clients) == 1
    assert unrelated == 1
    shared = next(item for item in clients if item["client"] == "com.example.shared")
    assert shared["last_modified"] == 1002
    assert shared["services"] == [
        "kTCCServiceMicrophone",
        "kTCCServiceSystemPolicyAllFiles",
    ]


def test_live_tcc_databases_include_user_and_system_stores(tmp_path: Path):
    assert AUDIT._tcc_databases({"HOME": str(tmp_path)}) == (
        tmp_path / "Library/Application Support/com.apple.TCC/TCC.db",
        Path("/Library/Application Support/com.apple.TCC/TCC.db"),
    )


def test_revoked_decisions_remain_in_the_identity_inventory(tmp_path: Path):
    home = tmp_path / "home"
    application = home / "Applications/DomusAgentHost.app"
    database = _database(
        tmp_path / "TCC.db",
        [
            (
                str(home / ".local/share/claude/versions/revoked-release"),
                1,
                "kTCCServicePhotos",
                1002,
            ),
            (
                str(home / ".local/share/claude/versions/active-release"),
                1,
                "kTCCServiceMicrophone",
                1003,
            ),
            ("com.example.revoked", 0, "kTCCServicePhotos", 1004),
        ],
    )
    connection = sqlite3.connect(database)
    connection.execute("UPDATE access SET auth_value = 0 WHERE service = 'kTCCServicePhotos'")
    connection.commit()
    connection.close()

    clients, unrelated = AUDIT._read_clients(
        (database,),
        baseline_identities=frozenset(
            {
                AUDIT._identity_id(
                    str(home / ".local/share/claude/versions/revoked-release"),
                    1,
                ),
                AUDIT._identity_id(
                    str(home / ".local/share/claude/versions/active-release"),
                    1,
                ),
            }
        ),
        application=application,
        env={"HOME": str(home)},
    )

    assert {item["client"] for item in clients} == {
        str(home / ".local/share/claude/versions/revoked-release"),
        str(home / ".local/share/claude/versions/active-release"),
        "com.example.revoked",
    }
    revoked = next(item for item in clients if "revoked-release" in item["client"])
    assert revoked["classification"] == "baseline_managed"
    assert revoked["active"] is False
    assert revoked["decisions"][0]["auth_value"] == 0
    assert unrelated == 1


def test_arbitrary_rotated_claude_and_python_paths_are_active_leaks(
    tmp_path: Path,
):
    home = tmp_path / "home"
    rows = [
        (
            str(home / ".local/share/claude/versions/release-omega"),
            1,
            "kTCCServiceSystemPolicyAppBundles",
            1002,
        ),
        (
            str(home / "Workspace/limen/.venv/bin/python9"),
            1,
            "kTCCServiceSystemPolicyAppBundles",
            1003,
        ),
        (
            "/opt/homebrew/Cellar/uv/build-omega/bin/uvx",
            1,
            "kTCCServiceSystemPolicyAppBundles",
            1004,
        ),
    ]
    payload = AUDIT.audit(
        _environment(tmp_path, rows),
        platform_name="Darwin",
    )
    assert payload["ok"] is False
    assert payload["summary"]["active_leaks"] == 3
    assert "active_managed_tcc_leak" in payload["failures"]
    assert {item["pattern"] for item in payload["clients"] if item["pattern"]} == {
        "claude_version",
        "limen_venv",
        "homebrew_cellar",
    }


def test_configured_dispatch_worktree_python_is_an_active_leak(
    tmp_path: Path,
):
    worktrees = tmp_path / "dispatch-worktrees"
    rows = [
        (
            str(worktrees / "lane-omega/.agent-runtime/bin/python3.14"),
            1,
            "kTCCServiceSystemPolicyAppBundles",
            1004,
        )
    ]
    env = _environment(tmp_path, rows)
    env["LIMEN_WORKTREE_ROOT"] = str(worktrees)

    payload = AUDIT.audit(env, platform_name="Darwin")

    assert payload["ok"] is False
    assert payload["summary"]["active_leaks"] == 1
    assert payload["clients"][0]["pattern"] == "limen_venv"


def test_default_dispatch_worktree_roots_are_active_leaks(
    tmp_path: Path,
):
    home = tmp_path / "home"
    rows = [
        (
            str(home / "Workspace/.limen-worktrees/lane-alpha/.venv/bin/python3.15"),
            1,
            "kTCCServiceSystemPolicyAppBundles",
            1004,
        ),
        (
            "/Volumes/Scratch/limen-worktrees/lane-beta/.agent-runtime/bin/python4",
            1,
            "kTCCServiceSystemPolicyAppBundles",
            1005,
        ),
    ]
    env = _environment(tmp_path, rows)

    payload = AUDIT.audit(env, platform_name="Darwin")

    assert payload["ok"] is False
    assert payload["summary"]["active_leaks"] == 2
    assert {item["pattern"] for item in payload["clients"] if item["pattern"]} == {"limen_venv"}


def test_limen_workdir_dispatch_root_is_an_active_leak(
    tmp_path: Path,
):
    workdir = tmp_path / "custom-workspace"
    rows = [
        (
            str(workdir / ".limen-worktrees/lane-gamma/.venv/bin/python3.16"),
            1,
            "kTCCServiceSystemPolicyAppBundles",
            1005,
        )
    ]
    env = _environment(tmp_path, rows)
    env["LIMEN_WORKDIR"] = str(workdir)

    payload = AUDIT.audit(env, platform_name="Darwin")

    assert payload["ok"] is False
    assert payload["summary"]["active_leaks"] == 1
    assert payload["clients"][0]["pattern"] == "limen_venv"


def test_three_independent_predicates_match_the_live_regression_shape(
    tmp_path: Path,
):
    home = tmp_path / "home"
    app_management = "kTCCServiceSystemPolicyAppBundles"
    serena = str(home / "Library/Caches/uv/serena-rotated/bin/python")
    rows = [
        ("/opt/homebrew/Cellar/ruby/3.4.1/bin/ruby", 1, app_management, 2, 900),
        ("/usr/local/Cellar/ruby/3.3.0/bin/ruby", 1, app_management, 2, 901),
        (
            str(home / ".local/share/claude/versions/release-history"),
            1,
            app_management,
            0,
            902,
        ),
        ("/opt/homebrew/Cellar/python@3.14/3.14.1/bin/python3", 1, app_management, 0, 903),
        (
            "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3",
            1,
            app_management,
            0,
            904,
        ),
        (str(home / ".cache/uv/history/bin/python"), 1, app_management, 0, 905),
        (
            str(home / "Workspace/limen/.venv/bin/python"),
            1,
            app_management,
            0,
            906,
        ),
        (serena, 1, app_management, 2, 1),
    ]
    env = _environment(tmp_path, rows, host_app_management=False)
    baseline_path = Path(env["LIMEN_TCC_IDENTITY_BASELINE"])
    baseline = json.loads(baseline_path.read_text())
    baseline["managed_identities"].remove(AUDIT._identity_id(serena, 1))
    body = {key: value for key, value in baseline.items() if key != "digest"}
    baseline["digest"] = AUDIT._baseline_digest(body)
    baseline_path.write_text(json.dumps(baseline))

    payload = AUDIT.audit(env, platform_name="Darwin")

    assert payload["predicates"]["active_leaks"]["count"] == 3
    visible = payload["predicates"]["visible_app_management_path_rows"]
    assert visible["count"] == 8
    assert visible["stable_host_row_count"] == 0
    assert visible["stable_host_grant_count"] == 0
    assert payload["predicates"]["unhosted_configured_ingresses"]["count"] == 0
    serena_item = next(item for item in payload["clients"] if item["identity"] == AUDIT._identity_id(serena, 1))
    assert serena_item["classification"] == "new_managed"
    assert serena not in json.dumps(payload)


def test_writing_a_baseline_is_redacted_deterministic_and_private(tmp_path: Path):
    home = tmp_path / "home"
    managed_path = str(home / ".local/share/claude/versions/release-alpha")
    env = _environment(
        tmp_path,
        [
            (
                managed_path,
                1,
                "kTCCServiceSystemPolicyAppBundles",
                0,
                800,
            ),
            (
                "com.example.preserved",
                0,
                "kTCCServiceSystemPolicyAppBundles",
                2,
                801,
            ),
        ],
    )
    baseline_path = tmp_path / "written-baseline.json"

    payload = AUDIT.audit(
        env,
        platform_name="Darwin",
        write_baseline=baseline_path,
    )
    document = json.loads(baseline_path.read_text())

    assert payload["identity_baseline"]["written"] is True
    assert baseline_path.stat().st_mode & 0o777 == 0o600
    assert managed_path not in baseline_path.read_text()
    assert document["managed_identities"] == [AUDIT._identity_id(managed_path, 1)]
    assert document["app_management_bundle_grants"] == [{"auth_value": 2, "client": "com.example.preserved"}]
    body = {key: value for key, value in document.items() if key != "digest"}
    assert document["digest"] == AUDIT._baseline_digest(body)


def test_writing_a_baseline_refuses_to_replace_the_cutover_anchor(tmp_path: Path):
    env = _environment(tmp_path, [])
    baseline_path = tmp_path / "existing-baseline.json"
    baseline_path.write_text("preserve-me")

    payload = AUDIT.audit(
        env,
        platform_name="Darwin",
        write_baseline=baseline_path,
    )

    assert payload["ok"] is False
    assert "identity_baseline_write_failed" in payload["failures"]
    assert "refusing to overwrite" in payload["identity_baseline"]["error"]
    assert baseline_path.read_text() == "preserve-me"


def test_configured_local_ingresses_fail_until_every_command_uses_ensure(
    tmp_path: Path,
):
    env = _environment(tmp_path, [])
    home = Path(env["HOME"])
    desktop = home / "Library/Application Support/Claude/claude_desktop_config.json"
    desktop.parent.mkdir(parents=True)
    desktop.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "serena": {"command": "uvx", "args": ["serena"]},
                }
            }
        )
    )
    claude = home / ".claude.json"
    claude.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "github": {
                        "command": str(home / ".local/bin/domus-agent-host"),
                        "args": ["ensure", "--", "github-mcp-server", "stdio"],
                    }
                }
            }
        )
    )
    codex = home / ".local/share/codex/config.toml"
    codex.parent.mkdir(parents=True)
    codex.write_text('[mcp_servers.conductor]\ncommand = "organvm-conductor-mcp"\n')

    before = AUDIT.audit(env, platform_name="Darwin")
    desktop.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "serena": {
                        "command": str(home / ".local/bin/domus-agent-host"),
                        "args": ["ensure", "--", "uvx", "serena"],
                    }
                }
            }
        )
    )
    codex.write_text(
        "[mcp_servers.conductor]\n"
        f'command = "{home}/.local/bin/domus-agent-host"\n'
        'args = ["ensure", "--", "organvm-conductor-mcp"]\n'
    )
    after = AUDIT.audit(env, platform_name="Darwin")

    ingress = before["predicates"]["unhosted_configured_ingresses"]
    assert ingress["configured_count"] == 3
    assert ingress["count"] == 2
    assert {(item["surface"], item["server"]) for item in ingress["ingresses"]} == {
        ("claude_desktop", "serena"),
        ("codex_desktop", "conductor"),
    }
    assert after["predicates"]["unhosted_configured_ingresses"] == {
        "ok": True,
        # Config-derived, so it stays measurable even when the TCC database is blind.
        "measured": True,
        "count": 0,
        "configured_count": 3,
        "ingresses": [],
    }


def test_ingress_rejects_an_impostor_with_the_host_wrapper_basename(tmp_path: Path):
    env = _environment(tmp_path, [])
    home = Path(env["HOME"])
    desktop = home / "Library/Application Support/Claude/claude_desktop_config.json"
    desktop.parent.mkdir(parents=True)
    desktop.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "serena": {
                        "command": str(tmp_path / "impostor/domus-agent-host"),
                        "args": ["ensure", "--", "uvx", "serena"],
                    }
                }
            }
        )
    )

    payload = AUDIT.audit(env, platform_name="Darwin")

    ingress = payload["predicates"]["unhosted_configured_ingresses"]
    assert ingress["ok"] is False
    assert ingress["count"] == 1
    assert ingress["ingresses"][0]["command"] == "domus-agent-host"


def test_unrelated_app_management_bundle_grants_must_match_the_baseline(
    tmp_path: Path,
):
    env = _environment(
        tmp_path,
        [
            (
                "com.example.preserved",
                0,
                "kTCCServiceSystemPolicyAppBundles",
                2,
                800,
            )
        ],
    )
    connection = sqlite3.connect(env["LIMEN_TCC_DB"])
    connection.execute("UPDATE access SET auth_value = 0 WHERE client = 'com.example.preserved'")
    connection.commit()
    connection.close()

    payload = AUDIT.audit(env, platform_name="Darwin")

    assert payload["unrelated_app_management_preservation"]["ok"] is False
    assert "unrelated_app_management_grants_changed" in payload["failures"]


def test_stable_application_follows_dispatch_host_configuration(
    tmp_path: Path,
):
    home = tmp_path / "home"
    executable = home / "Applications/ConfiguredHost.app/Contents/MacOS/DomusAgentHost"
    env = {
        "HOME": str(home),
        "LIMEN_AGENT_HOST_BIN": ("~/Applications/ConfiguredHost.app/Contents/MacOS/DomusAgentHost"),
    }

    assert AUDIT._stable_host_executable(env) == executable
    assert AUDIT._stable_application(env) == (home / "Applications/ConfiguredHost.app")


def test_wrapper_skips_missing_python_only_when_not_strict(tmp_path: Path):
    dirname = shutil.which("dirname")
    assert dirname is not None
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "dirname").symlink_to(dirname)
    env = {
        "HOME": str(tmp_path),
        "PATH": str(bin_dir),
    }

    non_strict = subprocess.run(
        ["/bin/sh", str(WRAPPER), "--json"],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )
    strict = subprocess.run(
        ["/bin/sh", str(WRAPPER), "--json", "--strict"],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )

    assert non_strict.returncode == 0
    assert "SKIP: Python 3 is unavailable" in non_strict.stderr
    assert strict.returncode == os.EX_UNAVAILABLE
    assert "Python 3 is unavailable" in strict.stderr


def test_wrapper_requires_live_host_lifetime_descriptor(tmp_path: Path):
    dirname = shutil.which("dirname")
    assert dirname is not None
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "dirname").symlink_to(dirname)
    (bin_dir / "uname").write_text("#!/bin/sh\nprintf Darwin\n")
    (bin_dir / "python3").write_text("#!/bin/sh\nprintf python\n")
    host = tmp_path / "DomusAgentHost"
    host.write_text("#!/bin/sh\nprintf host\n")
    primary_host = tmp_path / "PrimaryDomusAgentHost"
    primary_host.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        f"  status) printf '%s\\n' '{_host_status_json()}' ;;\n"
        '  verify-lifetime) [ "${DOMUS_AGENT_HOST_LIFETIME_ID:-}" = expected ] ;;\n'
        "  run) printf primary-host ;;\n"
        "esac\n"
    )
    for executable in (
        bin_dir / "uname",
        bin_dir / "python3",
        host,
        primary_host,
    ):
        executable.chmod(0o755)
    env = {
        "DOMUS_AGENT_HOST_ACTIVE": "1",
        "DOMUS_AGENT_HOST_BIN": str(host),
        "LIMEN_AGENT_HOST_BIN": str(primary_host),
        "HOME": str(tmp_path),
        "PATH": str(bin_dir),
    }

    stale = subprocess.run(
        ["/bin/sh", str(WRAPPER)],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )
    read_fd, write_fd = os.pipe()
    try:
        live = subprocess.run(
            ["/bin/sh", str(WRAPPER)],
            capture_output=True,
            check=False,
            env={
                **env,
                "DOMUS_AGENT_HOST_LIFETIME_FD": str(write_fd),
                "DOMUS_AGENT_HOST_LIFETIME_ID": "expected",
            },
            pass_fds=(write_fd,),
            text=True,
        )
    finally:
        os.close(read_fd)
        os.close(write_fd)

    assert stale.returncode == 0
    assert stale.stdout == "primary-host"
    assert live.returncode == 0
    assert live.stdout == "python"


def test_wrapper_expands_configured_host_home_path(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    dirname = shutil.which("dirname")
    assert dirname is not None
    (bin_dir / "dirname").symlink_to(dirname)
    (bin_dir / "uname").write_text("#!/bin/sh\nprintf Darwin\n")
    (bin_dir / "python3").write_text("#!/bin/sh\nprintf python\n")
    host = tmp_path / "Applications/ConfiguredHost.app/Contents/MacOS/DomusAgentHost"
    host.parent.mkdir(parents=True)
    host.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        f"  status) printf '%s\\n' '{_host_status_json()}' ;;\n"
        "  verify-lifetime) exit 1 ;;\n"
        "  run) printf configured-host ;;\n"
        "esac\n"
    )
    for executable in (bin_dir / "uname", bin_dir / "python3", host):
        executable.chmod(0o755)

    completed = subprocess.run(
        ["/bin/sh", str(WRAPPER), "--json", "--strict"],
        capture_output=True,
        check=False,
        env={
            "HOME": str(tmp_path),
            "PATH": str(bin_dir),
            "LIMEN_AGENT_HOST_BIN": ("~/Applications/ConfiguredHost.app/Contents/MacOS/DomusAgentHost"),
        },
        text=True,
    )

    assert completed.returncode == 0
    assert completed.stdout == "configured-host"


def test_wrapper_rejects_executable_without_host_contract(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    dirname = shutil.which("dirname")
    assert dirname is not None
    (bin_dir / "dirname").symlink_to(dirname)
    (bin_dir / "uname").write_text("#!/bin/sh\nprintf Darwin\n")
    (bin_dir / "python3").write_text("#!/bin/sh\nprintf python\n")
    wrong_host = tmp_path / "wrong-host"
    wrong_host.write_text("#!/bin/sh\nexit 0\n")
    for executable in (
        bin_dir / "uname",
        bin_dir / "python3",
        wrong_host,
    ):
        executable.chmod(0o755)

    completed = subprocess.run(
        ["/bin/sh", str(WRAPPER), "--json", "--strict"],
        capture_output=True,
        check=False,
        env={
            "HOME": str(tmp_path),
            "PATH": str(bin_dir),
            "LIMEN_AGENT_HOST_BIN": str(wrong_host),
        },
        text=True,
    )

    assert completed.returncode == os.EX_UNAVAILABLE
    assert "host contract is invalid" in completed.stderr


def test_update_disabling_controls_fail_the_same_strict_predicate(tmp_path: Path):
    env = _environment(tmp_path, [])
    env["DISABLE_UPDATES"] = "1"
    payload = AUDIT.audit(env, platform_name="Darwin")
    assert payload["automatic_updates"]["enabled"] is False
    assert payload["automatic_updates"]["blockers"] == [{"key": "DISABLE_UPDATES", "source": "environment"}]
    assert "automatic_updates_disabled" in payload["failures"]


def test_update_controls_follow_configured_limen_root(tmp_path: Path):
    env = _environment(tmp_path, [])
    limen_root = tmp_path / "configured-limen"
    settings = limen_root / ".agent-runtime/claude/settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"env": {"DISABLE_AUTOUPDATER": "true"}}))
    env["LIMEN_ROOT"] = str(limen_root)

    payload = AUDIT.audit(env, platform_name="Darwin")

    assert payload["automatic_updates"]["enabled"] is False
    assert {
        "key": "DISABLE_AUTOUPDATER",
        "source": str(settings),
    } in payload["automatic_updates"]["blockers"]
    assert "automatic_updates_disabled" in payload["failures"]


def test_stable_host_contract_rejects_a_wrong_bundle_identity(tmp_path: Path):
    env = _environment(tmp_path, [])
    status_path = Path(env["LIMEN_TCC_HOST_STATUS_JSON"])
    status = json.loads(status_path.read_text())
    status["bundle_id"] = "com.example.rotating-host"
    status_path.write_text(json.dumps(status))

    payload = AUDIT.audit(env, platform_name="Darwin")

    assert payload["ok"] is False
    assert payload["stable_host"]["contract_failures"] == ["bundle_id"]
    assert "stable_host_invalid" in payload["failures"]


def test_stable_host_contract_rejects_non_object_json(tmp_path: Path):
    env = _environment(tmp_path, [])
    Path(env["LIMEN_TCC_HOST_STATUS_JSON"]).write_text("[]")

    payload = AUDIT.audit(env, platform_name="Darwin")

    assert payload["ok"] is False
    assert payload["stable_host"] == {
        "ok": False,
        "error": "stable-host status fixture is malformed",
    }
    assert "stable_host_invalid" in payload["failures"]


def test_strict_audit_rejects_fixture_backed_host_status(tmp_path: Path):
    env = _environment(tmp_path, [])

    payload = AUDIT.audit(
        env,
        platform_name="Darwin",
        strict=True,
    )

    assert payload["ok"] is False
    assert payload["stable_host"] == {
        "ok": False,
        "error": "strict audit rejects fixture-backed stable-host status",
    }
    assert "stable_host_invalid" in payload["failures"]


def test_strict_host_contract_binds_deployment_identity_receipt(tmp_path: Path):
    home = tmp_path / "home"
    application = home / "Applications/DomusAgentHost.app"
    receipt = home / "Applications/.DomusAgentHost.designated-requirement"
    receipt.parent.mkdir(parents=True)
    requirement = 'cdhash H"' + "a" * 40 + '"'
    receipt.write_text(requirement + "\n")
    payload = _host_status_json()

    def runner(command, **kwargs):
        assert command == [
            str(application / "Contents/MacOS/DomusAgentHost"),
            "status",
            "--json",
        ]
        return subprocess.CompletedProcess(command, 0, payload, "")

    matched = AUDIT._host_status(
        {"HOME": str(home)},
        runner,
        strict=True,
    )
    receipt.write_text('cdhash H"' + "b" * 40 + '"\n')
    replaced = AUDIT._host_status(
        {"HOME": str(home)},
        runner,
        strict=True,
    )

    assert matched["ok"] is True
    assert matched["deployment_identity_matches"] is True
    assert replaced["ok"] is False
    assert replaced["deployment_identity_matches"] is False
    assert "deployment_identity" in replaced["contract_failures"]


def test_strict_audit_requires_stable_host_tcc_identity(tmp_path: Path):
    env = _environment(tmp_path, [], host_app_management=False)

    non_strict = AUDIT.audit(env, platform_name="Darwin")
    strict = AUDIT.audit(
        env,
        platform_name="Darwin",
        strict=True,
    )

    assert "stable_host_tcc_identity_missing" not in non_strict["failures"]
    assert "stable_host_tcc_identity_missing" in strict["failures"]


def test_historical_toggle_changes_activity_without_reclassifying_identity(
    tmp_path: Path,
):
    home = tmp_path / "home"
    client = str(home / ".local/share/claude/versions/release-history")
    env = _environment(
        tmp_path,
        [
            (
                client,
                1,
                "kTCCServiceSystemPolicyAppBundles",
                0,
                900,
            )
        ],
    )

    before = AUDIT.audit(env, platform_name="Darwin")
    connection = sqlite3.connect(env["LIMEN_TCC_DB"])
    connection.execute(
        "UPDATE access SET auth_value = 2, last_modified = 999999 WHERE client = ?",
        (client,),
    )
    connection.commit()
    connection.close()
    after = AUDIT.audit(env, platform_name="Darwin")

    before_client = next(item for item in before["clients"] if item["identity"] == AUDIT._identity_id(client, 1))
    after_client = next(item for item in after["clients"] if item["identity"] == AUDIT._identity_id(client, 1))
    assert before_client["classification"] == "baseline_managed"
    assert after_client["classification"] == "baseline_managed"
    assert before["predicates"]["active_leaks"]["count"] == 0
    assert after["predicates"]["active_leaks"]["count"] == 1
    assert before["predicates"]["visible_app_management_path_rows"]["count"] == 1
    assert after["predicates"]["visible_app_management_path_rows"]["count"] == 1


def test_strict_audit_rejects_fixture_backed_launchservices_inventory(
    tmp_path: Path,
):
    env = _environment(tmp_path, [])

    payload = AUDIT.audit(
        env,
        platform_name="Darwin",
        strict=True,
    )

    assert "claude_helper_registration_unreadable" in payload["failures"]
    assert payload["malformed_claude_helpers"] == [
        {
            "path": "",
            "detail": "strict audit rejects fixture-backed LaunchServices inventory",
        }
    ]


def test_malformed_registered_claude_helper_is_blocking(tmp_path: Path):
    env = _environment(tmp_path, [])
    helper = Path(env["HOME"]) / ".local/share/claude/ClaudeCode.app"
    helper.mkdir(parents=True)
    Path(env["LIMEN_TCC_LSREGISTER_DUMP"]).write_text(f"path: {helper}\n")

    def runner(command, **kwargs):
        assert command[:3] == ["codesign", "--verify", "--strict"]
        return subprocess.CompletedProcess(command, 1, "", "invalid resource seal")

    payload = AUDIT.audit(env, platform_name="Darwin", runner=runner)
    assert payload["ok"] is False
    assert payload["malformed_claude_helpers"] == [{"path": str(helper), "detail": "invalid resource seal"}]
    assert "malformed_claude_helper_registration" in payload["failures"]


def test_non_macos_is_explicitly_not_applicable():
    payload = AUDIT.audit({}, platform_name="Linux")
    assert payload["ok"] is True
    assert payload["status"] == "not_applicable"
    assert payload["platform_supported"] is False


def test_strict_cli_returns_failure_and_emits_json(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    home = tmp_path / "home"
    rows = [
        (
            str(home / ".local/share/claude/versions/release-omega"),
            1,
            "kTCCServiceSystemPolicyAppBundles",
            1002,
        )
    ]
    env = _environment(tmp_path, rows)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    status = AUDIT.main(
        [
            "--json",
            "--strict",
            "--db",
            env["LIMEN_TCC_DB"],
        ]
    )

    assert status == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["summary"]["active_leaks"] == 1


# --- Regression contracts: the two blind spots that discharged L-DOMUS-AGENT-HOST-TCC ---
#
# On 2026-08-05 the Track C closeout finalized `met` and discharged the lever while
# Claude Code auto-updates were OFF, so the version could never advance and the
# "survives a vendor update" proof could never be exercised. inventory_green() DOES
# guard on automatic_updates_disabled — but _disabled_updates() only scanned env vars,
# settings.json `env` blocks and ~/.limen.env, and never read `autoUpdates` in
# .claude.json. The guard was blind to the field it guarded.


def test_auto_updates_false_in_claude_json_is_an_update_blocker(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude.json").write_text(json.dumps({"autoUpdates": False}))
    blockers = AUDIT._disabled_updates({"HOME": str(home), "LIMEN_ROOT": str(tmp_path / "absent")})
    assert [item["key"] for item in blockers] == ["autoUpdates_false"]


def test_auto_updates_absent_means_enabled(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude.json").write_text(json.dumps({"numStartups": 3}))
    assert AUDIT._disabled_updates({"HOME": str(home), "LIMEN_ROOT": str(tmp_path / "absent")}) == []


def test_auto_updates_read_from_claude_config_dir_not_only_home(tmp_path: Path):
    """The split-brain case: a session under CLAUDE_CONFIG_DIR never reads ~/.claude.json.

    Flipping only the home copy leaves updates off where the session actually runs,
    which is exactly the state the 2026-08-05 discharge was produced in.
    """
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude.json").write_text(json.dumps({"autoUpdates": True}))
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / ".claude.json").write_text(json.dumps({"autoUpdates": False}))
    blockers = AUDIT._disabled_updates(
        {
            "HOME": str(home),
            "LIMEN_ROOT": str(tmp_path / "absent"),
            "CLAUDE_CONFIG_DIR": str(runtime),
        }
    )
    assert [item["key"] for item in blockers] == ["autoUpdates_false"]
    assert str(runtime) in blockers[0]["source"]


def test_unreadable_tcc_database_is_unmeasured_not_a_finding(tmp_path: Path):
    """An unreadable database must not manufacture verdicts in either direction.

    Before this contract an empty `clients` list produced one false green
    (active_leaks ok/0 — asserting zero leaks having observed nothing) and two
    false reds (stable_host_app_management_grant_missing,
    unrelated_app_management_grants_changed — naming defects nobody looked for).
    """
    env = _environment(tmp_path, [])
    env["LIMEN_TCC_DB"] = str(tmp_path / "does-not-exist.db")
    payload = AUDIT.audit(env, platform_name="Darwin")

    assert payload["status"] == "unmeasured"
    assert payload["measured"]["tcc_database"] is False
    # Fail toward caution: unmeasured is never green.
    assert payload["ok"] is False
    # ...but the only failure is the honest one.
    assert payload["failures"] == ["tcc_database_unavailable"]
    assert "stable_host_app_management_grant_missing" not in payload["failures"]
    assert "unrelated_app_management_grants_changed" not in payload["failures"]
    # The database-derived predicates report unmeasured, never a clean bill of health.
    assert payload["predicates"]["active_leaks"]["measured"] is False
    assert payload["predicates"]["active_leaks"]["ok"] is False
    assert payload["predicates"]["visible_app_management_path_rows"]["measured"] is False
    # The config-derived predicate stays measurable — blindness is scoped, not global.
    assert payload["predicates"]["unhosted_configured_ingresses"]["measured"] is True


def test_documents_grant_on_a_version_path_is_caught_though_app_management_is_clean(tmp_path: Path):
    """The operator's actual dialog, which every prior predicate scored as green.

    `"2.1.222" would like to access files in your Documents folder` is a
    kTCCServiceSystemPolicyDocumentsFolder grant against a path-keyed client under
    ~/.local/share/claude/versions/<version>/. App Management is spotless in this
    fixture — the stable host holds its one bundle grant and no path row carries an
    App Management decision — so `active_leaks` and
    `visible_app_management_path_rows` both report ok. Only the rotating-identity
    predicate sees the sprawl.
    """
    home = tmp_path / "home"
    rows = [
        (
            str(home / ".local/share/claude/versions/2.1.222/claude"),
            1,
            "kTCCServiceSystemPolicyDocumentsFolder",
            2,  # granted, not revoked
            1100,
        ),
    ]
    payload = AUDIT.audit(_environment(tmp_path, rows), platform_name="Darwin")

    # The old lens: clean.
    assert payload["predicates"]["active_leaks"]["ok"] is True
    assert payload["predicates"]["visible_app_management_path_rows"]["ok"] is True

    # The new lens: the re-prompt is visible, and named by service.
    rotating = payload["predicates"]["rotating_identity_active_grants"]
    assert rotating["measured"] is True
    assert rotating["ok"] is False
    assert rotating["count"] == 1
    assert rotating["services"] == ["kTCCServiceSystemPolicyDocumentsFolder"]

    assert "rotating_identity_active_grants" in payload["failures"]
    assert payload["ok"] is False
    assert payload["status"] == "blocked"  # a real finding, never "unmeasured"
