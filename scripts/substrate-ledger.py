#!/usr/bin/env python3
"""Classify dynamic local substrates used by Limen.

Dry-run by default. With --write, this records a private JSON receipt and a
tracked redacted summary. Missing configured roots are receipts, not global
blockers, unless a caller makes them required in its own gate.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "substrate-ledger.json"
DOC_PATH = ROOT / "docs" / "substrate-ledger.md"
CONFIG_PATH = Path(os.environ.get("LIMEN_SUBSTRATE_CONFIG", ROOT / ".limen-private" / "substrate-roots.json"))

ENV_ROOTS = {
    "storage_roots": "LIMEN_STORAGE_ROOTS",
    "repo_roots": "LIMEN_REPO_ROOTS",
    "prompt_sources": "LIMEN_PROMPT_SOURCES",
    "archive_targets": "LIMEN_ARCHIVE_TARGETS",
}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def stable_display(path: Path) -> str:
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        resolved = path.expanduser().absolute()
    try:
        return "~/" + str(resolved.relative_to(HOME))
    except ValueError:
        return str(resolved)


def split_paths(value: str | None) -> list[Path]:
    if not value:
        return []
    parts: list[str] = []
    for chunk in value.split(os.pathsep):
        parts.extend(item.strip() for item in chunk.split(","))
    return [Path(item).expanduser() for item in parts if item]


def load_private_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return obj if isinstance(obj, dict) else {}


def mounted_volumes() -> list[Path]:
    volumes = Path("/Volumes")
    if not volumes.exists():
        return []
    try:
        return sorted(path for path in volumes.iterdir() if path.exists())
    except OSError:
        return []


def default_roots() -> list[tuple[str, str, Path]]:
    return [
        ("repo-default", "limen-root", ROOT),
        ("repo-default", "workspace", HOME / "Workspace"),
        ("repo-default", "workspace-parent", ROOT.parent),
        ("prompt-default", "codex-sessions", HOME / ".codex" / "sessions"),
        ("prompt-default", "codex-history", HOME / ".codex" / "history.jsonl"),
        ("prompt-default", "claude-projects", HOME / ".claude" / "projects"),
        ("private-default", "private-session-corpus", PRIVATE_ROOT),
    ]


def configured_roots(config: dict[str, Any]) -> list[tuple[str, str, Path]]:
    rows: list[tuple[str, str, Path]] = []
    for key, env_key in ENV_ROOTS.items():
        for path in split_paths(os.environ.get(env_key)):
            rows.append((f"env:{key}", env_key, path))
        values = config.get(key) or []
        if isinstance(values, str):
            values = [values]
        if isinstance(values, list):
            for value in values:
                if isinstance(value, str) and value.strip():
                    rows.append((f"private-config:{key}", CONFIG_PATH.name, Path(value).expanduser()))
    return rows


def root_key(path: Path) -> str:
    try:
        return str(path.expanduser().resolve())
    except OSError:
        return str(path.expanduser().absolute())


def classify_path(path: Path, *, free_floor_gib: float, usage_ceiling_pct: float) -> dict[str, Any]:
    exists = path.exists()
    detail = "missing"
    status = "missing"
    free_gib = None
    usage_pct = None
    read_ok = False
    write_ok = False
    if exists:
        read_ok = os.access(path, os.R_OK)
        write_ok = os.access(path, os.W_OK)
        probe = path if path.is_dir() else path.parent
        try:
            usage = shutil.disk_usage(probe)
            free_gib = round(usage.free / (1024**3), 2)
            usage_pct = round((usage.used / usage.total) * 100, 1) if usage.total else None
        except OSError:
            pass
        if not read_ok:
            status = "unreadable"
            detail = "exists but is not readable"
        elif not write_ok:
            status = "read_only"
            detail = "exists but is not writable"
        elif free_gib is not None and free_gib < free_floor_gib:
            status = "full"
            detail = f"free {free_gib} GiB below {free_floor_gib} GiB floor"
        elif usage_pct is not None and usage_pct > usage_ceiling_pct:
            status = "full"
            detail = f"usage {usage_pct}% above {usage_ceiling_pct}% ceiling"
        else:
            status = "active"
            detail = "exists and is usable"
    return {
        "path": str(path.expanduser()),
        "display_path": stable_display(path),
        "exists": exists,
        "is_dir": path.is_dir() if exists else False,
        "status": status,
        "detail": detail,
        "readable": read_ok,
        "writable": write_ok,
        "free_gib": free_gib,
        "usage_pct": usage_pct,
    }


def build_snapshot(
    *,
    config_path: Path = CONFIG_PATH,
    include_mounted: bool = True,
    free_floor_gib: float = 10.0,
    usage_ceiling_pct: float = 95.0,
) -> dict[str, Any]:
    config = load_private_config(config_path)
    candidates = configured_roots(config)
    candidates.extend(default_roots())
    if include_mounted:
        candidates.extend(("mounted-volume", "mounted-discovery", path) for path in mounted_volumes())

    by_key: dict[str, dict[str, Any]] = {}
    for source, label, path in candidates:
        key = root_key(path)
        if key not in by_key:
            row = classify_path(path, free_floor_gib=free_floor_gib, usage_ceiling_pct=usage_ceiling_pct)
            row.update({"sources": [], "labels": []})
            by_key[key] = row
        by_key[key]["sources"].append(source)
        by_key[key]["labels"].append(label)

    roots = sorted(by_key.values(), key=lambda row: (row["status"] != "active", row["display_path"]))
    counts = Counter(str(row["status"]) for row in roots)
    return {
        "generated_at": now_iso(),
        "config_path": str(config_path),
        "env_keys": ENV_ROOTS,
        "counts": dict(sorted(counts.items())),
        "roots": roots,
        "status": "ready" if any(row["status"] == "active" for row in roots) else "blocked",
    }


def render_markdown(snapshot: dict[str, Any]) -> str:
    lines = [
        "# Substrate Ledger",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        f"Status: `{snapshot['status']}`",
        "",
        "## Counts",
        "",
    ]
    for key, value in snapshot["counts"].items():
        lines.append(f"- `{key}`: {value}")
    lines += [
        "",
        "## Roots",
        "",
        "| Root | Status | Sources | Detail |",
        "|---|---|---|---|",
    ]
    for row in snapshot["roots"]:
        sources = ", ".join(f"`{source}`" for source in row["sources"])
        detail = str(row["detail"]).replace("|", "\\|")
        lines.append(f"| `{row['display_path']}` | `{row['status']}` | {sources} | {detail} |")
    lines += [
        "",
        "## Contract",
        "",
        "- Configured roots are classified with receipts; stale or missing roots do not become global blockers by name.",
        "- Raw prompt bodies and private indexes stay under `.limen-private/`.",
    ]
    return "\n".join(lines) + "\n"


def write_outputs(snapshot: dict[str, Any], markdown: str) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(markdown, encoding="utf-8")
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh the dynamic substrate ledger.")
    parser.add_argument("--refresh", action="store_true", help="accepted for operator symmetry")
    parser.add_argument("--write", action="store_true", help="write tracked summary and private index")
    parser.add_argument("--no-mounted", action="store_true", help="skip /Volumes discovery")
    parser.add_argument("--free-floor-gib", type=float, default=float(os.environ.get("LIMEN_STORAGE_FREE_FLOOR_GIB", "10")))
    parser.add_argument(
        "--usage-ceiling-pct",
        type=float,
        default=float(os.environ.get("LIMEN_STORAGE_USAGE_CEILING_PCT", "95")),
    )
    args = parser.parse_args()
    snapshot = build_snapshot(
        include_mounted=not args.no_mounted,
        free_floor_gib=args.free_floor_gib,
        usage_ceiling_pct=args.usage_ceiling_pct,
    )
    markdown = render_markdown(snapshot)
    if args.write:
        write_outputs(snapshot, markdown)
        print(f"substrate-ledger: {snapshot['status']}; wrote {DOC_PATH} and {PRIVATE_INDEX}")
    else:
        print(markdown, end="")
        print(f"substrate-ledger: {snapshot['status']}; dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
