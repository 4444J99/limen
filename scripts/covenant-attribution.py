#!/usr/bin/env python3
"""covenant-attribution.py — attribution sensor for the Record-Keeper Covenant.

Proves every memory-dir write has a matching keeper receipt. Advisory severity;
fail-open when any expected resource is absent.

State file: logs/covenant-attribution-state.json (gitignored; hash + timestamp only).
Receipts:   <memdir>/.covenant-receipts.jsonl (written by cli/src/limen/memoria.py in a
            sibling PR — absent here is normal; this script is fail-open on all of that).

Verdict logic:
  first run (no state)    → record baseline, exit 0
  hash unchanged          → exit 0 (nothing moved)
  hash changed, receipt   → a keeper receipt covers the window → exit 0
  hash changed, no receipt→ a session wrote directly → advisory exit 1

Rewrite the state file on every run (even on violation) so each beat reports the
delta exactly once.

Usage:
  python3 scripts/covenant-attribution.py [--check]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))

# Standard memdir derivation (mirrors evocator.py exactly; LIMEN_MEMORY_DIR overrides it).
_WS = Path(os.environ.get("LIMEN_WORKDIR", Path.home() / "Workspace" / "limen")).expanduser()
_MEM_DEFAULT = Path.home() / ".claude" / "projects" / str(_WS).replace("/", "-") / "memory"
MEMDIR = Path(os.environ.get("LIMEN_MEMORY_DIR", _MEM_DEFAULT))

MEMORY_MD = MEMDIR / "MEMORY.md"
RECEIPTS_FILE = MEMDIR / ".covenant-receipts.jsonl"
STATE_FILE = ROOT / "logs" / "covenant-attribution-state.json"


def _sha256(path: Path) -> str:
    """SHA-256 of a file; returns hex of empty bytes when file is absent."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return hashlib.sha256(b"").hexdigest()


def _load_state() -> dict | None:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _save_state(sha: str, epoch: float) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps({"memory_md_sha256": sha, "checked_at_epoch": epoch}, indent=2),
        encoding="utf-8",
    )


def _latest_receipt_ts() -> float | None:
    """Return the maximum ts from .covenant-receipts.jsonl, or None when absent/empty/unreadable."""
    try:
        text = RECEIPTS_FILE.read_text(encoding="utf-8")
    except OSError:
        return None
    best: float | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            ts = float(obj.get("ts", 0))
            if best is None or ts > best:
                best = ts
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return best


def _mtime_changed_atoms(since_epoch: float) -> int:
    """Count files in memdir whose mtime is >= since_epoch (rough atom-change count)."""
    try:
        count = 0
        for p in MEMDIR.iterdir():
            try:
                if p.stat().st_mtime >= since_epoch:
                    count += 1
            except OSError:
                pass
        return count
    except OSError:
        return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="covenant attribution sensor")
    ap.add_argument("--check", action="store_true", help="same as default; explicit mode")
    ap.parse_args(argv)

    if not MEMDIR.exists():
        print("attribution: memdir absent — skip")
        return 0

    now = time.time()
    current_sha = _sha256(MEMORY_MD)
    state = _load_state()

    if state is None:
        # First run: record baseline, no verdict yet.
        _save_state(current_sha, now)
        print("attribution: baseline recorded — no prior state")
        return 0

    prev_sha: str = state.get("memory_md_sha256", "")
    prev_ts: float = float(state.get("checked_at_epoch", 0))

    if current_sha == prev_sha:
        # No change in MEMORY.md; re-stamp the checked_at so each beat is live.
        _save_state(current_sha, now)
        print("attribution: MEMORY.md unchanged — ok")
        return 0

    # MEMORY.md changed since last beat. Check whether a keeper receipt covers the window.
    latest_receipt = _latest_receipt_ts()
    has_receipt = latest_receipt is not None and latest_receipt >= prev_ts

    # Count changed atoms by mtime for the advisory line (filenames excluded — PII-clean).
    changed_atoms = _mtime_changed_atoms(prev_ts)

    # Always rewrite state so this delta reports only once per beat cycle.
    _save_state(current_sha, now)

    prev_prefix = prev_sha[:12]
    curr_prefix = current_sha[:12]

    if has_receipt:
        print(
            f"attribution: MEMORY.md changed ({prev_prefix}…→{curr_prefix}…), "
            f"keeper receipt covers window — ok"
        )
        return 0

    # Violation: hash changed with no covering receipt.
    print(
        f"attribution: VIOLATION — MEMORY.md changed ({prev_prefix}…→{curr_prefix}…) "
        f"with NO keeper receipt since prev beat (ts={prev_ts:.0f}); "
        f"~{changed_atoms} file(s) in memdir updated since prev beat — "
        f"a session wrote memory directly; route captures through the memoria lane (memory-ticket.py)"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
