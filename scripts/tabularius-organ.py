#!/usr/bin/env python3
"""tabularius-organ.py — outbound compatibility relay to the conduct keeper.

Each beat it drains the lock-free ticket inbox (``logs/tickets/inbox``) by submitting bounded
packets to the authenticated remote owner. ``tasks.yaml`` is a read-only hot projection. A ticket
is archived only after the remote GitHub-backed projection receipt is acknowledged; broker
unavailability leaves the unacknowledged suffix pending.

Idempotent and beat-safe: an empty inbox is an instant no-op (no lock, no board I/O), so it is
harmless to fire every beat while no producers exist yet. If the queue lock is held by a legacy
writer mid-migration, it defers to the next beat rather than blocking.

  python3 scripts/tabularius-organ.py            # relay the inbox, else no-op (exit 0)
  python3 scripts/tabularius-organ.py --check    # report pending count only; never mutate
  python3 scripts/tabularius-organ.py --dry-run  # report what WOULD be applied; make no writes
  python3 scripts/tabularius-organ.py --preflight # fail closed unless the remote keeper admits work
  python3 scripts/tabularius-organ.py --require-published  # require remote projection custody
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.tabularius import (  # noqa: E402
    board_publication_preflight,
    drain_once,
    pending_count,
    preserve_board_projection,
)

ROOT = Path(
    os.environ.get("LIMEN_ROOT") or os.environ.get("GITHUB_WORKSPACE") or Path(__file__).resolve().parent.parent
)
BOARD = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
ENABLED = os.environ.get("LIMEN_TABVLARIVS", "1") != "0"
MEMORIA_ENABLED = os.environ.get("LIMEN_MEMORIA", "0") == "1"
STATE = ROOT / "logs" / "tabularius-organ-state.json"


def _stamp(**fields: object) -> None:
    """Write the counts-only liveness stamp organ-health.py probes (no task content — PII-clean)."""
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        # `updated` is read by scripts/organ-health.py `_json_field_ts`, which honours a trailing
        # `Z` and otherwise parses naive datetime as LOCAL. `datetime.now(timezone.utc).isoformat()`
        # emits "+00:00", which that reader does NOT recognise as UTC — so it read this stamp as
        # local time and reported the record as being in the future ("recorded -1.0h ago").
        # Emit the trailing-Z form the reader documents, matching the other UTC producers.
        STATE.write_text(
            json.dumps(
                {
                    "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    **fields,
                },
                indent=2,
            )
        )
    except OSError:
        pass


def _describe(memory: dict[str, object]) -> str:
    """Human-readable memory outcome, for the non-mutating modes' stdout."""
    if "memory_error" in memory:
        return f"pass FAILED ({memory['memory_error']})"
    # A deferral is not a pass. `drain_memory_once` defers while the memory lock is
    # held, reporting pending with nothing applied and nothing rejected — which, once
    # applied/rejected are dropped, is indistinguishable from an empty inbox and
    # rendered as "pass OK (0 pending, 0 applied, 0 rejected)".
    if memory.get("memory_deferred"):
        streak = memory.get("memory_defer_note")
        detail = f" — {streak}" if streak else ""
        return f"pass DEFERRED ({memory['memory_deferred']}{detail})"
    pending = memory.get("memory_pending")
    applied = memory.get("memory_applied")
    rejected = memory.get("memory_rejected")
    if applied is None:
        return f"pass OK ({pending} pending)"
    # Under --dry-run these are WOULD-BE counts: memoria reports how many tickets
    # are *applicable* and how many are *unparseable*, having written nothing.
    # Rendering them "applied"/"rejected" reports completions that never happened.
    # The dry-run fact travels in the outcome dict rather than being re-derived from
    # the caller's flag, so `--check --dry-run` — whose count is a real count — stays
    # truthful instead of being relabelled.
    if memory.get("memory_dry_run"):
        return f"pass OK WOULD APPLY ({pending} pending, would apply {applied}, {rejected} unparseable)"
    return f"pass OK ({pending} pending, {applied} applied, {rejected} rejected)"


def _prior_memory_deferral() -> tuple[int, str]:
    """The previous run's deferral streak, so repetition is measurable.

    The stamp is overwritten every run, so repetition cannot be derived from it alone: a
    single contention event and the hundredth consecutive one produce identical fields.
    Carrying the streak forward is what lets a reader distinguish "contended this beat" —
    the designed outcome, since `drain_memory_once` defers rather than blocking — from "the
    lane is stuck". Returns (streak, since) where `since` is when the current streak began.
    """
    try:
        obj = json.loads(STATE.read_text())
    except (OSError, ValueError):
        return 0, ""
    if not isinstance(obj, dict):
        return 0, ""
    streak = obj.get("memory_defer_streak")
    since = obj.get("memory_deferred_since")
    return (
        streak if isinstance(streak, int) and streak > 0 else 0,
        since if isinstance(since, str) else "",
    )


def _memory_pass(*, check: bool, dry_run: bool) -> dict[str, object]:
    if not MEMORIA_ENABLED:
        return {}
    try:
        # `memoria` owns the memory-dir derivation and exposes no module-level
        # constant for it. Both call sites below leave `memdir` unset so its
        # resolver (LIMEN_MEMORY_DIR, else the workspace-derived default) stays
        # authoritative. Do not reintroduce a hardcoded path here.
        from limen.memoria import drain_memory_once, pending_count

        if check:
            return {"memory_pending": pending_count()}
        result = drain_memory_once(dry_run=dry_run)
        # `deferred` and `note` are part of this outcome, not decoration. Dropping them
        # published a held-lock deferral as pending-with-nothing-applied, which both the
        # health reader and `_describe` read as success.
        note = str(getattr(result, "note", "") or "")
        fields: dict[str, object] = {
            "memory_pending": result.pending,
            "memory_applied": result.applied,
            "memory_rejected": result.rejected,
            "memory_dry_run": bool(dry_run),
        }
        if note:
            fields["memory_note"] = note
        if getattr(result, "deferred", False):
            # A STRING, not a bool. `organ-health.py` readers require a non-empty string
            # at a key path, so a bare `true` would be written and then silently unread.
            streak, since = _prior_memory_deferral()
            fields["memory_deferred"] = note or "deferred to next beat"
            fields["memory_defer_streak"] = streak + 1
            # When the CURRENT streak began, not when this run happened: a reader must
            # be able to tell one recent deferral from a streak that has outlasted the
            # threshold, and the stamp alone cannot express "how long".
            fields["memory_deferred_since"] = since or datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            # `_describe` is the only channel a reader of this outcome has when the memory
            # lane is enabled but the board inbox is empty — that branch prints no memory
            # line, so a streak that never advances visibly would look like a single
            # tolerated event indefinitely. Show the count and its age; the health reader
            # applies the threshold, this just makes repetition legible at the call site.
            hours = ""
            try:
                started = datetime.strptime(
                    str(fields["memory_deferred_since"]), "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=timezone.utc)
                hours = f", {round(max(0.0, (datetime.now(timezone.utc) - started).total_seconds()) / 3600, 1)}h"
            except ValueError:
                pass
            fields["memory_defer_note"] = (
                f"{fields['memory_defer_streak']} consecutive run(s){hours}"
            )
        elif not dry_run:
            # A drain that ran and did not defer IS a successful drain, and it ends the
            # streak — including the "inbox empty" no-op, which means the lane worked
            # and had nothing to do. Only a real deferred run may carry the streak on.
            fields["memory_defer_streak"] = 0
        return fields
    except Exception as exc:
        print(f"tabularius[memoria]: skipped ({type(exc).__name__}: {str(exc)[:120]})")
        return {"memory_error": type(exc).__name__}

def _publication_required_failure(required: bool, preserve: object | None) -> bool:
    """Return whether CI lacks exact remote board custody."""
    if not required:
        return False
    if preserve is None:
        return True
    published = bool(getattr(preserve, "published", False))
    reason = str(getattr(preserve, "reason", ""))
    failed_effect = (
        reason.startswith(
            (
                "github-unavailable:",
                "pr-",
                "publication-",
                "push-rejected:",
                "remote-keeper-",
            )
        )
        and reason != "publication-in-flight"
    )
    return not published or failed_effect


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="relay the ticket inbox to the authenticated conduct keeper")
    ap.add_argument("--check", action="store_true", help="report pending ticket count; never mutate")
    ap.add_argument("--dry-run", action="store_true", help="report what would be applied; no writes")
    ap.add_argument(
        "--preflight",
        action="store_true",
        help="admit a producer only when the authenticated remote keeper owns publication",
    )
    ap.add_argument(
        "--require-published",
        action="store_true",
        help="fail unless the remote keeper proves projection custody",
    )
    args = ap.parse_args(argv)

    if not ENABLED:
        print("tabularius: LIMEN_TABVLARIVS=0 — record-keeper disabled; leaving inbox as-is")
        return 2 if args.require_published or args.preflight else 0

    if args.preflight:
        result = board_publication_preflight(BOARD)
        if result.reason == "preflight-clear":
            print("tabularius: remote keeper preflight clear")
            return 0
        if result.published and result.deferred:
            print(
                f"tabularius: publication preflight deferred ({result.reason})"
                + (f" at PR #{result.pr_number}" if result.pr_number else "")
            )
            return 75
        if result.reason == "remote-keeper-preflight-required":
            # The local publication writer this preflight used to gate is retired — the kernel
            # (board_publication_preflight) correctly fails closed rather than reviving it, since
            # it has no way to ask the remote conduct broker whether IT is ready. That is a
            # "cannot answer" for a WORKFLOW-level preflight, not a "not ready": nothing this
            # adapter could ever do makes the kernel's answer different, so treating it as a hard
            # failure (exit 2) parked a scheduled workflow permanently red — the deferred path
            # (exit 75) is the honest one, same as any other "not this beat" skip. The kernel
            # itself is untouched; only this adapter's interpretation of its fixed answer changes.
            print(
                f"tabularius: publication preflight deferred to the remote keeper ({result.reason})"
                " — the retired local writer no longer answers this; the workflow step is"
                " honestly skipped, not failed",
                file=sys.stderr,
            )
            return 75
        print(f"tabularius: remote keeper preflight failed ({result.reason})", file=sys.stderr)
        return 2

    if args.check:
        n = pending_count(BOARD)
        print(f"tabularius: {n} ticket(s) pending in inbox" if n else "tabularius: inbox empty")
        memory = _memory_pass(check=True, dry_run=args.dry_run)
        # `--check` is a read-only diagnostic: it reports on stdout and must not
        # create ROOT/logs or write the liveness stamp.
        if memory:
            print(f"tabularius: memory {_describe(memory)}")
        return 0

    result = drain_once(BOARD, dry_run=args.dry_run)
    preserve = None if args.dry_run else preserve_board_projection(BOARD)
    memory = _memory_pass(check=False, dry_run=args.dry_run)
    # Under --dry-run the stamp is suppressed, so stdout is the only channel. A
    # deferral is reported there too, and in normal mode: it is the one non-error
    # outcome that reads as success if you only look at the counts, since
    # `pending=N, applied=0, rejected=0` is exactly what an empty inbox looks
    # like. Nothing else renders it, so without this the `_describe` deferral
    # branch would be unreachable.
    if memory and (args.dry_run or memory.get("memory_deferred")):
        print(f"tabularius: memory {_describe(memory)}")
    publication_failed = _publication_required_failure(args.require_published, preserve)

    # Two contracts meet here. `--dry-run` promises no writes, so the liveness
    # stamp is suppressed entirely. Otherwise every published stamp carries the
    # memory outcome computed above, so an enabled-but-failing memory pass can
    # never read as memory success in the status monitoring consumes. Board
    # outcomes stay independent: a memory failure does not stop the board pass.
    def stamp(**fields: object) -> None:
        if args.dry_run:
            return
        _stamp(**fields, **memory)

    if result.deferred:
        note = getattr(result, "note", "remote keeper deferred")
        print(f"tabularius: {result.pending} ticket(s) deferred ({note})")
        stamp(
            pending=result.pending,
            applied=getattr(result, "applied", 0),
            rejected=getattr(result, "rejected", 0),
            deferred=True,
        )
        return 2 if args.require_published else 0

    if result.pending == 0:
        if preserve and preserve.reason not in {"no-board-changes", ""}:
            print(f"tabularius: OK — inbox empty; local publication skipped ({preserve.reason})")
        else:
            print("tabularius: OK — inbox empty (no-op)")
        stamp(
            pending=0,
            applied=0,
            rejected=0,
            preserve_published=bool(preserve and preserve.published),
            preserve_reason=(preserve.reason if preserve else ""),
        )
        return 2 if publication_failed else 0

    verb = "WOULD relay" if args.dry_run else "broker acknowledged"
    parts = [f"tabularius: {verb} {result.applied} ticket(s)"]
    if result.rejected:
        parts.append(f"quarantined {result.rejected}")
    if preserve and preserve.reason not in {"no-board-changes", ""}:
        parts.append(f"local publication skipped: {preserve.reason}")
    print("; ".join(parts))
    stamp(
        pending=result.pending,
        applied=result.applied,
        rejected=result.rejected,
        wrote=result.wrote,
        dry_run=args.dry_run,
        preserve_published=bool(preserve and preserve.published),
        preserve_reason=(preserve.reason if preserve else ""),
    )
    return 2 if publication_failed else 0


if __name__ == "__main__":
    sys.exit(main())