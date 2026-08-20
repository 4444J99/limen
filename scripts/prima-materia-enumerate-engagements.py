#!/usr/bin/env python3
"""Enumerate the tracked engagement ledger for a universe dimension."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.engagement_ledger_enumerator import main

if __name__ == "__main__":
    raise SystemExit(main(root=ROOT))
