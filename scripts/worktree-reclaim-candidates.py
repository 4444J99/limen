#!/usr/bin/env python3
"""Emit human-acceptance packets for safe-looking worktree reclamation.

This script is deliberately non-destructive. It turns the current
`worktree_debt_report()` view into a bounded candidate packet so the owner can
accept exact roots instead of manually translating "missing acceptance" skips.
It never writes `docs/worktree-reclaim-acceptance.jsonl`.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

CODE_ROOT = Path(__file__).resolve().parents[1]
STATE_ROOT = Path(os.environ.get("LIMEN_STATE_ROOT", os.environ.get("LIMEN_ROOT", CODE_ROOT))).expanduser().resolve()


def writable_output_root() -> Path:
    explicit = os.environ.get("LIMEN_OUTPUT_ROOT")
    if explicit:
        return Path(explicit).expanduser().resolve()
    env_root = os.environ.get("LIMEN_ROOT")
    if env_root:
        candidate = Path(env_root).expanduser()
        docs = candidate / "docs"
        if os.access(candidate, os.W_OK) and (docs.exists() or os.access(candidate, os.W_OK)):
            return candidate.resolve()
    return CODE_ROOT


OUTPUT_ROOT = writable_output_root()
sys.path.insert(0, str(CODE_ROOT / "cli" / "src"))

from limen.worktree_debt import WorktreeDebtReport, worktree_debt_report  # noqa: E402
from limen.capacity import PAID_AGENT_ORDER  # noqa: E402

DOC_PATH = OUTPUT_ROOT / "docs" / "worktree-reclaim-candidates.md"
JSON_PATH = OUTPUT_ROOT / "docs" / "worktree-reclaim-candidates.json"
VALUE_REPOS = STATE_ROOT / "value-repos.json"
SCORE_LEDGER = STATE_ROOT / "logs" / "ledger.jsonl"
ACCEPTANCE_LEDGER = OUTPUT_ROOT / "docs" / "worktree-reclaim-acceptance.jsonl"
SAFE_REASONS = {"clean+merged+idle"}
WORKTREE_LIFECYCLE_SCORE = 32


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fmt_bytes(n: int | None) -> str:
    if n is None:
        return "not measured"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    value = float(n)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{n} B"


def measure_size(path: str, timeout: int = 90) -> int | None:
    try:
        proc = subprocess.run(["du", "-sk", path], capture_output=True, text=True, timeout=timeout)
        if proc.returncode == 0 and proc.stdout.strip():
            return int(proc.stdout.split()[0]) * 1024
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    return None


def load_report(path: Path | None) -> WorktreeDebtReport:
    if path is None:
        cached = load_cached_candidate_packet()
        if cached is not None:
            return cached
        with estate_scan_env():
            return worktree_debt_report(STATE_ROOT)
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "total": int(data.get("total", 0)),
        "debt": int(data.get("debt", 0)),
        "by_reason": dict(data.get("by_reason") or {}),
        "items": list(data.get("items") or []),
    }


def load_cached_candidate_packet() -> WorktreeDebtReport | None:
    if STATE_ROOT == OUTPUT_ROOT:
        return None
    path = STATE_ROOT / "docs" / "worktree-reclaim-candidates.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if data.get("schema") != "limen.worktree_reclaim_candidates.v1":
        return None
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return None
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    items = [
        {
            "name": str(row.get("name") or Path(str(row.get("path") or "")).name),
            "path": str(row.get("path") or ""),
            "reason": str(row.get("reason") or "clean+merged+idle"),
            "debt": False,
            "size_bytes": row.get("size_bytes"),
        }
        for row in candidates
        if isinstance(row, dict) and row.get("path")
    ]
    if not items:
        return None
    return {
        "total": int(summary.get("scanned_roots") or len(items)),
        "debt": int(summary.get("debt_roots") or 0),
        "by_reason": dict(data.get("by_reason") or {"clean+merged+idle": len(items)}),
        "items": items,
    }


def path_contains(parent: Path, child: Path) -> bool:
    try:
        child.expanduser().resolve().relative_to(parent.expanduser().resolve())
        return True
    except (OSError, ValueError):
        return False


@contextmanager
def estate_scan_env():
    """Ignore a dispatch-lane worktree root when scanning the durable estate."""
    key = "LIMEN_WORKTREE_ROOT"
    current = os.environ.get(key)
    should_unset = bool(current and path_contains(Path(current), OUTPUT_ROOT) and STATE_ROOT != OUTPUT_ROOT)
    if not should_unset:
        yield
        return
    try:
        del os.environ[key]
        yield
    finally:
        os.environ[key] = current


def load_value_repos(path: Path = VALUE_REPOS) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    repos = data.get("repos") if isinstance(data, dict) else []
    if not isinstance(repos, list):
        return []
    return [str(repo) for repo in repos if str(repo).strip()]


def score_dispatch_summary(path: Path = SCORE_LEDGER, *, tail: int = 2000) -> dict[str, Any]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-tail:]
    except OSError:
        return {"ledger_present": False, "records_sampled": 0, "by_grade": {}, "sunk": 0}
    by_grade: dict[str, int] = {}
    sunk = 0
    sampled = 0
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        sampled += 1
        grade = str(row.get("grade") or "unknown")
        by_grade[grade] = by_grade.get(grade, 0) + 1
        try:
            sunk += int(row.get("sunk") or 0)
        except (TypeError, ValueError):
            pass
    return {"ledger_present": True, "records_sampled": sampled, "by_grade": by_grade, "sunk": sunk}


def governance_context(
    *,
    value_repos: list[str] | None = None,
    score_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    repos = value_repos if value_repos is not None else load_value_repos()
    return {
        "decision": "allowed-candidate-packet-only",
        "why_allowed": (
            "Limen is value-tier and worktree_lifecycle is the top prompt attack-path family; "
            "the action is non-destructive packetization, not local deletion."
        ),
        "why_not_auto_delete": (
            "scripts/reclaim-worktrees.py --apply removes only the merged loss-free class "
            "(clean+merged+idle) under "
            "the operator standing grant standing-grant-2026-07-09 (docs/removal-acceptance-covenant.md "
            "§Standing grant; disable with LIMEN_RECLAIM_STANDING_ACCEPTANCE=0); every other class still "
            "requires a matching human acceptance/redaction/archive proof event in "
            "docs/worktree-reclaim-acceptance.jsonl."
        ),
        "repo": "organvm/limen",
        "repo_in_value_tier": "organvm/limen" in set(repos),
        "value_repo_count": len(repos),
        "prompt_attack_path": {
            "family": "worktree_lifecycle",
            "score": WORKTREE_LIFECYCLE_SCORE,
            "agent": "codex/openCode",
            "source": "scripts/session-attack-paths.py",
        },
        "agent_policy": {
            "candidate_packet_lane": "codex-conductor",
            "destructive_cleanup_lane": "standing-grant-or-human-acceptance-then-reclaim-worktrees",
            "canonical_vendor_order": list(PAID_AGENT_ORDER),
            "single_writer_boundary": "do not write tasks.yaml or acceptance ledgers as a shortcut from this script",
        },
        "spend_score": score_summary if score_summary is not None else score_dispatch_summary(),
        "authority_sources": [
            "value-repos.json",
            "cli/src/limen/census.py",
            "cli/src/limen/capacity.py",
            "cli/src/limen/model_selection.py",
            "scripts/score-dispatch.py",
            "scripts/session-attack-paths.py",
            "scripts/reclaim-worktrees.py",
            "docs/worktree-reclaim-acceptance.md",
        ],
    }


def reclaim_action(path: str) -> str:
    git_path = Path(path) / ".git"
    return "remove-worktree" if git_path.is_file() else "remove-clone"


def acceptance_event(row: dict[str, Any], accepted_at: str = "<ISO-8601-UTC>") -> dict[str, Any]:
    return {
        "accepted_at": accepted_at,
        "root": row["name"],
        "path": row["path"],
        "accepted": True,
        "action": row["action"],
        "reason": row["reason"],
        "archive_status": "not_required_clean_merged_remote",
        "archive_proof": (
            "worktree debt classified this root clean+merged+idle; "
            "HEAD/content is already preserved on the remote lifecycle"
        ),
        "redaction_review": "not_required_remote_only",
        "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle",
    }


def candidate_rows(
    report: WorktreeDebtReport,
    *,
    limit: int,
    measure: bool,
    size_scan_limit: int,
    size_timeout_sec: int = 10,
    size_budget_sec: int = 60,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in report.get("items", []):
        if item.get("debt") is True:
            continue
        if item.get("reason") not in SAFE_REASONS:
            continue
        path = str(item.get("path") or "")
        if not path:
            continue
        rows.append(
            {
                "name": str(item.get("name") or Path(path).name),
                "path": path,
                "reason": str(item.get("reason")),
                "action": reclaim_action(path),
                "size_bytes": item.get("size_bytes"),
            }
        )

    if measure:
        started = time.monotonic()
        for row in rows[: max(0, size_scan_limit)]:
            if row.get("size_bytes") is not None:
                continue
            if time.monotonic() - started >= max(0, size_budget_sec):
                break
            row["size_bytes"] = measure_size(row["path"], timeout=max(1, size_timeout_sec))
        rows.sort(key=lambda row: (row["size_bytes"] is not None, row["size_bytes"] or 0, row["name"]), reverse=True)
    else:
        rows.sort(key=lambda row: row["name"])

    bounded = rows[:limit]
    for row in bounded:
        row["acceptance_event_template"] = acceptance_event(row)
    return bounded


def build_packet(
    report: WorktreeDebtReport,
    *,
    generated_at: str,
    limit: int,
    measure: bool,
    size_scan_limit: int,
    size_timeout_sec: int = 10,
    size_budget_sec: int = 60,
) -> dict[str, Any]:
    rows = candidate_rows(
        report,
        limit=limit,
        measure=measure,
        size_scan_limit=size_scan_limit,
        size_timeout_sec=size_timeout_sec,
        size_budget_sec=size_budget_sec,
    )
    measured = [row["size_bytes"] for row in rows if row.get("size_bytes") is not None]
    total_measured = sum(int(value) for value in measured)
    return {
        "schema": "limen.worktree_reclaim_candidates.v1",
        "generated_at": generated_at,
        "status": "candidate_packet_only",
        "destructive_cleanup_performed": False,
        "acceptance_ledger_written": False,
        "governance": governance_context(),
        "acceptance_ledger": str(ACCEPTANCE_LEDGER),
        "summary": {
            "scanned_roots": report["total"],
            "debt_roots": report["debt"],
            "clean_merged_idle_roots": int(report.get("by_reason", {}).get("clean+merged+idle", 0)),
            "pushed_unmerged_roots": int(report.get("by_reason", {}).get("not-merged-to-default", 0)),
            "candidate_roots": len(rows),
            "candidate_limit": limit,
            "size_measured": bool(measure),
            "size_scan_limit": size_scan_limit,
            "size_timeout_sec": size_timeout_sec,
            "size_budget_sec": size_budget_sec,
            "measured_roots": len(measured),
            "measured_candidate_bytes": total_measured,
            "measured_candidate_size": fmt_bytes(total_measured) if measured else "not measured",
        },
        "by_reason": dict(sorted(report.get("by_reason", {}).items())),
        "candidates": rows,
        "next_command_after_acceptance": "python3 scripts/reclaim-worktrees.py --apply --force",
    }


def render_markdown(packet: dict[str, Any]) -> str:
    summary = packet["summary"]
    lines = [
        "# Worktree Reclaim Candidates",
        "",
        f"Generated: `{packet['generated_at']}`",
        "",
        "This is a candidate packet, not acceptance. It does not write",
        "`docs/worktree-reclaim-acceptance.jsonl` and it does not delete roots.",
        "",
        "## Summary",
        "",
        f"- Scanned roots: `{summary['scanned_roots']}`",
        f"- Debt roots: `{summary['debt_roots']}`",
        f"- Clean merged idle roots available: `{summary['clean_merged_idle_roots']}`",
        f"- Pushed but unmerged roots retained: `{summary['pushed_unmerged_roots']}`",
        f"- Candidate roots in this packet: `{summary['candidate_roots']}`",
        f"- Measured candidate size: `{summary['measured_candidate_size']}`",
        "",
        "## Authority Gate",
        "",
        f"- Decision: `{packet['governance']['decision']}`",
        f"- Repo in value tier: `{str(packet['governance']['repo_in_value_tier']).lower()}`",
        f"- Prompt family: `{packet['governance']['prompt_attack_path']['family']}` "
        f"score `{packet['governance']['prompt_attack_path']['score']}`",
        f"- Candidate lane: `{packet['governance']['agent_policy']['candidate_packet_lane']}`",
        f"- Delete gate: `{packet['governance']['agent_policy']['destructive_cleanup_lane']}`",
        "",
        "Authority sources: " + ", ".join(f"`{source}`" for source in packet["governance"]["authority_sources"]),
        "",
        "## Acceptance Flow",
        "",
        "1. Review the roots below.",
        "2. Copy only the explicitly accepted JSON objects into `docs/worktree-reclaim-acceptance.jsonl`.",
        "3. Replace `<ISO-8601-UTC>` with the current UTC timestamp.",
        "4. Run `python3 scripts/reclaim-worktrees.py --apply --force`.",
        "",
        "## Candidates",
        "",
    ]
    for index, row in enumerate(packet["candidates"], start=1):
        lines.extend(
            [
                f"### {index}. `{row['name']}`",
                "",
                f"- Path: `{row['path']}`",
                f"- Action: `{row['action']}`",
                f"- Reason: `{row['reason']}`",
                f"- Size: `{fmt_bytes(row.get('size_bytes'))}`",
                "",
                "Acceptance event template:",
                "",
                "```json",
                json.dumps(row["acceptance_event_template"], sort_keys=True),
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Write a non-destructive worktree reclaim candidate packet.")
    parser.add_argument("--input", type=Path, help="read a saved worktree-debt JSON report")
    parser.add_argument("--limit", type=int, default=50, help="candidate rows to emit")
    parser.add_argument("--size-scan-limit", type=int, default=500, help="candidate roots to size before sorting")
    parser.add_argument(
        "--size-timeout-sec",
        type=int,
        default=int(os.environ.get("LIMEN_RECLAIM_SIZE_TIMEOUT_SEC", "10")),
        help="per-root du timeout while measuring candidate sizes",
    )
    parser.add_argument(
        "--size-budget-sec",
        type=int,
        default=int(os.environ.get("LIMEN_RECLAIM_SIZE_BUDGET_SEC", "60")),
        help="total best-effort sizing budget for candidate roots",
    )
    parser.add_argument("--no-measure-size", action="store_true", help="skip du-based size measurement")
    parser.add_argument("--write", action="store_true", help="write docs/worktree-reclaim-candidates.*")
    parser.add_argument("--json", action="store_true", help="print the packet JSON")
    args = parser.parse_args()

    generated_at = utc_now()
    report = load_report(args.input)
    packet = build_packet(
        report,
        generated_at=generated_at,
        limit=max(args.limit, 0),
        measure=not args.no_measure_size,
        size_scan_limit=max(args.size_scan_limit, 0),
        size_timeout_sec=max(args.size_timeout_sec, 1),
        size_budget_sec=max(args.size_budget_sec, 0),
    )
    if args.write:
        DOC_PATH.write_text(render_markdown(packet), encoding="utf-8")
        JSON_PATH.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json or not args.write:
        print(json.dumps(packet, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
