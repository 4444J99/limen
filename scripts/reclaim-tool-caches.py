#!/usr/bin/env python3
"""Reclaim package/tool caches from the local user profile.

This excludes agent state, model stores, private corpora, messages, mail, photos,
and scratch/worktree roots. The allowlist is limited to dependency-manager and
browser-automation caches that can be regenerated.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any


HOME = Path(os.environ.get("HOME", "/Users/4jp")).expanduser()
ROOT = Path(os.environ.get("LIMEN_ROOT", HOME / "Workspace" / "limen")).expanduser()
LOG_PATH = ROOT / "logs" / "reclaim-tool-caches.jsonl"

CACHE_PATHS = (
    "~/.cache/npm",
    "~/.cache/pnpm",
    "~/.cache/pre-commit",
    "~/.cache/puppeteer",
    "~/.cache/uv",
    "~/.npm/_cacache",
    "~/.pytest_cache",
    "~/.local/share/pnpm/store",
    "~/Library/Caches/ms-playwright",
    "~/Library/Caches/ms-playwright-go",
    "~/Library/Caches/node-gyp",
    "~/Library/Caches/pip",
    "~/Library/Caches/pip-audit",
    "~/Library/Caches/pnpm",
    "~/Library/Caches/prisma-nodejs",
    "~/Library/Caches/pylint",
    "~/Library/Caches/virtualenv",
)


def expand(path: str) -> Path:
    return Path(path.replace("~", str(HOME), 1)).expanduser()


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


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    shutil.rmtree(path)


def cache_rows(*, apply: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in CACHE_PATHS:
        path = expand(raw)
        before = du_kib(path)
        exists = path.exists()
        error = ""
        if apply and exists:
            try:
                remove_path(path)
            except OSError as exc:
                error = str(exc)
        after = du_kib(path) if apply else before
        reclaimed = max((before or 0) - (after or 0), 0) if apply else 0
        rows.append(
            {
                "path": str(path),
                "label": raw,
                "exists": exists,
                "ok": not error,
                "error": error,
                "reclaimable_kib": before or 0,
                "reclaimable_size": fmt_bytes((before or 0) * 1024),
                "reclaimed_kib": reclaimed,
                "reclaimed_size": fmt_bytes(reclaimed * 1024),
            }
        )
    return rows


def write_log(payload: dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean regenerable package/tool caches.")
    parser.add_argument("--apply", action="store_true", help="perform cleanup; default is dry-run")
    parser.add_argument("--json", action="store_true", help="print JSON")
    args = parser.parse_args()

    started = time.time()
    rows = cache_rows(apply=args.apply)
    failed = [row for row in rows if not row["ok"]]
    reclaimable_kib = sum(int(row["reclaimable_kib"]) for row in rows)
    reclaimed_kib = sum(int(row["reclaimed_kib"]) for row in rows)
    payload = {
        "schema": "limen.reclaim_tool_caches.v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "apply": args.apply,
        "checked_paths": len(rows),
        "existing_paths": sum(1 for row in rows if row["exists"]),
        "failed_paths": len(failed),
        "total_reclaimable_kib": reclaimable_kib,
        "total_reclaimable_size": fmt_bytes(reclaimable_kib * 1024),
        "total_reclaimed_kib": reclaimed_kib,
        "total_reclaimed_size": fmt_bytes(reclaimed_kib * 1024),
        "duration_sec": round(time.time() - started, 2),
        "excluded_classes": [
            "agent-state",
            "agy-scratch",
            "gemini-brain",
            "ollama-models",
            "opencode-snapshots",
            "private-corpus",
            "mail-messages-photos",
        ],
        "rows": rows,
    }
    if args.apply:
        write_log(payload)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        mode = "apply" if args.apply else "dry-run"
        size = payload["total_reclaimed_size"] if args.apply else payload["total_reclaimable_size"]
        print(f"reclaim-tool-caches [{mode}]: {size}; {len(failed)} failed")
        for row in rows:
            if row["reclaimable_kib"]:
                print(f"  {row['reclaimable_size']:>10} {row['label']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
