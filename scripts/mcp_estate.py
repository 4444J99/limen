"""Desired/observed MCP estate reconciliation; unavailable coverage never becomes green.

Domus owns intent. This module reads configs but never edits them. Raw launch specifications
remain process-local: reports expose only stable identities and content fingerprints.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
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


def read_config(path):
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
            data = json.loads(raw_json)
        else:
            data = json.loads(raw)
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


def normalize(spec):
    command = spec.get("command")
    url = spec.get("url") or spec.get("serverUrl") or spec.get("httpUrl")
    return {
        "command": command,
        "args": spec.get("args", []),
        "url": url,
        "transport": "stdio" if command else ("http" if url else "unsupported"),
        "env": spec.get("env", {}),
        "cwd": spec.get("cwd"),
        "bearer_token_env_var": spec.get("bearer_token_env_var"),
        "disabled": spec.get("disabled") is True or spec.get("enabled") is False,
    }


def inventory(policy, config_paths=None, project=None):
    paths = config_paths if config_paths is not None else [(c, active_config_path(c)) for c in MCP_VENDOR_KEYS]
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
            "spec": normalize(spec),
            "active": active,
        }
        if key in records:
            issues.append({"client": client, "reason": "ambiguous_registration", "owner": "domus-genoma"})
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
        table = server_map(data)
        if client == "ianva" and not table:
            table = {k: v for k, v in data.items() if isinstance(v, dict)}
        for name, spec in table.items():
            if isinstance(spec, dict):
                add(client, name, spec, "active-config", digest)
            else:
                issues.append({"client": client, "reason": "invalid_registration", "owner": "domus-genoma"})
        for plugin, settings in data.get("plugins", {}).items():
            if not isinstance(settings, dict):
                issues.append({"client": client, "reason": "plugin_state_unmeasured", "owner": "domus-genoma"})
                continue
            plugin_name = plugin.split("@", 1)[0]
            roots = list((path.parent / "plugins/cache").glob(f"*/{plugin_name}/*"))
            manifests = [r / ".mcp.json" for r in roots if (r / ".mcp.json").exists()]
            if len(roots) == 1 and not manifests:
                try:
                    metadata, _ = read_config(roots[0] / ".claude-plugin/plugin.json")
                    if "mcpServers" not in metadata:
                        continue  # installed plugin explicitly has no MCP entry point
                    if isinstance(metadata["mcpServers"], dict):
                        for name, spec in metadata["mcpServers"].items():
                            add(client, name, spec, "plugin-inline", digest, plugin)
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
                    if not isinstance(spec, dict):
                        raise ValueError("invalid plugin server")
                    enabled = settings.get("enabled", True) and settings.get("mcp_servers", {}).get(name, {}).get(
                        "enabled", True
                    )
                    add(
                        client,
                        name,
                        {**spec, "enabled": enabled},
                        "plugin",
                        fingerprint([digest, plugin_digest]),
                        plugin,
                    )
            except (ValueError, OSError):
                issues.append({"client": client, "reason": "plugin_manifest_unreadable", "owner": "domus-genoma"})
        if client == "claude":
            for location, scoped in data.get("projects", {}).items():
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
            for candidate in candidate_config_paths(client):
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


def summarize(rows, issues):
    counts = dict.fromkeys(DISTANCES, 0)
    for row in rows:
        d = row["dimensions"]
        counts["missing_capabilities"] += row.get("missing_capabilities", 0)
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


def apply_client_receipts(rows, receipts, policy, now=None):
    """Accept only exact-dependency, fresh per-registration canaries; retain unaffected receipts."""
    now = time.time() if now is None else now
    accepted = set()
    for row in rows:
        key = (row["client"], row["name"], row["route"])
        contract = policy["services"].get(row["service"], {})
        for receipt in receipts:
            if (receipt.get("client"), receipt.get("name"), receipt.get("route")) != key:
                continue
            age = now - receipt.get("observed_at", 0)
            ttl = policy.get("defaults", {}).get("evidence_ttl_seconds", 3600)
            if (
                not 0 <= age <= ttl
                or receipt.get("fingerprint") != row["fingerprint"]
                or receipt.get("contract_fingerprint") != fingerprint(contract)
                or not receipt.get("client_version")
                or not receipt.get("server_version")
                or receipt.get("schema_version") != "limen.mcp_client_canary.v1"
            ):
                continue
            dimensions = receipt.get("dimensions", {})
            for dimension in ("startup_ui", "explicit_ui", "isolation", "client_route"):
                if dimensions.get(dimension) in ("pass", "fail", "not_applicable"):
                    row["dimensions"][dimension] = dimensions[dimension]
            row["client_version"] = receipt["client_version"]
            row["evidence_age_seconds"] = age
            accepted.add(key[0])
    return accepted


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
        d["configuration"] = "pass" if spec else "fail"
        d["ownership"] = "pass" if owner else "unmeasured"
        row = {k: record[k] for k in ("client", "name", "route", "service", "source", "fingerprint")}
        row.update(
            desired_state=desired,
            observed_state="missing" if not spec else ("disabled" if spec["disabled"] else "enabled"),
            dimensions=d,
            owner=(owner or {}).get("source_owner", "domus-genoma"),
            evidence_age_seconds=0,
            repair_outcome="not_attempted",
        )
        if len(enabled_routes.get((record["client"], record["service"]), [])) > 1:
            d["ownership"] = "fail"
        if desired == "disabled" and spec and spec["disabled"]:
            d.update({k: "not_applicable" for k in DIMENSIONS if k not in ("configuration", "ownership")})
        elif not spec or spec["disabled"]:
            row["missing_capabilities"] = max(
                1, sum(len(v) for v in (owner or {}).get("verification", {}).get("expected", {}).values())
            )
        elif not inventory_only and owner and time.monotonic() < deadline:
            contract = owner.get("verification", {})
            # Unknown launchers can pop UI or initiate auth. They remain counted, never launched speculatively.
            quiet = spec["transport"] == "http" or contract.get("quiet_probe") is True
            if record["service"] == "serena":
                args = spec.get("args", [])
                quiet = any(args[i : i + 2] == ["--open-web-dashboard", "false"] for i in range(len(args)))
            if quiet:
                result = verify(
                    spec,
                    min(timeout, deadline - time.monotonic()),
                    contract.get("expected"),
                    contract.get("protocol", "unsupported"),
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
        "exit": code,
        "distance": counts,
        "denominator": {"services": len({r["service"] for r in records}), "registrations": len(records)},
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
        if args.receipts:
            try:
                receipts = json.loads(args.receipts.read_text())
                if not isinstance(receipts, list):
                    raise ValueError("invalid receipt bundle")
                accepted = apply_client_receipts(payload["servers"], receipts, policy)
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
                payload["repair"] = {"outcome": repair.get("outcome", "unavailable"), "owner": "domus-genoma"}
                if repair.get("outcome") == "verified":
                    affected = [r for r in records if r["service"] == "serena"]
                    checked = measure(policy, affected, [], False, None, args.timeout, args.total_timeout)
                    replacements = {(r["client"], r["name"], r["route"]): r for r in checked["servers"]}
                    payload["servers"] = [
                        replacements.get((r["client"], r["name"], r["route"]), r) for r in payload["servers"]
                    ]
            except (OSError, ValueError, subprocess.TimeoutExpired):
                payload["repair"] = {"outcome": "unavailable", "owner": "domus-genoma"}
        payload["distance"], payload["exit"] = summarize(payload["servers"], issues)
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
