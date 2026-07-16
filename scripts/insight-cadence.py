#!/usr/bin/env python3
"""
Autonomous, read-only, proposal-only organ that drafts insight reports at FOUR wall-clock cadences.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib

LIMEN_ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
LOGS = LIMEN_ROOT / "logs"
TASKS = Path(os.environ.get("LIMEN_TASKS", LIMEN_ROOT / "tasks.yaml"))
STATE_PATH = LOGS / "insight-cadence-state.json"
OUT_DIR = LOGS / "insight-cadence"
DRIFT_JSON = LOGS / "insights-drift.json"

TIER_SECONDS = {"hourly": 3600, "daily": 86400, "weekly": 604800, "monthly": 2592000}


def _now():
    return datetime.now(timezone.utc)


def _iso(dt=None):
    return (dt or _now()).isoformat(timespec="seconds")


def _parse_ts(v):
    if not isinstance(v, str):
        return None
    try:
        return datetime.fromisoformat(v)
    except ValueError:
        return None


def due_tiers(state, now, force=None):
    if force:
        return [force] if force in TIER_SECONDS else []
    last = (state or {}).get("last_run", {})
    due = []
    for tier, span in TIER_SECONDS.items():
        prev = _parse_ts(last.get(tier))
        if prev is None or (now - prev).total_seconds() >= span:
            due.append(tier)
    return due


def _atomic_write(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, p)


def _load_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return default


def _gen_id(source, subject):
    h = hashlib.sha256(f"{source}:{subject}".encode()).hexdigest()[:8]
    return f"{source}-{h}"


def _refresh_lineage():
    """Regenerate logs/insights-drift.json from the /insights snapshot archive.

    This is the conduit the censor's weekly tier has been starving on: the
    machine-readable lineage of every archived /insights report (friction
    persistence, key-pattern timeline, area churn). Degrades silently when the
    insights-drift tool isn't deployed — the gatherer then reads whatever file
    already exists."""
    import shutil
    import subprocess

    tool = shutil.which("insights-drift") or str(Path.home() / ".local" / "bin" / "insights-drift")
    if not Path(tool).exists():
        return False
    try:
        r = subprocess.run(
            [tool, "--json", str(DRIFT_JSON)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _gather_insights():
    insights = []

    # 1. organ-health
    health = _load_json(LOGS / "organ-health.json", {})
    for organ, data in health.items():
        if isinstance(data, dict) and data.get("status") in ("stale", "down"):
            insights.append(
                {
                    "id": _gen_id("organ-health", organ),
                    "severity": "warning",
                    "title": f"Organ {organ} is {data.get('status')}",
                    "detail": f"Organ {organ} reported status {data.get('status')} at {data.get('timestamp')}",
                    "owner": organ,
                    "source": "organ-health.json",
                    "suggested_action": "Check organ logs and heartbeat",
                    "healable": True,
                }
            )

    # 2. censor-decisions
    try:
        if (LOGS / "censor-decisions.jsonl").exists():
            for line in (LOGS / "censor-decisions.jsonl").read_text().splitlines():
                if not line.strip():
                    continue
                d = json.loads(line)
                verdict = d.get("verdict", {})
                if verdict.get("disposition") == "propose":
                    insights.append(
                        {
                            "id": _gen_id("censor", d.get("id", "unknown")),
                            "severity": "info",
                            "title": f"Censor proposes action for {d.get('id', 'unknown')}",
                            "detail": f"Censor derived proposal from {d.get('branch', 'unknown')} branch",
                            "owner": "censor",
                            "source": "censor-decisions.jsonl",
                            "suggested_action": "Review censor decision log",
                            "healable": False,
                        }
                    )
    except (OSError, json.JSONDecodeError):
        pass

    # 3. self-improve-proposal
    sip = _load_json(LOGS / "self-improve-proposal.json", {})
    for prop in sip.get("proposals", []):
        insights.append(
            {
                "id": _gen_id("self-improve", prop.get("target", "sys")),
                "severity": "info",
                "title": prop.get("title", "Self-improve proposal"),
                "detail": prop.get("reasoning", ""),
                "owner": "self-improve",
                "source": "self-improve-proposal.json",
                "suggested_action": prop.get("action", "review"),
                "healable": False,
            }
        )

    # 4. usage
    usage = _load_json(LOGS / "usage.json", {})
    if usage.get("burn_rate", 0) > usage.get("budget", float("inf")):
        insights.append(
            {
                "id": _gen_id("usage", "budget"),
                "severity": "warning",
                "title": "High token burn rate",
                "detail": f"Burn rate {usage.get('burn_rate')} exceeds budget {usage.get('budget')}",
                "owner": "anthony",
                "source": "usage.json",
                "suggested_action": "Review agent limits",
                "healable": True,
            }
        )

    # 5. ledger
    ledger = _load_json(LOGS / "ledger.json", {})
    if "obligations" in ledger:
        for ob in ledger["obligations"]:
            if ob.get("status") == "overdue":
                insights.append(
                    {
                        "id": _gen_id("ledger", ob.get("id", "x")),
                        "severity": "warning",
                        "title": f"Overdue obligation: {ob.get('title', '')}",
                        "detail": "Obligation past deadline",
                        "owner": ob.get("owner", "anthony"),
                        "source": "ledger.json",
                        "suggested_action": "Complete obligation",
                        "healable": False,
                    }
                )

    # 6. tasks.yaml dispatch_log
    try:
        if TASKS.exists():
            content = TASKS.read_text()
            # Simple stdlib regex parser for tasks.yaml failed dispatch logs
            tasks = re.split(r"^-\s+id:\s+", content, flags=re.MULTILINE)[1:]
            for task_block in tasks:
                task_id_match = re.match(r"([^\n]+)", task_block)
                if not task_id_match:
                    continue
                task_id = task_id_match.group(1).strip()

                repo_match = re.search(r"^\s+repo:\s+([^\n]+)", task_block, re.MULTILINE)
                repo = repo_match.group(1).strip() if repo_match else None
                owner = repo if repo else "anthony"

                # Look for the dispatch_log section
                log_idx = task_block.find("dispatch_log:")
                if log_idx != -1:
                    log_block = task_block[log_idx:]
                    # Extract status lines in the log block
                    status_matches = re.findall(r"^\s+status:\s+([^\n]+)", log_block, re.MULTILINE)
                    if status_matches and status_matches[-1].strip().startswith("failed"):
                        insights.append(
                            {
                                "id": _gen_id("tasks", task_id),
                                "severity": "warning",
                                "title": f"Task failed: {task_id}",
                                "detail": f"Last log status: {status_matches[-1].strip()}",
                                "owner": owner,
                                "source": "tasks.yaml",
                                "suggested_action": "Investigate failure reason",
                                "healable": True,
                            }
                        )
    except Exception:
        pass

    # 7. insights lineage — recurring/resolved frictions across the archived
    # /insights reports (logs/insights-drift.json, refreshed each due tier).
    # Every new report is compared against every report before it; a friction
    # present in >=2 reports including the latest is a standing-correction
    # candidate for the censor's weekly cascade.
    drift = _load_json(DRIFT_JSON, {})
    for fr in (drift.get("recurring") or [])[:8]:
        label = fr.get("label", "?")
        insights.append(
            {
                "id": _gen_id("insights-lineage", label),
                "severity": "warning",
                "title": f"Recurring friction across {fr.get('reports', '?')} insights reports: {label}",
                "detail": (
                    f"First seen {fr.get('first_seen')}, still present in {fr.get('last_seen')}. "
                    f"{fr.get('latest_description', '')}"
                ),
                "owner": "censor",
                "source": "insights-drift.json",
                "suggested_action": "Promote to a standing correction (CLAUDE.md/memory) via the censor cascade",
                "healable": False,
            }
        )
    for fr in (drift.get("resolved") or [])[:4]:
        label = fr.get("label", "?")
        insights.append(
            {
                "id": _gen_id("insights-lineage-resolved", label),
                "severity": "info",
                "title": f"Friction resolved since {fr.get('last_seen')}: {label}",
                "detail": (
                    f"Present in {fr.get('reports', '?')} report(s) "
                    f"({fr.get('first_seen')} to {fr.get('last_seen')}), absent from the latest."
                ),
                "owner": "censor",
                "source": "insights-drift.json",
                "suggested_action": "None — confirm the correction that resolved it stays standing",
                "healable": True,
            }
        )

    # 8. insights suggestion coverage — every archived /insights snapshot must be
    # dispositioned in censor/insights-suggestions.jsonl (the suggestion ledger).
    # Frictions have the drift lineage above; suggestions have this ledger. A
    # snapshot missing from every `reports` list is an unaudited report and is
    # surfaced every due tier until its suggestions are dispositioned. Fails open
    # when the archive is absent (other hosts / CI).
    try:
        archive = Path(
            os.environ.get(
                "LIMEN_INSIGHTS_ARCHIVE",
                str(Path.home() / "Workspace" / "organvm" / "claude-runtime-state" / "usage-data" / "snapshots"),
            )
        ).expanduser()
        ledger_path = LIMEN_ROOT / "censor" / "insights-suggestions.jsonl"
        if archive.is_dir():
            covered = set()
            if ledger_path.exists():
                for line in ledger_path.read_text().splitlines():
                    if not line.strip():
                        continue
                    try:
                        covered.update(json.loads(line).get("reports") or [])
                    except json.JSONDecodeError:
                        continue
            for snap in sorted(p.name for p in archive.iterdir() if p.is_dir()):
                if snap not in covered:
                    insights.append(
                        {
                            "id": _gen_id("insights-suggestions", snap),
                            "severity": "warning",
                            "title": f"Insights report {snap} has no suggestion disposition",
                            "detail": (
                                f"Snapshot {snap} exists in the archive but appears in no `reports` list in "
                                "censor/insights-suggestions.jsonl — its suggestions were never dispositioned."
                            ),
                            "owner": "censor",
                            "source": "insights-suggestions.jsonl",
                            "suggested_action": "Sweep the report's suggestions and append disposition rows to the ledger",
                            "healable": False,
                        }
                    )
    except OSError:
        pass

    # ensure at least one insight for tests if none found
    if not insights:
        insights.append(
            {
                "id": _gen_id("system", "heartbeat"),
                "severity": "low",
                "title": "System nominal",
                "detail": "No actionable insights derived during this window.",
                "owner": "insight-cadence",
                "source": "internal",
                "suggested_action": "None",
                "healable": True,
            }
        )

    return insights


def _derive_frictions(insights: list[dict]) -> list[dict]:
    """Derive a structured frictions list from the gathered insights.

    A friction is any warning-or-critical insight — it represents a system
    condition worth promoting to the censor's standing-correction cascade.
    Each friction record carries ``category`` (the insight's title) and
    ``description`` (the detail field) so that the ``insights-drift`` lineage
    tool can cluster them across successive snapshots by semantic similarity.
    """
    return [
        {
            "category": ins["title"],
            "description": ins.get("detail", ""),
            "owner": ins.get("owner", ""),
            "source": ins.get("source", ""),
            "severity": ins.get("severity", "warning"),
        }
        for ins in insights
        if ins.get("severity") in ("critical", "warning")
    ]


def _generate_report(tier, start_iso, generated_iso, insights):
    report = {
        "tier": tier,
        "generated_at": generated_iso,
        "window_start": start_iso,
        "insights": insights,
        "frictions": _derive_frictions(insights),
    }
    return report


def _generate_markdown(report):
    lines = [f"# Insight Report: {report['tier']}"]
    lines.append(f"**Generated:** {report['generated_at']} | **Window Start:** {report['window_start']}")
    lines.append("")

    for ins in report["insights"]:
        lines.append(f"## {ins['title']} ({ins['severity']})")
        lines.append(f"- **Owner:** {ins['owner']}")
        lines.append(f"- **Source:** {ins['source']}")
        lines.append(f"- **Healable:** {ins['healable']}")
        lines.append(f"- **Action:** {ins['suggested_action']}")
        lines.append(f"  {ins['detail']}")
        lines.append("")

    return "\n".join(lines)


def _stamp_health() -> None:
    """Proprioception: record that the INSIGHT-CADENCE organ fired this beat"""
    try:
        LOGS.mkdir(exist_ok=True)
        (LOGS / "insight-cadence-health.json").write_text(
            json.dumps({"timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")}) + "\n"
        )
    except OSError:
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run all currently-due tiers once")
    parser.add_argument("--dry-run", action="store_true", help="Compute and print, write nothing")
    parser.add_argument("--force", help="Force a specific tier")
    args = parser.parse_args()

    state = _load_json(STATE_PATH, {})
    now = _now()

    tiers = due_tiers(state, now, args.force)

    if not tiers:
        if not args.dry_run:
            _stamp_health()
        return 0

    if not args.dry_run:
        _refresh_lineage()

    insights = _gather_insights()

    for tier in tiers:
        prev_iso = state.get("last_run", {}).get(tier)
        prev = _parse_ts(prev_iso)
        span = TIER_SECONDS[tier]

        window_start = (now - timedelta(seconds=span)) if not prev else prev

        report = _generate_report(tier, _iso(window_start), _iso(now), insights)
        md = _generate_markdown(report)

        if args.dry_run:
            print(f"--- {tier} ---")
            print(json.dumps(report, indent=2))
        else:
            ts = _iso(now).replace(":", "")
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            _atomic_write(OUT_DIR / f"{tier}-{ts}.json", json.dumps(report, indent=2))
            _atomic_write(OUT_DIR / f"{tier}-latest.md", md)

            state.setdefault("last_run", {})[tier] = _iso(now)

    if not args.dry_run:
        _atomic_write(STATE_PATH, json.dumps(state, indent=2))
        _stamp_health()

    return 0


if __name__ == "__main__":
    sys.exit(main())
