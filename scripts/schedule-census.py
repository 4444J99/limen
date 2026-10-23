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
interval (`--interval-hours`, default 168) so a metabolize-pass caller stays cheap between censuses.
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
    core = (payload or {}).get("resources", {}).get("core") if st == OK and isinstance(payload, dict) else None
    if not isinstance(core, dict):
        return None
    try:
        return int(core.get("remaining")), int(core.get("reset"))
    except (TypeError, ValueError):
        return None


def rate_guard(*, floor: int = 60, deadline: float | None = None, sleep=time.sleep, now=time.time) -> str:
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


def universe_from_gh_repo_list(owners: list[str] | None = None) -> tuple[list[dict], str] | None:
    """Host path: `gh repo list <owner>` per owner (the identity plus its orgs, unless LIMEN_OWNERS pins them)."""
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
            items = json.loads(run.stdout) if run.returncode == 0 and run.stdout.strip() else []
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            items = []
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
    return (sorted(rows, key=lambda r: r["repo"]), f"gh-repo-list:{','.join(owners)}") if rows else None


def resolve_universe(explicit: list[str], repos_file: Path | None, estate_cache: Path) -> tuple[list[dict], str]:
    if explicit:
        return [{"repo": r} for r in explicit], "explicit"
    if repos_file is not None:
        names = [
            ln.strip()
            for ln in repos_file.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")
        ]
        return [{"repo": r} for r in names], f"repos-file:{repos_file}"
    found = universe_from_estate_cache(estate_cache) or universe_from_gh_repo_list(_owners_pin())
    if found is None:
        return [], "none"
    return found


def _owners_pin() -> list[str] | None:
    raw = (os.environ.get("LIMEN_OWNERS") or "").strip()
    return [o.strip() for o in raw.split(",") if o.strip()] or None


# ── carrier parsers: text -> declaration dict (or None when the carrier declares no schedule) ─


def _on_block(data: object) -> dict | None:
    if not isinstance(data, dict):
        return None
    on = data.get("on")
    if on is None:
        on = data.get(True)  # PyYAML reads a bare `on:` key as boolean True
    return on if isinstance(on, dict) else None


def _cron_cadence(cron: str) -> str:
    try:
        return S.cadence_class(S.parse_cron(cron))
    except Exception:  # noqa: BLE001 — a cron we cannot parse is still a declaration
        return "unparsed"


def parse_workflow(text: str) -> list[str]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return [m.group(1).strip() for m in map(CRON_LINE_RX.match, text.splitlines()) if m]
    on = _on_block(data)
    sched = on.get("schedule") if on else None
    crons: list[str] = []
    for entry in sched or []:
        if isinstance(entry, dict) and entry.get("cron"):
            crons.append(str(entry["cron"]).strip())
    return crons


_JSON_COMMENT_RX = re.compile(r'("(?:\\.|[^"\\])*")|/\*.*?\*/|//[^\n]*', re.S)


def _strip_json_comments(text: str) -> str:
    """Drop // and /* */ comments outside string literals (jsonc), leaving strings such as URLs intact."""
    return _JSON_COMMENT_RX.sub(lambda m: m.group(1) or "", text)


def parse_wrangler(path: str, text: str) -> list[str]:
    if path.endswith(".toml"):
        if tomllib is None:
            return []
        try:
            data = tomllib.loads(text)
        except (tomllib.TOMLDecodeError, ValueError):
            return []
    else:
        stripped = _strip_json_comments(text)
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            return []
    crons = ((data.get("triggers") or {}).get("crons") if isinstance(data, dict) else None) or []
    return [str(c) for c in crons]


def parse_vercel(text: str) -> list[dict]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    return [c for c in (data.get("crons") or []) if isinstance(c, dict)] if isinstance(data, dict) else []


def parse_launchd(text: str) -> dict | None:
    try:
        data = plistlib.loads(text.encode("utf-8"))
    except Exception:  # noqa: BLE001 — not a launchd plist
        return None
    out: dict = {}
    if isinstance(data.get("StartInterval"), int):
        out["interval_seconds"] = data["StartInterval"]
    cal = data.get("StartCalendarInterval")
    if isinstance(cal, dict):
        cal = [cal]
    if isinstance(cal, list):
        out["calendar"] = [{k: v for k, v in c.items()} for c in cal if isinstance(c, dict)]
    if data.get("RunAtLoad") and not out:
        return None
    return out or None


def parse_crontab(text: str) -> list[str]:
    return [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#") and CRONTAB_RX.match(ln)
    ]


def parse_timer(text: str) -> list[str]:
    return [ln.split("=", 1)[1].strip() for ln in text.splitlines() if ln.strip().startswith("OnCalendar=")]


def parse_dependabot(text: str) -> list[str]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return []
    out = []
    for upd in (data.get("updates") or []) if isinstance(data, dict) else []:
        sched = upd.get("schedule") if isinstance(upd, dict) else None
        if isinstance(sched, dict) and sched.get("interval"):
            out.append(
                str(sched["interval"])
                + (f" {sched['day']}" if sched.get("day") else "")
                + (f" {sched['time']}" if sched.get("time") else "")
            )
    return out


def parse_renovate(text: str) -> list[str]:
    try:
        data = json.loads(_strip_json_comments(text))
    except json.JSONDecodeError:
        return []
    sched = data.get("schedule") if isinstance(data, dict) else None
    return [str(s) for s in sched] if isinstance(sched, list) else ([str(sched)] if sched else [])


def parse_cloud_routines(text: str) -> int:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return 0
    rows = data.get("routines") if isinstance(data, dict) else data
    if isinstance(rows, dict):
        rows = list(rows.values())
    return sum(
        1 for r in (rows or []) if isinstance(r, dict) and (r.get("cron") or r.get("cadence") or r.get("schedule"))
    )


def parse_manifest(text: str) -> list[dict]:
    return [
        {"name": m.group("name"), "cron": m.group("cron"), "max_per_day": int(m.group("cap"))}
        for m in S._MANIFEST_TARGET_RX.finditer(text)
    ]


def declaration_for(kind: str, path: str, text: str) -> dict | None:
    base = {"kind": kind, "path": path}
    if kind == "gh-workflow":
        crons = parse_workflow(text)
        return {**base, "crons": crons, "cadence": [_cron_cadence(c) for c in crons]} if crons else None
    if kind == "wrangler":
        crons = parse_wrangler(path, text)
        return {**base, "crons": crons, "cadence": [_cron_cadence(c) for c in crons]} if crons else None
    if kind == "cloudflare-manifest":
        targets = parse_manifest(text)
        return {**base, "targets": targets} if targets else None
    if kind == "vercel":
        crons = parse_vercel(text)
        return (
            {**base, "crons": [str(c.get("schedule")) for c in crons], "paths": [str(c.get("path")) for c in crons]}
            if crons
            else None
        )
    if kind == "launchd":
        parsed = parse_launchd(text)
        return {**base, **parsed} if parsed else None
    if kind == "crontab":
        lines = parse_crontab(text)
        return {**base, "crons": lines} if lines else None
    if kind == "systemd-timer":
        cal = parse_timer(text)
        return {**base, "on_calendar": cal} if cal else None
    if kind == "dependabot":
        intervals = parse_dependabot(text)
        return {**base, "intervals": intervals} if intervals else None
    if kind == "renovate":
        sched = parse_renovate(text)
        return {**base, "schedule": sched} if sched else None
    if kind == "cloud-routines":
        n = parse_cloud_routines(text)
        return {**base, "routines": n} if n else None
    return None


# ── fired: scheduled runs ───────────────────────────────────────────────────────────────────


def summarize_scheduled_runs(page1: dict | None, oldest_page: dict | None = None) -> dict:
    runs = (page1 or {}).get("workflow_runs") or []
    total = int((page1 or {}).get("total_count") or 0)
    by_workflow: dict[str, dict] = {}
    for r in runs:
        if not isinstance(r, dict):
            continue
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
    newest = runs[0].get("created_at") if runs and isinstance(runs[0], dict) else None
    old_runs = (oldest_page or {}).get("workflow_runs") or []
    oldest = (
        old_runs[-1].get("created_at")
        if old_runs and isinstance(old_runs[-1], dict)
        else (runs[-1].get("created_at") if runs else None)
    )
    return {
        "total_scheduled_runs": total,
        "newest": newest,
        "oldest_seen": oldest,
        "by_workflow": by_workflow,
        "retention_note": "GitHub keeps Actions run records for the repository's retention window (90 days by default); older attempts are visible only in git history",
    }


# ── attempt discourse: issues and PRs that talk about scheduling ────────────────────────────


def read_attempts(repo: str, call, pages: int = ATTEMPT_PAGES) -> dict:
    """Issues and PRs (the /issues listing carries both) whose title or labels match ATTEMPT_RX. These are
    speech acts — a plan, a proposal, a PR — not evidence anything ran; the receipt keeps them apart."""
    items: list[dict] = []
    seen = 0
    truncated = False
    for page in range(1, pages + 1):
        st, rows = call(f"repos/{repo}/issues?state=all&per_page=100&page={page}&sort=created&direction=desc")
        if st != OK or not isinstance(rows, list):
            return {"readable": False, "items": items, "seen": seen, "truncated": True, "note": f"issues listing {st}"}
        seen += len(rows)
        for it in rows:
            if not isinstance(it, dict):
                continue
            title = str(it.get("title") or "")
            labels = [str(lab.get("name") or "") for lab in it.get("labels") or [] if isinstance(lab, dict)]
            if not (ATTEMPT_RX.search(title) or any(ATTEMPT_RX.search(lab) for lab in labels)):
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
    return {"readable": True, "items": items, "seen": seen, "truncated": truncated}


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
    added: dict[str, list[str]] = {}
    removed: dict[str, list[str]] = {}
    cur = None
    for line in patches.splitlines():
        if line.startswith("commit "):
            cur = line.split(" ", 1)[1][:10]
            continue
        if cur is None or len(line) < 2 or line.startswith(("+++", "---")):
            continue
        m = CRON_LINE_RX.match(line[1:])
        if m and line[0] == "+":
            added.setdefault(cur, []).append(m.group(1).strip())
        elif m and line[0] == "-":
            removed.setdefault(cur, []).append(m.group(1).strip())
    for ev in events:
        ev["crons_added"] = added.get(ev["sha"], [])
        ev["crons_removed"] = removed.get(ev["sha"], [])
    commits = {e["sha"] for e in events}
    return {"source": "git", "commits_seen": len(commits), "truncated": False, "events": events}


def history_from_api(repo: str, cap: int) -> dict:
    st, commits = gh_api(f"repos/{repo}/commits?path={WORKFLOW_DIR}&per_page=100")
    if st != OK or not isinstance(commits, list):
        return {"source": "api", "commits_seen": 0, "truncated": True, "events": [], "note": f"commit listing {st}"}
    shas = [c.get("sha") for c in commits if isinstance(c, dict) and c.get("sha")]
    sample = shas if len(shas) <= cap else shas[: cap - cap // 2] + shas[-(cap // 2) :]
    events: list[dict] = []
    for sha in sample:
        st, detail = gh_api(f"repos/{repo}/commits/{sha}")
        if st != OK or not isinstance(detail, dict):
            continue
        at = ((detail.get("commit") or {}).get("committer") or {}).get("date")
        for f in detail.get("files") or []:
            if not isinstance(f, dict) or not str(f.get("filename", "")).startswith(WORKFLOW_DIR + "/"):
                continue
            patch = str(f.get("patch") or "")
            added = [
                m.group(1).strip()
                for m in (CRON_LINE_RX.match(ln[1:]) for ln in patch.splitlines() if ln.startswith("+"))
                if m
            ]
            removed = [
                m.group(1).strip()
                for m in (CRON_LINE_RX.match(ln[1:]) for ln in patch.splitlines() if ln.startswith("-"))
                if m
            ]
            events.append(
                {
                    "at": at,
                    "sha": sha[:10],
                    "path": f["filename"],
                    "change": str(f.get("status")),
                    "crons_added": added,
                    "crons_removed": removed,
                }
            )
    truncated = len(shas) > cap or len(commits) >= 100
    return {
        "source": "api",
        "commits_seen": len(shas),
        "truncated": truncated,
        "events": events,
        "sampled": len(sample),
    }


# ── per-repo scan ───────────────────────────────────────────────────────────────────────────


def scan_repo(repo: str, *, clone: Path | None = None, history_cap: int = 30) -> dict:
    out: dict = {
        "repo": repo,
        "reach": OK,
        "declarations": [],
        "fired": None,
        "history": None,
        "notes": [],
        "api_calls": 0,
        "failing_workflows": [],
        "actions_registered_not_in_tree": [],
    }

    def call(path: str) -> tuple[str, object | None]:
        out["api_calls"] += 1
        return gh_api(path)

    st, meta = call(f"repos/{repo}")
    if st != OK or not isinstance(meta, dict):
        out["reach"] = st if st != OK else ERROR
        out["notes"].append(f"repository metadata {st}")
        out["verdict"] = "unreachable"
        return out
    out["private"] = bool(meta.get("private"))
    out["archived"] = bool(meta.get("archived"))
    out["default_branch"] = str(meta.get("default_branch") or "main")
    out["pushed_at"] = meta.get("pushed_at")
    branch = out["default_branch"]

    st, tree = call(f"repos/{repo}/git/trees/{branch}?recursive=1")
    paths: list[str] = []
    if st == OK and isinstance(tree, dict):
        paths = [str(e.get("path")) for e in tree.get("tree") or [] if isinstance(e, dict) and e.get("type") == "blob"]
        if tree.get("truncated"):
            out["notes"].append("tree listing truncated by GitHub — carriers beyond the limit were not seen")
    else:
        out["notes"].append(f"tree listing {st}")
    carriers = [(kind, p) for p in paths for kind, rx in CARRIER_RX.items() if rx.search(p)]

    st, wf = call(f"repos/{repo}/actions/workflows?per_page=100")
    states: dict[str, dict] = {}
    if st == OK and isinstance(wf, dict):
        for w in wf.get("workflows") or []:
            if isinstance(w, dict) and w.get("path"):
                states[str(w["path"])] = {"state": str(w.get("state")), "name": str(w.get("name")), "id": w.get("id")}
    else:
        out["notes"].append(f"actions workflows listing {st} (workflow states unknown)")

    seen_workflow_paths: set[str] = set()
    for kind, path in carriers:
        st, c = call(f"repos/{repo}/contents/{path}?ref={branch}")
        text = _decode_contents(c) if st == OK else None
        if text is None:
            out["notes"].append(f"{path}: contents {st}")
            continue
        decl = declaration_for(kind, path, text)
        if kind == "gh-workflow":
            seen_workflow_paths.add(path)
            state = states.get(path, {}).get("state", "unknown")
            if decl is None and not state.startswith("disabled"):
                continue
            decl = {
                **(decl or {"kind": kind, "path": path, "crons": [], "cadence": []}),
                "state": state,
                "name": states.get(path, {}).get("name"),
            }
        if decl:
            out["declarations"].append(decl)
    for path, s in states.items():  # registered with Actions but gone from the default branch tree
        if path not in seen_workflow_paths and path.startswith(WORKFLOW_DIR):
            out["declarations"].append(
                {
                    "kind": "gh-workflow",
                    "path": path,
                    "crons": [],
                    "cadence": [],
                    "state": s["state"],
                    "name": s["name"],
                    "note": "registered with Actions but absent from the default branch",
                }
            )

    st, page1 = call(f"repos/{repo}/actions/runs?event=schedule&per_page=100")
    if st == OK and isinstance(page1, dict):
        total = int(page1.get("total_count") or 0)
        oldest_page = None
        if total > 100:
            last = (total + 99) // 100
            st2, oldest_page = call(f"repos/{repo}/actions/runs?event=schedule&per_page=100&page={last}")
            if st2 != OK:
                oldest_page = None
        out["fired"] = summarize_scheduled_runs(page1, oldest_page if isinstance(oldest_page, dict) else None)
    else:
        out["notes"].append(f"scheduled runs listing {st}")

    out["attempts"] = read_attempts(repo, call)
    by = (out.get("fired") or {}).get("by_workflow") or {}
    out["failing_workflows"] = sorted(n for n, v in by.items() if v.get("last_conclusion") in BAD_CONCLUSIONS)
    out["actions_registered_not_in_tree"] = sorted(d["path"] for d in out["declarations"] if d.get("note"))
    if clone_is_full(clone):
        out["history"] = history_from_git(clone)  # type: ignore[arg-type]
    else:
        if clone is not None:
            out["notes"].append("local clone is shallow — history read through the Commits API instead")
        out["history"] = history_from_api(repo, history_cap)
    out["verdict"] = verdict_for_repo(out)
    return out


def verdict_for_repo(row: dict) -> str:
    """One word per repo, from evidence only. unreachable ≠ none."""
    if row.get("reach") != OK:
        return "unreachable"
    gh = [d for d in row["declarations"] if d["kind"] == "gh-workflow"]
    others = [d for d in row["declarations"] if d["kind"] != "gh-workflow"]
    active = [d for d in gh if d.get("state") == "active" and d.get("crons")]
    fired = row.get("fired") or {}
    if any(d.get("state") == "disabled_manually" for d in gh) and not active:
        return "manually-disabled"
    if any(d.get("state") == "disabled_inactivity" for d in gh) and not active:
        return "auto-disabled"
    if active:
        if fired.get("total_scheduled_runs", 0) == 0:
            return "declared-never-fired"
        by = fired.get("by_workflow") or {}
        if by and all(v.get("last_conclusion") in BAD_CONCLUSIONS for v in by.values()):
            return "firing-but-failing"
        return "active"
    hist = row.get("history") or {}
    if any(e.get("change") == "removed" for e in hist.get("events") or []):
        return "abandoned-in-history"
    if others:
        return "declared-outside-actions"
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
    gaps = []
    for row in rows:
        if row.get("reach") != OK or row["repo"] in covered:
            continue
        active = [
            d
            for d in row["declarations"]
            if d["kind"] == "gh-workflow" and d.get("state") == "active" and d.get("crons")
        ]
        if active:
            gaps.append(
                {
                    "repo": row["repo"],
                    "workflows": [d["path"] for d in active],
                    "crons": [c for d in active for c in d["crons"]],
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
) -> dict:
    scanned = [r for r in rows if r.get("reach") == OK]
    unreachable = [r["repo"] for r in rows if r.get("reach") != OK]
    verdicts: dict[str, int] = {}
    for r in rows:
        verdicts[r.get("verdict", "?")] = verdicts.get(r.get("verdict", "?"), 0) + 1
    gh_decl = [d for r in scanned for d in r["declarations"] if d["kind"] == "gh-workflow"]
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "elapsed_seconds": round(time.monotonic() - started, 1),
        "denominators": {
            "universe_source": universe_source,
            "universe_count": len(universe),
            "scanned": len(scanned),
            "unreachable": len(unreachable),
            "unscanned_by_budget": len(unscanned),
            "note": "conclusions below are about the scanned set only; unreachable and unscanned repositories (time budget or API quota) are listed, never counted as unscheduled",
        },
        "channels_read": CHANNELS,
        "channels_not_read": NOT_READ,
        "totals": {
            "repos_with_any_declaration": sum(1 for r in scanned if r["declarations"]),
            "gh_workflows_with_schedule": sum(1 for d in gh_decl if d.get("crons")),
            "gh_workflows_active": sum(1 for d in gh_decl if d.get("state") == "active" and d.get("crons")),
            "gh_workflows_disabled_inactivity": sum(
                1 for d in gh_decl if d.get("crons") and d.get("state") == "disabled_inactivity"
            ),
            "gh_workflows_disabled_manually": sum(
                1 for d in gh_decl if d.get("crons") and d.get("state") == "disabled_manually"
            ),
            "workflows_disabled_any_trigger": sum(1 for d in gh_decl if str(d.get("state", "")).startswith("disabled")),
            "workflows_failing_last_scheduled_run": sum(len(r.get("failing_workflows") or []) for r in scanned),
            "actions_registered_not_in_tree": sum(len(r.get("actions_registered_not_in_tree") or []) for r in scanned),
            "attempt_discourse_items": sum(len((r.get("attempts") or {}).get("items") or []) for r in scanned),
            "repos_with_attempt_discourse": sum(1 for r in scanned if (r.get("attempts") or {}).get("items")),
            "scheduled_runs_in_retention": sum(
                int((r.get("fired") or {}).get("total_scheduled_runs") or 0) for r in scanned
            ),
            "verdicts": verdicts,
        },
        "registry_gaps": gaps,
        "unreachable": unreachable,
        "unscanned_by_budget": unscanned,
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


def render_markdown(report: dict) -> str:
    d = report["denominators"]
    t = report["totals"]
    lines = [
        "# Schedule census",
        "",
        f"Generated {report['generated_at']} · universe {d['universe_count']} ({d['universe_source']}) · scanned {d['scanned']} · unreachable {d['unreachable']} · unscanned by budget {d['unscanned_by_budget']}",
        "",
        f"Channels read: {', '.join(report['channels_read'])}. Not read here: {', '.join(report['channels_not_read'])}.",
        "",
        f"Declared Actions schedules {t['gh_workflows_with_schedule']} (active {t['gh_workflows_active']}, auto-disabled {t['gh_workflows_disabled_inactivity']}, manually disabled {t['gh_workflows_disabled_manually']}); scheduled runs in retention {t['scheduled_runs_in_retention']}.",
        "",
        "| repo | verdict | declarations | fired (retention) | history | issues/PRs about scheduling |",
        "|---|---|---|---|---|---|",
    ]
    for r in report["repos"]:
        decls = r.get("declarations") or []
        timed = [
            x
            for x in decls
            if x.get("crons")
            or x.get("targets")
            or x.get("interval_seconds")
            or x.get("calendar")
            or x.get("on_calendar")
        ]
        rest = [x for x in decls if x not in timed]
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
        lines.append(f"| {r['repo']} | {r.get('verdict', '?')} | {decl} | {fired_s} | {hist_s} | {att_s} |")
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
        lines += ["", "## Not declared in schedules.yaml (active Actions schedules outside any plane)", ""]
        lines += [
            f"- {g['repo']}: {', '.join(g['workflows'])} — {', '.join(g['crons'])}" for g in report["registry_gaps"]
        ]
    if report.get("unreachable"):
        lines += ["", "## Unreachable from this runner (not scanned, not concluded)", ""] + [
            f"- {u}" for u in report["unreachable"]
        ]
    if report.get("unscanned_by_budget"):
        lines += ["", "## Left unscanned by the time budget", ""] + [f"- {u}" for u in report["unscanned_by_budget"]]
    return "\n".join(lines) + "\n"


def receipt_is_fresh(path: Path, interval_hours: float, now: datetime | None = None) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        generated = datetime.fromisoformat(str(data.get("generated_at")))
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return False
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=timezone.utc)
    return (now or datetime.now(timezone.utc)) - generated < timedelta(hours=interval_hours)


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
    rate_check_every: int = 10,
) -> dict:
    started = time.monotonic()
    deadline = time.time() + budget_seconds
    rows: list[dict] = []
    unscanned: list[str] = []
    exhausted = False
    for index, entry in enumerate(universe):
        repo = entry["repo"]
        if skip_archived and entry.get("archived"):
            continue
        if exhausted or time.monotonic() - started > budget_seconds:
            unscanned.append(repo)
            continue
        if index % rate_check_every == 0 and rate_guard(deadline=deadline) == "exhausted":
            exhausted = True
            unscanned.append(repo)
            continue
        rows.append(scan_repo(repo, clone=(clones or {}).get(repo), history_cap=history_cap))
    gaps = registry_gaps(rows, registry_covered_repos(root, self_repo)) if check_registry else None
    return build_report(
        rows, universe=universe, universe_source=universe_source, unscanned=unscanned, gaps=gaps, started=started
    )


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
        "--budget-seconds", type=float, default=float(os.environ.get("LIMEN_SCHEDULE_CENSUS_BUDGET_SECONDS") or 1500)
    )
    ap.add_argument("--history-cap", type=int, default=int(os.environ.get("LIMEN_SCHEDULE_CENSUS_HISTORY_CAP") or 30))
    ap.add_argument(
        "--check-registry", action="store_true", help="list active Actions schedules outside every schedules.yaml plane"
    )
    ap.add_argument("--self-repo", default="4444J99/limen")
    ap.add_argument("--skip-archived", action="store_true")
    ap.add_argument("--force", action="store_true", help="run even when the receipt is younger than --interval-hours")
    ap.add_argument("--json", action="store_true", help="print the report JSON")
    args = ap.parse_args(argv)

    if not args.force and args.receipt.exists() and receipt_is_fresh(args.receipt, args.interval_hours):
        print(
            f"schedule-census: receipt {args.receipt} is younger than {args.interval_hours:g}h — nothing to do (use --force)"
        )
        return 0
    universe, source = resolve_universe(args.repos, args.repos_file, args.estate_cache)
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
    )
    write_receipt(args.receipt, report)
    ledger = args.ledger if args.ledger is not None else args.receipt.with_suffix(".md")
    if str(ledger) != "-":
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(render_markdown(report), encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=1))
    d, t = report["denominators"], report["totals"]
    print(
        f"schedule-census: universe {d['universe_count']} ({d['universe_source']}), scanned {d['scanned']}, unreachable {d['unreachable']}, "
        f"unscanned {d['unscanned_by_budget']}; Actions schedules {t['gh_workflows_with_schedule']} (active {t['gh_workflows_active']}, "
        f"auto-off {t['gh_workflows_disabled_inactivity']}, manual-off {t['gh_workflows_disabled_manually']}); verdicts {t['verdicts']}"
        + (f"; registry gaps {len(report['registry_gaps'])}" if report.get("registry_gaps") is not None else "")
    )
    if d["scanned"] == 0 and (d["unreachable"] or d["unscanned_by_budget"]):
        return 3
    findings = (report.get("registry_gaps") or []) or any(
        v in {"declared-never-fired", "firing-but-failing", "auto-disabled"} for v in t["verdicts"]
    )
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
