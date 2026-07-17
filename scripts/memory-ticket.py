#!/usr/bin/env python3
"""memory-ticket.py — submit one memory ticket to the record-keeper's inbox (MEMORIA lane).

A session's *only* memory-write surface. Sessions no longer hand-edit MEMORY.md or drop atom files
into the memory dir directly (the ~N-writer race the covenant dissolves). Instead they append one
immutable ticket to the lock-free inbox; TABVLARIVS (the record-keeper) folds it into the memory dir
on its next beat, as the single writer. No memory-dir read, no lock, no clobber risk here.

  python3 scripts/memory-ticket.py --slug my-atom --title "My Atom" --desc "one-line summary"
  python3 scripts/memory-ticket.py --slug my-atom --title "My Atom" --desc "…" --body-file note.md --star
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.memoria import MemoryTicket, new_ticket_id, submit_memory_ticket  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="submit one memory ticket for the record-keeper to fold in")
    ap.add_argument("--slug", required=True, help="safe kebab filename stem — becomes <slug>.md")
    ap.add_argument("--title", required=True, help="human title (the MEMORY.md link text)")
    ap.add_argument("--desc", required=True, help="one-line summary (index line + synthesized body)")
    ap.add_argument("--body-file", help="path to verbatim atom content; omit to synthesize from --desc")
    ap.add_argument("--star", action="store_true", help="prefix the index title with ★")
    ap.add_argument("--link", action="append", default=[], help="related atom/URL (repeatable)")
    ap.add_argument("--type", default="project", help="atom type (default: project)")
    ap.add_argument("--agent", default="session", help="submitting agent id")
    ap.add_argument("--session-id", default="unknown", help="submitting session id")
    args = ap.parse_args(argv)

    body = None
    if args.body_file:
        body = Path(args.body_file).expanduser().read_text(encoding="utf-8")

    now = datetime.now(timezone.utc)
    ticket = MemoryTicket(
        ticket_id=new_ticket_id(args.session_id, now),
        timestamp=now,
        agent=args.agent,
        session_id=args.session_id,
        slug=args.slug,
        title=args.title,
        desc=args.desc,
        body=body,
        star=args.star,
        links=list(args.link),
        type=args.type,
    )
    submit_memory_ticket(ticket)
    print(
        f"{ticket.ticket_id} queued — the record keeper (TABVLARIVS) folds this into memory "
        "on the next beat."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
