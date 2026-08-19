#!/usr/bin/env python3
"""Compatibility entrypoint for Representation Substrate validation."""

from __future__ import annotations

import sys

from representation_substrate import main


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        args = ["--fleet"]
    raise SystemExit(main(["validate", *args]))
