#!/usr/bin/env python3
"""Run dynamically registered universe source enumerators within bounded receipts."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.universe_adapter_runner import main

if __name__ == "__main__":
    raise SystemExit(main(root=ROOT))
