#!/usr/bin/env python3
"""Compatibility entrypoint for Representation Substrate validation."""

from __future__ import annotations

import sys

from representation_substrate import main


if __name__ == "__main__":
    raise SystemExit(main(["validate", *sys.argv[1:]]))
