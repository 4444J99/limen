#!/usr/bin/env python3
"""The ONE answer to "which root am I" — and a worktree is never mistaken for the organism.

A guard that a single write can satisfy is not a guard. `scripts/diurnal.py` shipped with

    def has_body(root): return (root / "logs" / ".voice").is_dir()

documented as "True iff this root is a live organism, not a bare projection", and guarding what
its own sibling docstring calls "the single most dangerous failure mode this organ has". Measured
2026-07-31: it returns True in a worktree holding exactly ONE voice stamp, against the live root's
61. The organ then emitted a full morning briefing in which five sections that are PRESENT in the
live root rendered `ABSENT — does not exist`, and organ liveness read `3/65 green` where the live
body reads `27/64 green · 34 down`. It exited 0 and wrote the page. An emptier briefing reads as a
quieter morning.

The stamp it trusted is written by `scripts/beat-sensors.py`, which resolves its own root the same
way — `LIMEN_ROOT` or `Path(__file__).resolve().parent.parent`. Run from a worktree with no
`LIMEN_ROOT`, a sensor MANUFACTURES the body that fools the guard. `.voice` is not a liveness
signal; it is a signal that something once ran here.

Why one module instead of a fix in diurnal.py: ~232 sites resolve root via `LIMEN_ROOT` and ~90
more via `Path(__file__).parents[N]` with no env fallback at all, and their fallbacks disagree —
some default to *this tree*, some to the hardcoded canonical `~/Workspace/limen`. Those two answers
are identical everywhere EXCEPT inside a worktree, which is the one place the distinction matters.
Meanwhile ~13 organs (`organ-health`, `governance-organ`, `financial-organ`, `life-organ`,
`cvstos-organ`, …) read `logs/.voice/<x>` as ground truth for liveness, so all of them are fooled
by the same stray stamp. Duplicated resolution is how one wrong answer survives in a hundred places
at once — the lesson `_uma_root.py` already learned from five.

The discriminator is exact, not heuristic, and was already implemented correctly four times in this
repo without ever being packaged: **a linked worktree's `.git` is a FILE (a gitdir pointer); a real
checkout's `.git` is a DIRECTORY.** See `reclaim-worktrees.py:941`, `worktree_debt.py:328`,
`worktree_abandonment.py:244` (which also rejects a symlinked `.git`), `worktree_roots.py:245`.

Resolution order, and why:

  1. `LIMEN_ROOT` — explicit configuration wins. But an explicit value that is NOT a limen checkout
     is an ERROR naming the bad path, never a silent fall-through. Silently correcting bad config
     is what makes config errors invisible (`_uma_root.py`'s founding lesson).
  2. otherwise, walk up from this file to the first directory carrying the marker. Never
     `parents[N]`: the correct N is position-dependent (`scripts/`→1, `scripts/hooks/`→2,
     `cli/src/limen/`→3), so moving a file silently breaks it.
  3. otherwise, unresolved — with the searched list in the reason, so the log says what to fix.

`resolve_root()` answers honestly and never redirects a worktree to the live root. Knowing you are
a worktree is the whole point; a caller that needs the organism asks `has_body()` and refuses.

    python3 scripts/_root.py --path          # print the resolved root; exit 1 + reason if unresolved
    python3 scripts/_root.py --explain       # print what this root IS; always exit 0
    python3 scripts/_root.py --require-body  # exit 0 iff this root is a live organism
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path

# The file that proves a directory is a limen checkout rather than a same-named empty shell.
MARKER = Path("institutio") / "governance" / "sensors.yaml"

ENV_NAME = "LIMEN_ROOT"

VOICE_REL = Path("logs") / ".voice"

# Defence in depth behind the exact `.git` test, for the root that is a real checkout but not the
# ORGANISM — a second clone, a fresh CI checkout, a restored backup. Measured 2026-07-31: the live
# body carries 61 voice stamps; a worktree touched by one scheduled sensor carries 1. Any floor in
# between separates them, so this is deliberately nowhere near either edge.
DEFAULT_VOICE_FLOOR = 5


def _voice_floor() -> int:
    try:
        return max(1, int(os.environ.get("LIMEN_ROOT_VOICE_FLOOR", DEFAULT_VOICE_FLOOR)))
    except ValueError:
        return DEFAULT_VOICE_FLOOR


def is_checkout(path: Path) -> bool:
    """True iff this directory is a limen checkout at all (worktree or primary)."""
    return (path / MARKER).is_file()


def is_worktree(root: Path) -> bool:
    """True iff root is a LINKED WORKTREE rather than a primary checkout.

    Exact, not heuristic: git writes a `.git` FILE holding a gitdir pointer in a linked worktree
    and a `.git` DIRECTORY in the primary checkout. `lstat` + `S_ISREG` rather than `is_file()` so
    a symlinked `.git` — which `is_file()` follows and reports True for — is not read as a
    worktree. Borrowed verbatim from `worktree_abandonment.py:244`, the strictest of the four
    existing copies.
    """
    gitfile = root / ".git"
    try:
        return stat.S_ISREG(gitfile.lstat().st_mode) and not gitfile.is_symlink()
    except OSError:
        return False


def voice_count(root: Path) -> int:
    """How many beat voices have ever stamped this root. Zero on any unreadable root."""
    try:
        return sum(1 for p in (root / VOICE_REL).iterdir() if p.is_file())
    except OSError:
        return 0


def has_body(root: Path) -> tuple[bool, str]:
    """(is_live_organism, reason). The reason is always sayable out loud.

    Two independent conditions, because either alone has a documented false positive:
      - not a linked worktree  (the exact test; `.voice` alone let a 1-stamp worktree through)
      - voices at or above the floor  (a second clone is not a worktree, and is not the body either)
    """
    if not is_checkout(root):
        return False, f"{root} is not a limen checkout (no {MARKER})"
    if is_worktree(root):
        return False, f"{root} is a linked worktree (.git is a gitdir pointer), not the organism"
    voices = voice_count(root)
    floor = _voice_floor()
    if voices < floor:
        return False, (
            f"{root} is a checkout but not the live organism — {voices} voice stamp(s) "
            f"below the floor of {floor}; the body has never beaten here"
        )
    return True, f"{root} is the live organism ({voices} voice stamps)"


def resolve() -> tuple[Path | None, str]:
    """(root, reason). root is None ⟺ unresolved; reason is always sayable out loud."""
    raw = os.environ.get(ENV_NAME)
    if raw:
        candidate = Path(raw).expanduser().resolve()
        if is_checkout(candidate):
            return candidate, f"{ENV_NAME}={candidate}"
        return None, (
            f"{ENV_NAME} is set to {candidate}, which is not a limen checkout (no {MARKER}). "
            f"Explicit configuration is not silently overridden — fix or unset {ENV_NAME}."
        )

    here = Path(__file__).resolve()
    for candidate in here.parents:
        if is_checkout(candidate):
            return candidate, f"walked up from {here.name} to {candidate}"
    return None, (f"no limen checkout found (looked for {MARKER} in every parent of {here}); set {ENV_NAME}")


def resolve_root() -> Path:
    """The resolved root, or raise. Callers wanting the reason use resolve()."""
    root, reason = resolve()
    if root is None:
        raise RuntimeError(f"cannot resolve {ENV_NAME}: {reason}")
    return root


def explain(root: Path | None = None) -> str:
    """One line describing what this root IS — checkout, worktree, or the living body."""
    if root is None:
        root, reason = resolve()
        if root is None:
            return f"unresolved: {reason}"
    live, why = has_body(root)
    kind = "live" if live else ("worktree" if is_worktree(root) else "checkout")
    return f"{kind}: {why}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve and classify the limen root.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--path", action="store_true", help="print the root; exit 1 if unresolved")
    group.add_argument("--explain", action="store_true", help="print what this root is; always exit 0")
    group.add_argument("--require-body", action="store_true", help="exit 0 iff this root is the live organism")
    parser.add_argument("--root", help="classify this path instead of resolving one")
    args = parser.parse_args(argv)

    if args.root:
        root, reason = Path(args.root).expanduser().resolve(), f"--root {args.root}"
    else:
        root, reason = resolve()

    if args.explain:
        print(explain(root) if root is not None else f"unresolved: {reason}")
        return 0

    if root is None:
        print(reason, file=sys.stderr)
        return 1

    if args.require_body:
        live, why = has_body(root)
        print(why, file=sys.stdout if live else sys.stderr)
        return 0 if live else 1

    print(root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
