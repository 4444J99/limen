#!/usr/bin/env python3
"""Ground-truth predicate for ARCA release-asset writes."""

from __future__ import annotations

import json
import re
import subprocess
import sys


def _api(path: str) -> dict[str, object]:
    result = subprocess.run(
        ["gh", "api", path],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    if result.returncode:
        raise RuntimeError("GitHub repository identity lookup failed")
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise TypeError("GitHub returned an invalid repository identity")
    return value


def inspect_repository(repo: str) -> tuple[int, str, str]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise RuntimeError("repository must be owner/name")
    alias = _api(f"repos/{repo}")
    stable_id = int(alias["id"])
    live = _api(f"repositories/{stable_id}")
    coordinate = str(live["full_name"])
    default_branch = str(live["default_branch"])
    if (
        stable_id <= 0
        or int(live.get("id", -1)) != stable_id
        or alias.get("private") is not True
        or live.get("private") is not True
        or str(alias.get("full_name", "")) != coordinate
        or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", coordinate)
        or not re.fullmatch(r"[A-Za-z0-9_./-]+", default_branch)
    ):
        raise RuntimeError("immutable repository identity or private visibility did not verify")
    return stable_id, coordinate, default_branch


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: preflight-arca-release-assets.py <owner/repo>", file=sys.stderr)
        return 2
    try:
        stable_id, coordinate, _default_branch = inspect_repository(sys.argv[1])
    except (
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        RuntimeError,
        OSError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"FAIL: ARCA asset target unavailable ({type(exc).__name__})", file=sys.stderr)
        return 1
    print(f"PASS: private repository identity verified (id={stable_id}, coordinate={coordinate})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
