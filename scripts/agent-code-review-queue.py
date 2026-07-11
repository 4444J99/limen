#!/usr/bin/env python3
"""Build a redacted code/work-surface review queue from agent session evidence.

This does not read raw prompt bodies. It consumes the private full-stack review
JSON, which already contains prompt/session hashes, ideal-form gaps, and any
structured changed-file refs exposed by agent stores.
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
HOME = Path.home()
PRIVATE_ROOT = Path(os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus"))
FULL_STACK_REVIEW = PRIVATE_ROOT / "full-stack-review" / "agent-session-review.json"
PRIVATE_QUEUE = PRIVATE_ROOT / "full-stack-review" / "agent-code-review-queue.json"
DOC_PATH = ROOT / "docs" / "agent-code-review-queue.md"
REVIEW_LEDGER_PATH = ROOT / "docs" / "agent-code-diff-review.md"
SELF_OUTPUT_PATHS = {
    "docs/agent-code-review-queue.md",
    "scripts/agent-code-review-queue.py",
}
BACKTICKED_TOKEN_RE = re.compile(r"`([^`]+)`")
SESSION_TOKEN_RE = re.compile(r"\b(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|ses_[A-Za-z0-9]+)\b")


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def relpath(path: str | Path | None) -> str:
    if not path:
        return ""
    value = str(path).replace(str(HOME), "~")
    try:
        p = Path(path).expanduser().resolve()
        return str(p.relative_to(ROOT))
    except (OSError, ValueError):
        return value


def private_corpus_relpath(path: Path) -> str:
    parts = path.parts
    if ".limen-private" in parts:
        return str(Path(*parts[parts.index(".limen-private") :]))
    return relpath(path)


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def run_git(cwd: Path, args: list[str]) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


GIT_ROOT_CACHE: dict[str, str | None] = {}


def git_root(cwd: str | None) -> str | None:
    if not cwd:
        return None
    key = str(cwd)
    if key in GIT_ROOT_CACHE:
        return GIT_ROOT_CACHE[key]
    path = Path(cwd).expanduser()
    if not path.exists():
        GIT_ROOT_CACHE[key] = None
        return None
    root = run_git(path, ["rev-parse", "--show-toplevel"])
    GIT_ROOT_CACHE[key] = root or None
    return GIT_ROOT_CACHE[key]


def dirty_summary(root: str | None) -> dict[str, Any]:
    if not root:
        return {"state": "missing-or-non-git", "dirty_count": 0, "sample": []}
    output = run_git(Path(root), ["status", "--short", "--untracked-files=all"])
    if not output:
        return {"state": "clean-or-unreadable", "dirty_count": 0, "sample": []}
    rows = []
    for line in output.splitlines():
        path = line[3:].strip()
        if path in SELF_OUTPUT_PATHS:
            continue
        rows.append(line)
    if not rows:
        return {"state": "clean-or-self-only", "dirty_count": 0, "sample": []}
    return {"state": "dirty", "dirty_count": len(rows), "sample": rows[:12]}


def path_bucket(path: str) -> str:
    lowered = path.lower()
    base = Path(path).name.lower()
    if lowered.endswith("/tasks.yaml") or lowered == "tasks.yaml":
        return "board"
    if "/logs/" in lowered or base.endswith(".log"):
        return "logs"
    if "/studium/" in lowered:
        return "content"
    if "/tests/" in lowered or base.startswith("test_") or base.endswith("_test.py"):
        return "tests"
    if "/.github/workflows/" in lowered:
        return "ci"
    if lowered.endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".sh")):
        return "code"
    if lowered.endswith((".toml", ".yml", ".yaml", ".json", ".env.example")):
        return "config"
    if "/docs/" in lowered or lowered.endswith(".md"):
        return "docs"
    return "other"


def review_score(session: dict[str, Any], buckets: Counter[str]) -> int:
    score = int(session.get("risk_score") or 0) + min(int(session.get("changed_file_count") or 0), 50)
    score += buckets["code"] * 8 + buckets["tests"] * 7 + buckets["ci"] * 7 + buckets["config"] * 5
    score += buckets["content"] * 2 + buckets["docs"]
    gaps = set(session.get("ideal_gaps") or [])
    if "session outcome lacks verification signal" in gaps:
        score += 25
    if "session outcome lacks durable receipt signal" in gaps:
        score += 15
    if "failure/blocker language outweighs done language" in gaps:
        score += 12
    if "prompt missing executable predicate" in gaps:
        score += 8
    return score


def relative_changed_files(files: list[str], root: str | None) -> list[str]:
    out: list[str] = []
    root_path = Path(root).resolve() if root else None
    for file in files:
        p = Path(file)
        if root_path:
            try:
                out.append(str(p.resolve().relative_to(root_path)))
                continue
            except (OSError, ValueError):
                pass
        out.append(relpath(file))
    return sorted(dict.fromkeys(out))


def normalize_session(session: dict[str, Any]) -> dict[str, Any]:
    root = git_root(session.get("cwd"))
    changed_files = [str(path) for path in session.get("changed_files") or []]
    changed_rel = relative_changed_files(changed_files, root)
    buckets = Counter(path_bucket(path) for path in changed_rel)
    return {
        "agent": session.get("agent"),
        "session_id": session.get("session_id"),
        "cwd": session.get("cwd"),
        "git_root": root,
        "display_root": relpath(root or session.get("cwd")),
        "first_ts": session.get("first_ts"),
        "last_ts": session.get("last_ts"),
        "prompt_events": int(session.get("prompt_events") or 0),
        "risk_score": int(session.get("risk_score") or 0),
        "review_score": review_score(session, buckets),
        "ideal_gaps": session.get("ideal_gaps") or [],
        "changed_file_count": int(session.get("changed_file_count") or 0),
        "changed_files": changed_rel,
        "buckets": dict(sorted(buckets.items())),
        "outcome": session.get("outcome") or {},
    }


def command_for_session(item: dict[str, Any], *, max_paths: int = 4) -> str:
    root = item.get("git_root") or item.get("cwd")
    if not root:
        return "reconstruct from private session row"
    parts = ["git", "-C", relpath(root), "log"]
    if item.get("first_ts"):
        parts.append(f"--since={item['first_ts']}")
    if item.get("last_ts"):
        parts.append(f"--until={item['last_ts']}")
    parts.extend(["--stat", "--oneline", "--"])
    parts.extend((item.get("changed_files") or [])[:max_paths])
    return " ".join(parts)


def command_for_root(item: dict[str, Any]) -> str:
    root = item.get("git_root")
    if not root:
        return "no git root; inspect private session paths and outcome receipts"
    first = item.get("first_ts")
    last = item.get("last_ts")
    parts = ["git", "-C", relpath(root), "log"]
    if first:
        parts.append(f"--since={first}")
    if last:
        parts.append(f"--until={last}")
    parts.extend(["--stat", "--oneline"])
    return " ".join(parts)


def build_queue(review: dict[str, Any]) -> dict[str, Any]:
    sessions = [item for item in review.get("sessions") or [] if isinstance(item, dict)]
    normalized = [normalize_session(session) for session in sessions]
    structured = [item for item in normalized if item["changed_file_count"] > 0]
    board_only = [item for item in structured if item["buckets"] and set(item["buckets"]).issubset({"board", "logs"})]
    changed_review = [
        item for item in structured if item["buckets"] and not set(item["buckets"]).issubset({"board", "logs"})
    ]
    changed_review.sort(key=lambda item: (-item["review_score"], -item["changed_file_count"], str(item["session_id"])))
    board_only.sort(key=lambda item: (-item["review_score"], str(item["session_id"])))

    grouped: dict[str, dict[str, Any]] = {}
    for item in normalized:
        if item["changed_file_count"] > 0 or item["risk_score"] <= 0:
            continue
        key = item.get("git_root") or item.get("cwd") or "unknown"
        bucket = grouped.setdefault(
            key,
            {
                "git_root": item.get("git_root"),
                "display_root": item.get("display_root") or "unknown",
                "sessions": [],
                "agents": Counter(),
                "gaps": Counter(),
                "risk_score": 0,
                "prompt_events": 0,
                "first_ts": item.get("first_ts"),
                "last_ts": item.get("last_ts"),
            },
        )
        bucket["sessions"].append(item)
        bucket["agents"][str(item.get("agent") or "unknown")] += 1
        bucket["risk_score"] += int(item.get("risk_score") or 0)
        bucket["prompt_events"] += int(item.get("prompt_events") or 0)
        for gap in item.get("ideal_gaps") or []:
            bucket["gaps"][gap] += 1
        if item.get("first_ts") and (not bucket.get("first_ts") or item["first_ts"] < bucket["first_ts"]):
            bucket["first_ts"] = item["first_ts"]
        if item.get("last_ts") and (not bucket.get("last_ts") or item["last_ts"] > bucket["last_ts"]):
            bucket["last_ts"] = item["last_ts"]

    reconstruct = []
    for bucket in grouped.values():
        sessions_by_risk = sorted(bucket["sessions"], key=lambda item: -item["risk_score"])
        root = bucket.get("git_root")
        record = {
            "display_root": bucket["display_root"],
            "git_root": root,
            "session_count": len(bucket["sessions"]),
            "agents": dict(bucket["agents"].most_common()),
            "risk_score": bucket["risk_score"],
            "prompt_events": bucket["prompt_events"],
            "top_gaps": bucket["gaps"].most_common(5),
            "first_ts": bucket["first_ts"],
            "last_ts": bucket["last_ts"],
            "top_sessions": [
                {
                    "agent": item["agent"],
                    "session_id": item["session_id"],
                    "risk_score": item["risk_score"],
                    "prompt_events": item["prompt_events"],
                    "ideal_gaps": item["ideal_gaps"],
                }
                for item in sessions_by_risk[:8]
            ],
            "dirty": dirty_summary(root),
        }
        record["command"] = command_for_root(record)
        reconstruct.append(record)
    reconstruct.sort(key=lambda item: (-item["risk_score"], -item["session_count"], item["display_root"]))

    bucket_totals = Counter()
    for item in structured:
        bucket_totals.update(item["buckets"])
    return {
        "generated_at": now_iso(),
        "source": str(FULL_STACK_REVIEW),
        "counts": {
            "sessions": len(sessions),
            "structured_changed_file_sessions": len(structured),
            "changed_file_review_candidates": len(changed_review),
            "board_or_log_only_sessions": len(board_only),
            "reconstruction_roots": len(reconstruct),
        },
        "bucket_totals": dict(bucket_totals.most_common()),
        "changed_review": changed_review,
        "board_only": board_only,
        "reconstruct": reconstruct,
    }


def gap_text(gaps: list[str], limit: int = 3) -> str:
    return "; ".join(gaps[:limit]) or "none"


def paths_text(paths: list[str], limit: int = 5) -> str:
    shown = paths[:limit]
    suffix = "" if len(paths) <= limit else f"<br>... +{len(paths) - limit} more"
    return "<br>".join(f"`{path}`" for path in shown) + suffix


def render_markdown(queue: dict[str, Any]) -> str:
    counts = queue["counts"]
    lines = [
        "# Agent Code Review Queue",
        "",
        f"Generated: `{queue['generated_at']}`",
        "",
        "## Scope",
        "",
        "- Input: private full-stack session review metadata; no raw prompt bodies are read or printed.",
        "- Purpose: rank where human/code review should inspect actual work against the prompt/session ideal diff.",
        "- Split: structured changed-file sessions first; sessions without changed-file refs require git-window reconstruction.",
        "",
        "## Counts",
        "",
        f"- Sessions reviewed: `{counts['sessions']}`.",
        f"- Structured changed-file sessions: `{counts['structured_changed_file_sessions']}`.",
        f"- Immediate changed-file review candidates: `{counts['changed_file_review_candidates']}`.",
        f"- Board/log-only sessions: `{counts['board_or_log_only_sessions']}`.",
        f"- Reconstruction roots: `{counts['reconstruction_roots']}`.",
        "",
        "## Changed-File Buckets",
        "",
        "| Bucket | Files |",
        "|---|---:|",
    ]
    for bucket, count in queue["bucket_totals"].items():
        lines.append(f"| `{bucket}` | {count} |")

    lines.extend(
        [
            "",
            "## Immediate Changed-File Review",
            "",
            "| Rank | Agent | Session | Score | Files | Buckets | Gaps | First Paths | Start Command |",
            "|---:|---|---|---:|---:|---|---|---|---|",
        ]
    )
    for idx, item in enumerate(queue["changed_review"][:30], 1):
        buckets = ", ".join(f"{k}:{v}" for k, v in item["buckets"].items()) or "none"
        lines.append(
            f"| {idx} | `{item['agent']}` | `{item['session_id']}` | {item['review_score']} | "
            f"{item['changed_file_count']} | {buckets} | {gap_text(item['ideal_gaps'])} | "
            f"{paths_text(item['changed_files'])} | `{command_for_session(item)}` |"
        )

    lines.extend(
        [
            "",
            "## Board/Log Churn Queue",
            "",
            "These are not code correctness reviews; they are task-board/governance receipt reviews.",
            "",
            "| Rank | Agent | Session | Score | Files | Gaps | Paths |",
            "|---:|---|---|---:|---:|---|---|",
        ]
    )
    for idx, item in enumerate(queue["board_only"][:20], 1):
        lines.append(
            f"| {idx} | `{item['agent']}` | `{item['session_id']}` | {item['review_score']} | "
            f"{item['changed_file_count']} | {gap_text(item['ideal_gaps'])} | {paths_text(item['changed_files'])} |"
        )

    lines.extend(
        [
            "",
            "## Reconstruction Queue",
            "",
            "These sessions have prompts/outcome text but no structured changed-file refs. Review starts by reconstructing the git window for the root.",
            "",
            "| Rank | Root | Sessions | Agents | Risk | Dirty | Top Gaps | Start Command |",
            "|---:|---|---:|---|---:|---|---|---|",
        ]
    )
    for idx, item in enumerate(queue["reconstruct"][:30], 1):
        agents = ", ".join(f"{agent}:{count}" for agent, count in item["agents"].items())
        gaps = "; ".join(f"{gap} ({count})" for gap, count in item["top_gaps"][:3]) or "none"
        dirty = item["dirty"]
        dirty_text = f"{dirty['state']}:{dirty['dirty_count']}"
        lines.append(
            f"| {idx} | `{item['display_root']}` | {item['session_count']} | {agents} | "
            f"{item['risk_score']} | {dirty_text} | {gaps} | `{item['command']}` |"
        )

    lines.extend(
        [
            "",
            "## Findings",
            "",
            "1. Changed-file extraction is now multi-surface: OpenCode contributes native SQLite diffs, Codex/Claude contribute conservative patch/edit/write tool paths, and Agy contributes conservative CLI `TargetFile` tool paths when present.",
            "2. `tasks.yaml` churn is a separate governance review path and should not be treated as product/code implementation without a matching task-state receipt.",
            "3. The highest immediate code-review candidates mix code, tests, CI, config, and docs with missing predicate/receipt signals; review should start there before broad prompt-pressure sessions.",
            "4. Broad Claude/Codex sessions remain high risk, but the next move is root-level reconstruction, not reading more prompt text.",
            "",
            "## Commands",
            "",
            "- Refresh full-stack source first: `env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-session-full-stack-review.py --write`",
            "- Refresh this queue: `env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-code-review-queue.py --write`",
            "- Check the executable depth stop predicate: `env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-code-review-queue.py --depth-stop-predicate --review-score-floor 100`",
            f"- Private structured queue: `{private_corpus_relpath(PRIVATE_QUEUE)}`",
        ]
    )
    return "\n".join(lines) + "\n"


def reviewed_tokens_from_doc(text: str) -> set[str]:
    """Return public row/session tokens from the tracked review ledger.

    The review ledger intentionally keeps prompt bodies private, but session ids
    are public row keys. Matching queue session ids against explicit
    session-shaped tokens keeps this predicate robust even when fenced code
    blocks make naive Markdown backtick parsing ambiguous. Backticked tokens are
    still included for table labels such as ``changed 147`` and ``refreshed 35``.
    """

    return {match.group(1) for match in BACKTICKED_TOKEN_RE.finditer(text)} | {
        match.group(0) for match in SESSION_TOKEN_RE.finditer(text)
    }


def depth_queue_rows(queue: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for section in ("changed_review", "board_only"):
        for item in queue.get(section) or []:
            if isinstance(item, dict) and item.get("session_id"):
                rows.append(item)
    rows.sort(
        key=lambda item: (
            -int(item.get("review_score") or 0),
            -int(item.get("changed_file_count") or 0),
            str(item.get("session_id") or ""),
        )
    )
    return rows


def depth_stop_status(
    queue: dict[str, Any],
    review_doc_text: str,
    *,
    review_score_floor: int,
    max_open: int,
    sample_limit: int = 10,
) -> dict[str, Any]:
    reviewed = reviewed_tokens_from_doc(review_doc_text)
    eligible = [row for row in depth_queue_rows(queue) if int(row.get("review_score") or 0) >= review_score_floor]
    open_rows = [row for row in eligible if str(row.get("session_id")) not in reviewed]
    next_rows = [
        {
            "agent": row.get("agent"),
            "session_id": row.get("session_id"),
            "review_score": int(row.get("review_score") or 0),
            "changed_file_count": int(row.get("changed_file_count") or 0),
            "ideal_gaps": list(row.get("ideal_gaps") or [])[:3],
            "command": command_for_session(row),
        }
        for row in open_rows[:sample_limit]
    ]
    return {
        "passed": len(open_rows) <= max_open,
        "review_score_floor": review_score_floor,
        "max_open": max_open,
        "eligible_count": len(eligible),
        "reviewed_count": len(eligible) - len(open_rows),
        "open_count": len(open_rows),
        "next": next_rows,
    }


def print_depth_stop_status(status: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(status, indent=2, sort_keys=True))
        return
    state = "passed" if status["passed"] else "blocked"
    print(
        "agent-code-review-depth-stop: "
        f"{state}; {status['open_count']} open of {status['eligible_count']} "
        f"eligible rows at review_score>={status['review_score_floor']} "
        f"(max_open={status['max_open']})"
    )
    for row in status.get("next") or []:
        print(
            "- "
            f"{row.get('agent')} {row.get('session_id')} "
            f"score={row.get('review_score')} files={row.get('changed_file_count')}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write tracked markdown and private JSON")
    parser.add_argument(
        "--depth-stop-predicate",
        action="store_true",
        help="exit 0 only when the tracked depth ledger has reviewed all queue rows above the score floor",
    )
    parser.add_argument("--review-score-floor", type=int, default=100)
    parser.add_argument("--max-open", type=int, default=0)
    parser.add_argument("--json", action="store_true", help="emit machine-readable output for predicate mode")
    args = parser.parse_args()

    if args.depth_stop_predicate:
        review = load_json(FULL_STACK_REVIEW)
        queue = build_queue(review) if review else {}
        if not queue.get("counts"):
            queue = load_json(PRIVATE_QUEUE)
        if not queue.get("counts"):
            print("agent-code-review-depth-stop: missing private queue/source review", flush=True)
            return 2
        status = depth_stop_status(
            queue,
            REVIEW_LEDGER_PATH.read_text(encoding="utf-8", errors="replace") if REVIEW_LEDGER_PATH.exists() else "",
            review_score_floor=args.review_score_floor,
            max_open=args.max_open,
        )
        print_depth_stop_status(status, as_json=args.json)
        return 0 if status["passed"] else 1

    review = load_json(FULL_STACK_REVIEW)
    queue = build_queue(review)
    if args.write:
        PRIVATE_QUEUE.parent.mkdir(parents=True, exist_ok=True)
        PRIVATE_QUEUE.write_text(json.dumps(queue, indent=2, sort_keys=True), encoding="utf-8")
        DOC_PATH.write_text(render_markdown(queue), encoding="utf-8")
    print(
        "agent-code-review-queue: "
        f"{queue['counts']['changed_file_review_candidates']} changed-file candidates, "
        f"{queue['counts']['reconstruction_roots']} reconstruction roots"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
