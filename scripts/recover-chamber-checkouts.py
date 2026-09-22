#!/usr/bin/env python3
"""Apply a reviewed chamber inventory through the existing retirement lifecycle.

No refs, dirty files, ignored payloads, standalone clones, or active checkouts are
removed. A frozen exact head and live remote ancestry proof are mandatory.
"""

from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli" / "src"))
from limen.worktree_abandonment import detach_registered_worktree
from _worktree_liveness import active_process_cwds, owner_in


def git(path, *args):
    result = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError("git-proof-unavailable")
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--receipt-root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    rows = json.loads(args.manifest.read_text())
    retired = []
    retained = []
    absent = 0
    recovered = 0
    authority = Path.home() / "Workspace" / "chamber_worktrees"
    remote_cache = {}
    for row in rows:
        if row.get("disposition") != "eligible-disposable-copy-refs-retained":
            continue
        target = Path(row["path"])
        if not target.exists():
            absent += 1
            continue
        try:
            if authority not in target.parents or not (target / ".git").is_file() or target.is_symlink():
                raise RuntimeError("outside-linked-chamber-scope")
            if git(target, "rev-parse", "HEAD") != row["head"]:
                raise RuntimeError("head-advanced")
            if git(target, "status", "--porcelain=v1", "--untracked-files=all"):
                raise RuntimeError("dirty")
            if git(target, "ls-files", "--others", "--ignored", "--exclude-standard"):
                raise RuntimeError("ignored-payload")
            if git(target, "remote", "get-url", "origin") != row["remote"]:
                raise RuntimeError("remote-changed")
            if row["remote"] not in remote_cache:
                raw = git(target, "ls-remote", "--heads", "origin")
                remote_cache[row["remote"]] = dict(line.split()[::-1] for line in raw.splitlines())
            proof = next(
                (p for p in row["remote_proof"] if remote_cache[row["remote"]].get(p["ref"]) == p["tip"]), None
            )
            if not proof:
                raise RuntimeError("remote-tip-changed")
            git(target, "merge-base", "--is-ancestor", row["head"], proof["tip"])
            if owner_in(active_process_cwds(), target) is not None:
                raise RuntimeError("active-or-owner-unmeasured")
            size = sum(p.lstat().st_blocks * 512 for p in target.rglob("*") if p.is_file() or p.is_symlink())
            if args.apply:
                superproject = Path(row["common"]).parent
                receipt = detach_registered_worktree(
                    superproject,
                    target,
                    reason="user-authorized recovery: disposable copy; exact head remotely recoverable; refs retained",
                    receipt_root=args.receipt_root,
                )
                retired.append(
                    {
                        "path_sha256": hashlib.sha256(str(target).encode()).hexdigest(),
                        "head": row["head"],
                        "remote": row["remote"],
                        "proof": proof,
                        "allocated_bytes": size,
                        "state": receipt["state"],
                    }
                )
                recovered += size
        except Exception as exc:
            retained.append({"path_sha256": hashlib.sha256(str(target).encode()).hexdigest(), "reason": str(exc)[:160]})
    result = {
        "retired": retired,
        "retained": retained,
        "already_absent": absent,
        "allocated_bytes_removed": recovered,
        "refs_deleted": 0,
    }
    if args.apply and retired:
        args.receipt_root.mkdir(parents=True, exist_ok=True)
        path = args.receipt_root / (
            "batch-" + hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16] + ".json"
        )
        path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 1 if retained else 0


if __name__ == "__main__":
    raise SystemExit(main())
