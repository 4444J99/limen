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
GATE_HISTORY = PRIVATE_ROOT / "lifecycle" / "session-value-gate-history.jsonl"
PRODUCT_LEDGER_INDEX = PRIVATE_ROOT / "lifecycle" / "product-ledger.json"
PROMPT_PACKET_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-packet-ledger.json"

RECORDED_STATUSES = {"owner-recorded", "non-source-recorded", "superseded-recorded"}
FOLLOWUP_ROOT_STATUSES = {
    "remote_pr_preserved",
    "remote_branch_preserved",
    "remote_branch_preserved_no_pr",
    "closed_pr_live_branch_preserved",
    "closed_pr_recorded_with_branch",
}
GATE_EXIT_CODES = {
    "continue_prompt_sweep": 0,
    "continue_prompt_sweep_watch_followups": 0,
    "continue_current_work": 0,
    "continue_direct_product_work": 0,
    "switch_to_packetization": 10,
    "switch_to_direct_product_work": 10,
    "stop_missing_inputs": 20,
    "stop_no_durable_progress": 20,
}
HIGH_MOTION_COMMIT_THRESHOLD = 20


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


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return rows
    for line in lines:
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


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
    if lowered.startswith("tabularius: preserve board projection"):
        return "task_board"
    if "task board" in lowered or "task states" in lowered or "stale task" in lowered or "jules" in lowered:
        return "task_board"
    if lowered.startswith("limen: refresh") and "pr receipt" in lowered:
        return "receipt_refresh"
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


def current_packet_queue() -> dict[str, Any]:
    index = load_json(PROMPT_PACKET_INDEX)
    coverage = index.get("coverage") if isinstance(index.get("coverage"), dict) else {}
    open_packets = []
    for item in index.get("open_packets") or []:
        if not isinstance(item, dict):
            continue
        open_packets.append(
            {
                "id": item.get("id"),
                "family": item.get("family"),
                "dispatchability": item.get("dispatchability"),
                "agent_fit": item.get("agent_fit"),
                "verification": item.get("verification"),
            }
        )
    return {
        "present": PROMPT_PACKET_INDEX.exists() and bool(index),
        "coverage": coverage,
        "next": open_packets[:5],
    }


def sum_field(items: list[dict[str, Any]], field: str) -> int:
    return sum(int(item.get(field) or 0) for item in items)


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def command_for_batch(batch: dict[str, Any]) -> str:
    batch_id = str(batch.get("id") or "")
    lane = str(batch.get("lane") or "")
    if not batch_id:
        return "python3 scripts/prompt-batch-review-ledger.py --write"
    if lane in {"family", "historical-worktree-review"}:
        return f"python3 scripts/resolve-codex-family-batch.py {batch_id} --write"
    if lane == "hash-review":
        return f"python3 scripts/resolve-codex-hash-batch.py {batch_id} --write"
    if lane == "legacy-session-review":
        return f"python3 scripts/resolve-legacy-session-batch.py {batch_id} --write"
    if lane == "stalled-review":
        return "python3 scripts/prompt-packet-ledger.py --write"
    return "python3 scripts/prompt-batch-review-ledger.py --write"


def gate_history() -> list[dict[str, Any]]:
    return load_jsonl(GATE_HISTORY)


def consecutive_pressure(name: str, current_pressure: bool, history: list[dict[str, Any]]) -> int:
    count = 1 if current_pressure else 0
    if not current_pressure:
        return count
    for row in reversed(history):
        gate = row.get("gate") if isinstance(row.get("gate"), dict) else {}
        pressures = gate.get("pressures") if isinstance(gate.get("pressures"), dict) else {}
        if pressures.get(name):
            count += 1
            continue
        break
    return count


def consecutive_followup_pressure(current_pressure: bool, history: list[dict[str, Any]]) -> int:
    return consecutive_pressure("followup_over_done_or_routed", current_pressure, history)


def direct_product_action() -> dict[str, Any]:
    rows = load_json(PRODUCT_LEDGER_INDEX).get("next_unblocked") or []
    row = rows[0] if rows and isinstance(rows[0], dict) else {}
    action = {
        "source": "product_ledger",
        "command": "python3 scripts/product-ledger.py --refresh --redacted-summary",
    }
    if row:
        action.update(
            {
                "product": row.get("id"),
                "owner": row.get("owner"),
                "state": row.get("state"),
                "disposition": row.get("disposition"),
            }
        )
    return action


def prompt_queue_action(next_batch: dict[str, Any]) -> dict[str, Any]:
    command = command_for_batch(next_batch)
    lane = str(next_batch.get("lane") or "")
    source = "prompt_packet_queue" if lane == "stalled-review" else "prompt_batch_queue"
    return {
        "source": source,
        "batch": next_batch.get("id"),
        "lane": next_batch.get("lane"),
        "command": command,
    }


def decide_gate(snapshot: dict[str, Any], history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    metrics = snapshot["metrics"]
    queue = snapshot.get("current_queue") or {}
    coverage = queue.get("coverage") if isinstance(queue.get("coverage"), dict) else {}
    packet_queue = snapshot.get("current_packet_queue") or {}
    packet_coverage = (
        packet_queue.get("coverage") if isinstance(packet_queue.get("coverage"), dict) else {}
    )
    findings = snapshot.get("findings") if isinstance(snapshot.get("findings"), dict) else {}
    commit_kinds = findings.get("commit_kinds") if isinstance(findings.get("commit_kinds"), dict) else {}
    inputs = snapshot.get("inputs") or {}
    missing_inputs = sorted(
        name
        for name, item in inputs.items()
        if isinstance(item, dict)
        and item.get("present") is False
        and name not in {"git", "product_ledger_index", "prompt_packet_index"}
    )
    done_or_routed = int(metrics.get("merged_roots") or 0) + int(metrics.get("owner_absent_roots") or 0)
    followups = int(metrics.get("followup_roots") or 0)
    followup_pressure = followups > done_or_routed and followups > 0
    history_rows = history if history is not None else gate_history()
    pressure_run = consecutive_followup_pressure(followup_pressure, history_rows)
    commits = int(metrics.get("commits") or 0)
    receipts = int(metrics.get("batch_receipts") or 0)
    open_batches = int(coverage.get("open_review_batches") or 0)
    packet_index_present = bool(packet_queue.get("present"))
    packet_next = [item for item in packet_queue.get("next") or [] if isinstance(item, dict)]
    try:
        open_packets = int(packet_coverage.get("open_packets") or len(packet_next))
    except (TypeError, ValueError):
        open_packets = len(packet_next)
    maintenance_commits = int(commit_kinds.get("task_board") or 0) + int(commit_kinds.get("receipt_refresh") or 0)
    value_commits = max(0, commits - maintenance_commits)
    has_durable_progress = receipts > 0 or value_commits > 0
    motion_without_receipts = commits > 0 and receipts == 0 and open_batches > 0
    high_motion_no_receipts = motion_without_receipts and commits >= env_int(
        "LIMEN_HIGH_MOTION_COMMIT_THRESHOLD",
        HIGH_MOTION_COMMIT_THRESHOLD,
    )
    receipt_only_motion = (
        receipts == 0
        and commits > 0
        and int(commit_kinds.get("receipt_refresh") or 0) > max(1, commits // 2)
    )
    no_receipt_run = consecutive_pressure("motion_without_receipts", motion_without_receipts, history_rows)
    high_motion_run = consecutive_pressure("high_motion_no_receipts", high_motion_no_receipts, history_rows)
    queue_next = [item for item in queue.get("next") or [] if isinstance(item, dict)]
    next_batch = queue_next[0] if queue_next else {}
    prompt_action = prompt_queue_action(next_batch)
    product_action = direct_product_action()
    next_action: dict[str, Any] = {}

    if missing_inputs:
        action = "stop_missing_inputs"
        reason = "Required metadata inputs are missing: " + ", ".join(missing_inputs) + "."
        next_commands = [
            "python3 scripts/prompt-priority-map.py --write",
            "python3 scripts/prompt-batch-review-ledger.py --write",
        ]
    elif receipt_only_motion:
        action = "switch_to_direct_product_work"
        owner = product_action.get("owner") or "the top unblocked product owner"
        product = product_action.get("product") or "the next unblocked product"
        reason = (
            f"Most landed commits were receipt refreshes and zero prompt-batch receipts moved; "
            f"classify this as custody-only and switch to product work on {product} ({owner})."
        )
        next_action = product_action
        next_commands = [str(product_action["command"])]
    elif not has_durable_progress:
        action = "stop_no_durable_progress"
        reason = "No landed value commits or prompt-batch receipts were detected in this cadence window."
        next_commands = [
            "python3 scripts/session-value-review.py --write --hours 12",
            "python3 scripts/validate-task-board.py",
        ]
    elif motion_without_receipts and no_receipt_run >= 2:
        if next_batch:
            action = "switch_to_packetization"
            reason = (
                "Commits landed while zero prompt-batch receipts moved for two consecutive cadence windows; "
                "stop generic dispatch and resolve or packetize the next prompt batch."
            )
            next_action = prompt_action
            next_commands = [str(prompt_action["command"])]
        else:
            action = "switch_to_direct_product_work"
            owner = product_action.get("owner") or "the top unblocked product owner"
            product = product_action.get("product") or "the next unblocked product"
            reason = (
                "Commits landed while zero prompt-batch receipts moved for two consecutive cadence windows, "
                f"and no prompt queue slice is available; switch to product work on {product} ({owner})."
            )
            next_action = product_action
            next_commands = [str(product_action["command"])]
    elif open_batches <= 0:
        if not packet_index_present or open_packets > 0:
            action = "switch_to_packetization"
            reason = (
                "No open prompt-review batches remain; refresh or resolve prompt packets before "
                "generic dispatch resumes."
            )
            next_action = {
                "source": "prompt_packet_queue",
                "command": "python3 scripts/prompt-packet-ledger.py --write",
            }
            next_commands = [str(next_action["command"])]
        else:
            action = "continue_direct_product_work"
            owner = product_action.get("owner") or "the top unblocked product owner"
            product = product_action.get("product") or "the next unblocked product"
            reason = (
                "No open prompt-review batches or prompt packets remain; continue value-gated "
                f"direct product dispatch on {product} ({owner})."
            )
            next_action = product_action
            next_commands = [str(product_action["command"])]
    elif pressure_run >= 2:
        action = "switch_to_packetization"
        reason = "Follow-up roots outnumbered merged/routed roots for two consecutive cadence reports."
        next_action = {"source": "prompt_packet_queue", "command": "python3 scripts/prompt-packet-ledger.py --write"}
        next_commands = [
            "python3 scripts/prompt-packet-ledger.py --write",
            "python3 scripts/validate-task-board.py",
        ]
    elif followup_pressure:
        action = "continue_prompt_sweep_watch_followups"
        reason = "Durable progress exists, but follow-up roots outnumber merged/routed roots in this cadence window."
        next_action = prompt_action
        next_commands = [str(prompt_action["command"]), "python3 scripts/session-value-review.py --gate --hours 1.5"]
    elif receipts > 0:
        action = "continue_prompt_sweep"
        reason = "Prompt-batch receipt movement is still producing durable lifecycle evidence."
        next_action = prompt_action
        next_commands = [str(prompt_action["command"])]
    else:
        action = "continue_current_work"
        reason = (
            "Commits landed, but no prompt-batch receipt moved; this is the grace window before "
            "the gate requires prompt-batch resolution, packetization, or direct product work."
        )
        next_commands = ["python3 scripts/session-value-review.py --gate --hours 1.5"]

    return {
        "policy": "session-value-gate-v1",
        "action": action,
        "exit_code": GATE_EXIT_CODES[action],
        "reason": reason,
        "pressures": {
            "followup_over_done_or_routed": followup_pressure,
            "consecutive_followup_pressure_reports": pressure_run,
            "followup_roots": followups,
            "done_or_routed_roots": done_or_routed,
            "no_durable_progress": not has_durable_progress,
            "motion_without_receipts": motion_without_receipts,
            "consecutive_motion_without_receipts": no_receipt_run,
            "high_motion_no_receipts": high_motion_no_receipts,
            "consecutive_high_motion_no_receipts": high_motion_run,
            "receipt_only_motion": receipt_only_motion,
            "maintenance_commits": maintenance_commits,
            "value_commits": value_commits,
            "open_review_batches": open_batches,
        },
        "evidence": {
            "commits": commits,
            "batch_receipts": receipts,
            "prompt_events_recorded": int(metrics.get("prompt_events_recorded") or 0),
            "commit_kinds": commit_kinds,
            "next_batch": next_batch.get("id"),
            "next_lane": next_batch.get("lane"),
            "next_product": product_action.get("product"),
            "next_product_owner": product_action.get("owner"),
            "prompt_packet_index_present": packet_index_present,
            "open_prompt_packets": open_packets,
        },
        "next_action": next_action,
        "next_commands": next_commands,
    }


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

    if commits and not batch_count and open_batches:
        critique_points.append(
            f"{len(commits)} commits landed while zero prompt-batch receipts moved and {open_batches} review batches remain open; this is current-work motion, not proven ask-corpus closure."
        )
    if len(commits) >= 20 and not batch_count:
        critique_points.append(
            f"High-motion/no-receipt window: {sum_field(commits, 'files')} file touches and no prompt-event recording. Run the explicit prompt batch command or switch to bounded product/owner work instead of letting receipt-free activity masquerade as lifecycle progress."
        )
    if commit_kinds.get("receipt_refresh", 0) > max(1, len(commits) // 2):
        critique_points.append(
            "Most commits were PR-receipt refreshes; useful for custody, but weak evidence of shipped product, resolved prompts, or reduced open review pressure."
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
        "At session start and every 90 minutes, run `python3 scripts/session-value-review.py --gate --hours 1.5`; continue only on exit 0."
    )
    controls.append(
        "Treat gate exit 10 as a lane switch: stop batch sweeping and run packetization, PR review, owner routing, or direct product work."
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
    snapshot = {
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
            "prompt_packet_index": {"path": str(PROMPT_PACKET_INDEX), "present": PROMPT_PACKET_INDEX.exists()},
            "product_ledger_index": {"path": str(PRODUCT_LEDGER_INDEX), "present": PRODUCT_LEDGER_INDEX.exists()},
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
        "current_packet_queue": current_packet_queue(),
    }
    snapshot["gate"] = decide_gate(snapshot)
    return snapshot


def render_counts(counts: dict[str, int]) -> str:
    return ", ".join(f"`{key}` {value}" for key, value in counts.items()) or "none"


def render_markdown(snapshot: dict[str, Any], *, limit: int) -> str:
    metrics = snapshot["metrics"]
    findings = snapshot["findings"]
    gate = snapshot.get("gate") or {}
    pressures = gate.get("pressures") if isinstance(gate.get("pressures"), dict) else {}
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
        "## Operating Gate",
        "",
        f"- Action: `{gate.get('action', 'unknown')}` (exit `{gate.get('exit_code', 'n/a')}`).",
        f"- Reason: {gate.get('reason', 'No gate decision available.')}",
        f"- Follow-up pressure: `{pressures.get('followup_roots', 0)}` follow-up roots vs `{pressures.get('done_or_routed_roots', 0)}` merged/routed roots; consecutive pressure reports `{pressures.get('consecutive_followup_pressure_reports', 0)}`.",
        f"- No-receipt pressure: `{str(pressures.get('motion_without_receipts', False)).lower()}`; consecutive reports `{pressures.get('consecutive_motion_without_receipts', 0)}`; high-motion `{str(pressures.get('high_motion_no_receipts', False)).lower()}`.",
        f"- Maintenance commits: `{pressures.get('maintenance_commits', 0)}`; value commits: `{pressures.get('value_commits', 0)}`; custody-only: `{str(pressures.get('receipt_only_motion', False)).lower()}`.",
        f"- Open review batches: `{pressures.get('open_review_batches', 0)}`; no durable progress: `{str(pressures.get('no_durable_progress', False)).lower()}`.",
        f"- Next commands: {'; '.join(f'`{command}`' for command in gate.get('next_commands') or ['none'])}.",
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
        "- Short cadence gate: `python3 scripts/session-value-review.py --gate --hours 1.5`",
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


def append_gate_history(snapshot: dict[str, Any]) -> None:
    gate = snapshot.get("gate") if isinstance(snapshot.get("gate"), dict) else {}
    record = {
        "recorded_at": utc_now().isoformat(timespec="seconds"),
        "window": snapshot.get("window") or {},
        "gate": {
            "policy": gate.get("policy"),
            "action": gate.get("action"),
            "exit_code": gate.get("exit_code"),
            "reason": gate.get("reason"),
            "pressures": gate.get("pressures") or {},
            "evidence": gate.get("evidence") or {},
        },
    }
    GATE_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with GATE_HISTORY.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a metadata-only long-session value review.")
    parser.add_argument("--hours", type=float, default=12.0, help="lookback window ending at --until")
    parser.add_argument("--since", help="ISO-8601 UTC timestamp for the review start")
    parser.add_argument("--until", help="ISO-8601 UTC timestamp for the review end")
    parser.add_argument("--limit", type=int, default=20, help="recent commits/receipts to show")
    parser.add_argument("--write", action="store_true", help="write docs and ignored private JSON")
    parser.add_argument("--gate", action="store_true", help="print and enforce the operating gate decision")
    parser.add_argument("--no-record-gate", action="store_true", help="do not append --gate to ignored gate history")
    args = parser.parse_args()

    until = parse_timestamp(args.until) if args.until else utc_now()
    since = parse_timestamp(args.since) if args.since else until - dt.timedelta(hours=max(args.hours, 0.01))
    snapshot = build_snapshot(since, until)
    markdown = render_markdown(snapshot, limit=max(1, args.limit))
    if args.write:
        write_outputs(snapshot, markdown)
    if args.gate and not args.no_record_gate:
        append_gate_history(snapshot)
    if args.gate:
        print(json.dumps(snapshot["gate"], indent=2, sort_keys=True))
        return int(snapshot["gate"]["exit_code"])
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
