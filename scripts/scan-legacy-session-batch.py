#!/usr/bin/env python3
"""Build a metadata-only scan for a legacy prompt review batch.

The scanner reads private Claude JSONL files, but it only writes derived
metadata: session keys, source existence, cwd/branch names, public GitHub
anchors, event/tool counts, and keyword counts. It intentionally never writes
prompt, assistant, tool-result, or attachment text.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
PRIORITY_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-priority-map.json"
SESSION_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
OUTPUT_DIR = PRIVATE_ROOT / "lifecycle" / "legacy-session-scans"

GITHUB_ANCHOR_RE = re.compile(
    r"https://github\\.com/"
    r"(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)/"
    r"(?P<kind>pull|issues)/(?P<number>\\d+)"
)
REPO_REF_RE = re.compile(
    r"\\b(?P<owner>organvm(?:-[a-z0-9-]+)?|a-organvm|4444J99)/"
    r"(?P<repo>[A-Za-z0-9_.-]+)\\b"
)
SENSITIVE_PATTERNS = {
    "account": re.compile(r"\\b(account|login|email address|username)\\b", re.I),
    "billing": re.compile(r"\\b(billing|invoice|subscription|payment|stripe|gumroad)\\b", re.I),
    "credential": re.compile(r"\\b(secret|token|api[_ -]?key|password|credential|bearer)\\b", re.I),
    "financial": re.compile(r"\\b(bank|card|payout|revenue|income|fraud|santander)\\b", re.I),
    "health": re.compile(r"\\b(health|medical|clinical|diagnosis|patient)\\b", re.I),
    "private": re.compile(r"\\b(private|confidential|personal)\\b", re.I),
}
SAFE_STRING_KEYS = {"cwd", "gitBranch", "type", "userType", "entrypoint", "sessionKind"}
LOCAL_WORKTREE_BASES = [
    Path("/Users/4jp/Workspace/.limen-worktrees"),
    ROOT / ".worktrees",
    ROOT / ".claude" / "worktrees",
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def iter_strings(value: Any) -> Any:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from iter_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_strings(child)


def content_has_prompt_text(obj: dict[str, Any]) -> bool:
    return "message" in obj or "attachment" in obj or "toolUseResult" in obj


def extract_tool_names(value: Any, names: Counter[str]) -> None:
    if isinstance(value, dict):
        if value.get("type") == "tool_use" and value.get("name"):
            names[str(value["name"])] += 1
        if value.get("commandName"):
            names[str(value["commandName"])] += 1
        for child in value.values():
            extract_tool_names(child, names)
    elif isinstance(value, list):
        for child in value:
            extract_tool_names(child, names)


def owner_lane_for_cwd(cwd: str) -> str:
    if not cwd:
        return "legacy-session-unknown"
    if cwd.startswith("/Volumes/Archive4T"):
        return "archive4t-estate-subagent-cluster"
    marker = "/.claude/worktrees/"
    if marker in cwd:
        return "limen-subagent-" + cwd.split(marker, 1)[1].split("/", 1)[0]
    if cwd.rstrip("/") == str(ROOT):
        return "limen-root-subagent-cluster"
    if cwd.startswith(str(ROOT)):
        return "limen-local-project"
    return "external-local-project"


def local_worktree_hits(cwd: str) -> list[str]:
    marker = "/.claude/worktrees/"
    if marker not in cwd:
        return []
    slug = cwd.split(marker, 1)[1].split("/", 1)[0]
    hits = []
    for base in LOCAL_WORKTREE_BASES:
        candidate = base / slug
        if candidate.exists():
            hits.append(str(candidate))
    return hits


def public_anchors_from_strings(strings: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    anchors = {}
    repos = set()
    for text in strings:
        for match in GITHUB_ANCHOR_RE.finditer(text):
            owner = match.group("owner")
            repo = match.group("repo")
            kind = match.group("kind")
            number = int(match.group("number"))
            url = f"https://github.com/{owner}/{repo}/{kind}/{number}"
            anchors[url] = {
                "url": url,
                "repo": f"{owner}/{repo}",
                "kind": "pr" if kind == "pull" else "issue",
                "number": number,
            }
            repos.add(f"{owner}/{repo}")
        for match in REPO_REF_RE.finditer(text):
            repos.add(f"{match.group('owner')}/{match.group('repo')}")
    return sorted(anchors.values(), key=lambda row: row["url"]), sorted(repos)


def scan_source(path: Path) -> dict[str, Any]:
    event_types: Counter[str] = Counter()
    top_keys: Counter[str] = Counter()
    branches: Counter[str] = Counter()
    cwds: Counter[str] = Counter()
    tool_names: Counter[str] = Counter()
    keyword_counts: Counter[str] = Counter()
    public_strings: list[str] = []
    line_count = 0
    prompt_text_bearing_events = 0
    malformed_lines = 0

    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line_count += 1
            try:
                obj = json.loads(line)
            except ValueError:
                malformed_lines += 1
                continue
            if not isinstance(obj, dict):
                continue
            top_keys.update(str(key) for key in obj.keys())
            event_types[str(obj.get("type") or "unknown")] += 1
            if obj.get("cwd"):
                cwds[str(obj["cwd"])] += 1
            if obj.get("gitBranch"):
                branches[str(obj["gitBranch"])] += 1
            if content_has_prompt_text(obj):
                prompt_text_bearing_events += 1
            extract_tool_names(obj, tool_names)
            strings = list(iter_strings(obj))
            public_strings.extend(strings)
            for text in strings:
                for name, pattern in SENSITIVE_PATTERNS.items():
                    keyword_counts[name] += len(pattern.findall(text))

    anchors, repos = public_anchors_from_strings(public_strings)
    cwd_values = [value for value, _ in cwds.most_common()]
    primary_cwd = cwd_values[0] if cwd_values else ""
    branch_values = [value for value, _ in branches.most_common()]
    return {
        "source_exists": path.exists(),
        "line_count": line_count,
        "malformed_lines": malformed_lines,
        "event_types": dict(event_types.most_common()),
        "top_level_keys": dict(top_keys.most_common()),
        "prompt_text_bearing_events": prompt_text_bearing_events,
        "cwd_values": cwd_values,
        "owner_lane": owner_lane_for_cwd(primary_cwd),
        "git_branches": branch_values,
        "local_worktree_hits": local_worktree_hits(primary_cwd),
        "tool_names": dict(tool_names.most_common()),
        "public_github_anchors": anchors,
        "repo_refs": repos,
        "sensitive_keyword_counts": dict(keyword_counts.most_common()),
    }


def batch_by_id(priority: dict[str, Any], batch_id: str) -> dict[str, Any]:
    for batch in priority.get("review_batches") or []:
        if isinstance(batch, dict) and batch.get("id") == batch_id:
            return batch
    raise SystemExit(f"batch not found: {batch_id}")


def build_scan(batch_id: str) -> dict[str, Any]:
    priority = load_json(PRIORITY_INDEX)
    session_index = load_json(SESSION_INDEX)
    sessions = {
        str(row.get("session_key")): row
        for row in session_index.get("sessions") or []
        if isinstance(row, dict) and row.get("session_key")
    }
    batch = batch_by_id(priority, batch_id)
    rows = []
    duplicate_counts = Counter(str(key) for key in batch.get("session_keys") or [])
    for session_key in batch.get("session_keys") or []:
        key = str(session_key)
        session = sessions.get(key)
        if not session:
            rows.append({"session_key": key, "source_exists": False, "missing_index_row": True})
            continue
        path = Path(str(session.get("path") or ""))
        source_scan = scan_source(path) if path.exists() else {"source_exists": False}
        rows.append(
            {
                "root": f"legacy-session-{key}",
                "session_key": key,
                "source": session.get("source"),
                "source_exists": path.exists(),
                "display_path": session.get("display_path"),
                "event_count": int(session.get("event_count") or 0),
                "prompt_event_count": int(session.get("prompt_event_count") or 0),
                "unique_prompt_hashes": len(set(session.get("prompt_hashes") or [])),
                "duplicate_count": int(duplicate_counts[key]),
                **source_scan,
            }
        )
    status_counts = Counter("source_exists" if row.get("source_exists") else "source_missing" for row in rows)
    owner_lanes = Counter(str(row.get("owner_lane") or "unknown") for row in rows)
    repo_refs = Counter(repo for row in rows for repo in (row.get("repo_refs") or []))
    anchor_kinds = Counter(
        anchor.get("kind") for row in rows for anchor in (row.get("public_github_anchors") or [])
    )
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    return {
        "generated_at": now,
        "batch": batch_id,
        "privacy": {
            "raw_prompt_text_written": False,
            "raw_assistant_text_written": False,
            "raw_tool_result_text_written": False,
            "public_github_urls_written": True,
        },
        "batch_summary": {
            "band": batch.get("band"),
            "lane": batch.get("lane"),
            "session_count": int(batch.get("session_count") or 0),
            "prompt_events": int(batch.get("prompt_events") or 0),
            "unique_prompt_hashes": int(batch.get("unique_prompt_hashes") or 0),
            "source_counts": batch.get("sources") or {},
            "family_counts": batch.get("families") or {},
            "status_counts": dict(status_counts.most_common()),
            "owner_lanes": dict(owner_lanes.most_common()),
            "repo_refs": dict(repo_refs.most_common()),
            "anchor_kinds": dict(anchor_kinds.most_common()),
            "duplicate_session_keys": {
                key: count for key, count in duplicate_counts.items() if count > 1
            },
        },
        "sessions": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan a legacy prompt batch without writing raw text.")
    parser.add_argument("batch_id")
    parser.add_argument("--write", action="store_true", help="write private scan JSON")
    args = parser.parse_args()
    scan = build_scan(args.batch_id)
    if args.write:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output = OUTPUT_DIR / f"{args.batch_id}.json"
        output.write_text(json.dumps(scan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {output}")
    print(
        "legacy-session-scan: "
        f"{scan['batch']} "
        f"{scan['batch_summary']['session_count']} sessions, "
        f"{scan['batch_summary']['prompt_events']} prompt events, "
        f"anchors {scan['batch_summary']['anchor_kinds']}, "
        f"owner lanes {len(scan['batch_summary']['owner_lanes'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
