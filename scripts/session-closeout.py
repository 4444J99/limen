#!/usr/bin/env python3
"""Use the canonical session checker from source or the installed runtime."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli/src"))
from limen.session_closeout import main

if __name__ == "__main__":
    raise SystemExit(main())
