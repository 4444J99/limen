#!/usr/bin/env python3
"""Antigravity/Agy scratch bridge.

Inventory ~/.gemini/antigravity-cli/scratch and classify each root before any
local deletion. Deletion is opt-in and limited to roots reclassified as
`safe_reap_candidate` immediately before removal.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1])).resolve()
HOME = Path.home()
SCRATCH_ROOT = Path(os.environ.get("LIMEN_AGY_SCRATCH_ROOT", HOME / ".gemini/antigravity-cli/scratch"))
DOC_PATH = ROOT / "docs" / "antigravity-scratch-bridge.md"
HISTORY_PATH = ROOT / "docs" / "antigravity-scratch-bridge-history.jsonl"
LOG_PATH = ROOT / "logs" / "antigravity-scratch-bridge.json"
REMOTE_RE = re.compile(r"(?:github\.com[:/])([^/\s]+)/([^/\s]+?)(?:\.git)?$")


def fmt_bytes(n: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    val = float(n)
    for unit in units:
        if val < 1024 or unit == units[-1]:
            return f"{int(val)} {unit}" if unit == "B" else f"{val:.1f} {unit}"
        val /= 1024
    return f"{n} B"


def relpath(path: Path) -> str:
    try:
        return "~/" + str(path.expanduser().resolve().relative_to(HOME))
    except (OSError, ValueError):
        return str(path)


def run_git(path: Path, args: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    cmd = ["git", "-C", str(path), *args]
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False, stdin=subprocess.DEVNULL
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(cmd, 1, "", str(exc))


def dir_size_bytes(path: Path) -> int:
    try:
        proc = subprocess.run(["du", "-sk", str(path)], capture_output=True, text=True, timeout=120)
        if proc.returncode == 0 and proc.stdout.strip():
            return int(proc.stdout.split()[0]) * 1024
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    total = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in {".git", "node_modules", ".venv", "venv"}]
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue
    return total


def repo_slug(remote: str | None) -> str | None:
    if not remote:
        return None
    match = REMOTE_RE.search(remote.strip())
    return f"{match.group(1)}/{match.group(2)}" if match else None


def porcelain_counts(path: Path) -> dict[str, int]:
    proc = run_git(path, ["status", "--porcelain", "-z"], timeout=30)
    if proc.returncode != 0:
        return {"entries": 0, "untracked": 0, "tracked": 0, "deletions": 0}
    entries = [part for part in proc.stdout.split("\0") if part]
    tracked = untracked = deletions = 0
    i = 0
    while i < len(entries):
        xy = entries[i][:2]
        if xy == "??":
            untracked += 1
        else:
            tracked += 1
            deletions += "D" in xy
        i += 2 if ("R" in xy or "C" in xy) else 1
    return {"entries": tracked + untracked, "untracked": untracked, "tracked": tracked, "deletions": deletions}


def git_lines(path: Path, args: list[str], timeout: int = 30) -> list[str]:
    proc = run_git(path, args, timeout=timeout)
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def path_digest(paths: list[str]) -> str:
    payload = "\n".join(sorted(paths)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def path_buckets(paths: list[str], limit: int = 8) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for path in paths:
        counts[path.split("/", 1)[0] if "/" in path else "(root)"] += 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit])


def dirty_profile(path: Path) -> dict[str, Any]:
    staged_deleted = git_lines(path, ["diff", "--cached", "--name-only", "--diff-filter=D"], timeout=60)
    staged_other = git_lines(path, ["diff", "--cached", "--name-only", "--diff-filter=ACMRTUXB"], timeout=60)
    unstaged = git_lines(path, ["diff", "--name-only"], timeout=60)
    untracked = git_lines(path, ["ls-files", "--others", "--exclude-standard"], timeout=60)
    combined = [f"D:{item}" for item in staged_deleted]
    combined += [f"S:{item}" for item in staged_other]
    combined += [f"W:{item}" for item in unstaged]
    combined += [f"U:{item}" for item in untracked]
    return {
        "fingerprint": path_digest(combined),
        "staged_deleted_count": len(staged_deleted),
        "staged_deleted_hash": path_digest(staged_deleted),
        "staged_other_count": len(staged_other),
        "staged_other_hash": path_digest(staged_other),
        "unstaged_count": len(unstaged),
        "unstaged_hash": path_digest(unstaged),
        "untracked_count": len(untracked),
        "untracked_hash": path_digest(untracked),
        "top_buckets": path_buckets(staged_deleted + staged_other + unstaged + untracked),
        "staged_deleted_buckets": path_buckets(staged_deleted),
        "untracked_buckets": path_buckets(untracked),
    }


def remote_default_ref(path: Path) -> str | None:
    proc = run_git(path, ["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"])
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    for ref in ("origin/main", "origin/master"):
        if run_git(path, ["show-ref", "--verify", "--quiet", f"refs/remotes/{ref}"]).returncode == 0:
            return ref
    return None


def head_reachable_from_remote(path: Path, head: str) -> bool:
    refs = run_git(path, ["for-each-ref", "--format=%(refname)", "refs/remotes"], timeout=30)
    if refs.returncode != 0:
        return False
    return any(
        run_git(path, ["merge-base", "--is-ancestor", head, ref], timeout=30).returncode == 0
        for ref in refs.stdout.splitlines()
    )


def merged_into_default(path: Path, head: str) -> bool:
    ref = remote_default_ref(path)
    return bool(ref and run_git(path, ["merge-base", "--is-ancestor", head, ref], timeout=30).returncode == 0)


def patch_equivalent_to_default(path: Path) -> bool:
    ref = remote_default_ref(path)
    if not ref:
        return False
    proc = run_git(path, ["cherry", ref, "HEAD"], timeout=30)
    if proc.returncode != 0:
        return False
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    return bool(lines) and all(line.startswith("-") for line in lines)


def git_snapshot(path: Path, min_idle_hours: float) -> dict[str, Any]:
    status = run_git(path, ["status", "--short", "--branch"], timeout=30)
    branch_line = status.stdout.splitlines()[0] if status.returncode == 0 and status.stdout.splitlines() else "unknown"
    remote = run_git(path, ["remote", "get-url", "origin"]).stdout.strip() or None
    head = run_git(path, ["rev-parse", "HEAD"]).stdout.strip() or None
    counts = porcelain_counts(path)
    remote_preserved = head_reachable_from_remote(path, head) if head else False
    patch_equiv = patch_equivalent_to_default(path)
    idle_hours = max(0.0, (time.time() - path.stat().st_mtime) / 3600)
    clean = counts["entries"] == 0
    if not clean:
        disposition, reason = "bridge_required", "dirty-or-untracked"
    elif idle_hours < min_idle_hours:
        disposition, reason = "keep_active", "idle-window-not-met"
    elif remote_preserved or patch_equiv:
        disposition, reason = "safe_reap_candidate", "clean-idle-remote-preserved"
    else:
        disposition, reason = "preserve_required", "clean-but-head-not-proven-on-remote"
    snapshot = {
        "kind": "git",
        "branch": branch_line,
        "remote": remote,
        "repo": repo_slug(remote),
        "head": head[:12] if head else None,
        "dirty_entries": counts["entries"],
        "untracked_entries": counts["untracked"],
        "tracked_dirty_entries": counts["tracked"],
        "deleted_entries": counts["deletions"],
        "remote_preserved": remote_preserved,
        "merged_to_default": merged_into_default(path, head) if head else False,
        "patch_equivalent_to_default": patch_equiv,
        "idle_hours": round(idle_hours, 2),
        "disposition": disposition,
        "reason": reason,
    }
    if not clean:
        snapshot["dirty_profile"] = dirty_profile(path)
    return snapshot


def nested_git_roots(path: Path, max_depth: int = 2) -> list[Path]:
    roots: list[Path] = []
    base_parts = len(path.parts)
    for current, dirs, _files in os.walk(path):
        cur = Path(current)
        depth = len(cur.parts) - base_parts
        if ".git" in dirs:
            roots.append(cur)
            dirs[:] = []
            continue
        if depth >= max_depth:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in {".git", "node_modules", ".venv", "venv", "__pycache__"}]
    return roots


def classify_root(path: Path, min_idle_hours: float) -> dict[str, Any]:
    st = path.stat()
    row: dict[str, Any] = {
        "name": path.name,
        "path": str(path),
        "display_path": relpath(path),
        "size_bytes": dir_size_bytes(path),
        "mtime": dt.datetime.fromtimestamp(st.st_mtime, tz=dt.timezone.utc).isoformat(timespec="seconds"),
    }
    row["size"] = fmt_bytes(int(row["size_bytes"]))
    if (path / ".git").exists():
        row.update(git_snapshot(path, min_idle_hours))
        return row
    nested_rows = [classify_root(p, min_idle_hours) for p in nested_git_roots(path)]
    nested_by_disposition = Counter(str(r["disposition"]) for r in nested_rows)
    row.update(
        {
            "kind": "container" if nested_rows else "non_git",
            "nested_git_roots": len(nested_rows),
            "nested_by_disposition": dict(sorted(nested_by_disposition.items())),
            "disposition": "container_review_required" if nested_rows else "non_git_review_required",
            "reason": "nested-git-roots" if nested_rows else "no-git-receipt",
        }
    )
    return row


def build_report(scratch_root: Path = SCRATCH_ROOT, min_idle_hours: float = 24.0) -> dict[str, Any]:
    generated = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    if not scratch_root.is_dir():
        return {
            "generated_at": generated,
            "scratch_root": str(scratch_root),
            "present": False,
            "summary": {"total_roots": 0, "total_bytes": 0, "by_disposition": {}},
            "roots": [],
        }
    rows = [classify_root(path, min_idle_hours) for path in sorted(scratch_root.iterdir()) if path.is_dir()]
    rows.sort(key=lambda item: int(item["size_bytes"]), reverse=True)
    by_disp = Counter(str(row["disposition"]) for row in rows)
    safe_reap_bytes = sum(int(row["size_bytes"]) for row in rows if row["disposition"] == "safe_reap_candidate")
    total_bytes = sum(int(row["size_bytes"]) for row in rows)
    return {
        "generated_at": generated,
        "scratch_root": str(scratch_root),
        "present": True,
        "min_idle_hours": min_idle_hours,
        "summary": {
            "total_roots": len(rows),
            "total_bytes": total_bytes,
            "total_size": fmt_bytes(total_bytes),
            "by_disposition": dict(sorted(by_disp.items())),
            "safe_reap_bytes": safe_reap_bytes,
            "safe_reap_size": fmt_bytes(safe_reap_bytes),
        },
        "roots": rows,
    }


def apply_safe_reap(report: dict[str, Any], min_idle_hours: float) -> dict[str, Any]:
    scratch_root = Path(report["scratch_root"]).expanduser().resolve()
    results: list[dict[str, Any]] = []
    for row in report.get("roots", []):
        if row.get("disposition") != "safe_reap_candidate":
            continue
        raw_path = Path(str(row.get("path", ""))).expanduser()
        try:
            path = raw_path.resolve()
            path.relative_to(scratch_root)
        except (OSError, ValueError):
            results.append(
                {
                    "name": row.get("name"),
                    "path": str(raw_path),
                    "status": "skipped",
                    "reason": "path-outside-scratch-root",
                }
            )
            continue
        if path == scratch_root:
            results.append(
                {
                    "name": row.get("name"),
                    "path": str(path),
                    "status": "skipped",
                    "reason": "refused-scratch-root",
                }
            )
            continue
        if not path.exists():
            results.append(
                {
                    "name": row.get("name"),
                    "path": str(path),
                    "status": "skipped",
                    "reason": "already-missing",
                }
            )
            continue

        checked = classify_root(path, min_idle_hours)
        if checked.get("disposition") != "safe_reap_candidate":
            results.append(
                {
                    "name": checked.get("name"),
                    "path": checked.get("path"),
                    "status": "skipped",
                    "reason": f"reclassified-{checked.get('disposition')}",
                }
            )
            continue
        try:
            shutil.rmtree(path)
            results.append(
                {
                    "name": checked.get("name"),
                    "path": checked.get("path"),
                    "status": "reaped",
                    "reason": checked.get("reason"),
                    "size_bytes": int(checked.get("size_bytes", 0)),
                    "size": checked.get("size"),
                    "repo": checked.get("repo"),
                    "head": checked.get("head"),
                }
            )
        except OSError as exc:
            results.append(
                {
                    "name": checked.get("name"),
                    "path": checked.get("path"),
                    "status": "failed",
                    "reason": str(exc),
                }
            )

    reaped_bytes = sum(int(item.get("size_bytes", 0)) for item in results if item["status"] == "reaped")
    by_status = Counter(str(item["status"]) for item in results)
    return {
        "applied_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "summary": {
            "candidates_considered": len(results),
            "reaped": by_status.get("reaped", 0),
            "skipped": by_status.get("skipped", 0),
            "failed": by_status.get("failed", 0),
            "reaped_bytes": reaped_bytes,
            "reaped_size": fmt_bytes(reaped_bytes),
        },
        "results": results,
    }


def build_reap_history_event(report: dict[str, Any]) -> dict[str, Any] | None:
    reap = report.get("reap") or {}
    summary = reap.get("summary") or {}
    if int(summary.get("candidates_considered", 0)) <= 0:
        return None
    results: list[dict[str, Any]] = []
    for item in reap.get("results", []):
        compact = {
            key: item[key]
            for key in ("name", "status", "reason", "size_bytes", "size", "repo", "head")
            if key in item and item[key] is not None
        }
        results.append(compact)
    return {
        "applied_at": reap.get("applied_at"),
        "generated_at": report.get("generated_at"),
        "scratch_root": relpath(Path(str(report.get("scratch_root", "")))),
        "summary": summary,
        "results": results,
    }


def load_reap_history(path: Path = HISTORY_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    events.sort(key=lambda event: str(event.get("applied_at", "")))
    return events


def append_reap_history(report: dict[str, Any], path: Path = HISTORY_PATH) -> list[dict[str, Any]]:
    history = load_reap_history(path)
    event = build_reap_history_event(report)
    if not event:
        return history
    event_key = (event.get("applied_at"), event.get("scratch_root"))
    if any((existing.get("applied_at"), existing.get("scratch_root")) == event_key for existing in history):
        return history
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
    history.append(event)
    history.sort(key=lambda item: str(item.get("applied_at", "")))
    return history


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Antigravity Scratch Bridge",
        "",
        f"Generated: `{report['generated_at']}`",
        f"Scratch root: `{relpath(Path(report['scratch_root']))}`",
        "",
        "## Decision",
        "",
        "Do not delete Antigravity scratch roots by size alone. A root is only a reclaim candidate",
        "when this bridge proves it is clean, idle, and preserved on a remote/default-equivalent ref.",
        "Dirty roots are `bridge_required`: their per-root delta must be carried home or archived",
        "before any deletion.",
        "",
        "`staged_deleted_count` in this receipt means Git observed files already missing/staged",
        "inside a scratch clone. It is a preservation blocker, not authorization to delete the root.",
        "",
        "## Summary",
        "",
        f"- Roots scanned: `{summary.get('total_roots', 0)}`.",
        f"- Total scratch size: `{summary.get('total_size', '0 B')}`.",
        f"- Safe-reap candidate size: `{summary.get('safe_reap_size', '0 B')}`.",
    ]
    by_disp = summary.get("by_disposition") or {}
    if by_disp:
        lines.append("- Dispositions: " + ", ".join(f"`{k}` {v}" for k, v in by_disp.items()) + ".")
    if report.get("post_reap_summary"):
        post = report["post_reap_summary"]
        lines.append(
            f"- Post-reap scratch size: `{post.get('total_size', '0 B')}` across `{post.get('total_roots', 0)}` roots."
        )
    if report.get("reap"):
        reap = report["reap"]["summary"]
        lines += [
            "",
            "## Reap Results",
            "",
            f"- Applied at: `{report['reap']['applied_at']}`.",
            f"- Reaped: `{reap.get('reaped', 0)}` roots, `{reap.get('reaped_size', '0 B')}`.",
            f"- Skipped: `{reap.get('skipped', 0)}`; failed: `{reap.get('failed', 0)}`.",
        ]
        for item in report["reap"].get("results", []):
            if item.get("status") == "reaped":
                proof = item.get("repo") or "remote"
                if item.get("head"):
                    proof = f"{proof}@{item['head']}"
                lines.append(f"- Reaped `{item.get('name')}` `{item.get('size')}` ({proof}).")
            else:
                lines.append(f"- {item.get('status', 'skipped').title()} `{item.get('name')}`: {item.get('reason')}.")
    history = report.get("reap_history") or []
    if history:
        total_reaped = sum(int((event.get("summary") or {}).get("reaped", 0)) for event in history)
        total_reaped_bytes = sum(int((event.get("summary") or {}).get("reaped_bytes", 0)) for event in history)
        lines += [
            "",
            "## Reap History",
            "",
            f"- Recorded reap events: `{len(history)}`.",
            f"- Cumulative reaped roots: `{total_reaped}`.",
            f"- Cumulative reclaimed size: `{fmt_bytes(total_reaped_bytes)}`.",
        ]
        for event in reversed(history[-10:]):
            event_summary = event.get("summary") or {}
            roots = [
                str(item.get("name"))
                for item in event.get("results", [])
                if item.get("status") == "reaped" and item.get("name")
            ]
            shown_roots = ", ".join(f"`{name}`" for name in roots[:8])
            if len(roots) > 8:
                shown_roots += f", ... +{len(roots) - 8}"
            lines.append(
                f"- `{event.get('applied_at')}`: `{event_summary.get('reaped', 0)}` roots, "
                f"`{event_summary.get('reaped_size', '0 B')}`"
                + (f" ({shown_roots})." if shown_roots else ".")
            )
    staged_missing_groups: dict[str, dict[str, Any]] = {}
    dirty_groups: dict[str, dict[str, Any]] = {}
    for row in report.get("roots", []):
        profile = row.get("dirty_profile") or {}
        staged_deleted_hash = profile.get("staged_deleted_hash")
        if staged_deleted_hash and int(profile.get("staged_deleted_count", 0)) > 0:
            group = staged_missing_groups.setdefault(
                str(staged_deleted_hash),
                {
                    "roots": [],
                    "staged_deleted_count": profile.get("staged_deleted_count", 0),
                    "staged_deleted_buckets": profile.get("staged_deleted_buckets") or {},
                },
            )
            group["roots"].append(str(row.get("name")))
        fingerprint = profile.get("fingerprint")
        if not fingerprint:
            continue
        group = dirty_groups.setdefault(
            str(fingerprint),
            {
                "roots": [],
                "staged_deleted_count": profile.get("staged_deleted_count", 0),
                "untracked_count": profile.get("untracked_count", 0),
                "top_buckets": profile.get("top_buckets") or {},
            },
        )
        group["roots"].append(str(row.get("name")))
    repeated_staged_missing = sorted(
        (group for group in staged_missing_groups.values() if len(group["roots"]) > 1),
        key=lambda group: (-len(group["roots"]), str(group["roots"][0])),
    )
    if repeated_staged_missing:
        lines += [
            "",
            "## Repeated Staged-Missing Fingerprints",
            "",
            "These roots have the same set of files already missing/staged inside their scratch clone.",
            "That is a preservation blocker and duplicate-state signal, not deletion permission.",
            "",
            "| Count | Roots | Staged missing | Top staged buckets |",
            "|---:|---|---:|---|",
        ]
        for group in repeated_staged_missing[:10]:
            buckets = ", ".join(
                f"{key}:{value}" for key, value in group["staged_deleted_buckets"].items()
            ) or "none"
            roots = ", ".join(f"`{name}`" for name in group["roots"][:8])
            if len(group["roots"]) > 8:
                roots += f", ... +{len(group['roots']) - 8}"
            lines.append(
                f"| `{len(group['roots'])}` | {roots} | `{group['staged_deleted_count']}` | `{buckets}` |"
            )
    repeated_dirty = sorted(
        (group for group in dirty_groups.values() if len(group["roots"]) > 1),
        key=lambda group: (-len(group["roots"]), str(group["roots"][0])),
    )
    if repeated_dirty:
        lines += [
            "",
            "## Repeated Dirty Fingerprints",
            "",
            "These are duplicate-looking unsafe scratch states. They still require bridge/archive proof",
            "before any local root can be removed.",
            "",
            "| Count | Roots | Staged missing | Untracked | Top buckets |",
            "|---:|---|---:|---:|---|",
        ]
        for group in repeated_dirty[:10]:
            buckets = ", ".join(f"{key}:{value}" for key, value in group["top_buckets"].items()) or "none"
            roots = ", ".join(f"`{name}`" for name in group["roots"][:8])
            if len(group["roots"]) > 8:
                roots += f", ... +{len(group['roots']) - 8}"
            lines.append(
                f"| `{len(group['roots'])}` | {roots} | `{group['staged_deleted_count']}` | `{group['untracked_count']}` | `{buckets}` |"
            )
    largest_heading = "## Largest Roots"
    if report.get("reap"):
        largest_heading = "## Largest Roots Before Reap"
    lines += [
        "",
        largest_heading,
        "",
        "| Root | Size | Kind | Disposition | Reason | Remote / nested proof |",
        "|---|---:|---|---|---|---|",
    ]
    for row in report.get("roots", [])[:40]:
        if row.get("kind") == "git":
            proof = row.get("repo") or row.get("remote") or "no origin"
            if row.get("head"):
                proof = f"{proof}@{row['head']}"
        else:
            nested = row.get("nested_by_disposition") or {}
            proof = ", ".join(f"{k}:{v}" for k, v in nested.items()) or "none"
        lines.append(
            f"| `{row['name']}` | `{row['size']}` | `{row.get('kind')}` | `{row.get('disposition')}` | `{row.get('reason')}` | `{proof}` |"
        )
    lines += [
        "",
        "## Operating Rule",
        "",
        "- `safe_reap_candidate`: local deletion is allowed only through `--apply-safe-reap --write`, "
        "which reclassifies the root before removal and writes a receipt.",
        "- `bridge_required`: preserve/carry the uncommitted delta first.",
        "- `preserve_required`: push, archive, or receipt the local commit before deletion.",
        "- `container_review_required`: inspect nested repos; do not delete the parent as one blob.",
        "- `non_git_review_required`: classify the directory owner before deleting it.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Antigravity scratch roots before deletion.")
    parser.add_argument("--root", type=Path, default=SCRATCH_ROOT, help="scratch root to scan")
    parser.add_argument("--min-idle-hours", type=float, default=24.0, help="idle age required for reap candidates")
    parser.add_argument("--json", action="store_true", help="print machine JSON")
    parser.add_argument("--write", action="store_true", help="write docs/ and logs/ receipts")
    parser.add_argument(
        "--apply-safe-reap",
        action="store_true",
        help="delete roots that reclassify as safe_reap_candidate; requires --write",
    )
    args = parser.parse_args()
    if args.apply_safe_reap and not args.write:
        parser.error("--apply-safe-reap requires --write")
    report = build_report(args.root.expanduser(), args.min_idle_hours)
    if args.apply_safe_reap:
        report["reap"] = apply_safe_reap(report, args.min_idle_hours)
        report["post_reap_summary"] = build_report(args.root.expanduser(), args.min_idle_hours)["summary"]
    if args.write:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
        if args.apply_safe_reap:
            report["reap_history"] = append_reap_history(report, HISTORY_PATH)
        else:
            report["reap_history"] = load_reap_history(HISTORY_PATH)
        LOG_PATH.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        DOC_PATH.write_text(render_markdown(report), encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        summary = report["summary"]
        print(
            f"antigravity-scratch: {summary.get('total_roots', 0)} roots, {summary.get('total_size', '0 B')}; safe-reap candidates {summary.get('safe_reap_size', '0 B')}"
        )
        for name, count in (summary.get("by_disposition") or {}).items():
            print(f"  {name}: {count}")
        if args.write:
            print(f"  wrote: {relpath(DOC_PATH)}")
            print(f"  wrote: {relpath(LOG_PATH)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
