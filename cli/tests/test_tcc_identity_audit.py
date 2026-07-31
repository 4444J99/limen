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


def _database(path: Path, rows: list[tuple[str, int, str, int]]) -> Path:
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE access ("
        "service TEXT NOT NULL, client TEXT NOT NULL, "
        "client_type INTEGER NOT NULL, last_modified INTEGER NOT NULL)"
    )
    connection.executemany(
        "INSERT INTO access(client, client_type, service, last_modified) VALUES (?, ?, ?, ?)",
        rows,
    )
    connection.commit()
    connection.close()
    return path


def _environment(tmp_path: Path, rows: list[tuple[str, int, str, int]]) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir()
    database = _database(tmp_path / "TCC.db", rows)
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
    return {
        "HOME": str(home),
        "PATH": "/usr/bin:/bin",
        "LIMEN_TCC_DB": str(database),
        "LIMEN_TCC_HOST_STATUS_JSON": str(status),
        "LIMEN_TCC_LSREGISTER_DUMP": str(launch_services),
        "LIMEN_TCC_HOST_DEPLOYED_AT": "1000",
    }


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


def test_predeployment_versions_are_legacy_and_do_not_fail(tmp_path: Path):
    home = tmp_path / "home"
    rows = [
        (
            str(home / ".local/share/claude/versions/release-alpha"),
            1,
            "kTCCServiceSystemPolicyDownloadsFolder",
            900,
        ),
        (
            "/opt/homebrew/Cellar/python@next/build-alpha/bin/python",
            1,
            "kTCCServiceSystemPolicyDocumentsFolder",
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
    assert payload["schema"] == "limen.tcc_identity_audit.v1"
    assert payload["ok"] is True
    assert payload["summary"] == {
        "stable_host": 1,
        "legacy_stale": 2,
        "versioned_leak": 0,
        "unrelated": 1,
    }
    assert {item["classification"] for item in payload["clients"]} == {
        "stable_host",
        "legacy_stale",
        "unrelated",
    }
    assert (
        next(item for item in payload["clients"] if item["classification"] == "unrelated")["client"]
        == "com.example.unrelated"
    )


def test_arbitrary_rotated_claude_and_python_paths_are_versioned_leaks(
    tmp_path: Path,
):
    home = tmp_path / "home"
    rows = [
        (
            str(home / ".local/share/claude/versions/release-omega"),
            1,
            "kTCCServiceSystemPolicyDownloadsFolder",
            1002,
        ),
        (
            str(home / "Workspace/limen/.venv/bin/python9"),
            1,
            "kTCCServicePhotos",
            1003,
        ),
        (
            "/opt/homebrew/Cellar/uv/build-omega/bin/uvx",
            1,
            "kTCCServiceSystemPolicyDownloadsFolder",
            1004,
        ),
    ]
    payload = AUDIT.audit(
        _environment(tmp_path, rows),
        platform_name="Darwin",
    )
    assert payload["ok"] is False
    assert payload["summary"]["versioned_leak"] == 3
    assert "versioned_tcc_client_after_host_deployment" in payload["failures"]
    assert {item["pattern"] for item in payload["clients"]} == {
        "claude_version",
        "limen_venv",
        "homebrew_cellar",
    }


def test_configured_dispatch_worktree_python_is_a_versioned_leak(
    tmp_path: Path,
):
    worktrees = tmp_path / "dispatch-worktrees"
    rows = [
        (
            str(worktrees / "lane-omega/.agent-runtime/bin/python3.14"),
            1,
            "kTCCServiceSystemPolicyDownloadsFolder",
            1004,
        )
    ]
    env = _environment(tmp_path, rows)
    env["LIMEN_WORKTREE_ROOT"] = str(worktrees)

    payload = AUDIT.audit(env, platform_name="Darwin")

    assert payload["ok"] is False
    assert payload["summary"]["versioned_leak"] == 1
    assert payload["clients"][0]["pattern"] == "limen_venv"


def test_default_dispatch_worktree_roots_are_versioned_leaks(
    tmp_path: Path,
):
    home = tmp_path / "home"
    rows = [
        (
            str(home / "Workspace/.limen-worktrees/lane-alpha/.venv/bin/python3.15"),
            1,
            "kTCCServiceSystemPolicyDownloadsFolder",
            1004,
        ),
        (
            "/Volumes/Scratch/limen-worktrees/lane-beta/.agent-runtime/bin/python4",
            1,
            "kTCCServiceSystemPolicyDocumentsFolder",
            1005,
        ),
    ]
    env = _environment(tmp_path, rows)

    payload = AUDIT.audit(env, platform_name="Darwin")

    assert payload["ok"] is False
    assert payload["summary"]["versioned_leak"] == 2
    assert {item["pattern"] for item in payload["clients"]} == {"limen_venv"}


def test_limen_workdir_dispatch_root_is_a_versioned_leak(
    tmp_path: Path,
):
    workdir = tmp_path / "custom-workspace"
    rows = [
        (
            str(workdir / ".limen-worktrees/lane-gamma/.venv/bin/python3.16"),
            1,
            "kTCCServiceSystemPolicyDocumentsFolder",
            1005,
        )
    ]
    env = _environment(tmp_path, rows)
    env["LIMEN_WORKDIR"] = str(workdir)

    payload = AUDIT.audit(env, platform_name="Darwin")

    assert payload["ok"] is False
    assert payload["summary"]["versioned_leak"] == 1
    assert payload["clients"][0]["pattern"] == "limen_venv"


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
    env = _environment(tmp_path, [])

    non_strict = AUDIT.audit(env, platform_name="Darwin")
    strict = AUDIT.audit(
        env,
        platform_name="Darwin",
        strict=True,
    )

    assert "stable_host_tcc_identity_missing" not in non_strict["failures"]
    assert "stable_host_tcc_identity_missing" in strict["failures"]


def test_invalid_deployment_epoch_is_a_machine_readable_failure(tmp_path: Path):
    env = _environment(tmp_path, [])
    env["LIMEN_TCC_HOST_DEPLOYED_AT"] = "not-an-epoch"

    payload = AUDIT.audit(env, platform_name="Darwin")

    assert payload["schema"] == "limen.tcc_identity_audit.v1"
    assert payload["ok"] is False
    assert payload["host_deployed_at"] is None
    assert payload["host_deployment_error"] == "LIMEN_TCC_HOST_DEPLOYED_AT must be an integer"
    assert "deployment_epoch_invalid" in payload["failures"]


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
            "kTCCServiceSystemPolicyDownloadsFolder",
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
    assert payload["summary"]["versioned_leak"] == 1
