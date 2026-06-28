#!/usr/bin/env python3
"""Review whether a long Limen work session created durable value.

The report is intentionally metadata-only. It reads Git commit metadata, public
prompt-batch receipts, and the ignored prompt-batch queue index; it never opens
raw prompt/session source files.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
BATCH_RESOLUTION_RECEIPTS = ROOT / "docs" / "prompt-batch-resolution-receipts.json"
BATCH_REVIEW_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-batch-review-ledger.json"
DOC_PATH = ROOT / "docs" / "session-value-review.md"
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "session-value-review.json"

RECORDED_STATUSES = {"owner-recorded", "non-source-recorded", "superseded-recorded"}
FOLLOWUP_ROOT_STATUSES = {
    "remote_pr_preserved",
    "remote_branch_preserved",
    "remote_branch_preserved_no_pr",
    "closed_pr_live_branch_preserved",
    "closed_pr_recorded_with_branch",
}


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_timestamp(value: str) -> dt.datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def relpath(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except (OSError, ValueError):
        return str(path)


def run_git(args: list[str]) -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True)


def commit_kind(subject: str) -> str:
    lowered = subject.lower()
    if "prompt" in lowered and re.search(r"\blimen: (record|resolve|add|route|packetize)", lowered):
        return "prompt_corpus"
    if "task board" in lowered or "task states" in lowered or "stale task" in lowered or "jules" in lowered:
        return "task_board"
    if lowered.startswith(("ci:", "chore:", "docs:", "fix:", "feat:")):
        return "direct_engineering"
    if lowered.startswith("capture:"):
        return "capture"
    return "other"


def commit_numstat(sha: str) -> dict[str, Any]:
    output = run_git(["show", "--no-renames", "--numstat", "--format=", sha])
    files = 0
    insertions = 0
    deletions = 0
    paths: list[str] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, removed, path = parts
        files += 1
        if added.isdigit():
            insertions += int(added)
        if removed.isdigit():
            deletions += int(removed)
        paths.append(path)
    return {
        "files": files,
        "insertions": insertions,
        "deletions": deletions,
        "paths": sorted(paths),
    }


def git_commits(since: dt.datetime, until: dt.datetime) -> list[dict[str, Any]]:
    output = run_git(
        [
            "log",
            f"--since={since.isoformat()}",
            f"--until={until.isoformat()}",
            "--pretty=format:%H%x1f%aI%x1f%s%x1e",
        ]
    )
    commits: list[dict[str, Any]] = []
    for row in output.strip("\x1e\n").split("\x1e"):
        if not row.strip():
            continue
        parts = row.strip().split("\x1f")
        if len(parts) != 3:
            continue
        sha, authored_at, subject = parts
        stats = commit_numstat(sha)
        commits.append(
            {
                "sha": sha,
                "short_sha": sha[:7],
                "authored_at": parse_timestamp(authored_at).isoformat(timespec="seconds"),
                "subject": subject,
                "kind": commit_kind(subject),
                **stats,
            }
        )
    commits.sort(key=lambda item: item["authored_at"])
    return commits


def receipt_timestamp(receipt: dict[str, Any]) -> dt.datetime | None:
    generated_at = receipt.get("generated_at")
    if not isinstance(generated_at, str) or not generated_at.strip():
        return None
    try:
        return parse_timestamp(generated_at)
    except ValueError:
        return None


def batch_receipts(since: dt.datetime, until: dt.datetime) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for receipt in load_json(BATCH_RESOLUTION_RECEIPTS).get("receipts") or []:
        if not isinstance(receipt, dict):
            continue
        stamp = receipt_timestamp(receipt)
        if stamp is None or stamp < since or stamp > until:
            continue
        roots = [root for root in receipt.get("roots") or [] if isinstance(root, dict)]
        root_statuses = Counter(str(root.get("status") or "unknown") for root in roots)
        repos = sorted({str(root.get("repo")) for root in roots if root.get("repo")})
        receipts.append(
            {
                "batch": receipt.get("batch"),
                "generated_at": stamp.isoformat(timespec="seconds"),
                "status": receipt.get("status"),
                "band": receipt.get("band"),
                "lane": receipt.get("lane"),
                "session_count": int(receipt.get("session_count") or 0),
                "prompt_events": int(receipt.get("prompt_events") or 0),
                "unique_prompt_hashes": int(receipt.get("unique_prompt_hashes") or 0),
                "root_count": len(roots),
                "root_statuses": dict(root_statuses.most_common()),
                "repo_count": len(repos),
                "followup_roots": sum(root_statuses.get(status, 0) for status in FOLLOWUP_ROOT_STATUSES),
                "merged_roots": int(root_statuses.get("remote_pr_merged", 0)),
                "owner_absent_roots": int(root_statuses.get("owner_repo_routed_absent_branch", 0)),
                "sensitive_roots": sum(
                    count for status, count in root_statuses.items() if "sensitive" in status
                ),
            }
        )
    receipts.sort(key=lambda item: item["generated_at"])
    return receipts


def current_queue() -> dict[str, Any]:
    index = load_json(BATCH_REVIEW_INDEX)
    coverage = index.get("coverage") if isinstance(index.get("coverage"), dict) else {}
    counts = index.get("counts") if isinstance(index.get("counts"), dict) else {}
    queue = []
    for item in index.get("review_queue") or []:
        if not isinstance(item, dict):
            continue
        queue.append(
            {
                "id": item.get("id"),
                "status": item.get("status"),
                "band": item.get("band"),
                "lane": item.get("lane"),
                "session_count": int(item.get("session_count") or 0),
                "prompt_events": int(item.get("prompt_events") or 0),
                "unique_prompt_hashes": int(item.get("unique_prompt_hashes") or 0),
            }
        )
    return {"coverage": coverage, "counts": counts, "next": queue[:5]}


def sum_field(items: list[dict[str, Any]], field: str) -> int:
    return sum(int(item.get(field) or 0) for item in items)


def build_findings(
    commits: list[dict[str, Any]],
    receipts: list[dict[str, Any]],
    queue: dict[str, Any],
    hours: float,
) -> dict[str, Any]:
    commit_kinds = Counter(str(commit["kind"]) for commit in commits)
    lane_counts = Counter(str(receipt.get("lane") or "unknown") for receipt in receipts)
    root_statuses: Counter[str] = Counter()
    for receipt in receipts:
        root_statuses.update(receipt.get("root_statuses") or {})

    batch_count = len(receipts)
    prompt_events = sum_field(receipts, "prompt_events")
    sessions = sum_field(receipts, "session_count")
    merged = int(root_statuses.get("remote_pr_merged", 0))
    followups = sum_field(receipts, "followup_roots")
    absent = int(root_statuses.get("owner_repo_routed_absent_branch", 0))
    recorded_batches = int((queue.get("coverage") or {}).get("recorded_batches") or 0)
    open_batches = int((queue.get("coverage") or {}).get("open_review_batches") or 0)

    value_points: list[str] = []
    critique_points: list[str] = []
    controls: list[str] = []

    if batch_count:
        value_points.append(
            f"Resolved {batch_count} prompt-corpus batches covering {sessions} sessions and {prompt_events} prompt events into durable metadata receipts."
        )
    if merged:
        value_points.append(f"Linked {merged} roots to already-merged PR evidence instead of leaving them as ambiguous session residue.")
    if recorded_batches:
        value_points.append(
            f"Left the current redacted queue measurable: {recorded_batches} recorded batches and {open_batches} open review batches."
        )
    if commits:
        value_points.append(
            f"Landed {len(commits)} commits with {sum_field(commits, 'files')} file touches and {sum_field(commits, 'insertions')} insertions."
        )

    if commit_kinds.get("prompt_corpus", 0) > max(1, len(commits) // 2):
        critique_points.append(
            "Most commits were prompt-corpus accounting, so the session was valuable as inventory reduction but weak as direct product/revenue delivery."
        )
    if followups:
        critique_points.append(
            f"{followups} roots still require follow-up review of an open/closed/live branch, so recording was not the same thing as finishing the downstream work."
        )
    if absent:
        critique_points.append(
            f"{absent} roots were routed to owner repos with no exact branch or PR; that is useful closure only if later runs do not rehydrate them without new evidence."
        )
    if hours >= 4 and batch_count and prompt_events / hours < 250:
        critique_points.append(
            "Throughput was modest for a long session; the review loop likely spent meaningful time on route discovery and verification rather than pure batch burn-down."
        )
    if not commits:
        critique_points.append("No commits landed in the window; this would be poor value unless the work was deliberately exploratory.")

    controls.append(
        "At session start and every 90 minutes, run `python3 scripts/session-value-review.py --hours 1.5` and continue only if it shows landed commits, receipt movement, or a named blocker."
    )
    controls.append(
        "Stop batch sweeping when follow-up roots outnumber merged/routed roots for two consecutive reports; switch to PR review, owner routing, or direct product work."
    )
    controls.append(
        "Close every long run with this report plus `python3 scripts/validate-task-board.py`; commit the report only when it changes public operating guidance."
    )

    if batch_count and commits:
        verdict = "valuable, but mostly as lifecycle debt reduction rather than immediate shipping"
    elif commits:
        verdict = "partly valuable, but not proven as prompt-corpus progress"
    else:
        verdict = "not yet proven valuable"

    return {
        "verdict": verdict,
        "commit_kinds": dict(commit_kinds.most_common()),
        "receipt_lanes": dict(lane_counts.most_common()),
        "root_statuses": dict(root_statuses.most_common()),
        "value_points": value_points,
        "critique_points": critique_points,
        "controls": controls,
    }


def build_snapshot(since: dt.datetime, until: dt.datetime) -> dict[str, Any]:
    commits = git_commits(since, until)
    receipts = batch_receipts(since, until)
    queue = current_queue()
    hours = max((until - since).total_seconds() / 3600, 0.01)
    findings = build_findings(commits, receipts, queue, hours)
    return {
        "generated_at": utc_now().isoformat(timespec="seconds"),
        "window": {
            "since": since.isoformat(timespec="seconds"),
            "until": until.isoformat(timespec="seconds"),
            "hours": round(hours, 2),
        },
        "inputs": {
            "git": {"root": str(ROOT), "commit_count": len(commits)},
            "batch_resolution_receipts": {
                "path": str(BATCH_RESOLUTION_RECEIPTS),
                "present": BATCH_RESOLUTION_RECEIPTS.exists(),
            },
            "batch_review_index": {"path": str(BATCH_REVIEW_INDEX), "present": BATCH_REVIEW_INDEX.exists()},
        },
        "metrics": {
            "commits": len(commits),
            "files_touched": sum_field(commits, "files"),
            "insertions": sum_field(commits, "insertions"),
            "deletions": sum_field(commits, "deletions"),
            "batch_receipts": len(receipts),
            "sessions_recorded": sum_field(receipts, "session_count"),
            "prompt_events_recorded": sum_field(receipts, "prompt_events"),
            "unique_prompt_hash_refs_recorded": sum_field(receipts, "unique_prompt_hashes"),
            "followup_roots": sum_field(receipts, "followup_roots"),
            "merged_roots": sum_field(receipts, "merged_roots"),
            "owner_absent_roots": sum_field(receipts, "owner_absent_roots"),
            "batches_per_hour": round(len(receipts) / hours, 2),
            "prompt_events_per_hour": round(sum_field(receipts, "prompt_events") / hours, 2),
        },
        "findings": findings,
        "commits": commits,
        "batch_receipts": receipts,
        "current_queue": queue,
    }


def render_counts(counts: dict[str, int]) -> str:
    return ", ".join(f"`{key}` {value}" for key, value in counts.items()) or "none"


def render_markdown(snapshot: dict[str, Any], *, limit: int) -> str:
    metrics = snapshot["metrics"]
    findings = snapshot["findings"]
    queue_coverage = (snapshot.get("current_queue") or {}).get("coverage") or {}
    queue_counts = ((snapshot.get("current_queue") or {}).get("counts") or {}).get("statuses") or {}
    lines = [
        "# Session Value Review",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        f"Window: `{snapshot['window']['since']}` to `{snapshot['window']['until']}` ({snapshot['window']['hours']}h)",
        "",
        "## Verdict",
        "",
        f"- `{findings['verdict']}`.",
        "",
        "## Measured Output",
        "",
        f"- Commits landed: `{metrics['commits']}`; files touched: `{metrics['files_touched']}`; insertions/deletions: `{metrics['insertions']}` / `{metrics['deletions']}`.",
        f"- Prompt batch receipts: `{metrics['batch_receipts']}`; batches/hour: `{metrics['batches_per_hour']}`.",
        f"- Sessions recorded: `{metrics['sessions_recorded']}`; prompt events recorded: `{metrics['prompt_events_recorded']}`; prompt events/hour: `{metrics['prompt_events_per_hour']}`.",
        f"- Merged-root evidence: `{metrics['merged_roots']}`; follow-up roots: `{metrics['followup_roots']}`; absent owner routes: `{metrics['owner_absent_roots']}`.",
        f"- Commit mix: {render_counts(findings['commit_kinds'])}.",
        f"- Receipt lane mix: {render_counts(findings['receipt_lanes'])}.",
        f"- Current corpus queue: `{queue_coverage.get('recorded_batches', 0)}` recorded, `{queue_coverage.get('open_review_batches', 0)}` open, `{queue_coverage.get('parked_secret_batches', 0)}` parked secret.",
        f"- Current queue status mix: {render_counts(queue_counts)}.",
        "",
        "## Value",
        "",
    ]
    for point in findings["value_points"] or ["No durable value points detected."]:
        lines.append(f"- {point}")
    lines += [
        "",
        "## Critique",
        "",
    ]
    for point in findings["critique_points"] or ["No critique points detected for this window."]:
        lines.append(f"- {point}")
    lines += [
        "",
        "## Next-Run Controls",
        "",
    ]
    for point in findings["controls"]:
        lines.append(f"- {point}")

    lines += [
        "",
        "## Recent Commits",
        "",
        "| Time | Commit | Kind | Subject |",
        "|---|---|---|---|",
    ]
    for commit in snapshot["commits"][-limit:]:
        lines.append(
            f"| `{commit['authored_at']}` | `{commit['short_sha']}` | `{commit['kind']}` | {commit['subject']} |"
        )
    if not snapshot["commits"]:
        lines.append("| n/a | n/a | n/a | none |")

    lines += [
        "",
        "## Batch Receipts",
        "",
        "| Time | Batch | Lane | Sessions | Events | Root Statuses |",
        "|---|---|---|---:|---:|---|",
    ]
    for receipt in snapshot["batch_receipts"][-limit:]:
        lines.append(
            f"| `{receipt['generated_at']}` | `{receipt['batch']}` | `{receipt['lane']}` | "
            f"{receipt['session_count']} | {receipt['prompt_events']} | {render_counts(receipt['root_statuses'])} |"
        )
    if not snapshot["batch_receipts"]:
        lines.append("| n/a | n/a | n/a | 0 | 0 | none |")

    lines += [
        "",
        "## Next Queue Slice",
        "",
        "| Batch | Status | Lane | Sessions | Events |",
        "|---|---|---|---:|---:|",
    ]
    for item in (snapshot.get("current_queue") or {}).get("next") or []:
        lines.append(
            f"| `{item['id']}` | `{item['status']}` | `{item['lane']}` | {item['session_count']} | {item['prompt_events']} |"
        )
    if not (snapshot.get("current_queue") or {}).get("next"):
        lines.append("| none | n/a | n/a | 0 | 0 |")

    lines += [
        "",
        "## Commands",
        "",
        "- Refresh this review: `python3 scripts/session-value-review.py --write --hours 12`",
        "- Short cadence check: `python3 scripts/session-value-review.py --hours 1.5`",
        "- Verify the task board: `python3 scripts/validate-task-board.py`",
        "",
        "## Privacy",
        "",
        "- This report uses commit metadata, public receipt metadata, and redacted batch queue metadata only.",
        "- It does not read or publish raw prompt/session text.",
        f"- Private JSON snapshot: `{relpath(PRIVATE_INDEX)}`.",
        "",
    ]
    return "\n".join(lines)


def write_outputs(snapshot: dict[str, Any], markdown: str) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(markdown, encoding="utf-8")
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a metadata-only long-session value review.")
    parser.add_argument("--hours", type=float, default=12.0, help="lookback window ending at --until")
    parser.add_argument("--since", help="ISO-8601 UTC timestamp for the review start")
    parser.add_argument("--until", help="ISO-8601 UTC timestamp for the review end")
    parser.add_argument("--limit", type=int, default=20, help="recent commits/receipts to show")
    parser.add_argument("--write", action="store_true", help="write docs and ignored private JSON")
    args = parser.parse_args()

    until = parse_timestamp(args.until) if args.until else utc_now()
    since = parse_timestamp(args.since) if args.since else until - dt.timedelta(hours=max(args.hours, 0.01))
    snapshot = build_snapshot(since, until)
    markdown = render_markdown(snapshot, limit=max(1, args.limit))
    if args.write:
        write_outputs(snapshot, markdown)
    else:
        print(markdown)
    msg = (
        "session-value-review: "
        f"{snapshot['metrics']['commits']} commits, "
        f"{snapshot['metrics']['batch_receipts']} batch receipts, "
        f"{snapshot['metrics']['prompt_events_recorded']} prompt events"
    )
    if args.write:
        msg += f"; wrote {DOC_PATH}"
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
