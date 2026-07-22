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

- **CI-JAM CLASS (2026-07-17):** a RED whose failed jobs all have ZERO steps is not a broken tree —
  the runner never started (every job "fails" in 3-4 s with no logs). Emitting a HEAL-mainred repair
  task for that is the WRONG effector, so the RED path first classifies ``ci-fail`` (real — heal path
  unchanged) vs ``ci-jam`` (never-started). The 2026-07-17 root cause taught the real lesson: the jam
  was **visibility drift** — organvm/limen had been flipped PRIVATE while the estate registry
  (`institutio/github/estate.yaml`) declares it PUBLIC, so its CI silently began consuming the Free
  plan's metered private-repo Actions minutes, exhausted them, and every job then died at start with
  GitHub's generic "payments failed OR spending limit" string. **Nothing was owed** — the fix was to
  restore the repo to its registry-desired public visibility, NOT to pay anything. So on a jam the
  sensor (a) checks `_visibility_drift(repo)` — private-but-registry-says-public — and, if so, notifies
  ONCE via scripts/_notify.py naming the DRIFT and its real fix (restore public → free Actions), never
  a billing/payment chore; a neutral "Actions quota/infra jam" message otherwise; and (b) behind
  ``LIMEN_CI_JAM_RERUN`` (default armed) attempts a bounded ``gh run rerun --failed`` per jammed run
  with per-run exponential backoff — harmless while the jam persists, and the FIRST beat after the
  drift/quota clears re-greens main and the jammed PR heads with zero hands (merge-drain then lands
  them). Backoff state ``logs/vigilia/ci-jam-state.json``; it and the notification clear on green.

Fail-open: no ``gh`` / offline / parse error → exit 0 (never breaks the beat).

  python3 scripts/check-main-green.py             # detect + surface (+ emit if APPLY=1)
  python3 scripts/check-main-green.py --dry-run    # detect + report only, never emit
  python3 scripts/check-main-green.py --throttle 900
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling scripts/ for _notify
import _notify  # noqa: E402
from limen.io import load_limen_file  # noqa: E402
from limen.intake import IntakeContractError, contract_fields, github_main_green_contract  # noqa: E402
from limen.models import DispatchLogEntry, Task, has_jules_landing_hold  # noqa: E402
from limen.tabularius import apply_limen_file_sync  # noqa: E402
from limen.workstream_contract import WORKSTREAM_SUCCESSOR_REQUIRED_LABEL  # noqa: E402

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
# CI-jam recovery (2026-07-17): rerun valve + per-run exponential backoff bounds.
# Backoff caps at hours, never a hard attempt cap — recovery must still fire if the jam clears
# days later, while API spam stays logarithmic while it persists.
JAM_RERUN = os.environ.get("LIMEN_CI_JAM_RERUN", "1").strip() == "1"
JAM_BACKOFF_S = int(os.environ.get("LIMEN_CI_JAM_BACKOFF_S", "1800"))
JAM_BACKOFF_MAX_S = int(os.environ.get("LIMEN_CI_JAM_BACKOFF_MAX_S", "14400"))
JAM_RERUN_CAP = int(os.environ.get("LIMEN_CI_JAM_RERUN_CAP", "6"))
JAM_STATE = ROOT / "logs" / "vigilia" / "ci-jam-state.json"
JAM_KEY = "ci-jam"
# The estate registry: a repo classed here as public but observed private is a VISIBILITY DRIFT —
# on the Free plan that silently meters its CI into the never-started jam (the 2026-07-17 root cause).
ESTATE = ROOT / "institutio" / "github" / "estate.yaml"
# GitHub's generic never-started string — payment failure OR (more often) an exhausted quota /
# $0 spending limit. It does NOT imply a bill is owed; on 2026-07-17 nothing was owed and the true
# cause was a private repo metering the Free tier. Used only to distinguish a quota/infra jam from
# a real test failure — never to attribute a payment problem.
_QUOTA_RE = re.compile(r"payments? have failed|spending limit", re.IGNORECASE)
_RUN_ID_RE = re.compile(r"/actions/runs/(\d+)")
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


def _fetch_open_prs() -> list[dict]:
    """Open PRs + check rollup (one fetch shared by wedge impact and jam recovery). Fail-open to []."""
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
    return prs if isinstance(prs, list) else []


def _fresh_since(fresh_hours: int = FRESH_HOURS) -> str:
    return (_now() - timedelta(hours=fresh_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def open_pr_impact(
    fresh_hours: int = FRESH_HOURS,
    k: int = WEDGE_K,
    prs: list[dict] | None = None,
    required: set[str] | None = None,
) -> dict:
    """Live: fetch open PRs + their check rollup, return the wedge impact. Fail-open to empty.

    ``prs``/``required`` may be passed in when the caller already fetched them (main() shares one
    fetch between this and the jam-recovery run-id scan) — defaults keep the standalone behavior.
    """
    if prs is None:
        prs = _fetch_open_prs()
    if not prs:
        return {"considered": 0, "wedged_checks": {}, "wedged_prs": 0}
    return wedge_impact(prs, required if required is not None else required_checks(), _fresh_since(fresh_hours), k)


def classify_red_run(run_id: int | str) -> tuple[str, str]:
    """Classify a RED run: ``ci-fail`` (real test failure) vs ``ci-jam`` (never-started).

    Jam fingerprint: every failed job has ZERO steps — the runner never started the work (the
    2026-07-17 event: each job "fails" in 3-4 s, ``gh run view --log-failed`` says "log not found").
    A real failure always has executed steps. GitHub's generic never-started annotation ("payments
    failed OR spending limit") confirms the quota/never-started class — but it does NOT mean a bill
    is owed (the real 2026-07-17 cause was a private repo metering the Free tier; nothing was owed).
    Fail-open to ``ci-fail`` so an API outage never suppresses the real-failure heal path. Returns
    ``(klass, detail)``.
    """
    if not run_id:
        return "ci-fail", ""
    data = _gh_json(["api", f"repos/{REPO}/actions/runs/{run_id}/jobs"], None)
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list) or not jobs:
        return "ci-fail", ""
    failed = [j for j in jobs if isinstance(j, dict) and (j.get("conclusion") or "") in ("failure", "startup_failure")]
    if not failed or any(j.get("steps") for j in failed):
        return "ci-fail", ""
    ann = _gh_json(["api", f"repos/{REPO}/check-runs/{failed[0].get('id')}/annotations"], [])
    msgs = " ".join(str(a.get("message", "")) for a in ann if isinstance(a, dict)) if isinstance(ann, list) else ""
    if _QUOTA_RE.search(msgs):
        return "ci-jam", "runner never started (Actions quota / spending-limit / metered-private)"
    return "ci-jam", "failed jobs have zero steps (runner never started)"


def _visibility_drift(repo: str) -> bool:
    """True iff ``repo`` is observed PRIVATE while the estate registry desires it PUBLIC.

    The 2026-07-17 root cause: organvm/limen was flipped private against `estate.yaml` (which classes
    it public), so its CI silently metered the Free tier into the never-started jam. This is the
    real, actionable cause of a quota jam — its fix is 'restore public → free Actions', never a
    payment. Fail-closed to False (no false drift alarm) on any read error.
    """
    private = _gh_json(["api", f"repos/{repo}", "--jq", ".private"], None)
    if private is not True:
        return False
    try:
        import yaml  # lazy — only when a jam is being classified

        estate = yaml.safe_load(ESTATE.read_text())
    except Exception:
        return False
    classes = (estate or {}).get("classes", {}) if isinstance(estate, dict) else {}
    # desired-public if any class matching this repo declares visibility: public (conductor first-match).
    for cls in classes.values() if isinstance(classes, dict) else []:
        if not isinstance(cls, dict):
            continue
        match = cls.get("match") or []
        names = match if isinstance(match, list) else [match]
        if repo in names and str(cls.get("visibility", "")).lower() == "public":
            return True
    return False


def jammed_pr_run_ids(prs: list[dict], required: set[str], fresh_since: str | None) -> list[int]:
    """Pure: run ids behind FAILING required checks on fresh non-draft open PRs (jam-recovery targets).

    Same freshness/draft filter as ``wedge_impact`` — the chronic stale backlog is not rerun fodder.
    Ids come from each check's ``detailsUrl`` (…/actions/runs/<id>/job/<jid>), so no extra API calls.
    """
    ids: set[int] = set()
    for pr in prs:
        if pr.get("isDraft"):
            continue
        if fresh_since and str(pr.get("updatedAt", "")) < fresh_since:
            continue
        for c in pr.get("statusCheckRollup") or []:
            name = c.get("name") or c.get("context") or ""
            concl = (c.get("conclusion") or c.get("state") or "").upper()
            if name in required and concl in BAD_CHECK:
                m = _RUN_ID_RE.search(str(c.get("detailsUrl") or ""))
                if m:
                    ids.add(int(m.group(1)))
    return sorted(ids)


def attempt_reruns(run_ids: list[int], now: float | None = None) -> list[dict]:
    """Bounded ``gh run rerun --failed`` per jammed run, per-run exponential backoff, state-tracked.

    No hard attempt cap — backoff doubles from JAM_BACKOFF_S to JAM_BACKOFF_MAX_S so recovery still
    fires if the jam clears days later, while attempts while it persists stay ~a handful per day.
    While the jam persists a rerun is accepted and instantly re-fails (same run id) — harmless, free,
    and the attempt is recorded. State clears wholesale when trunk goes green.
    """
    if not JAM_RERUN or not run_ids:
        return []
    now = time.time() if now is None else now
    try:
        state = json.loads(JAM_STATE.read_text())
        state = state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        state = {}
    results: list[dict] = []
    for rid in run_ids[:JAM_RERUN_CAP]:
        rec = state.get(str(rid)) or {"attempts": 0, "last": 0.0}
        delay = min(JAM_BACKOFF_S * (2 ** max(int(rec.get("attempts", 0)) - 1, 0)), JAM_BACKOFF_MAX_S)
        if rec.get("attempts") and (now - float(rec.get("last", 0.0))) < delay:
            results.append({"run": rid, "action": "backoff"})
            continue
        try:
            r = subprocess.run(
                ["gh", "run", "rerun", str(rid), "--repo", REPO, "--failed"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            ok = r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
        state[str(rid)] = {"attempts": int(rec.get("attempts", 0)) + 1, "last": now}
        results.append({"run": rid, "action": "rerun", "ok": ok})
    try:
        JAM_STATE.parent.mkdir(parents=True, exist_ok=True)
        JAM_STATE.write_text(json.dumps(state, indent=1, sort_keys=True))
    except OSError:
        pass
    return results


def _clear_jam() -> None:
    """Trunk is green — end the jam condition: notification re-arms, backoff state resets."""
    _notify.clear_condition(ROOT, JAM_KEY)
    try:
        JAM_STATE.unlink()
    except OSError:
        pass


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
        "run_id": run.get("databaseId") or 0,
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
        if existing is not None and has_jules_landing_hold(existing):
            return None
        try:
            contract = contract_fields(github_main_green_contract(REPO, head_sha, WORKFLOW))
        except IntakeContractError:
            return None  # stale/partial cache cannot create an exact-head contract; retry after live refresh
        collateral = {
            "origin": "system_debt",
            "horizon": "present",
            "value_case": f"Restore {REPO} protected main to green at exact head {head_sha}",
            "owner_surface": REPO,
        }
        if existing is not None:
            if WORKSTREAM_SUCCESSOR_REQUIRED_LABEL in (existing.labels or []):
                return None
            if existing.status in _ACTIVE_STATES:
                changed = False
                for key, value in {
                    "title": title,
                    "context": context,
                    "predicate": contract["predicate"],
                    "receipt_target": contract["receipt_target"],
                    **collateral,
                }.items():
                    if getattr(existing, key) != value:
                        setattr(existing, key, value)
                        changed = True
                if url and url not in (existing.urls or []):
                    existing.urls = [*(existing.urls or []), url]
                    changed = True
                if changed:
                    existing.updated = _now()
                    apply_limen_file_sync(
                        tasks_path,
                        lf,
                        agent="check-main-green",
                        session_id="refresh",
                    )
                return None  # already being worked — converge, idempotent
            # prior red episode healed; trunk is red again → reopen the SAME canonical ticket
            prior_status = existing.status
            existing.status = "open"
            existing.title = title
            existing.context = context
            existing.priority = "critical"
            existing.predicate = contract["predicate"]
            existing.receipt_target = contract["receipt_target"]
            for key, value in collateral.items():
                setattr(existing, key, value)
            if url and url not in (existing.urls or []):
                existing.urls = [*(existing.urls or []), url]
            existing.updated = _now()
            existing.dispatch_log.append(
                DispatchLogEntry(
                    timestamp=existing.updated,
                    agent="check-main-green",
                    session_id="recurrence-reopen",
                    status="open",
                    lifecycle_repair=("recurrence-reopen" if prior_status in {"done", "archived"} else None),
                    recurrence_source=("main-green" if prior_status in {"done", "archived"} else None),
                    recurrence_head_sha=(head_sha if prior_status in {"done", "archived"} else None),
                    output=f"check-main-green: reopened recurring red trunk at {head_sha}",
                )
            )
            apply_limen_file_sync(
                tasks_path,
                lf,
                agent="check-main-green",
                session_id="reopen",
            )
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
                **collateral,
                depends_on=[],
                created=stamp,
                dispatch_log=[],
            )
        )
        apply_limen_file_sync(
            tasks_path,
            lf,
            agent="check-main-green",
            session_id="create",
        )
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
    # blocked, and catch a wedge that persists even when trunk ci.yml is green. One PR fetch is
    # shared with the jam-recovery run-id scan below.
    prs = _fetch_open_prs()
    required = required_checks() if prs else set()
    impact = open_pr_impact(prs=prs, required=required)
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
        _clear_jam()  # trunk green — the jam condition (if any) has ended; notification re-arms
        if wp:
            # trunk's own ci.yml is green, yet a required check is wedged across the queue — a divergence
            # the ci.yml-on-main read alone cannot see. Surface it; heal the base.
            print(
                f"check-main-green: WEDGE (trunk green) — {wp} fresh PRs blocked on {wc}; a required check diverges from {WORKFLOW}"
            )
            return 1
        print(f"check-main-green: GREEN — main {WORKFLOW} {conclusion} @ {head} ({v.get('source')})")
        return 0

    # RED — first split the class: a never-started jam is not a broken tree, so the HEAL-mainred
    # repair task would be the wrong effector for it (nothing in the tree to fix).
    klass, detail = classify_red_run(v.get("run_id") or 0)
    tag = f" [{klass}]" if klass != "ci-fail" else ""
    print(f"check-main-green: RED{tag} — main {WORKFLOW} {conclusion} @ {head}{blast} ({url})")

    if klass != "ci-fail":
        # Name the REAL cause. The 2026-07-17 jam was VISIBILITY DRIFT — a registry-public repo
        # observed private, silently metering the Free tier — whose fix is 'restore public', never a
        # payment. Check for that first; fall back to a neutral quota/infra message. Never a card lever.
        if _visibility_drift(REPO):
            msg = (
                f"VISIBILITY DRIFT — {REPO} is PRIVATE but the estate registry declares it PUBLIC, so its "
                "CI is metering the Free plan's private-repo Actions minutes and jammed. Fix: restore it "
                "to public (`gh repo edit --visibility public`) → free unlimited Actions. Nothing is owed."
            )
        else:
            msg = (
                "GitHub Actions runs fail before any step executes (Actions quota / spending-limit / infra "
                "jam) — no bill is implied; bounded reruns are armed and re-green CI once the quota clears."
            )
        _notify.notify_once(ROOT, JAM_KEY, msg, title="LIMEN trunk CI")
        run_ids = [int(v.get("run_id") or 0)] + jammed_pr_run_ids(prs, required, _fresh_since())
        results = attempt_reruns([rid for rid in run_ids if rid])
        rerun = sum(1 for r in results if r.get("action") == "rerun")
        backoff = sum(1 for r in results if r.get("action") == "backoff")
        print(f"  → jam recovery ({detail or klass}): rerun={rerun} backoff={backoff} of {len(results)} target(s)")
        return 1

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
