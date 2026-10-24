#!/usr/bin/env python3
"""schedule-utilization — audit inventory, bounded observations and separately evidenced capacity.

Reads institutio/governance/schedules.yaml (the SCHEDULES registry) and, per enabled plane, answers
three numbers and one verdict for the current UTC day:

  allotment   what the vendor/carrier allows (runs per window, or active-task cap)
  declared    what is scheduled against it (cron fires today, active jobs, or the plane's floor)
    observed    attributable execution evidence (None = unmeasured); configuration is separate

  verdict     full               observed covers declared (or the floor) — nothing on the floor
              partial-evidence   bounded native collection or partial pages; never whole-plane full
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
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _schedules as S  # noqa: E402
from _schedule_reporting import capacity_report, read_native_snapshot  # noqa: E402

RED_VERDICTS = {"dark", "underfilled", "unscheduled-headroom", "undeclared-off", "declared-off-but-active"}
EXIT_RED = 1
EXIT_STALE_READBACK = (
    3  # no red, but a plane WITH an evidence path could not be read (stale snapshot, dead witness, gh down)
)
GH_TIMEOUT = 25
_COLLECTION_DEADLINE: ContextVar[float | None] = ContextVar("schedule_collection_deadline", default=None)


class CollectionDeadlineReached(TimeoutError):
    """No remote read may consume the time reserved for publishing the sensor receipt."""


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


@contextmanager
def _collection_budget():
    # Share the existing sensor ceiling, leaving half for local readers and atomic receipt/history
    # writes. A fresh evaluation gets a fresh budget; nested evaluations cannot extend their parent.
    budget = min(60.0, _env_int("LIMEN_SCHEDULE_UTILIZATION_TIMEOUT", 120) / 2)
    deadline = time.monotonic() + budget
    parent_deadline = _COLLECTION_DEADLINE.get()
    token = _COLLECTION_DEADLINE.set(min(deadline, parent_deadline) if parent_deadline is not None else deadline)
    try:
        yield
    finally:
        _COLLECTION_DEADLINE.reset(token)


def _gh_timeout() -> float:
    deadline = _COLLECTION_DEADLINE.get()
    remaining = GH_TIMEOUT if deadline is None else min(GH_TIMEOUT, deadline - time.monotonic())
    if remaining <= 0:
        raise CollectionDeadlineReached("collection deadline reached")
    return remaining


def _run_gh(args: list[str]) -> subprocess.CompletedProcess | None:
    timeout = _gh_timeout()
    try:
        return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        _gh_timeout()  # expose an exhausted shared budget, rather than starting another timeout
        return None


def gh_available() -> bool:
    return shutil.which("gh") is not None


def gh_json(args: list[str]) -> object | None:
    """Run gh and parse JSON; None on any failure (missing binary, auth, network)."""
    if not gh_available():
        return None
    run = _run_gh(args)
    if run is None or run.returncode != 0 or not run.stdout.strip():
        return None
    try:
        return json.loads(run.stdout)
    except json.JSONDecodeError:
        return None


# ── evidence readers: (plane_id, plane, jobs, today, root) -> (observed | None, detail) ────────


def summarize_runs(rows: list) -> tuple[int, int]:
    """(successful, failed-or-cancelled) scheduled runs; an in-progress run counts as neither."""
    ok = sum(1 for r in rows if isinstance(r, dict) and r.get("conclusion") == "success")
    bad = sum(
        1
        for r in rows
        if isinstance(r, dict)
        and r.get("conclusion") in {"failure", "cancelled", "timed_out", "startup_failure", "action_required"}
    )
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


def read_gh_actions_runs(
    plane_id: str, plane: dict, jobs: list[S.Job], today: date, root: Path
) -> tuple[int | None, str, dict]:
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
    truncated = False
    active: list[S.Job] = []
    disabled: list[str] = []
    declared_off = {str(row.get("file")): row for row in (plane.get("declared_off") or []) if isinstance(row, dict)}
    undeclared_off: list[str] = []
    rotten_off: list[str] = []
    for job in jobs:
        if not job.enabled or not job.crons:
            continue
        wf = job.extra.get("workflow_file") or (
            job.source.split(".github/workflows/", 1)[1] if ".github/workflows/" in job.source else None
        )
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
        rows = gh_json(
            [
                "run",
                "list",
                "--repo",
                repo,
                "--workflow",
                wf,
                "--event",
                "schedule",
                "--created",
                today.isoformat(),
                "--json",
                "conclusion",
                "--limit",
                "100",
            ]
        )
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            return None, f"gh run list failed for {repo} {wf}", {}
        truncated = truncated or len(rows) >= 100
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
    extra: dict = {
        "declared_jobs": active,
        "measurement_kind": "execution",
        "coverage": "partial" if truncated else "complete",
    }
    if undeclared_off:
        extra["override"] = "undeclared-off"
        detail += f"; UNDECLARED OFF (nobody owns the switch): {', '.join(sorted(undeclared_off))}"
    elif rotten_off:
        extra["override"] = "declared-off-but-active"
        detail += f"; declared off but ACTIVE live (declaration rotted): {', '.join(sorted(rotten_off))}"
    return total, detail, extra


PRESENT, ABSENT, UNREADABLE = "present", "absent", "unreadable"


def _gh_api(path: str) -> tuple[int, object | None]:
    """(exit code, parsed stdout JSON or None). `gh api` prints the error body to stdout on an HTTP error, so
    the body survives for inspection; -1 means gh itself could not run."""
    run = _run_gh(["api", path])
    if run is None:
        return -1, None
    try:
        return run.returncode, json.loads(run.stdout) if run.stdout.strip() else None
    except json.JSONDecodeError:
        return run.returncode, None


def _is_404(payload: object) -> bool:
    return isinstance(payload, dict) and (
        str(payload.get("status", "")) == "404" or payload.get("message") == "Not Found"
    )


def _gh_contents(repo: str, rel: str) -> tuple[str | None, str]:
    """GitHub Contents read with the three outcomes kept apart: (text, PRESENT) on a decodable file,
    (None, ABSENT) only when the parent folder LISTS and does not contain the file, (None, UNREADABLE) on
    anything else — missing or unauthenticated gh, a network cut, a non-file payload. A bare 404 proves
    nothing: an unauthenticated read of a private repository is also a 404, so absence is confirmed by
    reading the folder the file would live in."""
    if not gh_available():
        return None, UNREADABLE
    code, payload = _gh_api(f"repos/{repo}/contents/{rel}")
    if code == 0 and isinstance(payload, dict) and payload.get("encoding") == "base64":
        try:
            return base64.b64decode(payload.get("content") or "").decode("utf-8"), PRESENT
        except (ValueError, UnicodeDecodeError):
            return None, UNREADABLE
    if code != 0 and _is_404(payload):
        folder, _, name = rel.rpartition("/")
        lcode, listing = _gh_api(f"repos/{repo}/contents/{folder}")
        if lcode == 0 and isinstance(listing, list):
            names = {str(e.get("name")) for e in listing if isinstance(e, dict)}
            return (None, ABSENT) if name not in names else (None, UNREADABLE)
    return None, UNREADABLE


def _sibling_file(repo: str, rel: str, root: Path) -> tuple[str | None, str]:
    """(text, state) for a sibling repo's file: from the local clone when one is configured, else via the
    GitHub Contents API. ABSENT is a confirmed observation (the store answered "no such file"); UNREADABLE
    is the absence of an observation (nothing could be read) and must never be scored as zero."""
    clone = S.sibling_root(repo, dict(os.environ), Path.home())
    if clone is not None:
        path = clone / rel
        if not path.exists():
            try:
                names = {child.name for child in path.parent.iterdir()}
            except OSError:
                return None, UNREADABLE
            return None, ABSENT if path.name not in names else UNREADABLE
        try:
            return path.read_text(encoding="utf-8"), PRESENT
        except (OSError, UnicodeDecodeError):
            return None, UNREADABLE
    return _gh_contents(repo, rel)


def read_bookend_tsv(plane_id: str, plane: dict, jobs: list[S.Job], today: date, root: Path) -> tuple[int | None, str]:
    locator = str(plane["evidence"].get("locator"))  # "owner/repo:bookends"
    repo, _, folder = locator.partition(":")
    rel = f"{folder}/{today.isoformat()}.tsv"
    text, state = _sibling_file(repo, rel, root)
    if state == UNREADABLE:
        # No clone and the API read failed (auth, network, gh missing): nothing was observed, so nothing is
        # scored — a failed read is not an empty day.
        return None, f"cannot read {repo}:{rel} (no sibling clone; gh contents read failed) — unmeasured, not zero"
    if state == ABSENT or text is None:
        # The store answered: no file for today. That IS an observation (nothing bookended today).
        return 0, f"no {rel} in {repo} (readable, confirmed absent)"
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


def read_witness_audit(
    plane_id: str, plane: dict, jobs: list[S.Job], today: date, root: Path
) -> tuple:
    locator = str(plane["evidence"].get("locator"))  # "owner/repo:audit"
    repo, _, folder = locator.partition(":")
    clone = S.sibling_root(repo, dict(os.environ), Path.home())
    names: list[str] = []
    if clone is not None:
        names = sorted(p.name for p in (clone / folder).glob("*-witness.md"))
    else:
        listing = gh_json(["api", f"repos/{repo}/contents/{folder}"])
        if isinstance(listing, list):
            names = sorted(
                str(e.get("name"))
                for e in listing
                if isinstance(e, dict) and str(e.get("name", "")).endswith("-witness.md")
            )
    if not names:
        return None, f"no *-witness.md readable in {repo}:{folder}"
    newest = names[-1]
    try:
        report_day = date.fromisoformat(newest[:10])
    except ValueError:
        return None, f"cannot date {newest}"
    max_age = _env_int("LIMEN_SCHEDULE_WITNESS_MAX_AGE_DAYS", 8)
    if not 0 <= (today - report_day).days <= max_age:
        return None, f"newest witness report {newest} is {(today - report_day).days}d old (outside 0..{max_age}d)"
    text, state = _sibling_file(repo, f"{folder}/{newest}", root)
    if text is None:
        return None, f"cannot read {repo}:{folder}/{newest} ({state})"
    targets = {j.id.split("/", 1)[1] for j in jobs if j.enabled}
    latest_day: dict[str, tuple[str, bool]] = {}
    for day, job, start, end in _WITNESS_ROW_RX.findall(text):
        if job not in targets:
            continue
        prior = latest_day.get(job)
        if prior is None or day > prior[0]:
            latest_day[job] = (day, start == "yes" and end == "yes")
    healthy = sum(1 for _, ok in latest_day.values() if ok)
    return (
        healthy,
        f"{healthy}/{len(targets)} targets healthy on their latest witnessed day ({newest})",
        {"readback_fresh": True, "witness_report_date": report_day.isoformat()},
    )


def read_voice_stamps(plane_id: str, plane: dict, jobs: list[S.Job], today: date, root: Path) -> tuple[int | None, str]:
    voice = root / str(plane["evidence"].get("locator"))
    if not voice.is_dir():
        return None, f"{voice} absent (CI or worktree) — unmeasured"
    try:
        ever_stamped = any(voice.iterdir())
    except OSError:
        ever_stamped = False
    if not ever_stamped:
        # The directory exists (a sensor run or hook created it) but no heartbeat has ever stamped here:
        # this checkout is not a beating host, so there is nothing to score.
        return (
            None,
            f"{voice} holds no stamps at all — no heartbeat beats on this checkout (CI or worktree) — unmeasured",
        )
    daily = [j for j in jobs if j.cadence_hours and j.cadence_hours <= 24]
    now_ts = datetime.now(timezone.utc).timestamp()
    current = 0
    late: list[str] = []
    for job in daily:
        sid = job.id.split("/", 1)[1]
        try:
            age = now_ts - (voice / sid).stat().st_mtime
        except OSError:
            late.append(f"{sid} (never)")
            continue
        if age <= _stamp_bound_seconds(job):
            current += 1
        else:
            late.append(f"{sid} ({int(age // 3600)}h)")
    detail = (
        f"{current}/{len(daily)} daily-or-faster cadence sensors stamped within 2× their worst-case cadence window "
        "(the beat-sensors canary bound; a UTC-midnight cutoff would fault every sensor not yet due)"
    )
    if late:
        detail += f"; late: {', '.join(sorted(late))}"
    return current, detail


def _stamp_bound_seconds(job: S.Job) -> float:
    """beat-sensors.py canary: a stamp older than cadence × loop_max × 2 is STALE. The same bound here, so
    the two never disagree about a sensor's health."""
    loop_max = int((job.extra or {}).get("loop_max_seconds") or S.BEAT_LOOP_MAX_SECONDS)
    if job.cadence_beats:
        return job.cadence_beats * max(1, loop_max) * 2
    return (job.cadence_hours or 1) * S.SECONDS_PER_HOUR * 2


def read_claude_snapshot(plane_id: str, plane: dict, jobs: list[S.Job], today: date, root: Path) -> tuple:
    path, snapshot = S.newest_snapshot(root)
    if path is None or snapshot is None:
        return None, "no claude-triggers snapshot receipt — export one from an interactive session (list_triggers)"
    age = S.snapshot_age_days(snapshot, today)
    max_age = _env_int("LIMEN_SCHEDULE_SNAPSHOT_MAX_AGE_DAYS", 7)
    if age is None or not 0 <= age <= max_age:
        return None, f"snapshot {path.name} is {age}d old (outside 0..{max_age}d) — re-export before trusting it"
    contracted = {j.id.split("/", 1)[1] for j in jobs if j.enabled}
    rows = [r for r in snapshot.get("triggers") or [] if isinstance(r, dict) and r.get("routine") in contracted]
    enabled = sum(1 for r in rows if r.get("enabled"))
    denied = sum(1 for r in rows if (r.get("last_run_failure_reason") or "") == "ACCESS_DENIED")
    return (
        None,
        f"{enabled}/{len(contracted)} contracted routines enabled in {path.name} ({age}d old); {denied} last failed ACCESS_DENIED; configuration only, execution unmeasured",
        {"configured_enabled": enabled, "measurement_kind": "configuration", "coverage": "partial", "readback_fresh": True},
    )


def _as_utc(stamp: object) -> datetime | None:
    if isinstance(stamp, datetime):
        return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)
    if isinstance(stamp, str):
        try:
            return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            return None
    return None


PUBLIC_PROJECTION_SCHEMA_PREFIX = "limen.public_board_projection"

# A `dispatched` dispatch_log row is a CLAIM, not an execution (AGENTS.md task states). The dispatcher
# writes one before the provider runs (serial: "dispatch-serial: canonical claim requested before
# provider execution", parallel: "dispatch-parallel: reserved before agent execution") and `_apply_result`
# writes another for the confirmed submission; lifecycle guards write more without launching anything.
# Only the confirmed submission is a launch.
RESERVATION_OUTPUT_PREFIXES = ("dispatch-serial:", "dispatch-parallel:", "dispatch result ignored")
GUARD_SESSION_IDS = {"reserve", "serial-reserve", "pr-open-lifecycle-guard", "result-lifecycle-guard"}


def is_confirmed_launch(entry: dict) -> bool:
    """True for a dispatch_log row that records a provider submission, not a pre-launch claim or a guard."""
    if str(entry.get("status") or "").lower() != "dispatched":
        return False
    if str(entry.get("session_id") or "") in GUARD_SESSION_IDS:
        return False
    output = str(entry.get("output") or "")
    return not output.startswith(RESERVATION_OUTPUT_PREFIXES)


def board_path(root: Path, locator: str, env: dict[str, str] | None = None) -> Path:
    """The board projection this host actually reads: `LIMEN_TASKS`, else `$LIMEN_ROOT/<locator>`, else the
    checkout's own copy (AGENTS.md: tasks.yaml at $LIMEN_ROOT is TABVLARIVS's local read-only projection)."""
    environ = env if env is not None else os.environ
    explicit = (environ.get("LIMEN_TASKS") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    limen_root = (environ.get("LIMEN_ROOT") or "").strip()
    if limen_root:
        return Path(limen_root).expanduser() / locator
    return root / locator


def is_public_projection(data: object) -> bool:
    """The redacted projection the public checkout carries (`schema_version: limen.public_board_projection.v1`,
    `tasks: []`) — aggregate counts only, no dispatch_log — so it can prove nothing about launches."""
    if not isinstance(data, dict):
        return False
    schema = str(data.get("schema_version") or "")
    if schema.startswith(PUBLIC_PROJECTION_SCHEMA_PREFIX):
        return True
    portal = data.get("portal")
    return not data.get("tasks") and isinstance(portal, dict) and "public_projection" in portal


def read_board_dispatch_receipts(
    plane_id: str, plane: dict, jobs: list[S.Job], today: date, root: Path
) -> tuple[int | None, str]:
    board = board_path(root, str(plane["evidence"].get("locator")))
    if not board.exists():
        return None, f"{board} absent"
    try:
        data = yaml.safe_load(board.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        return None, f"{board.name} unreadable: {exc.__class__.__name__}"
    if is_public_projection(data):
        return None, (
            f"{board} is the redacted public projection (tasks: [], no dispatch_log) — the broker's launch receipts "
            "are not in this checkout; point LIMEN_TASKS or LIMEN_ROOT at the live local projection to measure jules"
        )
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)
    launches: set[tuple[str, str]] = set()  # (task id, provider session) — one launch, however many rows echo it
    claims = 0
    for task in data.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        for entry in task.get("dispatch_log") or []:
            if not isinstance(entry, dict) or str(entry.get("agent") or "").lower() != "jules":
                continue
            if str(entry.get("status") or "").lower() != "dispatched":
                continue
            when = _as_utc(entry.get("timestamp"))
            if when is None or not (cutoff < when <= now):
                continue
            if not is_confirmed_launch(entry):
                claims += 1
                continue
            launches.add((str(task.get("id") or ""), str(entry.get("session_id") or "")))
    used = len(launches)
    return used, (
        f"{used} confirmed jules launches in the rolling 24h recorded by this broker "
        f"({claims} pre-launch claim/guard rows not counted; not vendor remaining quota)"
    )


def read_issue_comments(
    plane_id: str, plane: dict, jobs: list[S.Job], today: date, root: Path
) -> tuple[int | None, str]:
    locator = str(plane["evidence"].get("locator"))  # "owner/repo#N"
    repo, _, number = locator.partition("#")
    if not gh_available():
        return None, "gh unavailable"
    rows = gh_json(["api", f"repos/{repo}/issues/{number}/comments?since={today.isoformat()}T00:00:00Z&per_page=100"])
    if not isinstance(rows, list):
        return None, f"cannot read comments on {locator}"
    return None, f"{len(rows)} comment(s) on {locator} today; attribution, acceptance and delivery unverified"


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
        return (
            None,
            f"{detail}; unmeasured for {age}d, past the {budget}d readback budget (L-SCHED-READBACKS)",
            {"readback_overdue": True},
        )
    return None, f"{detail}; {budget - age}d of readback budget left", {}


READERS = {
    "native-snapshot": read_native_snapshot,
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
        inventory = plane.get("native_inventory") or {}
        return inventory.get("enabled_count", len(enabled))
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
    kind = (plane.get("evidence") or {}).get("kind")
    if kind in {"issue-comments", "native-snapshot", "claude-snapshot", "board-dispatch-receipts"}:
        return "unmeasured" if observed is None else "partial-evidence"
    floor = int(plane.get("floor") or 0) if policy == "floor" else 0
    if policy == "floor" and declared < floor and (plane.get("allotment") or {}).get("window") != "rolling-24h":
        return "unscheduled-headroom"
    if observed is None:
        return "unmeasured"
    if declared == 0:
        return "idle-by-design"
    if observed == 0:
        return "dark"
    if policy == "floor" and observed < floor:
        return "underfilled"
    if observed < declared * fill_floor:
        return "underfilled"
    return "full"


@_collection_budget()
def evaluate(
    root: Path,
    today: date,
    *,
    readers: dict | None = None,
    now: datetime | None = None,
    registry_path: Path | None = None,
    snapshot_path: Path | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    registry = S.load_registry(root, registry_path)
    if snapshot_path:
        for plane in registry.get("planes", {}).values():
            if (plane.get("evidence") or {}).get("kind") == "native-snapshot":
                plane["evidence"]["locator"] = str(snapshot_path.resolve())
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
            result = (reader(pid, plane, plane_jobs, today, root, now=now) if reader is read_native_snapshot
                      else reader(pid, plane, plane_jobs, today, root))
            observed, detail = result[0], result[1]
            extra = result[2] if len(result) > 2 and isinstance(result[2], dict) else {}
        except CollectionDeadlineReached:
            observed, detail = None, "collection deadline reached — unmeasured, not zero"
        except Exception as exc:  # a broken reader is an unmeasured plane, never a crash of the beat
            observed, detail = None, f"reader error: {exc.__class__.__name__}: {exc}"
        readback_overdue = bool(extra.get("readback_overdue"))
        declared_jobs = extra.get("declared_jobs")
        declared = declared_for(plane, declared_jobs if isinstance(declared_jobs, list) else plane_jobs, today, now)
        allot = plane.get("allotment") or {}
        verdict = verdict_for(plane, declared, observed, fill_floor)
        if extra.get("coverage") in {"partial", "unknown"} and verdict == "full":
            verdict = "partial-evidence"
        if extra.get("override") in RED_VERDICTS:
            verdict = str(extra["override"])
        runs_cap = allot.get("runs")
        # declared is a RUN count only for cron-fire planes and an active-task count for active-task planes;
        # for job-matched evidence kinds (witness rows, snapshot rows, bookend jobs, voice stamps) it is a job
        # count in a different unit from the allotment, so no gap is computed rather than a wrong one.
        same_unit = allot.get("window") == "active-tasks" or (
            allot.get("window") == "calendar-day" and kind in {"gh-actions-runs", "issue-comments", "none"}
        )
        allocation_gap = (runs_cap - declared) if isinstance(runs_cap, int) and same_unit else None
        execution_gap = (declared - observed) if isinstance(observed, int) and kind != "native-snapshot" else None
        planes.append(
            {
                "plane": pid,
                "provider": plane.get("provider"),
                "surface": plane.get("surface"),
                "allotment": allot.get("runs"),
                "capacity": capacity_report(plane, now),
                "measurement_kind": extra.get("measurement_kind", "execution" if observed is not None else "unknown"),
                "coverage": extra.get("coverage", "unknown"),
                "native_counts": extra.get("native_counts"),
                "configured_enabled": extra.get("configured_enabled"),
                "window": allot.get("window"),
                "entitlement": allot.get("entitlement"),
                "declared": declared,
                "observed": observed,
                "allocation_gap": allocation_gap,
                "execution_gap": execution_gap,
                "verdict": verdict,
                "evidence": kind,
                "readback_overdue": readback_overdue,
                "readback_fresh": extra.get("readback_fresh") is True,
                "readback_max_age_days": extra.get("readback_max_age_days"),
                "witness_report_date": extra.get("witness_report_date"),
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
    stale = [
        p["plane"] for p in unmeasured
        if p["readback_overdue"] or (
            p["evidence"] != "none" and not (
                p["readback_fresh"] and p["measurement_kind"] in {"configuration", "native-evidence"}
            )
        )
    ]
    measurable = [p for p in planes if p["evidence"] != "none"]
    measured = [p for p in measurable if p["observed"] is not None]
    status = "fail" if red else ("stale-readback" if stale else "pass")
    return {
        "schema_version": "limen.schedule_utilization.v1",
        "day": today.isoformat(),
        "as_of": now.isoformat(timespec="seconds"),
        "status": status,
        "operational_readiness": "degraded" if red else "unverified",
        "coverage_gaps": registry.get("coverage_gaps", []),
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
                fh.write(
                    json.dumps(
                        {
                            "ts": report["generated_at"],
                            "day": report["day"],
                            **{
                                k: plane[k] for k in ("plane", "allotment", "window", "declared", "observed", "verdict")
                            },
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )


def print_table(report: dict) -> None:
    print(
        f"schedule-utilization {report['day']} — {len(report['planes'])} planes; measured {report['measured']}; "
        f"red={report['red'] or 'none'}; unmeasured={report['unmeasured'] or 'none'}; stale-readback={report['stale_readback'] or 'none'}"
    )
    print(f"{'plane':28} {'allot':>6} {'window':13} {'decl':>5} {'obs':>5}  verdict               detail")
    for p in report["planes"]:
        obs = "—" if p["observed"] is None else str(p["observed"])
        allot = "—" if p["allotment"] is None else str(p["allotment"])
        print(
            f"{p['plane']:28} {allot:>6} {str(p['window']):13} {p['declared']:>5} {obs:>5}  {p['verdict']:21} {p['detail']}"
        )
        if p["verdict"] in RED_VERDICTS:
            print(f"  ↑ {p['plane']} is {p['verdict']} — effector: {p['effector']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--registry", type=Path, help="offline registry override; relative locators use --root")
    parser.add_argument("--snapshot", type=Path, help="bounded private native metadata snapshot override")
    parser.add_argument("--day", default=None, help="UTC day to evaluate (YYYY-MM-DD; default today)")
    parser.add_argument(
        "--receipt", default=None, help="write the JSON receipt here (atomic) and append history beside it"
    )
    parser.add_argument("--json", action="store_true", help="print the report as JSON instead of a table")
    args = parser.parse_args(argv)
    root = Path(args.root)
    today = date.fromisoformat(args.day) if args.day else datetime.now(timezone.utc).date()
    report = evaluate(root, today, registry_path=args.registry, snapshot_path=args.snapshot)
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
