#!/usr/bin/env python3
"""Author a well-formed ``logs/AUTONOMY_PAUSED`` marker — the FIRST official writer.

Until now nothing in production wrote the marker: it was created by the operator by hand or by test
fixtures, and every system only *read* + *unlinked* it. That is exactly why the same malformed marker
kept freezing the beat three times (2026-07-14/15/16): a hand-authored marker with an ``owner_surface:``
prose line but no ``owner:``/``pr:`` coordinate and no ``next_command`` runbook can NEVER autoclear
(autonomy-governor._marker_owner_merged returns False forever), and nothing stopped it being written.

``scripts/pause-marker-hygiene.py`` *catches* that after the fact. This *prevents* it at the source: a
marker authored here is structurally guaranteed to satisfy the hygiene contract, because ``arm`` refuses
to write one that doesn't. A marker needs, at minimum:

  • ``class:`` — ``fence`` (a peer-coordination pause: protects a peer agent's lanes; a directed session
    self-coordinates around them and drives its own insulated work) or ``wall`` (a genuine safety halt);
  • ``reason:`` — a human-readable why;
  • a RELEASE PATH — at least one of ``--pr N`` / ``--owner BRANCH`` (a coordinate the governor autoclears
    on MERGE) or ``--next-command`` (a machine-executable recovery runbook).

Anything missing ⇒ the command exits non-zero and writes nothing. The write itself is atomic
(``os.replace``) so a reader never sees a half-written marker, and it refuses to clobber an existing
marker unless ``--force`` (the live marker may be a peer's coordination artifact — never overwrite it
blindly).

Read-only on everything except the marker it is explicitly asked to author.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT") or Path(__file__).resolve().parents[1])
MARKER = ROOT / "logs" / "AUTONOMY_PAUSED"

# Emitted in this stable order; only non-empty fields are written. `class`/`reason` always present
# (arm requires them); at least one of pr/owner/next_command is guaranteed by _validate.
_ORDER = (
    "class",
    "reason",
    "created_at",
    "owner_surface",
    "owner",
    "pr",
    "repo",
    "prohibitions",
    "release_predicate",
    "next_command",
)


def _clean(value: str) -> str:
    """A marker is strict one-line ``<name>: <value>`` — collapse any newline so a value can't forge
    a second field (a ``reason`` containing a newline + ``pr: 9`` would otherwise inject a coordinate)."""
    return " ".join((value or "").split())


def _validate(fields: dict[str, str]) -> list[str]:
    problems: list[str] = []
    cls = fields.get("class", "")
    if cls not in ("fence", "wall"):
        problems.append(f"class must be 'fence' or 'wall' (got {cls!r})")
    if not fields.get("reason"):
        problems.append("reason is required")
    if not (fields.get("pr") or fields.get("owner") or fields.get("next_command")):
        problems.append(
            "a marker needs a release path — at least one of --pr / --owner (a coordinate the governor "
            "autoclears on merge) or --next-command (a recovery runbook); otherwise it can never clear"
        )
    return problems


def _render(fields: dict[str, str]) -> str:
    return "".join(f"{name}: {fields[name]}\n" for name in _ORDER if fields.get(name))


def _write_atomic(marker: Path, text: str) -> None:
    marker.parent.mkdir(parents=True, exist_ok=True)
    tmp = marker.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, marker)  # atomic on POSIX — a reader sees the old marker or the new, never a splice


def cmd_arm(args: argparse.Namespace) -> int:
    fields = {
        "class": args.klass,
        "reason": _clean(args.reason),
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "owner_surface": _clean(args.owner_surface),
        "owner": _clean(args.owner),
        "pr": _clean(args.pr),
        "repo": _clean(args.repo),
        "prohibitions": _clean(args.prohibitions),
        "release_predicate": _clean(args.release_predicate),
        "next_command": _clean(args.next_command),
    }
    problems = _validate(fields)
    if problems:
        print("pause arm: REFUSED — a malformed marker can never clear:", file=sys.stderr)
        for p in problems:
            print(f"  • {p}", file=sys.stderr)
        return 2

    if MARKER.exists() and not args.force:
        print(
            f"pause arm: REFUSED — {MARKER} already exists (it may be a peer's coordination artifact). "
            "Pass --force only if you own it.",
            file=sys.stderr,
        )
        return 3

    _write_atomic(MARKER, _render(fields))
    print(f"pause arm: wrote {MARKER}")
    print(_render(fields), end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="pause", description="Author a well-formed AUTONOMY_PAUSED marker.")
    sub = ap.add_subparsers(dest="command", required=True)
    arm = sub.add_parser("arm", help="write a marker (refuses a malformed one)")
    arm.add_argument("--class", dest="klass", choices=("fence", "wall"), required=True,
                     help="fence = peer-coordination (insulated work proceeds); wall = safety halt")
    arm.add_argument("--reason", required=True, help="human-readable why (required)")
    arm.add_argument("--pr", default="", help="release coordinate: PR number (autoclears on merge)")
    arm.add_argument("--owner", default="", help="release coordinate: PR head branch (autoclears on merge)")
    arm.add_argument("--next-command", dest="next_command", default="",
                     help="release runbook: a machine-executable recovery command")
    arm.add_argument("--prohibitions", default="", help="what the pause forbids (e.g. 'no merges; no sends')")
    arm.add_argument("--owner-surface", dest="owner_surface", default="", help="human owner context (never a coordinate)")
    arm.add_argument("--release-predicate", dest="release_predicate", default="", help="human release condition")
    arm.add_argument("--repo", default="", help="repository identifier (optional)")
    arm.add_argument("--force", action="store_true", help="overwrite an existing marker (own it first)")
    arm.set_defaults(func=cmd_arm)
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
