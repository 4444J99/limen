#!/usr/bin/env python3
"""check-ruff-pin — the ruff toolchain-parity predicate (issue #1658).

The estate's ruff pin has exactly ONE carrier: the `ruff==X.Y.Z` row in cli/pyproject.toml's
test extras. CI installs it via `-e "cli[test]"`; local scoped runs assert against it here
before ruff executes. Exit 0 ⟺ the interpreter's ruff matches the pin; exit 1 prints the one
command that fixes it. This turns the machine-dependent 1,308-finding false-red (Homebrew ruff
0.16.0 vs CI 0.15.8) into a loud, actionable verdict instead of noise.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "cli" / "pyproject.toml"


def pinned_version() -> str:
    match = re.search(r'"ruff==([0-9][0-9A-Za-z.]*)"', PYPROJECT.read_text(encoding="utf-8"))
    if not match:
        print(f"check-ruff-pin: no `ruff==X` pin found in {PYPROJECT} — the single carrier is gone", file=sys.stderr)
        raise SystemExit(1)
    return match.group(1)


def installed_version() -> str | None:
    """Inspect the command the gates execute, not potentially stale dist-info.

    Ruff's Python launcher can select a Homebrew binary outside the installed
    wheel. Matching package metadata alone does not establish toolchain parity.
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode:
        return None
    match = re.fullmatch(r"ruff ([0-9][0-9A-Za-z.]*)", result.stdout.strip())
    return match.group(1) if match else None


def main() -> int:
    want = pinned_version()
    have = installed_version()
    if have is None:
        print(
            f"check-ruff-pin: this interpreter could not execute a verifiable Ruff binary — "
            f"use an isolated environment installed from cli[test] (pins ruff=={want})",
            file=sys.stderr,
        )
        return 1
    if have != want:
        print(
            f"check-ruff-pin: executed ruff {have} != pinned {want} — verdicts would be "
            "machine-dependent noise. Use an isolated environment installed from cli[test]; "
            "do not overwrite a package-manager-owned binary to repair Python metadata.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
