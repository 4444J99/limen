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
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from reap_acceptance import REQUIRED_ACCEPTANCE_PROOF_FIELDS, has_required_acceptance_proof  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1])).resolve()
HOME = Path.home()
SCRATCH_ROOT = Path(os.environ.get("LIMEN_AGY_SCRATCH_ROOT", HOME / ".gemini/antigravity-cli/scratch"))
DOC_PATH = ROOT / "docs" / "antigravity-scratch-bridge.md"
HISTORY_PATH = ROOT / "docs" / "antigravity-scratch-bridge-history.jsonl"
PRESERVATION_HISTORY_PATH = ROOT / "docs" / "antigravity-scratch-preservation.jsonl"
REAP_ACCEPTANCE_PATH = ROOT / "docs" / "antigravity-scratch-reap-acceptance.jsonl"
REAP_ACCEPTANCE_DOC = ROOT / "docs" / "antigravity-scratch-reap-acceptance.md"
LOG_PATH = ROOT / "logs" / "antigravity-scratch-bridge.json"
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
PRIVATE_PRESERVE_ROOT = PRIVATE_ROOT / "lifecycle" / "agy-scratch-preserve"
ARCHIVE_ROOT = Path(os.environ.get("LIMEN_ARCHIVE_ROOT", "/Volumes/Archive4T"))
ARCHIVE_PRESERVE_ROOT = Path(
    os.environ.get("LIMEN_AGY_ARCHIVE_ROOT", str(ARCHIVE_ROOT / "limen-private" / "agy-scratch-preserve"))
)
REMOTE_RE = re.compile(r"(?:github\.com[:/])([^/\s]+)/([^/\s]+?)(?:\.git)?$")
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
ACCEPTED_REDACTION_REVIEWS = {"accepted", "private_archive_only", "not_required_private_archive"}
REAP_ACCEPTANCE_REQUIRED_FIELDS = REQUIRED_ACCEPTANCE_PROOF_FIELDS


def fmt_bytes(n: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    val = float(n)
    for unit in units:
        if val < 1024 or unit == units[-1]:
            return f"{int(val)} {unit}" if unit == "B" else f"{val:.1f} {unit}"
        val /= 1024
    return f"{n} B"


def fmt_count_span(counts: list[int]) -> str:
    if not counts:
        return "0"
    low = min(counts)
    high = max(counts)
    return str(low) if low == high else f"{low}-{high}"


def relpath(path: Path) -> str:
    try:
        return "~/" + str(path.expanduser().resolve().relative_to(HOME))
    except (OSError, ValueError):
        return str(path)


def rel_to_root(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except (OSError, ValueError):
        return relpath(path)


def safe_name(value: str) -> str:
    cleaned = SAFE_NAME_RE.sub("-", value.strip()).strip("-._")
    return cleaned[:80] or "scratch-root"


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


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_private(path: Path, content: str) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", errors="replace")
    return {"path": rel_to_root(path), "bytes": path.stat().st_size, "sha256": file_sha256(path)}


def resolve_recorded_path(value: str | None) -> Path | None:
    if not value:
        return None
    raw = str(value)
    if raw.startswith("~/"):
        return HOME / raw[2:]
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    return ROOT / path


def archive_available(path: Path = ARCHIVE_PRESERVE_ROOT) -> bool:
    root = path
    while not root.exists() and root != root.parent:
        root = root.parent
    return root.exists() and os.access(root, os.W_OK)


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
    staged_deleted_set = set(staged_deleted)
    untracked_set = set(untracked)
    staged_deleted_untracked_overlap = sorted(staged_deleted_set & untracked_set)
    staged_deleted_absent = sorted(staged_deleted_set - untracked_set)
    extra_untracked = sorted(untracked_set - staged_deleted_set)
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
        "staged_deleted_untracked_overlap_count": len(staged_deleted_untracked_overlap),
        "staged_deleted_untracked_overlap_hash": path_digest(staged_deleted_untracked_overlap),
        "staged_deleted_absent_count": len(staged_deleted_absent),
        "staged_deleted_absent_hash": path_digest(staged_deleted_absent),
        "staged_deleted_absent_buckets": path_buckets(staged_deleted_absent),
        "extra_untracked_count": len(extra_untracked),
        "extra_untracked_hash": path_digest(extra_untracked),
        "extra_untracked_buckets": path_buckets(extra_untracked),
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


def current_head(path: Path) -> str | None:
    proc = run_git(path, ["rev-parse", "HEAD"], timeout=30)
    head = proc.stdout.strip()
    if proc.returncode != 0 or len(head) != 40 or any(ch not in "0123456789abcdefABCDEF" for ch in head):
        return None
    return head


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
    head = current_head(path)
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


def matching_preservation_event(row: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any] | None:
    name = str(row.get("name") or "")
    head = row.get("head")
    disposition = row.get("disposition")
    size_bytes = row.get("size_bytes")
    for event in reversed(history):
        if event.get("root") != name:
            continue
        if not event.get("archive_verified"):
            continue
        if not event.get("archive_path"):
            continue
        if not event.get("private_receipt") or not event.get("private_receipt_sha256"):
            continue
        if head and event.get("head") and event.get("head") != head:
            continue
        if disposition and event.get("disposition") and event.get("disposition") != disposition:
            continue
        if size_bytes is not None and event.get("size_bytes") is not None:
            try:
                if int(event["size_bytes"]) != int(size_bytes):
                    continue
            except (TypeError, ValueError):
                continue
        return event
    return None


def matching_reap_acceptance(
    row: dict[str, Any], preservation: dict[str, Any], history: list[dict[str, Any]]
) -> dict[str, Any] | None:
    name = str(row.get("name") or "")
    receipt_hash = preservation.get("private_receipt_sha256")
    for event in reversed(history):
        if event.get("root") != name:
            continue
        if event.get("private_receipt_sha256") != receipt_hash:
            continue
        if event.get("accepted") is not True:
            continue
        if event.get("redaction_review") not in ACCEPTED_REDACTION_REVIEWS:
            continue
        if not has_required_acceptance_proof(event):
            continue
        return event
    return None


def reap_permission(
    row: dict[str, Any], preservation_history: list[dict[str, Any]], acceptance_history: list[dict[str, Any]]
) -> tuple[bool, str, dict[str, Any]]:
    preservation = matching_preservation_event(row, preservation_history)
    if not preservation:
        return False, "missing-verified-archive-preservation", {}
    acceptance = matching_reap_acceptance(row, preservation, acceptance_history)
    if not acceptance:
        return False, "missing-human-reap-acceptance", {
            "private_receipt": preservation.get("private_receipt"),
            "private_receipt_sha256": preservation.get("private_receipt_sha256"),
        }
    return True, "human-accepted-archive-preserved-redaction-reviewed", {
        "private_receipt": preservation.get("private_receipt"),
        "private_receipt_sha256": preservation.get("private_receipt_sha256"),
        "archive_path": preservation.get("archive_path"),
        "accepted_at": acceptance.get("accepted_at"),
        "archive_proof": acceptance.get("archive_proof"),
        "redaction_review": acceptance.get("redaction_review"),
        "redaction_proof": acceptance.get("redaction_proof"),
    }


def apply_safe_reap(
    report: dict[str, Any],
    min_idle_hours: float,
    preservation_history: list[dict[str, Any]] | None = None,
    acceptance_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    scratch_root = Path(report["scratch_root"]).expanduser().resolve()
    preservation_history = preservation_history or []
    acceptance_history = acceptance_history or []
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
        allowed, reason, proof = reap_permission(checked, preservation_history, acceptance_history)
        if not allowed:
            results.append(
                {
                    "name": checked.get("name"),
                    "path": checked.get("path"),
                    "status": "skipped",
                    "reason": reason,
                    **proof,
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
                    **proof,
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
            for key in (
                "name",
                "status",
                "reason",
                "size_bytes",
                "size",
                "repo",
                "head",
                "archive_path",
                "accepted_at",
                "archive_proof",
                "redaction_review",
                "redaction_proof",
                "private_receipt_sha256",
            )
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


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            out.append(data)
    out.sort(key=lambda event: str(event.get("preserved_at", event.get("applied_at", ""))))
    return out


def run_rsync_archive(src: Path, dst: Path, timeout: int) -> dict[str, Any]:
    dst.mkdir(parents=True, exist_ok=True)
    src_arg = str(src) + "/"
    dst_arg = str(dst) + "/"
    copy = subprocess.run(
        ["rsync", "-a", src_arg, dst_arg],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    verify = subprocess.run(
        ["rsync", "-anci", src_arg, dst_arg],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    pending = [line for line in verify.stdout.splitlines() if line[:1] in "<>"]
    return {
        "copy_returncode": copy.returncode,
        "verify_returncode": verify.returncode,
        "verified": copy.returncode == 0 and verify.returncode == 0 and not pending,
        "pending_count": len(pending),
        "copy_stdout": copy.stdout,
        "copy_stderr": copy.stderr,
        "verify_stdout": verify.stdout,
        "verify_stderr": verify.stderr,
    }


def preserve_root(row: dict[str, Any], scratch_root: Path, min_idle_hours: float, timeout: int) -> dict[str, Any]:
    preserved_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = str(row.get("name") or "scratch-root")
    raw_path = Path(str(row.get("path") or "")).expanduser()
    try:
        path = raw_path.resolve()
        path.relative_to(scratch_root)
    except (OSError, ValueError):
        return {
            "preserved_at": preserved_at,
            "name": name,
            "status": "skipped",
            "reason": "path-outside-scratch-root",
        }
    if not path.exists():
        return {"preserved_at": preserved_at, "name": name, "status": "skipped", "reason": "already-missing"}

    checked = classify_root(path, min_idle_hours)
    private_dir = PRIVATE_PRESERVE_ROOT / f"{stamp}-{safe_name(name)}"
    private_dir.mkdir(parents=True, exist_ok=True)
    private_files: dict[str, Any] = {
        "status_porcelain": write_private(
            private_dir / "status-porcelain.txt",
            run_git(path, ["status", "--porcelain=v1"], timeout=60).stdout,
        ),
        "status_branch": write_private(
            private_dir / "status-branch.txt",
            run_git(path, ["status", "--short", "--branch"], timeout=60).stdout,
        ),
        "staged_deleted": write_private(
            private_dir / "staged-deleted.txt",
            "\n".join(git_lines(path, ["diff", "--cached", "--name-only", "--diff-filter=D"], timeout=60))
            + "\n",
        ),
        "untracked": write_private(
            private_dir / "untracked.txt",
            "\n".join(git_lines(path, ["ls-files", "--others", "--exclude-standard"], timeout=60)) + "\n",
        ),
        "dirty_profile": write_private(
            private_dir / "dirty-profile.json",
            json.dumps(checked.get("dirty_profile") or {}, indent=2, sort_keys=True) + "\n",
        ),
    }

    archive_status = "unavailable"
    archive_path: str | None = None
    archive_verified = False
    archive_pending_count: int | None = None
    if archive_available(ARCHIVE_PRESERVE_ROOT):
        archive_dir = ARCHIVE_PRESERVE_ROOT / f"{stamp}-{safe_name(name)}" / "root"
        archive_path = str(archive_dir)
        try:
            archive_result = run_rsync_archive(path, archive_dir, timeout)
            archive_status = "verified" if archive_result["verified"] else "failed"
            archive_verified = bool(archive_result["verified"])
            archive_pending_count = int(archive_result["pending_count"])
            private_files["rsync_copy_stdout"] = write_private(
                private_dir / "rsync-copy.stdout", archive_result["copy_stdout"]
            )
            private_files["rsync_copy_stderr"] = write_private(
                private_dir / "rsync-copy.stderr", archive_result["copy_stderr"]
            )
            private_files["rsync_verify_stdout"] = write_private(
                private_dir / "rsync-verify.stdout", archive_result["verify_stdout"]
            )
            private_files["rsync_verify_stderr"] = write_private(
                private_dir / "rsync-verify.stderr", archive_result["verify_stderr"]
            )
        except subprocess.TimeoutExpired:
            archive_status = "timeout"
        except OSError as exc:
            archive_status = f"error:{exc}"

    status = "external_archive_preserved" if archive_verified else "private_manifest_preserved"
    receipt = {
        "preserved_at": preserved_at,
        "root": name,
        "status": status,
        "classification": "antigravity scratch root preservation receipt",
        "source": checked.get("display_path") or relpath(path),
        "repo": checked.get("repo"),
        "head": checked.get("head"),
        "disposition": checked.get("disposition"),
        "reason": checked.get("reason"),
        "size_bytes": int(checked.get("size_bytes", 0)),
        "size": checked.get("size"),
        "dirty_profile": checked.get("dirty_profile") or {},
        "private_files": private_files,
        "archive": {
            "root": str(ARCHIVE_PRESERVE_ROOT),
            "path": archive_path,
            "status": archive_status,
            "verified": archive_verified,
            "pending_count": archive_pending_count,
        },
        "next_action": (
            "Do not delete the scratch root from local storage until a human accepts this preservation "
            "receipt or a narrower bridge proves every delta has landed in the owner repository."
        ),
    }
    receipt_path = private_dir / "receipt.json"
    receipt["private_receipt"] = rel_to_root(receipt_path)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt["private_receipt_sha256"] = file_sha256(receipt_path)
    return receipt


def refresh_preservation_receipt_hash(event: dict[str, Any]) -> bool:
    receipt_path = resolve_recorded_path(event.get("private_receipt"))
    if not receipt_path or not receipt_path.exists() or not receipt_path.is_file():
        return False
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        receipt = None
    if isinstance(receipt, dict) and "private_receipt_sha256" in receipt:
        receipt.pop("private_receipt_sha256", None)
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digest = file_sha256(receipt_path)
    if event.get("private_receipt_sha256") == digest:
        return False
    event["private_receipt_sha256"] = digest
    return True


def write_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")


def append_preservation_history(receipts: list[dict[str, Any]], path: Path = PRESERVATION_HISTORY_PATH) -> list[dict[str, Any]]:
    history = load_jsonl(path)
    hash_refreshed = False
    for event in history:
        hash_refreshed = refresh_preservation_receipt_hash(event) or hash_refreshed
    existing_keys = {(item.get("preserved_at"), item.get("root")) for item in history}
    new_events: list[dict[str, Any]] = []
    for receipt in receipts:
        if receipt.get("status") == "skipped":
            continue
        event = {
            "preserved_at": receipt.get("preserved_at"),
            "root": receipt.get("root"),
            "status": receipt.get("status"),
            "repo": receipt.get("repo"),
            "head": receipt.get("head"),
            "size_bytes": receipt.get("size_bytes"),
            "size": receipt.get("size"),
            "disposition": receipt.get("disposition"),
            "private_receipt": receipt.get("private_receipt"),
            "private_receipt_sha256": receipt.get("private_receipt_sha256"),
            "archive_status": (receipt.get("archive") or {}).get("status"),
            "archive_verified": (receipt.get("archive") or {}).get("verified"),
            "archive_path": (receipt.get("archive") or {}).get("path"),
        }
        refresh_preservation_receipt_hash(event)
        key = (event.get("preserved_at"), event.get("root"))
        if key in existing_keys:
            continue
        new_events.append(event)
        existing_keys.add(key)
    if new_events:
        history.extend(new_events)
        history.sort(key=lambda event: str(event.get("preserved_at", "")))
    if hash_refreshed or new_events:
        write_jsonl(path, history)
    return history


def preserve_named_roots(report: dict[str, Any], names: list[str], min_idle_hours: float, timeout: int) -> dict[str, Any]:
    scratch_root = Path(report["scratch_root"]).expanduser().resolve()
    by_name = {str(row.get("name")): row for row in report.get("roots", [])}
    receipts: list[dict[str, Any]] = []
    for name in names:
        row = by_name.get(name)
        if not row:
            receipts.append(
                {
                    "preserved_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "name": name,
                    "status": "skipped",
                    "reason": "root-not-found",
                }
            )
            continue
        receipts.append(preserve_root(row, scratch_root, min_idle_hours, timeout))
    by_status = Counter(str(item.get("status")) for item in receipts)
    preserved_bytes = sum(int(item.get("size_bytes", 0)) for item in receipts if item.get("status") != "skipped")
    return {
        "summary": {
            "requested": len(names),
            "by_status": dict(sorted(by_status.items())),
            "preserved_bytes": preserved_bytes,
            "preserved_size": fmt_bytes(preserved_bytes),
        },
        "results": receipts,
    }


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
        "Do not delete Antigravity scratch roots by size alone. A root is only a review candidate",
        "when this bridge proves it is clean, idle, and preserved on a remote/default-equivalent ref.",
        "Physical deletion additionally requires a verified archive preservation receipt plus a",
        f"human acceptance/redaction-review event in `{rel_to_root(REAP_ACCEPTANCE_PATH)}`.",
        f"The required acceptance shape is documented in `{rel_to_root(REAP_ACCEPTANCE_DOC)}`.",
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
                extra = ""
                if item.get("accepted_at") or item.get("redaction_review"):
                    extra = (
                        f"; accepted `{item.get('accepted_at', 'unknown')}`; "
                        f"redaction `{item.get('redaction_review', 'unknown')}`"
                    )
                lines.append(f"- Reaped `{item.get('name')}` `{item.get('size')}` ({proof}{extra}).")
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
    preservation_history = report.get("preservation_history") or []
    if preservation_history:
        total_event_bytes = sum(int(event.get("size_bytes") or 0) for event in preservation_history)
        verified_bytes = sum(
            int(event.get("size_bytes") or 0) for event in preservation_history if event.get("archive_verified")
        )
        verified = sum(1 for event in preservation_history if event.get("archive_verified"))
        lines += [
            "",
            "## Preservation History",
            "",
            f"- Preservation receipts: `{len(preservation_history)}`.",
            f"- External archives verified: `{verified}`.",
            f"- Verified external archive source size: `{fmt_bytes(verified_bytes)}`.",
            f"- Event source size total: `{fmt_bytes(total_event_bytes)}` (includes retries).",
        ]
        for event in reversed(preservation_history[-10:]):
            archive_status = event.get("archive_status") or "none"
            private_receipt = event.get("private_receipt") or "none"
            lines.append(
                f"- `{event.get('preserved_at')}` `{event.get('root')}`: `{event.get('status')}`; "
                f"archive `{archive_status}`; private receipt `{private_receipt}`."
            )
    if report.get("preservation"):
        preservation = report["preservation"]
        lines += [
            "",
            "## Preservation Results",
            "",
            f"- Requested roots: `{preservation['summary'].get('requested', 0)}`.",
            f"- Source size receipted: `{preservation['summary'].get('preserved_size', '0 B')}`.",
        ]
        by_status = preservation["summary"].get("by_status") or {}
        if by_status:
            lines.append("- Statuses: " + ", ".join(f"`{key}` {value}" for key, value in by_status.items()) + ".")
        for item in preservation.get("results", []):
            if item.get("status") == "skipped":
                lines.append(f"- Skipped `{item.get('name') or item.get('root')}`: {item.get('reason')}.")
                continue
            archive = item.get("archive") or {}
            lines.append(
                f"- Preserved `{item.get('root')}` `{item.get('size')}` as `{item.get('status')}`; "
                f"archive `{archive.get('status')}`; private receipt `{item.get('private_receipt')}`."
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
                    "staged_deleted_untracked_overlap_counts": [],
                    "staged_deleted_absent_counts": [],
                    "staged_deleted_buckets": profile.get("staged_deleted_buckets") or {},
                    "staged_deleted_absent_buckets": profile.get("staged_deleted_absent_buckets") or {},
                },
            )
            group["roots"].append(str(row.get("name")))
            group["staged_deleted_untracked_overlap_counts"].append(
                int(profile.get("staged_deleted_untracked_overlap_count", 0))
            )
            group["staged_deleted_absent_counts"].append(int(profile.get("staged_deleted_absent_count", 0)))
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
            "| Count | Roots | Staged missing | Same path untracked | Absent from worktree | Top staged buckets |",
            "|---:|---|---:|---:|---:|---|",
        ]
        for group in repeated_staged_missing[:10]:
            buckets = ", ".join(
                f"{key}:{value}" for key, value in group["staged_deleted_buckets"].items()
            ) or "none"
            roots = ", ".join(f"`{name}`" for name in group["roots"][:8])
            if len(group["roots"]) > 8:
                roots += f", ... +{len(group['roots']) - 8}"
            lines.append(
                f"| `{len(group['roots'])}` | {roots} | `{group['staged_deleted_count']}` | "
                f"`{fmt_count_span(group['staged_deleted_untracked_overlap_counts'])}` | "
                f"`{fmt_count_span(group['staged_deleted_absent_counts'])}` | `{buckets}` |"
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
        "which reclassifies the root before removal, then requires a matching verified archive receipt "
        "and human redaction acceptance with `accepted_at`, `archive_proof`, and `redaction_proof` "
        "before writing a deletion receipt.",
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
    parser.add_argument(
        "--preserve-root",
        action="append",
        default=[],
        help="copy a named scratch root to the private external archive and write redacted receipts; requires --write",
    )
    parser.add_argument(
        "--archive-timeout",
        type=int,
        default=7200,
        help="seconds allowed for each rsync copy/verify during --preserve-root",
    )
    args = parser.parse_args()
    if args.apply_safe_reap and not args.write:
        parser.error("--apply-safe-reap requires --write")
    if args.preserve_root and not args.write:
        parser.error("--preserve-root requires --write")
    report = build_report(args.root.expanduser(), args.min_idle_hours)
    if args.apply_safe_reap:
        preservation_history = load_jsonl(PRESERVATION_HISTORY_PATH)
        acceptance_history = load_jsonl(REAP_ACCEPTANCE_PATH)
        report["reap"] = apply_safe_reap(report, args.min_idle_hours, preservation_history, acceptance_history)
        report["post_reap_summary"] = build_report(args.root.expanduser(), args.min_idle_hours)["summary"]
    if args.preserve_root:
        report["preservation"] = preserve_named_roots(
            report, args.preserve_root, args.min_idle_hours, args.archive_timeout
        )
        report["preservation_history"] = append_preservation_history(report["preservation"]["results"])
    if args.write:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
        if args.apply_safe_reap:
            report["reap_history"] = append_reap_history(report, HISTORY_PATH)
        else:
            report["reap_history"] = load_reap_history(HISTORY_PATH)
        if not args.preserve_root:
            report["preservation_history"] = append_preservation_history([], PRESERVATION_HISTORY_PATH)
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
