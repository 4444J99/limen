#!/usr/bin/env python3
"""Snapshot or enumerate the live privacy-safe GitHub estate."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.github_estate_enumerator import main

if __name__ == "__main__":
    raise SystemExit(main(root=ROOT))
