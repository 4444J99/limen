"""Private board hydration for a public aggregate tasks.yaml projection.

The public checkout is a status cache after board partition migration. Local
dispatch must opt into an authenticated/off-disk full board explicitly; it must
never infer private custody from a second public branch or silently fall back to
the public aggregate.
"""

from __future__ import annotations

import os
from pathlib import Path

from limen.io import load_limen_file
from limen.models import LimenFile


def private_board_path(public_path: Path) -> Path | None:
    raw = os.environ.get("LIMEN_PRIVATE_TASKS", "").strip()
    if not raw:
        return None
    private = Path(raw).expanduser().resolve()
    public = Path(public_path).expanduser().resolve()
    if private == public:
        raise ValueError("LIMEN_PRIVATE_TASKS must not point at the public tasks.yaml projection")
    return private


def load_operational_board(public_path: Path) -> tuple[LimenFile, Path]:
    """Load the full local board only from an explicit private custody path."""

    private = private_board_path(public_path)
    if private is None:
        return load_limen_file(public_path), Path(public_path)
    if not private.is_file():
        raise FileNotFoundError(
            f"private board custody is configured but unavailable: {private}"
        )
    return load_limen_file(private), private

