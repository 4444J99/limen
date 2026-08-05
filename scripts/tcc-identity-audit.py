#!/usr/bin/env python3
"""Audit macOS TCC clients against the stable Domus responsibility identity."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import sqlite3
import subprocess
import tomllib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any


SCHEMA = "limen.tcc_identity_audit.v2"
BASELINE_SCHEMA = "limen.tcc_identity_baseline.v1"
HOST_SCHEMA = "domus.agent_host_status.v1"
HOST_BUNDLE_ID = "org.organvm.domus.agent-host"
APP_MANAGEMENT_SERVICE = "kTCCServiceSystemPolicyAppBundles"
# Failures that mean "the instrument could not read", never "the system is wrong".
# A run whose failures are all in this set is UNMEASURED: not green, but not a finding.
MEASUREMENT_BLIND_FAILURES = frozenset(
    {
        "tcc_database_unavailable",
        "claude_helper_registration_unreadable",
    }
)
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
CONFIGURED_INGRESSES: tuple[tuple[str, str, str, frozenset[str]], ...] = (
    (
        "claude_desktop",
        "json",
        "Library/Application Support/Claude/claude_desktop_config.json",
        frozenset({"github", "serena", "filesystem", "sequential-thinking", "memory"}),
    ),
    (
        "claude_code",
        "json",
        ".claude.json",
        frozenset({"conductor", "voice-scorer", "github"}),
    ),
    (
        "codex_desktop",
        "toml",
        ".local/share/codex/config.toml",
        frozenset({"conductor", "voice-scorer"}),
    ),
    (
        "cline",
        "json",
        (
            "Library/Application Support/Code/User/globalStorage/"
            "saoudrizwan.claude-dev/settings/cline_mcp_settings.json"
        ),
        frozenset({"github", "jupyter", "serena"}),
    ),
)

Runner = Callable[..., subprocess.CompletedProcess[str]]


class AuditError(RuntimeError):
    """The read-only audit could not establish its predicate."""


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in TRUE_VALUES


def _home(env: Mapping[str, str]) -> Path:
    return Path(env.get("HOME", str(Path.home()))).expanduser()


def _tcc_databases(env: Mapping[str, str]) -> tuple[Path, ...]:
    override = env.get("LIMEN_TCC_DB")
    if override:
        return (Path(override).expanduser(),)
    return (
        _home(env) / "Library/Application Support/com.apple.TCC/TCC.db",
        Path("/Library/Application Support/com.apple.TCC/TCC.db"),
    )


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


def _deployment_identity_receipt(application: Path) -> Path:
    name = application.name.removesuffix(".app")
    return application.parent / f".{name}.designated-requirement"


def _limen_runtime_roots(env: Mapping[str, str]) -> tuple[Path, ...]:
    home = _home(env)
    live_root = _expand_user_path(
        env.get("LIMEN_ROOT", str(home / "Workspace/limen")),
        env,
    )
    workdir = _expand_user_path(
        env.get("LIMEN_WORKDIR", str(home / "Workspace")),
        env,
    )
    roots = [
        live_root,
        live_root / ".worktrees",
        workdir / ".limen-worktrees",
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


def _identity_id(client: str, client_type: int) -> str:
    material = f"limen.tcc.identity.v1\0{client_type}\0{client}".encode()
    return "sha256:" + hashlib.sha256(material).hexdigest()


def classify_client(
    client: str,
    *,
    client_type: int,
    baseline_identities: frozenset[str] | None,
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
    if baseline_identities is None:
        return "managed_unbaselined", pattern, exists
    classification = (
        "baseline_managed"
        if _identity_id(client, client_type) in baseline_identities
        else "new_managed"
    )
    return classification, pattern, exists


def _read_clients(
    databases: Sequence[Path],
    *,
    baseline_identities: frozenset[str] | None,
    application: Path,
    env: Mapping[str, str],
) -> tuple[list[dict[str, Any]], int]:
    rows: list[tuple[Any, ...]] = []
    for database in databases:
        try:
            connection = sqlite3.connect(
                f"{database.resolve().as_uri()}?mode=ro",
                uri=True,
            )
        except (OSError, sqlite3.Error) as exc:
            raise AuditError(f"TCC database is unavailable: {database}") from exc
        try:
            rows.extend(
                connection.execute(
                    "SELECT client, client_type, service, auth_value, last_modified "
                    "FROM access ORDER BY client, service"
                ).fetchall()
            )
        except sqlite3.Error as exc:
            raise AuditError(f"TCC access schema is unreadable: {database}") from exc
        finally:
            connection.close()

    grouped: dict[tuple[str, int], dict[str, Any]] = {}
    unrelated = 0
    for client_raw, client_type_raw, service_raw, auth_raw, modified_raw in rows:
        client = str(client_raw)
        client_type = int(client_type_raw)
        service = str(service_raw)
        authorization = int(auth_raw)
        modified = int(modified_raw)
        key = (client, client_type)
        item = grouped.setdefault(
            key,
            {
                "client": client,
                "client_type": client_type,
                "last_modified": modified,
                "decisions": {},
            },
        )
        item["last_modified"] = max(int(item["last_modified"]), modified)
        previous = item["decisions"].get(service)
        if previous is None or modified >= int(previous["last_modified"]):
            item["decisions"][service] = {
                "service": service,
                "auth_value": authorization,
                "last_modified": modified,
            }

    inventory: list[dict[str, Any]] = []
    for item in grouped.values():
        classification, pattern, exists = classify_client(
            str(item["client"]),
            client_type=int(item["client_type"]),
            baseline_identities=baseline_identities,
            application=application,
            env=env,
        )
        if classification == "unrelated":
            unrelated += 1
        decisions = sorted(item["decisions"].values(), key=lambda value: value["service"])
        active_services = [
            decision["service"]
            for decision in decisions
            if int(decision["auth_value"]) != 0
        ]
        app_management_active = any(
            decision["service"] == APP_MANAGEMENT_SERVICE
            and int(decision["auth_value"]) != 0
            for decision in decisions
        )
        inventory.append(
            {
                "client": item["client"],
                "client_type": item["client_type"],
                "identity": _identity_id(str(item["client"]), int(item["client_type"])),
                "client_kind": (
                    "path"
                    if int(item["client_type"]) == 1 or str(item["client"]).startswith("/")
                    else "bundle"
                ),
                "last_modified": item["last_modified"],
                "classification": classification,
                "pattern": pattern,
                "exists": exists,
                "active": bool(active_services),
                "app_management_active": app_management_active,
                "active_services": active_services,
                "services": [decision["service"] for decision in decisions],
                "decisions": decisions,
            }
        )
    inventory.sort(key=lambda value: (value["classification"], value["client"]))
    return inventory, unrelated


def _identity_baseline_path(env: Mapping[str, str]) -> Path:
    configured = env.get("LIMEN_TCC_IDENTITY_BASELINE")
    if configured:
        return _expand_user_path(configured, env)
    return _home(env) / ".config/limen/tcc-identity-baseline.json"


def _app_management_decision(item: Mapping[str, Any]) -> Mapping[str, Any] | None:
    return next(
        (
            decision
            for decision in item.get("decisions", [])
            if decision.get("service") == APP_MANAGEMENT_SERVICE
        ),
        None,
    )


def _app_management_bundle_grants(
    clients: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    grants: list[dict[str, Any]] = []
    for item in clients:
        if int(item["client_type"]) != 0 or item["client"] == HOST_BUNDLE_ID:
            continue
        decision = _app_management_decision(item)
        if decision is None:
            continue
        grants.append(
            {
                "client": str(item["client"]),
                "auth_value": int(decision["auth_value"]),
            }
        )
    return sorted(grants, key=lambda value: value["client"])


def _baseline_digest(document: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _identity_baseline_document(
    clients: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    body = {
        "schema": BASELINE_SCHEMA,
        "managed_identities": sorted(
            {
                str(item["identity"])
                for item in clients
                if item.get("pattern") is not None
            }
        ),
        "app_management_bundle_grants": _app_management_bundle_grants(clients),
    }
    return {**body, "digest": _baseline_digest(body)}


def _load_identity_baseline(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AuditError("identity baseline is missing") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditError("identity baseline is unreadable") from exc
    if not isinstance(document, dict) or document.get("schema") != BASELINE_SCHEMA:
        raise AuditError("identity baseline schema is incompatible")
    identities = document.get("managed_identities")
    grants = document.get("app_management_bundle_grants")
    if not isinstance(identities, list) or not all(
        isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value)
        for value in identities
    ):
        raise AuditError("identity baseline managed identities are malformed")
    if not isinstance(grants, list) or not all(
        isinstance(value, dict)
        and isinstance(value.get("client"), str)
        and not str(value["client"]).startswith("/")
        and isinstance(value.get("auth_value"), int)
        for value in grants
    ):
        raise AuditError("identity baseline App Management grants are malformed")
    body = {
        "schema": BASELINE_SCHEMA,
        "managed_identities": sorted(set(identities)),
        "app_management_bundle_grants": sorted(grants, key=lambda value: value["client"]),
    }
    digest = _baseline_digest(body)
    if document.get("digest") != digest:
        raise AuditError("identity baseline digest does not match its contents")
    return {**body, "digest": digest}


def _write_identity_baseline(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(document, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise AuditError(
                "identity baseline already exists; refusing to overwrite the cutover anchor"
            ) from exc
        path.chmod(0o600)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _apply_baseline_classification(
    clients: Sequence[dict[str, Any]],
    identities: frozenset[str],
) -> None:
    for item in clients:
        if item.get("pattern") is None:
            continue
        item["classification"] = (
            "baseline_managed"
            if item["identity"] in identities
            else "new_managed"
        )


def _redacted_item(item: Mapping[str, Any]) -> dict[str, Any]:
    public = dict(item)
    if item.get("client_kind") == "path":
        public["client"] = f"<redacted:{str(item['identity']).removeprefix('sha256:')[:12]}>"
    return public


def _redacted_predicate_identity(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "identity": item["identity"],
        "classification": item["classification"],
        "pattern": item.get("pattern"),
        "active": item["active"],
        "active_services": item["active_services"],
        "decisions": item["decisions"],
    }


def _configured_ingress_violations(
    env: Mapping[str, str],
) -> tuple[list[dict[str, str]], int]:
    violations: list[dict[str, str]] = []
    configured = 0
    home = _home(env)
    expected_host = (home / ".local/bin/domus-agent-host").resolve(strict=False)
    for surface, format_name, relative, managed_names in CONFIGURED_INGRESSES:
        path = home / relative
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            continue
        except OSError:
            violations.append(
                {
                    "surface": surface,
                    "server": "<config>",
                    "command": "",
                    "reason": "config_unreadable",
                }
            )
            continue
        try:
            if format_name == "toml":
                document = tomllib.loads(raw.decode())
                servers = document.get("mcp_servers", {})
            else:
                document = json.loads(raw)
                servers = document.get("mcpServers", {})
        except (UnicodeDecodeError, json.JSONDecodeError, tomllib.TOMLDecodeError):
            violations.append(
                {
                    "surface": surface,
                    "server": "<config>",
                    "command": "",
                    "reason": "config_unreadable",
                }
            )
            continue
        if not isinstance(servers, dict):
            violations.append(
                {
                    "surface": surface,
                    "server": "<config>",
                    "command": "",
                    "reason": "server_registry_malformed",
                }
            )
            continue
        for name in sorted(managed_names):
            server = servers.get(name)
            if not isinstance(server, dict) or "command" not in server:
                continue
            configured += 1
            command = server.get("command")
            arguments = server.get("args", [])
            command_name = ""
            command_path: Path | None = None
            if isinstance(command, str) and command.strip():
                command_value = command.strip()
                command_name = Path(command_value).name
                command_path = _expand_user_path(command_value, env).resolve(
                    strict=False
                )
            hosted = (
                command_name == "domus-agent-host"
                and command_path == expected_host
                and isinstance(arguments, list)
                and arguments[:2] == ["ensure", "--"]
                and len(arguments) >= 3
            )
            if not hosted:
                violations.append(
                    {
                        "surface": surface,
                        "server": name,
                        "command": command_name,
                        "reason": "missing_domus_agent_host_ensure",
                    }
                )
    return violations, configured


def _settings_paths(env: Mapping[str, str]) -> list[Path]:
    home = _home(env)
    limen_root = _expand_user_path(
        env.get("LIMEN_ROOT", str(home / "Workspace/limen")),
        env,
    )
    candidates = [
        home / ".claude/settings.json",
        limen_root / ".agent-runtime/claude/settings.json",
    ]
    if config := env.get("CLAUDE_CONFIG_DIR"):
        candidates.append(_expand_user_path(config, env) / "settings.json")
    seen: set[Path] = set()
    result: list[Path] = []
    for path in candidates:
        resolved = path.resolve(strict=False)
        if resolved not in seen:
            seen.add(resolved)
            result.append(path)
    return result


def _config_paths(env: Mapping[str, str]) -> list[Path]:
    """The `.claude.json` files that carry the real `autoUpdates` switch.

    Sibling of `_settings_paths`: same three roots, but the config document sits
    *beside* `~/.claude/` rather than inside it, and beside `settings.json` under an
    explicit `CLAUDE_CONFIG_DIR`. Both are live on this host simultaneously — a session
    under `CLAUDE_CONFIG_DIR` reads the runtime copy and never sees the home one, so
    flipping only `~/.claude.json` leaves updates off where it counts.
    """
    home = _home(env)
    limen_root = _expand_user_path(
        env.get("LIMEN_ROOT", str(home / "Workspace/limen")),
        env,
    )
    candidates = [
        home / ".claude.json",
        limen_root / ".agent-runtime/claude/.claude.json",
    ]
    if config := env.get("CLAUDE_CONFIG_DIR"):
        candidates.append(_expand_user_path(config, env) / ".claude.json")
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
    # The switch the vendor actually honours. Scanning only for *disable* env keys and
    # `env` blocks reported "automatic updates: enabled" on 2026-08-05 while `autoUpdates`
    # was literally false in BOTH config roots — which is how inventory_green()'s
    # `automatic_updates_disabled` guard passed vacuously and discharged
    # L-DOMUS-AGENT-HOST-TCC against a version that could never advance.
    # Absent means enabled (vendor default); only an explicit false is a blocker.
    for path in _config_paths(env):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, json.JSONDecodeError):
            blockers.append({"key": "config_unreadable", "source": str(path)})
            continue
        if not isinstance(document, dict):
            continue
        if document.get("autoUpdates") is False:
            blockers.append({"key": "autoUpdates_false", "source": str(path)})
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


def _host_status(
    env: Mapping[str, str],
    runner: Runner,
    *,
    strict: bool,
) -> dict[str, Any]:
    if fixture := env.get("LIMEN_TCC_HOST_STATUS_JSON"):
        if strict:
            raise AuditError("strict audit rejects fixture-backed stable-host status")
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
    if strict:
        receipt = _deployment_identity_receipt(_stable_application(env))
        payload["deployment_identity_receipt"] = str(receipt)
        try:
            receipt_lines = receipt.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            receipt_lines = []
            payload["deployment_identity_error"] = str(exc)
        if (
            len(receipt_lines) != 1
            or not receipt_lines[0].strip()
            or receipt_lines[0].strip() != str(payload.get("designated_requirement", "")).strip()
        ):
            contract_failures.append("deployment_identity")
            payload["deployment_identity_matches"] = False
        else:
            payload["deployment_identity_matches"] = True
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


def _registered_claude_helpers(
    env: Mapping[str, str],
    runner: Runner,
    *,
    strict: bool,
) -> list[dict[str, str]]:
    if dump_file := env.get("LIMEN_TCC_LSREGISTER_DUMP"):
        if strict:
            raise AuditError("strict audit rejects fixture-backed LaunchServices inventory")
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
    strict: bool = False,
    write_baseline: Path | None = None,
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
            # Key always present so consumers can read payload["measured"] unconditionally.
            "measured": {"tcc_database": False, "not_applicable": True, "blind_failures": []},
            "failures": [],
            "automatic_updates": {"enabled": True, "blockers": []},
            "stable_host": {"ok": True, "not_applicable": True},
            "clients": [],
            "summary": {
                "stable_host": 0,
                "baseline_managed": 0,
                "managed_unbaselined": 0,
                "new_managed": 0,
                "active_leaks": 0,
                "visible_app_management_path_rows": 0,
                "unhosted_configured_ingresses": 0,
                "rotating_identity_active_grants": 0,
                "unrelated": 0,
            },
            "predicates": {
                "active_leaks": {"ok": True, "measured": False, "count": 0, "identities": []},
                "visible_app_management_path_rows": {
                    "ok": True,
                    "measured": False,
                    "count": 0,
                    "identities": [],
                    "stable_host_row_count": 0,
                    "stable_host_grant_count": 0,
                },
                "unhosted_configured_ingresses": {
                    "ok": True,
                    "measured": False,
                    "count": 0,
                    "configured_count": 0,
                    "ingresses": [],
                },
                "rotating_identity_active_grants": {
                    "ok": True,
                    "measured": False,
                    "count": 0,
                    "identities": [],
                    "services": [],
                },
            },
            "identity_baseline": {"loaded": False, "not_applicable": True},
            "malformed_claude_helpers": [],
        }

    failures: list[str] = []
    application_error: str | None = None
    try:
        application = _stable_application(values)
    except AuditError as exc:
        application = _default_stable_application(values)
        application_error = str(exc)
    if application_error:
        host = {"ok": False, "error": application_error}
    else:
        try:
            host = _host_status(values, runner, strict=strict)
        except AuditError as exc:
            host = {"ok": False, "error": str(exc)}
    if not host.get("ok"):
        failures.append("stable_host_invalid")

    update_blockers = _disabled_updates(values)
    if update_blockers:
        failures.append("automatic_updates_disabled")

    baseline_path = write_baseline or _identity_baseline_path(values)
    baseline: dict[str, Any] | None = None
    baseline_error: str | None = None
    baseline_written = False
    if write_baseline is None:
        try:
            baseline = _load_identity_baseline(baseline_path)
        except AuditError as exc:
            baseline_error = str(exc)
    baseline_identities = (
        frozenset(baseline["managed_identities"])
        if baseline is not None
        else None
    )
    try:
        clients, unrelated = _read_clients(
            _tcc_databases(values),
            baseline_identities=baseline_identities,
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

    if write_baseline is not None and database_error is None:
        baseline = _identity_baseline_document(clients)
        try:
            _write_identity_baseline(write_baseline, baseline)
        except (AuditError, OSError) as exc:
            baseline_error = f"identity baseline write failed: {exc}"
            failures.append("identity_baseline_write_failed")
            baseline = None
        else:
            baseline_written = True
            baseline_error = None
            baseline_identities = frozenset(baseline["managed_identities"])
            _apply_baseline_classification(clients, baseline_identities)
            clients.sort(key=lambda value: (value["classification"], value["client"]))

    if baseline is None:
        if baseline_error == "identity baseline is missing":
            failures.append("identity_baseline_missing")
        elif baseline_error:
            failures.append("identity_baseline_invalid")

    active_leaks = [
        item
        for item in clients
        if item.get("pattern") is not None
        and (
            item["app_management_active"]
            or item["classification"] == "new_managed"
        )
    ]
    visible_path_rows = [
        item
        for item in clients
        if item["client_kind"] == "path"
        and _app_management_decision(item) is not None
    ]
    stable_host_rows = [
        item
        for item in clients
        if item["client"] == HOST_BUNDLE_ID
        and _app_management_decision(item) is not None
    ]
    stable_host_grants = [
        item
        for item in stable_host_rows
        if int(_app_management_decision(item)["auth_value"]) != 0  # type: ignore[index]
    ]
    # THE SPRAWL ITSELF, measured directly.
    #
    # Every predicate below `active_leaks` judges exactly one service —
    # APP_MANAGEMENT_SERVICE. The dialog the operator actually gets is
    # `"<version>" would like to access files in your Documents folder`, i.e.
    # kTCCServiceSystemPolicyDocumentsFolder against a path-keyed client under
    # ~/.local/share/claude/versions/<version>/. The audit already READS those rows
    # (they land in `services`/`active_services`) and already knows the path shape
    # (MANAGED_CLIENT_PATTERNS "claude_version") — it simply never judged them. So the
    # whole Track C inventory could report green while every vendor update minted a new
    # identity and re-prompted, because nothing counted the thing that was sprawling.
    #
    # A path-keyed client matching a rotating pattern and holding ANY live grant is one
    # future re-prompt, whatever the service. The ideal is zero: grants belong to the
    # stable bundle identity, which survives version rotation.
    rotating_grants = [
        item
        for item in clients
        if item.get("pattern") is not None
        and item["client_kind"] == "path"
        and item["active_services"]
    ]
    ingress_violations, configured_ingresses = _configured_ingress_violations(values)

    # Every database-derived predicate below reads an EMPTY `clients` when the TCC
    # database could not be read, and emptiness then reads as evidence: `active_leaks`
    # would report ok/0 (asserting zero leaks having observed nothing) while the grant
    # checks would name a missing grant and a changed bundle map (defects nobody looked
    # for). Unmeasured is a third verdict, never a green and never a named red.
    # See docs/IDEAL-FORMS-LEDGER.md → IF-AGENT-IDENTITY.
    db_measured = database_error is None

    predicates = {
        "active_leaks": {
            "ok": db_measured and not active_leaks,
            "measured": db_measured,
            "count": len(active_leaks),
            "identities": [_redacted_predicate_identity(item) for item in active_leaks],
        },
        "visible_app_management_path_rows": {
            "ok": (
                db_measured
                and not visible_path_rows
                and len(stable_host_rows) == 1
                and len(stable_host_grants) == 1
            ),
            "measured": db_measured,
            "count": len(visible_path_rows),
            "identities": [
                _redacted_predicate_identity(item) for item in visible_path_rows
            ],
            "stable_host_row_count": len(stable_host_rows),
            "stable_host_grant_count": len(stable_host_grants),
        },
        "unhosted_configured_ingresses": {
            # Config-derived, not database-derived: measurable even when TCC is blind.
            "ok": not ingress_violations,
            "measured": True,
            "count": len(ingress_violations),
            "configured_count": configured_ingresses,
            "ingresses": ingress_violations,
        },
        "rotating_identity_active_grants": {
            "ok": db_measured and not rotating_grants,
            "measured": db_measured,
            "count": len(rotating_grants),
            "identities": [
                _redacted_predicate_identity(item) for item in rotating_grants
            ],
            # Every distinct TCC service still pinned to a rotating path — the exact
            # set of dialogs the operator will be shown again on the next update.
            "services": sorted(
                {
                    service
                    for item in rotating_grants
                    for service in item["active_services"]
                }
            ),
        },
    }

    counts = {
        classification: sum(
            1 for item in clients if item["classification"] == classification
        )
        for classification in (
            "stable_host",
            "baseline_managed",
            "managed_unbaselined",
            "new_managed",
        )
    }
    counts.update(
        {
            "active_leaks": len(active_leaks),
            "visible_app_management_path_rows": len(visible_path_rows),
            "unhosted_configured_ingresses": len(ingress_violations),
            "rotating_identity_active_grants": len(rotating_grants),
            "unrelated": unrelated,
        }
    )
    if db_measured and rotating_grants:
        failures.append("rotating_identity_active_grants")
    if active_leaks:
        failures.append("active_managed_tcc_leak")
    if visible_path_rows:
        failures.append("visible_app_management_path_client")
    # Guarded on db_measured: with no database read, stable_host_rows is empty for want
    # of looking, and naming `..._grant_missing` would report a defect never observed.
    # `tcc_database_unavailable` is already the honest failure in that case.
    if db_measured and (len(stable_host_rows) != 1 or len(stable_host_grants) != 1):
        failures.append("stable_host_app_management_grant_missing")
    if ingress_violations:
        failures.append("unhosted_configured_ingress")
    if strict and not counts["stable_host"] and db_measured:
        failures.append("stable_host_tcc_identity_missing")

    current_bundle_grants = _app_management_bundle_grants(clients)
    expected_bundle_grants = (
        baseline["app_management_bundle_grants"] if baseline is not None else None
    )
    preservation_ok = (
        db_measured
        and expected_bundle_grants is not None
        and current_bundle_grants == expected_bundle_grants
    )
    # Same guard: an empty grant map read from an unreadable database is not a change.
    if db_measured and expected_bundle_grants is not None and not preservation_ok:
        failures.append("unrelated_app_management_grants_changed")

    try:
        malformed = _registered_claude_helpers(values, runner, strict=strict)
    except AuditError as exc:
        malformed = [{"path": "", "detail": str(exc)}]
        failures.append("claude_helper_registration_unreadable")
    if malformed and "claude_helper_registration_unreadable" not in failures:
        failures.append("malformed_claude_helper_registration")

    failures = list(dict.fromkeys(failures))
    # Three verdicts, not two. `ok` stays False when blind (fail toward caution, so
    # --strict still exits 1 and nothing turns green on a failed read), but the STATUS
    # distinguishes "we looked and it is wrong" from "we could not look" — otherwise
    # indistinguishable in the output, which is how a blind run gets read as a finding.
    unmeasured = bool(failures) and set(failures) <= MEASUREMENT_BLIND_FAILURES
    return {
        "schema": SCHEMA,
        "ok": not failures,
        "status": "ok" if not failures else ("unmeasured" if unmeasured else "blocked"),
        "measured": {
            "tcc_database": db_measured,
            "blind_failures": sorted(set(failures) & MEASUREMENT_BLIND_FAILURES),
        },
        "platform": observed_platform,
        "platform_supported": True,
        "automatic_updates": {
            "enabled": not update_blockers,
            "blockers": update_blockers,
        },
        "stable_host": host,
        "clients": [_redacted_item(item) for item in clients],
        "summary": counts,
        "predicates": predicates,
        "identity_baseline": {
            "schema": BASELINE_SCHEMA,
            "loaded": baseline is not None,
            "written": baseline_written,
            "digest": baseline.get("digest") if baseline is not None else None,
            "managed_identity_count": (
                len(baseline["managed_identities"]) if baseline is not None else 0
            ),
            "app_management_bundle_grant_count": (
                len(baseline["app_management_bundle_grants"])
                if baseline is not None
                else 0
            ),
            "error": baseline_error,
        },
        "unrelated_app_management_preservation": {
            "ok": preservation_ok,
            "current_count": len(current_bundle_grants),
            "baseline_count": (
                len(expected_bundle_grants)
                if expected_bundle_grants is not None
                else 0
            ),
        },
        "malformed_claude_helpers": malformed,
        "tcc_database_error": database_error,
        "failures": failures,
    }


def print_human(payload: Mapping[str, Any]) -> None:
    print(f"TCC identity audit: {payload['status']}")
    if payload.get("status") == "unmeasured":
        blind = ", ".join(payload.get("measured", {}).get("blind_failures") or []) or "unknown"
        print(f"  UNMEASURED — the instrument could not read ({blind}).")
        print("  This is NOT a finding: no grant state was observed. Re-run beneath the")
        print("  stable host, which holds the Full Disk Access this read requires.")
    print("  automatic updates: " + ("enabled" if payload["automatic_updates"]["enabled"] else "DISABLED"))
    host = payload["stable_host"]
    print("  stable host: " + ("valid" if host.get("ok") else "INVALID"))
    summary = payload["summary"]
    print(
        "  identities: "
        f"{summary['stable_host']} stable host, "
        f"{summary['baseline_managed']} baseline managed, "
        f"{summary['new_managed']} new managed"
    )
    predicates = payload["predicates"]
    print(f"  active leaks: {predicates['active_leaks']['count']}")
    rotating = predicates.get("rotating_identity_active_grants")
    if rotating is not None:
        line = f"  rotating-identity grants: {rotating['count']}"
        if rotating["services"]:
            line += " across " + ", ".join(rotating["services"])
        print(line + ("" if rotating["measured"] else "  (unmeasured)"))
    visible = predicates["visible_app_management_path_rows"]
    print(
        "  App Management: "
        f"{visible['count']} path row(s), "
        f"{visible['stable_host_grant_count']} stable host grant(s)"
    )
    print(
        "  unhosted configured ingresses: "
        f"{predicates['unhosted_configured_ingresses']['count']}"
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
    parser.add_argument("--baseline")
    parser.add_argument("--write-baseline")
    args = parser.parse_args(argv)
    env = dict(os.environ)
    if args.db:
        env["LIMEN_TCC_DB"] = args.db
    if args.baseline:
        env["LIMEN_TCC_IDENTITY_BASELINE"] = args.baseline
    write_baseline = Path(args.write_baseline).expanduser() if args.write_baseline else None
    if write_baseline is not None and args.baseline:
        if write_baseline.resolve(strict=False) != Path(args.baseline).expanduser().resolve(
            strict=False
        ):
            parser.error("--baseline and --write-baseline must name the same path")
    payload = audit(
        env,
        strict=args.strict,
        write_baseline=write_baseline,
    )
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_human(payload)
    return 1 if args.strict and not payload["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
