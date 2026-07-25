#!/usr/bin/env python3
"""Proof-gated reclamation for regenerable package and tool caches.

The laptop is a hot cache, but deletion still fails closed. ``--check`` emits
an immutable candidate manifest and digest. ``--apply`` accepts only that exact
digest after re-probing path identity and live process ownership.

Agent state, model stores, private corpora, messages, mail, photos, worktrees,
and scratch roots are deliberately outside the allowlist.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


HOME = Path(os.environ.get("HOME", "/Users/4jp")).expanduser()
ROOT = Path(os.environ.get("LIMEN_ROOT", HOME / "Workspace" / "limen")).expanduser()
LOG_PATH = ROOT / "logs" / "reclaim-tool-caches.jsonl"


@dataclass(frozen=True)
class CacheSpec:
    label: str
    process_tokens: tuple[str, ...]


CACHE_SPECS = (
    CacheSpec("~/.cache/npm", ("npm", "npx", "node")),
    CacheSpec("~/.cache/pnpm", ("pnpm", "node")),
    CacheSpec("~/.cache/pre-commit", ("pre-commit",)),
    CacheSpec("~/.cache/puppeteer", ("puppeteer", "chrome-for-testing")),
    CacheSpec("~/.cache/uv", ("uv", "uvx")),
    CacheSpec("~/.npm/_cacache", ("npm", "npx", "node")),
    CacheSpec("~/.pytest_cache", ("pytest",)),
    CacheSpec("~/.local/share/pnpm/store", ("pnpm", "node")),
    CacheSpec("~/Library/Caches/ms-playwright", ("playwright",)),
    CacheSpec("~/Library/Caches/ms-playwright-go", ("playwright",)),
    CacheSpec("~/Library/Caches/node-gyp", ("node-gyp", "npm", "node")),
    CacheSpec("~/Library/Caches/pip", ("pip",)),
    CacheSpec("~/Library/Caches/pip-audit", ("pip-audit",)),
    CacheSpec("~/Library/Caches/pnpm", ("pnpm", "node")),
    CacheSpec("~/Library/Caches/prisma-nodejs", ("prisma", "node")),
    CacheSpec("~/Library/Caches/pylint", ("pylint",)),
    CacheSpec("~/Library/Caches/virtualenv", ("virtualenv",)),
)

EXCLUDED_CLASSES = (
    "agent-state",
    "agy-scratch",
    "gemini-brain",
    "ollama-models",
    "opencode-snapshots",
    "private-corpus",
    "mail-messages-photos",
    "worktrees",
    "personal-raw-data",
)


def expand(path: str) -> Path:
    return Path(path.replace("~", str(HOME), 1)).expanduser()


def _under_home(path: Path) -> bool:
    try:
        path.relative_to(HOME)
    except ValueError:
        return False
    return path != HOME


def du_kib(path: Path, timeout: int = 30) -> int | None:
    try:
        proc = subprocess.run(
            ["du", "-sk", str(path)],
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
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


def process_snapshot() -> tuple[list[dict[str, object]], str]:
    """Return bounded PID/argv/cwd evidence, or an explicit sensor error."""

    try:
        ps = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        cwd = subprocess.run(
            ["lsof", "-nP", "-a", "-d", "cwd", "-F", "pcn"],
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [], f"process-sensor-error:{type(exc).__name__}"
    if ps.returncode != 0 or cwd.returncode != 0:
        return [], f"process-sensor-returncode:ps={ps.returncode},lsof={cwd.returncode}"

    rows: dict[int, dict[str, object]] = {}
    for line in ps.stdout.splitlines():
        fields = line.strip().split(maxsplit=1)
        if not fields or not fields[0].isdigit():
            continue
        pid = int(fields[0])
        rows[pid] = {"pid": pid, "command": fields[1] if len(fields) > 1 else "", "cwd": ""}

    current_pid: int | None = None
    for line in cwd.stdout.splitlines():
        if line.startswith("p") and line[1:].isdigit():
            current_pid = int(line[1:])
        elif line.startswith("n") and current_pid in rows:
            rows[current_pid]["cwd"] = line[1:]
    return list(rows.values()), ""


def _path_contains(parent: Path, child: str) -> bool:
    if not child:
        return False
    try:
        Path(child).resolve().relative_to(parent.resolve())
    except (OSError, ValueError):
        return False
    return True


def active_owners(spec: CacheSpec, path: Path, processes: Iterable[dict[str, object]]) -> list[int]:
    tokens = tuple(token.lower() for token in spec.process_tokens)
    owners: set[int] = set()
    for row in processes:
        command = str(row.get("command") or "").lower()
        cwd = str(row.get("cwd") or "")
        if any(token in command for token in tokens) or _path_contains(path, cwd):
            try:
                owners.add(int(row["pid"]))
            except (KeyError, TypeError, ValueError):
                continue
    return sorted(owners)


def _tree_identity(path: Path) -> tuple[str, int]:
    """Hash bounded filesystem metadata without reading cache contents."""

    digest = hashlib.sha256()
    count = 0

    def add(entry: Path) -> None:
        nonlocal count
        info = entry.lstat()
        relative = "." if entry == path else str(entry.relative_to(path))
        record = (
            relative,
            stat.S_IFMT(info.st_mode),
            info.st_size,
            info.st_mtime_ns,
            info.st_ino,
        )
        digest.update(json.dumps(record, separators=(",", ":")).encode())
        digest.update(b"\n")
        count += 1

    add(path)
    if path.is_dir() and not path.is_symlink():

        def raise_walk_error(error: OSError) -> None:
            raise error

        for root, directories, files in os.walk(
            path,
            followlinks=False,
            onerror=raise_walk_error,
        ):
            directories.sort()
            files.sort()
            root_path = Path(root)
            for name in (*directories, *files):
                add(root_path / name)
    return digest.hexdigest(), count


def _identity(path: Path, kib: int) -> dict[str, object]:
    info = path.lstat()
    kind = "symlink" if stat.S_ISLNK(info.st_mode) else "directory" if stat.S_ISDIR(info.st_mode) else "file"
    tree_hash, entry_count = _tree_identity(path)
    return {
        "path": str(path),
        "label": next(spec.label for spec in CACHE_SPECS if expand(spec.label) == path),
        "kind": kind,
        "device": info.st_dev,
        "inode": info.st_ino,
        "mtime_ns": info.st_mtime_ns,
        "reclaimable_kib": kib,
        "tree_metadata_sha256": tree_hash,
        "entry_count": entry_count,
    }


def inspect_caches() -> list[dict[str, Any]]:
    processes, sensor_error = process_snapshot()
    rows: list[dict[str, Any]] = []
    for spec in CACHE_SPECS:
        path = expand(spec.label)
        exists = path.exists() or path.is_symlink()
        kib = du_kib(path) if exists else 0
        owners = active_owners(spec, path, processes) if not sensor_error else []
        reason = "missing"
        identity: dict[str, object] | None = None
        if exists and not _under_home(path):
            reason = "outside-home"
        elif exists and sensor_error:
            reason = "sensor-unknown"
        elif exists and owners:
            reason = "active-process"
        elif exists and kib is None:
            reason = "size-unknown"
        elif exists:
            try:
                identity = _identity(path, int(kib))
            except (OSError, StopIteration):
                reason = "identity-unknown"
            else:
                reason = "candidate"
        rows.append(
            {
                "path": str(path),
                "label": spec.label,
                "exists": exists,
                "classification": reason,
                "active_pids": owners,
                "sensor_error": sensor_error,
                "reclaimable_kib": int(kib or 0),
                "reclaimable_size": fmt_bytes(int(kib or 0) * 1024),
                "identity": identity,
            }
        )
    return rows


def canonical_candidates(rows: Iterable[dict[str, Any]]) -> list[dict[str, object]]:
    candidates = [dict(row["identity"]) for row in rows if row.get("classification") == "candidate"]
    return sorted(candidates, key=lambda row: str(row["path"]))


def plan_sha256(candidates: Iterable[dict[str, object]]) -> str:
    payload = json.dumps(list(candidates), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def check_payload() -> dict[str, Any]:
    rows = inspect_caches()
    candidates = canonical_candidates(rows)
    reclaimable_kib = sum(int(row["reclaimable_kib"]) for row in candidates)
    return {
        "schema": "limen.reclaim_tool_caches.plan.v2",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "apply": False,
        "checked_paths": len(rows),
        "candidate_count": len(candidates),
        "blocked_count": sum(1 for row in rows if row["classification"] not in {"candidate", "missing"}),
        "total_reclaimable_kib": reclaimable_kib,
        "total_reclaimable_size": fmt_bytes(reclaimable_kib * 1024),
        "plan_sha256": plan_sha256(candidates),
        "candidates": candidates,
        "excluded_classes": list(EXCLUDED_CLASSES),
        "rows": rows,
    }


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    shutil.rmtree(path)


def apply_plan(expected_plan_sha: str) -> dict[str, Any]:
    checked = check_payload()
    actual_plan_sha = str(checked["plan_sha256"])
    if expected_plan_sha != actual_plan_sha:
        raise ValueError(f"candidate drift: expected {expected_plan_sha}, observed {actual_plan_sha}")

    verified: list[tuple[Path, dict[str, object]]] = []
    for candidate in checked["candidates"]:
        path = Path(str(candidate["path"]))
        # Verify every candidate before the first deletion, so known drift cannot
        # produce a partial apply. This also refuses symlink swaps.
        observed = _identity(path, int(candidate["reclaimable_kib"]))
        if observed != candidate:
            raise ValueError(f"candidate identity drift: {path}")
        verified.append((path, candidate))

    removed: list[dict[str, object]] = []
    for path, candidate in verified:
        remove_path(path)
        removed.append(candidate)

    reclaimed_kib = sum(int(row["reclaimable_kib"]) for row in removed)
    residual = check_payload()
    payload = {
        "schema": "limen.reclaim_tool_caches.apply.v2",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "apply": True,
        "expected_plan_sha256": expected_plan_sha,
        "applied_plan_sha256": actual_plan_sha,
        "removed_count": len(removed),
        "removed": removed,
        "total_reclaimed_kib": reclaimed_kib,
        "total_reclaimed_size": fmt_bytes(reclaimed_kib * 1024),
        "residual_plan_sha256": residual["plan_sha256"],
        "residual_candidate_count": residual["candidate_count"],
        "excluded_classes": list(EXCLUDED_CLASSES),
    }
    write_log(payload)
    return payload


def write_log(payload: dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _print_human(payload: dict[str, Any]) -> None:
    if payload["apply"]:
        print(f"reclaim-tool-caches [apply]: {payload['total_reclaimed_size']}; {payload['removed_count']} removed")
        return
    print(
        "reclaim-tool-caches [check]: "
        f"{payload['total_reclaimable_size']}; {payload['candidate_count']} candidates; "
        f"plan {payload['plan_sha256']}"
    )
    for row in payload["rows"]:
        if row["exists"]:
            print(f"  {row['reclaimable_size']:>10} {row['classification']:<16} {row['label']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Proof-gated cleanup of regenerable tool caches.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="emit the candidate plan (default)")
    mode.add_argument("--apply", action="store_true", help="apply an unchanged candidate plan")
    parser.add_argument(
        "--expected-plan-sha",
        help="required with --apply; exact plan_sha256 emitted by --check",
    )
    parser.add_argument("--json", action="store_true", help="print JSON")
    args = parser.parse_args(argv)

    if args.apply and not args.expected_plan_sha:
        parser.error("--apply requires --expected-plan-sha")
    if not args.apply and args.expected_plan_sha:
        parser.error("--expected-plan-sha is valid only with --apply")

    try:
        payload = apply_plan(args.expected_plan_sha) if args.apply else check_payload()
    except (OSError, ValueError) as exc:
        print(f"reclaim-tool-caches: BLOCKED: {exc}")
        return 2
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_human(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
