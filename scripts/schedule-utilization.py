#!/usr/bin/env python3
"""schedule-utilization — every scheduler plane's allotment vs declared vs observed, as one gauge.

Reads institutio/governance/schedules.yaml (the SCHEDULES registry) and, per enabled plane, answers
three numbers and one verdict for the current UTC day:

  allotment   what the vendor/carrier allows (runs per window, or active-task cap)
  declared    what is scheduled against it (cron fires today, active jobs, or the plane's floor)
  observed    what the plane's declared evidence shows actually happened (None = could not look)

  verdict     full               observed covers declared (or the floor) — nothing on the floor
              idle-by-design     the plane is declared idle on purpose
              unscheduled-headroom  fill_policy floor and fewer jobs/runs are declared than the floor
              underfilled        observed < declared × LIMEN_SCHEDULE_FILL_FLOOR, or < floor
              dark               declared > 0 and observed == 0 (evidence readable, nothing ran)
              unmeasured         evidence kind `none`, unreadable, or a snapshot past its max age

An unmeasured plane is NEVER red — 'I could not look' and 'nothing happened' are different facts
(Data Grounding). dark / underfilled / unscheduled-headroom exit 1 (advisory in the beat) and the
line names the plane's `effector` from the registry: the organ or human action that fixes it. The
sensor mutates nothing but its own receipt (logs/schedule-utilization.json, written atomically) and
history (logs/schedule-utilization.jsonl, one row per plane per run).

  python3 scripts/schedule-utilization.py                       # table + exit code
  python3 scripts/schedule-utilization.py --receipt logs/schedule-utilization.json --json
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _schedules as S  # noqa: E402

RED_VERDICTS = {"dark", "underfilled", "unscheduled-headroom", "undeclared-off", "declared-off-but-active"}
EXIT_RED = 1
EXIT_STALE_READBACK = 3  # no red, but a plane WITH an evidence path could not be read (stale snapshot, dead witness, gh down)
GH_TIMEOUT = 25


def _env_float(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, "") or default)
    except ValueError:
        return default
    return value if 0 < value <= 1 else default


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, "") or default)
    except ValueError:
        return default
    return value if value > 0 else default


def gh_available() -> bool:
    return shutil.which("gh") is not None


def gh_json(args: list[str]) -> object | None:
    """Run gh and parse JSON; None on any failure (missing binary, auth, network)."""
    if not gh_available():
        return None
    try:
        run = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=GH_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if run.returncode != 0 or not run.stdout.strip():
        return None
    try:
        return json.loads(run.stdout)
    except json.JSONDecodeError:
        return None


# ── evidence readers: (plane_id, plane, jobs, today, root) -> (observed | None, detail) ────────

def summarize_runs(rows: list) -> tuple[int, int]:
    """(successful, failed-or-cancelled) scheduled runs; an in-progress run counts as neither."""
    ok = sum(1 for r in rows if isinstance(r, dict) and r.get("conclusion") == "success")
    bad = sum(1 for r in rows if isinstance(r, dict) and r.get("conclusion") in {"failure", "cancelled", "timed_out", "startup_failure", "action_required"})
    return ok, bad


def workflow_states(repo: str) -> dict[str, str] | None:
    """`.github/workflows/<file>` -> state (active | disabled_manually | disabled_inactivity | …), or None if unreadable."""
    payload = gh_json(["api", f"repos/{repo}/actions/workflows?per_page=100"])
    rows = payload.get("workflows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return None
    out: dict[str, str] = {}
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("path"), str):
            out[row["path"].rsplit("/", 1)[-1]] = str(row.get("state") or "")
    return out


def read_gh_actions_runs(plane_id: str, plane: dict, jobs: list[S.Job], today: date, root: Path) -> tuple[int | None, str, dict]:
    """Scheduled runs today across the plane's cron workflows. A workflow GitHub reports as disabled is
    NOT declared work (a deliberate off-switch is not a dropped slot) and is named in the detail instead."""
    repo = str(plane["evidence"].get("locator"))
    if not gh_available():
        return None, "gh unavailable", {}
    states = workflow_states(repo)
    if states is None:
        return None, f"cannot read workflow states for {repo}", {}
    total = 0
    failed = 0
    active: list[S.Job] = []
    disabled: list[str] = []
    declared_off = {str(row.get("file")): row for row in (plane.get("declared_off") or []) if isinstance(row, dict)}
    undeclared_off: list[str] = []
    rotten_off: list[str] = []
    for job in jobs:
        if not job.enabled or not job.crons:
            continue
        wf = job.extra.get("workflow_file") or (job.source.split(".github/workflows/", 1)[1] if ".github/workflows/" in job.source else None)
        if not wf:
            continue
        state = states.get(wf, "unknown")
        if state != "active":
            disabled.append(f"{wf}={state}")
            if wf not in declared_off:
                undeclared_off.append(wf)
            continue
        if wf in declared_off:
            rotten_off.append(wf)
        rows = gh_json(["run", "list", "--repo", repo, "--workflow", wf, "--event", "schedule", "--created", today.isoformat(), "--json", "conclusion", "--limit", "100"])
        if rows is None:
            return None, f"gh run list failed for {repo} {wf}", {}
        active.append(job)
        ok, bad = summarize_runs(rows if isinstance(rows, list) else [])
        total += ok
        failed += bad
    if not active and not disabled:
        return None, "no cron workflows to look at", {}
    detail = f"{total} successful scheduled runs across {len(active)} active cron workflows ({repo})"
    if failed:
        detail += f"; {failed} fired-but-failed (a run that dies is a run left on the floor)"
    if disabled:
        detail += f"; declared off, not counted: {', '.join(sorted(disabled))}"
    extra: dict = {"declared_jobs": active}
    if undeclared_off:
        extra["override"] = "undeclared-off"
        detail += f"; UNDECLARED OFF (nobody owns the switch): {', '.join(sorted(undeclared_off))}"
    elif rotten_off:
        extra["override"] = "declared-off-but-active"
        detail += f"; declared off but ACTIVE live (declaration rotted): {', '.join(sorted(rotten_off))}"
    return total, detail, extra


def _sibling_file(repo: str, rel: str, root: Path) -> str | None:
    clone = S.sibling_root(repo, dict(os.environ), Path.home())
    if clone is not None:
        path = clone / rel
        return path.read_text(encoding="utf-8") if path.exists() else None
    payload = gh_json(["api", f"repos/{repo}/contents/{rel}"])
    if isinstance(payload, dict) and payload.get("encoding") == "base64":
        try:
            return base64.b64decode(payload.get("content") or "").decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None
    return None


def read_bookend_tsv(plane_id: str, plane: dict, jobs: list[S.Job], today: date, root: Path) -> tuple[int | None, str]:
    locator = str(plane["evidence"].get("locator"))  # "owner/repo:bookends"
    repo, _, folder = locator.partition(":")
    text = _sibling_file(repo, f"{folder}/{today.isoformat()}.tsv", root)
    if text is None:
        clone = S.sibling_root(repo, dict(os.environ), Path.home())
        if clone is None and not gh_available():
            return None, "no sibling clone and gh unavailable"
        # Readable source, but no file for today: that is an observation (nothing bookended today).
        return 0, f"no {folder}/{today.isoformat()}.tsv in {repo} (readable, absent)"
    starts: set[str] = set()
    ends: set[str] = set()
    for line in text.splitlines():
        cols = line.split("\t")
        if len(cols) < 6:
            continue
        job, phase = cols[1], cols[4]
        (starts if phase == "start" else ends if phase == "end" else set()).add(job)
    paired = starts & ends
    return len(paired), f"{len(paired)} job(s) with paired start/end bookends today: {sorted(paired)}"


_WITNESS_ROW_RX = re.compile(r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*([\w-]+)\s*\|\s*(yes|no)\s*\|\s*(yes|no)\s*\|", re.M)


def read_witness_audit(plane_id: str, plane: dict, jobs: list[S.Job], today: date, root: Path) -> tuple[int | None, str]:
    locator = str(plane["evidence"].get("locator"))  # "owner/repo:audit"
    repo, _, folder = locator.partition(":")
    clone = S.sibling_root(repo, dict(os.environ), Path.home())
    names: list[str] = []
    if clone is not None:
        names = sorted(p.name for p in (clone / folder).glob("*-witness.md"))
    else:
        listing = gh_json(["api", f"repos/{repo}/contents/{folder}"])
        if isinstance(listing, list):
            names = sorted(str(e.get("name")) for e in listing if isinstance(e, dict) and str(e.get("name", "")).endswith("-witness.md"))
    if not names:
        return None, f"no *-witness.md readable in {repo}:{folder}"
    newest = names[-1]
    try:
        report_day = date.fromisoformat(newest[:10])
    except ValueError:
        return None, f"cannot date {newest}"
    max_age = _env_int("LIMEN_SCHEDULE_WITNESS_MAX_AGE_DAYS", 8)
    if (today - report_day).days > max_age:
        return None, f"newest witness report {newest} is {(today - report_day).days}d old (> {max_age}d)"
    text = _sibling_file(repo, f"{folder}/{newest}", root)
    if text is None:
        return None, f"cannot read {repo}:{folder}/{newest}"
    targets = {j.id.split("/", 1)[1] for j in jobs if j.enabled}
    latest_day: dict[str, tuple[str, bool]] = {}
    for day, job, start, end in _WITNESS_ROW_RX.findall(text):
        if job not in targets:
            continue
        prior = latest_day.get(job)
        if prior is None or day > prior[0]:
            latest_day[job] = (day, start == "yes" and end == "yes")
    healthy = sum(1 for _, ok in latest_day.values() if ok)
    return healthy, f"{healthy}/{len(targets)} targets healthy on their latest witnessed day ({newest})"


def read_voice_stamps(plane_id: str, plane: dict, jobs: list[S.Job], today: date, root: Path) -> tuple[int | None, str]:
    voice = root / str(plane["evidence"].get("locator"))
    if not voice.is_dir():
        return None, f"{voice} absent (CI or worktree) — unmeasured"
    expected = {j.id.split("/", 1)[1] for j in jobs if j.cadence_hours and j.cadence_hours <= 24}
    stamped_today = 0
    for sid in expected:
        stamp = voice / sid
        try:
            mtime = datetime.fromtimestamp(stamp.stat().st_mtime, tz=timezone.utc).date()
        except OSError:
            continue
        if mtime == today:
            stamped_today += 1
    return stamped_today, f"{stamped_today}/{len(expected)} daily-or-faster cadence sensors stamped today"


def read_claude_snapshot(plane_id: str, plane: dict, jobs: list[S.Job], today: date, root: Path) -> tuple[int | None, str]:
    path, snapshot = S.newest_snapshot(root)
    if path is None or snapshot is None:
        return None, "no claude-triggers snapshot receipt — export one from an interactive session (list_triggers)"
    age = S.snapshot_age_days(snapshot, today)
    max_age = _env_int("LIMEN_SCHEDULE_SNAPSHOT_MAX_AGE_DAYS", 7)
    if age is None or age > max_age:
        return None, f"snapshot {path.name} is {age}d old (> {max_age}d) — re-export before trusting it"
    contracted = {j.id.split("/", 1)[1] for j in jobs if j.enabled}
    rows = [r for r in snapshot.get("triggers") or [] if isinstance(r, dict) and r.get("routine") in contracted]
    enabled = sum(1 for r in rows if r.get("enabled"))
    denied = sum(1 for r in rows if (r.get("last_run_failure_reason") or "") == "ACCESS_DENIED")
    return enabled, f"{enabled}/{len(contracted)} contracted routines enabled in {path.name} ({age}d old); {denied} last failed ACCESS_DENIED"


def _as_utc(stamp: object) -> datetime | None:
    if isinstance(stamp, datetime):
        return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)
    if isinstance(stamp, str):
        try:
            return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def read_board_dispatch_receipts(plane_id: str, plane: dict, jobs: list[S.Job], today: date, root: Path) -> tuple[int | None, str]:
    board = root / str(plane["evidence"].get("locator"))
    if not board.exists():
        return None, f"{board.name} absent"
    try:
        data = yaml.safe_load(board.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        return None, f"{board.name} unreadable: {exc.__class__.__name__}"
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)
    used = 0
    for task in data.get("tasks") or []:
        for entry in (task.get("dispatch_log") or []) if isinstance(task, dict) else []:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("agent") or "").lower() != "jules" or str(entry.get("status") or "").lower() != "dispatched":
                continue
            when = _as_utc(entry.get("timestamp"))
            if when is not None and cutoff < when <= now:
                used += 1
    return used, f"{used} jules launches in the rolling 24h recorded by this broker (not vendor remaining quota)"


def read_issue_comments(plane_id: str, plane: dict, jobs: list[S.Job], today: date, root: Path) -> tuple[int | None, str]:
    locator = str(plane["evidence"].get("locator"))  # "owner/repo#N"
    repo, _, number = locator.partition("#")
    if not gh_available():
        return None, "gh unavailable"
    rows = gh_json(["api", f"repos/{repo}/issues/{number}/comments?since={today.isoformat()}T00:00:00Z&per_page=100"])
    if not isinstance(rows, list):
        return None, f"cannot read comments on {locator}"
    return len(rows), f"{len(rows)} comment(s) on {locator} today (delivery signal, not a run count)"


def read_none(plane_id: str, plane: dict, jobs: list[S.Job], today: date, root: Path) -> tuple[int | None, str, dict]:
    """A plane nobody can read. Unmeasured, never zero — but not forever: after the readback budget
    (counted from the plane's `declared_on`) the silence itself becomes a stale readback (exit 3)."""
    declared_on = plane.get("declared_on")
    try:
        since = date.fromisoformat(str(declared_on))
    except (TypeError, ValueError):
        since = None
    budget = _env_int("LIMEN_SCHEDULE_READBACK_MAX_AGE_DAYS", 31)
    detail = "no evidence path declared — the owner must declare a delivery locator before this plane can be measured"
    if since is None:
        return None, detail + " (no declared_on date; readback budget cannot be applied)", {"readback_overdue": True}
    age = (today - since).days
    if age > budget:
        return None, f"{detail}; unmeasured for {age}d, past the {budget}d readback budget (L-SCHED-READBACKS)", {"readback_overdue": True}
    return None, f"{detail}; {budget - age}d of readback budget left", {}


READERS = {
    "gh-actions-runs": read_gh_actions_runs,
    "bookend-tsv": read_bookend_tsv,
    "witness-audit": read_witness_audit,
    "voice-stamps": read_voice_stamps,
    "claude-snapshot": read_claude_snapshot,
    "board-dispatch-receipts": read_board_dispatch_receipts,
    "issue-comments": read_issue_comments,
    "none": read_none,
}


# ── declared counts ───────────────────────────────────────────────────────────────────────────

def _fires_so_far(job: S.Job, today: date, now: datetime) -> int:
    """Cron fires on `today` that have already come due — a half-elapsed day is compared to half its fires."""
    tz = S.resolve_tz(job.tz)
    count = 0
    for c in job.crons:
        for when in S.fires_on_utc_day(S.parse_cron(c), tz, today):
            if today != now.date() or when <= now:
                count += 1
    return count


def declared_for(plane: dict, jobs: list[S.Job], today: date, now: datetime) -> int:
    window = (plane.get("allotment") or {}).get("window")
    kind = (plane.get("evidence") or {}).get("kind")
    enabled = [j for j in jobs if j.enabled]
    if window == "active-tasks":
        return len(enabled)
    if window == "rolling-24h" and plane.get("fill_policy") == "floor":
        return int(plane.get("floor") or 0)
    if kind == "claude-snapshot":
        return len(enabled)  # contracted routines, matched 1:1 against the snapshot's enabled flags
    if kind == "witness-audit":
        return len(enabled)  # targets with a witnessed day, matched 1:1
    if kind == "bookend-tsv":
        enabled = [j for j in enabled if (j.delivery or {}).get("kind") == "bookend-tsv"]
        return sum(1 for j in enabled if _fires_so_far(j, today, now))
    if kind == "voice-stamps":
        return sum(1 for j in enabled if j.cadence_hours and j.cadence_hours <= 24)
    return sum(_fires_so_far(job, today, now) for job in enabled)


def verdict_for(plane: dict, declared: int, observed: int | None, fill_floor: float) -> str:
    policy = plane.get("fill_policy")
    if policy == "idle-by-design":
        return "idle-by-design"
    floor = int(plane.get("floor") or 0) if policy == "floor" else 0
    if policy == "floor" and declared < floor and (plane.get("allotment") or {}).get("window") != "rolling-24h":
        return "unscheduled-headroom"
    if observed is None:
        return "unmeasured"
    if declared == 0:
        return "idle-by-design"
    if observed == 0:
        return "dark"
    kind = (plane.get("evidence") or {}).get("kind")
    if kind == "issue-comments":
        return "full"  # any delivery today is the signal; comment counts are not run counts
    if policy == "floor" and observed < floor:
        return "underfilled"
    if observed < declared * fill_floor:
        return "underfilled"
    return "full"


def evaluate(root: Path, today: date, *, readers: dict | None = None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    registry = S.load_registry(root)
    jobs = S.all_jobs(root, registry)
    readers = readers or READERS
    fill_floor = _env_float("LIMEN_SCHEDULE_FILL_FLOOR", 0.5)
    planes: list[dict] = []
    for pid, plane in (registry.get("planes") or {}).items():
        if not isinstance(plane, dict) or not plane.get("enabled", True):
            continue
        plane_jobs = [j for j in jobs if j.plane == pid]
        kind = (plane.get("evidence") or {}).get("kind") or "none"
        reader = readers.get(kind, read_none)
        extra: dict = {}
        try:
            result = reader(pid, plane, plane_jobs, today, root)
            observed, detail = result[0], result[1]
            extra = result[2] if len(result) > 2 and isinstance(result[2], dict) else {}
        except Exception as exc:  # a broken reader is an unmeasured plane, never a crash of the beat
            observed, detail = None, f"reader error: {exc.__class__.__name__}: {exc}"
        readback_overdue = bool(extra.get("readback_overdue"))
        declared_jobs = extra.get("declared_jobs")
        declared = declared_for(plane, declared_jobs if isinstance(declared_jobs, list) else plane_jobs, today, now)
        allot = plane.get("allotment") or {}
        verdict = verdict_for(plane, declared, observed, fill_floor)
        if extra.get("override") in RED_VERDICTS:
            verdict = str(extra["override"])
        runs_cap = allot.get("runs")
        # declared is a RUN count only for cron-fire planes and an active-task count for active-task planes;
        # for job-matched evidence kinds (witness rows, snapshot rows, bookend jobs, voice stamps) it is a job
        # count in a different unit from the allotment, so no gap is computed rather than a wrong one.
        same_unit = allot.get("window") == "active-tasks" or (allot.get("window") == "calendar-day" and kind in {"gh-actions-runs", "issue-comments", "none"})
        allocation_gap = (runs_cap - declared) if isinstance(runs_cap, int) and same_unit else None
        execution_gap = (declared - observed) if isinstance(observed, int) else None
        planes.append(
            {
                "plane": pid,
                "provider": plane.get("provider"),
                "surface": plane.get("surface"),
                "allotment": allot.get("runs"),
                "window": allot.get("window"),
                "entitlement": allot.get("entitlement"),
                "declared": declared,
                "observed": observed,
                "allocation_gap": allocation_gap,
                "execution_gap": execution_gap,
                "verdict": verdict,
                "evidence": kind,
                "readback_overdue": readback_overdue,
                "upstream_state": (plane.get("authority") or {}).get("upstream_state"),
                "detail": detail,
                "owner": plane.get("owner"),
                "effector": plane.get("effector"),
                "jobs": len([j for j in plane_jobs if j.enabled]),
            }
        )
    red = [p for p in planes if p["verdict"] in RED_VERDICTS]
    unmeasured = [p for p in planes if p["verdict"] == "unmeasured"]
    # had a way to look and could not, or has had no way to look for longer than the readback budget
    stale = [p["plane"] for p in unmeasured if p["evidence"] != "none" or p["readback_overdue"]]
    measurable = [p for p in planes if p["evidence"] != "none"]
    measured = [p for p in measurable if p["observed"] is not None]
    status = "fail" if red else ("stale-readback" if stale else "pass")
    return {
        "schema_version": "limen.schedule_utilization.v1",
        "day": today.isoformat(),
        "as_of": now.isoformat(timespec="seconds"),
        "status": status,
        "measured": f"{len(measured)}/{len(measurable)}",
        "red": [p["plane"] for p in red],
        "unmeasured": [p["plane"] for p in unmeasured],
        "stale_readback": stale,
        "planes": planes,
    }


def write_receipt(path: Path, report: dict, history: Path | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".schedule-utilization.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    if history is not None:
        with open(history, "a", encoding="utf-8") as fh:
            for plane in report["planes"]:
                fh.write(json.dumps({"ts": report["generated_at"], "day": report["day"], **{k: plane[k] for k in ("plane", "allotment", "window", "declared", "observed", "verdict")}}, sort_keys=True) + "\n")


def print_table(report: dict) -> None:
    print(
        f"schedule-utilization {report['day']} — {len(report['planes'])} planes; measured {report['measured']}; "
        f"red={report['red'] or 'none'}; unmeasured={report['unmeasured'] or 'none'}; stale-readback={report['stale_readback'] or 'none'}"
    )
    print(f"{'plane':28} {'allot':>6} {'window':13} {'decl':>5} {'obs':>5}  verdict               detail")
    for p in report["planes"]:
        obs = "—" if p["observed"] is None else str(p["observed"])
        allot = "—" if p["allotment"] is None else str(p["allotment"])
        print(f"{p['plane']:28} {allot:>6} {str(p['window']):13} {p['declared']:>5} {obs:>5}  {p['verdict']:21} {p['detail']}")
        if p["verdict"] in RED_VERDICTS:
            print(f"  ↑ {p['plane']} is {p['verdict']} — effector: {p['effector']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--day", default=None, help="UTC day to evaluate (YYYY-MM-DD; default today)")
    parser.add_argument("--receipt", default=None, help="write the JSON receipt here (atomic) and append history beside it")
    parser.add_argument("--json", action="store_true", help="print the report as JSON instead of a table")
    args = parser.parse_args(argv)
    root = Path(args.root)
    today = date.fromisoformat(args.day) if args.day else datetime.now(timezone.utc).date()
    report = evaluate(root, today)
    report["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if args.receipt:
        receipt = Path(args.receipt)
        receipt = receipt if receipt.is_absolute() else root / receipt
        write_receipt(receipt, report, receipt.with_suffix(".jsonl"))
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_table(report)
    if report["status"] == "fail":
        return EXIT_RED
    if report["status"] == "stale-readback":
        return EXIT_STALE_READBACK
    return 0


if __name__ == "__main__":
    sys.exit(main())
