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
unreachable, unscanned, partially read or errored) earns only the shorter `--retry-hours` horizon. A pass is written
beside the standing receipt as `*.last-attempt.json` instead of over it when it is narrower than a universe census,
incomplete where the standing one is complete, or lower in complete coverage share — while that receipt is still
within its horizon; past it, the newer pass is the census. A fresh receipt (or last attempt) answers only a request
for the same scope.

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
# history channel states that count as READ: a repository with no live schedule may be concluded `none` only when
# its history was read (an API sample, even truncated or partially read, was read; an empty repository has none to
# read). A 404 on the Commits API is NOT an observation — the endpoint answers 200 [] for no commits, so a 404 means
# the repository or the token's view of it is gone
HISTORY_READ = frozenset({"git", "git:partial", "api", "api:partial", "api:truncated", "empty"})
REPO_LIST_LIMIT = 1000  # `gh repo list --limit`: a listing this long may be capped, and a capped roster is named
FINDING_VERDICTS = frozenset({"declared-never-fired", "firing-but-failing", "auto-disabled"})
HYGIENE_KINDS = frozenset({"dependabot", "renovate"})  # dependency-update schedules: hygiene, not an operator scheduler
RUN_LISTING_CAP = 2500  # the Actions run listing stops counting here; a total at the cap is a floor, not a count
HOURS_PER_DAY, DAYS_PER_WEEK, DAYS_PER_MONTH, MONTHS_PER_YEAR = 24, 7, 30.44, 12
DEFAULT_RETRY_HOURS = 24.0
MAX_INCOMPLETE_SHARE = 0.25

CHANNELS = {
    "gh-workflow": "Actions workflow files with on.schedule; state from the Actions API",
    "gh-scheduled-runs": "actions/runs?event=schedule (fired; bounded by Actions run retention)",
    "gh-workflow-history": "git history of .github/workflows (full clone) or the Commits API (capped) — workflow files only; the other carriers are read live from the tree, never historically",
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


def _says_empty_repository(payload: object) -> bool:
    """GitHub's own word for a repository with no commits: 409 "Git Repository is empty." A 5xx, a timeout or a
    connection cut is an ERROR too, and size 0 alone (computed lazily, 0 for a tiny fresh repository) proves nothing."""
    if not isinstance(payload, dict):
        return False
    return str(payload.get("status")) == "409" or "repository is empty" in str(payload.get("message", "")).lower()


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


def _estate_ttl_hours() -> float:
    """The estate cache's own TTL (LIMEN_ESTATE_CACHE_TTL_HOURS, the value estate-repos-refresh.py refreshes on)."""
    try:
        return float(os.environ.get("LIMEN_ESTATE_CACHE_TTL_HOURS", "24") or 24)
    except ValueError:
        return 24.0


def universe_from_estate_cache(
    path: Path, *, ttl_hours: float | None = None, now: datetime | None = None
) -> tuple[list[dict], str, list[str]] | None:
    """(rows, source, caveats). A cache older than the estate TTL is still a roster, but a roster that may be short
    of every repository created since: the caveat `stale-cache:<fetched_at>` rides into the receipt's unlisted list
    so such a universe is never rested on as complete (resolve_universe prefers a live listing over it)."""
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
    caveats: list[str] = []
    try:
        fetched_at = datetime.fromisoformat(str(data.get("fetched_at")))
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        ttl = ttl_hours if ttl_hours is not None else _estate_ttl_hours()
        if (now or datetime.now(timezone.utc)) - fetched_at > timedelta(hours=ttl):
            caveats.append(f"stale-cache:{fetched_at.isoformat(timespec='seconds')}")
    except (TypeError, ValueError):
        caveats.append("stale-cache:unknown-age")
    return rows, f"estate-cache:{path}", caveats


def universe_from_gh_repo_list(owners: list[str] | None = None) -> tuple[list[dict], str, list[str]] | None:
    """Host path: `gh repo list <owner>` per owner (the identity plus its orgs, unless LIMEN_OWNERS pins them).
    Returns (rows, source, unlisted owners): an owner whose listing failed is NAMED, so the universe is never
    silently smaller than the account set — a reduced denominator would read as complete coverage."""
    if not gh_available():
        return None
    unlisted: list[str] = []
    if not owners:
        st, me = gh_api("user")
        if st != OK or not isinstance(me, dict):
            return None
        owners = [str(me.get("login"))]
        st, orgs = gh_api("user/orgs?per_page=100")
        if st == OK and isinstance(orgs, list):
            owners += [str(o.get("login")) for o in orgs if isinstance(o, dict) and o.get("login")]
        else:
            unlisted.append(f"orgs-of:{owners[0]}")  # the organizations never listed: the universe is short of them
    rows: list[dict] = []
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
        if isinstance(items, list) and len(items) >= REPO_LIST_LIMIT:
            unlisted.append(f"capped:{owner}")  # the listing may be longer than its cap: named, never trusted whole
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
    """(universe rows, source, caveats). The third element names everything that makes the universe itself
    incomplete — an owner whose listing failed, a listing at its cap, the organizations never listed, a roster older
    than the estate TTL — so the receipt says so instead of resting on a short denominator. A fresh estate cache is
    preferred (no API spend); a stale one yields to a live listing and is used, caveated, only when that fails.
    Repeated names (an explicit list, a repos file) are scanned once."""
    if explicit:
        return _dedupe([{"repo": r} for r in explicit]), "explicit", []
    if repos_file is not None:
        names = [
            ln.strip()
            for ln in repos_file.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")
        ]
        return _dedupe([{"repo": r} for r in names]), f"repos-file:{repos_file}", []
    cached = universe_from_estate_cache(estate_cache)
    if cached is not None and not cached[2]:
        return _dedupe(cached[0]), cached[1], []
    found = universe_from_gh_repo_list(_owners_pin())
    if found is not None:
        return _dedupe(found[0]), found[1], found[2]
    if cached is not None:  # a stale roster beats no roster — and the receipt says it is stale
        return _dedupe(cached[0]), cached[1], cached[2]
    return [], "none", []


def _dedupe(rows: list[dict]) -> list[dict]:
    """First occurrence wins, order kept: a name listed twice (GitHub names are case-insensitive) is one repository,
    scanned and counted once."""
    seen: set[str] = set()
    out: list[dict] = []
    for r in rows:
        if str(r["repo"]).lower() in seen:
            continue
        seen.add(str(r["repo"]).lower())
        out.append(r)
    return out


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
    """(nominal fires per day, cadence label) from the cron's own fields — never the registry's routine-parity
    classes, which read `*/30 * * * *` as "daily" because no day field is restricted."""
    try:
        c = S.parse_cron(cron)
    except Exception:  # noqa: BLE001 — a cron we cannot parse is still a declaration
        return None, "unparsed"
    base = float(len(c.minutes) * len(c.hours))
    dow_share = len(c.dow) / DAYS_PER_WEEK
    dom_share = len(c.dom) / DAYS_PER_MONTH
    if c.dow_restricted and c.dom_restricted:
        day_share = min(1.0, dow_share + dom_share)  # vixie OR
    elif c.dow_restricted:
        day_share = dow_share
    elif c.dom_restricted:
        day_share = dom_share
    else:
        day_share = 1.0
    per_day = base * day_share * (len(c.months) / MONTHS_PER_YEAR)
    if c.dow_restricted and c.dow == frozenset({1, 2, 3, 4, 5}) and base == 1:
        label = "weekdays"
    elif c.dow_restricted and len(c.dow) == 1 and base == 1 and not c.dom_restricted:
        label = "weekly"
    elif c.dom_restricted and len(c.dom) == 1 and base == 1 and not c.dow_restricted:
        label = "monthly"
    elif per_day > HOURS_PER_DAY:
        label = "sub-hourly"
    elif len(c.hours) == HOURS_PER_DAY and len(c.minutes) == 1 and day_share == 1.0:
        label = "hourly"
    elif per_day > 1:
        label = "intraday"
    elif per_day == 1:
        label = "daily"
    else:
        label = "other"
    return round(per_day, 3), label


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


def parse_launchd(text: str) -> dict | None:
    """None = not a plist; {} = a plist that schedules nothing; else interval/calendar keys. A plist expat
    rejects (a `--` inside an XML comment is the common case) is read again by regex for StartInterval; one
    that also carries StartCalendarInterval stays unparseable rather than half-read."""
    try:
        data = plistlib.loads(text.encode("utf-8"))
    except Exception:  # noqa: BLE001 — not a well-formed plist
        if "<plist" not in text:
            return None
        m = _PLIST_INTERVAL_RX.search(text)
        if "StartCalendarInterval" in text:
            return None
        return {"interval_seconds": int(m.group(1)), "parse": "regex"} if m else {}
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
    if not isinstance(data, dict):
        return []
    out = _str_list(data.get("schedule"))
    rules = data.get("packageRules")
    for rule in rules if isinstance(rules, list) else []:  # a schedule may live on a package rule, not the root
        if isinstance(rule, dict) and rule.get("schedule"):
            out += [s for s in _str_list(rule.get("schedule")) if s not in out]
    return out


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
        # keyed by the workflow file (two files may share a display name); the name rides along for the ledger
        key = str(r.get("path") or r.get("name") or "?")
        row = by_workflow.setdefault(
            key,
            {
                "name": str(r.get("name") or key),
                "runs_on_page": 0,
                "last_at": None,
                "last_conclusion": None,
                "failed_on_page": 0,
            },
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
        "page_oldest_seen": runs[-1].get("created_at") if runs else None,  # the summarized page's own edge
        "page_runs": len(runs),
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
    """Full-clone history: every commit touching a workflow path, with the cron lines it added/removed. A git
    read that fails or times out is `unreadable` — an unread history is never reported as an empty one."""
    log = _git(clone, *GIT_LOG, "--format=commit %H %cI", "--name-status", "--", WORKFLOW_DIR)
    patches = _git(clone, *GIT_LOG, "--format=commit %H", "-p", *GIT_PATCH, "--", WORKFLOW_DIR)
    if log is None or patches is None:
        return {
            "source": "git",
            "status": ERROR,
            "commits_seen": 0,
            "truncated": True,
            "events": [],
            "note": "git log failed or timed out — history unread, not empty",
        }
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
    # keyed by (commit, path): a commit that moves a cron in a.yml and edits a comment in b.yml must not hand
    # b.yml a scheduling attempt it never had
    added: dict[tuple[str, str], list[str]] = {}
    removed: dict[tuple[str, str], list[str]] = {}
    cur = None
    cur_path = None
    unparsed_headers = 0
    for line in patches.splitlines():
        if line.startswith("commit "):
            cur = line.split(" ", 1)[1][:10]
            cur_path = None
            continue
        if line.startswith("diff --git "):
            cur_path = _diff_header_path(line)
            if cur_path is None:
                unparsed_headers += 1  # loud, not silent: the crons under this header go unattributed
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
    out = {"source": "git", "status": OK, "commits_seen": len(commits), "truncated": False, "events": events}
    if unparsed_headers:
        out["status"], out["truncated"] = "partial", True
        out["note"] = f"{unparsed_headers} diff header(s) unparsed: their cron changes are not attributed"
    return out


DIFF_HEADER_RX = re.compile(r'^diff --git (?:"a/.*?"|a/.*?) (?:"b/(.*)"|b/(.*))$')
# core.quotePath=false: --name-status and the diff headers print the same raw UTF-8 path, so a workflow named
# café.yml keys its cron changes by (commit, path) like any other (git would otherwise octal-escape one and not
# the other)
GIT_LOG = ("-c", "core.quotePath=false", "log", "--all", "--date-order", "--no-color")
# the -p read pins the header shape too: a host whose diff.noprefix / diff.external / color.ui would otherwise
# reshape `diff --git a/x b/x` must not silently un-attribute every cron change
GIT_PATCH = ("--src-prefix=a/", "--dst-prefix=b/", "--no-ext-diff")


def _diff_header_path(line: str) -> str | None:
    """`diff --git a/<old> b/<new>` → <new>: the path --name-status reports for a rename, and the only path for an
    add, edit or delete. A quoted path has its quotes stripped (git quotes only names with a double quote,
    backslash or control character once core.quotePath is off — practically nonexistent for a workflow)."""
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


def history_from_api(repo: str, cap: int, *, deadline: float | None = None, call=None) -> dict:
    """Commits API sample (newest + oldest, capped). `deadline` is a time.monotonic() bound: the per-commit detail
    requests stop there and the remainder is recorded as unread, so a slow history never outlives the census
    budget (the sensor's execution timeout would otherwise kill the pass before any receipt is written)."""
    call = call or gh_api  # scan_repo hands in its counting wrapper so these requests reach the rate check
    st, commits = call(f"repos/{repo}/commits?path={WORKFLOW_DIR}&per_page=100")
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
        st, detail = call(f"repos/{repo}/commits/{sha}")
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
        "failing_not_firing": [],
        "runs_unmeasured": [],
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
    elif meta.get("size") == 0 and (st == ABSENT or _says_empty_repository(tree)):
        channels["tree"] = "empty"  # no commits, no tree: GitHub answers 409 "Git Repository is empty" (or a 404)
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
    timed_active = [
        d
        for d in out["declarations"]
        if d.get("kind") == "gh-workflow" and d.get("state") == "active" and d.get("crons")
    ]
    # runs are keyed by workflow path (a fixture or an old listing may carry only the name): join on either
    firing = {d.get("path") for d in timed_active} | {d.get("name") for d in timed_active if d.get("name")}
    bad = {k for k, v in by.items() if v.get("last_conclusion") in BAD_CONCLUSIONS}
    out["failing_workflows"] = sorted(str(by[k].get("name") or k) for k in bad & firing)  # scheduled and failing
    out["failing_not_firing"] = sorted(str(by[k].get("name") or k) for k in bad - firing)  # off since: history only
    # an active schedule with no run on the summarized page, on a listing longer than that page: its latest run sits
    # on an unread page — unmeasured, never healthy and never failing
    fired_total = (
        int((out.get("fired") or {}).get("total_scheduled_runs") or 0) if isinstance(out.get("fired"), dict) else 0
    )
    page_runs = int((out.get("fired") or {}).get("page_runs") or 0) if isinstance(out.get("fired"), dict) else 0
    seen_keys = set(by) | {str(v.get("name")) for v in by.values() if v.get("name")}
    out["runs_unmeasured"] = sorted(
        str(d.get("name") or d.get("path"))
        for d in timed_active
        if fired_total > page_runs and d.get("path") not in seen_keys and d.get("name") not in seen_keys
    )
    out["actions_registered_not_in_tree"] = sorted(d["path"] for d in out["declarations"] if d.get("absent_from_tree"))

    if channels.get("tree") == "empty":
        channels["history"] = "empty"  # no commits: nothing to read, and the Commits API would answer 409 too
        out["history"] = {"source": "none", "status": OK, "commits_seen": 0, "truncated": False, "events": []}
    elif clone_is_full(clone):
        out["history"] = history_from_git(clone)  # type: ignore[arg-type]
        git_status = out["history"].get("status")
        channels["history"] = "git" + ("" if git_status == OK else f":{git_status}")
    elif over():
        channels["history"] = "skipped:budget"
    else:
        if clone is not None:
            out["notes"].append("local clone is shallow — history read through the Commits API instead")
        out["history"] = history_from_api(repo, history_cap, deadline=deadline, call=call)
        channels["history"] = (
            "api"
            + ("" if out["history"].get("status") == OK else f":{out['history'].get('status')}")
            + (":truncated" if out["history"].get("truncated") and out["history"].get("status") == OK else "")
        )

    out["partial"] = any(channels.get(name) not in {OK, "empty"} for name in ESSENTIAL_CHANNELS) or (
        channels.get("history") not in HISTORY_READ  # an unread history cannot conclude `none`
    )
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
        firing = {d.get("path") for d in active} | {d.get("name") for d in active if d.get("name")}
        live = {k: v for k, v in by.items() if k in firing}  # a retired workflow's failures are history, not this
        if live and all(v.get("last_conclusion") in BAD_CONCLUSIONS for v in live.values()):
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


def registry_covered_repos(root: Path, self_repo: str) -> set[str]:
    try:
        planes = S.load_registry(root).get("planes") or {}
    except Exception:  # noqa: BLE001 — no registry here is simply no coverage
        return set()
    covered: set[str] = set()
    for plane in planes.values():
        if not isinstance(plane, dict):
            continue
        owner_repo = (plane.get("authority") or {}).get("owner_repo")
        if owner_repo:
            covered.add(str(owner_repo))
        locator = str((plane.get("evidence") or {}).get("locator") or "")
        m = re.match(r"^([\w.-]+/[\w.-]+)[:#]", locator)
        if m:
            covered.add(m.group(1))
        if (plane.get("jobs_source") or {}).get("kind") == "workflows":
            covered.add(self_repo)
    return covered


def registry_gaps(rows: list[dict], covered: set[str]) -> list[dict]:
    """Repositories outside every plane that declare an Actions cron GitHub reports active — or whose state could
    not be read (listed under `unverified`: declared, possibly burning, not confirmed)."""
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
            gaps.append(
                {
                    "repo": row["repo"],
                    "workflows": [d["path"] for d in timed],
                    "crons": [c for d in timed for c in d["crons"]],
                    "unverified": [d["path"] for d in timed if d.get("state") != "active"],
                }
            )
    return gaps


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
            "workflows_runs_unmeasured": sum(len(r.get("runs_unmeasured") or []) for r in scanned),
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
        if x.get("crons")
        or x.get("targets")
        or x.get("interval_seconds")
        or x.get("calendar")
        or x.get("on_calendar")
        or x.get("intervals")
        or x.get("schedule")
        or x.get("routines")
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
            + (" " + ",".join(x.get("intervals") or []) if x.get("intervals") else "")
            + (
                " " + ",".join(x.get("schedule") or [])
                if isinstance(x.get("schedule"), list) and x.get("schedule")
                else ""
            )
            + (f" {x['routines']} routines" if x.get("routines") else "")
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
        if r.get("runs_unmeasured"):
            decl += f" · latest run beyond the summarized page (unmeasured): {', '.join(r['runs_unmeasured'])}"
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
        lines += ["", "## Not declared in schedules.yaml (Actions crons outside any plane)", ""]
        for g in report["registry_gaps"]:
            unverified = g.get("unverified") or []
            lines.append(
                f"- {g['repo']}: {', '.join(g['workflows'])} — {', '.join(g['crons'])}"
                + (f" (state unverified: {', '.join(unverified)})" if unverified else "")
            )
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
        lines += [
            "",
            "## Universe incomplete (an owner listing failed or was capped, or the estate roster is stale)",
            "",
        ] + [f"- {o}" for o in report["unlisted_owners"]]
    return "\n".join(lines) + "\n"


def receipt_is_complete(report: dict, *, max_incomplete_share: float = MAX_INCOMPLETE_SHARE) -> bool:
    """A receipt that read nothing, whose universe is missing an owner, or that left more than
    `max_incomplete_share` of its universe unread — unreachable, unscanned, partially read or errored — is not a
    census to rest on for a whole interval (a transient outage must earn the retry horizon, not a week)."""
    d = report.get("denominators") or {}
    try:
        scanned = int(d.get("scanned") or 0)
        universe = int(d.get("universe_count") or 0)
        unlisted = int(d.get("universe_unlisted_owners") or 0)
        unread = (
            int(d.get("unreachable") or 0)
            + int(d.get("unscanned_by_budget") or 0)
            + int(d.get("internal_errors") or 0)
            + int(d.get("scanned_partial") or 0)
        )
    except (TypeError, ValueError):
        return False
    if scanned == 0 or unlisted:
        return False
    return universe == 0 or unread / universe <= max_incomplete_share


def _generated_at(data: dict | None) -> datetime | None:
    try:
        generated = datetime.fromisoformat(str((data or {}).get("generated_at")))
    except (ValueError, TypeError):
        return None
    return generated.replace(tzinfo=timezone.utc) if generated.tzinfo is None else generated


def receipt_scope(data: dict) -> tuple[str, object]:
    """What a receipt is a census OF: an explicit repository set, a repos file, or the whole universe. A fresh
    receipt answers only a request for the same scope."""
    source = str(((data.get("denominators") or {}).get("universe_source")) or "")
    if source.startswith("explicit"):
        names = [str(r.get("repo")) for r in data.get("repos") or [] if isinstance(r, dict)]
        names += [str(x) for key in ("unscanned_by_budget", "skipped_archived") for x in data.get(key) or []]
        return "explicit", frozenset(n.lower() for n in names)  # every name the pass was asked for, scanned or not
    if source.startswith("repos-file:"):
        return "repos-file", source.removeprefix("repos-file:")
    return "universe", None


def requested_scope(explicit: list[str], repos_file: Path | None) -> tuple[str, object]:
    if explicit:
        return "explicit", frozenset(r.lower() for r in explicit)
    if repos_file is not None:
        return "repos-file", str(repos_file)
    return "universe", None


def sidecar_path(receipt: Path) -> Path:
    return receipt.with_name(receipt.stem + ".last-attempt" + receipt.suffix)


def coverage_share(report: dict) -> float:
    """Completely read repositories as a share of the universe — the measure a pass must not fall below to
    replace the standing receipt (metadata reach alone is not coverage)."""
    d = report.get("denominators") or {}
    try:
        universe = int(d.get("universe_count") or 0)
        complete = int(d.get("scanned") or 0) - int(d.get("scanned_partial") or 0)
    except (TypeError, ValueError):
        return 0.0
    return complete / universe if universe > 0 else 0.0


def keeps_standing_receipt(
    previous: dict | None,
    report: dict,
    scope: tuple[str, object],
    *,
    interval_hours: float,
    retry_hours: float = DEFAULT_RETRY_HOURS,
    now: datetime | None = None,
) -> str | None:
    """Why this pass is parked beside the standing receipt (`*.last-attempt.json`) instead of replacing it — or None
    when it replaces it. In order: a narrower pass (explicit set, repos file) never overwrites a universe receipt and
    a universe pass always displaces a narrower one; a standing receipt past its own horizon is no longer standing;
    an incomplete pass never replaces a complete receipt; and within one scope the complete coverage share
    (scanned minus partial, over the universe) must not fall."""
    if previous is None:
        return None
    prev_scope = receipt_scope(previous)
    if prev_scope != scope:
        if scope[0] == "universe":
            return None
        return f"the standing receipt is a {prev_scope[0]} census and this pass a narrower {scope[0]} one"
    moment = now or datetime.now(timezone.utc)
    generated = _generated_at(previous)
    horizon = interval_hours if receipt_is_complete(previous) else min(interval_hours, retry_hours)
    if generated is None or moment - generated >= timedelta(hours=horizon):
        return None  # past its horizon the standing receipt is history; this pass is the census now
    if receipt_is_complete(previous) and not receipt_is_complete(report):
        return "this pass is incomplete and the standing receipt (still within its horizon) is complete"
    share, previous_share = coverage_share(report), coverage_share(previous)
    if share < previous_share:
        return f"complete coverage {share:.0%} is below the standing receipt's {previous_share:.0%}"
    return None


def receipt_is_fresh(
    path: Path,
    interval_hours: float,
    now: datetime | None = None,
    *,
    retry_hours: float = DEFAULT_RETRY_HOURS,
    scope: tuple[str, object] | None = None,
    sidecar: Path | None = None,
) -> bool:
    """Younger than the interval — but an incomplete receipt only earns the shorter retry horizon, a receipt for
    another scope answers nothing, and a degraded pass parked beside the receipt (`*.last-attempt.json`) is still
    the last attempt: it earns the retry horizon too, so a shrunk universe or an outage never turns the census
    into an every-beat scan."""
    moment = now or datetime.now(timezone.utc)
    data = load_receipt(path)
    if data is not None and (scope is None or receipt_scope(data) == scope):
        generated = _generated_at(data)
        if generated is not None:
            horizon = interval_hours if receipt_is_complete(data) else min(interval_hours, retry_hours)
            if moment - generated < timedelta(hours=horizon):
                return True
    side = load_receipt(sidecar) if sidecar is not None else None
    if side is None or (scope is not None and receipt_scope(side) != scope):
        return False
    attempted = _generated_at(side)
    return attempted is not None and moment - attempted < timedelta(hours=min(interval_hours, retry_hours))


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
    self_repo: str = "4444J99/limen",
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
    gaps = registry_gaps(rows, registry_covered_repos(root, self_repo)) if check_registry else None
    return build_report(
        rows,
        universe=universe,
        universe_source=universe_source,
        unscanned=unscanned,
        gaps=gaps,
        started=started,
        skipped=skipped,
        unlisted_owners=unlisted_owners,
    )


def exit_code_for(report: dict) -> int:
    """4 internal errors (fix the engine) · 3 read nothing · 1 findings on the scanned set · 2 no findings but
    coverage incomplete (unreachable, unscanned, partial, an owner unlisted) · 0 clean and complete.

    Findings are read from the workflow-level totals as well as the repository verdicts: a verdict is one word per
    repository and `active` outranks an auto-disabled or failing schedule beside a healthy one — the totals
    do not, and the sensor's exit-1 escalation names exactly those."""
    d, t = report["denominators"], report["totals"]
    if d.get("internal_errors"):
        return 4
    if d["scanned"] == 0:
        return 3
    workflow_findings = int(t.get("gh_workflows_disabled_inactivity") or 0) + int(
        t.get("workflows_failing_last_scheduled_run") or 0
    )
    if report.get("registry_gaps") or workflow_findings or any(v in FINDING_VERDICTS for v in t["verdicts"]):
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
    ap.add_argument("--self-repo", default="4444J99/limen")
    ap.add_argument(
        "--skip-archived", action="store_true", help="skip archived repositories (their historical attempts go unread)"
    )
    ap.add_argument("--force", action="store_true", help="run even when the receipt is younger than --interval-hours")
    ap.add_argument(
        "--replace",
        action="store_true",
        help="overwrite the standing receipt even when this pass would be parked beside it (narrower scope, incomplete "
        "where it is complete, or lower complete coverage while it is within its horizon)",
    )
    ap.add_argument("--json", action="store_true", help="print the report JSON")
    args = ap.parse_args(argv)

    scope = requested_scope(args.repos, args.repos_file)
    if (
        not args.force
        and args.receipt.exists()
        and receipt_is_fresh(
            args.receipt,
            args.interval_hours,
            retry_hours=args.retry_hours,
            scope=scope,
            sidecar=sidecar_path(args.receipt),
        )
    ):
        print(
            f"schedule-census: receipt {args.receipt} (or its last attempt) is younger than its horizon "
            f"({args.interval_hours:g}h complete, {args.retry_hours:g}h incomplete or attempted) for this scope — "
            "nothing to do (use --force)"
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
    kept = (
        None
        if args.replace
        else keeps_standing_receipt(
            previous, report, scope, interval_hours=args.interval_hours, retry_hours=args.retry_hours
        )
    )
    if kept is not None:
        sidecar = sidecar_path(args.receipt)
        write_receipt(sidecar, report)
        print(f"schedule-census: {kept} — kept {args.receipt}, wrote {sidecar} (--replace overrides)")
    else:
        # the ledger first: a failure between the two writes leaves an old receipt the next pass regenerates,
        # never a fresh receipt beside a stale ledger
        ledger = args.ledger if args.ledger is not None else args.receipt.with_suffix(".md")
        if str(ledger) != "-":
            ledger.parent.mkdir(parents=True, exist_ok=True)
            ledger.write_text(render_markdown(report), encoding="utf-8")
        write_receipt(args.receipt, report)
    if args.json:
        print(json.dumps(report, indent=1))
    print(
        f"schedule-census: universe {d['universe_count']} ({d['universe_source']}), scanned {d['scanned']} (partial {d['scanned_partial']}), "
        f"unreachable {d['unreachable']}, unscanned {d['unscanned_by_budget']}, skipped archived {d['skipped_archived']}, "
        f"internal errors {d['internal_errors']}, owners unlisted {d['universe_unlisted_owners']}; "
        f"Actions schedules {t['gh_workflows_with_schedule']} (active {t['gh_workflows_active']}, "
        f"auto-off {t['gh_workflows_disabled_inactivity']}, manual-off {t['gh_workflows_disabled_manually']}, "
        f"state unknown {t['gh_workflows_state_unknown']}); verdicts {t['verdicts']}"
        + (f"; registry gaps {len(report['registry_gaps'])}" if report.get("registry_gaps") is not None else "")
    )
    return exit_code_for(report)


if __name__ == "__main__":
    sys.exit(main())
