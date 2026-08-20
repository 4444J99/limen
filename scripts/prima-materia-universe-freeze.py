#!/usr/bin/env python3
"""Freeze source-owned project and collaborator observations into bound manifests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.universe_freezer import main

if __name__ == "__main__":
    raise SystemExit(main(root=ROOT))
