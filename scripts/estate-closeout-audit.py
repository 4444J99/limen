#!/usr/bin/env python3
"""Build a whole-estate closeout audit receipt.

This is a read-only classifier. It does not merge, delete, reset, stash, or edit
the task board. With --write it only writes:

* docs/estate-closeout-audit.md: redacted, tracked summary.
* .limen-private/session-corpus/lifecycle/estate-closeout-audit.json: full local snapshot.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any


HOME = Path(os.environ.get("HOME", "/Users/4jp")).expanduser()
ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1])).expanduser()
LIVE_ROOT = Path(os.environ.get("LIMEN_LIVE_ROOT", HOME / "Workspace" / "limen")).expanduser()
DOC_PATH = ROOT / "docs" / "estate-closeout-audit.md"
PRIVATE_PATH = ROOT / ".limen-private" / "session-corpus" / "lifecycle" / "estate-closeout-audit.json"
TARGET_FREE_GIB = float(os.environ.get("LIMEN_ALWAYS_WORKING_TARGET_FREE_GIB", "200"))

DEFAULT_SCAN_ROOTS = (
    HOME / "Workspace",
    Path("/Volumes/Scratch"),
    Path("/Volumes/Archive4T"),
    HOME,
)
DEFAULT_PR_OWNERS = (
    "organvm",
    "4444J99",
    "a-organvm",
    "organvm-i-theoria",
    "organvm-ii-officium",
    "organvm-iii-ergon",
    "organvm-iv-taxis",
    "organvm-v-biblos",
    "organvm-v-logos",
    "organvm-vi-koinonia",
    "organvm-vii-physis",
)
SKIP_DIR_NAMES = {
    ".Trash",
    ".cache",
    ".next",
    ".npm",
    ".parcel-cache",
    ".pytest_cache",
    ".ruff_cache",
    ".turbo",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
}
PERSONAL_SKIP_PATHS = (
    HOME / "Library",
    HOME / "Pictures",
    HOME / "Movies",
    HOME / "Music",
)
GITHUB_REMOTE_RE = re.compile(r"(?:github\.com[:/])(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?$")
OWNED_REMOTE_OWNER_RE = re.compile(r"^(4444J99|a-organvm|organvm(?:-|$).*)$")


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run(
    args: list[str],
    cwd: Path | None = None,
    timeout: int = 30,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except Exception as exc:
        return subprocess.CompletedProcess(args, 1, "", str(exc))


def git(path: Path, *args: str, timeout: int = 10) -> subprocess.CompletedProcess[str]:
    return run(["git", *args], cwd=path, timeout=timeout)


def stable(path: Path | str) -> str:
    value = Path(path).expanduser()
    try:
        resolved = value.resolve()
    except OSError:
        resolved = value
    try:
        return "~/" + str(resolved.relative_to(HOME))
    except ValueError:
        return str(resolved)


def path_contains(parent: Path, child: Path) -> bool:
    try:
        child.expanduser().resolve().relative_to(parent.expanduser().resolve())
        return True
    except (OSError, ValueError):
        return False


def compact_roots(paths: list[Path]) -> list[Path]:
    existing: list[Path] = []
    for raw in paths:
        path = raw.expanduser()
        if path.exists() and path not in existing:
            existing.append(path)
    # Prefer focused roots first. Nested roots are still recorded as requested
    # roots, but skipped during broader parent scans to avoid double walking.
    return existing


def should_prune(path: Path, active_roots: list[Path]) -> bool:
    name = path.name
    if name in SKIP_DIR_NAMES:
        return True
    for personal in PERSONAL_SKIP_PATHS:
        if path == personal:
            return True
    for root in active_roots:
        if path != root and path_contains(path, root):
            return True
    return False


def discover_git_roots(
    roots: list[Path],
    *,
    max_roots: int,
    max_seconds: float,
) -> dict[str, Any]:
    started = time.monotonic()
    seen: set[str] = set()
    found: list[dict[str, Any]] = []
    skipped_roots: list[str] = []
    truncated_reason: str | None = None
    active_roots = compact_roots(roots)

    for scan_root in active_roots:
        if time.monotonic() - started > max_seconds:
            truncated_reason = "scan-timeout"
            break
        try:
            walker = os.walk(scan_root)
            for dirpath, dirnames, filenames in walker:
                current = Path(dirpath)
                if time.monotonic() - started > max_seconds:
                    truncated_reason = "scan-timeout"
                    break
                if len(found) >= max_roots:
                    truncated_reason = "max-local-roots"
                    break
                pruned = []
                keep = []
                for dirname in dirnames:
                    child = current / dirname
                    if should_prune(child, [r for r in active_roots if r != scan_root]):
                        pruned.append(stable(child))
                    else:
                        keep.append(dirname)
                dirnames[:] = keep
                if ".git" in dirnames or ".git" in filenames:
                    repo_path = current
                    try:
                        key = str(repo_path.resolve())
                    except OSError:
                        key = str(repo_path)
                    if key not in seen:
                        seen.add(key)
                        found.append({"path": str(repo_path), "display_path": stable(repo_path)})
                    if ".git" in dirnames:
                        dirnames.remove(".git")
                if pruned and len(skipped_roots) < 60:
                    skipped_roots.extend(pruned[: max(0, 60 - len(skipped_roots))])
            if truncated_reason:
                break
        except OSError as exc:
            skipped_roots.append(f"{stable(scan_root)} ({exc})")
    return {
        "requested_roots": [stable(path) for path in roots],
        "scanned_roots": [stable(path) for path in active_roots],
        "git_roots_found": found,
        "git_roots_count": len(found),
        "truncated": truncated_reason is not None,
        "truncated_reason": truncated_reason,
        "sample_pruned_paths": skipped_roots[:60],
        "scan_seconds": round(time.monotonic() - started, 2),
    }


def github_slug(remote: str | None) -> str | None:
    if not remote:
        return None
    match = GITHUB_REMOTE_RE.search(remote.strip())
    if not match:
        return None
    repo = match.group("repo").removesuffix(".git")
    return f"{match.group('owner')}/{repo}"


def owner_for(path: Path, repo: str | None) -> str:
    if path_contains(ROOT, path):
        return "organvm/limen"
    if path_contains(HOME / "Workspace" / ".limen-worktrees", path) or path_contains(
        Path("/Volumes/Scratch/limen-worktrees"), path
    ):
        return "docs/worktree-reclaim-acceptance.md"
    if path_contains(HOME / ".gemini" / "antigravity-cli" / "scratch", path):
        return "docs/antigravity-scratch-bridge.md"
    if path_contains(HOME / ".gemini" / "antigravity-cli" / "brain", path):
        return "agy conductor brain custody"
    if ".claude" in path.parts:
        return "claude session/worktree custody"
    if ".local" in path.parts and "codex" in path.parts:
        return "codex local plugin/memory custody"
    if path_contains(Path("/Volumes/Archive4T"), path):
        return "Archive4T custody"
    if repo:
        return repo
    return "local owner route required"


def classify_local(path: Path, *, probe_pr: bool) -> dict[str, Any]:
    row: dict[str, Any] = {
        "path": str(path),
        "display_path": stable(path),
        "exists": path.exists(),
    }
    if not path.exists():
        row.update({"status": "missing", "deletion_eligibility": "not_eligible_missing"})
        return row

    remote = git(path, "config", "--get", "remote.origin.url", timeout=5).stdout.strip()
    repo = github_slug(remote)
    branch = git(path, "rev-parse", "--abbrev-ref", "HEAD", timeout=5).stdout.strip()
    head = git(path, "rev-parse", "--short=12", "HEAD", timeout=5).stdout.strip()
    status_proc = git(path, "status", "--porcelain", timeout=10)
    status_lines = [line for line in status_proc.stdout.splitlines() if line.strip()]
    upstream = git(path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", timeout=5).stdout.strip()
    ahead = behind = None
    if upstream:
        counts = git(path, "rev-list", "--left-right", "--count", f"HEAD...{upstream}", timeout=10).stdout.split()
        if len(counts) == 2:
            try:
                ahead = int(counts[0])
                behind = int(counts[1])
            except ValueError:
                ahead = behind = None
    default_ref = ""
    for candidate in ("origin/main", "origin/master"):
        if git(path, "show-ref", "--verify", "--quiet", f"refs/remotes/{candidate}", timeout=5).returncode == 0:
            default_ref = candidate
            break
    merged_to_default = None
    if default_ref and head:
        merged_to_default = git(path, "merge-base", "--is-ancestor", "HEAD", default_ref, timeout=10).returncode == 0

    pr_links: list[dict[str, Any]] = []
    pr_probe_status = "not-probed"
    if probe_pr and repo and branch and branch != "HEAD":
        pr = run(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                repo,
                "--head",
                branch,
                "--state",
                "open",
                "--json",
                "number,url,isDraft,state,baseRefName,headRefName",
            ],
            timeout=25,
        )
        if pr.returncode == 0:
            try:
                parsed = json.loads(pr.stdout or "[]")
                pr_links = parsed if isinstance(parsed, list) else []
                pr_probe_status = "ok"
            except ValueError:
                pr_probe_status = "invalid-json"
        else:
            pr_probe_status = (pr.stderr or pr.stdout or "gh-failed").strip()[:200]

    if status_lines:
        eligibility = "blocked_dirty"
    elif ahead and ahead > 0 and not pr_links:
        eligibility = "blocked_unpushed_or_unpreserved"
    elif default_ref and merged_to_default is False:
        eligibility = "blocked_not_merged_to_default"
    elif pr_links:
        eligibility = "blocked_remote_pr_open"
    else:
        eligibility = "owner_review_required"

    row.update(
        {
            "repo": repo,
            "origin": remote,
            "branch": branch,
            "head": head,
            "dirty": bool(status_lines),
            "dirty_entries": len(status_lines),
            "upstream": upstream,
            "ahead": ahead,
            "behind": behind,
            "default_ref": default_ref,
            "merged_to_default": merged_to_default,
            "owner": owner_for(path, repo),
            "open_prs": pr_links,
            "pr_probe_status": pr_probe_status,
            "deletion_eligibility": eligibility,
        }
    )
    return row


def summarize_local(rows: list[dict[str, Any]], discovery: dict[str, Any]) -> dict[str, Any]:
    by_owner = collections.Counter(str(row.get("owner") or "unknown") for row in rows)
    by_eligibility = collections.Counter(str(row.get("deletion_eligibility") or "unknown") for row in rows)
    by_repo = collections.Counter(str(row.get("repo") or "no-github-remote") for row in rows)
    dirty = [row for row in rows if row.get("dirty")]
    unpushed = [row for row in rows if row.get("ahead") and not row.get("open_prs")]
    open_pr_local = [row for row in rows if row.get("open_prs")]
    return {
        "discovery": discovery,
        "probed_roots": len(rows),
        "by_owner": dict(by_owner.most_common(25)),
        "by_deletion_eligibility": dict(by_eligibility.most_common()),
        "top_repos": by_repo.most_common(25),
        "dirty_roots": len(dirty),
        "unpushed_or_unpreserved_roots": len(unpushed),
        "local_roots_with_open_pr": len(open_pr_local),
        "sample_dirty_roots": [
            {"path": row.get("display_path"), "repo": row.get("repo"), "dirty_entries": row.get("dirty_entries")}
            for row in dirty[:20]
        ],
        "sample_unpushed_roots": [
            {"path": row.get("display_path"), "repo": row.get("repo"), "ahead": row.get("ahead")}
            for row in unpushed[:20]
        ],
    }


def disk_snapshot() -> dict[str, Any]:
    rows = []
    for path in (Path("/System/Volumes/Data"), HOME, HOME / "Workspace", Path("/Volumes/Scratch"), Path("/Volumes/Archive4T")):
        if not path.exists():
            rows.append({"path": stable(path), "exists": False})
            continue
        try:
            stat = os.statvfs(path)
            free_gib = round((stat.f_bavail * stat.f_frsize) / 1024**3, 1)
            total_gib = round((stat.f_blocks * stat.f_frsize) / 1024**3, 1)
        except OSError as exc:
            rows.append({"path": stable(path), "exists": True, "error": str(exc)})
            continue
        rows.append({"path": stable(path), "exists": True, "free_gib": free_gib, "total_gib": total_gib})
    internal = next((row for row in rows if row.get("path") == "/System/Volumes/Data"), rows[0] if rows else {})
    free = internal.get("free_gib")
    shortfall = round(max(TARGET_FREE_GIB - float(free), 0), 1) if isinstance(free, (int, float)) else None
    return {
        "target_free_gib": TARGET_FREE_GIB,
        "internal_free_gib": free,
        "internal_shortfall_gib": shortfall,
        "filesystems": rows,
        "status": "needs-owner-gates" if shortfall else "clear",
    }


def run_json_command(args: list[str], timeout: int = 120) -> dict[str, Any]:
    proc = run(args, cwd=ROOT, timeout=timeout)
    if proc.returncode != 0:
        return {"ok": False, "returncode": proc.returncode, "error": (proc.stderr or proc.stdout).strip()[:2000]}
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        return {"ok": False, "returncode": proc.returncode, "error": "invalid JSON", "stdout": proc.stdout[:2000]}
    return {"ok": True, "data": data}


def run_text_command(args: list[str], timeout: int = 120, env: dict[str, str] | None = None) -> dict[str, Any]:
    proc = run(args, cwd=ROOT, timeout=timeout, env=env)
    text = proc.stdout or proc.stderr
    status_match = re.search(r"Status:\s*`?([A-Za-z0-9_-]+)`?", text)
    blockers: list[str] = []
    if "## Blockers" in text:
        blockers = re.findall(r"- `([^`]+)`(?::|$)", text.split("## Blockers", 1)[-1])
    if not blockers:
        match = re.search(r"Blocking gates:\s*`([^`]+)`", text)
        if match:
            blockers = [item.strip() for item in match.group(1).split(",") if item.strip()]
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "status": status_match.group(1) if status_match else None,
        "blockers": blockers[:20],
        "tail": "\n".join(text.splitlines()[-30:]),
    }


def query_remote_prs(owners: list[str], *, limit: int, classify_limit: int) -> dict[str, Any]:
    args = [
        "gh",
        "search",
        "prs",
        "--state",
        "open",
        "--limit",
        str(limit),
        "--json",
        "number,repository,title,url,isDraft,createdAt,updatedAt",
    ]
    for owner in owners:
        args.extend(["--owner", owner])
    proc = run(args, cwd=ROOT, timeout=120)
    if proc.returncode != 0:
        return {
            "ok": False,
            "owners": owners,
            "limit": limit,
            "error": (proc.stderr or proc.stdout or "gh search failed").strip()[:2000],
        }
    try:
        rows = json.loads(proc.stdout or "[]")
    except ValueError as exc:
        return {"ok": False, "owners": owners, "limit": limit, "error": f"invalid gh JSON: {exc}"}
    if not isinstance(rows, list):
        rows = []
    by_repo = collections.Counter(str(row.get("repository", {}).get("nameWithOwner")) for row in rows)
    draft = [row for row in rows if row.get("isDraft")]
    non_draft = [row for row in rows if not row.get("isDraft")]
    classified = classify_remote_prs(non_draft[:classify_limit])
    by_class = collections.Counter(row.get("classification", "unclassified") for row in classified)
    return {
        "ok": True,
        "owners": owners,
        "limit": limit,
        "hit_limit": len(rows) >= limit,
        "total_returned": len(rows),
        "draft": len(draft),
        "non_draft": len(non_draft),
        "repos": len(by_repo),
        "top_repos": by_repo.most_common(25),
        "deep_classify_limit": classify_limit,
        "deep_classified": len(classified),
        "unclassified_due_to_bounds": max(0, len(rows) - len(classified)),
        "by_classification": dict(by_class),
        "merge_ready_candidates": [
            row for row in classified if row.get("classification") == "mergeable_needs_owner_review"
        ][:20],
        "blocked_samples": [row for row in classified if row.get("classification") != "mergeable_needs_owner_review"][
            :30
        ],
    }


def status_state(value: str | None) -> str:
    return str(value or "").upper()


def classify_remote_prs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        repo = str(row.get("repository", {}).get("nameWithOwner") or "")
        number = str(row.get("number") or "")
        view = run(
            [
                "gh",
                "pr",
                "view",
                number,
                "--repo",
                repo,
                "--json",
                "number,url,title,isDraft,mergeable,mergeStateStatus,state,statusCheckRollup,baseRefName,headRefOid",
            ],
            cwd=ROOT,
            timeout=45,
        )
        if view.returncode != 0:
            out.append(
                {
                    "repo": repo,
                    "number": row.get("number"),
                    "url": row.get("url"),
                    "classification": "unclassified",
                    "detail": (view.stderr or view.stdout or "gh pr view failed").strip()[:200],
                }
            )
            continue
        try:
            data = json.loads(view.stdout or "{}")
        except ValueError:
            data = {}
        checks = data.get("statusCheckRollup") if isinstance(data.get("statusCheckRollup"), list) else []
        states = [status_state(check.get("conclusion") or check.get("state")) for check in checks if isinstance(check, dict)]
        if data.get("isDraft"):
            classification = "draft"
        elif data.get("mergeable") == "CONFLICTING":
            classification = "conflict_blocked"
        elif any(state in {"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"} for state in states):
            classification = "ci_blocked"
        elif any(state in {"PENDING", "IN_PROGRESS", "QUEUED", "EXPECTED", ""} for state in states):
            classification = "ci_pending"
        elif data.get("mergeable") == "MERGEABLE":
            classification = "mergeable_needs_owner_review"
        else:
            classification = "owner_blocked_or_unclassified"
        out.append(
            {
                "repo": repo,
                "number": data.get("number") or row.get("number"),
                "url": data.get("url") or row.get("url"),
                "title": data.get("title") or row.get("title"),
                "classification": classification,
                "mergeable": data.get("mergeable"),
                "merge_state": data.get("mergeStateStatus"),
                "check_states": dict(collections.Counter(states)),
            }
        )
    return out


def redacted_rows(rows: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    redacted = []
    for row in rows[:limit]:
        redacted.append(
            {
                "path": row.get("display_path"),
                "repo": row.get("repo"),
                "branch": row.get("branch"),
                "dirty": row.get("dirty"),
                "ahead": row.get("ahead"),
                "behind": row.get("behind"),
                "owner": row.get("owner"),
                "deletion_eligibility": row.get("deletion_eligibility"),
            }
        )
    return redacted


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    roots = [Path(path).expanduser() for path in (args.root or DEFAULT_SCAN_ROOTS)]
    discovery = discover_git_roots(roots, max_roots=args.max_local_roots, max_seconds=args.scan_seconds)
    rows = []
    pr_probed = 0
    for entry in discovery["git_roots_found"]:
        if len(rows) >= args.local_detail_limit:
            break
        path = Path(entry["path"])
        probe_pr = pr_probed < args.local_pr_probe_limit
        row = classify_local(path, probe_pr=probe_pr)
        if probe_pr:
            pr_probed += 1
        rows.append(row)

    local_summary = summarize_local(rows, discovery)
    owner_set = set(args.pr_owner or DEFAULT_PR_OWNERS)
    for slug in local_repos(rows):
        owner = slug.split("/", 1)[0]
        if OWNED_REMOTE_OWNER_RE.match(owner):
            owner_set.add(owner)
    owners = sorted(owner_set)[:16]
    if args.skip_heavy_gates:
        skipped = {"ok": False, "skipped": True, "reason": "--skip-heavy-gates"}
        worktree_debt = skipped
        reclaim_check = skipped
        storage_pressure = skipped
        session_value_gate = skipped
        dispatch_health = skipped
        live_root_gate = skipped
    else:
        worktree_debt = run_json_command(["python3", "scripts/worktree-debt.py", "--json"], timeout=180)
        reclaim_check = run_json_command(["python3", "scripts/reclaim-worktrees.py", "--force", "--json"], timeout=180)
        storage_pressure = run_json_command(["python3", "scripts/substrate-storage-pressure.py", "--json"], timeout=180)
        session_value_gate = run_json_command(
            ["python3", "scripts/session-value-review.py", "--gate", "--hours", "72", "--no-record-gate"],
            timeout=180,
        )
        live_root_env = {
            **os.environ,
            "LIMEN_ROOT": str(LIVE_ROOT),
            "LIMEN_LIVE_ROOT": str(LIVE_ROOT),
        }
        dispatch_health = run_text_command(
            ["python3", "scripts/dispatch-health.py", "--probe-async"],
            timeout=180,
            env=live_root_env,
        )
        live_root_gate = run_text_command(["python3", "scripts/live-root-gate.py"], timeout=120, env=live_root_env)

    return {
        "schema": "limen.estate_closeout_audit.v1",
        "generated_at": utc_now(),
        "status": "blocked",
        "contract": {
            "read_only": True,
            "deletion_authorized": False,
            "merge_authorized": False,
            "reason": "inventory and owner-routing receipt only; merge/delete remain behind their owner gates",
        },
        "bounds": {
            "scan_seconds": args.scan_seconds,
            "max_local_roots": args.max_local_roots,
            "local_detail_limit": args.local_detail_limit,
            "local_pr_probe_limit": args.local_pr_probe_limit,
            "remote_pr_limit": args.remote_pr_limit,
            "remote_pr_classify_limit": args.remote_pr_classify_limit,
        },
        "disk": disk_snapshot(),
        "worktree_debt": worktree_debt,
        "reclaim_check": reclaim_check,
        "storage_pressure": storage_pressure,
        "session_value_gate": session_value_gate,
        "dispatch_health": dispatch_health,
        "live_root_gate": live_root_gate,
        "local_estate": {**local_summary, "roots": rows},
        "remote_prs": query_remote_prs(
            owners,
            limit=args.remote_pr_limit,
            classify_limit=args.remote_pr_classify_limit,
        ),
    }


def local_repos(rows: list[dict[str, Any]]) -> set[str]:
    return {str(row.get("repo")) for row in rows if row.get("repo") and "/" in str(row.get("repo"))}


def fmt_count_map(mapping: dict[str, Any], *, limit: int = 20) -> list[str]:
    lines = []
    for key, value in list(mapping.items())[:limit]:
        lines.append(f"| `{key}` | `{value}` |")
    if not lines:
        lines.append("| `(none)` | `0` |")
    return lines


def fmt_pr_ref(row: dict[str, Any]) -> str:
    repo = row.get("repo")
    number = row.get("number")
    url = row.get("url")
    title = str(row.get("title") or "").replace("|", "\\|")
    if url:
        return f"| `{repo}#{number}` | [{title}]({url}) | `{row.get('classification')}` |"
    return f"| `{repo}#{number}` | {title} | `{row.get('classification')}` |"


def render(snapshot: dict[str, Any]) -> str:
    disk = snapshot.get("disk", {})
    worktree = (snapshot.get("worktree_debt") or {}).get("data") or {}
    reclaim = (snapshot.get("reclaim_check") or {}).get("data") or {}
    local = snapshot.get("local_estate", {})
    remote = snapshot.get("remote_prs", {})
    remote_ok = remote.get("ok") is True
    session = ((snapshot.get("session_value_gate") or {}).get("data") or {})
    dispatch = snapshot.get("dispatch_health") or {}
    live = snapshot.get("live_root_gate") or {}

    lines = [
        "# Estate Closeout Audit",
        "",
        f"Generated: `{snapshot.get('generated_at')}`",
        "Status: `blocked`",
        "",
        "## Verdict",
        "",
        "- Whole-estate closeout is not done.",
        f"- Internal free space is `{disk.get('internal_free_gib')} GiB`; target is `{disk.get('target_free_gib')} GiB`; shortfall is `{disk.get('internal_shortfall_gib')} GiB`.",
        f"- Worktree debt is `{worktree.get('debt')}` debt roots / `{worktree.get('total')}` scanned; reapable roots `{worktree.get('reapable')}`.",
        f"- Remote PR search returned `{remote.get('total_returned') if remote_ok else 'unavailable'}` open PRs across `{remote.get('repos') if remote_ok else 'unavailable'}` repos; query hit limit `{remote.get('hit_limit') if remote_ok else 'unavailable'}`.",
        f"- Live root gate is `{live.get('status')}`; dispatch health is `{dispatch.get('status')}`.",
        "",
        "## Contract",
        "",
        "- This receipt is read-only. It does not merge PRs, delete roots, reset branches, stash work, or edit `tasks.yaml`.",
        "- Deletion stays gated by merged, patch-equivalent, idle, externally preserved, or explicit owner-accepted proof.",
        "- PR merges remain owner-gated; merge-ready means candidate for Anthony/owner review, not auto-merged.",
        "",
        "## Disk",
        "",
        "| Path | Free GiB | Total GiB |",
        "|---|---:|---:|",
    ]
    for row in disk.get("filesystems") or []:
        lines.append(f"| `{row.get('path')}` | `{row.get('free_gib', 'n/a')}` | `{row.get('total_gib', 'n/a')}` |")

    lines += [
        "",
        "## Worktree / Reclaim",
        "",
        f"- Debt cap: `{worktree.get('limit')}`; reapable cap: `{worktree.get('reapable_limit')}`.",
        f"- Reclaim dry-run reapable count: `{reclaim.get('reapable_count')}`.",
        "",
        "| Reason | Roots |",
        "|---|---:|",
        *fmt_count_map(worktree.get("by_reason") or {}),
        "",
        "## Local Git Estate",
        "",
        f"- Git roots discovered: `{local.get('discovery', {}).get('git_roots_count')}`.",
        f"- Git roots probed in detail: `{local.get('probed_roots')}`.",
        f"- Discovery truncated: `{local.get('discovery', {}).get('truncated')}` (`{local.get('discovery', {}).get('truncated_reason')}`).",
        f"- Dirty roots among probed roots: `{local.get('dirty_roots')}`.",
        f"- Unpushed or unpreserved roots among probed roots: `{local.get('unpushed_or_unpreserved_roots')}`.",
        "",
        "| Deletion Eligibility | Roots |",
        "|---|---:|",
        *fmt_count_map(local.get("by_deletion_eligibility") or {}),
        "",
        "### Sample Dirty Roots",
        "",
        "| Path | Repo | Dirty Entries |",
        "|---|---|---:|",
    ]
    for row in local.get("sample_dirty_roots") or []:
        lines.append(f"| `{row.get('path')}` | `{row.get('repo')}` | `{row.get('dirty_entries')}` |")
    if not local.get("sample_dirty_roots"):
        lines.append("| `(none)` |  | `0` |")

    lines += [
        "",
        "## Remote PR Estate",
        "",
        f"- Owners queried: `{', '.join(remote.get('owners') or [])}`.",
        f"- Query status: `{'ok' if remote_ok else 'failed'}`.",
        f"- Open PRs returned: `{remote.get('total_returned') if remote_ok else 'unavailable'}`; draft `{remote.get('draft') if remote_ok else 'unavailable'}`; non-draft `{remote.get('non_draft') if remote_ok else 'unavailable'}`.",
        f"- Search hit limit: `{remote.get('hit_limit') if remote_ok else 'unavailable'}`; unclassified due to bounds: `{remote.get('unclassified_due_to_bounds') if remote_ok else 'unavailable'}`.",
        "",
        "| Classification | PRs In Deep Sample |",
        "|---|---:|",
        *fmt_count_map(remote.get("by_classification") or {}),
        "",
        "### Merge-Ready Candidate Sample",
        "",
        "| PR | Title | Classification |",
        "|---|---|---|",
    ]
    for row in remote.get("merge_ready_candidates") or []:
        lines.append(fmt_pr_ref(row))
    if not remote.get("merge_ready_candidates"):
        lines.append("| `(none in bounded sample)` |  |  |")
    if not remote_ok:
        lines += ["", f"- Remote PR error: `{str(remote.get('error', 'unknown'))[:500]}`."]

    lines += [
        "",
        "## Prompt / Session Lifecycle",
        "",
        f"- Gate action: `{session.get('action')}`.",
        f"- Reason: {session.get('reason', 'unavailable')}",
        f"- Follow-up roots: `{(session.get('pressures') or {}).get('followup_roots')}`.",
        f"- Done or routed roots: `{(session.get('pressures') or {}).get('done_or_routed_roots')}`.",
        "",
        "## Current Blockers",
        "",
        f"- Live root: `{live.get('status')}`; blockers: `{', '.join(live.get('blockers') or ['none'])}`.",
        f"- Dispatch health: `{dispatch.get('status')}`; blockers: `{', '.join(dispatch.get('blockers') or ['none'])}`.",
        f"- Remote PR classification is incomplete because search returned the cap or failed: `{remote.get('hit_limit') if remote_ok else 'failed'}`.",
        f"- Local Git estate classification is bounded; truncated: `{local.get('discovery', {}).get('truncated')}`.",
        "",
        "## Next Owner Commands",
        "",
        "- `python3 scripts/estate-closeout-audit.py --write --remote-pr-classify-limit 250`",
        "- `python3 scripts/worktree-pr-receipts.py --apply` only for clean local work that needs draft PR custody.",
        "- `python3 scripts/self-heal.py --dry-run --scan 1000 --scan-max 1000` to queue exact PR repair candidates without mutating.",
        "- `python3 scripts/merge-drain.py --dry-run --scan 1000 --scan-max 1000 --limit 0` to refresh merge-ready candidates without merging.",
        "- `python3 scripts/substrate-storage-pressure.py --write` to keep byte owners current.",
    ]
    return "\n".join(lines) + "\n"


def write(snapshot: dict[str, Any]) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(render(snapshot), encoding="utf-8")
    PRIVATE_PATH.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a read-only whole-estate closeout audit receipt.")
    parser.add_argument("--write", action="store_true", help="write tracked Markdown and private JSON receipts")
    parser.add_argument("--json", action="store_true", help="print the full JSON snapshot")
    parser.add_argument("--root", action="append", help="root to scan; repeatable")
    parser.add_argument("--scan-seconds", type=float, default=float(os.environ.get("LIMEN_ESTATE_SCAN_SECONDS", "75")))
    parser.add_argument("--max-local-roots", type=int, default=int(os.environ.get("LIMEN_ESTATE_MAX_ROOTS", "1400")))
    parser.add_argument(
        "--local-detail-limit",
        type=int,
        default=int(os.environ.get("LIMEN_ESTATE_LOCAL_DETAIL_LIMIT", "900")),
    )
    parser.add_argument(
        "--local-pr-probe-limit",
        type=int,
        default=int(os.environ.get("LIMEN_ESTATE_LOCAL_PR_PROBE_LIMIT", "120")),
    )
    parser.add_argument("--pr-owner", action="append", help="GitHub owner/org to include in remote PR search")
    parser.add_argument("--remote-pr-limit", type=int, default=int(os.environ.get("LIMEN_ESTATE_PR_LIMIT", "1000")))
    parser.add_argument(
        "--remote-pr-classify-limit",
        type=int,
        default=int(os.environ.get("LIMEN_ESTATE_PR_CLASSIFY_LIMIT", "120")),
    )
    parser.add_argument(
        "--skip-heavy-gates",
        action="store_true",
        help="skip existing slow live/worktree/storage gates for fast script validation only",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    snapshot = build_snapshot(args)
    if args.write:
        write(snapshot)
    if args.json or not args.write:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
    else:
        local = snapshot.get("local_estate", {})
        remote = snapshot.get("remote_prs", {})
        disk = snapshot.get("disk", {})
        print(
            "estate-closeout-audit: "
            f"status={snapshot.get('status')} "
            f"free={disk.get('internal_free_gib')}GiB "
            f"shortfall={disk.get('internal_shortfall_gib')}GiB "
            f"git_roots={local.get('discovery', {}).get('git_roots_count')} "
            f"open_prs_returned={remote.get('total_returned')} "
            f"remote_pr_hit_limit={remote.get('hit_limit')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
