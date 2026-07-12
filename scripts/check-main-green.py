#!/usr/bin/env python3
"""Trunk-green invariant — detect (and optionally heal) a RED main, so it can never sit broken.

The gap this closes (2026-07-10): main's REQUIRED ``pr-gate`` silently went red (non-hermetic tests)
and *nothing detected it*. It blocked every PR until a human noticed and a reactive lane fixed it —
in parallel with a duplicate fix. Beat sensors watch creds / cartridge / lanes / ship-artifacts, but
none watched whether **main's own CI is green**.

Signal. ``pr-gate.yml`` runs on ``pull_request`` only, so it never runs on main. ``ci.yml`` runs on
``push: [main]`` with the SAME pytest suite — so the latest completed ``CI`` run on main is the
trunk-health proxy for pr-gate. This sensor reads it (`gh run list --workflow ci.yml -b main`), and:

- **DETECT (always on):** on a RED verdict it exits non-zero so the beat surfaces ``↑ main trunk RED``
  — closing the silence gap. Verdict is cached (throttled `gh`) so it surfaces every beat cheaply.
- **HEAL (dark until armed, ``LIMEN_MAIN_GREEN_APPLY=1``):** emit ONE idempotent, SYMPTOM-scoped
  ``HEAL-mainred-organvm-limen`` task via the daemon's queue-lock (the same safe shared-append path
  self-heal.py uses) — a single canonical task all lanes converge on, closing the duplicate-work gap.
  The id is scoped to the symptom (trunk is red), NOT the head SHA, so a *moving* red trunk (new
  commits while it stays broken) converges on ONE task instead of spawning a fresh task per SHA
  (limen#895); the SHA lives in the title/context. Observable-before-autonomous: detection ships
  armed, emission ships dark.

- **BLAST RADIUS + WEDGE (integrated from PR #882):** the ci.yml verdict says WHETHER trunk is red;
  a scan of open PRs says HOW MANY fresh PRs it is actually blocking and on which required check
  (``wedged_prs`` on ``wedged_checks``). This quantifies the RED alarm's urgency AND catches a wedge
  that persists when ci.yml looks green — a required check diverging from ci.yml / branch-protection
  drift — which the trunk-only read cannot see. Only FRESH PRs count (chronic stale backlog excluded).

Fail-open: no ``gh`` / offline / parse error → exit 0 (never breaks the beat).

  python3 scripts/check-main-green.py             # detect + surface (+ emit if APPLY=1)
  python3 scripts/check-main-green.py --dry-run    # detect + report only, never emit
  python3 scripts/check-main-green.py --throttle 900
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.io import load_limen_file, save_limen_file  # noqa: E402
from limen.intake import IntakeContractError, contract_fields, github_main_green_contract  # noqa: E402
from limen.models import Task  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
LOCKD = ROOT / "logs" / ".queue.lock.d"
STAMP = ROOT / "logs" / "main-green.json"
WORKFLOW = os.environ.get("LIMEN_MAIN_GREEN_WORKFLOW", "ci.yml")
REPO = os.environ.get("LIMEN_MAIN_GREEN_REPO", "organvm/limen")
RED = {"failure", "cancelled", "timed_out", "startup_failure"}
# Blast-radius / queue-wedge signal (integrated from PR #882): the ci.yml-on-main verdict says WHETHER
# trunk is red; this says HOW MANY PRs it is actually blocking and on which check — and catches a wedge
# that persists even when ci.yml looks green (a required check diverging from ci.yml / branch-protection
# drift). Only FRESH PRs count so the chronic stale-PR backlog is not mistaken for an acute break.
WEDGE_K = int(os.environ.get("LIMEN_MAIN_GREEN_WEDGE_K", "5"))
FRESH_HOURS = int(os.environ.get("LIMEN_MAIN_GREEN_FRESH_HOURS", "36"))
BAD_CHECK = {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "STARTUP_FAILURE"}
# Mirrors limen.dispatch._ACTIVE_SUPERSEDER_STATUSES (parity asserted in test_check_main_green.py so a
# drift is a red test, not silent). A HEAL-mainred singleton in one of these states is already being
# worked → converge on it. Any OTHER state (done/archived/failed) is a PRIOR red episode that healed;
# a fresh red trunk RE-OPENS the same ticket so a recurrence is never dropped by a stale done-row.
# (Kept local — mirrored not imported — so this beat-script stays light and does not pull in dispatch.)
_ACTIVE_STATES = frozenset({"open", "dispatched", "in_progress", "needs_human", "failed_blocked"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gh_main_runs() -> list[dict] | None:
    """Recent CI workflow runs on main, or ``None`` when GitHub is unavailable.

    Workflow selection belongs here rather than in callers such as ``omega.sh``.  Keeping the
    query and its completed-push filtering in one module prevents a newer unrelated workflow run
    (validate, deploy, conductor report, ...) from being mistaken for trunk CI.
    """
    try:
        out = subprocess.run(
            [
                "gh",
                "run",
                "list",
                "--repo",
                REPO,
                "--workflow",
                WORKFLOW,
                "--branch",
                "main",
                "--limit",
                "8",
                "--json",
                "databaseId,conclusion,status,headSha,url,event",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if out.returncode != 0:
            return None
        runs = json.loads(out.stdout or "[]")
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return [run for run in runs if isinstance(run, dict)]


def select_completed_push_run(runs: list[dict], *, head_sha: str | None = None) -> dict | None:
    """Select the newest completed push run, optionally for one exact commit.

    ``gh run list`` is newest-first.  Matching the full ``headSha`` is intentional: a green run for
    the previous main commit is not evidence for the current head, and abbreviated hashes are not a
    sufficient identity contract.
    """
    for run in runs:
        if run.get("event") != "push" or run.get("status") != "completed":
            continue
        if head_sha is not None and run.get("headSha") != head_sha:
            continue
        return run
    return None


def _gh_latest_main_run() -> dict | None:
    """Latest COMPLETED CI run on main (push event). None on any error → caller fails open."""
    runs = _gh_main_runs()
    return select_completed_push_run(runs) if runs is not None else None


def _remote_main_head() -> str | None:
    """Return the remote owner's full ``main`` identity without mutating local refs.

    ``origin/main`` is only a cache and may lag GitHub indefinitely. ``ls-remote`` reads the
    canonical remote ref without fetching objects or changing the checkout, so an old green local
    tracking ref can never prove the current remote head.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "ls-remote", "--exit-code", "origin", "refs/heads/main"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    fields = (out.stdout or "").strip().split()
    if out.returncode != 0 or len(fields) != 2 or fields[1] != "refs/heads/main":
        return None
    head = fields[0]
    return head if len(head) == 40 and all(char in "0123456789abcdef" for char in head.lower()) else None


def exact_head_check() -> int:
    """Fail closed unless current remote ``main`` has a successful completed CI push run.

    This is Omega's live main-green predicate.  It deliberately bypasses the throttle cache and
    wedge/task-emission logic: a cached prior head cannot prove the current head, and a predicate
    must not mutate board state while checking it.
    """
    head = _remote_main_head()
    if head is None:
        print("check-main-green: EXACT-HEAD FAIL — remote main is unavailable")
        return 1
    runs = _gh_main_runs()
    if runs is None:
        print(f"check-main-green: EXACT-HEAD FAIL — GitHub CI runs unavailable for {head}")
        return 1
    run = select_completed_push_run(runs, head_sha=head)
    if run is None:
        print(f"check-main-green: EXACT-HEAD FAIL — no completed {WORKFLOW} push run for {head}")
        return 1
    conclusion = str(run.get("conclusion") or "unknown")
    url = str(run.get("url") or "")
    if conclusion != "success":
        print(f"check-main-green: EXACT-HEAD RED — {WORKFLOW} {conclusion} @ {head} ({url})")
        return 1
    print(f"check-main-green: EXACT-HEAD GREEN — {WORKFLOW} success @ {head} ({url})")
    return 0


def _gh_json(args: list[str], default):
    """gh → parsed JSON, or `default` on any error (fail-open — a probe outage never breaks the beat)."""
    try:
        out = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return default
    if out.returncode != 0:
        return default
    try:
        return json.loads(out.stdout or "")
    except ValueError:
        return default


def required_checks() -> set[str]:
    """The required status-check contexts on main's branch protection (fallback: pr-gate)."""
    data = _gh_json(["api", f"repos/{REPO}/branches/main/protection/required_status_checks"], {})
    ctx = set(data.get("contexts") or []) if isinstance(data, dict) else set()
    return ctx or {"pr-gate"}


def failing_required_checks(pr: dict, required: set[str]) -> set[str]:
    """The required checks that are FAILING/errored on this PR (check-runs `conclusion` or legacy `state`)."""
    out: set[str] = set()
    for c in pr.get("statusCheckRollup") or []:
        name = c.get("name") or c.get("context") or ""
        concl = (c.get("conclusion") or c.get("state") or "").upper()
        if name in required and concl in BAD_CHECK:
            out.add(name)
    return out


def wedge_impact(prs: list[dict], required: set[str], fresh_since: str | None, k: int) -> dict:
    """Pure: among FRESH non-draft open PRs, count those failing each required check.

    `wedged_checks` = checks failing on >= k FRESH PRs (the acute trunk-wedge fingerprint, not the
    chronic stale-PR pile). `wedged_prs` = the largest such count = the blast radius. UTC 'Z'
    timestamps compare lexicographically, so no parsing.
    """
    counts: Counter[str] = Counter()
    considered = 0
    for pr in prs:
        if pr.get("isDraft"):
            continue
        if fresh_since and str(pr.get("updatedAt", "")) < fresh_since:
            continue
        considered += 1
        for chk in failing_required_checks(pr, required):
            counts[chk] += 1
    wedged = {c: n for c, n in counts.items() if n >= k}
    return {
        "considered": considered,
        "wedged_checks": wedged,
        "wedged_prs": max(wedged.values(), default=0),
    }


def open_pr_impact(fresh_hours: int = FRESH_HOURS, k: int = WEDGE_K) -> dict:
    """Live: fetch open PRs + their check rollup, return the wedge impact. Fail-open to empty."""
    prs = _gh_json(
        [
            "pr",
            "list",
            "--repo",
            REPO,
            "--state",
            "open",
            "--limit",
            "200",
            "--json",
            "number,statusCheckRollup,isDraft,updatedAt",
        ],
        [],
    )
    if not isinstance(prs, list):
        return {"considered": 0, "wedged_checks": {}, "wedged_prs": 0}
    fresh_since = (_now() - timedelta(hours=fresh_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return wedge_impact(prs, required_checks(), fresh_since, k)


def _read_stamp() -> dict:
    try:
        return json.loads(STAMP.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_stamp(payload: dict) -> None:
    try:
        STAMP.parent.mkdir(exist_ok=True)
        STAMP.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass


def verdict(throttle: int) -> dict:
    """Return {conclusion, head_sha, url, source}. Uses cached verdict within the throttle window."""
    cached = _read_stamp()
    if cached.get("checked_at"):
        try:
            age = (_now() - datetime.fromisoformat(cached["checked_at"])).total_seconds()
        except ValueError:
            age = throttle + 1
        if age < throttle and cached.get("conclusion"):
            return {**cached, "source": "cache"}
    run = _gh_latest_main_run()
    if run is None:
        # fail open: keep the last known verdict if any, else "unknown"
        return (
            {**cached, "source": "gh-unavailable"}
            if cached.get("conclusion")
            else {"conclusion": "unknown", "source": "gh-unavailable"}
        )
    payload = {
        "checked_at": _now().isoformat(timespec="seconds"),
        "conclusion": run.get("conclusion") or "unknown",
        "head_sha": run.get("headSha") or "",
        "url": run.get("url") or "",
    }
    _write_stamp(payload)
    return {**payload, "source": "gh"}


def _emit_heal_task(head_sha: str, url: str, tasks_path: Path, impact_note: str = "") -> str | None:
    """Emit/refresh ONE idempotent, SYMPTOM-scoped HEAL-mainred task under the queue-lock.

    The id is scoped to the SYMPTOM (this repo's trunk is red), NOT the head SHA, so a *moving* red
    trunk — new commits landing while it stays broken — converges on ONE canonical task instead of
    spawning a fresh task per SHA (the limen#895 duplicate-repair gap). The specific SHA lives in the
    title/context, never the id. The guard is status-aware (``_ACTIVE_STATES``): if the singleton is
    already being worked we converge silently (return None); if a PRIOR red episode healed
    (done/archived/failed) and trunk is red AGAIN, we RE-OPEN the same ticket so the recurrence is
    never dropped by a stale done-row. Returns the id when it (re)opened, else None.
    """
    tid = f"HEAL-mainred-{REPO.replace('/', '-').lower()}"
    for _ in range(15):
        try:
            LOCKD.mkdir()
            break
        except FileExistsError:
            return None  # daemon holds the lock — retry next beat
        except OSError:
            return None
    try:
        lf = load_limen_file(tasks_path)
        stamp = _now().date().isoformat()
        short_head = head_sha[:8]
        title = f"Restore main to green — {REPO} CI is RED at {short_head}"
        context = (
            f"main's CI ({WORKFLOW}) is RED at exact head {head_sha} ({url}).{impact_note} Reproduce with "
            "`PYTHONPATH=cli/src pytest web/api/tests cli/tests -q`, fix at root, land a heal PR. "
            f"Single canonical SYMPTOM-scoped task (stable id {tid}) so every lane AND every "
            f"successive red commit converges here instead of duplicating. "
            f"[auto-emitted {stamp} by check-main-green]"
        )
        existing = next((t for t in lf.tasks if t.id == tid), None)
        try:
            contract = contract_fields(github_main_green_contract(REPO, head_sha, WORKFLOW))
        except IntakeContractError:
            return None  # stale/partial cache cannot create an exact-head contract; retry after live refresh
        if existing is not None:
            if existing.status in _ACTIVE_STATES:
                changed = False
                for key, value in {
                    "title": title,
                    "context": context,
                    "predicate": contract["predicate"],
                    "receipt_target": contract["receipt_target"],
                }.items():
                    if getattr(existing, key) != value:
                        setattr(existing, key, value)
                        changed = True
                if url and url not in (existing.urls or []):
                    existing.urls = [*(existing.urls or []), url]
                    changed = True
                if changed:
                    existing.updated = _now()
                    save_limen_file(tasks_path, lf)
                return None  # already being worked — converge, idempotent
            # prior red episode healed; trunk is red again → reopen the SAME canonical ticket
            existing.status = "open"
            existing.title = title
            existing.context = context
            existing.priority = "critical"
            existing.predicate = contract["predicate"]
            existing.receipt_target = contract["receipt_target"]
            if url and url not in (existing.urls or []):
                existing.urls = [*(existing.urls or []), url]
            existing.updated = _now()
            save_limen_file(tasks_path, lf)
            return tid
        lf.tasks.append(
            Task(
                id=tid,
                title=title,
                repo=REPO,
                type="code",
                target_agent="any",
                priority="critical",
                budget_cost=1,
                status="open",
                labels=["lifecycle", "ci", "mainred"],
                urls=[url] if url else [],
                context=context,
                **contract,
                depends_on=[],
                created=stamp,
                dispatch_log=[],
            )
        )
        save_limen_file(tasks_path, lf)
        return tid
    finally:
        try:
            LOCKD.rmdir()
        except OSError:
            pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="trunk-green invariant sensor")
    ap.add_argument("--dry-run", action="store_true", help="detect + report only, never emit a task")
    ap.add_argument(
        "--exact-head-check",
        action="store_true",
        help="fail closed unless current origin/main has a completed successful CI workflow push run",
    )
    ap.add_argument("--throttle", type=int, default=int(os.environ.get("LIMEN_MAIN_GREEN_THROTTLE", "1800")))
    ap.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS", str(ROOT / "tasks.yaml")))
    args = ap.parse_args(argv)

    if args.exact_head_check:
        return exact_head_check()

    v = verdict(args.throttle)
    conclusion = v.get("conclusion", "unknown")
    head = v.get("head_sha", "")
    url = v.get("url", "")

    # Blast-radius / queue-wedge (integrated from #882): quantify how many FRESH PRs are actually
    # blocked, and catch a wedge that persists even when trunk ci.yml is green.
    impact = open_pr_impact()
    wp = impact.get("wedged_prs", 0)
    wc = ", ".join(sorted(impact.get("wedged_checks") or {})) or "?"
    blast = f" — blocking {wp} fresh PR(s) on {wc}" if wp else ""

    if conclusion == "unknown":
        if wp:
            print(f"check-main-green: WEDGE — {wp} fresh PRs blocked on {wc} (trunk CI status unavailable)")
            return 1
        print(f"check-main-green: SKIP — main CI status unavailable ({v.get('source')}); failing open")
        return 0
    if conclusion not in RED:
        if wp:
            # trunk's own ci.yml is green, yet a required check is wedged across the queue — a divergence
            # the ci.yml-on-main read alone cannot see. Surface it; heal the base.
            print(
                f"check-main-green: WEDGE (trunk green) — {wp} fresh PRs blocked on {wc}; a required check diverges from {WORKFLOW}"
            )
            return 1
        print(f"check-main-green: GREEN — main {WORKFLOW} {conclusion} @ {head} ({v.get('source')})")
        return 0

    # RED
    print(f"check-main-green: RED — main {WORKFLOW} {conclusion} @ {head}{blast} ({url})")
    apply_on = os.environ.get("LIMEN_MAIN_GREEN_APPLY", "0").strip() == "1"
    if apply_on and not args.dry_run:
        impact_note = f" It is blocking {wp} fresh PR(s) on {wc}." if wp else ""
        tid = _emit_heal_task(head, url, Path(args.tasks), impact_note=impact_note)
        if tid:
            print(f"  → emitted heal task {tid}")
        else:
            print("  → heal task already open / lock busy (idempotent)")
    else:
        print("  → detection-only (LIMEN_MAIN_GREEN_APPLY!=1); arm it to auto-emit one heal task")
    return 1


if __name__ == "__main__":
    sys.exit(main())
