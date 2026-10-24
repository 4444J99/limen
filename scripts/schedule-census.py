#!/usr/bin/env python3
"""schedule-census — every schedule attempt across the GitHub universe, live and historical, as one ledger.

#3178 (the SCHEDULES registry) declares the planes limen already knows about. This organ answers the wider
question the owner asked on 2026-10-23 — *all schedule attempts from the history of the whole GitHub
universe* — by reading every repository the owner accounts hold and every carrier a schedule can live in:

  gh-workflow          .github/workflows/*.yml `on.schedule` — live state from the Actions API
                       (active | disabled_inactivity | disabled_manually), crons from the file
  gh-scheduled-runs    actions/runs?event=schedule — what actually FIRED (bounded by Actions run
                       retention; the names of deleted workflows survive here)
  gh-workflow-history  git history of the workflow dir (a full local clone) or the Commits API (capped,
                       sampled newest+oldest, flagged truncated) — first seen, cron changes, removals
  wrangler / cloudflare-manifest / vercel / launchd / crontab / systemd-timer / dependabot / renovate /
  cloud-routines       declared schedules in the default-branch tree (one recursive tree listing, then
                       only the carriers are read)
  NOT READ HERE        ChatGPT, Jules native, Gemini and Grok schedules (no GitHub record: schedules.yaml
                       declared rows via L-SCHED-READBACKS), Cloudflare account-level crons configured in
                       the dashboard rather than a repo

Data grounding: the receipt states the universe source and count, how many repos were scanned, unreachable
or left unscanned by the time budget, and which channels were read — before any conclusion. "I read
nothing" (unreachable) is never rendered as "nothing is scheduled" (no declarations).

Reads only: every GitHub call is a `gh api` GET; nothing here can start, retry, disable or deploy a run.
Receipt: logs/schedule-census.json (atomic) + optional Markdown ledger. The organ owns its own wall-clock
interval (`--interval-hours`, default 168) so a metabolize-pass caller stays cheap between censuses; an
incomplete receipt (read nothing; an owner whose repository listing failed; more than a quarter of the universe
unreachable, unscanned, partially read or errored) earns only the shorter `--retry-hours` horizon, and a pass that reads fewer repositories than the standing receipt is written beside
it as `*.last-attempt.json` instead of over it.

Every repository row carries a per-channel read status; a row whose essential channels were not all read is
`partial` and may confirm what it saw but never concludes absence. Exit codes: 0 clean and complete · 1 findings
on the scanned set (a registry gap, declared-never-fired, firing-but-failing, auto-disabled) · 2 no findings
but coverage incomplete · 3 read nothing · 4 an internal error in the engine itself (the receipt names it).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import plistlib
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

try:  # py311+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import _schedules as S  # noqa: E402

SCHEMA = "limen.schedule_census.v1"
ESTATE_CACHE_SCHEMA = "limen.estate_repos.v1"
GH_TIMEOUT = 25
DEFAULT_RECEIPT = ROOT / "logs" / "schedule-census.json"
DEFAULT_LEDGER = ROOT / "logs" / "schedule-census.md"
DEFAULT_ESTATE_CACHE = ROOT / "logs" / "estate-repos.json"
WORKFLOW_DIR = ".github/workflows"
OK, ABSENT, UNREACHABLE, ERROR = "ok", "absent", "unreachable", "error"
RATE_FLOOR = 200  # core-quota calls kept in hand before a repository scan (the largest single scan stays under it)
RATE_CHECK_EVERY_CALLS = 50
WORKFLOW_LIST_PAGES = 10
ESSENTIAL_CHANNELS = ("tree", "actions-workflows", "contents", "scheduled-runs")
FINDING_VERDICTS = frozenset({"declared-never-fired", "firing-but-failing", "auto-disabled"})
HYGIENE_KINDS = frozenset({"dependabot", "renovate"})  # dependency-update schedules: hygiene, not an operator scheduler
RUN_LISTING_CAP = 2500  # the Actions run listing stops counting here; a total at the cap is a floor, not a count
DEFAULT_RETRY_HOURS = 24.0
MAX_INCOMPLETE_SHARE = S.CENSUS_MAX_INCOMPLETE_SHARE

CHANNELS = {
    "gh-workflow": "Actions workflow files with on.schedule; state from the Actions API",
    "gh-scheduled-runs": "actions/runs?event=schedule (fired; bounded by Actions run retention)",
    "gh-workflow-history": "git history of .github/workflows (full clone) or the Commits API (capped)",
    "wrangler": "wrangler.toml/.json(c) [triggers] crons",
    "cloudflare-manifest": "ops-style cloudflare/src/manifest.ts targets (name, schedule, maxInvocationsPerDay)",
    "vercel": "vercel.json crons",
    "launchd": "*.plist StartInterval / StartCalendarInterval",
    "crontab": "crontab files",
    "systemd-timer": "*.timer OnCalendar",
    "dependabot": ".github/dependabot.yml update schedules",
    "renovate": "renovate.json schedule",
    "cloud-routines": "cloud-routines.json (claude.ai routines manifest)",
    "gh-issues-prs": "issues and pull requests whose title or labels name scheduling — speech acts about attempts, never executions; newest 300 per repository",
}
NOT_READ = {
    "chatgpt-scheduled-tasks": "no GitHub record — schedules.yaml declared rows only (L-SCHED-READBACKS)",
    "jules-native-scheduled-tasks": "no GitHub record — schedules.yaml plane, unmeasured until the readback",
    "gemini-scheduled-actions": "no GitHub record",
    "grok-automations": "no GitHub record",
    "cloudflare-dashboard-crons": "account-level crons configured outside any repository",
}
CARRIER_RX: dict[str, re.Pattern[str]] = {
    "gh-workflow": re.compile(r"^\.github/workflows/[^/]+\.ya?ml$"),
    "wrangler": re.compile(r"(^|/)wrangler\.(toml|json|jsonc)$"),
    "cloudflare-manifest": re.compile(r"(^|/)cloudflare/src/manifest\.ts$"),
    "vercel": re.compile(r"(^|/)vercel\.json$"),
    "launchd": re.compile(r"\.plist$"),
    "crontab": re.compile(r"(^|/)crontab(\.[^/]+)?$"),
    "systemd-timer": re.compile(r"\.timer$"),
    "dependabot": re.compile(r"^\.github/dependabot\.ya?ml$"),
    "renovate": re.compile(r"(^|/)renovate\.json5?$"),
    "cloud-routines": re.compile(r"(^|/)cloud-routines\.json$"),
}
CRON_LINE_RX = re.compile(r"""^\s*-?\s*cron:\s*["']?([^"'\n#]+?)["']?\s*(#.*)?$""")
CRONTAB_RX = re.compile(r"^\s*(@\w+|(\S+\s+){4}\S+)\s+\S")
BAD_CONCLUSIONS = {"failure", "cancelled", "timed_out", "startup_failure", "action_required"}
ATTEMPT_RX = re.compile(
    r"(?i)\b(schedul\w*|cron\w*|routines?|heartbeat|launchd|crontab|nightly|hourly|automations?|scheduled[- ]tasks?|timers?|cadence|keepalive|dispatcher)\b"
)
ATTEMPT_PAGES = 3


# ── gh access (every call a GET; tests monkeypatch gh_api) ───────────────────────────────────


def gh_available() -> bool:
    import shutil

    return shutil.which("gh") is not None


def gh_api(path: str) -> tuple[str, object | None]:
    """(OK|ABSENT|UNREACHABLE|ERROR, payload). `gh api` prints the error body to stdout, so a 404 can be told
    from a session-bound 403 ("not enabled for this session") or a network cut; none of them is "no schedule"."""
    if not gh_available():
        return UNREACHABLE, None
    try:
        run = subprocess.run(["gh", "api", path], capture_output=True, text=True, timeout=GH_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError):
        return UNREACHABLE, None
    try:
        payload = json.loads(run.stdout) if run.stdout.strip() else None
    except json.JSONDecodeError:
        payload = None
    if run.returncode == 0:
        return OK, payload
    message = str((payload or {}).get("message", "")) if isinstance(payload, dict) else ""
    status = str((payload or {}).get("status", "")) if isinstance(payload, dict) else ""
    if status == "404" or message == "Not Found":
        return ABSENT, payload
    if status in {"401", "403"} or "not enabled for this session" in message or "not available" in message:
        return UNREACHABLE, payload
    return ERROR, payload


def _decode_contents(payload: object) -> str | None:
    if isinstance(payload, dict) and payload.get("encoding") == "base64":
        try:
            return base64.b64decode(payload.get("content") or "").decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None
    return None


def rate_limit_state() -> tuple[int, int] | None:
    """(remaining, reset_epoch) for the core API, or None when it cannot be read."""
    st, payload = gh_api("rate_limit")
    resources = payload.get("resources") if st == OK and isinstance(payload, dict) else None
    core = resources.get("core") if isinstance(resources, dict) else None
    if not isinstance(core, dict):
        return None
    try:
        return int(core.get("remaining")), int(core.get("reset"))
    except (TypeError, ValueError):
        return None


def rate_guard(*, floor: int = RATE_FLOOR, deadline: float | None = None, sleep=time.sleep, now=time.time) -> str:
    """Before a repository scan: if the core quota is nearly spent, wait for the reset when the budget allows it,
    else say so. Returns "ok", "slept:<seconds>" or "exhausted" (the caller stops and lists the unscanned)."""
    state = rate_limit_state()
    if state is None:
        return "ok"
    remaining, reset = state
    if remaining >= floor:
        return "ok"
    wait = max(0.0, reset - now()) + 5.0
    if deadline is not None and now() + wait > deadline:
        return "exhausted"
    sleep(wait)
    return f"slept:{int(wait)}"


# ── universe ────────────────────────────────────────────────────────────────────────────────


def universe_from_estate_cache(path: Path) -> tuple[list[dict], str] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("schema") != ESTATE_CACHE_SCHEMA:
        return None
    repos = data.get("repos") or {}
    rows = [{"repo": name, **(meta if isinstance(meta, dict) else {})} for name, meta in sorted(repos.items())]
    return rows, f"estate-cache:{path}"


def universe_from_gh_repo_list(owners: list[str] | None = None) -> tuple[list[dict], str, list[str]] | None:
    """Host path: `gh repo list <owner>` per owner (the identity plus its orgs, unless LIMEN_OWNERS pins them).
    Returns (rows, source, unlisted owners): an owner whose listing failed is NAMED, so the universe is never
    silently smaller than the account set — a reduced denominator would read as complete coverage."""
    if not gh_available():
        return None
    if not owners:
        st, me = gh_api("user")
        if st != OK or not isinstance(me, dict):
            return None
        owners = [str(me.get("login"))]
        st, orgs = gh_api("user/orgs?per_page=100")
        if st == OK and isinstance(orgs, list):
            owners += [str(o.get("login")) for o in orgs if isinstance(o, dict) and o.get("login")]
    rows: list[dict] = []
    unlisted: list[str] = []
    for owner in owners:
        try:
            run = subprocess.run(
                [
                    "gh",
                    "repo",
                    "list",
                    owner,
                    "--limit",
                    "1000",
                    "--json",
                    "nameWithOwner,isArchived,isFork,isPrivate,pushedAt",
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if run.returncode != 0:
                unlisted.append(owner)
                continue
            items = json.loads(run.stdout) if run.stdout.strip() else []
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            unlisted.append(owner)
            continue
        for it in items:
            if isinstance(it, dict) and it.get("nameWithOwner"):
                rows.append(
                    {
                        "repo": it["nameWithOwner"],
                        "archived": bool(it.get("isArchived")),
                        "fork": bool(it.get("isFork")),
                        "private": it.get("isPrivate"),
                        "pushed_at": it.get("pushedAt"),
                    }
                )
    if not rows:
        return None
    listed = [o for o in owners if o not in unlisted]
    return sorted(rows, key=lambda r: r["repo"]), f"gh-repo-list:{','.join(listed)}", unlisted


def resolve_universe(
    explicit: list[str], repos_file: Path | None, estate_cache: Path
) -> tuple[list[dict], str, list[str]]:
    """(universe rows, source, unlisted owners). The third element is non-empty only on the gh-repo-list path,
    when one owner's listing failed: that universe is incomplete and the receipt must say so."""
    if explicit:
        return [{"repo": r} for r in explicit], "explicit", []
    if repos_file is not None:
        names = [
            ln.strip()
            for ln in repos_file.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")
        ]
        return [{"repo": r} for r in names], f"repos-file:{repos_file}", []
    cached = universe_from_estate_cache(estate_cache)
    if cached is not None:
        return cached[0], cached[1], []
    found = universe_from_gh_repo_list(_owners_pin())
    if found is None:
        return [], "none", []
    return found


def _owners_pin() -> list[str] | None:
    raw = (os.environ.get("LIMEN_OWNERS") or "").strip()
    return [o.strip() for o in raw.split(",") if o.strip()] or None


# ── carrier parsers: text -> schedule (None = the carrier could not be parsed; empty = parsed, no schedule) ─


def _on_block(data: object) -> dict | None:
    if not isinstance(data, dict):
        return None
    on = data.get("on")
    if on is None:
        on = data.get(True)  # PyYAML reads a bare `on:` key as boolean True
    return on if isinstance(on, dict) else None


def cron_rate(cron: str) -> tuple[float | None, str]:
    """(nominal fires per day, cadence label) from the cron's own fields — _schedules.cron_fires_per_day /
    cadence_label, shared with the utilization sensor so the two never label one cron differently. Never the
    registry's routine-parity classes, which read `*/30 * * * *` as "daily" because no day field is restricted."""
    try:
        c = S.parse_cron(cron)
    except Exception:  # noqa: BLE001 — a cron we cannot parse is still a declaration
        return None, "unparsed"
    return S.cron_fires_per_day(c), S.cadence_label(c)


def _cron_cadence(cron: str) -> str:
    return cron_rate(cron)[1]


def _fires_per_day(crons: list[str]) -> float:
    return round(sum(cron_rate(c)[0] or 0.0 for c in crons), 3)


def parse_workflow(text: str) -> list[str] | None:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        found = [m.group(1).strip() for m in map(CRON_LINE_RX.match, text.splitlines()) if m]
        return found or None  # regex fallback; a broken file with no cron line is unparseable, not "no schedule"
    on = _on_block(data)
    sched = on.get("schedule") if on else None
    if isinstance(sched, dict):
        sched = [sched]
    if not isinstance(sched, list):
        return []
    crons: list[str] = []
    for entry in sched:
        if isinstance(entry, dict) and entry.get("cron"):
            crons.append(str(entry["cron"]).strip())
    return crons


_JSON_COMMENT_RX = re.compile(r'("(?:\\.|[^"\\])*")|/\*.*?\*/|//[^\n]*', re.S)
_JSON_TRAILING_COMMA_RX = re.compile(r'("(?:\\.|[^"\\])*")|,(\s*[}\]])', re.S)


def _strip_json_comments(text: str) -> str:
    """Drop // and /* */ comments and trailing commas outside string literals (jsonc), leaving strings intact."""
    without_comments = _JSON_COMMENT_RX.sub(lambda m: m.group(1) or "", text)
    return _JSON_TRAILING_COMMA_RX.sub(lambda m: m.group(1) or m.group(2), without_comments)


def _str_list(value: object) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if v is not None]
    return [str(value)] if isinstance(value, (str, int)) and value != "" else []


_WRANGLER_TRIGGERS_RX = re.compile(r"^\s*\[triggers\]\s*$", re.M)
_WRANGLER_CRONS_RX = re.compile(r"^\s*crons\s*=\s*\[(.*?)\]", re.M | re.S)
_QUOTED_RX = re.compile(r"""["']([^"']+)["']""")


def parse_wrangler(path: str, text: str) -> list[str] | None:
    """[triggers] crons. A file the TOML/JSON parser rejects (wrangler tolerates e.g. a `[vars]` table declared
    twice) is read again by regex: no `[triggers]` table means no schedule; a table whose crons cannot be read
    is unparseable."""
    if path.endswith(".toml"):
        data = None
        if tomllib is not None:
            try:
                data = tomllib.loads(text)
            except (tomllib.TOMLDecodeError, ValueError):
                data = None
        if data is None:
            if not _WRANGLER_TRIGGERS_RX.search(text):
                return None if re.search(r"\bcrons\b", text) else []  # a cron mentioned outside a table is unreadable
            block = text[_WRANGLER_TRIGGERS_RX.search(text).end() :]
            m = _WRANGLER_CRONS_RX.search(block)
            return _QUOTED_RX.findall(m.group(1)) if m else None
    else:
        try:
            data = json.loads(_strip_json_comments(text))
        except json.JSONDecodeError:
            return None
    triggers = data.get("triggers") if isinstance(data, dict) else None
    return _str_list(triggers.get("crons")) if isinstance(triggers, dict) else []


def parse_vercel(text: str) -> list[dict] | None:
    try:
        data = json.loads(_strip_json_comments(text))
    except json.JSONDecodeError:
        return None
    crons = data.get("crons") if isinstance(data, dict) else None
    return [c for c in crons if isinstance(c, dict)] if isinstance(crons, list) else []


_PLIST_INTERVAL_RX = re.compile(r"<key>\s*StartInterval\s*</key>\s*<integer>\s*(\d+)\s*</integer>")
_PLIST_LABEL_RX = re.compile(r"<key>\s*Label\s*</key>\s*<string>\s*([^<]+?)\s*</string>")


def parse_launchd(text: str) -> dict | None:
    """None = not a plist; {} = a plist that schedules nothing; else interval/calendar keys plus the plist's
    `Label` (the launchd-host plane keys its rows by Label, falling back to the file stem). A plist expat rejects
    (a `--` inside an XML comment is the common case) is read again by regex for StartInterval and Label; one
    that also carries StartCalendarInterval stays unparseable rather than half-read."""
    try:
        data = plistlib.loads(text.encode("utf-8"))
    except Exception:  # noqa: BLE001 — not a well-formed plist
        if "<plist" not in text:
            return None
        m = _PLIST_INTERVAL_RX.search(text)
        if "StartCalendarInterval" in text:
            return None
        if not m:
            return {}
        out = {"interval_seconds": int(m.group(1)), "parse": "regex"}
        label = _PLIST_LABEL_RX.search(text)
        if label:
            out["label"] = label.group(1)
        return out
    if not isinstance(data, dict):
        return {}
    out: dict = {}
    if isinstance(data.get("StartInterval"), int):
        out["interval_seconds"] = data["StartInterval"]
    cal = data.get("StartCalendarInterval")
    if isinstance(cal, dict):
        cal = [cal]
    if isinstance(cal, list):
        out["calendar"] = [{k: v for k, v in c.items()} for c in cal if isinstance(c, dict)]
    if out and isinstance(data.get("Label"), str) and data["Label"].strip():
        out["label"] = data["Label"].strip()
    return out


def parse_crontab(text: str) -> list[str]:
    return [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#") and CRONTAB_RX.match(ln)
    ]


def parse_timer(text: str) -> list[str]:
    return [ln.split("=", 1)[1].strip() for ln in text.splitlines() if ln.strip().startswith("OnCalendar=")]


def parse_dependabot(text: str) -> list[str] | None:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    updates = data.get("updates") if isinstance(data, dict) else None
    out = []
    for upd in updates if isinstance(updates, list) else []:
        sched = upd.get("schedule") if isinstance(upd, dict) else None
        if isinstance(sched, dict) and sched.get("interval"):
            out.append(
                str(sched["interval"])
                + (f" {sched['day']}" if sched.get("day") else "")
                + (f" {sched['time']}" if sched.get("time") else "")
            )
    return out


def parse_renovate(text: str) -> list[str] | None:
    try:
        data = json.loads(_strip_json_comments(text))
    except json.JSONDecodeError:
        return None
    sched = data.get("schedule") if isinstance(data, dict) else None
    return _str_list(sched)


def parse_cloud_routines(text: str) -> int | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    rows = data.get("routines") if isinstance(data, dict) else data
    if isinstance(rows, dict):
        rows = list(rows.values())
    if not isinstance(rows, list):
        return 0
    return sum(1 for r in rows if isinstance(r, dict) and (r.get("cron") or r.get("cadence") or r.get("schedule")))


def parse_manifest(text: str) -> list[dict]:
    return [
        {"name": m.group("name"), "cron": m.group("cron"), "max_per_day": int(m.group("cap"))}
        for m in S._MANIFEST_TARGET_RX.finditer(text)
    ]


def declaration_for(kind: str, path: str, text: str) -> dict | None:
    """The declaration a carrier file makes, None when it schedules nothing, or {"unparseable": True} when the
    file could not be read as its format — a tri-state, because an unreadable carrier is not "no schedule"."""
    base = {"kind": kind, "path": path}
    unparseable = {**base, "unparseable": True}
    if kind == "gh-workflow":
        crons = parse_workflow(text)
        if crons is None:
            return unparseable
        return (
            {
                **base,
                "crons": crons,
                "cadence": [_cron_cadence(c) for c in crons],
                "fires_per_day": _fires_per_day(crons),
            }
            if crons
            else None
        )
    if kind == "wrangler":
        crons = parse_wrangler(path, text)
        if crons is None:
            return unparseable
        return (
            {
                **base,
                "crons": crons,
                "cadence": [_cron_cadence(c) for c in crons],
                "fires_per_day": _fires_per_day(crons),
            }
            if crons
            else None
        )
    if kind == "cloudflare-manifest":
        targets = parse_manifest(text)
        return {**base, "targets": targets} if targets else None
    if kind == "vercel":
        crons = parse_vercel(text)
        if crons is None:
            return unparseable
        return (
            {**base, "crons": [str(c.get("schedule")) for c in crons], "paths": [str(c.get("path")) for c in crons]}
            if crons
            else None
        )
    if kind == "launchd":
        parsed = parse_launchd(text)
        if parsed is None:
            return unparseable
        return {**base, **parsed} if parsed else None
    if kind == "crontab":
        lines = parse_crontab(text)
        return {**base, "crons": lines} if lines else None
    if kind == "systemd-timer":
        cal = parse_timer(text)
        return {**base, "on_calendar": cal} if cal else None
    if kind == "dependabot":
        intervals = parse_dependabot(text)
        if intervals is None:
            return unparseable
        return {**base, "intervals": intervals} if intervals else None
    if kind == "renovate":
        sched = parse_renovate(text)
        if sched is None:
            return unparseable
        return {**base, "schedule": sched} if sched else None
    if kind == "cloud-routines":
        n = parse_cloud_routines(text)
        if n is None:
            return unparseable
        return {**base, "routines": n} if n else None
    return None


# ── fired: scheduled runs ───────────────────────────────────────────────────────────────────


def summarize_scheduled_runs(page1: dict | None, oldest_page: dict | None = None) -> dict:
    """Newest page (and the deepest page when it could be read). total_count at RUN_LISTING_CAP is a floor;
    oldest_seen without the deepest page is page one's edge, never the first run."""
    runs = (page1 or {}).get("workflow_runs")
    runs = [r for r in runs if isinstance(r, dict)] if isinstance(runs, list) else []
    try:
        total = int((page1 or {}).get("total_count") or 0)
    except (TypeError, ValueError):
        total = len(runs)
    by_workflow: dict[str, dict] = {}
    for r in runs:
        name = str(r.get("name") or r.get("path") or "?")
        row = by_workflow.setdefault(
            name, {"runs_on_page": 0, "last_at": None, "last_conclusion": None, "failed_on_page": 0}
        )
        row["runs_on_page"] += 1
        if row["last_at"] is None:  # page is newest-first
            row["last_at"] = r.get("created_at")
            row["last_conclusion"] = r.get("conclusion")
        if r.get("conclusion") in BAD_CONCLUSIONS:
            row["failed_on_page"] += 1
    newest = runs[0].get("created_at") if runs else None
    old_runs = (oldest_page or {}).get("workflow_runs")
    old_runs = [r for r in old_runs if isinstance(r, dict)] if isinstance(old_runs, list) else []
    oldest = old_runs[-1].get("created_at") if old_runs else (runs[-1].get("created_at") if runs else None)
    return {
        "total_scheduled_runs": total,
        "listing_capped": total >= RUN_LISTING_CAP,
        "oldest_page_read": bool(old_runs),
        "newest": newest,
        "oldest_seen": oldest,
        "by_workflow": by_workflow,
        "retention_note": "GitHub keeps Actions run records for the repository's retention window (90 days by default); older attempts are visible only in git history",
    }


# ── attempt discourse: issues and PRs that talk about scheduling ────────────────────────────


def read_attempts(repo: str, call, pages: int = ATTEMPT_PAGES, *, deadline: float | None = None) -> dict:
    """Issues and PRs (the /issues listing carries both) whose title or labels match ATTEMPT_RX. These are
    speech acts — a plan, a proposal, a PR — not evidence anything ran; the receipt keeps them apart. `deadline`
    (time.monotonic()) stops the pager between pages so a slow listing never outlives the census budget."""
    items: list[dict] = []
    seen = 0
    truncated = False
    repo_tokens = {tok for tok in re.split(r"[^a-z0-9]+", repo.lower()) if tok}
    for page in range(1, pages + 1):
        if page > 1 and deadline is not None and time.monotonic() > deadline:
            return {
                "readable": True,
                "status": "partial",
                "items": items,
                "seen": seen,
                "truncated": True,
                "note": f"issues listing stopped after {page - 1} page(s): census budget reached",
            }
        st, rows = call(f"repos/{repo}/issues?state=all&per_page=100&page={page}&sort=created&direction=desc")
        if st != OK or not isinstance(rows, list):
            status = st if st != OK else ERROR
            return {
                "readable": False,
                "status": status,
                "items": items,
                "seen": seen,
                "truncated": True,
                "note": f"issues listing {status}",
            }
        seen += len(rows)
        for it in rows:
            if not isinstance(it, dict):
                continue
            title = str(it.get("title") or "")
            raw_labels = it.get("labels") if isinstance(it.get("labels"), list) else []
            labels = [str(lab.get("name") or "") for lab in raw_labels if isinstance(lab, dict)]
            hits = {m.group(1).lower() for m in ATTEMPT_RX.finditer(title)}
            for lab in labels:
                hits |= {m.group(1).lower() for m in ATTEMPT_RX.finditer(lab)}
            if (
                not hits or hits <= repo_tokens
            ):  # "automation" inside universal-mail--automation names the repo, not a schedule
                continue
            pr = it.get("pull_request") if isinstance(it.get("pull_request"), dict) else None
            items.append(
                {
                    "number": it.get("number"),
                    "kind": "pr" if pr else "issue",
                    "title": title[:140],
                    "state": it.get("state"),
                    "created_at": it.get("created_at"),
                    "closed_at": it.get("closed_at"),
                    "merged": bool(pr.get("merged_at")) if pr else None,
                    "labels": labels[:6],
                }
            )
        if len(rows) < 100:
            break
        if page == pages:
            truncated = True
    return {"readable": True, "status": OK, "items": items, "seen": seen, "truncated": truncated}


# ── history ─────────────────────────────────────────────────────────────────────────────────


def _git(clone: Path, *args: str) -> str | None:
    try:
        run = subprocess.run(["git", "-C", str(clone), *args], capture_output=True, text=True, timeout=120, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return run.stdout if run.returncode == 0 else None


def clone_is_full(clone: Path | None) -> bool:
    if clone is None or not (clone / ".git").exists():
        return False
    out = _git(clone, "rev-parse", "--is-shallow-repository")
    return out is not None and out.strip() == "false"


def history_from_git(clone: Path) -> dict:
    """Full-clone history: every commit touching a carrier path, with the cron lines it added/removed."""
    log = (
        _git(clone, "log", "--all", "--date-order", "--format=commit %H %cI", "--name-status", "--", WORKFLOW_DIR) or ""
    )
    events: list[dict] = []
    sha = at = None
    for line in log.splitlines():
        if line.startswith("commit "):
            _, sha, at = line.split(" ", 2)
            continue
        if not line.strip() or sha is None:
            continue
        parts = line.split("\t")
        status, path = parts[0][0], parts[-1]
        change = {"A": "added", "D": "removed", "M": "modified", "R": "renamed"}.get(status, status)
        events.append({"at": at, "sha": sha[:10], "path": path, "change": change})
    patches = _git(clone, "log", "--all", "--date-order", "--format=commit %H", "-p", "--", WORKFLOW_DIR) or ""
    # keyed by (commit, path): a commit that moves a cron in a.yml and edits a comment in b.yml must not hand
    # b.yml a scheduling attempt it never had
    added: dict[tuple[str, str], list[str]] = {}
    removed: dict[tuple[str, str], list[str]] = {}
    cur = None
    cur_path = None
    for line in patches.splitlines():
        if line.startswith("commit "):
            cur = line.split(" ", 1)[1][:10]
            cur_path = None
            continue
        if line.startswith("diff --git "):
            cur_path = _diff_header_path(line)
            continue
        if cur is None or cur_path is None or len(line) < 2 or line.startswith(("+++", "---")):
            continue
        m = CRON_LINE_RX.match(line[1:])
        if m and line[0] == "+":
            added.setdefault((cur, cur_path), []).append(m.group(1).strip())
        elif m and line[0] == "-":
            removed.setdefault((cur, cur_path), []).append(m.group(1).strip())
    for ev in events:
        ev["crons_added"] = added.get((ev["sha"], ev["path"]), [])
        ev["crons_removed"] = removed.get((ev["sha"], ev["path"]), [])
    commits = {e["sha"] for e in events}
    return {"source": "git", "status": OK, "commits_seen": len(commits), "truncated": False, "events": events}


DIFF_HEADER_RX = re.compile(r'^diff --git (?:"a/.*?"|a/.*?) (?:"b/(.*)"|b/(.*))$')


def _diff_header_path(line: str) -> str | None:
    """`diff --git a/<old> b/<new>` → <new>: the path --name-status reports for a rename, and the only path for an
    add, edit or delete. Quoted paths (spaces, non-ASCII) are unquoted."""
    m = DIFF_HEADER_RX.match(line.rstrip())
    if not m:
        return None
    path = m.group(1) if m.group(1) is not None else m.group(2)
    return path or None


def _patch_crons(patch: str, sign: str) -> list[str]:
    return [
        m.group(1).strip()
        for m in (CRON_LINE_RX.match(ln[1:]) for ln in patch.splitlines() if ln.startswith(sign))
        if m
    ]


def history_from_api(repo: str, cap: int, *, deadline: float | None = None) -> dict:
    """Commits API sample (newest + oldest, capped). `deadline` is a time.monotonic() bound: the per-commit detail
    requests stop there and the remainder is recorded as unread, so a slow history never outlives the census
    budget (the sensor's execution timeout would otherwise kill the pass before any receipt is written)."""
    st, commits = gh_api(f"repos/{repo}/commits?path={WORKFLOW_DIR}&per_page=100")
    if st != OK or not isinstance(commits, list):
        status = st if st != OK else ERROR
        return {
            "source": "api",
            "status": status,
            "commits_seen": 0,
            "truncated": True,
            "events": [],
            "note": f"commit listing {status}",
        }
    shas = [str(c.get("sha")) for c in commits if isinstance(c, dict) and c.get("sha")]
    cap = max(2, int(cap))
    sample = shas if len(shas) <= cap else shas[: cap - cap // 2] + shas[-(cap // 2) :]
    events: list[dict] = []
    unread = 0
    stopped = 0  # sampled commits left unread because the census budget ran out
    for i, sha in enumerate(sample):
        if deadline is not None and time.monotonic() > deadline:
            stopped = len(sample) - i
            break
        st, detail = gh_api(f"repos/{repo}/commits/{sha}")
        if st != OK or not isinstance(detail, dict):
            unread += 1
            continue
        commit = detail.get("commit") if isinstance(detail.get("commit"), dict) else {}
        committer = commit.get("committer") if isinstance(commit.get("committer"), dict) else {}
        at = committer.get("date")
        files = detail.get("files") if isinstance(detail.get("files"), list) else []
        for f in files:
            if not isinstance(f, dict) or not str(f.get("filename", "")).startswith(WORKFLOW_DIR + "/"):
                continue
            patch = str(f.get("patch") or "")
            events.append(
                {
                    "at": at,
                    "sha": sha[:10],
                    "path": f["filename"],
                    "change": str(f.get("status")),
                    "crons_added": _patch_crons(patch, "+"),
                    "crons_removed": _patch_crons(patch, "-"),
                }
            )
    truncated = len(shas) > cap or len(commits) >= 100 or stopped > 0
    out = {
        "source": "api",
        "status": OK if not (unread or stopped) else "partial",
        "commits_seen": len(shas),
        "truncated": truncated,
        "events": events,
        "sampled": len(sample),
    }
    notes = []
    if unread:
        notes.append(f"{unread} of {len(sample)} sampled commits unreadable")
    if stopped:
        notes.append(f"{stopped} of {len(sample)} sampled commits unread: census budget reached")
    if notes:
        out["note"] = "; ".join(notes)
    return out


# ── per-repo scan ───────────────────────────────────────────────────────────────────────────


def _blank_row(repo: str) -> dict:
    return {
        "repo": repo,
        "reach": OK,
        "declarations": [],
        "fired": None,
        "history": None,
        "attempts": None,
        "notes": [],
        "api_calls": 0,
        "failing_workflows": [],
        "actions_registered_not_in_tree": [],
        "channels": {},
        "partial": False,
        "verdict": None,
    }


def scan_repo(repo: str, *, clone: Path | None = None, history_cap: int = 30, deadline: float | None = None) -> dict:
    """One repository, every channel. Each channel's read status lands in row["channels"]; a repository whose
    essential channels (tree, workflow states, scheduled runs, every carrier's contents) were not all read is
    marked partial — its verdict may confirm what it saw but never concludes absence. `deadline` is a
    time.monotonic() bound: past it, the remaining channels are recorded as skipped:budget instead of read."""
    out = _blank_row(repo)
    channels: dict[str, str] = out["channels"]

    def call(path: str) -> tuple[str, object | None]:
        out["api_calls"] += 1
        return gh_api(path)

    def over() -> bool:
        return deadline is not None and time.monotonic() > deadline

    st, meta = call(f"repos/{repo}")
    if st != OK or not isinstance(meta, dict):
        status = st if st != OK else ERROR
        out["reach"] = UNREACHABLE if status in {ABSENT, UNREACHABLE} else ERROR
        channels["metadata"] = status
        out["notes"].append(
            f"repository metadata {status}"
            + (" (missing, renamed, or not visible from this runner)" if status == ABSENT else "")
        )
        out["verdict"] = "unreachable"
        return out
    channels["metadata"] = OK
    out["private"] = bool(meta.get("private"))
    out["archived"] = bool(meta.get("archived"))
    out["fork"] = bool(meta.get("fork"))
    out["default_branch"] = str(meta.get("default_branch") or "main")
    out["pushed_at"] = meta.get("pushed_at")
    branch = out["default_branch"]

    st, tree = call(f"repos/{repo}/git/trees/{branch}?recursive=1")
    paths: list[str] = []
    tree_complete = False
    if st == OK and isinstance(tree, dict) and isinstance(tree.get("tree"), list):
        paths = [str(e.get("path")) for e in tree["tree"] if isinstance(e, dict) and e.get("type") == "blob"]
        if tree.get("truncated"):
            channels["tree"] = "truncated"
            out["notes"].append("tree listing truncated by GitHub — carriers beyond the limit were not seen")
        else:
            channels["tree"] = OK
            tree_complete = True
    elif st == ABSENT and meta.get("size") == 0:
        channels["tree"] = "empty"  # a repository with no commits has no tree to list
        tree_complete = True
    else:
        channels["tree"] = st if st != OK else ERROR
        out["notes"].append(f"tree listing {channels['tree']}")
    carriers = [(kind, p) for p in paths for kind, rx in CARRIER_RX.items() if rx.search(p)]

    states: dict[str, dict] = {}
    states_status = OK
    page = 1
    while True:
        st, wf = call(f"repos/{repo}/actions/workflows?per_page=100&page={page}")
        if st != OK or not isinstance(wf, dict):
            states_status = st if st != OK else ERROR
            break
        items = wf.get("workflows") if isinstance(wf.get("workflows"), list) else []
        for w in items:
            if isinstance(w, dict) and w.get("path"):
                states[str(w["path"])] = {"state": str(w.get("state")), "name": str(w.get("name")), "id": w.get("id")}
        total = wf.get("total_count")
        if len(items) < 100 or (isinstance(total, int) and len(states) >= total):
            break
        if page >= WORKFLOW_LIST_PAGES:
            states_status = "truncated"
            out["notes"].append(f"actions workflows listing stopped after {WORKFLOW_LIST_PAGES} pages")
            break
        page += 1
    channels["actions-workflows"] = states_status
    if states_status not in {OK, "truncated"}:
        out["notes"].append(f"actions workflows listing {states_status} (workflow states unknown)")

    seen_workflow_paths: set[str] = set()
    unread_carriers = 0
    skipped_carriers = 0
    for kind, path in carriers:
        if kind == "gh-workflow":
            seen_workflow_paths.add(path)  # in the tree is in the tree, whether or not its contents could be read
        if over():
            skipped_carriers += 1
            continue
        st, c = call(f"repos/{repo}/contents/{path}?ref={branch}")
        text = _decode_contents(c) if st == OK else None
        if text is None:
            unread_carriers += 1
            out["notes"].append(f"{path}: contents {st if st != OK else 'undecodable'}")
            continue
        decl = declaration_for(kind, path, text)
        if decl is not None and decl.get("unparseable"):
            unread_carriers += 1
            out["notes"].append(f"{path}: {kind} carrier could not be parsed — counted neither way")
            continue
        if kind == "gh-workflow":
            state = states.get(path, {}).get("state", "unknown")
            if decl is None and state != "disabled_inactivity":
                continue  # disabled_inactivity is a verdict GitHub passes only on scheduled workflows
            decl = {
                **(decl or {"kind": kind, "path": path, "crons": [], "cadence": []}),
                "state": state,
                "name": states.get(path, {}).get("name"),
            }
        if decl:
            out["declarations"].append(decl)
    if unread_carriers or skipped_carriers:
        channels["contents"] = f"partial:{unread_carriers} unread,{skipped_carriers} skipped"
    else:
        channels["contents"] = OK
    declared_paths = {d["path"] for d in out["declarations"] if d.get("kind") == "gh-workflow"}
    for path, s in states.items():
        if path in declared_paths or not path.startswith(WORKFLOW_DIR):
            continue
        registered = {
            "kind": "gh-workflow",
            "path": path,
            "crons": [],
            "cadence": [],
            "state": s["state"],
            "name": s["name"],
        }
        if tree_complete and path not in seen_workflow_paths:  # only a complete tree can say a workflow is gone
            out["declarations"].append(
                {
                    **registered,
                    "absent_from_tree": True,
                    "note": "registered with Actions but absent from the default branch",
                }
            )
        elif (
            s["state"] == "disabled_inactivity"
        ):  # a verdict GitHub passes only on scheduled workflows: evidence on its own
            out["declarations"].append(
                {**registered, "note": "state from the Actions API; the workflow file itself was not read"}
            )

    if over():
        channels["scheduled-runs"] = "skipped:budget"
    else:
        st, page1 = call(f"repos/{repo}/actions/runs?event=schedule&per_page=100")
        if st == OK and isinstance(page1, dict):
            channels["scheduled-runs"] = OK
            try:
                total = int(page1.get("total_count") or 0)
            except (TypeError, ValueError):
                total = 0
            oldest_page = None
            if total > 100:
                last = (total + 99) // 100
                st2, oldest_page = call(f"repos/{repo}/actions/runs?event=schedule&per_page=100&page={last}")
                if st2 != OK:
                    oldest_page = None
            out["fired"] = summarize_scheduled_runs(page1, oldest_page if isinstance(oldest_page, dict) else None)
        else:
            channels["scheduled-runs"] = st if st != OK else ERROR
            out["notes"].append(f"scheduled runs listing {channels['scheduled-runs']}")

    if over():
        channels["issues-prs"] = "skipped:budget"
        out["attempts"] = {"readable": False, "status": "skipped:budget", "items": [], "seen": 0, "truncated": True}
    else:
        out["attempts"] = read_attempts(repo, call, deadline=deadline)
        channels["issues-prs"] = str(out["attempts"].get("status") or (OK if out["attempts"]["readable"] else ERROR))

    by = (out.get("fired") or {}).get("by_workflow") or {}
    out["failing_workflows"] = sorted(n for n, v in by.items() if v.get("last_conclusion") in BAD_CONCLUSIONS)
    out["actions_registered_not_in_tree"] = sorted(d["path"] for d in out["declarations"] if d.get("absent_from_tree"))

    if clone_is_full(clone):
        out["history"] = history_from_git(clone)  # type: ignore[arg-type]
        channels["history"] = "git"
    elif over():
        channels["history"] = "skipped:budget"
    else:
        if clone is not None:
            out["notes"].append("local clone is shallow — history read through the Commits API instead")
        out["history"] = history_from_api(repo, history_cap, deadline=deadline)
        channels["history"] = (
            "api"
            + ("" if out["history"].get("status") == OK else f":{out['history'].get('status')}")
            + (":truncated" if out["history"].get("truncated") and out["history"].get("status") == OK else "")
        )

    out["partial"] = any(channels.get(name) not in {OK, "empty"} for name in ESSENTIAL_CHANNELS)
    out["verdict"] = verdict_for_repo(out)
    return out


def verdict_for_repo(row: dict) -> str:
    """One word per repository, from evidence only. unreachable ≠ none, and a partial read ≠ none.

    Positive evidence wins in this order: an active Actions schedule (then: fired-unmeasured when the run listing
    could not be read, declared-never-fired, firing-but-failing, active) → a disabled one (auto-disabled is a
    state GitHub passes only on scheduled workflows, so it stands without the cron lines; a manual disable or a
    fork disable needs them) → a declared cron whose state could not be verified → a schedule outside Actions →
    a cron removed in history → partial (something essential was not read) → none. A row whose only non-Actions
    carriers are dependabot/renovate is hygiene-only: dependency updates are not an operator's scheduler."""
    if row.get("reach") != OK:
        return "unreachable"
    decls = [d for d in row.get("declarations") or [] if isinstance(d, dict)]
    gh = [d for d in decls if d.get("kind") == "gh-workflow"]
    others = [d for d in decls if d.get("kind") != "gh-workflow"]
    timed = [d for d in gh if d.get("crons")]
    active = [d for d in timed if d.get("state") == "active"]
    if active:
        fired = row.get("fired")
        if not isinstance(fired, dict):
            return "fired-unmeasured"
        if int(fired.get("total_scheduled_runs") or 0) == 0:
            return "declared-never-fired"
        by = fired.get("by_workflow") or {}
        if by and all(v.get("last_conclusion") in BAD_CONCLUSIONS for v in by.values()):
            return "firing-but-failing"
        return "active"
    if any(d.get("state") == "disabled_inactivity" for d in gh):
        return "auto-disabled"
    timed_states = {str(d.get("state")) for d in timed}
    if "disabled_manually" in timed_states:
        return "manually-disabled"
    if "disabled_fork" in timed_states:
        return "disabled-fork"
    if timed:
        return "declared-state-unknown"
    if others:
        return "hygiene-only" if {d.get("kind") for d in others} <= HYGIENE_KINDS else "declared-outside-actions"
    hist = row.get("history") or {}
    if any(e.get("crons_removed") for e in (hist.get("events") or []) if isinstance(e, dict)):
        return "abandoned-in-history"
    if row.get("partial"):
        return "partial"
    return "none"


# ── registry parity ─────────────────────────────────────────────────────────────────────────


def load_registry_or_none(root: Path) -> dict | None:
    try:
        return S.load_registry(root)
    except Exception:  # noqa: BLE001 — no registry here is simply no coverage
        return None


def registry_covered_repos(root: Path, self_repo: str | None = None) -> set[str]:
    """The repositories some SPECIFIC schedules.yaml plane already owns — _schedules.specific_plane_repos, the one
    selector the registry gate, the sensor and this census share (a census plane never counts as coverage: it
    owns the remainder, which is what a gap is measured against). The workflows plane's own repository comes
    from the registry itself; `self_repo` only ADDS an explicit override and never replaces that."""
    registry = load_registry_or_none(root)
    return S.specific_plane_repos(registry, self_repo) if registry else set()


def registry_gaps(rows: list[dict], covered: set[str], residual: dict | None = None) -> list[dict]:
    """Repositories outside every SPECIFIC plane that declare an Actions cron GitHub reports active — or whose state
    could not be read (listed under `unverified`: declared, possibly burning, not confirmed). When the registry
    declares residual census planes, each gap carries `owned_by` — the plane that derives it by fact — and is no
    longer a finding; a gap with `owned_by` null is allotment burning outside every plane."""
    gaps = []
    for row in rows:
        if row.get("reach") != OK or row["repo"] in covered:
            continue
        timed = [
            d
            for d in row.get("declarations") or []
            if d.get("kind") == "gh-workflow" and d.get("crons") and d.get("state") in {"active", "unknown"}
        ]
        if timed:
            visibility = "private" if row.get("private") else "public"
            owner = (residual or {}).get(visibility) or (residual or {}).get(None)
            gaps.append(
                {
                    "repo": row["repo"],
                    "workflows": [d["path"] for d in timed],
                    "crons": [c for d in timed for c in d["crons"]],
                    "unverified": [d["path"] for d in timed if d.get("state") != "active"],
                    "owned_by": owner,
                }
            )
    return gaps


def cloudflare_target_crons(registry: dict | None) -> dict[str, list[str]]:
    """cron text → declared job ids on cloudflare-provider planes (the ops scheduler's targets)."""
    out: dict[str, list[str]] = {}
    if not registry:
        return out
    cloudflare = {
        pid
        for pid, p in (registry.get("planes") or {}).items()
        if isinstance(p, dict) and p.get("provider") == "cloudflare"
    }
    for job in S.declared_jobs(registry):
        if job.plane in cloudflare:
            for c in job.crons:
                out.setdefault(c, []).append(job.id)
    return out


def wrangler_shadows(rows: list[dict], target_crons: dict[str, list[str]]) -> list[dict]:
    """A repository's own wrangler [triggers] cron that equals an ops Cloudflare scheduler target's cron: two
    schedulers aimed at one target — an advisory for the owner, never a finding here."""
    shadows = []
    for row in rows:
        if row.get("reach") != OK:
            continue
        for d in row.get("declarations") or []:
            if d.get("kind") != "wrangler" or not d.get("crons"):
                continue
            hits = sorted({jid for c in d["crons"] for jid in target_crons.get(str(c), [])})
            if hits:
                shadows.append({"repo": row["repo"], "path": d["path"], "crons": list(d["crons"]), "shadows": hits})
    return shadows


# ── receipt / ledger ────────────────────────────────────────────────────────────────────────


def build_report(
    rows: list[dict],
    *,
    universe: list[dict],
    universe_source: str,
    unscanned: list[str],
    gaps: list[dict] | None,
    started: float,
    skipped: list[str] | None = None,
    residual_planes: dict | None = None,
    shadows: list[dict] | None = None,
    unlisted_owners: list[str] | None = None,
) -> dict:
    errors = [r for r in rows if r.get("verdict") == "error"]
    scanned = [r for r in rows if r.get("reach") == OK]
    unreachable = [r["repo"] for r in rows if r.get("reach") != OK and r.get("verdict") != "error"]
    partial = [r["repo"] for r in scanned if r.get("partial")]
    verdicts: dict[str, int] = {}
    for r in rows:
        verdicts[r.get("verdict") or "?"] = verdicts.get(r.get("verdict") or "?", 0) + 1
    gh_decl = [d for r in scanned for d in r["declarations"] if d["kind"] == "gh-workflow"]
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "elapsed_seconds": round(time.monotonic() - started, 1),
        "denominators": {
            "universe_source": universe_source,
            "universe_count": len(universe),
            "scanned": len(scanned),
            "scanned_partial": len(partial),
            "unreachable": len(unreachable),
            "unscanned_by_budget": len(unscanned),
            "skipped_archived": len(skipped or []),
            "universe_unlisted_owners": len(unlisted_owners or []),
            "internal_errors": len(errors),
            "note": "conclusions below are about the scanned set only; unreachable, unscanned (time budget or API quota), skipped and errored repositories are listed, never counted as unscheduled; a partial scan confirms what it read and concludes nothing about what it did not; an owner whose repository listing failed leaves the universe itself incomplete",
        },
        "channels_read": CHANNELS,
        "channels_not_read": NOT_READ,
        "totals": {
            "repos_with_any_declaration": sum(1 for r in scanned if r["declarations"]),
            "gh_workflows_with_schedule": sum(1 for d in gh_decl if d.get("crons")),
            "gh_workflows_active": sum(1 for d in gh_decl if d.get("state") == "active" and d.get("crons")),
            "gh_workflows_disabled_inactivity": sum(1 for d in gh_decl if d.get("state") == "disabled_inactivity"),
            "gh_workflows_disabled_manually": sum(
                1 for d in gh_decl if d.get("crons") and d.get("state") == "disabled_manually"
            ),
            "gh_workflows_state_unknown": sum(1 for d in gh_decl if d.get("crons") and d.get("state") == "unknown"),
            "workflows_disabled_any_trigger": sum(1 for d in gh_decl if str(d.get("state", "")).startswith("disabled")),
            "workflows_failing_last_scheduled_run": sum(len(r.get("failing_workflows") or []) for r in scanned),
            "actions_registered_not_in_tree": sum(len(r.get("actions_registered_not_in_tree") or []) for r in scanned),
            "attempt_discourse_items": sum(len((r.get("attempts") or {}).get("items") or []) for r in scanned),
            "repos_with_attempt_discourse": sum(1 for r in scanned if (r.get("attempts") or {}).get("items")),
            "scheduled_runs_listed": sum(int((r.get("fired") or {}).get("total_scheduled_runs") or 0) for r in scanned),
            "repos_with_cron_removed_in_history": sum(
                1
                for r in scanned
                if any(e.get("crons_removed") for e in ((r.get("history") or {}).get("events") or []))
            ),
            "verdicts": verdicts,
        },
        "registry_gaps": gaps,
        "residual_planes": {str(k) if k is not None else "all": v for k, v in (residual_planes or {}).items()},
        "wrangler_shadows": shadows or [],
        "unreachable": unreachable,
        "unscanned_by_budget": unscanned,
        "skipped_archived": list(skipped or []),
        "unlisted_owners": list(unlisted_owners or []),
        "partial": partial,
        "internal_errors": [{"repo": r["repo"], "notes": r.get("notes") or []} for r in errors],
        "repos": rows,
    }


def write_receipt(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=1, sort_keys=False)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load_receipt(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("schema") == SCHEMA else None


def _timed_declarations(decls: list[dict]) -> tuple[list[dict], list[dict]]:
    timed = [
        x
        for x in decls
        if x.get("crons") or x.get("targets") or x.get("interval_seconds") or x.get("calendar") or x.get("on_calendar")
    ]
    return timed, [x for x in decls if x not in timed]


def render_markdown(report: dict) -> str:
    d = report["denominators"]
    t = report["totals"]
    lines = [
        "# Schedule census",
        "",
        f"Generated {report['generated_at']} · universe {d['universe_count']} ({d['universe_source']}) · scanned {d['scanned']} "
        f"(partial {d.get('scanned_partial', 0)}) · unreachable {d['unreachable']} · unscanned by budget {d['unscanned_by_budget']} "
        f"· skipped archived {d.get('skipped_archived', 0)} · internal errors {d.get('internal_errors', 0)} "
        f"· owners unlisted {d.get('universe_unlisted_owners', 0)}",
        "",
        f"Channels read: {', '.join(report['channels_read'])}. Not read here: {', '.join(report['channels_not_read'])}.",
        "",
        f"Declared Actions schedules {t['gh_workflows_with_schedule']} (active {t['gh_workflows_active']}, auto-disabled {t['gh_workflows_disabled_inactivity']}, "
        f"manually disabled {t['gh_workflows_disabled_manually']}, state unknown {t.get('gh_workflows_state_unknown', 0)}); "
        f"scheduled runs listed {t['scheduled_runs_listed']}; repositories with a cron removed in history {t.get('repos_with_cron_removed_in_history', 0)}.",
        "",
        "| repo | verdict | declarations | fired (listed) | history | issues/PRs about scheduling |",
        "|---|---|---|---|---|---|",
    ]
    for r in report["repos"]:
        timed, rest = _timed_declarations(r.get("declarations") or [])
        parts = [
            f"{x['kind']}:{Path(x['path']).name}"
            + (f"[{x.get('state')}]" if x.get("state") else "")
            + (" " + ",".join(x.get("crons") or []) if x.get("crons") else "")
            + (f" {len(x['targets'])} targets" if x.get("targets") else "")
            + (f" every {x['interval_seconds']}s" if x.get("interval_seconds") else "")
            for x in timed[:8]
        ]
        if len(timed) > 8:
            parts.append(f"+{len(timed) - 8} more timed")
        if rest:
            kinds: dict[str, int] = {}
            for x in rest:
                kinds[x["kind"]] = kinds.get(x["kind"], 0) + 1
            parts.append("+" + ", ".join(f"{n} {k}" for k, n in sorted(kinds.items())) + " without a schedule")
        decl = "; ".join(parts) or "—"
        if r.get("failing_workflows"):
            decl += f" · failing: {', '.join(r['failing_workflows'])}"
        fired = r.get("fired") or {}
        fired_s = (
            f"{fired.get('total_scheduled_runs', 0)} (newest {str(fired.get('newest') or '-')[:10]})" if fired else "—"
        )
        hist = r.get("history") or {}
        hist_s = (
            f"{hist.get('source', '-')}: {hist.get('commits_seen', 0)} commits{' (truncated)' if hist.get('truncated') else ''}"
            if hist
            else "—"
        )
        att = r.get("attempts") or {}
        att_s = (
            (
                f"{len(att.get('items') or [])} of {att.get('seen', 0)} read"
                + (" (truncated)" if att.get("truncated") else "")
            )
            if att.get("readable")
            else ("—" if not att else "unreadable")
        )
        verdict = str(r.get("verdict") or "?") + (
            " (partial)" if r.get("partial") and r.get("verdict") != "partial" else ""
        )
        lines.append(f"| {r['repo']} | {verdict} | {decl} | {fired_s} | {hist_s} | {att_s} |")
    history_rows = []
    for r in report["repos"]:
        events = [
            e
            for e in ((r.get("history") or {}).get("events") or [])
            if isinstance(e, dict) and (e.get("crons_added") or e.get("crons_removed") or e.get("change") == "removed")
        ]
        if events:
            history_rows.append((r["repo"], events))
    if history_rows:
        lines += ["", "## Historical attempts (workflow schedules added, changed or removed)", ""]
        for repo, events in history_rows:
            shown = events[:12]
            lines.append(
                f"- **{repo}** ({len(events)}): "
                + "; ".join(
                    f"{str(e.get('at') or '')[:10]} {e.get('change')} {Path(str(e.get('path') or '')).name}"
                    + (f" +[{', '.join(e['crons_added'])}]" if e.get("crons_added") else "")
                    + (f" -[{', '.join(e['crons_removed'])}]" if e.get("crons_removed") else "")
                    for e in shown
                )
                + (f"; +{len(events) - 12} more" if len(events) > 12 else "")
            )
    discourse = [(r["repo"], (r.get("attempts") or {}).get("items") or []) for r in report["repos"]]
    discourse = [(repo, items) for repo, items in discourse if items]
    if discourse:
        lines += ["", "## Issues and pull requests that name scheduling (intent, not execution)", ""]
        for repo, items in discourse:
            shown = items[:10]
            lines.append(
                f"- **{repo}** ({len(items)}): "
                + "; ".join(
                    f"{'PR' if i['kind'] == 'pr' else '#'}{i['number']} {i['title'][:70]} [{i['state']}{', merged' if i.get('merged') else ''}, {str(i.get('created_at') or '')[:10]}]"
                    for i in shown
                )
                + (f"; +{len(items) - 10} more" if len(items) > 10 else "")
            )
    if report.get("registry_gaps"):
        unowned = [g for g in report["registry_gaps"] if not g.get("owned_by")]
        lines += [
            "",
            f"## Actions crons outside every specific schedules.yaml plane ({len(report['registry_gaps'])} repositories; "
            f"{len(unowned)} owned by no plane at all"
            + (
                f"; the rest derived by fact into {', '.join(sorted(set(str(g.get('owned_by')) for g in report['registry_gaps'] if g.get('owned_by'))))}"
                if len(unowned) < len(report["registry_gaps"])
                else ""
            )
            + ")",
            "",
        ]
        for g in report["registry_gaps"]:
            unverified = g.get("unverified") or []
            lines.append(
                f"- {g['repo']}: {', '.join(g['workflows'])} — {', '.join(g['crons'])}"
                + (f" (state unverified: {', '.join(unverified)})" if unverified else "")
                + (f" → {g['owned_by']}" if g.get("owned_by") else " → OWNED BY NO PLANE")
            )
    if report.get("wrangler_shadows"):
        lines += [
            "",
            "## Cloudflare scheduler targets also declared in a repository's own wrangler triggers (two schedulers, one target — advisory)",
            "",
        ]
        for sh in report["wrangler_shadows"]:
            lines.append(f"- {sh['repo']}:{sh['path']} {', '.join(sh['crons'])} shadows {', '.join(sh['shadows'])}")
    partial = [r for r in report["repos"] if r.get("partial")]
    if partial:
        lines += ["", "## Partially read (a channel was unreadable or skipped — absence is not concluded)", ""]
        for r in partial:
            bad = {k: v for k, v in (r.get("channels") or {}).items() if v not in {OK, "empty", "git", "api"}}
            lines.append(f"- {r['repo']}: " + ", ".join(f"{k} {v}" for k, v in sorted(bad.items())))
    notes = [(r["repo"], r.get("notes") or []) for r in report["repos"] if r.get("notes") and r.get("reach") == OK]
    if notes:
        lines += ["", "## Notes", ""]
        for repo, ns in notes:
            lines.append(f"- {repo}: " + "; ".join(ns[:6]) + (f"; +{len(ns) - 6} more" if len(ns) > 6 else ""))
    if report.get("internal_errors"):
        lines += ["", "## Internal errors (the engine, not the repository — fix the census)", ""] + [
            f"- {e['repo']}: {'; '.join(e.get('notes') or [])}" for e in report["internal_errors"]
        ]
    if report.get("unreachable"):
        lines += ["", "## Unreachable from this runner (not scanned, not concluded)", ""] + [
            f"- {u}" for u in report["unreachable"]
        ]
    if report.get("unscanned_by_budget"):
        lines += ["", "## Left unscanned by the time budget", ""] + [f"- {u}" for u in report["unscanned_by_budget"]]
    if report.get("skipped_archived"):
        lines += ["", "## Skipped (archived; --skip-archived — their historical attempts were not read)", ""] + [
            f"- {u}" for u in report["skipped_archived"]
        ]
    if report.get("unlisted_owners"):
        lines += ["", "## Owners whose repository listing failed (the universe itself is incomplete)", ""] + [
            f"- {o}" for o in report["unlisted_owners"]
        ]
    return "\n".join(lines) + "\n"


def receipt_is_complete(report: dict, *, max_incomplete_share: float = MAX_INCOMPLETE_SHARE) -> bool:
    """A receipt that read nothing, whose universe is missing an owner, or that left more than
    `max_incomplete_share` of its universe unread — unreachable, unscanned, partially read or errored — is not a
    census to rest on for a whole interval (a transient outage must earn the retry horizon, not a week).
    _schedules.census_receipt_is_complete holds the rule, shared with the sensor."""
    return S.census_receipt_is_complete(report, max_incomplete_share=max_incomplete_share)


def receipt_is_fresh(
    path: Path, interval_hours: float, now: datetime | None = None, *, retry_hours: float = DEFAULT_RETRY_HOURS
) -> bool:
    """Younger than the interval — but an incomplete receipt only earns the shorter retry horizon."""
    data = load_receipt(path)
    if data is None:
        return False
    try:
        generated = datetime.fromisoformat(str(data.get("generated_at")))
    except (ValueError, TypeError):
        return False
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=timezone.utc)
    horizon = interval_hours if receipt_is_complete(data) else min(interval_hours, retry_hours)
    return (now or datetime.now(timezone.utc)) - generated < timedelta(hours=horizon)


# ── main ────────────────────────────────────────────────────────────────────────────────────


def run_census(
    universe: list[dict],
    universe_source: str,
    *,
    clones: dict[str, Path] | None = None,
    history_cap: int = 30,
    budget_seconds: float = 1500,
    check_registry: bool = False,
    root: Path = ROOT,
    self_repo: str | None = None,
    skip_archived: bool = False,
    rate_check_every_calls: int = RATE_CHECK_EVERY_CALLS,
    unlisted_owners: list[str] | None = None,
) -> dict:
    started = time.monotonic()
    deadline = started + budget_seconds
    wall_deadline = time.time() + budget_seconds
    rows: list[dict] = []
    unscanned: list[str] = []
    skipped: list[str] = []
    exhausted = False
    calls_since_check: int | None = None  # None → check the quota before the first scan
    for entry in universe:
        repo = entry["repo"]
        if skip_archived and entry.get("archived"):
            skipped.append(repo)
            continue
        if exhausted or time.monotonic() > deadline:
            unscanned.append(repo)
            continue
        if calls_since_check is None or calls_since_check >= rate_check_every_calls:
            if rate_guard(deadline=wall_deadline) == "exhausted":
                exhausted = True
                unscanned.append(repo)
                continue
            calls_since_check = 0
        try:
            row = scan_repo(repo, clone=(clones or {}).get(repo), history_cap=history_cap, deadline=deadline)
        except Exception as exc:  # noqa: BLE001 — one repository's surprise never aborts the census
            row = {
                **_blank_row(repo),
                "reach": ERROR,
                "verdict": "error",
                "notes": [f"internal error: {type(exc).__name__}: {exc}"],
            }
        calls_since_check += int(row.get("api_calls") or 0)
        rows.append(row)
    registry = load_registry_or_none(root) if check_registry else None
    residual = S.residual_planes(registry) if registry else {}
    gaps = (
        registry_gaps(rows, S.specific_plane_repos(registry, self_repo) if registry else set(), residual)
        if check_registry
        else None
    )
    return build_report(
        rows,
        universe=universe,
        universe_source=universe_source,
        unscanned=unscanned,
        gaps=gaps,
        started=started,
        skipped=skipped,
        residual_planes=residual if check_registry else None,
        shadows=wrangler_shadows(rows, cloudflare_target_crons(registry)) if check_registry else None,
        unlisted_owners=unlisted_owners,
    )


def exit_code_for(report: dict) -> int:
    """4 internal errors (fix the engine) · 3 read nothing · 1 findings on the scanned set · 2 no findings but
    coverage incomplete (unreachable, unscanned, partial, an owner unlisted) · 0 clean and complete.

    A registry gap is a finding only when no plane owns it: a gap a residual census plane derives by fact is
    declared, measured by the sensor, and held to that plane's ceilings — not a floor to report twice.
    Findings are read from the workflow-level totals as well as the repository verdicts: a verdict is one word per
    repository and `active` outranks an auto-disabled or failing schedule beside a healthy one — the totals
    do not, and the sensor's exit-1 escalation names exactly those."""
    d, t = report["denominators"], report["totals"]
    if d.get("internal_errors"):
        return 4
    if d["scanned"] == 0:
        return 3
    unowned = [g for g in report.get("registry_gaps") or [] if not g.get("owned_by")]
    workflow_findings = int(t.get("gh_workflows_disabled_inactivity") or 0) + int(
        t.get("workflows_failing_last_scheduled_run") or 0
    )
    if unowned or workflow_findings or any(v in FINDING_VERDICTS for v in t["verdicts"]):
        return 1
    if d["unreachable"] or d["unscanned_by_budget"] or d.get("scanned_partial") or d.get("universe_unlisted_owners"):
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--repos", nargs="*", default=[], help="explicit owner/repo list (else estate cache, else gh repo list)"
    )
    ap.add_argument("--repos-file", type=Path, default=None)
    ap.add_argument(
        "--estate-cache", type=Path, default=Path(os.environ.get("LIMEN_ESTATE_REPOS_CACHE") or DEFAULT_ESTATE_CACHE)
    )
    ap.add_argument(
        "--clone", action="append", default=[], metavar="OWNER/REPO=PATH", help="full local clone to read history from"
    )
    ap.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    ap.add_argument(
        "--ledger", type=Path, default=None, help="Markdown ledger path (default beside the receipt; '-' to skip)"
    )
    ap.add_argument(
        "--interval-hours", type=float, default=float(os.environ.get("LIMEN_SCHEDULE_CENSUS_INTERVAL_HOURS") or 168)
    )
    ap.add_argument(
        "--retry-hours",
        type=float,
        default=float(os.environ.get("LIMEN_SCHEDULE_CENSUS_RETRY_HOURS") or DEFAULT_RETRY_HOURS),
        help="hours before an incomplete receipt (read nothing, or too much unread) is retried",
    )
    ap.add_argument(
        "--budget-seconds", type=float, default=float(os.environ.get("LIMEN_SCHEDULE_CENSUS_BUDGET_SECONDS") or 1500)
    )
    ap.add_argument("--history-cap", type=int, default=int(os.environ.get("LIMEN_SCHEDULE_CENSUS_HISTORY_CAP") or 30))
    ap.add_argument(
        "--check-registry", action="store_true", help="list active Actions schedules outside every schedules.yaml plane"
    )
    ap.add_argument(
        "--self-repo",
        default=None,
        help="an extra repository to treat as registry-covered (the workflows plane's own repository is read from the registry itself)",
    )
    ap.add_argument(
        "--skip-archived", action="store_true", help="skip archived repositories (their historical attempts go unread)"
    )
    ap.add_argument("--force", action="store_true", help="run even when the receipt is younger than --interval-hours")
    ap.add_argument(
        "--replace",
        action="store_true",
        help="overwrite the receipt even when this pass read fewer repositories than the standing one",
    )
    ap.add_argument("--json", action="store_true", help="print the report JSON")
    args = ap.parse_args(argv)

    if (
        not args.force
        and args.receipt.exists()
        and receipt_is_fresh(args.receipt, args.interval_hours, retry_hours=args.retry_hours)
    ):
        print(
            f"schedule-census: receipt {args.receipt} is younger than its horizon ({args.interval_hours:g}h complete, "
            f"{args.retry_hours:g}h incomplete) — nothing to do (use --force)"
        )
        return 0
    universe, source, unlisted = resolve_universe(args.repos, args.repos_file, args.estate_cache)
    if not universe:
        print(
            "schedule-census: no universe — pass --repos/--repos-file, refresh the estate cache (scripts/estate-repos-refresh.py), or run where gh is authenticated",
            file=sys.stderr,
        )
        return 3
    clones: dict[str, Path] = {}
    for spec in args.clone:
        name, _, path = spec.partition("=")
        if name and path:
            clones[name] = Path(path).expanduser()
    report = run_census(
        universe,
        source,
        clones=clones,
        history_cap=args.history_cap,
        budget_seconds=args.budget_seconds,
        check_registry=args.check_registry,
        self_repo=args.self_repo,
        skip_archived=args.skip_archived,
        unlisted_owners=unlisted,
    )
    d, t = report["denominators"], report["totals"]
    previous = load_receipt(args.receipt)
    previous_scanned = int(((previous or {}).get("denominators") or {}).get("scanned") or 0)
    if previous is not None and not args.replace and d["scanned"] < previous_scanned:
        sidecar = args.receipt.with_name(args.receipt.stem + ".last-attempt" + args.receipt.suffix)
        write_receipt(sidecar, report)
        print(
            f"schedule-census: this pass read {d['scanned']} repositories, the standing receipt holds {previous_scanned} — "
            f"kept {args.receipt}, wrote {sidecar} (--replace overrides)"
        )
    else:
        write_receipt(args.receipt, report)
        ledger = args.ledger if args.ledger is not None else args.receipt.with_suffix(".md")
        if str(ledger) != "-":
            ledger.parent.mkdir(parents=True, exist_ok=True)
            ledger.write_text(render_markdown(report), encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=1))
    print(
        f"schedule-census: universe {d['universe_count']} ({d['universe_source']}), scanned {d['scanned']} (partial {d['scanned_partial']}), "
        f"unreachable {d['unreachable']}, unscanned {d['unscanned_by_budget']}, skipped archived {d['skipped_archived']}, "
        f"internal errors {d['internal_errors']}, owners unlisted {d['universe_unlisted_owners']}; "
        f"Actions schedules {t['gh_workflows_with_schedule']} (active {t['gh_workflows_active']}, "
        f"auto-off {t['gh_workflows_disabled_inactivity']}, manual-off {t['gh_workflows_disabled_manually']}, "
        f"state unknown {t['gh_workflows_state_unknown']}); verdicts {t['verdicts']}"
        + (
            f"; outside specific planes {len(report['registry_gaps'])} ({sum(1 for g in report['registry_gaps'] if not g.get('owned_by'))} owned by no plane)"
            if report.get("registry_gaps") is not None
            else ""
        )
    )
    return exit_code_for(report)


if __name__ == "__main__":
    sys.exit(main())
