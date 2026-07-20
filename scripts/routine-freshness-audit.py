#!/usr/bin/env python3
"""routine-freshness-audit.py — detect claude.ai cloud routines that fire but stop delivering.

The gap this closes: a cloud routine can FIRE (its scheduler triggers it) without DELIVERING
(writing a new comment to its rolling GitHub issue). The atom-backlog-triage precedent made this
concrete — 25 days of silence while the routine appeared live in the scheduler, with no internal
monitor surfacing the gap. firing != delivering is the invariant; this organ proves it on every
beat by querying the rolling-issue comment timestamps and classifying each routine's freshness.

The RemoteTrigger API is in-session-only so we cannot observe the fire side directly; we audit
the DELIVERY side (rolling-issue comments) via `gh issue view`. Any claude.ai session that adds,
removes, or reconfigures a routine must update cloud-routines.json (the SSOT manifest).

Verdicts (per routine):
  green       — last comment age <= max_silent_days
  stale       — age > max_silent_days but <= 2x (degraded, watch it)
  down        — age > 2x max_silent_days (operator action needed)
  quiet       — a `may_be_silent` routine past its silence window: silence is legitimately healthy
                here (posts only on a state change / when there is something to say), so it is NOT
                a defect and hangs NO operator atom. Informational only.
  unknown     — gh probe failed (network / auth / missing issue); not "down" on a probe failure
  unmonitored — class is pr-delivery or issue is null; never classified down by this organ

Never-delivered (issue has comments=[] but gh succeeded):
  -> "down" only if the issue itself is older than 2x max_silent_days, else "stale"
     (a `may_be_silent` routine collapses stale/down to "quiet" — see below).

`may_be_silent` (opt-in per-routine flag, NOT derivable from `class`): a delta-gated routine whose
silence is genuinely healthy — it delivers ONLY when its subject state changes, so a long quiet
stretch means "nothing to report", not "fired-but-failed-to-deliver". Comment-age cannot tell a
healthy-quiet routine from a truly-dead one, so a flagged routine caps at the non-atom `quiet`
verdict instead of manufacturing a false `down`. Detecting a genuinely dead `may_be_silent` routine
needs an independent run-liveness probe (did the cloud session fire at all?) — a separate concern,
tracked in limen#894. Set this flag deliberately per routine; do not blanket-apply it, or the organ
goes blind to the fired-but-not-delivering gap it exists to catch.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
MANIFEST = ROOT / "cloud-routines.json"
LOGS = ROOT / "logs"
OUT = LOGS / "routine-freshness.json"
VOICE_DIR = LOGS / ".voice"
LEDGER = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))


def positive_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def load_manifest() -> list[dict]:
    """Read cloud-routines.json; skip enabled:false rows."""
    try:
        data = json.loads(MANIFEST.read_text())
    except (OSError, ValueError) as e:
        print(f"[routine-freshness] ERROR: cannot read manifest {MANIFEST}: {e}", file=sys.stderr)
        return []
    rows = data.get("routines", [])
    return [r for r in rows if r.get("enabled", True)]


def last_delivery(repo: str | None, issue: int | None) -> tuple[datetime.datetime | None, str]:
    """Return (newest_comment_dt, verdict_source) via gh.

    verdict_source: "comment" | "no-comments" | "error"
    Fail-open: any gh error -> (None, "error"); never calls it "down".
    """
    if repo is None or issue is None:
        return None, "unmonitored"

    try:
        cp = subprocess.run(
            ["gh", "issue", "view", str(issue), "-R", repo, "--json", "comments,createdAt"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as e:
        print(f"[routine-freshness] gh probe error ({repo}#{issue}): {e}", file=sys.stderr)
        return None, "error"

    if cp.returncode != 0:
        err = (cp.stderr or "").strip()
        print(f"[routine-freshness] gh exit {cp.returncode} ({repo}#{issue}): {err}", file=sys.stderr)
        return None, "error"

    try:
        obj = json.loads(cp.stdout)
    except ValueError:
        return None, "error"

    comments = obj.get("comments") or []
    if not comments:
        # no comments delivered yet — no fallback to updatedAt: "never delivered"
        return None, "no-comments"

    best = None
    for c in comments:
        raw = c.get("createdAt") or c.get("updatedAt") or ""
        if not raw:
            continue
        try:
            dt = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if best is None or dt > best:
            best = dt
    return best, "comment"


def classify(
    row: dict,
    last_ts: datetime.datetime | None,
    verdict_source: str,
    now: datetime.datetime,
) -> tuple[str, float | None]:
    """Return (verdict, age_days_or_None).

    unmonitored — class pr-delivery or null issue (never "down")
    unknown     — probe failed
    green       — age_days <= max_silent_days
    stale       — max_silent_days < age_days <= 2x
    down        — age_days > 2x
    quiet       — a `may_be_silent` routine past its silence window (stale/down collapse to quiet):
                  silence is healthy here, so no operator atom is hung.
    For never-delivered (no comments, gh OK): "down" only if issue itself is older than 2x, else "stale".
    """
    if row.get("class") == "pr-delivery" or row.get("issue") is None:
        return "unmonitored", None

    if verdict_source == "error":
        return "unknown", None

    max_days = row.get("max_silent_days", 7)
    # A `may_be_silent` routine (opt-in, deliberate per row) delivers only on a state change, so any
    # silence beyond its window is healthy-quiet, never a defect. Cap it at "quiet" instead of
    # stale/down so no false operator atom is hung. green (recently posted) still reads green.
    may_be_silent = bool(row.get("may_be_silent", False))

    if verdict_source == "no-comments":
        # never delivered: age relative to when the routine was first expected to deliver
        # use the issue creation date as the reference floor
        repo = row.get("issue_repo")
        issue = row.get("issue")
        issue_age_days: float | None = None
        if repo and issue:
            try:
                cp = subprocess.run(
                    ["gh", "issue", "view", str(issue), "-R", repo, "--json", "createdAt"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if cp.returncode == 0:
                    obj = json.loads(cp.stdout)
                    raw = obj.get("createdAt", "")
                    if raw:
                        created = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
                        issue_age_days = (now - created).total_seconds() / 86400
            except Exception:
                pass
        if issue_age_days is None:
            # can't determine issue age; treat as stale rather than assuming down
            return ("quiet" if may_be_silent else "stale"), None
        if issue_age_days > 2 * max_days:
            return ("quiet" if may_be_silent else "down"), issue_age_days
        return ("quiet" if may_be_silent else "stale"), issue_age_days

    if last_ts is None:
        return "unknown", None

    age_days = (now - last_ts).total_seconds() / 86400

    if age_days <= max_days:
        return "green", age_days
    if may_be_silent:
        # beyond the freshness window but silence is healthy for this routine — no defect, no atom
        return "quiet", age_days
    if age_days <= 2 * max_days:
        return "stale", age_days
    return "down", age_days


def hang_down_atoms(down_rows: list[dict]) -> dict:
    """Upsert ASK-routine-<name> needs_human tasks for each down routine.

    Idempotent within the ASK-routine-* namespace; written under the shared queue_lock.
    Fail-open: any error skips the upsert (never crashes the beat).
    """
    res: dict = {"created": [], "refreshed": [], "homed": [], "ledger": str(LEDGER)}
    if not down_rows:
        return res

    try:
        sys.path.insert(0, str(ROOT / "cli" / "src"))
        from datetime import date as _date
        from datetime import datetime as _datetime
        from datetime import timezone as _tz

        from limen.io import load_limen_file, queue_lock
        from limen.intake import contract_fields, github_issue_owner_contract
        from limen.models import DispatchLogEntry, Task, has_jules_landing_hold
        from limen.tabularius import apply_limen_file_sync
        from limen.workstream_contract import WORKSTREAM_SUCCESSOR_REQUIRED_LABEL
    except Exception as e:
        res["error"] = f"ledger unavailable ({e}); atoms not hung"
        return res

    if not LEDGER.exists():
        res["error"] = f"no ledger at {LEDGER}; atoms not hung"
        return res

    with queue_lock(LEDGER) as got:
        if not got:
            res["error"] = "queue busy; skipped this beat (self-corrects)"
            return res

        lf = load_limen_file(LEDGER)
        index = {t.id: t for t in lf.tasks}
        now_dt = _datetime.now(_tz.utc)
        changed = False

        for r in down_rows:
            name = r["name"]
            tid = f"ASK-routine-{name}"
            repo = r.get("issue_repo")
            issue = r.get("issue")
            days_silent = r.get("_days_silent")
            issue_url = f"https://github.com/{repo}/issues/{issue}" if repo and issue else "no rolling issue"
            days_label = f"{days_silent:.0f} days silent" if days_silent is not None else "never delivered"
            ctx = (
                f"Cloud routine '{name}' is DOWN: {days_label}. "
                f"Rolling issue: {issue_url}. "
                f"Fixing a cloud routine requires opening the operator's claude.ai session, "
                f"locating the '{name}' scheduled routine, and verifying it is configured and "
                f"enabled. This organ cannot trigger cloud routines — only the operator's "
                f"claude.ai session can do so."
            )

            ex = index.get(tid)
            contract = contract_fields(github_issue_owner_contract("organvm/limen", tid))
            if (
                ex
                and ex.status != "done"
                and WORKSTREAM_SUCCESSOR_REQUIRED_LABEL not in (ex.labels or [])
                and not has_jules_landing_hold(ex)
            ):
                refreshed = False
                if ex.status != "needs_human":
                    ex.status = "needs_human"
                    ex.dispatch_log.append(
                        DispatchLogEntry(
                            timestamp=now_dt,
                            agent="routine-freshness",
                            session_id="hang-down",
                            status="needs_human",
                            lifecycle_repair="human-gate-reconcile",
                            routine_name=name,
                            routine_observed_state="down",
                            output=f"routine-freshness: routine '{name}' is down; reconciled human gate",
                        )
                    )
                    refreshed = True
                if ex.context != ctx:
                    ex.context = ctx
                    refreshed = True
                if "routine-freshness" not in (ex.labels or []):
                    ex.labels = list(ex.labels or []) + ["routine-freshness"]
                    refreshed = True
                if "needs-human" not in (ex.labels or []):
                    ex.labels = list(ex.labels or []) + ["needs-human"]
                    refreshed = True
                if refreshed:
                    ex.updated = now_dt
                    changed = True
                    res["refreshed"].append(tid)
                else:
                    res["homed"].append(f"{name} → {tid}")
            elif ex is None:
                lf.tasks.append(
                    Task(
                        id=tid,
                        title=f"Routine '{name}' is DOWN — check claude.ai session",
                        repo="organvm/limen",
                        type="ops",
                        target_agent="human",
                        priority="high",
                        status="needs_human",
                        labels=["routine-freshness", "needs-human"],
                        context=ctx,
                        **contract,
                        created=_date.today(),
                        updated=now_dt,
                    )
                )
                changed = True
                res["created"].append(tid)

        if changed:
            apply_limen_file_sync(
                LEDGER,
                lf,
                agent="routine-freshness",
                session_id="hang-down",
            )

    return res


def retire_recovered_atoms(down_names: set[str], all_names: list[str]) -> dict:
    """Retire (→done) any organ-owned ASK-routine-<name> atom whose routine is no longer 'down'.

    The symmetric half of hang_down_atoms: that opens an atom when a routine goes down; this closes
    it when the routine recovers (back to green) OR is reclassified healthy-quiet (may_be_silent,
    limen#894). Without this, a resolved false-positive lingers in the operator's needs_human queue
    forever — a sensor that fires an effector but never retracts it. Only atoms this organ created
    (labelled "routine-freshness") and not already done/archived are touched. Same queue_lock path;
    fail-open (any error skips, never crashes the beat).
    """
    res: dict = {"retired": [], "ledger": str(LEDGER)}
    recovered = sorted(n for n in all_names if n not in down_names)
    if not recovered:
        return res

    try:
        sys.path.insert(0, str(ROOT / "cli" / "src"))
        from datetime import datetime as _datetime
        from datetime import timezone as _tz

        from limen.io import load_limen_file, queue_lock
        from limen.tabularius import apply_limen_file_sync
        from limen.models import DispatchLogEntry, has_jules_landing_hold
    except Exception as e:
        res["error"] = f"ledger unavailable ({e}); atoms not retired"
        return res

    if not LEDGER.exists():
        return res

    with queue_lock(LEDGER) as got:
        if not got:
            res["error"] = "queue busy; skipped this beat (self-corrects)"
            return res

        lf = load_limen_file(LEDGER)
        index = {t.id: t for t in lf.tasks}
        now_dt = _datetime.now(_tz.utc)
        changed = False

        for name in recovered:
            tid = f"ASK-routine-{name}"
            ex = index.get(tid)
            if (
                ex is not None
                and ex.status not in ("done", "archived")
                and "routine-freshness" in (ex.labels or [])
                and not has_jules_landing_hold(ex)
            ):
                ex.status = "done"
                ex.updated = now_dt
                ex.context = (
                    f"Auto-retired by routine-freshness-audit: routine '{name}' recovered / "
                    f"reclassified healthy (green or may_be_silent quiet) — no operator action needed."
                )
                ex.dispatch_log.append(
                    DispatchLogEntry(
                        timestamp=now_dt,
                        agent="routine-freshness",
                        session_id="retire-recovered",
                        status="done",
                        lifecycle_repair="routine-recovered",
                        routine_name=name,
                        routine_observed_state="recovered",
                        output=ex.context,
                    )
                )
                changed = True
                res["retired"].append(tid)

        if changed:
            apply_limen_file_sync(
                LEDGER,
                lf,
                agent="routine-freshness",
                session_id="retire-recovered",
            )

    return res


def _write_voice_stamp(ts_iso: str) -> None:
    """Stamp logs/.voice/routines with iso timestamp (mtime-based signal for organ-health.py)."""
    try:
        VOICE_DIR.mkdir(parents=True, exist_ok=True)
        (VOICE_DIR / "routines").write_text(ts_iso)
    except OSError:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(
        description="routine-freshness-audit — detect cloud routines that fire but stop delivering"
    )
    ap.add_argument(
        "--throttle",
        type=int,
        default=positive_int_env("LIMEN_ROUTINE_FRESHNESS_THROTTLE", 21600),
        metavar="SECONDS",
        help="skip if logs/routine-freshness.json is younger than this many seconds (default 21600)",
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if any routine is 'down' (for use as a predicate gate)",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="ignore throttle and run unconditionally",
    )
    args = ap.parse_args()

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_iso = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Throttle: skip if the output artifact is fresh enough
    if not args.force and not args.check:
        try:
            age_s = now_utc.timestamp() - OUT.stat().st_mtime
            if age_s < args.throttle:
                print(f"[routine-freshness] throttled — artifact is {age_s:.0f}s old (< {args.throttle}s); skipping")
                return 0
        except OSError:
            pass  # no artifact yet; run

    rows = load_manifest()
    if not rows:
        print("[routine-freshness] no enabled routines in manifest; nothing to audit")
        return 0

    results = []
    summary: dict[str, int] = {"green": 0, "stale": 0, "down": 0, "quiet": 0, "unknown": 0, "unmonitored": 0}
    down_rows: list[dict] = []

    for row in rows:
        name = row["name"]
        cls = row.get("class", "delta-gated")
        issue = row.get("issue")
        repo = row.get("issue_repo")

        if cls == "pr-delivery" or issue is None:
            verdict = "unmonitored"
            last_dt = None
            age_days = None
        else:
            last_dt, src = last_delivery(repo, issue)
            verdict, age_days = classify(row, last_dt, src, now_utc)

        last_str = last_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if last_dt else None
        age_label = f"{age_days:.1f}d" if age_days is not None else "—"

        print(f"  {verdict:12s}  {name}  (last={last_str or 'never'}  age={age_label})")

        rec = {
            "name": name,
            "verdict": verdict,
            "last_delivery": last_str,
            "days_silent": round(age_days, 1) if age_days is not None else None,
        }
        results.append(rec)
        summary[verdict] = summary.get(verdict, 0) + 1

        if verdict == "down":
            row_copy = dict(row)
            row_copy["_days_silent"] = age_days
            down_rows.append(row_copy)

    # Hang needs_human atoms for down routines
    if down_rows:
        h = hang_down_atoms(down_rows)
        bits = []
        if h.get("created"):
            bits.append(f"created {', '.join(h['created'])}")
        if h.get("refreshed"):
            bits.append(f"refreshed {', '.join(h['refreshed'])}")
        if h.get("homed"):
            bits.append(f"already-homed {len(h['homed'])}")
        if h.get("error"):
            bits.append(h["error"])
        print(f"[routine-freshness] ledger: {'; '.join(bits) or 'no change'}")

    # Symmetric half: retire any lingering ASK-routine atom whose routine is no longer down
    # (recovered to green, or reclassified healthy-quiet under may_be_silent — limen#894).
    down_names = {r["name"] for r in down_rows}
    all_names = [r["name"] for r in rows]
    rr = retire_recovered_atoms(down_names, all_names)
    if rr.get("retired"):
        print(f"[routine-freshness] retired stale atoms: {', '.join(rr['retired'])}")
    elif rr.get("error"):
        print(f"[routine-freshness] retire: {rr['error']}")

    # Write output artifact
    out_obj = {
        "generated": now_iso,
        "routines": results,
        "summary": summary,
    }
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(out_obj, indent=2))
        _write_voice_stamp(now_iso)
    except OSError as e:
        print(f"[routine-freshness] WARNING: could not write {OUT}: {e}", file=sys.stderr)

    n_down = summary.get("down", 0)
    print(
        f"[routine-freshness] summary: {summary.get('green', 0)} green, "
        f"{summary.get('stale', 0)} stale, {n_down} down, "
        f"{summary.get('quiet', 0)} quiet, "
        f"{summary.get('unknown', 0)} unknown, {summary.get('unmonitored', 0)} unmonitored"
    )

    if args.check and n_down > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
