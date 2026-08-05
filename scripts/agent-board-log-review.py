#!/usr/bin/env python3
"""Review task-board-only agent sessions without publishing prompt text.

This consumes the redacted/private full-stack queue produced by
``agent-code-review-queue.py``. It reconstructs nearby ``tasks.yaml`` commits,
then summarizes task-state, budget, and dispatch-log anomalies. Raw prompts and
task output bodies stay in the ignored private corpus.
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import json
import os
import re
import subprocess
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
PRIVATE_QUEUE = PRIVATE_ROOT / "full-stack-review" / "agent-code-review-queue.json"
PRIVATE_REVIEW = PRIVATE_ROOT / "full-stack-review" / "agent-board-log-review.json"
DOC_PATH = ROOT / "docs" / "agent-board-log-review.md"
TASKS_PATH = ROOT / "tasks.yaml"
MCP_SERVER = ROOT / "mcp" / "src" / "limen_mcp" / "server.py"

VERIFY_RE = re.compile(
    r"\b("
    r"verify-whole\.sh|pytest|ruff|mypy|py_compile|npm run (?:build|check|test)|"
    r"pnpm (?:test|build)|vitest|git diff --check|verify|predicate|tests? passed|"
    r"passed|green|ci green|build passed"
    r")\b",
    re.I,
)
RECEIPT_RE = re.compile(
    r"(https://github\.com/[^)\s]+/pull/\d+|\bPR\s*#?\d+\b|\bcommit\s+[0-9a-f]{7,40}\b|"
    r"\b[0-9a-f]{7,40}\b|\.jsonl\b|\.md\b|\.json\b|artifact|receipt)",
    re.I,
)
BLOCKER_RE = re.compile(
    r"\b(blocked|needs human|needs_human|auth|billing|credential|permission|quota|failed|failure|cannot)\b",
    re.I,
)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_iso(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def relpath(path: str | Path | None) -> str:
    if not path:
        return ""
    p = Path(path)
    try:
        return str(p.resolve().relative_to(ROOT))
    except (OSError, ValueError):
        return str(path).replace(str(Path.home()), "~")


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_valid_statuses() -> set[str]:
    try:
        module = ast.parse(MCP_SERVER.read_text(encoding="utf-8"))
    except OSError:
        return {"open", "dispatched", "in_progress", "done", "failed", "failed_blocked", "needs_human", "archived"}
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "VALID_STATUSES":
                    return {str(item) for item in ast.literal_eval(node.value)}
    return {"open", "dispatched", "in_progress", "done", "failed", "failed_blocked", "needs_human", "archived"}


def git(args: list[str], *, timeout: int = 20) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(ROOT), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout if proc.returncode == 0 else ""


@lru_cache(maxsize=256)
def git_yaml(commit: str) -> dict[str, Any]:
    text = git(["show", f"{commit}:tasks.yaml"], timeout=30)
    if not text:
        return {}
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def tasks_by_id(board: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(task.get("id")): task
        for task in board.get("tasks") or []
        if isinstance(task, dict) and task.get("id") is not None
    }


def budget_spent(board: dict[str, Any]) -> tuple[int | float | None, dict[str, int | float]]:
    track = (((board.get("portal") or {}).get("budget") or {}).get("track") or {})
    per_agent = track.get("per_agent") or {}
    return track.get("spent"), {str(k): v for k, v in per_agent.items() if isinstance(v, (int, float))}


def text_surface(task: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("id", "title", "description", "receipt", "verification", "result", "notes"):
        value = task.get(key)
        if isinstance(value, str):
            parts.append(value)
    for entry in task.get("dispatch_log") or []:
        if not isinstance(entry, dict):
            continue
        for key in ("status", "output", "receipt", "verification", "error"):
            value = entry.get(key)
            if isinstance(value, str):
                parts.append(value)
    return "\n".join(parts)


def evidence_flags(task: dict[str, Any]) -> dict[str, bool]:
    text = text_surface(task)
    return {
        "verification": bool(VERIFY_RE.search(text)),
        "receipt": bool(RECEIPT_RE.search(text)),
        "blocker": bool(BLOCKER_RE.search(text)),
    }


def transition(before: dict[str, Any] | None, after: dict[str, Any] | None) -> str:
    if before is None:
        left = "<added>"
    else:
        left = str(before.get("status") or "<missing>")
    if after is None:
        right = "<deleted>"
    else:
        right = str(after.get("status") or "<missing>")
    return f"{left}->{right}"


def changed_tasks(before: dict[str, Any], after: dict[str, Any]) -> list[tuple[str, dict[str, Any] | None, dict[str, Any] | None]]:
    left = tasks_by_id(before)
    right = tasks_by_id(after)
    out = []
    for task_id in sorted(set(left) | set(right)):
        old = left.get(task_id)
        new = right.get(task_id)
        if old != new:
            out.append((task_id, old, new))
    return out


def status_counts(board: dict[str, Any]) -> Counter[str]:
    return Counter(str(task.get("status") or "<missing>") for task in board.get("tasks") or [] if isinstance(task, dict))


def analyze_commit(commit: str, valid_statuses: set[str]) -> dict[str, Any]:
    meta = git(["show", "-s", "--format=%H%x09%h%x09%aI%x09%s", commit]).strip()
    if not meta:
        return {}
    full, short, authored_at, subject = meta.split("\t", 3)
    before = git_yaml(f"{full}^")
    after = git_yaml(full)
    if not before or not after:
        return {}
    changed = changed_tasks(before, after)
    spent_before, per_before = budget_spent(before)
    spent_after, per_after = budget_spent(after)
    per_agent_delta = {
        key: per_after.get(key, 0) - per_before.get(key, 0)
        for key in sorted(set(per_before) | set(per_after))
        if per_after.get(key, 0) != per_before.get(key, 0)
    }

    transitions: Counter[str] = Counter()
    invalid_after: Counter[str] = Counter()
    log_shrink_ids: list[str] = []
    direct_done_without_log: list[str] = []
    done_without_verification: list[str] = []
    done_without_receipt: list[str] = []
    reopened_after_done: list[str] = []

    for task_id, old, new in changed:
        tr = transition(old, new)
        transitions[tr] += 1
        new_status = str((new or {}).get("status") or "") if new else ""
        if new_status and new_status not in valid_statuses:
            invalid_after[new_status] += 1

        old_log = (old or {}).get("dispatch_log") or []
        new_log = (new or {}).get("dispatch_log") or []
        if len(new_log) < len(old_log):
            log_shrink_ids.append(task_id)

        old_status = str((old or {}).get("status") or "") if old else "<added>"
        if new_status == "done":
            flags = evidence_flags(new or {})
            if len(new_log) == 0 or len(new_log) <= len(old_log):
                direct_done_without_log.append(task_id)
            if not flags["verification"]:
                done_without_verification.append(task_id)
            if not flags["receipt"]:
                done_without_receipt.append(task_id)
        if old and any(str((entry or {}).get("status") or "") == "done" for entry in old_log):
            if new_status not in {"done", "archived"}:
                reopened_after_done.append(task_id)
        if old_status == "done" and new_status not in {"done", "archived"}:
            reopened_after_done.append(task_id)

    before_status_counts = status_counts(before)
    after_status_counts = status_counts(after)
    invalid_status_total = sum(count for status, count in after_status_counts.items() if status not in valid_statuses)
    status_delta = {
        status: after_status_counts.get(status, 0) - before_status_counts.get(status, 0)
        for status in sorted(set(before_status_counts) | set(after_status_counts))
        if after_status_counts.get(status, 0) != before_status_counts.get(status, 0)
    }

    return {
        "commit": full,
        "short": short,
        "authored_at": authored_at,
        "subject": subject,
        "changed_tasks": len(changed),
        "budget_spent_before": spent_before,
        "budget_spent_after": spent_after,
        "budget_spent_delta": (
            spent_after - spent_before
            if isinstance(spent_after, (int, float)) and isinstance(spent_before, (int, float))
            else None
        ),
        "per_agent_delta": per_agent_delta,
        "transition_counts": dict(transitions.most_common()),
        "status_delta": status_delta,
        "invalid_status_total_after": invalid_status_total,
        "invalid_statuses_changed_after": dict(invalid_after),
        "log_shrink_ids": log_shrink_ids,
        "direct_done_without_log_ids": direct_done_without_log,
        "done_without_verification_ids": done_without_verification,
        "done_without_receipt_ids": done_without_receipt,
        "reopened_after_done_ids": sorted(set(reopened_after_done)),
    }


def session_commit_matches(rows: list[dict[str, Any]], window_minutes: int) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    matches: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unmatched: list[dict[str, Any]] = []
    for rank, row in enumerate(rows, 1):
        first = parse_iso(str(row.get("first_ts") or ""))
        last = parse_iso(str(row.get("last_ts") or ""))
        if not first or not last:
            unmatched.append({"rank": rank, "agent": row.get("agent"), "session_id": row.get("session_id"), "reason": "missing-time"})
            continue
        since = (first - dt.timedelta(minutes=window_minutes)).isoformat()
        until = (last + dt.timedelta(minutes=window_minutes)).isoformat()
        output = git(
            [
                "log",
                f"--since={since}",
                f"--until={until}",
                "--format=%H",
                "--",
                "tasks.yaml",
            ],
            timeout=20,
        )
        commits = [line.strip() for line in output.splitlines() if line.strip()]
        if not commits:
            unmatched.append(
                {
                    "rank": rank,
                    "agent": row.get("agent"),
                    "session_id": row.get("session_id"),
                    "review_score": row.get("review_score"),
                    "first_ts": row.get("first_ts"),
                    "last_ts": row.get("last_ts"),
                    "ideal_gaps": row.get("ideal_gaps") or [],
                    "reason": "no-nearby-tasks-yaml-commit",
                }
            )
            continue
        for commit in commits:
            matches[commit].append(
                {
                    "rank": rank,
                    "agent": row.get("agent"),
                    "session_id": row.get("session_id"),
                    "review_score": row.get("review_score"),
                    "first_ts": row.get("first_ts"),
                    "last_ts": row.get("last_ts"),
                    "ideal_gaps": row.get("ideal_gaps") or [],
                }
            )
    return matches, unmatched


def build_review(window_minutes: int, analyze_commit_limit: int) -> dict[str, Any]:
    queue = load_json(PRIVATE_QUEUE)
    rows = [row for row in queue.get("board_only") or [] if isinstance(row, dict)]
    valid_statuses = load_valid_statuses()
    matches, unmatched = session_commit_matches(rows, window_minutes)
    commits = []
    ordered_matches = sorted(
        matches.items(),
        key=lambda item: (-len(item[1]), min(int(row["rank"]) for row in item[1]), item[0]),
    )
    for commit, sessions in ordered_matches[:analyze_commit_limit]:
        analysis = analyze_commit(commit, valid_statuses)
        if not analysis:
            continue
        analysis["matched_session_count"] = len(sessions)
        analysis["matched_agents"] = dict(Counter(str(item.get("agent") or "unknown") for item in sessions).most_common())
        analysis["matched_session_ranks"] = [int(item["rank"]) for item in sorted(sessions, key=lambda item: int(item["rank"]))]
        analysis["matched_session_ids"] = [str(item.get("session_id")) for item in sorted(sessions, key=lambda item: int(item["rank"]))]
        gap_counts = Counter(gap for item in sessions for gap in item.get("ideal_gaps") or [])
        analysis["matched_gap_counts"] = dict(gap_counts.most_common())
        commits.append(analysis)

    commits.sort(
        key=lambda item: (
            -int(item.get("matched_session_count") or 0),
            -int(item.get("changed_tasks") or 0),
            str(item.get("authored_at") or ""),
        )
    )
    gap_counts = Counter(gap for row in rows for gap in row.get("ideal_gaps") or [])
    agent_counts = Counter(str(row.get("agent") or "unknown") for row in rows)
    matched_rank_set = {int(item["rank"]) for sessions in matches.values() for item in sessions}
    return {
        "generated_at": now_iso(),
        "source": str(PRIVATE_QUEUE),
        "window_minutes": window_minutes,
        "counts": {
            "board_only_sessions": len(rows),
            "matched_sessions": len(matched_rank_set),
            "unmatched_sessions": len(unmatched),
            "matched_commits": len(commits),
            "matched_commit_windows": len(matches),
            "analyzed_commit_limit": analyze_commit_limit,
        },
        "agent_counts": dict(agent_counts.most_common()),
        "gap_counts": dict(gap_counts.most_common()),
        "valid_statuses": sorted(valid_statuses),
        "commits": commits,
        "unmatched_sessions": unmatched,
        "current_board": current_board_summary(valid_statuses),
    }


def current_board_summary(valid_statuses: set[str]) -> dict[str, Any]:
    try:
        data = yaml.safe_load(TASKS_PATH.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {"present": False}
    counts = status_counts(data)
    invalid = {status: count for status, count in counts.items() if status not in valid_statuses}
    return {
        "present": True,
        "tasks": sum(counts.values()),
        "status_counts": dict(counts.most_common()),
        "invalid_status_counts": invalid,
    }


def compact_id_list(ids: list[str], limit: int = 8) -> str:
    if not ids:
        return "`0`"
    head = ", ".join(f"`{item}`" for item in ids[:limit])
    if len(ids) > limit:
        head += f", +{len(ids) - limit} more"
    return head


def public_text(value: Any) -> str:
    return str(value or "").replace("|", "/").replace("\u2014", "-").replace("\u2013", "-")


def render_doc(review: dict[str, Any], *, commit_limit: int) -> str:
    counts = review["counts"]
    current = review.get("current_board") or {}
    lines = [
        "# Agent Board/Log Review",
        "",
        f"Generated: `{review['generated_at']}`",
        "",
        "## Scope",
        "",
        "- Input: board/log-only rows from the private full-stack session queue.",
        "- Method: map sessions to nearby `tasks.yaml` commits, then diff task-state, budget, and dispatch-log structure.",
        "- Redaction boundary: prompt bodies, task output bodies, and raw private session text stay under `.limen-private/`.",
        "",
        "## Coverage",
        "",
        f"- Board/log-only sessions reviewed: `{counts['board_only_sessions']}`.",
        f"- Sessions with nearby `tasks.yaml` commits (`+/-{review['window_minutes']}m`): `{counts['matched_sessions']}`.",
        f"- Sessions with no nearby board commit: `{counts['unmatched_sessions']}`.",
        f"- Unique matched board commit windows discovered: `{counts.get('matched_commit_windows', counts['matched_commits'])}`.",
        f"- Deep-analyzed board commits: `{counts['matched_commits']}` (cap `{counts.get('analyzed_commit_limit')}`).",
        f"- Current board validation snapshot: `{current.get('tasks', 0)}` tasks; invalid statuses `{sum((current.get('invalid_status_counts') or {}).values())}`.",
        "",
        "## Agents",
        "",
        "| Agent | Sessions |",
        "|---|---:|",
    ]
    for agent, count in review.get("agent_counts", {}).items():
        lines.append(f"| `{agent}` | {count} |")

    lines.extend(
        [
            "",
            "## Ideal-Form Gaps",
            "",
            "| Gap | Sessions |",
            "|---|---:|",
        ]
    )
    for gap, count in review.get("gap_counts", {}).items():
        lines.append(f"| {gap} | {count} |")

    lines.extend(
        [
            "",
            "## Matched Commit Findings",
            "",
            "| Commit | Matched sessions | Changed tasks | Budget delta | Invalid statuses after | Log shrinks | Done lacking verification | Done lacking receipt | Subject |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for item in review.get("commits", [])[:commit_limit]:
        lines.append(
            "| "
            f"`{item['short']}` | "
            f"{item.get('matched_session_count', 0)} | "
            f"{item.get('changed_tasks', 0)} | "
            f"{item.get('budget_spent_delta')} | "
            f"{item.get('invalid_status_total_after', 0)} | "
            f"{len(item.get('log_shrink_ids') or [])} | "
            f"{len(item.get('done_without_verification_ids') or [])} | "
            f"{len(item.get('done_without_receipt_ids') or [])} | "
            f"{public_text(item.get('subject'))[:120]} |"
        )

    lines.extend(
        [
            "",
            "## High-Risk Examples",
            "",
        ]
    )
    high_risk = [
        item
        for item in review.get("commits", [])
        if int(item.get("changed_tasks") or 0) >= 50
        or len(item.get("log_shrink_ids") or []) > 0
        or int(item.get("invalid_status_total_after") or 0) > 0
        or len(item.get("direct_done_without_log_ids") or []) > 0
    ][:12]
    if not high_risk:
        lines.append("- No high-risk board commits matched the current heuristics.")
    for item in high_risk:
        lines.append(
            f"- `{item['short']}` matched `{item.get('matched_session_count', 0)}` session windows and changed "
            f"`{item.get('changed_tasks', 0)}` task records; subject: {public_text(item.get('subject'))}."
        )
        if item.get("invalid_status_total_after"):
            lines.append(
                f"  Invalid status count after commit: `{item['invalid_status_total_after']}`; "
                f"changed invalid statuses: `{item.get('invalid_statuses_changed_after')}`."
            )
        if item.get("log_shrink_ids"):
            lines.append(f"  Dispatch logs shrank for: {compact_id_list(item['log_shrink_ids'])}.")
        if item.get("direct_done_without_log_ids"):
            lines.append(f"  Done transitions without a new log entry: {compact_id_list(item['direct_done_without_log_ids'])}.")
        if item.get("reopened_after_done_ids"):
            lines.append(f"  Reopened after done: {compact_id_list(item['reopened_after_done_ids'])}.")

    lines.extend(
        [
            "",
            "## Unmatched Session Sample",
            "",
            "These sessions had prompt/session metadata and `tasks.yaml` as the only changed-file surface, but no nearby board commit was found in the reconstruction window.",
            "",
            "| Rank | Agent | Session | Score | First | Last | Gaps |",
            "|---:|---|---|---:|---|---|---|",
        ]
    )
    for item in review.get("unmatched_sessions", [])[:20]:
        gaps = "; ".join(item.get("ideal_gaps") or [])
        lines.append(
            f"| {item.get('rank')} | `{item.get('agent')}` | `{item.get('session_id')}` | "
            f"{item.get('review_score', '')} | `{item.get('first_ts')}` | `{item.get('last_ts')}` | {gaps} |"
        )

    lines.extend(
        [
            "",
            "## Findings",
            "",
            "1. Board-only sessions are mostly governance/accounting work, not implementation proof. The dominant failure mode is missing explicit predicates/receipts in the prompt and missing verification language in the outcome.",
            "2. Several historical board commits bundled one named completion with broad queue rewrites, budget counter changes, and mass dispatch churn. That makes prompt-vs-done attribution weak even when an individual task may have been legitimately finished.",
            "3. Historical commits used or preserved noncanonical `cancelled` statuses before the current canonical state set was enforced. The live board now validates, but the audit trail contains incompatible lifecycle vocabulary.",
            "4. Some `done` board transitions have no new dispatch-log entry, no verification phrase, or no durable receipt phrase. Those should be treated as unproven closures unless a separate PR/commit/receipt can be reconstructed.",
            "5. Sessions with no nearby board commit are likely no-op, abandoned, off-window, or state-only attempts. They need private-session receipt inspection before being credited as completed work.",
            "",
            "## Commands",
            "",
            "- Refresh source review first: `env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-code-review-queue.py --write`",
            "- Refresh this board/log review: `env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-board-log-review.py --write`",
            f"- Private structured output: `{relpath(PRIVATE_REVIEW)}`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a redacted review of board/log-only agent sessions.")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--window-minutes", type=int, default=30)
    parser.add_argument("--commit-limit", type=int, default=40)
    parser.add_argument("--analyze-commit-limit", type=int, default=20)
    args = parser.parse_args()

    review = build_review(args.window_minutes, args.analyze_commit_limit)
    doc = render_doc(review, commit_limit=args.commit_limit)
    if args.write:
        PRIVATE_REVIEW.parent.mkdir(parents=True, exist_ok=True)
        PRIVATE_REVIEW.write_text(json.dumps(review, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        DOC_PATH.write_text(doc, encoding="utf-8")
    else:
        print(doc, end="")
    counts = review["counts"]
    print(
        "agent-board-log-review: "
        f"{counts['board_only_sessions']} board sessions, "
        f"{counts['matched_sessions']} matched, "
        f"{counts['matched_commits']} commits"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
