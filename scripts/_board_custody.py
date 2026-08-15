"""_board_custody.py — one resolver every local board reader shares.

THE CUTOVER'S BLAST RADIUS, CLOSED. After the board partition cuts over, the public
``tasks.yaml`` is the keeper's counts-only aggregate. A reader that parses it directly
gets ``tasks: []`` and reports **zero work** — not an error, just a board that looks
finished. Measured 2026-08-15: 121 python files name tasks.yaml; 62 honor ``LIMEN_TASKS``
and flip with the beat env, 35 only mention it in prose, and **24 resolve a path and parse
it**. Those 24 are the ones that would go quietly wrong, and 19 of them parse with raw
``yaml.safe_load`` — so there is no single loader to fix. This module is the seam they
share instead.

Usage is one call at the point the path is resolved::

    from _board_custody import board_path
    data = yaml.safe_load(board_path(ROOT / "tasks.yaml").read_text())

Pre-cutover that returns the same path it was handed, so every adoption is a behavior-
preserving no-op today and becomes correct the moment the aggregate lands — the
consumers-derive ratchet ``institutio/governance/gates.yaml`` already uses six times over.

Post-cutover it returns hydrated private custody, and raises when custody is missing
rather than handing back an empty board. ``scripts/check-board-consumers.py`` is the
predicate that keeps every reader on this seam.
"""

from __future__ import annotations

import sys
from pathlib import Path

_CLI_SRC = Path(__file__).resolve().parent.parent / "cli" / "src"
if str(_CLI_SRC) not in sys.path:
    sys.path.insert(0, str(_CLI_SRC))

from limen.private_board import (  # noqa: E402
    PrivateCustodyUnavailable,
    operational_board_path,
    path_is_public_aggregate,
)

__all__ = ["PrivateCustodyUnavailable", "board_path", "board_is_aggregate"]


def board_path(public) -> Path:
    """The board this process should PARSE, given the public projection it meant to read.

    Delegates to :func:`limen.private_board.operational_board_path` so the shape probe,
    the custody default, and the missing-custody error live in exactly one place.
    """

    return operational_board_path(Path(public))


def board_is_aggregate(public) -> bool:
    """Is the public projection the counts-only aggregate rather than a work board?"""

    return path_is_public_aggregate(Path(public))
