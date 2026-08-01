#!/usr/bin/env python3
"""Clause 3 of the autonomy maintenance resume predicate: generated == installed.

Exit 0 ⟺ the launchd plist ``scripts/gen-launchd-plist.sh`` renders RIGHT NOW is byte-identical
to the one actually installed at ``~/Library/LaunchAgents/com.limen.heartbeat.plist``. That is
what "generated and installed heartbeat environments identical" means in
``logs/autonomy-policy.json``'s resume_predicate.

Why this is a lifecycle clause and not a nicety: the generator derives HOME, the repo root, the
interpreter and PATH at generation time — "names are outputs, not inputs". So a drift between
generated and installed means the daemon that is actually running was launched with a DIFFERENT
environment than the repo now describes: an older python, a moved checkout, a stale PATH. Resuming
autonomy in that state hands full authority to a process whose environment nobody has verified.

This check only ever READS. It never installs, loads, bootstraps, or restarts anything — writing
to LaunchAgents is a separate supervised step, and in this estate it is hook-blocked besides.

    python3 scripts/check-heartbeat-env.py           # exit 0 iff identical
    python3 scripts/check-heartbeat-env.py --diff    # show the drift when they differ
"""

from __future__ import annotations

import argparse
import difflib
import re
import subprocess
import sys
from pathlib import Path

INSTALLED = Path.home() / "Library" / "LaunchAgents" / "com.limen.heartbeat.plist"
PLIST_ROOT_RX = re.compile(r"<key>LIMEN_ROOT</key>\s*<string>([^<]+)</string>")


def _installed_root(installed: str) -> Path | None:
    """The root the installed daemon was generated FROM — it declares its own LIMEN_ROOT."""
    match = PLIST_ROOT_RX.search(installed)
    return Path(match.group(1)) if match else None


def compare() -> tuple[bool, str, str, str]:
    """(identical, reason, generated, installed). Fail CLOSED on every ambiguity.

    The generator runs from the root the INSTALLED plist names, never from wherever this checker
    happens to live. `gen-launchd-plist.sh` derives every path from its own location, so running
    the copy inside a worktree renders a plist full of worktree paths and reports DRIFT against a
    perfectly healthy install. Measured 2026-07-31, on the first run of this very file — the same
    "which root am I" defect that scripts/_root.py exists to end, reproduced one file later.

    Asking the installed plist which root produced it makes the question self-referential and
    exact: does the root you were installed from still generate you?
    """
    try:
        installed = INSTALLED.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False, f"no installed plist at {INSTALLED} — the heartbeat env is undeclared", "", ""
    except OSError as exc:
        return False, f"installed plist unreadable: {exc}", "", ""

    root = _installed_root(installed)
    if root is None:
        return False, f"installed {INSTALLED.name} declares no LIMEN_ROOT — cannot say what generated it", "", installed
    generator = root / "scripts" / "gen-launchd-plist.sh"
    if not generator.is_file():
        return False, f"the root the daemon names ({root}) has no {generator.name}", "", installed

    try:
        proc = subprocess.run(
            ["bash", str(generator)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            cwd=str(root),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"generator did not run: {exc}", "", installed
    if proc.returncode != 0:
        return False, f"generator exited {proc.returncode}: {proc.stderr.strip()[:200]}", "", installed

    generated = proc.stdout
    if not generated.strip():
        return False, "generator produced empty output", "", installed

    if generated == installed:
        return True, f"{root} still generates the installed {INSTALLED.name} byte-for-byte", generated, installed
    return (
        False,
        (
            f"installed {INSTALLED.name} DRIFTS from what {root} now generates — "
            "the running daemon's environment is not the one that root describes"
        ),
        generated,
        installed,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--diff", action="store_true", help="print a unified diff when they differ")
    args = ap.parse_args(argv)

    identical, reason, generated, installed = compare()
    stream = sys.stdout if identical else sys.stderr
    print(f"heartbeat-env: {'IDENTICAL' if identical else 'DRIFT'} — {reason}", file=stream)

    if args.diff and not identical and generated and installed:
        for line in difflib.unified_diff(
            installed.splitlines(keepends=True),
            generated.splitlines(keepends=True),
            fromfile="installed",
            tofile="generated",
        ):
            print(line, end="", file=stream)

    return 0 if identical else 1


if __name__ == "__main__":
    sys.exit(main())
