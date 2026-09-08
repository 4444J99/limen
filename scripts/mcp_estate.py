"""Desired/observed MCP estate reconciliation; unavailable coverage never becomes green.

Domus owns intent. This module reads configs but never edits them. Raw launch specifications
remain process-local: reports expose only stable identities and content fingerprints.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
from pathlib import Path
import subprocess
import sys
import time
import tomllib

from agent_config_paths import MCP_VENDOR_KEYS, active_config_path, candidate_config_paths
from mcp_protocol import verify

DIMENSIONS = (
    "configuration",
    "ownership",
    "transport",
    "protocol",
    "authentication",
    "capabilities",
    "functional",
    "startup_ui",
    "explicit_ui",
    "isolation",
    "cleanup",
    "client_route",
)
DISTANCES = (
    "missing_capabilities",
    "ownership_conflicts",
    "unintended_launches",
    "protocol_failures",
    "authentication_gaps",
    "unmeasured_integrations",
    "abandoned_processes",
)


def fingerprint(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate configuration field")
        result[key] = value
    return result


def read_config(path):
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("configuration ceiling")
    raw = path.read_bytes()
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError("configuration ceiling")
    if path.suffix == ".toml":
        data = tomllib.loads(raw.decode())
    else:
        if path.suffix == ".jsonc":
            spec = importlib.util.spec_from_file_location(
                "estate_jsonc", Path(__file__).with_name("mcp-server-boot.py")
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            raw_json = module._strip_jsonc(raw.decode())
            data = json.loads(raw_json, object_pairs_hook=unique_fields)
        else:
            data = json.loads(raw, object_pairs_hook=unique_fields)
    if not isinstance(data, dict):
        raise ValueError("configuration must be a mapping")
    return data, fingerprint(raw)


def server_map(data):
    for key in ("mcpServers", "mcp_servers", "servers", "mcp", "upstreams"):
        if isinstance(data.get(key), dict):
            return data[key]
    return {}


def policy_path():
    # The deployed copy is the default; an explicit source override supports isolated validation.
    return Path(os.environ.get("LIMEN_MCP_POLICY", Path.home() / ".config/domus/mcp-policy.json"))


def load_policy(path):
    data, digest = read_config(path)
    policy = data.get("config_ownership", {}).get("mcp_policy", data)
    if (
        policy.get("schema_version") != 1
        or not isinstance(policy.get("services"), dict)
        or not isinstance(policy.get("registrations"), list)
    ):
        raise ValueError("invalid MCP policy")
    seen = set()
    for registration in policy["registrations"]:
        key = (registration["client"], registration["name"], registration.get("route", "standalone"))
        if key in seen:
            raise ValueError("duplicate registration policy")
        seen.add(key)
        if registration["service"] not in policy["services"]:
            raise ValueError("unknown service policy")
    return policy, digest


def normalize(spec, client=None):
    if not isinstance(spec, dict):
        return {**normalize({}), "invalid": True}
    if client == "opencode" and "environment" in spec:
        if "env" in spec and spec["env"] != spec["environment"]:
            return {**normalize({}), "invalid": True}
        spec = {**spec, "env": spec["environment"]}
    command = spec.get("command")
    url = spec.get("url") or spec.get("serverUrl") or spec.get("httpUrl")
    args = spec.get("args", [])
    invalid = not isinstance(args, list) or any(not isinstance(arg, str) for arg in args)
    if isinstance(command, list):
        invalid = invalid or not command or any(not isinstance(arg, str) for arg in command)
        if not invalid:
            command, args = command[0], command[1:] + args
    invalid = (
        invalid
        or (command is not None and not isinstance(command, str))
        or (url is not None and not isinstance(url, str))
        or (command is not None and url is not None)
        or any(key in spec and type(spec[key]) is not bool for key in ("enabled", "disabled"))
        or any(spec.get(key) is not None and not isinstance(spec[key], str) for key in ("cwd", "bearer_token_env_var"))
    )
    for field in ("env", "headers", "http_headers", "env_http_headers"):
        value = spec.get(field, {})
        invalid = (
            invalid
            or not isinstance(value, dict)
            or any(not isinstance(k, str) or not isinstance(v, str) for k, v in value.items())
        )
    return {
        "command": command,
        "args": args,
        "url": url,
        "transport": "stdio" if command else ("http" if url else "unsupported"),
        "env": spec.get("env", {}),
        "cwd": spec.get("cwd"),
        "bearer_token_env_var": spec.get("bearer_token_env_var"),
        "headers": spec.get("headers", spec.get("http_headers", {})),
        "env_http_headers": spec.get("env_http_headers", {}),
        "disabled": spec.get("disabled") is True or spec.get("enabled") is False,
        "invalid": bool(invalid),
    }


def native_configuration_index(client, response):
    """Sanitize the effective native MCP map without treating absence as an empty catalog."""
    config = response.get("config") if client == "codex" else response
    field = "mcp_servers" if client == "codex" else "mcp"
    if not isinstance(config, dict) or field not in config or not isinstance(config[field], dict):
        return {"state": "unmeasured", "registrations": {}}
    rows = {}
    for name, declaration in config[field].items():
        spec = normalize(declaration, client)
        rows[name] = {
            "launch_fingerprint": fingerprint(spec),
            "disabled": spec["disabled"],
            "valid": not spec["invalid"] and spec["transport"] != "unsupported",
        }
    return {"state": "observed", "registrations": rows}


def installed_plugin_roots(path, plugin, project):
    """Select the installed registry entry; cached older versions are provenance only."""
    name = plugin.split("@", 1)[0]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise ValueError("invalid plugin identity")
    registry_path = path.parent / "plugins/installed_plugins.json"
    if not registry_path.exists():
        return sorted((path.parent / "plugins/cache").glob(f"*/{name}/*")), "cache_candidate"
    registry, _ = read_config(registry_path)
    entries = registry.get("plugins", {}).get(plugin, [])
    if not isinstance(entries, list):
        raise ValueError("invalid installed plugin entries")
    selected = []
    priority = {"user": 0, "project": 1, "local": 2}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("scope") not in priority:
            raise ValueError("unsupported plugin scope")
        if entry["scope"] != "user" and (
            project is None or Path(entry.get("projectPath", "")).resolve() != Path(project).resolve()
        ):
            continue
        root = Path(entry.get("installPath", ""))
        if not root.is_absolute() or not root.is_dir() or not entry.get("version"):
            raise ValueError("installed plugin unavailable")
        if root.name != str(entry["version"]):
            raise ValueError("installed plugin version mismatch")
        selected.append((priority[entry["scope"]], root))
    if not selected:
        return [], "installed_registry"
    rank = max(item[0] for item in selected)
    return list(dict.fromkeys(root for level, root in selected if level == rank)), "installed_registry"


def plugin_spec(spec, enabled):
    if not isinstance(spec, dict):
        return spec
    return {**spec, "enabled": enabled is True and spec.get("enabled", True) is not False}


def quiet_probe_allowed(record):
    spec, owner = record["spec"], record["policy"]
    if not spec or spec["invalid"] or not owner:
        return False
    if record["service"] == "serena":
        args = spec.get("args", [])
        return any(args[i : i + 2] == ["--open-web-dashboard", "false"] for i in range(len(args)))
    return spec["transport"] == "http" or owner.get("verification", {}).get("quiet_probe") is True


def plugin_provenance(path, plugin, selected):
    name = plugin.split("@", 1)[0]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        return []
    selected = {p.resolve() for p in selected}
    candidates = []
    for root in sorted((path.parent / "plugins/cache").glob(f"*/{name}/*")):
        if root.resolve() in selected:
            continue
        for relative in (".mcp.json", ".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
            manifest = root / relative
            if manifest.is_file():
                try:
                    _, value = read_config(manifest)
                    candidates.append({"source": "overridden-plugin-cache", "active": False, "fingerprint": value})
                except (ValueError, OSError):
                    candidates.append({"source": "overridden-plugin-cache", "active": False, "state": "unmeasured"})
    return candidates


def inventory(policy, config_paths=None, project=None, client_environments=None):
    # Native collectors pass each client's observed environment separately. Shell
    # inheritance is a candidate location, never evidence of another app's loader.
    client_environments = client_environments or {}
    paths = (
        config_paths
        if config_paths is not None
        else [(c, active_config_path(c, client_environments.get(c))) for c in MCP_VENDOR_KEYS]
    )
    if config_paths is None:
        home = Path.home()
        paths += [
            ("claude-desktop", home / "Library/Application Support/Claude/claude_desktop_config.json"),
            ("cursor", home / ".cursor/mcp.json"),
            ("vscode", home / "Library/Application Support/Code/User/mcp.json"),
            ("ianva", Path(os.environ.get("IANVA_REGISTRY", home / ".agents/mcp/servers.json"))),
            ("ianva", home / ".config/ianva/upstreams.json"),
        ]
    records, issues, stale, configs = {}, [], [], []

    def add(client, name, spec, source, digest, route="standalone", active=True):
        key = (client, name, route)
        entry = {
            "client": client,
            "name": name,
            "route": route,
            "source": source,
            "fingerprint": digest,
            "spec": normalize(spec, client),
            "active": active,
        }
        if key in records:
            issues.append({"client": client, "reason": "ambiguous_registration", "owner": "domus-genoma"})
            entry["provenance"] = records[key].get("provenance", []) + [
                {k: records[key][k] for k in ("source", "fingerprint", "active")}
            ]
        records[key] = entry

    for client, path in paths:
        try:
            data, digest = read_config(path)
        except FileNotFoundError:
            configs.append({"client": client, "state": "missing"})
            continue
        except (ValueError, OSError):
            configs.append({"client": client, "state": "unmeasured"})
            issues.append({"client": client, "reason": "configuration_unreadable", "owner": "domus-genoma"})
            continue
        configs.append({"client": client, "state": "valid", "fingerprint": digest})
        if any(
            key in data and not isinstance(data[key], dict)
            for key in ("mcpServers", "mcp_servers", "servers", "mcp", "upstreams")
        ):
            issues.append({"client": client, "reason": "registration_table_unmeasured", "owner": "domus-genoma"})
        table = server_map(data)
        if client == "ianva" and not table:
            table = {k: v for k, v in data.items() if isinstance(v, dict)}
        for name, spec in table.items():
            add(client, name, spec, "active-config", digest)
            if not isinstance(spec, dict):
                issues.append({"client": client, "reason": "invalid_registration", "owner": "domus-genoma"})
        plugins = data.get("plugins", {})
        plugin_path = path
        if client == "claude":
            settings_path = (
                active_config_path("claude-settings", client_environments.get(client))
                if config_paths is None
                else path.parent / "settings.json"
            )
            plugin_path = settings_path
            if settings_path.exists():
                try:
                    settings_data, settings_digest = read_config(settings_path)
                    enabled = settings_data.get("enabledPlugins", {})
                    if not isinstance(enabled, dict) or any(type(v) is not bool for v in enabled.values()):
                        raise ValueError("invalid enabled plugins")
                    plugins = {key: {"enabled": value} for key, value in enabled.items()}
                    digest = fingerprint([digest, settings_digest])
                except (ValueError, OSError):
                    issues.append({"client": client, "reason": "plugin_state_unmeasured", "owner": "domus-genoma"})
        if not isinstance(plugins, dict):
            issues.append({"client": client, "reason": "plugin_state_unmeasured", "owner": "domus-genoma"})
            plugins = {}
        for plugin, settings in plugins.items():
            if not isinstance(settings, dict):
                issues.append({"client": client, "reason": "plugin_state_unmeasured", "owner": "domus-genoma"})
                continue
            plugin_name = plugin.split("@", 1)[0]
            try:
                roots, selection = installed_plugin_roots(plugin_path, plugin, project)
            except (ValueError, OSError, TypeError, AttributeError):
                roots, selection = [], "installed_registry_unmeasured"
            overridden = plugin_provenance(plugin_path, plugin, roots)
            manifests = [r / ".mcp.json" for r in roots if (r / ".mcp.json").exists()]
            if len(roots) == 1 and not manifests:
                try:
                    metadata_paths = [roots[0] / kind / "plugin.json" for kind in (".codex-plugin", ".claude-plugin")]
                    metadata_path = next((p for p in metadata_paths if p.is_file()), metadata_paths[0])
                    metadata, _ = read_config(metadata_path)
                    if "mcpServers" not in metadata:
                        continue  # installed plugin explicitly has no MCP entry point
                    if isinstance(metadata["mcpServers"], dict):
                        for name, spec in metadata["mcpServers"].items():
                            add(
                                client,
                                name,
                                plugin_spec(spec, settings.get("enabled", True)),
                                "plugin-inline",
                                fingerprint([digest, metadata]),
                                plugin,
                            )
                            records[(client, name, plugin)]["plugin_selection"] = selection
                            records[(client, name, plugin)]["provenance"] = overridden
                        continue
                except (OSError, ValueError):
                    pass
            if len(manifests) != 1:
                # A missing/ambiguous cache does not prove the plugin supplies zero MCPs.
                add(
                    client,
                    plugin_name,
                    {"enabled": settings.get("enabled", True)},
                    "plugin-cache-unmeasured",
                    digest,
                    plugin,
                )
                issues.append({"client": client, "reason": "plugin_cache_unmeasured", "owner": "domus-genoma"})
                continue
            try:
                manifest, plugin_digest = read_config(manifests[0])
                plugin_table = server_map(manifest) or manifest
                for name, spec in plugin_table.items():
                    overrides = settings.get("mcp_servers", {})
                    if not isinstance(overrides, dict) or not isinstance(overrides.get(name, {}), dict):
                        raise ValueError("invalid plugin overrides")
                    enabled = settings.get("enabled", True) and overrides.get(name, {}).get("enabled", True)
                    add(
                        client,
                        name,
                        plugin_spec(spec, enabled),
                        "plugin",
                        fingerprint([digest, plugin_digest]),
                        plugin,
                    )
                    records[(client, name, plugin)]["plugin_selection"] = selection
                    records[(client, name, plugin)]["provenance"] = overridden
            except (ValueError, OSError):
                issues.append({"client": client, "reason": "plugin_manifest_unreadable", "owner": "domus-genoma"})
        if client == "claude":
            projects = data.get("projects", {})
            if not isinstance(projects, dict):
                issues.append({"client": client, "reason": "project_state_unmeasured", "owner": "domus-genoma"})
                projects = {}
            for location, scoped in projects.items():
                if not isinstance(scoped, dict):
                    issues.append({"client": client, "reason": "project_config_unreadable", "owner": "domus-genoma"})
                    continue
                for name, spec in server_map(scoped).items():
                    if isinstance(spec, dict):
                        selected = project is not None and Path(location).resolve() == Path(project).resolve()
                        add(
                            client,
                            name,
                            spec,
                            "project-override",
                            fingerprint([digest, location]),
                            "project:" + fingerprint(location)[:12],
                            selected,
                        )
        if config_paths is None and client in MCP_VENDOR_KEYS:
            for candidate in candidate_config_paths(client, client_environments.get(client)):
                if candidate.resolve() == path.resolve() or not candidate.exists():
                    continue
                try:
                    old, old_digest = read_config(candidate)
                    stale.append({"client": client, "fingerprint": old_digest, "registrations": len(server_map(old))})
                except (ValueError, OSError):
                    stale.append({"client": client, "state": "unmeasured"})
    if project:
        for client, rel in (("claude", ".mcp.json"), ("vscode", ".vscode/mcp.json"), ("cursor", ".cursor/mcp.json")):
            path = Path(project) / rel
            if path.exists():
                try:
                    data, digest = read_config(path)
                    for name, spec in server_map(data).items():
                        add(client, name, spec, "project-override", digest, "project")
                except (ValueError, OSError):
                    issues.append({"client": client, "reason": "project_config_unreadable", "owner": "domus-genoma"})
    if config_paths is None:
        cache = active_config_path("codex", client_environments.get("codex")).parent / "plugins/cache"
        for root in sorted(cache.glob("*/*/*")):
            if not root.is_dir():
                continue
            manifests = [root / kind / "plugin.json" for kind in (".codex-plugin", ".claude-plugin")]
            metadata_path = next((p for p in manifests if p.is_file()), None)
            if metadata_path is None:
                continue
            try:
                metadata, digest = read_config(metadata_path)
                plugin_route = root.parent.name + "@" + root.parent.parent.name
                for field in ("mcpServers", "apps"):
                    declaration = metadata.get(field)
                    if declaration is None:
                        continue
                    if isinstance(declaration, str):
                        declared_path = (root / declaration).resolve()
                        if not declared_path.is_relative_to(root.resolve()):
                            raise ValueError("plugin reference escapes installed root")
                        declaration, manifest_digest = read_config(declared_path)
                    elif isinstance(declaration, dict):
                        manifest_digest = fingerprint(declaration)
                    else:
                        raise ValueError("unsupported plugin declaration")
                    table = (
                        declaration.get("apps", declaration)
                        if field == "apps"
                        else server_map(declaration) or declaration
                    )
                    if not isinstance(table, dict):
                        raise ValueError("invalid plugin declaration table")
                    for name, spec in table.items():
                        if not isinstance(spec, dict):
                            raise ValueError("invalid plugin entry")
                        route = plugin_route if field == "mcpServers" else "hosted:" + plugin_route
                        key = ("codex", name, route)
                        if key in records:
                            records[key].setdefault("provenance", []).append(
                                {
                                    "source": "plugin-cache-candidate",
                                    "active": False,
                                    "fingerprint": fingerprint([digest, manifest_digest]),
                                }
                            )
                            continue
                        add(
                            "codex",
                            name,
                            spec if field == "mcpServers" else {},
                            "plugin-cache-candidate",
                            fingerprint([digest, manifest_digest]),
                            route,
                            False,
                        )
            except (OSError, ValueError, TypeError):
                issues.append(
                    {"client": "codex", "reason": "cached_plugin_manifest_unmeasured", "owner": "domus-genoma"}
                )
    for desired in policy.get("registrations", []):
        key = (desired["client"], desired["name"], desired.get("route", "standalone"))
        if key not in records:
            records[key] = {
                "client": key[0],
                "name": key[1],
                "route": key[2],
                "spec": None,
                "source": "expected-missing",
                "fingerprint": None,
                "active": False,
            }
        records[key]["desired"] = desired
    for record in records.values():
        desired = record.get("desired", {})
        service = desired.get(
            "service",
            record["name"] if record["name"] in policy["services"] else record["client"] + "/" + record["name"],
        )
        record["service"] = service
        record["policy"] = policy["services"].get(service)
    return list(records.values()), issues, stale, configs


def gateway_reconciliation():
    """Read and validate every owning input before comparing materialized settings."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ianva/src"))
    try:
        from ianva.config import load_config, _config_files
        from ianva import paths as gateway_paths
        from ianva.upstreams import load_upstreams
        from mcp_gateway_evidence import reconcile, server_table

        sources = []
        for path in _config_files():
            if path.exists():
                _, source_digest = read_config(path)
                sources.append(source_digest)
        config = load_config()
        registry = Path(config.registry) if config.registry else gateway_paths.DEFAULT_REGISTRY
        extra = Path(config.extra) if config.extra else gateway_paths.UPSTREAMS_JSON
        for path in (registry, extra):
            if not path.exists():
                if path == registry:
                    raise ValueError("gateway registry missing")
                continue
            if path.stat().st_size > 16 * 1024 * 1024:
                raise ValueError("gateway registry ceiling")
            raw = path.read_bytes()
            if len(raw) > 16 * 1024 * 1024:
                raise ValueError("gateway registry ceiling")
            server_table(json.loads(raw, object_pairs_hook=unique_fields))
            sources.append(fingerprint(raw))
        expected = load_upstreams(registry, extra, include_disabled=True)
        materialized, _ = read_config(gateway_paths.MCPHUB_SETTINGS)
        result = reconcile(expected, materialized)
        result["source_fingerprint"] = fingerprint(sources)
        return result
    except (OSError, ValueError, ImportError, TypeError, AttributeError):
        return {"owner": "ianva", "state": "unmeasured", "cutover_eligible": False}
    finally:
        sys.path.pop(0)


def summarize(rows, issues):
    counts = dict.fromkeys(DISTANCES, 0)
    for row in rows:
        d = row["dimensions"]
        counts["missing_capabilities"] += row.get("missing_capabilities", 0)
        counts["missing_capabilities"] += d.get("functional") == "fail"
        counts["ownership_conflicts"] += d["ownership"] == "fail"
        counts["unintended_launches"] += d["startup_ui"] == "fail"
        counts["protocol_failures"] += d["protocol"] == "fail"
        counts["authentication_gaps"] += d["authentication"] == "required"
        counts["unmeasured_integrations"] += "unmeasured" in d.values()
        counts["abandoned_processes"] += d["cleanup"] == "fail"
    if counts["unmeasured_integrations"] or issues:
        code = 77
    elif any(v for k, v in counts.items() if k != "unmeasured_integrations") or any(
        "fail" in r["dimensions"].values() for r in rows
    ):
        code = 1
    else:
        code = 0 if rows else 77
    return counts, code


def apply_client_receipts(rows, receipts, policy, now=None, observations=None):
    """Accept only exact-dependency, fresh per-registration canaries; retain unaffected receipts."""
    now = time.time() if now is None else now
    accepted = set()
    observations = observations or {}
    for row in rows:
        key = (row["client"], row["name"], row["route"])
        contract = policy["services"].get(row["service"], {})
        witness = observations.get(key, {})
        for receipt in receipts:
            if not isinstance(receipt, dict):
                continue
            if (receipt.get("client"), receipt.get("name"), receipt.get("route")) != key:
                continue
            observed_at = receipt.get("observed_at")
            if (
                isinstance(observed_at, bool)
                or not isinstance(observed_at, (int, float))
                or not math.isfinite(observed_at)
            ):
                continue
            age = now - observed_at
            ttl = policy.get("defaults", {}).get("evidence_ttl_seconds", 3600)
            if (
                not 0 <= age <= ttl
                or receipt.get("fingerprint") != row["fingerprint"]
                or receipt.get("contract_fingerprint") != fingerprint(contract)
                or not receipt.get("client_version")
                or not receipt.get("server_version")
                or receipt.get("schema_version") != "limen.mcp_client_canary.v1"
                or witness.get("receipt_fingerprint") != fingerprint(receipt)
                or not witness.get("dependency_fingerprint")
                or witness.get("dependency_fingerprint") != receipt.get("dependency_fingerprint")
                or witness.get("client_version") != receipt.get("client_version")
                or witness.get("server_version") != receipt.get("server_version")
                or not receipt.get("run_id")
                or not receipt.get("native_session_id")
                or witness.get("run_id") != receipt.get("run_id")
                or witness.get("native_session_id") != receipt.get("native_session_id")
                or witness.get("observed_at") != observed_at
                or (row.get("server_version") is not None and row["server_version"] != receipt["server_version"])
            ):
                continue
            dimensions = receipt.get("dimensions", {})
            if not isinstance(dimensions, dict):
                continue
            for dimension in ("startup_ui", "explicit_ui", "isolation", "client_route", "functional"):
                if dimensions.get(dimension) in ("pass", "fail", "not_applicable"):
                    row["dimensions"][dimension] = dimensions[dimension]
            row["client_version"] = receipt["client_version"]
            row["dependency_fingerprint"] = witness["dependency_fingerprint"]
            row["evidence_age_seconds"] = age
            if all(
                row["dimensions"].get(k) in ("pass", "not_applicable")
                for k in ("startup_ui", "explicit_ui", "isolation", "client_route")
            ):
                accepted.add(key[0])
    return accepted


def native_receipts(rows, policy, observation):
    """Bind direct collector output to one unambiguous registration and its policy."""
    receipts, witnesses = [], {}
    if observation.get("schema_version") != "limen.native_observation.v1" or observation.get("client") not in (
        "codex",
        "opencode",
    ):
        return receipts, witnesses
    for server in observation.get("servers", []):
        matches = [
            r
            for r in rows
            if r["client"] == observation["client"]
            and r["name"] == server["name"]
            and ((r["route"] == "standalone" and not server.get("plugin_id")) or r["route"] == server.get("plugin_id"))
        ]
        if len(matches) != 1 or not server.get("server_version"):
            continue
        row = matches[0]
        effective = observation.get("effective_configuration", {})
        native = effective.get("registrations", {}).get(server["name"], {})
        if (
            effective.get("state") != "observed"
            or native.get("valid") is not True
            or native.get("disabled") is not False
            or not row.get("launch_fingerprint")
            or native.get("launch_fingerprint") != row["launch_fingerprint"]
        ):
            continue
        dependency = fingerprint(
            [
                observation["binary_fingerprint"],
                observation["configuration_fingerprint"],
                row["fingerprint"],
                server["server_version"],
            ]
        )
        receipt = {
            "schema_version": "limen.mcp_client_canary.v1",
            **{k: row[k] for k in ("client", "name", "route", "fingerprint")},
            "contract_fingerprint": fingerprint(policy["services"].get(row["service"], {})),
            **{k: observation[k] for k in ("run_id", "native_session_id", "client_version", "observed_at")},
            "server_version": server["server_version"],
            "dependency_fingerprint": dependency,
            "dimensions": {
                "client_route": "pass" if server.get("runtime_status") == "connected" else "unmeasured",
                "functional": server.get("functional", {}).get("state", "unmeasured"),
            },
        }
        receipts.append(receipt)
        witnesses[(row["client"], row["name"], row["route"])] = {
            "receipt_fingerprint": fingerprint(receipt),
            "dependency_fingerprint": dependency,
            "client_version": receipt["client_version"],
            "server_version": receipt["server_version"],
            **{k: receipt[k] for k in ("run_id", "native_session_id", "observed_at")},
        }
    return receipts, witnesses


def measure(policy, records, issues, inventory_only=False, service=None, timeout=15, total_timeout=120):
    rows = []
    deadline = time.monotonic() + total_timeout
    enabled_routes = {}
    for record in records:
        if record["spec"] and not record["spec"]["disabled"] and record["active"]:
            enabled_routes.setdefault((record["client"], record["service"]), []).append(record)
    for record in records:
        if service and record["service"] not in service:
            continue
        spec, owner = record["spec"], record["policy"]
        desired = record.get("desired", {}).get("availability", (owner or {}).get("availability", "unknown"))
        d = dict.fromkeys(DIMENSIONS, "unmeasured")
        d["configuration"] = "pass" if spec and not spec["invalid"] else "fail"
        d["ownership"] = "pass" if owner else "unmeasured"
        row = {k: record[k] for k in ("client", "name", "route", "service", "source", "fingerprint")}
        row.update(
            desired_state=desired,
            observed_state="missing" if not spec else ("disabled" if spec["disabled"] else "enabled"),
            dimensions=d,
            owner=(owner or {}).get("source_owner", "domus-genoma"),
            evidence_age_seconds=None,
            repair_outcome="not_attempted",
            provenance=record.get("provenance", []) + [{k: record[k] for k in ("source", "fingerprint", "active")}],
            launch_fingerprint=fingerprint(spec) if spec else None,
        )
        if "plugin_selection" in record:
            row["plugin_selection"] = record["plugin_selection"]
        if len(enabled_routes.get((record["client"], record["service"]), [])) > 1:
            d["ownership"] = "fail"
        if spec and spec["invalid"]:
            row["reason"] = "invalid_registration"
        elif desired == "disabled" and spec and spec["disabled"]:
            d.update({k: "not_applicable" for k in DIMENSIONS if k not in ("configuration", "ownership")})
        elif not spec or spec["disabled"]:
            row["missing_capabilities"] = max(
                1, sum(len(v) for v in (owner or {}).get("verification", {}).get("expected", {}).values())
            )
        elif not record["active"]:
            row["observed_state"] = "inactive_or_activation_unmeasured"
            row["reason"] = "outside_active_client_scope"
        elif not inventory_only and owner and time.monotonic() < deadline:
            contract = owner.get("verification", {})
            # Unknown launchers can pop UI or initiate auth. They remain counted, never launched speculatively.
            quiet = quiet_probe_allowed(record)
            if quiet:
                result = verify(
                    spec,
                    min(timeout, deadline - time.monotonic()),
                    contract.get("expected"),
                    contract.get("protocol", "unsupported"),
                    safe_calls=contract.get("safe_calls"),
                )
                d.update(result.pop("dimensions"))
                # Only counts leave the wire boundary; resource names can contain private paths.
                result.pop("capability_names", None)
                row.update(result)
            else:
                row["reason"] = "quiet_launch_not_proven"
        rows.append(row)
    counts, code = summarize(rows, issues)
    return {
        "schema_version": "limen.mcp_estate.v1",
        "exit": 77 if service else code,
        "distance": counts,
        "denominator": {
            "services": len(set(policy["services"]) | {r["service"] for r in records}),
            "registrations": len(records),
        },
        "scope": "filtered" if service else "estate",
        "measured_registrations": len(rows),
        "unmeasured_surfaces": len(issues),
        "inventory_only": inventory_only,
        "servers": rows,
        "coverage_gaps": issues,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory-only", action="store_true")
    parser.add_argument("--service", action="append")
    parser.add_argument("--policy", type=Path, default=policy_path())
    parser.add_argument("--project", type=Path)
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--total-timeout", type=float, default=120)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--apply", action="store_true", help="one policy-owned Serena settings repair; no login")
    parser.add_argument("--receipts", type=Path, help="private client canary receipt bundle")
    parser.add_argument(
        "--collect-codex", action="store_true", help="fresh admitted native catalog and route observation"
    )
    parser.add_argument("--collect-client", choices=("codex", "opencode"), action="append", default=[])
    parser.add_argument("--broker-run", help="active broker execution run owning the native observation")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not 0 < args.timeout <= 120 or not 0 < args.total_timeout <= 600:
        parser.error("probe deadlines must be positive and bounded (120s/600s)")
    try:
        policy, digest = load_policy(args.policy)
        records, issues, stale, configs = inventory(policy, project=args.project)
        # Desktop/hosted clients have no universal local configuration format. A declared adapter
        # receipt is required; absence is visible even on a machine without that client installed.
        payload = measure(policy, records, issues, args.inventory_only, args.service, args.timeout, args.total_timeout)
        accepted = set()
        collectors = set(args.collect_client) | ({"codex"} if args.collect_codex else set())
        collection_deadline = time.monotonic() + args.total_timeout
        for client in sorted(collectors):
            from mcp_native_observer import collect_codex, ProtocolError
            from mcp_opencode_observer import collect_opencode
            from limen.host_admission import AdmissionDenied
            from limen.conduct.broker import ConductError

            try:
                if not args.broker_run:
                    raise ValueError("native collection requires its broker run")
                from limen.conduct.client import client_from_env

                # Listing status can start every configured MCP. Require every active
                # declaration to have an owner-declared quiet probe before doing so.
                client_records = [
                    r
                    for r in records
                    if r["client"] == client and r["active"] and r["spec"] and not r["spec"]["disabled"]
                ]
                quiet = bool(client_records) and all(quiet_probe_allowed(r) for r in client_records)
                remaining = min(collection_deadline - time.monotonic(), 120)
                if remaining <= 0:
                    raise ValueError("native collection deadline exhausted")
                collector = {"codex": collect_codex, "opencode": collect_opencode}[client]
                options = {}
                if client == "codex" and quiet and not args.inventory_only:
                    options["safe_calls"] = [
                        {**call, "server": record["name"], "launch_fingerprint": fingerprint(record["spec"])}
                        for record in client_records
                        for call in (record["policy"] or {}).get("verification", {}).get("safe_calls", [])
                    ]
                observation = collector(
                    client_from_env(),
                    args.broker_run,
                    args.project or Path.cwd(),
                    timeout=remaining,
                    include_mcp=quiet and not args.inventory_only,
                    **options,
                )
                fresh_records, _, _, _ = inventory(policy, project=args.project)
                if fingerprint(records) != fingerprint(fresh_records):
                    raise ValueError("configuration changed during native collection")
                receipts, witnesses = native_receipts(payload["servers"], policy, observation)
                accepted |= apply_client_receipts(payload["servers"], receipts, policy, observations=witnesses)
                summary = {k: v for k, v in observation.items() if k != "servers"}
                summary["observed_servers"] = len(observation["servers"])
                payload.setdefault("native_observations", []).append(summary)
            except (ValueError, OSError, ProtocolError, ConductError, AdmissionDenied, subprocess.SubprocessError):
                issues.append({"client": client, "reason": "native_collection_unavailable", "owner": "limen"})
        if args.receipts:
            try:
                receipts = json.loads(args.receipts.read_text())
                if not isinstance(receipts, list):
                    raise ValueError("invalid receipt bundle")
                accepted |= apply_client_receipts(payload["servers"], receipts, policy)
            except (ValueError, OSError, TypeError):
                issues.append({"reason": "canary_receipts_unavailable", "owner": "limen"})
        for client in policy.get("required_client_adapters", []):
            if client not in accepted:
                issues.append({"client": client, "reason": "fresh_client_canary_required", "owner": "limen"})
        if args.apply and not args.inventory_only and (not args.service or "serena" in args.service):
            # Domus's registered effector owns diagnosis, exact-content checks, episode lock and backup.
            try:
                process = subprocess.run(
                    [str(Path.home() / ".local/bin/domus-mcp-repair"), "--apply"],
                    capture_output=True,
                    timeout=15,
                    text=True,
                )
                repair = json.loads(process.stdout)
                outcome = repair.get("outcome", "unavailable")
                if process.returncode != 0 and outcome in ("verified", "unchanged"):
                    outcome = "unavailable"
                payload["repair"] = {"outcome": outcome, "owner": "domus-genoma"}
                if outcome == "verified":
                    fresh_records, fresh_issues, _, _ = inventory(policy, project=args.project)
                    issues.extend(fresh_issues)
                    affected = [r for r in fresh_records if r["service"] == "serena"]
                    checked = measure(policy, affected, [], False, None, args.timeout, args.total_timeout)
                    replacements = {(r["client"], r["name"], r["route"]): r for r in checked["servers"]}
                    payload["servers"] = [
                        replacements.get((r["client"], r["name"], r["route"]), r) for r in payload["servers"]
                    ]
                for row in payload["servers"]:
                    if row["service"] == "serena":
                        row["repair_outcome"] = outcome
            except (OSError, ValueError, subprocess.TimeoutExpired):
                payload["repair"] = {"outcome": "unavailable", "owner": "domus-genoma"}
        payload["gateway"] = gateway_reconciliation()
        gateway = payload["gateway"]
        if "ianva" in policy.get("required_client_adapters", []):
            if gateway.get("state") != "configuration_observed":
                issues.append({"client": "ianva", "reason": "gateway_configuration_unmeasured", "owner": "ianva"})
            elif gateway.get("configuration_mismatches", 0):
                issues.append({"client": "ianva", "reason": "gateway_configuration_mismatch", "owner": "ianva"})
            if not gateway.get("cutover_eligible"):
                issues.append({"client": "ianva", "reason": "gateway_equivalence_required", "owner": "ianva"})
        payload["distance"], payload["exit"] = summarize(payload["servers"], issues)
        if args.service:
            payload["exit"] = 77
        payload["unmeasured_surfaces"] = len(issues)
        payload.update(policy_fingerprint=digest, stale_configs=stale, configurations=configs)
    except (ValueError, OSError, KeyError, TypeError):
        payload = {"schema_version": "limen.mcp_estate.v1", "exit": 77, "reason": "policy_or_inventory_unavailable"}
    print(
        json.dumps(payload, indent=2)
        if args.json
        else json.dumps({k: v for k, v in payload.items() if k not in ("servers", "configurations", "stale_configs")})
    )
    return payload["exit"]
