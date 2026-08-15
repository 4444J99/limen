"""Private board hydration for a public aggregate tasks.yaml projection.

The public checkout is a status cache after board partition migration. Local
dispatch must opt into an authenticated/off-disk full board explicitly; it must
never infer private custody from a second public branch or silently fall back to
the public aggregate.

Once the partition cutover lands, the public ``tasks.yaml`` stops being a task
board at all: it becomes the counts-only aggregate the keeper publishes
(``limen.public_board_projection.v1``, ``tasks: []``). Every local consumer that
kept reading it would then see a board with **zero tasks** — indistinguishable
from "there is no work" and catastrophic in exactly the silent way the partition
plan warned about ("the failure mode is invisible, because the board still looks
full", inverted). So the aggregate shape is DERIVED here and treated as a hard
signal: local operational reads resolve to private custody, and when custody is
missing they raise :class:`PrivateCustodyUnavailable` rather than returning an
empty board. Loud beats empty.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from limen.io import load_limen_file
from limen.models import LimenFile

#: The keeper's counts-only public projection — a health surface, never a work board.
PUBLIC_AGGREGATE_SCHEMA = "limen.public_board_projection.v1"

#: Enough bytes to carry the document header of either shape; a 5.8 MB board is
#: never fully parsed just to answer "which shape is this?".
_SHAPE_PROBE_BYTES = 4096

# A column-0 key: the aggregate declares it as the document's own schema. A task's
# free-text `context` is always indented under `tasks:`, so it cannot match.
_AGGREGATE_MARKER = re.compile(
    rf"^schema_version:\s*['\"]?{re.escape(PUBLIC_AGGREGATE_SCHEMA)}['\"]?\s*$",
    re.MULTILINE,
)


class PrivateCustodyUnavailable(BaseException):
    """The public projection is an aggregate and no private custody answers for it.

    Inherits ``BaseException``, not ``Exception``, and that is the whole point.

    Board readers across this estate wrap their parse in a broad ``except Exception``
    that degrades to an empty result — a sane contract when the failure mode is "the
    file is briefly unreadable". It is a catastrophic one here: with an aggregate public
    projection and no custody, degrading means reporting **zero tasks** as though the
    fleet had no work. Verified 2026-08-15 against the simulated cutover: as a
    ``RuntimeError`` this was swallowed by ``omni-view.py`` and printed
    ``board 0 tasks`` with exit 0.

    So this joins ``KeyboardInterrupt`` and ``SystemExit`` in the category Python reserves
    for "do not let a generic handler pretend this didn't happen". Handlers that genuinely
    want it name it explicitly (``heal-board.py``, ``limen board custody-path``). One
    declaration replaces auditing the ``except`` clause of every reader, and it cannot
    rot as new readers are written.
    """


def private_board_path(public_path: Path) -> Path | None:
    raw = os.environ.get("LIMEN_PRIVATE_TASKS", "").strip()
    if not raw:
        return None
    private = Path(raw).expanduser().resolve()
    public = Path(public_path).expanduser().resolve()
    if private == public:
        raise ValueError("LIMEN_PRIVATE_TASKS must not point at the public tasks.yaml projection")
    return private


def document_is_public_aggregate(text: str) -> bool:
    """Is this document the keeper's counts-only projection rather than a task board?"""

    return bool(_AGGREGATE_MARKER.search(text[:_SHAPE_PROBE_BYTES]))


def path_is_public_aggregate(path: Path) -> bool:
    """Cheap shape probe: read only the document header, never the whole board."""

    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            return document_is_public_aggregate(handle.read(_SHAPE_PROBE_BYTES))
    except (OSError, UnicodeDecodeError):
        return False


def default_private_custody_path(public_path: Path | None = None) -> Path:
    """Where hydrated custody lives when no explicit override is configured.

    Derived from ``LIMEN_PRIVATE_ROOT`` (the registry's ignored local cartridge
    root, default ``$LIMEN_ROOT/.limen-private``) so custody shares the estate's
    one private-storage convention instead of inventing a second.
    """

    configured = os.environ.get("LIMEN_PRIVATE_ROOT", "").strip()
    if configured:
        root = Path(os.path.expandvars(configured)).expanduser()
    else:
        limen_root = os.environ.get("LIMEN_ROOT", "").strip()
        base = (
            Path(limen_root).expanduser()
            if limen_root
            else (Path(public_path).expanduser().parent if public_path else Path.home() / "Workspace" / "limen")
        )
        root = base / ".limen-private"
    return (root / "board" / "canonical.yaml").resolve()


def operational_board_path(public_path: Path) -> Path:
    """Resolve the board local code should OPERATE on (read state, derive preconditions).

    Precedence, and the reason for each rung:

    1. ``LIMEN_PRIVATE_TASKS`` — an explicit operator/beat declaration always wins.
    2. The public projection is the counts-only aggregate → private custody is
       mandatory. Hydrated custody is used; a missing one is an error, never a
       silent empty board.
    3. Otherwise the public projection still IS the board (pre-cutover).
    """

    public = Path(public_path).expanduser()
    explicit = private_board_path(public)
    if explicit is not None:
        return explicit
    if not path_is_public_aggregate(public):
        return public
    custody = default_private_custody_path(public)
    if custody.is_file():
        return custody
    raise PrivateCustodyUnavailable(
        f"{public} is the counts-only public aggregate ({PUBLIC_AGGREGATE_SCHEMA}); "
        f"local operation requires hydrated private custody at {custody}. "
        "Run `limen board hydrate --output "
        f"{custody}` (the beat's hydrate-private-board rung does this every cycle), "
        "or set LIMEN_PRIVATE_TASKS to an explicit custody path."
    )


def load_operational_board(public_path: Path) -> tuple[LimenFile, Path]:
    """Load the full local board from whichever custody actually answers for it."""

    resolved = operational_board_path(public_path)
    if resolved == Path(public_path).expanduser():
        return load_limen_file(resolved), resolved
    if not resolved.is_file():
        raise FileNotFoundError(f"private board custody is configured but unavailable: {resolved}")
    return load_limen_file(resolved), resolved
