#!/usr/bin/env python3
"""Runtime-lag predicate — does the RUNNING host carry merged main?

The beat already senses whether its lanes are alive (`sensor-canary`: a scheduled sensor
that never ran, or ran too long ago). It has never sensed whether a live lane is running
CURRENT CODE. Those are different failures, and the second one is invisible from inside the
first: a five-day-stale runtime install stamps its voice files on time, passes its canary,
and reports green the whole while executing week-old code.

This is the merge→host latency, and it is the same shape as the defect that produced it one
level down. `_notify.py` grew an in-tree gate; the gate only reached copies that had rebased,
because the effector (`osascript`) is a host singleton while the guard is tree-local. One
level up, the *install* is how merged main reaches the host at all — and nothing measured it.
When that was finally measured by hand it came back 88 commits and 5 days behind, which meant
the notify gate had been merged and shipped and was still not running anywhere on this host.

So: a fix is not deployed when it is merged. It is deployed when the thing that runs it is
rebuilt. Every future host-global fix inherits this latency, which is why this measures the
general condition rather than re-checking notify.

What it reads (never guesses):
  ~/.local/share/limen/current -> runtimes/<sha>, whose receipt.json is the authoritative
  record (schema domus-limen-runtime-receipt.v1: sha, installed_at, repository,
  default_branch). The symlink basename is the fallback when the receipt is unreadable.

Healing is NOT ours. The rotator lives in domus (`domus-limen-runtime install --sha …`) and
repoints a symlink underneath a daemon that executes from it every 300s. limen's authority
here ends at sensing, so this names the owner and the exact command and stops.

Exit 0 ⟺ no install on this host (dev box / CI / container), or the install is within bound,
         or the lag could not be measured (said out loud, never silently).
Exit 1 ⟺ the running runtime is further behind the default branch than the declared bound.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALL_CURRENT = Path.home() / ".local" / "share" / "limen" / "current"
DEFAULT_MAX_COMMITS = 25
ROTATOR = "domus-limen-runtime install --sha {sha}"


def _git(*args: str) -> tuple[int, str]:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    return out.returncode, out.stdout.strip()


def read_receipt(install: Path = INSTALL_CURRENT) -> dict | None:
    """The install's own account of itself. None ⇒ no install on this host.

    A malformed or missing receipt is NOT treated as "no install": the symlink still points at
    a runtime that launchd is executing, and reporting absence there would turn a measurable
    staleness into a silent pass — the exact failure mode this file exists to close.
    """
    if not install.exists():
        return None
    receipt = install / "receipt.json"
    try:
        data = json.loads(receipt.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("sha"):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    # Fallback: runtimes/<sha> — the layout the rotator builds.
    try:
        return {"sha": install.resolve().name, "degraded": "receipt unreadable; sha from symlink"}
    except OSError:
        return None


def install_age_days(receipt: dict) -> float | None:
    stamp = receipt.get("installed_at")
    if not stamp:
        return None
    try:
        when = datetime.fromisoformat(str(stamp))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - when).total_seconds() / 86400.0


def measure(receipt: dict) -> dict:
    """Commits the running runtime is behind the default branch.

    `unmeasurable` is a first-class outcome, not an error: a shallow clone, an unfetched
    branch, or a runtime built from a ref this checkout has never seen all mean "I do not
    know", which must never render as "I checked and it is fine".
    """
    sha = str(receipt.get("sha") or "")
    branch = str(receipt.get("default_branch") or "main")
    ref = f"origin/{branch}"
    result: dict = {"sha": sha, "ref": ref, "age_days": install_age_days(receipt)}

    if _git("cat-file", "-e", f"{sha}^{{commit}}")[0] != 0:
        result["unmeasurable"] = f"{sha[:12]} is not a commit in this clone (unfetched or rewritten)"
        return result
    if _git("rev-parse", "--verify", "--quiet", ref)[0] != 0:
        result["unmeasurable"] = f"{ref} is not present in this clone"
        return result

    result["is_ancestor"] = _git("merge-base", "--is-ancestor", sha, ref)[0] == 0
    code, count = _git("rev-list", "--count", f"{sha}..{ref}")
    if code != 0 or not count.isdigit():
        result["unmeasurable"] = f"could not count {sha[:12]}..{ref}"
        return result
    result["behind"] = int(count)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--max-commits",
        type=int,
        default=int(os.environ.get("LIMEN_RUNTIME_LAG_MAX_COMMITS") or DEFAULT_MAX_COMMITS),
        help="commits behind the default branch before this is a finding",
    )
    parser.add_argument("--json", action="store_true", help="emit the measurement as JSON")
    args = parser.parse_args()

    receipt = read_receipt()
    if receipt is None:
        # The overwhelmingly common case in CI and on any machine that is not his: there is
        # no scheduled runtime to be stale. Silence here is correct, not a skipped check.
        if args.json:
            print(json.dumps({"installed": False}))
        else:
            print("runtime-lag: no limen runtime install on this host — nothing schedules stale code here")
        return 0

    m = measure(receipt)
    if args.json:
        print(json.dumps({"installed": True, "max_commits": args.max_commits, **m}))

    age = m.get("age_days")
    age_text = f"{age:.1f}d old" if age is not None else "install date unknown"
    if receipt.get("degraded") and not args.json:
        print(f"runtime-lag: DEGRADED — {receipt['degraded']}")

    if "unmeasurable" in m:
        if not args.json:
            # Reported, never passed silently: "I checked and it is current" and "I could not
            # check" are otherwise identical in this output.
            print(f"runtime-lag: UNVERIFIED — {m['unmeasurable']} ({age_text})")
        return 0

    if not m.get("is_ancestor"):
        if not args.json:
            print(
                f"runtime-lag: DIVERGED — the running runtime {m['sha'][:12]} is not an ancestor of "
                f"{m['ref']} ({age_text}). It was built from a ref that is not on the default branch."
            )
        return 1

    behind = m.get("behind", 0)
    if behind > args.max_commits:
        if not args.json:
            head = _git("rev-parse", m["ref"])[1] or m["ref"]
            print(
                f"runtime-lag: STALE — the scheduled runtime is {behind} commits behind {m['ref']} "
                f"({age_text}). Everything merged since {m['sha'][:12]} is on the remote and running "
                f"NOWHERE on this host.\n"
                f"  rotate: {ROTATOR.format(sha=head)}"
            )
        return 1

    if not args.json:
        print(
            f"runtime-lag: OK — scheduled runtime {m['sha'][:12]} is {behind} commit(s) behind {m['ref']} ({age_text})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
