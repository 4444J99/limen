#!/usr/bin/env python3
"""Add the legacy owner bearer to a conduct principal registry without weakening it."""

from __future__ import annotations

import json
import os
import sys
from typing import Any


def merge_registry(registry: dict[str, Any], legacy: str) -> dict[str, Any]:
    principals = registry.get("principals")
    if not isinstance(principals, list):
        raise ValueError("conduct principal registry principals must be a list")

    if legacy:
        matches = [row for row in principals if isinstance(row, dict) and row.get("bearer") == legacy]
        if len(matches) > 1:
            raise ValueError("legacy bearer is bound to multiple conduct principals")
        if matches:
            roles = matches[0].get("roles", [])
            if not isinstance(roles, list) or not all(isinstance(role, str) for role in roles):
                raise ValueError("legacy conduct principal roles must be a string list")
            matches[0]["roles"] = sorted({*roles, "compatibility"})
        else:
            principals.append(
                {
                    "agent": "codex",
                    "bearer": legacy,
                    "principal_id": "codex-direct-legacy",
                    "roles": ["observer", "conductor", "compatibility"],
                    "surface": "direct",
                }
            )

    if not any(
        isinstance(row, dict) and "compatibility" in row.get("roles", [])
        for row in principals
    ):
        raise ValueError("merged conduct registry has no compatibility principal")
    return registry


def main() -> int:
    try:
        registry = json.loads(os.environ["LIMEN_CONDUCT_PRINCIPAL_REGISTRY"])
        if not isinstance(registry, dict):
            raise ValueError("conduct principal registry must be an object")
        merged = merge_registry(registry, os.environ.get("LIMEN_CONDUCT_TOKEN", ""))
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"merge-conduct-principal-registry: FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(merged, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
