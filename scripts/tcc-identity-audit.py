#!/usr/bin/env python3
"""Audit macOS TCC clients against the stable Domus responsibility identity."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sqlite3
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any


SCHEMA = "limen.tcc_identity_audit.v1"
HOST_SCHEMA = "domus.agent_host_status.v1"
HOST_BUNDLE_ID = "org.organvm.domus.agent-host"
TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
DISABLE_UPDATE_KEYS = (
    "DISABLE_AUTOUPDATER",
    "DISABLE_UPDATES",
    "HOMEBREW_NO_AUTO_UPDATE",
)
MANAGED_CLIENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "claude_version",
        re.compile(r"/\.local/share/claude/versions/[^/]+(?:/|$)"),
    ),
    (
        "homebrew_cellar",
        re.compile(r"^/(?:opt/homebrew|usr/local)/Cellar/[^/]+/[^/]+/"),
    ),
    (
        "python_framework",
        re.compile(r"^/Library/Frameworks/Python\.framework/Versions/[^/]+/"),
    ),
    (
        "uv_interpreter",
        re.compile(
            r"/(?:\.cache/uv|\.local/share/uv|Library/Caches/uv)/"
            r".*/(?:python(?:[0-9.]*)?|uvx?)(?:/|$)"
        ),
    ),
    (
        "limen_venv",
        re.compile(
            r"/\.local/share/limen/(?:current|runtimes/[^/]+)/"
            r".*/(?:python(?:[0-9.]*)?)(?:/|$)"
        ),
    ),
)

Runner = Callable[..., subprocess.CompletedProcess[str]]


class AuditError(RuntimeError):
    """The read-only audit could not establish its predicate."""


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in TRUE_VALUES


def _home(env: Mapping[str, str]) -> Path:
    return Path(env.get("HOME", str(Path.home()))).expanduser()


def _tcc_database(env: Mapping[str, str]) -> Path:
    override = env.get("LIMEN_TCC_DB")
    if override:
        return Path(override).expanduser()
    return _home(env) / "Library/Application Support/com.apple.TCC/TCC.db"


def _expand_user_path(value: str, env: Mapping[str, str]) -> Path:
    if value == "~":
        return _home(env)
    if value.startswith("~/"):
        return _home(env) / value[2:]
    return Path(value).expanduser()


def _default_stable_application(env: Mapping[str, str]) -> Path:
    return _home(env) / "Applications/DomusAgentHost.app"


def _stable_host_executable(env: Mapping[str, str]) -> Path:
    configured = env.get("LIMEN_AGENT_HOST_BIN") or env.get("DOMUS_AGENT_HOST_BIN")
    if configured:
        return _expand_user_path(configured, env)
    application = _expand_user_path(
        env.get(
            "DOMUS_AGENT_HOST_APP",
            str(_default_stable_application(env)),
        ),
        env,
    )
    return application / "Contents/MacOS/DomusAgentHost"


def _stable_application(env: Mapping[str, str]) -> Path:
    configured = env.get("LIMEN_AGENT_HOST_BIN") or env.get("DOMUS_AGENT_HOST_BIN")
    application_override = env.get("DOMUS_AGENT_HOST_APP")
    if configured:
        executable = _expand_user_path(configured, env)
        if (
            len(executable.parts) < 4
            or executable.parent.name != "MacOS"
            or executable.parent.parent.name != "Contents"
        ):
            raise AuditError("configured stable-host executable is not inside an application bundle")
        application = executable.parents[2]
        if application_override:
            expected = _expand_user_path(application_override, env)
            if application.resolve(strict=False) != expected.resolve(strict=False):
                raise AuditError("configured stable-host executable and application disagree")
        return application
    return _expand_user_path(
        application_override or str(_default_stable_application(env)),
        env,
    )


def _limen_runtime_roots(env: Mapping[str, str]) -> tuple[Path, ...]:
    home = _home(env)
    live_root = _expand_user_path(
        env.get("LIMEN_ROOT", str(home / "Workspace/limen")),
        env,
    )
    roots = [
        live_root,
        live_root / ".worktrees",
        home / "Workspace/.limen-worktrees",
        Path("/Volumes/Scratch/limen-worktrees"),
    ]
    for name in ("LIMEN_WORKTREE_ROOT", "LIMEN_WORKTREES"):
        if value := env.get(name):
            roots.append(_expand_user_path(value, env))
    unique: dict[str, Path] = {}
    for root in roots:
        unique[str(root.resolve(strict=False))] = root
    return tuple(unique.values())


def _is_limen_runtime_client(
    client: str,
    env: Mapping[str, str],
) -> bool:
    path = Path(client)
    if not path.is_absolute() or not re.fullmatch(
        r"python(?:[0-9.]*)?",
        path.name,
    ):
        return False
    if not ({".venv", ".agent-runtime"} & set(path.parts)):
        return False
    for root in _limen_runtime_roots(env):
        try:
            path.relative_to(root)
        except ValueError:
            continue
        return True
    return False


def _deployment_epoch(env: Mapping[str, str], application: Path) -> int | None:
    override = env.get("LIMEN_TCC_HOST_DEPLOYED_AT")
    if override:
        try:
            value = int(override)
        except ValueError as exc:
            raise AuditError("LIMEN_TCC_HOST_DEPLOYED_AT must be an integer") from exc
        return value if value >= 0 else None
    try:
        return int(application.stat().st_birthtime)
    except (AttributeError, OSError):
        return None


def _managed_pattern(
    client: str,
    env: Mapping[str, str],
) -> str | None:
    for name, pattern in MANAGED_CLIENT_PATTERNS:
        if pattern.search(client):
            return name
    if _is_limen_runtime_client(client, env):
        return "limen_venv"
    return None


def _client_exists(client: str) -> bool | None:
    if not client.startswith("/"):
        return None
    try:
        return Path(client).exists()
    except OSError:
        return None


def classify_client(
    client: str,
    *,
    last_modified: int,
    deployment_epoch: int | None,
    application: Path,
    env: Mapping[str, str],
) -> tuple[str, str | None, bool | None]:
    stable_executable = application / "Contents/MacOS/DomusAgentHost"
    if client == HOST_BUNDLE_ID or client in {
        str(application),
        str(stable_executable),
    }:
        return "stable_host", None, _client_exists(client)
    pattern = _managed_pattern(client, env)
    exists = _client_exists(client)
    if pattern is None:
        return "unrelated", None, exists
    if deployment_epoch is not None:
        if last_modified >= deployment_epoch:
            return "versioned_leak", pattern, exists
        return "legacy_stale", pattern, exists
    return ("legacy_stale", pattern, exists) if exists is False else ("versioned_leak", pattern, exists)


def _read_clients(
    database: Path,
    *,
    deployment_epoch: int | None,
    application: Path,
    env: Mapping[str, str],
) -> tuple[list[dict[str, Any]], int]:
    try:
        connection = sqlite3.connect(
            f"{database.resolve().as_uri()}?mode=ro",
            uri=True,
        )
    except (OSError, sqlite3.Error) as exc:
        raise AuditError(f"TCC database is unavailable: {database}") from exc
    try:
        rows = connection.execute(
            "SELECT client, client_type, service, last_modified FROM access ORDER BY client, service"
        ).fetchall()
    except sqlite3.Error as exc:
        raise AuditError("TCC access schema is unreadable") from exc
    finally:
        connection.close()

    grouped: dict[tuple[str, int], dict[str, Any]] = {}
    unrelated = 0
    for client_raw, client_type_raw, service_raw, modified_raw in rows:
        client = str(client_raw)
        client_type = int(client_type_raw)
        modified = int(modified_raw)
        key = (client, client_type)
        item = grouped.setdefault(
            key,
            {
                "client": client,
                "client_type": client_type,
                "last_modified": modified,
                "services": set(),
            },
        )
        item["last_modified"] = max(int(item["last_modified"]), modified)
        item["services"].add(str(service_raw))

    relevant: list[dict[str, Any]] = []
    for item in grouped.values():
        classification, pattern, exists = classify_client(
            str(item["client"]),
            last_modified=int(item["last_modified"]),
            deployment_epoch=deployment_epoch,
            application=application,
            env=env,
        )
        if classification == "unrelated":
            unrelated += 1
            continue
        relevant.append(
            {
                **item,
                "classification": classification,
                "pattern": pattern,
                "exists": exists,
                "services": sorted(item["services"]),
            }
        )
    relevant.sort(key=lambda value: (value["classification"], value["client"]))
    return relevant, unrelated


def _settings_paths(env: Mapping[str, str]) -> list[Path]:
    home = _home(env)
    candidates = [
        home / ".claude/settings.json",
        home / "Workspace/limen/.agent-runtime/claude/settings.json",
    ]
    if config := env.get("CLAUDE_CONFIG_DIR"):
        candidates.append(Path(config).expanduser() / "settings.json")
    seen: set[Path] = set()
    result: list[Path] = []
    for path in candidates:
        resolved = path.resolve(strict=False)
        if resolved not in seen:
            seen.add(resolved)
            result.append(path)
    return result


def _disabled_updates(env: Mapping[str, str]) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    for key in DISABLE_UPDATE_KEYS:
        if _truthy(env.get(key)):
            blockers.append({"key": key, "source": "environment"})
    for path in _settings_paths(env):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, json.JSONDecodeError):
            blockers.append({"key": "settings_unreadable", "source": str(path)})
            continue
        settings_env = document.get("env") if isinstance(document, dict) else None
        if not isinstance(settings_env, dict):
            continue
        for key in DISABLE_UPDATE_KEYS:
            if _truthy(settings_env.get(key)):
                blockers.append({"key": key, "source": str(path)})
    limen_env = Path(env.get("LIMEN_ENV", str(_home(env) / ".limen.env")))
    try:
        lines = limen_env.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = []
    except OSError:
        blockers.append({"key": "limen_env_unreadable", "source": str(limen_env)})
        lines = []
    for raw in lines:
        match = re.match(
            r"^\s*(?:export\s+)?(" + "|".join(DISABLE_UPDATE_KEYS) + r")\s*=\s*(.*?)\s*$",
            raw,
        )
        if match and _truthy(match.group(2).strip("\"'")):
            blockers.append({"key": match.group(1), "source": str(limen_env)})
    unique = {(item["key"], item["source"]): item for item in blockers}
    return [unique[key] for key in sorted(unique)]


def _host_status(env: Mapping[str, str], runner: Runner) -> dict[str, Any]:
    if fixture := env.get("LIMEN_TCC_HOST_STATUS_JSON"):
        try:
            payload = json.loads(Path(fixture).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AuditError("stable-host status fixture is unreadable") from exc
        if not isinstance(payload, dict):
            raise AuditError("stable-host status fixture is malformed")
    else:
        executable = _stable_host_executable(env)
        try:
            completed = runner(
                [str(executable), "status", "--json"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise AuditError("stable-host status command is unavailable") from exc
        try:
            payload = json.loads(completed.stdout or "")
        except json.JSONDecodeError as exc:
            raise AuditError("stable-host status is malformed") from exc
        if not isinstance(payload, dict):
            raise AuditError("stable-host status is malformed")
        if completed.returncode != 0:
            payload["ok"] = False
    if payload.get("schema") != HOST_SCHEMA:
        raise AuditError("stable-host status schema is incompatible")
    contract_failures: list[str] = []
    if payload.get("bundle_id") != HOST_BUNDLE_ID:
        contract_failures.append("bundle_id")
    if payload.get("stable_path") is not True:
        contract_failures.append("stable_path")
    if payload.get("signature_valid") is not True:
        contract_failures.append("signature")
    if not str(payload.get("designated_requirement", "")).strip():
        contract_failures.append("designated_requirement")
    if not re.fullmatch(r"[0-9a-fA-F]{40,128}", str(payload.get("cdhash", ""))):
        contract_failures.append("cdhash")
    if payload.get("ok") is not True:
        contract_failures.append("host_status")
    payload["contract_failures"] = list(dict.fromkeys(contract_failures))
    payload["ok"] = not contract_failures
    return payload


def _registered_claude_helpers(env: Mapping[str, str], runner: Runner) -> list[dict[str, str]]:
    if dump_file := env.get("LIMEN_TCC_LSREGISTER_DUMP"):
        try:
            dump = Path(dump_file).read_text(encoding="utf-8")
        except OSError as exc:
            raise AuditError("LaunchServices fixture is unreadable") from exc
    else:
        executable = Path(
            "/System/Library/Frameworks/CoreServices.framework/Versions/A/"
            "Frameworks/LaunchServices.framework/Support/lsregister"
        )
        if not executable.exists():
            return []
        try:
            completed = runner(
                [str(executable), "-dump"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise AuditError("LaunchServices registration probe failed") from exc
        if completed.returncode != 0:
            raise AuditError("LaunchServices registration probe failed")
        dump = completed.stdout

    home = _home(env)
    roots = (
        home / ".local/share/claude",
        home / ".Trash",
    )
    paths: set[Path] = set()
    for line in dump.splitlines():
        if "ClaudeCode.app" not in line:
            continue
        match = re.search(r"(/[^\n]*?ClaudeCode\.app)(?:\s|$)", line)
        if match:
            paths.add(Path(match.group(1)))
    malformed: list[dict[str, str]] = []
    for path in sorted(paths):
        resolved = path.resolve(strict=False)
        if not any(resolved.is_relative_to(root.resolve(strict=False)) for root in roots):
            continue
        try:
            completed = runner(
                ["codesign", "--verify", "--strict", str(path)],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise AuditError("Claude helper signature probe failed") from exc
        detail = (completed.stderr or completed.stdout or "").strip()
        if completed.returncode != 0:
            malformed.append({"path": str(path), "detail": detail[:200]})
    return malformed


def audit(
    env: Mapping[str, str] | None = None,
    *,
    platform_name: str | None = None,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    values = dict(os.environ if env is None else env)
    observed_platform = platform_name or platform.system()
    if observed_platform != "Darwin" and "LIMEN_TCC_DB" not in values:
        return {
            "schema": SCHEMA,
            "ok": True,
            "status": "not_applicable",
            "platform": observed_platform,
            "platform_supported": False,
            "failures": [],
            "automatic_updates": {"enabled": True, "blockers": []},
            "stable_host": {"ok": True, "not_applicable": True},
            "clients": [],
            "summary": {
                "stable_host": 0,
                "legacy_stale": 0,
                "versioned_leak": 0,
                "unrelated": 0,
            },
            "malformed_claude_helpers": [],
        }

    failures: list[str] = []
    application_error: str | None = None
    try:
        application = _stable_application(values)
    except AuditError as exc:
        application = _default_stable_application(values)
        application_error = str(exc)
    deployment_epoch = _deployment_epoch(values, application)
    if application_error:
        host = {"ok": False, "error": application_error}
    else:
        try:
            host = _host_status(values, runner)
        except AuditError as exc:
            host = {"ok": False, "error": str(exc)}
    if not host.get("ok"):
        failures.append("stable_host_invalid")

    update_blockers = _disabled_updates(values)
    if update_blockers:
        failures.append("automatic_updates_disabled")

    try:
        clients, unrelated = _read_clients(
            _tcc_database(values),
            deployment_epoch=deployment_epoch,
            application=application,
            env=values,
        )
    except AuditError as exc:
        clients = []
        unrelated = 0
        failures.append("tcc_database_unavailable")
        database_error = str(exc)
    else:
        database_error = None
    counts = {
        classification: sum(1 for item in clients if item["classification"] == classification)
        for classification in ("stable_host", "legacy_stale", "versioned_leak")
    }
    counts["unrelated"] = unrelated
    if counts["versioned_leak"]:
        failures.append("versioned_tcc_client_after_host_deployment")

    try:
        malformed = _registered_claude_helpers(values, runner)
    except AuditError as exc:
        malformed = [{"path": "", "detail": str(exc)}]
        failures.append("claude_helper_registration_unreadable")
    if malformed and "claude_helper_registration_unreadable" not in failures:
        failures.append("malformed_claude_helper_registration")

    failures = list(dict.fromkeys(failures))
    return {
        "schema": SCHEMA,
        "ok": not failures,
        "status": "ok" if not failures else "blocked",
        "platform": observed_platform,
        "platform_supported": True,
        "host_deployed_at": deployment_epoch,
        "automatic_updates": {
            "enabled": not update_blockers,
            "blockers": update_blockers,
        },
        "stable_host": host,
        "clients": clients,
        "summary": counts,
        "malformed_claude_helpers": malformed,
        "tcc_database_error": database_error,
        "failures": failures,
    }


def print_human(payload: Mapping[str, Any]) -> None:
    print(f"TCC identity audit: {payload['status']}")
    print("  automatic updates: " + ("enabled" if payload["automatic_updates"]["enabled"] else "DISABLED"))
    host = payload["stable_host"]
    print("  stable host: " + ("valid" if host.get("ok") else "INVALID"))
    summary = payload["summary"]
    print(
        "  identities: "
        f"{summary['stable_host']} stable host, "
        f"{summary['legacy_stale']} legacy stale, "
        f"{summary['versioned_leak']} versioned leak"
    )
    for item in payload.get("clients", []):
        print(f"  [{item['classification']}] {item['client']} ({len(item['services'])} service(s))")
    if payload.get("malformed_claude_helpers"):
        print(f"  malformed Claude helpers: {len(payload['malformed_claude_helpers'])}")
    for failure in payload.get("failures", []):
        print(f"  failure: {failure}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--db")
    args = parser.parse_args(argv)
    env = dict(os.environ)
    if args.db:
        env["LIMEN_TCC_DB"] = args.db
    payload = audit(env)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_human(payload)
    return 1 if args.strict and not payload["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
