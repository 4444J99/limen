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
    try:
        from importlib.metadata import version

        return version("ruff")
    except Exception:
        return None


def main() -> int:
    want = pinned_version()
    have = installed_version()
    if have is None:
        print(
            f"check-ruff-pin: ruff is not importable from this interpreter — "
            f"run: python3 -m pip install -e 'cli[test]'  (pins ruff=={want})",
            file=sys.stderr,
        )
        return 1
    if have != want:
        print(
            f"check-ruff-pin: interpreter ruff {have} != pinned {want} — verdicts would be "
            f"machine-dependent noise. Fix: python3 -m pip install 'ruff=={want}' "
            f"(add --break-system-packages on a Homebrew/PEP-668 python)",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
