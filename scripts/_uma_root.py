#!/usr/bin/env python3
"""The ONE name for the UMA checkout — and a missing one is a named blocker, never a crash.

Five call sites resolved this independently, under two different environment-variable names
(`UMA_ROOT` in four, `LIMEN_UMA_ROOT` in a fifth), every one of them defaulting to
`~/Workspace/universal-mail--automation`. That path does not exist. The real checkout is one
directory deeper — `~/Workspace/4444J99/universal-mail--automation` — so every mail rung has been
resolving to nothing. Duplicated resolution is how a one-segment path error survives in five places
at once.

Nothing failed loudly. Both `mail-story-ledger.py` and `mail-beat.sh` ended their resolution chain
with `["umail"]`, a bare binary that is not installed, so an unresolvable checkout surfaced as
`FileNotFoundError: 'umail'` inside a fail-open beat rung — indistinguishable from silence. Both
files already carry a `blocked` status representation they never got to emit. Meanwhile
`mail-send` had been printing the answer into a log nobody reads: "mail_send.py not found (set
UMA_ROOT?)".

Resolution order, and why:

  1. `UMA_ROOT`, then `LIMEN_UMA_ROOT` — explicit configuration wins. But an explicit value that is
     NOT a checkout is an ERROR naming the bad path, never a silent fall-through to the defaults.
     Silently correcting bad config is precisely what makes config errors invisible.
  2. otherwise, the known candidate paths, in order, first one that is really a checkout.
  3. otherwise, unresolved — with the searched list in the reason, so the log says what to fix.

"Is really a checkout" means the marker file is present. A directory that merely exists at the right
path proves nothing; the 2026-07-27 failure was a plausible-looking path with nothing behind it.

  python3 scripts/_uma_root.py --path      # print the resolved root, exit 1 + reason if unresolved
  python3 scripts/_uma_root.py --explain   # print the reason either way (always exit 0)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# The file that proves a directory is the UMA checkout rather than a same-named empty shell.
MARKER = "cli.py"

ENV_NAMES = ("UMA_ROOT", "LIMEN_UMA_ROOT")


def default_candidates() -> list[Path]:
    home = Path.home()
    return [
        home / "Workspace" / "4444J99" / "universal-mail--automation",
        home / "Workspace" / "universal-mail--automation",
    ]


def is_checkout(path: Path) -> bool:
    return (path / MARKER).is_file()


def resolve() -> tuple[Path | None, str]:
    """(root, reason). root is None ⟺ unresolved; reason is always sayable out loud."""
    for name in ENV_NAMES:
        raw = os.environ.get(name)
        if not raw:
            continue
        candidate = Path(raw).expanduser()
        if is_checkout(candidate):
            return candidate, f"{name}={candidate}"
        return None, (
            f"{name} is set to {candidate}, which is not a UMA checkout (no {MARKER}). "
            f"Explicit configuration is not silently overridden — fix or unset {name}."
        )

    candidates = default_candidates()
    for candidate in candidates:
        if is_checkout(candidate):
            return candidate, f"default candidate {candidate}"

    searched = ", ".join(str(c) for c in candidates)
    return None, f"no UMA checkout found (looked for {MARKER} in: {searched}); set UMA_ROOT"


def uma_root() -> Path | None:
    return resolve()[0]


def uma_command(override: str | None = None) -> list[str] | None:
    """The command that runs UMA's CLI, or None when it cannot be run.

    Returns None rather than `["umail"]`. That fallback named a binary which is not installed
    anywhere on this host, converting a resolvable configuration problem into a FileNotFoundError
    raised from inside a fail-open rung — the failure mode this module exists to end.
    """
    if override:
        return [override]
    binary = os.environ.get("UMA_BIN")
    if binary:
        return [binary]
    root = uma_root()
    if root is None:
        return None
    return [os.environ.get("LIMEN_PY", "python3"), str(root / MARKER)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve the UMA checkout root.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--path", action="store_true", help="print the root; exit 1 if unresolved")
    group.add_argument("--explain", action="store_true", help="print the reason; always exit 0")
    group.add_argument("--command", action="store_true", help="print the UMA CLI argv as JSON; exit 1 if unrunnable")
    args = parser.parse_args(argv)

    root, reason = resolve()
    if args.explain:
        print(reason)
        return 0
    if args.command:
        command = uma_command()
        if command is None:
            print(reason, file=sys.stderr)
            return 1
        import json

        print(json.dumps(command))
        return 0
    # --path is the default shape: shells want the value or a loud nothing.
    if root is None:
        print(reason, file=sys.stderr)
        return 1
    print(root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
