#!/usr/bin/env python3
"""Reclaim ignored generated state from workspace git roots.

This script is intentionally narrower than worktree removal. It does not delete
roots, branches, source files, untracked non-ignored files, or private patches.
It asks each git root to remove only ignored generated dependency/build/cache
paths from an allowlist.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


HOME = Path(os.environ.get("HOME", "/Users/4jp")).expanduser()
ROOT = Path(os.environ.get("LIMEN_ROOT", HOME / "Workspace" / "limen")).expanduser()
WORKSPACE_ROOT = Path(os.environ.get("LIMEN_WORKSPACE_ROOT", HOME / "Workspace")).expanduser()
LOG_PATH = ROOT / "logs" / "reclaim-generated-state.jsonl"

GENERATED_NAMES = (
    "node_modules",
    ".venv",
    ".next",
    "dist",
    "build",
    "coverage",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".parcel-cache",
    ".turbo",
    "__pycache__",
)

PRUNE_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    ".next",
    "dist",
    "build",
    "coverage",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".parcel-cache",
    ".turbo",
    "__pycache__",
}


def git(args: list[str], cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(args, 1, "", str(exc))


def du_kib(path: Path, timeout: int = 30) -> int | None:
    try:
        proc = subprocess.run(["du", "-sk", str(path)], text=True, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        return int(proc.stdout.split()[0])
    except (IndexError, ValueError):
        return None


def fmt_bytes(value: int | None) -> str:
    if value is None:
        return "unknown"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{int(amount)} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{value} B"


def iter_git_roots(roots: list[Path]) -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        root = root.expanduser()
        if not root.exists():
            continue
        for current, dirs, _files in os.walk(root):
            path = Path(current)
            git_marker = path / ".git"
            if git_marker.exists():
                try:
                    resolved = path.resolve()
                except OSError:
                    resolved = path
                if resolved not in seen:
                    seen.add(resolved)
                    found.append(path)
                dirs[:] = [name for name in dirs if name not in PRUNE_DIRS]
                continue
            dirs[:] = [name for name in dirs if name not in PRUNE_DIRS]
    return sorted(found, key=lambda path: str(path))


def clean_pathspecs() -> list[str]:
    return list(GENERATED_NAMES)


def repo_toplevel(root: Path) -> Path | None:
    proc = git(["rev-parse", "--show-toplevel"], root, timeout=30)
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        return Path(proc.stdout.strip()).resolve()
    except OSError:
        return Path(proc.stdout.strip())


def is_ignored(root: Path, path: Path, *, timeout: int) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False
    proc = git(["check-ignore", "--quiet", "--", rel.as_posix()], root, timeout=timeout)
    return proc.returncode == 0


def generated_candidates(root: Path, *, timeout: int) -> list[Path]:
    candidates: list[Path] = []
    for current, dirs, _files in os.walk(root):
        path = Path(current)
        if path.name == ".git":
            dirs[:] = []
            continue
        kept_dirs: list[str] = []
        for name in dirs:
            if name == ".git":
                continue
            child = path / name
            if name in GENERATED_NAMES and is_ignored(root, child, timeout=timeout):
                candidates.append(child)
                continue
            kept_dirs.append(name)
        dirs[:] = kept_dirs
    return sorted(candidates, key=lambda path: str(path))


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    shutil.rmtree(path)


def clean_root(root: Path, *, apply: bool, timeout: int) -> dict[str, Any]:
    top = repo_toplevel(root)
    try:
        resolved_root = root.resolve()
    except OSError:
        resolved_root = root
    if top is None or top != resolved_root:
        return {
            "root": str(root),
            "ok": True,
            "skipped": True,
            "skip_reason": "not-a-valid-git-root",
            "returncode": 0,
            "apply": apply,
            "changed_line_count": 0,
            "sample": [],
            "before_kib": None,
            "after_kib": None,
            "reclaimed_kib": 0,
            "reclaimed_size": "0 B",
        }
    candidates = generated_candidates(root, timeout=timeout)
    before_kib = sum(value for value in (du_kib(path) for path in candidates) if value is not None)
    lines = [f"{'Removing' if apply else 'Would remove'} {path.relative_to(root).as_posix()}/" for path in candidates]
    failed: list[str] = []
    if apply:
        for path in candidates:
            try:
                remove_path(path)
            except OSError as exc:
                failed.append(f"{path.relative_to(root).as_posix()}: {exc}")
    after_existing = [path for path in candidates if path.exists()]
    after_kib = sum(value for value in (du_kib(path) for path in after_existing) if value is not None) if apply else before_kib
    reclaimed_kib = max(before_kib - after_kib, 0) if apply else 0
    return {
        "root": str(root),
        "ok": not failed,
        "returncode": 0 if not failed else 1,
        "apply": apply,
        "changed_line_count": len(lines),
        "sample": [*lines[:10], *failed[:2]],
        "before_kib": before_kib,
        "after_kib": after_kib,
        "reclaimable_kib": before_kib,
        "reclaimable_size": fmt_bytes(before_kib * 1024),
        "reclaimed_kib": reclaimed_kib,
        "reclaimed_size": fmt_bytes(reclaimed_kib * 1024) if reclaimed_kib is not None else "unknown",
    }


def write_log(payload: dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clean ignored generated dependency/build/cache state.")
    parser.add_argument("--apply", action="store_true", help="perform cleanup; default is dry-run")
    parser.add_argument("--json", action="store_true", help="print JSON")
    parser.add_argument("--root", action="append", type=Path, help="workspace root to scan; repeatable")
    parser.add_argument("--limit", type=int, default=int(os.environ.get("LIMEN_RECLAIM_GENERATED_STATE_LIMIT", "500")))
    parser.add_argument("--timeout", type=int, default=int(os.environ.get("LIMEN_RECLAIM_GENERATED_STATE_TIMEOUT", "180")))
    args = parser.parse_args(argv)

    scan_roots = args.root or [WORKSPACE_ROOT]
    roots = iter_git_roots(scan_roots)[: max(args.limit, 0)]
    started = time.time()
    rows = [clean_root(path, apply=args.apply, timeout=max(args.timeout, 1)) for path in roots]
    total_reclaimed_kib = sum(int(row.get("reclaimed_kib") or 0) for row in rows)
    total_reclaimable_kib = sum(int(row.get("reclaimable_kib") or 0) for row in rows)
    failed = [row for row in rows if not row.get("ok")]
    changed = [row for row in rows if int(row.get("changed_line_count") or 0) > 0 or int(row.get("reclaimed_kib") or 0) > 0]
    payload = {
        "schema": "limen.reclaim_generated_state.v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "apply": args.apply,
        "scanned_roots": len(roots),
        "changed_roots": len(changed),
        "failed_roots": len(failed),
        "total_reclaimable_kib": total_reclaimable_kib,
        "total_reclaimable_size": fmt_bytes(total_reclaimable_kib * 1024),
        "total_reclaimed_kib": total_reclaimed_kib,
        "total_reclaimed_size": fmt_bytes(total_reclaimed_kib * 1024),
        "duration_sec": round(time.time() - started, 2),
        "allowlist": list(GENERATED_NAMES),
        "changed": changed,
        "failed": failed,
    }
    if args.apply:
        write_log(payload)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        mode = "apply" if args.apply else "dry-run"
        print(
            f"reclaim-generated-state [{mode}]: {len(changed)} changed / {len(roots)} scanned, "
            f"{len(failed)} failed, reclaimed {payload['total_reclaimed_size']}"
        )
        for row in changed[:40]:
            print(f"  {row['reclaimed_size']:>10} {row['root']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
