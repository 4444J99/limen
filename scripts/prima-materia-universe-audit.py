#!/usr/bin/env python3
"""Run one read-only, source-bound Prima Materia universe fixed-point predicate."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.universe_audit import main

if __name__ == "__main__":
    raise SystemExit(main(root=ROOT))
