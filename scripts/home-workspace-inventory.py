#!/usr/bin/env python3
"""Resumable, read-only filesystem frontier for home and Workspace.

The state contains private paths. Keep it in an owner-protected local location;
its findings are inventory evidence and never authorize retirement.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import time
from collections import deque
from pathlib import Path

SCHEMA = "limen.home_workspace_inventory.v1"
SOURCE_MARKERS = {"package.json", "pyproject.toml", "Cargo.toml", "go.mod", "Makefile"}


def identity(info: os.stat_result) -> str:
    return f"{info.st_dev}:{info.st_ino}"


def save(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(state, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def initial(roots: list[Path]) -> dict:
    resolved = [path.absolute() for path in roots]
    return {
        "schema": SCHEMA,
        "roots": [str(path) for path in resolved],
        "frontier": [str(path) for path in resolved],
        "root_devices": {str(path): os.lstat(path).st_dev for path in resolved},
        "seen_directories": [],
        "objects": [],
        "unmeasured": [],
        "resolved_changes": [],
        "complete": False,
    }


def _record(state: dict, path: str, kind: str, key: str, **extra: object) -> None:
    state["objects"].append({"path": path, "kind": kind, "fs_identity": key, **extra})


def advance(state: dict, *, max_directories: int, max_seconds: float) -> dict:
    if state.get("schema") != SCHEMA or not isinstance(state.get("frontier"), list):
        raise ValueError("invalid inventory state")
    state.setdefault("resolved_changes", [])
    deadline = time.monotonic() + max_seconds
    seen = set(state["seen_directories"])
    frontier = deque(state["frontier"])
    processed = 0
    while frontier and processed < max_directories and time.monotonic() < deadline:
        path = frontier.popleft()
        try:
            info = os.lstat(path)
            key = identity(info)
            if stat.S_ISLNK(info.st_mode):
                _record(state, path, "symlink", key, target=os.readlink(path))
                continue
            if not stat.S_ISDIR(info.st_mode):
                _record(state, path, "non_directory_root", key)
                continue
            if key in seen:
                _record(state, path, "directory_alias", key)
                continue
            root = next((root for root in state["roots"] if path == root or path.startswith(root + os.sep)), None)
            if root is None or info.st_dev != state["root_devices"][root]:
                _record(state, path, "mounted_boundary", key)
                continue
            seen.add(key)
            processed += 1
            with os.scandir(path) as stream:
                entries = list(stream)
            names = {entry.name for entry in entries}
            if ".git" in names:
                marker = next(entry for entry in entries if entry.name == ".git")
                marker_kind = "git_file_checkout_candidate" if marker.is_file(follow_symlinks=False) else "git_checkout"
                _record(state, path, marker_kind, key)
            elif {"HEAD", "objects", "refs"}.issubset(names):
                kind = "checkout_git_store" if Path(path).name == ".git" else "bare_git_candidate"
                _record(state, path, kind, key)
            elif names & SOURCE_MARKERS:
                _record(state, path, "copied_source_candidate", key, markers=sorted(names & SOURCE_MARKERS))
            for entry in entries:
                child = entry.path
                try:
                    child_info = entry.stat(follow_symlinks=False)
                    child_key = identity(child_info)
                    if stat.S_ISLNK(child_info.st_mode):
                        _record(state, child, "symlink", child_key, target=os.readlink(child))
                    elif stat.S_ISDIR(child_info.st_mode):
                        if child_key not in seen:
                            frontier.append(child)
                    elif entry.name == ".git":
                        _record(state, child, "git_file", child_key)
                except OSError as exc:
                    state["unmeasured"].append({"path": child, "error": type(exc).__name__})
        except OSError as exc:
            state["unmeasured"].append({"path": path, "error": type(exc).__name__})
    state["seen_directories"] = sorted(seen)
    state["frontier"] = list(frontier)
    still_unmeasured = []
    for item in state["unmeasured"]:
        if item["error"] == "FileNotFoundError" and not os.path.lexists(item["path"]):
            state["resolved_changes"].append({**item, "resolution": "vanished_during_scan"})
        else:
            still_unmeasured.append(item)
    state["unmeasured"] = still_unmeasured
    state["complete"] = not state["frontier"] and not state["unmeasured"]
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--root", action="append", type=Path)
    parser.add_argument("--max-directories", type=int, default=500)
    parser.add_argument("--max-seconds", type=float, default=10)
    args = parser.parse_args()
    if args.max_directories < 1 or args.max_seconds <= 0:
        parser.error("bounds must be positive")
    roots = args.root or [Path.home()]
    if args.state.exists():
        state = json.loads(args.state.read_text(encoding="utf-8"))
        if state.get("roots") != [str(path.absolute()) for path in roots]:
            parser.error("state roots differ from requested roots")
    else:
        state = initial(roots)
    for row in state["objects"]:
        if row["kind"] == "bare_git_candidate" and Path(row["path"]).name == ".git":
            row["kind"] = "checkout_git_store"
        elif row["kind"] == "linked_worktree":
            row["kind"] = "git_file_checkout_candidate"
    advance(state, max_directories=args.max_directories, max_seconds=args.max_seconds)
    save(args.state, state)
    print(json.dumps({"complete": state["complete"], "frontier": len(state["frontier"]),
                      "objects": len(state["objects"]), "unmeasured": len(state["unmeasured"]),
                      "resolved_changes": len(state["resolved_changes"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
