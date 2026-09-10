"""Gateway reconciliation without writes, login, or inferred routing equivalence.

Only hashes and counts leave configuration custody. Materialized credentials may
rotate independently; launch arguments, headers and environment still must agree
with the owning declaration before a cutover can be considered.
"""

from __future__ import annotations

import hashlib
import json


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def server_table(blob):
    """Accept the owning loader's shapes, but reject silently discarded entries."""
    if isinstance(blob, dict):
        containers = [key for key in ("servers", "mcpServers", "mcp") if key in blob]
        if len(containers) > 1:
            raise ValueError("ambiguous gateway container")
        if containers:
            blob = blob[containers[0]]
    if isinstance(blob, list):
        result = {}
        for entry in blob:
            if not isinstance(entry, dict) or not isinstance(entry.get("name"), str) or not entry["name"]:
                raise ValueError("invalid gateway registration")
            if entry["name"] in result:
                raise ValueError("duplicate gateway registration")
            result[entry["name"]] = entry
        return result
    if not isinstance(blob, dict) or any(
        not isinstance(name, str) or not name or not isinstance(spec, dict) for name, spec in blob.items()
    ):
        raise ValueError("invalid gateway registrations")
    return blob


def declared_spec(upstream):
    if upstream.is_remote():
        spec = {"type": "sse" if upstream.transport == "sse" else "streamable-http", "url": upstream.url}
        if upstream.headers:
            spec["headers"] = upstream.headers
    else:
        spec = {"command": upstream.command, "args": upstream.args}
        if upstream.env:
            spec["env"] = upstream.env
    spec["enabled"] = upstream.enabled
    if upstream.group and upstream.group != "default":
        spec["group"] = upstream.group
    return spec


def launch_identity(spec):
    # Empty/default values normalize identically to the owning materializer.
    # Backend-owned refresh tokens and opaque extra settings are provenance, not
    # values to copy back into the source declaration.
    keys = ("command", "args", "env", "url", "type", "headers", "enabled", "group")
    result = {key: spec[key] for key in keys if key in spec}
    result.setdefault("enabled", True)
    if type(result["enabled"]) is not bool:
        raise ValueError("invalid gateway enabled state")
    for key in ("env", "headers"):
        value = result.get(key, {})
        if not isinstance(value, dict) or any(
            not isinstance(k, str) or not isinstance(v, str) for k, v in value.items()
        ):
            raise ValueError("invalid gateway launch mapping")
        if not value:
            result.pop(key, None)
    if result.get("group") in (None, "", "default"):
        result.pop("group", None)
    if "command" in result:
        result.setdefault("args", [])
        if not isinstance(result["command"], str) or not result["command"] or "url" in result:
            raise ValueError("invalid gateway command")
        if not isinstance(result["args"], list) or any(not isinstance(v, str) for v in result["args"]):
            raise ValueError("invalid gateway arguments")
    elif (
        not isinstance(result.get("url"), str)
        or not result["url"]
        or result.get("type") not in ("sse", "streamable-http")
    ):
        raise ValueError("invalid gateway transport")
    return result


def reconcile(expected, materialized):
    actual = server_table(materialized)
    declarations = {upstream.name: declared_spec(upstream) for upstream in expected}
    if len(declarations) != len(expected):
        raise ValueError("duplicate declared upstream")
    rows = []
    for name in sorted(set(declarations) | set(actual)):
        desired, observed = declarations.get(name), actual.get(name)
        row = {
            "name": name,
            "desired_state": "undeclared" if desired is None else "enabled" if desired["enabled"] else "disabled",
            "observed_state": "missing"
            if observed is None
            else "enabled"
            if observed.get("enabled", True) is True
            else "disabled",
            "configuration": "fail",
            "capabilities": "unmeasured",
            "client_routes": "unmeasured",
            "desired_fingerprint": digest(desired) if desired is not None else None,
            "materialized_fingerprint": digest(observed) if observed is not None else None,
        }
        if desired is not None and observed is not None:
            try:
                row["configuration"] = "pass" if launch_identity(desired) == launch_identity(observed) else "fail"
            except ValueError:
                row["observed_state"] = "invalid"
        rows.append(row)
    return {
        "owner": "ianva",
        "state": "configuration_observed",
        "fingerprint": digest(materialized),
        "expected_upstreams": len(expected),
        "materialized_upstreams": len(actual),
        "configuration_mismatches": sum(row["configuration"] != "pass" for row in rows),
        "missing_upstreams": sum(row["observed_state"] == "missing" for row in rows),
        "undeclared_upstreams": sum(row["desired_state"] == "undeclared" for row in rows),
        "upstreams": rows,
        "cutover_eligible": False,
    }


def reconcile_capabilities(direct, routed, mapping):
    """Compare complete native catalogs under an explicit owner route mapping.

    Callers must independently bind both captures to fresh collector evidence.
    This pure comparison alone cannot authorize a cutover or certify a client.
    Names and resource URIs stay inside the comparator.
    """
    result = {}
    for kind, key in (("tools", "name"), ("resources", "uri"), ("prompts", "name")):
        left, right = direct.get(kind), routed.get(kind)
        aliases = mapping.get(kind, {})
        if not isinstance(left, list) or not isinstance(right, list) or not isinstance(aliases, dict):
            result[kind] = {"state": "unmeasured"}
            continue

        def index(rows):
            indexed = {}
            for row in rows:
                if not isinstance(row, dict) or not isinstance(row.get(key), str) or row[key] in indexed:
                    raise ValueError("invalid or duplicate capability")
                indexed[row[key]] = {k: v for k, v in row.items() if k != key}
            return indexed

        before, after = index(left), index(right)
        if (
            set(aliases) != set(before)
            or any(not isinstance(v, str) for v in aliases.values())
            or len(set(aliases.values())) != len(aliases)
        ):
            result[kind] = {"state": "fail", "reason": "incomplete_or_colliding_route_mapping"}
            continue
        translated = {aliases[name]: spec for name, spec in before.items()}
        missing = len(set(translated) - set(after))
        changed = sum(name in after and spec != after[name] for name, spec in translated.items())
        unexpected = len(set(after) - set(translated))
        result[kind] = {
            "state": "fail" if missing or changed or unexpected else "pass",
            "missing": missing,
            "changed": changed,
            "unexpected": unexpected,
        }
    return result
