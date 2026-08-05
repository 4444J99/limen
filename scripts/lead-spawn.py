#!/usr/bin/env python3
"""Spawn a domain-constrained battle worktree from inside a domain-lead capsule.

The lead/battle contract (the treaty architecture, 2026-07-24):

- A DOMAIN LEAD is an inhabitable capsule worktree pinned to one workstream
  channel. It plans; it never builds. Its one mutation is spawning battles.
- A BATTLE is a disposable capsule worktree spawned by a lead: it inherits the
  lead's workstream handle, receives a runway no longer than the lead's
  remaining runway, and is provider-agnostic (open it with any agent).
- Authority only attenuates downward: a battle can never carry a wider handle
  or a longer runway than the lead that spawned it.

This verb is a thin, deterministic wrapper over the canonical capsule minter
(scripts/start-worktree-session.sh) — it adds only the inheritance math and the
proliferation bound, both read from the parameter panel, never hardcoded:

- LIMEN_LEAD_BATTLE_RUNWAY  (default 8h)  — child runway when not requested
- LIMEN_LEAD_MAX_BATTLES    (default 3)   — max live battles per lead

Usage (from anywhere inside a lead worktree):
    python3 scripts/lead-spawn.py <battle-slug> --prompt-file <intent.md>
        [--runway 4h] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

RECEIPT_SCHEMA = "limen.workstream.receipt.v1"
_RUNWAY_RE = re.compile(r"^(\d+)([mhd])$")
_UNIT_SECONDS = {"m": 60, "h": 3600, "d": 86400}


class SpawnError(RuntimeError):
    """A fail-closed spawn refusal with one exact reason."""


def _param(name: str, default: str) -> str:
    """One parameter-panel read: env override wins, declared default otherwise."""
    value = os.environ.get(name, "").strip()
    return value or default


def parse_runway(text: str) -> int:
    match = _RUNWAY_RE.fullmatch(text.strip().lower())
    if not match:
        raise SpawnError(f"unparseable runway {text!r} (expected e.g. 45m, 8h, 7d)")
    return int(match.group(1)) * _UNIT_SECONDS[match.group(2)]


def format_runway(seconds: int) -> str:
    """Render seconds as the coarsest exact unit start-worktree-session.sh accepts."""
    if seconds <= 0:
        raise SpawnError("no runway remaining")
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds % size == 0 and seconds >= size:
            return f"{seconds // size}{unit}"
    return f"{max(1, seconds // 60)}m"


def find_lead_root(start: Path) -> Path:
    """Walk upward to the enclosing capsule worktree root."""
    node = start.resolve()
    for candidate in (node, *node.parents):
        if (candidate / ".limen-workstream" / "workstream.json").is_file():
            return candidate
    raise SpawnError(f"not inside a lead capsule (no .limen-workstream above {start})")


def read_receipt(root: Path) -> dict:
    """The tracked continuation receipt carries the capsule's workstream handle."""
    receipt_path = root / "docs" / "continuations" / root.name / "workstream.json"
    if not receipt_path.is_file():
        raise SpawnError(f"lead receipt missing: {receipt_path}")
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise SpawnError(f"unexpected receipt schema {receipt.get('schema')!r} in {receipt_path}")
    if not receipt.get("workstream"):
        raise SpawnError(f"lead receipt carries no workstream handle: {receipt_path}")
    return receipt


def remaining_runway_seconds(root: Path, now: float) -> int:
    contract = json.loads((root / ".limen-workstream" / "workstream.json").read_text())
    runway = contract.get("runway") or {}
    duration = int(runway.get("duration_seconds") or 0)
    if duration <= 0:
        raise SpawnError("lead contract carries no runway duration")
    deadline = runway.get("deadline_epoch")
    if deadline is None:
        return duration
    return max(0, int(float(deadline) - now))


def live_battles(repo_worktrees: Path, handle: str, lead_slug: str) -> list[str]:
    """Live battles of this lead: sibling capsule worktrees on the same handle."""
    battles: list[str] = []
    if not repo_worktrees.is_dir():
        return battles
    for tree in sorted(repo_worktrees.iterdir()):
        if tree.name == lead_slug or not tree.is_dir():
            continue
        receipt = tree / "docs" / "continuations" / tree.name / "workstream.json"
        try:
            if json.loads(receipt.read_text()).get("workstream") == handle:
                battles.append(tree.name)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
    return battles


def build_command(args: argparse.Namespace, *, now: float, cwd: Path) -> list[str]:
    lead_root = find_lead_root(cwd)
    receipt = read_receipt(lead_root)
    handle = str(receipt["workstream"])
    if not lead_root.name.startswith("lead-"):
        raise SpawnError(f"{lead_root.name} is not a lead capsule (leads are named lead-<handle>)")

    remaining = remaining_runway_seconds(lead_root, now)
    requested = parse_runway(args.runway or _param("LIMEN_LEAD_BATTLE_RUNWAY", "8h"))
    child_seconds = min(requested, remaining)
    if child_seconds <= 0:
        raise SpawnError("lead runway exhausted — emit a successor instead of spawning")

    max_battles = int(_param("LIMEN_LEAD_MAX_BATTLES", "3"))
    repo_root = lead_root.parent.parent  # <repo>/.worktrees/<lead-slug>
    open_battles = live_battles(lead_root.parent, handle, lead_root.name)
    if len(open_battles) >= max_battles:
        raise SpawnError(
            f"battle cap reached ({len(open_battles)}/{max_battles} live on {handle!r}: "
            f"{', '.join(open_battles)}) — close or reap one first"
        )

    minter = repo_root / "scripts" / "start-worktree-session.sh"
    if not minter.is_file():
        raise SpawnError(f"canonical minter missing: {minter}")
    prompt_file = Path(args.prompt_file).resolve()
    if not prompt_file.is_file():
        raise SpawnError(f"battle intent file missing: {prompt_file}")

    return [
        "bash",
        str(minter),
        "--runway",
        format_runway(child_seconds),
        "--workstream",
        handle,
        "--prompt-file",
        str(prompt_file),
        "limen",
        args.slug,
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug", help="battle worktree slug (one bounded objective)")
    parser.add_argument("--prompt-file", required=True, help="battle intent (becomes intent.md)")
    parser.add_argument("--runway", default=None, help="child runway request (clamped to lead remaining)")
    parser.add_argument("--dry-run", action="store_true", help="print the spawn command without running it")
    args = parser.parse_args(argv)

    try:
        command = build_command(args, now=time.time(), cwd=Path.cwd())
    except SpawnError as exc:
        print(f"lead-spawn: {exc}", file=sys.stderr)
        return 1
    print(" ".join(command))
    if args.dry_run:
        return 0
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
