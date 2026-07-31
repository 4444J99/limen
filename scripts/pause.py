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
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT") or Path(__file__).resolve().parents[1])
MARKER = ROOT / "logs" / "AUTONOMY_PAUSED"

# Emitted in this stable order; only non-empty fields are written. `class`/`reason` always present
# (arm requires them); at least one of pr/owner/next_command is guaranteed by _validate.
_ORDER = (
    "class",
    "reason",
    "created_at",
    "expires_at",
    "source_of_intent",
    "authorised_by",
    "owner_surface",
    "owner",
    "pr",
    "repo",
    "prohibitions",
    "release_predicate",
    "next_command",
)

# A pause is a GLOBAL halt on a fleet the operator owns. Until now anything with shell access could
# impose one with no identity, no provenance, and no expiry, into a gitignored file — so no artifact
# recorded who did it. On 2026-07-27 an agent armed one from a plan document authored by a PREVIOUS
# agent, framed to it as "the source of user intent". The operator had said no such thing. It stood
# for four days and, because the beat's paused branch also skipped sensing, cost four days of
# blindness (drift to 27 commits behind origin/main; an unswept inbox; a redundant email to a live
# recruiter). See docs/runbooks/ and PR #1713.
#
# The rule: an AGENT may arm a pause only by naming the HUMAN authority for it. A plan, a doc, a
# previous agent's conclusion, or its own inference is not authority — those are the exact shapes
# that laundered intent into a halt. Every marker also expires; an unbounded halt is how four days
# happen without anyone deciding on four days.
_MAX_TTL_HOURS = 168  # 7d — a pause needing longer is a decision someone should make again, out loud

# Substrings that indicate an agent is citing a DOCUMENT rather than a person. Intent laundering
# looks exactly like this, so it is refused by name.
_NOT_AUTHORITY = ("plan", "continuation", "docs/", ".md", "agent", "session", "plan-mode", "task")


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

    # PROVENANCE — who decided this, and on whose authority.
    intent = fields.get("source_of_intent", "")
    if intent not in ("human", "agent"):
        problems.append(f"source_of_intent must be 'human' or 'agent' (got {intent!r}) — there is no default")
    authority = fields.get("authorised_by", "")
    if not authority:
        problems.append("authorised_by is required — a halt with no named authority is how 2026-07-27 happened")
    elif intent == "agent":
        lowered = authority.lower()
        cited_doc = next((token for token in _NOT_AUTHORITY if token in lowered), None)
        if cited_doc:
            problems.append(
                f"authorised_by cites {cited_doc!r} — a plan, doc, session, or previous agent is NOT "
                "authority. An agent may arm a pause only by naming the human who asked for it, in "
                "their own words. Quote them."
            )
    return problems


def _render(fields: dict[str, str]) -> str:
    return "".join(f"{name}: {fields[name]}\n" for name in _ORDER if fields.get(name))


def _write_atomic(marker: Path, text: str) -> None:
    marker.parent.mkdir(parents=True, exist_ok=True)
    tmp = marker.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, marker)  # atomic on POSIX — a reader sees the old marker or the new, never a splice


def _parse_marker(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if ":" in line:
            name, _, value = line.partition(":")
            out[name.strip()] = value.strip()
    return out


def is_expired(fields: dict[str, str], now: datetime | None = None) -> bool:
    """True when the marker declares an expiry that has passed.

    Read by autonomy-governor so an expired marker is an ABSENT marker. A halt nobody renews is a
    halt nobody is still choosing — the 2026-07-27 marker stood for four days precisely because
    standing cost nothing. Fail toward caution: an unparseable or absent expiry is NOT expired, so
    a malformed marker still pauses.
    """
    raw = fields.get("expires_at", "").strip()
    if not raw:
        return False
    try:
        expiry = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return (now or datetime.now(timezone.utc)) >= expiry


def cmd_release(args: argparse.Namespace) -> int:
    """Lift a pause, leaving a receipt.

    `arm` shipped without a counterpart: the tool could impose a global halt and had no way to lift
    one. Release happened only by hand-rm, or by autonomy-governor's autoclear — which fires when a
    PR named by `owner:` merges REGARDLESS of what release_predicate says. So the only two ways to
    end a halt were untraceable or accidental. This is the third: deliberate, attributed, recorded.
    """
    if not MARKER.exists():
        print(f"pause release: nothing to do — {MARKER} does not exist")
        return 0
    text = MARKER.read_text(encoding="utf-8")
    fields = _parse_marker(text)

    receipts = ROOT / "logs" / "pause-receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    receipt = receipts / f"release-{stamp}.json"
    receipt.write_text(
        json.dumps(
            {
                "schema": "limen.pause_release.v1",
                "released_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "released_by": _clean(args.released_by),
                "reason": _clean(args.reason),
                "marker_was": fields,
                "marker_raw": text,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    MARKER.unlink()
    print(f"pause release: lifted {MARKER}")
    print(f"  receipt: {receipt}")
    print(f"  released_by: {_clean(args.released_by)}")
    print(f"  reason: {_clean(args.reason)}")
    print("  the marker it lifted:")
    for line in text.splitlines():
        print(f"    {line}")
    return 0


def cmd_arm(args: argparse.Namespace) -> int:
    ttl = max(1, min(int(args.ttl_hours), _MAX_TTL_HOURS))
    fields = {
        "class": args.klass,
        "reason": _clean(args.reason),
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=ttl)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_of_intent": args.source_of_intent or "",
        "authorised_by": _clean(args.authorised_by),
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
    arm.add_argument(
        "--class",
        dest="klass",
        choices=("fence", "wall"),
        required=True,
        help="fence = peer-coordination (insulated work proceeds); wall = safety halt",
    )
    arm.add_argument("--reason", required=True, help="human-readable why (required)")
    arm.add_argument("--pr", default="", help="release coordinate: PR number (autoclears on merge)")
    arm.add_argument("--owner", default="", help="release coordinate: PR head branch (autoclears on merge)")
    arm.add_argument(
        "--next-command", dest="next_command", default="", help="release runbook: a machine-executable recovery command"
    )
    arm.add_argument("--prohibitions", default="", help="what the pause forbids (e.g. 'no merges; no sends')")
    arm.add_argument(
        "--owner-surface", dest="owner_surface", default="", help="human owner context (never a coordinate)"
    )
    arm.add_argument("--release-predicate", dest="release_predicate", default="", help="human release condition")
    arm.add_argument("--repo", default="", help="repository identifier (optional)")
    arm.add_argument("--force", action="store_true", help="overwrite an existing marker (own it first)")
    arm.add_argument(
        "--source-of-intent",
        dest="source_of_intent",
        choices=("human", "agent"),
        required=True,
        help="who decided this halt. No default — an unattributed global halt is the 2026-07-27 defect",
    )
    arm.add_argument(
        "--authorised-by",
        dest="authorised_by",
        required=True,
        help="the HUMAN authority, quoted. For --source-of-intent agent this may not cite a plan, "
        "doc, session, or previous agent — those are laundered intent, not authority",
    )
    arm.add_argument(
        "--ttl-hours",
        dest="ttl_hours",
        type=int,
        default=24,
        help=f"hours until the marker expires (max {_MAX_TTL_HOURS}); an expired marker is an absent marker",
    )
    arm.set_defaults(func=cmd_arm)

    rel = sub.add_parser("release", help="lift a marker, leaving a receipt")
    rel.add_argument("--released-by", dest="released_by", required=True, help="who lifted it, and on whose authority")
    rel.add_argument("--reason", required=True, help="why it is being lifted")
    rel.set_defaults(func=cmd_release)
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
