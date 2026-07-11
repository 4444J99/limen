#!/usr/bin/env python3
"""Reconstruct session windows that have no structured changed-file refs.

This script does not read raw prompt bodies. It consumes the private full-stack
session review, groups no-change-ref sessions by git root, and maps them to
nearby git activity windows so broad/no-op/off-window sessions can be audited
without publishing private transcript text.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
FULL_STACK_REVIEW = PRIVATE_ROOT / "full-stack-review" / "agent-session-review.json"
PRIVATE_REVIEW = PRIVATE_ROOT / "full-stack-review" / "agent-reconstruction-review.json"
DOC_PATH = ROOT / "docs" / "agent-reconstruction-review.md"


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


def iso(value: dt.datetime | None) -> str | None:
    if not value:
        return None
    return value.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def relpath(path: str | Path | None) -> str:
    if not path:
        return "unknown"
    text = str(path).replace(str(HOME), "~")
    try:
        return str(Path(path).expanduser().resolve().relative_to(ROOT))
    except (OSError, ValueError):
        return text


def public_text(value: Any) -> str:
    return str(value or "").replace("|", "/").replace("\u2014", "-").replace("\u2013", "-")


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def run_git(cwd: Path, args: list[str], *, timeout: int = 20) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout if proc.returncode == 0 else ""


GIT_ROOT_CACHE: dict[str, str | None] = {}


def git_root(cwd: str | None) -> str | None:
    if not cwd:
        return None
    if cwd in GIT_ROOT_CACHE:
        return GIT_ROOT_CACHE[cwd]
    path = Path(cwd).expanduser()
    if not path.exists():
        GIT_ROOT_CACHE[cwd] = None
        return None
    root = run_git(path, ["rev-parse", "--show-toplevel"], timeout=6).strip()
    GIT_ROOT_CACHE[cwd] = root or None
    return GIT_ROOT_CACHE[cwd]


def load_sessions() -> list[dict[str, Any]]:
    review = load_json(FULL_STACK_REVIEW)
    sessions = []
    for item in review.get("sessions") or []:
        if not isinstance(item, dict):
            continue
        if int(item.get("changed_file_count") or 0) != 0:
            continue
        if int(item.get("risk_score") or 0) <= 0:
            continue
        first = parse_iso(str(item.get("first_ts") or ""))
        last = parse_iso(str(item.get("last_ts") or ""))
        root = git_root(item.get("cwd"))
        sessions.append(
            {
                "agent": item.get("agent"),
                "session_id": item.get("session_id"),
                "cwd": item.get("cwd"),
                "git_root": root,
                "display_root": relpath(root or item.get("cwd")),
                "first": first,
                "last": last,
                "first_ts": iso(first),
                "last_ts": iso(last),
                "prompt_events": int(item.get("prompt_events") or 0),
                "unique_prompts": int(item.get("unique_prompts") or 0),
                "risk_score": int(item.get("risk_score") or 0),
                "ideal_gaps": item.get("ideal_gaps") or [],
                "paths": item.get("paths") or [],
                "sources": sorted((item.get("sources") or {}).keys())
                if isinstance(item.get("sources"), dict)
                else [],
            }
        )
    return sessions


def session_groups(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for session in sessions:
        key = session.get("git_root") or f"nogit:{session.get('display_root')}"
        group = grouped.setdefault(
            key,
            {
                "key": key,
                "git_root": session.get("git_root"),
                "display_root": session.get("display_root"),
                "sessions": [],
                "agents": Counter(),
                "gaps": Counter(),
                "risk_score": 0,
                "prompt_events": 0,
                "first": session.get("first"),
                "last": session.get("last"),
            },
        )
        group["sessions"].append(session)
        group["agents"][str(session.get("agent") or "unknown")] += 1
        group["risk_score"] += int(session.get("risk_score") or 0)
        group["prompt_events"] += int(session.get("prompt_events") or 0)
        for gap in session.get("ideal_gaps") or []:
            group["gaps"][gap] += 1
        first = session.get("first")
        last = session.get("last")
        if first and (not group["first"] or first < group["first"]):
            group["first"] = first
        if last and (not group["last"] or last > group["last"]):
            group["last"] = last

    out = []
    for group in grouped.values():
        out.append(
            {
                "key": group["key"],
                "git_root": group["git_root"],
                "display_root": group["display_root"],
                "session_count": len(group["sessions"]),
                "agents": dict(group["agents"].most_common()),
                "top_gaps": group["gaps"].most_common(8),
                "risk_score": group["risk_score"],
                "prompt_events": group["prompt_events"],
                "first_ts": iso(group["first"]),
                "last_ts": iso(group["last"]),
                "sessions": sorted(group["sessions"], key=lambda item: -int(item.get("risk_score") or 0)),
            }
        )
    out.sort(key=lambda item: (-int(item["risk_score"]), -int(item["session_count"]), str(item["display_root"])))
    return out


def git_commits_for_group(group: dict[str, Any], window_minutes: int) -> list[dict[str, Any]]:
    root = group.get("git_root")
    first = parse_iso(group.get("first_ts"))
    last = parse_iso(group.get("last_ts"))
    if not root or not first or not last:
        return []
    since = (first - dt.timedelta(minutes=window_minutes)).isoformat()
    until = (last + dt.timedelta(minutes=window_minutes)).isoformat()
    output = run_git(
        Path(root),
        ["log", f"--since={since}", f"--until={until}", "--format=%H%x09%h%x09%aI%x09%s"],
        timeout=30,
    )
    commits: list[dict[str, Any]] = []
    for line in output.splitlines():
        parts = line.split("\t", 3)
        if len(parts) != 4:
            continue
        full, short, authored_at, subject = parts
        authored = parse_iso(authored_at)
        commits.append(
            {
                "commit": full,
                "short": short,
                "authored_at": iso(authored),
                "authored": authored,
                "subject": subject,
            }
        )
    commits.sort(key=lambda item: item["authored"] or dt.datetime.min.replace(tzinfo=dt.timezone.utc))
    return commits


def analyze_group(group: dict[str, Any], window_minutes: int) -> dict[str, Any]:
    commits = git_commits_for_group(group, window_minutes)
    matched_sessions = 0
    unmatched_sessions: list[dict[str, Any]] = []
    commit_hits: Counter[str] = Counter()
    session_summaries: list[dict[str, Any]] = []
    for session in group.get("sessions") or []:
        first = session.get("first")
        last = session.get("last")
        if not first or not last:
            overlaps: list[dict[str, Any]] = []
        else:
            start = first - dt.timedelta(minutes=window_minutes)
            end = last + dt.timedelta(minutes=window_minutes)
            overlaps = [commit for commit in commits if commit.get("authored") and start <= commit["authored"] <= end]
        if overlaps:
            matched_sessions += 1
            for commit in overlaps:
                commit_hits[str(commit["short"])] += 1
        else:
            unmatched_sessions.append(session)
        session_summaries.append(
            {
                "agent": session.get("agent"),
                "session_id": session.get("session_id"),
                "risk_score": session.get("risk_score"),
                "prompt_events": session.get("prompt_events"),
                "first_ts": session.get("first_ts"),
                "last_ts": session.get("last_ts"),
                "overlap_commit_count": len(overlaps),
                "ideal_gaps": session.get("ideal_gaps") or [],
            }
        )
    commit_by_short = {str(commit["short"]): commit for commit in commits}
    top_commits = []
    for short, count in commit_hits.most_common(20):
        commit = commit_by_short.get(short) or {}
        top_commits.append(
            {
                "short": short,
                "commit": commit.get("commit"),
                "authored_at": commit.get("authored_at"),
                "subject": commit.get("subject"),
                "overlapping_sessions": count,
            }
        )
    return {
        **{key: value for key, value in group.items() if key != "sessions"},
        "commit_count_in_window": len(commits),
        "matched_sessions": matched_sessions,
        "unmatched_sessions": len(unmatched_sessions),
        "top_commits_by_overlap": top_commits,
        "top_sessions": sorted(session_summaries, key=lambda item: -int(item.get("risk_score") or 0))[:20],
        "unmatched_session_sample": [
            {
                "agent": item.get("agent"),
                "session_id": item.get("session_id"),
                "risk_score": item.get("risk_score"),
                "prompt_events": item.get("prompt_events"),
                "first_ts": item.get("first_ts"),
                "last_ts": item.get("last_ts"),
                "ideal_gaps": item.get("ideal_gaps") or [],
            }
            for item in sorted(unmatched_sessions, key=lambda value: -int(value.get("risk_score") or 0))[:20]
        ],
    }


def build_review(window_minutes: int, analyze_root_limit: int) -> dict[str, Any]:
    sessions = load_sessions()
    groups = session_groups(sessions)
    analyzed = [analyze_group(group, window_minutes) for group in groups[:analyze_root_limit]]
    gap_counts = Counter(gap for session in sessions for gap in session.get("ideal_gaps") or [])
    agent_counts = Counter(str(session.get("agent") or "unknown") for session in sessions)
    return {
        "generated_at": now_iso(),
        "source": str(FULL_STACK_REVIEW),
        "window_minutes": window_minutes,
        "counts": {
            "sessions_without_changed_refs": len(sessions),
            "root_groups": len(groups),
            "analyzed_root_limit": analyze_root_limit,
            "analyzed_roots": len(analyzed),
        },
        "agent_counts": dict(agent_counts.most_common()),
        "gap_counts": dict(gap_counts.most_common()),
        "root_summaries": [
            {key: value for key, value in group.items() if key != "sessions"} for group in groups[:80]
        ],
        "analyzed_roots": analyzed,
    }


def render_counts(items: dict[str, int], limit: int = 4) -> str:
    bits = [f"{key}:{value}" for key, value in list(items.items())[:limit]]
    if len(items) > limit:
        bits.append(f"+{len(items) - limit} more")
    return ", ".join(bits) or "none"


def render_gaps(gaps: list[list[Any]] | list[tuple[Any, Any]], limit: int = 3) -> str:
    bits = [f"{gap} ({count})" for gap, count in gaps[:limit]]
    if len(gaps) > limit:
        bits.append(f"+{len(gaps) - limit} more")
    return "; ".join(bits) or "none"


def render_doc(review: dict[str, Any], root_limit: int) -> str:
    counts = review["counts"]
    lines = [
        "# Agent Reconstruction Review",
        "",
        f"Generated: `{review['generated_at']}`",
        "",
        "## Scope",
        "",
        "- Input: private full-stack session metadata for sessions with no structured changed-file references.",
        "- Method: group by git root, map session windows to nearby commits, and record temporal reconstruction leads.",
        "- Attribution boundary: overlapping commits are review leads, not proof that a session authored the commit.",
        "- Redaction boundary: no raw prompt bodies, task bodies, or private transcript text are included here.",
        "",
        "## Coverage",
        "",
        f"- Sessions without structured changed-file refs: `{counts['sessions_without_changed_refs']}`.",
        f"- Root groups: `{counts['root_groups']}`.",
        f"- Deep-analyzed roots: `{counts['analyzed_roots']}` (cap `{counts['analyzed_root_limit']}`).",
        f"- Commit matching window: `+/-{review['window_minutes']}m` around each session window.",
        "",
        "## Agents",
        "",
        "| Agent | Sessions |",
        "|---|---:|",
    ]
    for agent, count in review.get("agent_counts", {}).items():
        lines.append(f"| `{agent}` | {count} |")
    lines.extend(["", "## Ideal-Form Gaps", "", "| Gap | Sessions |", "|---|---:|"])
    for gap, count in review.get("gap_counts", {}).items():
        lines.append(f"| {gap} | {count} |")

    lines.extend(
        [
            "",
            "## Root Queue",
            "",
            "| Rank | Root | Sessions | Agents | Risk | Prompt events | Top gaps |",
            "|---:|---|---:|---|---:|---:|---|",
        ]
    )
    for idx, group in enumerate(review.get("root_summaries", [])[:root_limit], 1):
        lines.append(
            f"| {idx} | `{relpath(group.get('git_root') or group.get('display_root'))}` | "
            f"{group.get('session_count')} | {render_counts(group.get('agents') or {})} | "
            f"{group.get('risk_score')} | {group.get('prompt_events')} | {render_gaps(group.get('top_gaps') or [])} |"
        )

    lines.extend(
        [
            "",
            "## Analyzed Roots",
            "",
            "| Root | Sessions | Commits in window | Sessions with commits | Sessions without commits | Top overlapping commits |",
            "|---|---:|---:|---:|---:|---|",
        ]
    )
    for group in review.get("analyzed_roots", []):
        top_commits = ", ".join(
            f"`{item['short']}` ({item['overlapping_sessions']})"
            for item in (group.get("top_commits_by_overlap") or [])[:5]
        )
        lines.append(
            f"| `{relpath(group.get('git_root') or group.get('display_root'))}` | "
            f"{group.get('session_count')} | {group.get('commit_count_in_window')} | "
            f"{group.get('matched_sessions')} | {group.get('unmatched_sessions')} | {top_commits or 'none'} |"
        )

    root_dot = next(
        (
            group
            for group in review.get("analyzed_roots", [])
            if group.get("git_root") and Path(str(group["git_root"])).resolve() == ROOT.resolve()
        ),
        None,
    )
    if root_dot:
        lines.extend(["", "## Limen Root Detail", ""])
        lines.append(
            f"- Root `.` has `{root_dot['session_count']}` no-change-ref sessions, "
            f"`{root_dot['commit_count_in_window']}` commits in the aggregate window, "
            f"`{root_dot['matched_sessions']}` sessions with at least one temporal commit overlap, and "
            f"`{root_dot['unmatched_sessions']}` sessions with no nearby commit."
        )
        lines.extend(["", "Top overlapping commits:", ""])
        for item in (root_dot.get("top_commits_by_overlap") or [])[:12]:
            lines.append(
                f"- `{item['short']}` overlapped `{item['overlapping_sessions']}` session windows: "
                f"{public_text(item.get('subject'))[:140]}"
            )
        lines.extend(
            [
                "",
                "Top high-risk sessions in this root:",
                "",
                "| Agent | Session | Risk | Prompts | Overlap commits | Window | Gaps |",
                "|---|---|---:|---:|---:|---|---|",
            ]
        )
        for item in (root_dot.get("top_sessions") or [])[:12]:
            gaps = "; ".join(item.get("ideal_gaps") or [])
            lines.append(
                f"| `{item.get('agent')}` | `{item.get('session_id')}` | {item.get('risk_score')} | "
                f"{item.get('prompt_events')} | {item.get('overlap_commit_count')} | "
                f"`{item.get('first_ts')}`..`{item.get('last_ts')}` | {gaps} |"
            )

    lines.extend(
        [
            "",
            "## Findings",
            "",
            "1. No-change-ref sessions are not no-work by default; many overlap real git activity, but the attribution is temporal and must be verified against prompt intent before crediting closure.",
            "2. The largest root is Limen itself, dominated by OpenCode plus Claude/Codex/Agy sessions. Its reconstruction burden is high enough that session prompts need explicit receipt targets and predicates, not broad autonomous instructions alone.",
            "3. Missing or non-git roots are a separate artifact-loss lane. Those sessions should be inspected through private transcript paths, preserved worktree receipts, or external PR/branch references before being marked absorbed.",
            "4. Sessions with no overlapping commits are likely read-only, interrupted, no-op, off-window, or failed before mutation. They should not be counted as completed implementation work without an independent receipt.",
            "",
            "## Commands",
            "",
            "- Refresh source review first: `env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-session-full-stack-review.py --write`",
            "- Refresh queue next: `env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-code-review-queue.py --write`",
            "- Refresh this reconstruction review: `env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-reconstruction-review.py --write`",
            f"- Private structured output: `{relpath(PRIVATE_REVIEW)}`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a redacted reconstruction review for no-change-ref sessions.")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--window-minutes", type=int, default=30)
    parser.add_argument("--analyze-root-limit", type=int, default=20)
    parser.add_argument("--root-table-limit", type=int, default=40)
    args = parser.parse_args()

    review = build_review(args.window_minutes, args.analyze_root_limit)
    doc = render_doc(review, args.root_table_limit)
    if args.write:
        PRIVATE_REVIEW.parent.mkdir(parents=True, exist_ok=True)
        PRIVATE_REVIEW.write_text(json.dumps(review, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        DOC_PATH.write_text(doc, encoding="utf-8")
    else:
        print(doc, end="")
    counts = review["counts"]
    print(
        "agent-reconstruction-review: "
        f"{counts['sessions_without_changed_refs']} sessions, "
        f"{counts['root_groups']} roots, "
        f"{counts['analyzed_roots']} analyzed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
