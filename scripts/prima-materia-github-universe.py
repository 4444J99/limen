#!/usr/bin/env python3
"""Plan or check the privacy-safe GitHub universe projection."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.github_universe import main

if __name__ == "__main__":
    raise SystemExit(main())
