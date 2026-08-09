#!/usr/bin/env python3
"""check-heal-retirement.py — predicate for self-heal task retirement.

Exit 0 ⟺ no ACTIVE HEAL task names a PR that is no longer open, outside the known-debt baseline.
Exit 1 ⟺ a fresh violation. Exit 2 ⟺ UNDERDETERMINED — the question could not be answered.

WHY THERE IS A THIRD EXIT CODE. This predicate infers that a task is retirable from the ABSENCE of
its PR in an enumerated open-PR set. That inference is only as sound as the enumeration, and the
enumeration fails in two ways that look exactly like success:

  * ``_pr_scan.enumerate_open_prs`` returns ``[]`` on ANY gh failure — auth, network, or a spent
    rate-limit pool — because failing open was right for its original caller (emit fewer tasks).
    For a RETIREMENT question that inverts: an empty set makes every task look closed. Measured
    2026-08-09 on ``main``: with the GraphQL pool at 0/5000 (``gh search`` runs on it) the
    enumeration returned **0 PRs** and this gate reported "51 active HEAL tasks name closed/merged
    PRs". None of the 51 was closed. The gate had not detected anything — it had failed to look,
    and reported that failure in the vocabulary of a finding.
  * ``gh search --limit N`` TRUNCATES silently at N, and a prefix is indistinguishable from the
    whole set. A partial result is worse than an empty one, because the total-emptiness guard in
    ``self-heal.py`` does not catch it.

Both are properties of ``gh search``, so this predicate does not use it. It enumerates over REST,
per repo, paginated — a path whose completeness is PROVABLE (pagination ends on a short page) and
which runs on the REST pool rather than the GraphQL pool the fleet exhausts. The classification
``OK | UNREACHABLE | TRUNCATED`` remains, and only ``OK`` may produce a verdict: "I could not look"
and "nothing is there" must never print the same thing. ``self-heal.py`` still needs the
estate-wide ``gh search`` enumeration for EMISSION, so its retirement pass carries the matching
guards there instead.

WHY THERE IS A BASELINE. Nothing retired HEAL tasks until the reconcile pass in ``self-heal.py``
shipped beside this gate, so the estate carries real debt: 179 of 505 active HEAL tasks on
``main``'s projection (162 of 533 on the keeper's) named merged or closed PRs. A gate that asserts
a clean state the estate has never been in is red from birth and teaches its readers to ignore it.
This follows the shrink-only ratchet the registry already uses six times over (orphan-params,
board-partition, atom-residue, session-plan, note-links, effectors): existing debt is RECORDED, new
debt FAILS, and ``--write-baseline`` refuses to grow the file.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT") or Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT / "cli" / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from limen.io import load_limen_file  # noqa: E402

OWNERS = [o.strip() for o in os.environ.get("LIMEN_OWNERS", "organvm,4444J99").split(",") if o.strip()]

# Must match self-heal.py's retirement loop exactly. A status the repair retires but the predicate
# never inspects is a hole in the gate; the reverse is a red the gate can never clear.
ACTIVE_STATUSES = {"open", "dispatched", "in_progress", "failed", "failed_blocked", "needs_human"}

BASELINE = ROOT / "institutio" / "governance" / "heal-retirement-baseline.txt"
# Runaway guard on REST pagination, not a coverage cap: pagination proves its own completeness
# by ending on a short page, so this only bounds a pathological loop. 20 pages = 2000 PRs.
MAX_PAGES = int(os.environ.get("LIMEN_HEAL_RETIREMENT_MAX_PAGES", "20"))


def baseline_ids() -> set[str]:
    if not BASELINE.exists():
        return set()
    out: set[str] = set()
    for line in BASELINE.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.add(line)
    return out


def active_heal_tasks(tasks) -> list:
    return [
        t
        for t in tasks
        if (t.id.startswith("HEAL-cifix-") or t.id.startswith("HEAL-rebase-"))
        and not t.id.startswith("HEAL-rebase-stale-")
        and t.status in ACTIVE_STATUSES
    ]


def open_pr_set() -> tuple[set[tuple[str, int]], str]:
    """``(open_prs, state)`` where state is ``OK`` | ``UNREACHABLE`` | ``TRUNCATED``.

    Enumerated over REST, per repo, paginated — deliberately NOT through ``gh search``:

      * **Completeness is provable.** REST pagination ends on a short page, so "I have them all"
        is something this function can demonstrate rather than assume. ``gh search --limit N``
        can only ever return a prefix, and a prefix is indistinguishable from the whole set —
        which for a predicate that reads ABSENCE as closure is the difference between a verdict
        and a guess.
      * **It survives the pool that the fleet actually exhausts.** ``gh search`` runs on GraphQL.
        Measured 2026-08-09 with two lanes sweeping PRs: ``graphql 0/5000`` while ``core
        4887/5000`` — so the search path returned an empty list for hours while REST was fine.
        A gate that goes dark whenever the fleet is busy is a gate nobody can trust.
      * **The scope makes it cheap.** This predicate only judges ``organvm/limen`` tasks, so it
        enumerates that one repo: 175 open PRs, two pages.

    No author filter: a HEAL task can name a PR opened by anyone (dependabot, a collaborator), and
    filtering to the current actor would make those PRs invisible — that is, retirable — while they
    are still open.
    """
    prs: set[tuple[str, int]] = set()
    for repo in ("organvm/limen",):  # the repos find_violations judges; widen both together
        page = 1
        while True:
            r = subprocess.run(
                ["gh", "api", f"repos/{repo}/pulls?state=open&per_page=100&page={page}"],
                capture_output=True,
                text=True,
                timeout=90,
            )
            if r.returncode != 0:
                return set(), "UNREACHABLE"
            try:
                rows = json.loads(r.stdout or "[]")
            except json.JSONDecodeError:
                return set(), "UNREACHABLE"
            prs.update((repo, p["number"]) for p in rows)
            if len(rows) < 100:  # a short page proves the enumeration is exhausted
                break
            page += 1
            if page > MAX_PAGES:  # runaway guard; a prefix must never pass as complete
                return prs, "TRUNCATED"
    if not prs:
        return set(), "UNREACHABLE"
    return prs, "OK"


def find_violations(tasks, open_set: set[tuple[str, int]]) -> list[tuple[str, str, int, str]]:
    out = []
    for t in active_heal_tasks(tasks):
        parts = t.id.split("-")
        if not parts[-1].isdigit():
            continue
        num, repo = int(parts[-1]), (t.repo or "")
        if repo == "organvm/limen" and (repo, num) not in open_set:
            out.append((t.id, repo, num, t.status))
    return out


def main() -> int:
    quiet = "--quiet" in sys.argv
    tasks_path = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
    if not tasks_path.exists():
        if not quiet:
            print("[check-heal-retirement] tasks.yaml missing")
        return 0

    lf = load_limen_file(tasks_path)
    active = active_heal_tasks(lf.tasks)
    if not active:
        if not quiet:
            print("[check-heal-retirement] exit 0: 0 active HEAL tasks")
        return 0

    open_set, state = open_pr_set()
    if state != "OK":
        # Never render "I could not enumerate" as "those PRs are closed".
        print(
            f"[check-heal-retirement] UNDERDETERMINED ({state}): the open-PR enumeration is not a "
            f"complete answer ({len(open_set)} PRs), so absence from it proves "
            "nothing. Flagging nothing. "
            + (
                "Check `gh auth status` and `gh api rate_limit`."
                if state == "UNREACHABLE"
                else "Raise LIMEN_HEAL_RETIREMENT_MAX_PAGES — pagination did not terminate."
            ),
            file=sys.stderr,
        )
        return 2

    violations = find_violations(lf.tasks, open_set)
    base = baseline_ids()

    if "--write-baseline" in sys.argv:
        recorded = sorted({v[0] for v in violations} | base)
        if base and len(recorded) > len(base):
            print(
                f"refusing: baseline would GROW {len(base)} → {len(recorded)}. The ratchet is "
                "shrink-only — retire the new violation instead of recording it.",
                file=sys.stderr,
            )
            return 2
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            "# HEAL tasks naming a non-open PR when the retirement gate shipped (2026-08-09).\n"
            "# SHRINK-ONLY: --write-baseline refuses to grow this file. A line leaves when the task\n"
            "# is genuinely retired by self-heal.py's reconcile pass, never to silence a fresh one.\n"
            + "".join(f"{i}\n" for i in recorded),
            encoding="utf-8",
        )
        print(f"[check-heal-retirement] baseline written: {len(recorded)} id(s) → {BASELINE}")
        return 0

    fresh = [v for v in violations if v[0] not in base]
    if fresh:
        # Printed even under --quiet: a gate whose failure reason is suppressed shows up in CI as a
        # bare FAIL with no diagnostic, which is how this gate first landed red.
        print(f"[check-heal-retirement] FAIL: {len(fresh)} active HEAL task(s) name closed/merged PRs:")
        for tid, repo, num, st in fresh[:10]:
            print(f"    {tid} ({repo}#{num}, status={st})")
        if len(fresh) > 10:
            print(f"    … and {len(fresh) - 10} more")
        return 1

    if not quiet:
        print(
            f"[check-heal-retirement] exit 0: {len(active)} active HEAL task(s); "
            f"{len(violations)} known-debt baselined, 0 fresh"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
