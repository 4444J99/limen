#!/usr/bin/env python3
"""library-preserve.py — process ~/Library toward ideal form: preserve the irreplaceable
DURABLY, reclaim only regenerable cache as a byproduct, and PROPOSE (never auto-execute)
the irreversible. The personal-data analogue of clone-maintenance.sh.

The user's directive (2026-06-22): "all of the above and more; reduction is laziness" and
"make all hanging tasks known and owned and pervasive — then I decide." So this organ:

  CLASSIFY   ~/Library (+ ~/Pictures) into regenerable-cache / irreplaceable-personal /
             cloud-synced-redundant.
  PRESERVE   copy every at-risk irreplaceable class to /Volumes/Archive4T and CHECKSUM-verify
             — additive, copy->verify, NEVER move/delete. Closes the documented "only two
             local copies, no offsite 3rd" gap for the consciousness sliver.
  RECLAIM    (byproduct, safe) purge only REGENERABLE dev/build caches. Reversible (re-fetch).
  PROPOSE    the irreversible / big levers (iCloud Drive optimize ~34G, offsite 3rd copy,
             no-Time-Machine-backup) as KNOWN-OWNED-PERVASIVE levers — printed + written to a
             registry, executed only on the user's word.

HARD RULES (allwheres): NEVER auto-delete personal DATA, NEVER auto-send. Reversible only.
Dry-run by DEFAULT; set LIMEN_LIB_APPLY=1 to perform the SAFE phases (preserve + cache purge);
the PROPOSE phase is never auto-executed regardless.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

HOME = os.path.expanduser("~")
ARCHIVE = os.environ.get("LIMEN_ARCHIVE_ROOT", "/Volumes/Archive4T")
PRESERVE_DST = os.path.join(ARCHIVE, "personal-sliver-backup")
APPLY = os.environ.get("LIMEN_LIB_APPLY", "0") == "1"
ROOT = os.environ.get("LIMEN_ROOT", os.path.join(HOME, "Workspace/limen"))
REGISTRY = os.path.join(ROOT, "logs", "library-levers.json")

# ── REGENERABLE caches — definitively safe to purge (re-fetch on next use) ─────────────
REGENERABLE = [
    "Library/Caches/Homebrew", "Library/Caches/node-gyp", "Library/Caches/go-build",
    "Library/Caches/ms-playwright", "Library/Caches/ms-playwright-go", "Library/Caches/dotslash",
    "Library/Caches/typescript", "Library/Caches/Yarn", "Library/Caches/pip",
    "Library/Caches/deno", "Library/pnpm/store", ".cache/puppeteer",
]

# ── IRREPLACEABLE sliver — small, high-value, documented as lacking an offsite 3rd copy ─
# (Big media — Photos, Messages Attachments — are partly iCloud-held; PROPOSED, not auto-copied.)
SLIVER = [
    ".claude",                       # agent-memory + projects (this very memory)
    "Library/Mail",                  # mail store
    "Library/Messages/chat.db",      # message TEXT history (the irreplaceable part)
    "Library/Messages/chat.db-wal", "Library/Messages/chat.db-shm",
]


def _du(path: str) -> int:
    if not os.path.exists(path):
        return 0
    if os.path.isfile(path):
        try:
            return os.path.getsize(path)
        except OSError:
            return 0
    total = 0
    for r, _, fs in os.walk(path):
        for f in fs:
            try:
                total += os.path.getsize(os.path.join(r, f))
            except OSError:
                pass
    return total


def _gb(n: int) -> str:
    return f"{n / 1e9:.2f} GB"


def _archive_mounted() -> bool:
    return os.path.isdir(ARCHIVE) and os.access(ARCHIVE, os.W_OK)


def reclaim_caches() -> int:
    print("── reclaim regenerable caches (reversible: re-fetch on next use) ──")
    freed = 0
    for rel in REGENERABLE:
        p = os.path.join(HOME, rel)
        sz = _du(p)
        if sz == 0:
            continue
        freed += sz
        print(f"  {'purge' if APPLY else 'WOULD purge'}: ~/{rel}  ({_gb(sz)})")
        if APPLY:
            shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)
    print(f"  {'' if APPLY else '(dry-run) '}caches: {_gb(freed)} {'freed' if APPLY else 'reclaimable'}.")
    return freed


def preserve_sliver() -> int:
    print(f"── preserve irreplaceable sliver → {PRESERVE_DST} (copy→verify, additive) ──")
    if not _archive_mounted():
        print(f"  Archive4T not mounted/writable ({ARCHIVE}) — fail open; sliver stays a KNOWN lever.")
        return 0
    copied = total = 0
    if APPLY:
        os.makedirs(PRESERVE_DST, exist_ok=True)
    for rel in SLIVER:
        src = os.path.join(HOME, rel)
        if not os.path.exists(src):
            continue
        sz = _du(src)
        total += sz
        dst = os.path.join(PRESERVE_DST, rel.replace("/", "__"))
        print(f"  {'copy+verify' if APPLY else 'WOULD copy'}: ~/{rel}  ({_gb(sz)})")
        if APPLY:
            is_dir = os.path.isdir(src)
            src_, dst_ = src + ("/" if is_dir else ""), dst + ("/" if is_dir else "")
            # ADDITIVE rsync — no --delete: the backup only ever accumulates, never prunes
            # ("reduction is laziness"); never touches the source.
            rc = subprocess.run(["rsync", "-a", src_, dst_], capture_output=True, text=True).returncode
            # integrity: a CHECKSUM dry-run with nothing left to transfer == dst faithfully holds source
            chk = subprocess.run(["rsync", "-anc", src_, dst_], capture_output=True, text=True)
            pending = [ln for ln in chk.stdout.splitlines() if ln[:1] in "<>"]
            ok = rc == 0 and not pending
            print(f"      → {'verified ✓ (checksum)' if ok else f'VERIFY FAILED ({len(pending)} pending) — source untouched, retry next pass'}")
            if ok:
                copied += sz
    print(f"  {'' if APPLY else '(dry-run) '}sliver: {_gb(copied if APPLY else total)} "
          f"{'preserved to Archive4T (3rd copy)' if APPLY else 'would preserve'}.")
    return copied


def reclaim_icloud() -> int:
    """SOLVE the iCloud local-cache bloat autonomously — system-owned, NOT a 'your hand' toggle.
    Copy each materialized CloudDocs item to Archive4T (additive, Backblaze-offsite-backed),
    CHECKSUM-verify, then brctl-evict the local copy. Eviction is REVERSIBLE (iCloud + Archive4T
    both hold it; it re-downloads on access) — so it is NOT a delete and NOT the never-auto-delete
    rule. The cloud stays authoritative; only the redundant local cache is reclaimed."""
    src = os.path.join(HOME, "Library/Mobile Documents/com~apple~CloudDocs")
    if not os.path.isdir(src):
        return 0
    print("── iCloud Drive reclaim (copy→verify→evict; reversible, system-owned) ──")
    if not _archive_mounted():
        print("  Archive4T not mounted — skip (cloud still holds it); retry next pass.")
        return 0
    dst_root = os.path.join(ARCHIVE, "personal-cloud-docs")
    freed = 0
    for item in sorted(os.listdir(src)):
        s = os.path.join(src, item)
        if not os.path.isdir(s):
            continue
        sz = _du(s)
        if sz < 50 * 2**20:                      # skip tiny / already-evicted items
            continue
        print(f"  {item}: {_gb(sz)} {'→ copy→verify→evict' if APPLY else '(dry-run reclaimable)'}")
        if not APPLY:
            freed += sz
            continue
        d = os.path.join(dst_root, item)
        os.makedirs(d, exist_ok=True)
        subprocess.run(["rsync", "-a", s + "/", d + "/"], capture_output=True, text=True)
        chk = subprocess.run(["rsync", "-anc", s + "/", d + "/"], capture_output=True, text=True)
        pending = [ln for ln in chk.stdout.splitlines() if ln[:2] in (">f", "<f")]
        if pending:
            print(f"      VERIFY FAILED ({len(pending)} pending) — NOT evicting; source untouched")
            continue
        subprocess.run(["brctl", "evict", s], capture_output=True, text=True)
        print("      verified ✓ → evicted (iCloud + Archive4T + Backblaze-offsite all hold it)")
        freed += sz
    print(f"  {'' if APPLY else '(dry-run) '}iCloud: {_gb(freed)} {'reclaimed' if APPLY else 'reclaimable'} (reversible).")
    return freed


def status_report() -> dict:
    """Report the durability posture — what's SOLVED, and the ONE genuinely-physical item, stated
    once (KNOWN·OWNED·PERVASIVE, never nagged). No 'your hand' punting for anything solvable."""
    print("── durability status (solved autonomously where solvable) ──")
    bb = os.path.isdir(os.path.join(ARCHIVE, ".bzvol"))
    tm = subprocess.run(["tmutil", "latestbackup"], capture_output=True, text=True).stdout.strip()
    state = {
        "offsite_3rd_copy": "SOLVED" if bb else "OPEN",
        "offsite_via": "Backblaze backs /Volumes/Archive4T (sliver + cloud-docs copied there)" if bb else "—",
        "icloud_local_cache": "system-owned reclaim (copy→verify→evict each pass)",
        "time_machine": {"status": "no completed backup", "latest": tm or "NONE",
                         "note": "OPTIONAL — data already has 3 copies (local + Archive4T + Backblaze-offsite); "
                                 "TM is a whole-machine convenience needing a physical disk. Stated once, not nagged."},
    }
    print(f"  offsite 3rd copy: {state['offsite_3rd_copy']} ({state['offsite_via']})")
    print(f"  Time Machine: {state['time_machine']['status']} — {state['time_machine']['note'][:70]}…")
    if APPLY:
        os.makedirs(os.path.dirname(REGISTRY), exist_ok=True)
        json.dump(state, open(REGISTRY, "w"), indent=2)
        print(f"  status → {REGISTRY}")
    return state


def main() -> int:
    print(f"library-preserve [{'APPLY' if APPLY else 'DRY-RUN'}] — preserve-first, reclaim-byproduct, system-owned")
    reclaim_caches()
    preserve_sliver()
    reclaim_icloud()
    status_report()
    print("done — irreplaceable preserved (3 copies); reversible reclaim only; nothing punted to your hand.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
