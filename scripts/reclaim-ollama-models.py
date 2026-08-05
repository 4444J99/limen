#!/usr/bin/env python3
"""Reclaim pulled Ollama models when the local floor is not armed.

Ollama models are regenerable cache, but they are also the local-floor substrate.
This script refuses to remove them when LIMEN_LOCAL_FLOOR=1 or when `ollama ps`
shows a loaded model.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


HOME = Path(os.environ.get("HOME", "/Users/4jp")).expanduser()
ROOT = Path(os.environ.get("LIMEN_ROOT", HOME / "Workspace" / "limen")).expanduser()
OLLAMA_ROOT = Path(os.environ.get("OLLAMA_MODELS_ROOT", HOME / ".ollama" / "models")).expanduser()
LOG_PATH = ROOT / "logs" / "reclaim-ollama-models.jsonl"


def run(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)
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


def parse_ollama_list(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in text.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        rows.append({"name": parts[0], "id": parts[1], "size": " ".join(parts[2:4]) if len(parts) >= 4 else parts[2]})
    return rows


def loaded_models(text: str) -> list[str]:
    names: list[str] = []
    for line in text.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        names.append(line.split()[0])
    return names


def write_log(payload: dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove pulled Ollama models when local floor is dark.")
    parser.add_argument("--apply", action="store_true", help="remove models; default is dry-run")
    parser.add_argument("--json", action="store_true", help="print JSON")
    args = parser.parse_args()

    before_kib = du_kib(OLLAMA_ROOT)
    list_result = run(["ollama", "list"])
    ps_result = run(["ollama", "ps"])
    models = parse_ollama_list(list_result.stdout if list_result.returncode == 0 else "")
    loaded = loaded_models(ps_result.stdout if ps_result.returncode == 0 else "")
    floor_armed = os.environ.get("LIMEN_LOCAL_FLOOR", "0").strip() == "1"
    blocked_reason = ""
    removed: list[dict[str, str]] = []
    failed: list[dict[str, str]] = []
    if floor_armed:
        blocked_reason = "local-floor-armed"
    elif loaded:
        blocked_reason = "ollama-model-loaded"
    elif args.apply:
        for model in models:
            proc = run(["ollama", "rm", model["name"]], timeout=120)
            row = {"name": model["name"], "detail": (proc.stderr or proc.stdout or "").strip()[:300]}
            if proc.returncode == 0:
                removed.append(row)
            else:
                failed.append(row)
    after_kib = du_kib(OLLAMA_ROOT) if args.apply else before_kib
    reclaimed_kib = max((before_kib or 0) - (after_kib or 0), 0) if args.apply else 0
    payload = {
        "schema": "limen.reclaim_ollama_models.v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "apply": args.apply,
        "floor_armed": floor_armed,
        "blocked_reason": blocked_reason,
        "loaded_models": loaded,
        "model_count": len(models),
        "models": models,
        "removed": removed,
        "failed": failed,
        "before_kib": before_kib or 0,
        "after_kib": after_kib or 0,
        "reclaimable_size": fmt_bytes((before_kib or 0) * 1024),
        "reclaimed_kib": reclaimed_kib,
        "reclaimed_size": fmt_bytes(reclaimed_kib * 1024),
        "total_reclaimed_kib": reclaimed_kib,
        "total_reclaimed_size": fmt_bytes(reclaimed_kib * 1024),
    }
    if args.apply:
        write_log(payload)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        mode = "apply" if args.apply else "dry-run"
        print(f"reclaim-ollama-models [{mode}]: {payload['reclaimed_size']} reclaimed; blocker={blocked_reason or 'none'}")
        for model in models:
            print(f"  {model['name']} {model['size']}")
    return 1 if failed or blocked_reason else 0


if __name__ == "__main__":
    raise SystemExit(main())
