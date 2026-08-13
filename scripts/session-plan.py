#!/usr/bin/env python3
"""session-plan.py — the plan→issue→PR chain, as one command.

THE FRONT DOOR. ``session-phases.yaml`` declares that the ``plan`` phase (stage SHAPE)
``produces:`` a dated plan file — and then stops. Nothing carries that file to a GitHub
issue or to the PR that implements it, so plans accumulate unlinked (19 in ``docs/plans/``
at the time of writing, none citing an issue, none citing an implementing PR, and no way
to answer "which of these were actually built?").

This is the ``ship-docs.sh`` lesson applied one joint upstream: that script exists because
the ``docs:`` class bypassed PRs on 35 of 40 commits until a *single command* made the
front door cheaper than the side door. A plan → issue → PR chain that costs three manual
steps gets skipped exactly the same way. So it costs one:

    scripts/session-plan.py open <slug> --title "..." --issue 1843   # plan file + branch + PR
    scripts/session-plan.py close <slug> --pr 1234                   # stamp the implementing PR
    scripts/session-plan.py audit                                    # chain state for every plan

**This organ never writes to GitHub in-process.** `open` without `--issue` prints the exact
`gh issue create` to run and exits 2; `close` prints the `gh issue close`. That is deliberate:
`check-effectors.py` Class C is an AST walk that catches outward `gh` argv built inside Python,
because a PreToolUse(Bash) hook sees a command *string* and can never see `subprocess.run(["gh",
…])`. Its baseline is explicitly shrink-only, so a new organ does not get to add itself to the
blind list merely because two sibling issue-syncers are already on it. One extra step buys every
outward write staying on the rail the estate's hooks can actually reach.

``Issue:`` is the tracked issue for the work. ``PR:`` is the PR that *implements* the plan,
not the PR that ships the plan document — those are different artifacts, and conflating them
is what makes "was this plan implemented?" unanswerable. ``PR:`` is therefore ``(pending)``
between ``open`` and ``close``, which is a legitimate steady state and is what
``check-session-phase.py`` accepts while the issue is open.

Read-only unless ``open``/``close`` is invoked. Never overwrites an existing plan (plan
discipline: a same-slug plan on the same day gets a ``-v2`` suffix, never a silent clobber).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

# ROOT is bound to __file__, NOT to $LIMEN_ROOT, and that is deliberate: this organ and the
# `session-phase` gate built on it must judge the tree they were invoked from. A worktree runs
# verify-scoped with LIMEN_ROOT still exported to the live checkout (scripts/drain.sh:11,
# scripts/cells.sh:324 both set it), so honouring the variable would gate the WRONG tree —
# green on the live checkout while the worktree's own plan is malformed.
#
# The trap is that ignoring it silently is indistinguishable from agreeing with it. A probe run
# as `LIMEN_ROOT=/some/copy check-session-phase.py` returned `PASS — 15 plans`, byte-identical to
# the unmutated run, because the copy was never opened — the estate's own "I found nothing" and
# "I read nothing" collision. So the override is refused OUT LOUD rather than obeyed or ignored.
ROOT = Path(__file__).resolve().parent.parent

_env_root = os.environ.get("LIMEN_ROOT")
if _env_root and Path(_env_root).resolve() != ROOT:
    print(
        f"session-plan: NOTE — $LIMEN_ROOT={_env_root} is set but NOT used; this organ and the "
        f"session-phase gate always judge their own tree ({ROOT}). Run the copy's own checkout of "
        "this script to inspect a different tree.",
        file=sys.stderr,
    )

PLANS = ROOT / "docs" / "plans"
BASELINE = ROOT / "institutio" / "governance" / "session-plan-baseline.txt"

PLAN_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)\.md$")
# `[ \t]*$`, never `\s*$`: under re.MULTILINE, `\s*` is greedy across newlines and `$` happily
# matches at the end of a later blank line, so a `.sub()` that stamps `PR:` swallows the blank
# line separating the header from the first `##` heading. Observed on this file's own first
# stamp. Horizontal whitespace only — the line terminator is a delimiter, not content.
ISSUE_RE = re.compile(r"^Issue:[ \t]*#?(\d+|TBD)[ \t]*$", re.MULTILINE)
PR_RE = re.compile(r"^PR:[ \t]*(?:#(\d+)|\((pending)\)|(TBD))[ \t]*$", re.MULTILINE)
STATUS_RE = re.compile(r"^Status:[ \t]*(superseded|abandoned|folded)\b[ \t]*(.*)$", re.MULTILINE)

PENDING = "(pending)"

TEMPLATE = """# {title}

Issue: #{issue}
PR: {pr}

## Context

{objective}

## Resolved design decisions

- **D1 — ** (state the decision and the reason it beat the alternative)

## Steps

1.

## Premortem

- **What most plausibly makes this wrong or unwelcome?**

## Verification

- `bash scripts/verify-scoped.sh`
"""


class ChainError(RuntimeError):
    """A step in the plan→issue→PR chain could not be completed."""


def _today() -> str:
    """LOCAL date, deliberately — not UTC.

    A plan filename is a human-facing day marker that has to agree with the operator's day
    and with the date-sorted reading of `docs/plans/`. Under UTC, any session after ~20:00
    EDT files *tomorrow's* plan — caught by this script's own dry-run on 2026-08-05, which
    proposed `2026-08-06-…`. Machine-facing stamps elsewhere (ship-docs.sh branch suffixes)
    correctly stay UTC; this one is not machine-facing.
    """
    return _dt.datetime.now().astimezone().strftime("%Y-%m-%d")


def plan_path_for(slug: str, *, day: str | None = None) -> Path:
    """Resolve the next free plan path for ``slug``.

    Plan discipline (``~/.config/ai-context/plan-discipline.md``): a plan is never
    overwritten. A second plan for the same slug on the same day becomes ``-v2``, ``-v3``…
    """
    day = day or _today()
    base = PLANS / f"{day}-{slug}.md"
    if not base.exists():
        return base
    for n in range(2, 100):
        candidate = PLANS / f"{day}-{slug}-v{n}.md"
        if not candidate.exists():
            return candidate
    raise ChainError(f"refusing to mint a 100th revision of {slug} on {day}")


def find_plan(slug: str) -> Path:
    """Newest plan file whose slug matches, across all dates and revisions."""
    matches = sorted(
        (p for p in PLANS.glob("*.md") if (m := PLAN_NAME_RE.match(p.name)) and m.group(2).split("-v")[0] == slug),
        key=lambda p: p.name,
    )
    if not matches:
        raise ChainError(f"no plan found for slug '{slug}' in {PLANS.relative_to(ROOT)}/")
    return matches[-1]


def read_chain(path: Path) -> dict[str, object]:
    """Extract the declared chain state from a plan file. Pure text — no network."""
    text = path.read_text(encoding="utf-8")
    issue_m = ISSUE_RE.search(text)
    pr_m = PR_RE.search(text)
    status_m = STATUS_RE.search(text)
    issue = issue_m.group(1) if issue_m else None
    return {
        "plan": str(path.relative_to(ROOT)),
        "issue": None if issue in (None, "TBD") else int(issue),
        "issue_declared": issue_m is not None,
        "pr": int(pr_m.group(1)) if (pr_m and pr_m.group(1)) else None,
        "pr_declared": pr_m is not None,
        "pr_pending": bool(pr_m and not pr_m.group(1)),
        "status": status_m.group(1) if status_m else None,
        "status_reason": (status_m.group(2).strip() if status_m else ""),
    }


def baseline_names() -> set[str]:
    if not BASELINE.exists():
        return set()
    return {
        ln.strip()
        for ln in BASELINE.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    }


def all_plans() -> list[Path]:
    return sorted(p for p in PLANS.glob("*.md") if PLAN_NAME_RE.match(p.name))


# ── open ────────────────────────────────────────────────────────────────────


def cmd_open(args: argparse.Namespace) -> int:
    slug = args.slug
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
        raise ChainError("slug must be lowercase kebab-case")

    title = args.title
    if args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8")
    else:
        body = None
    objective = args.objective or "_(fill in: the real problem this plan engages)_"

    path = plan_path_for(slug)
    rel = path.relative_to(ROOT)

    if args.issue is None:
        print(_issue_recipe(title=title, objective=objective, rel=rel, slug=slug))
        return 2

    issue_num = str(args.issue)

    if args.dry_run:
        print(f"session-plan: DRY RUN\n  plan  → {rel}\n  issue → #{issue_num} (already open)")
        return 0

    if body is None:
        content = TEMPLATE.format(title=title, issue=issue_num, pr=PENDING, objective=objective)
    else:
        content = _stamp_header(body, title=title, issue=issue_num)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"session-plan: wrote {rel}")

    if args.no_ship:
        print("session-plan: --no-ship — commit and PR the plan yourself (charter § No side doors)")
        return 0

    ship = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [str(ROOT / "scripts" / "ship-docs.sh"), slug, f"docs(plan): {title}", str(rel)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    sys.stdout.write(ship.stdout)
    sys.stderr.write(ship.stderr)
    if ship.returncode not in (0, 2):
        raise ChainError(f"ship-docs.sh refused the plan (exit {ship.returncode})")
    print(f"session-plan: chain open — issue #{issue_num}, plan {rel}, PR {PENDING} until `close`")
    return 0


def _issue_recipe(*, title: str, objective: str, rel: Path, slug: str) -> str:
    """The exact `gh issue create` to run, printed rather than executed. Deliberate.

    This organ does NOT create the issue in-process. `scripts/check-effectors.py` Class C is
    an AST walk that catches outward `gh` argv built inside Python, because a PreToolUse(Bash)
    hook sees a command *string* and can never see `subprocess.run(["gh", …])`. The remedy the
    OUTBOUND-EFFECTORS registry states is "route the sender through the receipt check", and its
    baseline is explicitly shrink-only — so a new organ must not add itself to the blind list
    just because two sibling issue-syncers are already on it.

    Printing the command keeps every outward write on the guarded Bash rail where the estate's
    existing hooks can actually reach it, at the cost of one extra step. Shelling the same call
    out to a bash helper would silence the Python-only scanner while the blindness stayed
    identical — that is gate evasion, not a fix.
    """
    body = (
        f"{objective}\n\n"
        f"Plan artifact: `{rel}` (opened by `scripts/session-plan.py`).\n\n"
        "This issue is the tracked owner of the work. The plan's `PR:` line is stamped by "
        "`scripts/session-plan.py close` when the implementing PR lands; `scripts/check-session-phase.py` "
        "is the predicate that holds the chain together."
    )
    # shlex.quote, not repr: repr renders a newline as a literal backslash-n, which no shell
    # expands — the issue body would arrive with visible `\n` in it. shlex.quote preserves the
    # real newlines inside a single-quoted argument.
    return (
        "session-plan: --issue is required. Create it on the guarded Bash rail, then re-run:\n\n"
        f"  gh issue create --label plan --title {shlex.quote(title)} \\\n"
        f"    --body {shlex.quote(body)}\n\n"
        f"  scripts/session-plan.py open {slug} --title {shlex.quote(title)} --issue <N>\n"
    )


def _stamp_header(body: str, *, title: str, issue: str) -> str:
    """Insert/refresh the Issue:/PR: header block just under the plan's H1.

    The H1 is SYNTHESIZED when the body has none, and the block always ends with a blank line.
    Both were defects, found on this organ's second real use by reading the file it had just
    written (`--body-file`, the path the scaffold never exercises):

      · a body written the natural way — starting at `## Context`, no H1, because `--title` is a
        required argument and looks like it owns the title — drove `insert_at` to 0. The header
        landed above everything, the file began with a blank line, and the title was discarded
        entirely. A required argument must never be silently dropped.
      · nothing guaranteed a blank line after `PR:`, so the header ran straight into the first
        `##` heading and every markdown reader concatenated them.
    """
    body = ISSUE_RE.sub(f"Issue: #{issue}", body, count=1)
    if not ISSUE_RE.search(body):
        lines = body.splitlines()
        if not lines or not lines[0].startswith("# "):
            lines = [f"# {title}", *lines]
        insert_at = 1
        lines[insert_at:insert_at] = ["", f"Issue: #{issue}", f"PR: {PENDING}"]
        after = insert_at + 3
        if len(lines) > after and lines[after].strip():
            lines.insert(after, "")
        body = "\n".join(lines)
    elif not PR_RE.search(body):
        body = body.replace(f"Issue: #{issue}", f"Issue: #{issue}\nPR: {PENDING}", 1)
    return body if body.endswith("\n") else body + "\n"


# ── close ───────────────────────────────────────────────────────────────────


def cmd_close(args: argparse.Namespace) -> int:
    path = find_plan(args.slug)
    chain = read_chain(path)
    text = path.read_text(encoding="utf-8")

    if args.status:
        replacement = f"PR: {PENDING}\nStatus: {args.status} — {args.reason or 'no reason given'}"
        new = PR_RE.sub(replacement, text, count=1) if chain["pr_declared"] else text
        verb = f"dispositioned {args.status}"
    else:
        new = PR_RE.sub(f"PR: #{args.pr}", text, count=1)
        if not chain["pr_declared"]:
            raise ChainError(f"{path.name} has no `PR:` line to stamp — was it opened by session-plan.py?")
        verb = f"stamped PR #{args.pr}"

    if new == text:
        print(f"session-plan: {path.name} already {verb} — no change")
        return 0
    path.write_text(new, encoding="utf-8")
    print(f"session-plan: {verb} in {path.relative_to(ROOT)}")

    issue = chain["issue"]
    if issue:
        note = (
            f"Implemented in #{args.pr}."
            if args.pr
            else f"Closed as {args.status}: {args.reason or 'no reason given'}."
        )
        # Printed, never executed — same rail discipline as `open`; see _issue_recipe().
        print(
            "\n  Close the tracked issue on the guarded Bash rail:\n"
            f"    gh issue close {issue} --comment {shlex.quote(note)}"
        )
    return 0


# ── audit ───────────────────────────────────────────────────────────────────


def cmd_audit(args: argparse.Namespace) -> int:
    base = baseline_names()
    rows = []
    for path in all_plans():
        chain = read_chain(path)
        chain["baselined"] = path.name in base
        rows.append(chain)

    if args.json:
        print(json.dumps(rows, indent=2))
        return 0

    held = [r for r in rows if not r["baselined"]]
    print(f"session-plan: {len(rows)} plans · {len(base)} baselined · {len(held)} held to the chain")
    for r in held:
        issue = f"#{r['issue']}" if r["issue"] else "MISSING"
        if r["status"]:
            pr = r["status"]
        elif r["pr"]:
            pr = f"#{r['pr']}"
        else:
            pr = PENDING if r["pr_pending"] else "MISSING"
        print(
            f"  {'ok ' if r['issue'] and (r['pr'] or r['pr_pending'] or r['status']) else 'GAP'} "
            f"issue={issue:<8} pr={pr:<12} {r['plan']}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_open = sub.add_parser("open", help="write the plan against an existing issue, ship the PR")
    p_open.add_argument("slug", help="lowercase kebab-case slug")
    p_open.add_argument("--title", required=True, help="issue + plan H1 title")
    p_open.add_argument("--issue", type=int, help="the tracked issue; omitted → prints the exact gh command (exit 2)")
    p_open.add_argument("--objective", help="the real problem this plan engages (goes in the issue body)")
    p_open.add_argument("--body-file", help="use this file as the plan body instead of the scaffold")
    p_open.add_argument("--no-ship", action="store_true", help="write the plan, skip ship-docs.sh")
    p_open.add_argument("--dry-run", action="store_true", help="print what would happen; touch nothing")
    p_open.set_defaults(fn=cmd_open)

    p_close = sub.add_parser("close", help="stamp the implementing PR (or disposition the plan)")
    p_close.add_argument("slug")
    p_close.add_argument("--pr", type=int, help="the PR that implements this plan")
    p_close.add_argument("--status", choices=("superseded", "abandoned", "folded"), help="disposition instead")
    p_close.add_argument("--reason", help="required with --status")
    p_close.set_defaults(fn=cmd_close)

    p_audit = sub.add_parser("audit", help="chain state for every plan")
    p_audit.add_argument("--json", action="store_true")
    p_audit.set_defaults(fn=cmd_audit)

    args = ap.parse_args(argv)
    if args.cmd == "close" and not args.pr and not args.status:
        ap.error("close needs --pr N or --status <disposition> --reason ...")
    try:
        return args.fn(args)
    except ChainError as exc:
        print(f"session-plan: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
