"""Git, worktree, and pull-request custody for completed Jules sessions.

This module owns the external repository state machine. It deliberately does
not mutate the Limen task board; :mod:`limen.jules_landing_transaction` owns
that compare-and-swap transaction.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from limen.dispatch import _default_branch, _git, _resolve_repo_dir
from limen.jules_remote import JulesRemoteSnapshot, probe_jules_remote_sessions
from limen.models import Task
from limen.worktree_roots import default_worktrees_root

WT_ROOT = Path(os.environ.get("LIMEN_WORKTREES") or default_worktrees_root())
JULES = os.environ.get("LIMEN_JULES_BIN", "jules")
_TASK_ID_RE = re.compile(r"Complete task (\S+?):")
_GENERATED_CLEAN_PATHS = (
    "node_modules",
    ".venv",
    ".next",
    "dist",
    "build",
    "coverage",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".parcel-cache",
    ".turbo",
    "__pycache__",
)


class ClosedUnmergedPR(RuntimeError):
    """The deterministic branch already owns a closed, unmerged PR."""


def landing_branch(task_id: str, session_id: str) -> str:
    """Return stable branch identity for one task/session across retries."""
    slug = re.sub(r"[^a-z0-9]+", "-", task_id.lower()).strip("-")[:48] or "task"
    digest = hashlib.sha256(f"{task_id}\0{session_id}".encode()).hexdigest()[:12]
    return f"limen/jules-{slug}-{digest}"


def purge_generated_payloads(wt: Path) -> str:
    """Remove only ignored generated payloads from a retained worktree."""
    if not wt.exists():
        return "missing"
    clean = _git(["clean", "-Xdf", "--", *_GENERATED_CLEAN_PATHS], wt, timeout=180)
    if clean.returncode != 0:
        return f"failed:{(clean.stderr or clean.stdout).strip()[:160]}"
    removed = sum(1 for line in (clean.stdout or "").splitlines() if line.strip().startswith("Removing "))
    return f"removed:{removed}"


def completed_sessions(
    sid_map: dict[str, str] | None = None,
    snapshot: JulesRemoteSnapshot | None = None,
) -> list[tuple[str, str]]:
    """Return ``(session_id, task_id)`` for every completed Jules session."""
    sid_map = sid_map or {}
    remote = snapshot or probe_jules_remote_sessions(binary=JULES)
    if not remote.available:
        return []
    out: list[tuple[str, str]] = []
    for session in remote.sessions.values():
        if session.status != "completed":
            continue
        sid = session.session_id
        match = _TASK_ID_RE.search(session.raw)
        out.append((sid, sid_map.get(sid) or (match.group(1) if match else "")))
    return sorted(out)


def _target_branch_oid(repo: str, branch: str) -> str | None:
    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repo}/git/ref/heads/{branch}",
            "--jq",
            ".object.sha",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode == 0:
        oid = result.stdout.strip()
        if not oid:
            raise RuntimeError(f"target branch {branch} returned no head OID")
        return oid
    detail = (result.stderr or result.stdout or "gh api failed").strip()
    if "404" in detail or "not found" in detail.casefold():
        return None
    raise RuntimeError(f"target branch lookup failed: {detail[:160]}")


def _existing_pr_url(
    repo: str,
    branch: str,
    *,
    expected_head_oid: str | None = None,
) -> str:
    repo_parts = repo.split("/", 1)
    if len(repo_parts) != 2 or not all(repo_parts):
        raise RuntimeError(f"invalid target repository identity: {repo}")
    expected_owner = repo_parts[0].casefold()
    result = subprocess.run(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            repo,
            "--head",
            branch,
            "--state",
            "all",
            "--limit",
            "20",
            "--json",
            "number,url,state,mergedAt,headRefName,headRefOid,headRepositoryOwner",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "gh pr list failed").strip()[:160])
    try:
        rows = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"gh pr list returned invalid JSON: {exc}") from exc
    if not isinstance(rows, list):
        raise RuntimeError("gh pr list returned a non-list result")
    owned_matching: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError("gh pr list returned a malformed PR row")
        if str(row.get("headRefName") or "") != branch:
            continue
        owner_value = row.get("headRepositoryOwner")
        if isinstance(owner_value, dict):
            head_owner = str(owner_value.get("login") or "")
        else:
            head_owner = str(owner_value or "")
        if head_owner.casefold() != expected_owner:
            continue
        head_oid = str(row.get("headRefOid") or "")
        if not head_oid:
            raise RuntimeError(f"gh pr list returned no head OID for {branch}")
        url = str(row.get("url") or "")
        if "/pull/" not in url:
            raise RuntimeError(f"gh pr list returned a non-PR result: {url[:120]}")
        owned_matching.append(row)
    current_head_oid = expected_head_oid
    if current_head_oid is None and owned_matching:
        current_head_oid = _target_branch_oid(repo, branch)
    matching = [
        row
        for row in owned_matching
        if current_head_oid is None or str(row.get("headRefOid") or "") == current_head_oid
    ]
    if matching:
        latest = max(matching, key=lambda row: int(str(row.get("number") or 0)))
        state = str(latest.get("state") or "").upper()
        if state == "OPEN" or state == "MERGED" or bool(latest.get("mergedAt")):
            return str(latest["url"])
        raise ClosedUnmergedPR(f"closed-unmerged PR for {branch}: {str(latest['url'])[:240]}")
    return ""


def _retention_note(wt: Path, branch: str) -> str:
    return (
        f"local root retained: {wt}; branch retained: {branch}; "
        "cleanup delegated to docs/worktree-reclaim-acceptance.jsonl + "
        "reclaim-worktrees.py and docs/branch-reap-acceptance.jsonl + reap-branches.py"
    )


def _create_or_adopt_pr(
    task: Task,
    sid: str,
    branch: str,
    base: str,
    *,
    expected_head_oid: str,
) -> str:
    """Create the deterministic PR, adopting it if another retry won the race."""
    repo = str(task.repo)
    try:
        existing_pr = _existing_pr_url(
            repo,
            branch,
            expected_head_oid=expected_head_oid,
        )
    except ClosedUnmergedPR as exc:
        return f"BLOCKED {task.id}: {exc}"
    except RuntimeError as exc:
        return f"FAIL {task.id}: existing PR lookup ({exc})"
    if existing_pr:
        return f"LANDED {task.id} -> {existing_pr} ; adopted existing PR for {branch}"
    pr = subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--repo",
            repo,
            "--head",
            branch,
            "--base",
            base,
            "--title",
            f"[limen jules {task.id}] {task.title}"[:100],
            "--body",
            f"Lands completed jules session {sid}.\n\nlimen task {task.id}",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if pr.returncode == 0:
        try:
            created_pr = _existing_pr_url(
                repo,
                branch,
                expected_head_oid=expected_head_oid,
            )
        except ClosedUnmergedPR as exc:
            return f"BLOCKED {task.id}: {exc}"
        except RuntimeError:
            created_pr = ""
        if created_pr:
            return f"LANDED {task.id} -> {created_pr} ; verified created PR for {branch}"
        return f"FAIL {task.id}: pr create succeeded without a discoverable PR URL"
    try:
        existing_pr = _existing_pr_url(
            repo,
            branch,
            expected_head_oid=expected_head_oid,
        )
    except ClosedUnmergedPR as exc:
        return f"BLOCKED {task.id}: {exc}"
    except RuntimeError:
        existing_pr = ""
    if existing_pr:
        return f"LANDED {task.id} -> {existing_pr} ; adopted existing PR after create race"
    detail = (pr.stderr or pr.stdout).strip()[:120]
    return f"FAIL {task.id}: pr create ({detail})"


def land_one(
    task: Task,
    sid: str,
    apply: bool,
    *,
    branch: str | None = None,
) -> str:
    """Land one completed Jules session into durable Git and PR custody."""
    branch = branch or landing_branch(task.id, sid)
    if not apply:
        repo_dir = _resolve_repo_dir(task)
        if repo_dir is None:
            return f"BLOCKED {task.id}: no local checkout of {task.repo}"
        base = _default_branch(repo_dir)
        return f"would land {task.id} <- jules session {sid} into {task.repo} (base {base})"
    try:
        existing_pr = _existing_pr_url(str(task.repo), branch)
    except ClosedUnmergedPR as exc:
        return f"BLOCKED {task.id}: {exc}"
    except RuntimeError as exc:
        return f"FAIL {task.id}: existing PR lookup ({exc})"
    if existing_pr:
        return f"LANDED {task.id} -> {existing_pr} ; adopted existing PR for {branch}"
    repo_dir = _resolve_repo_dir(task)
    if repo_dir is None:
        return f"BLOCKED {task.id}: no local checkout of {task.repo}"
    base = _default_branch(repo_dir)
    fetch = _git(["fetch", "origin", base], repo_dir, timeout=300)
    if fetch.returncode != 0:
        detail = (fetch.stderr or fetch.stdout or "git fetch failed").strip()[:160]
        return f"FAIL {task.id}: fetch origin/{base} ({detail})"
    wt = WT_ROOT / branch.replace("/", "_")
    WT_ROOT.mkdir(parents=True, exist_ok=True)
    retain = _retention_note(wt, branch)

    remote_branch = _git(
        ["ls-remote", "--exit-code", "--heads", "origin", branch],
        repo_dir,
        timeout=120,
    )
    if remote_branch.returncode == 0:
        remote_fields = remote_branch.stdout.split()
        if not remote_fields:
            return f"FAIL {task.id}: remote branch {branch} had no discoverable head OID"
        result = _create_or_adopt_pr(
            task,
            sid,
            branch,
            base,
            expected_head_oid=remote_fields[0],
        )
        generated_cleanup = purge_generated_payloads(wt)
        return f"{result} ; generated cleanup {generated_cleanup}; {retain}"
    if remote_branch.returncode != 2:
        detail = (remote_branch.stderr or remote_branch.stdout or "git ls-remote failed").strip()[:160]
        return f"FAIL {task.id}: remote branch probe for {branch} ({detail})"

    if wt.exists():
        current_branch = _git(["symbolic-ref", "--quiet", "--short", "HEAD"], wt)
        if current_branch.returncode != 0 or current_branch.stdout.strip() != branch:
            detail = (current_branch.stderr or current_branch.stdout or "not a git worktree").strip()[:120]
            return f"BLOCKED {task.id}: retained path {wt} is not deterministic branch {branch} ({detail})"
    else:
        local_branch = _git(
            ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
            repo_dir,
        )
        if local_branch.returncode == 0:
            add = _git(["worktree", "add", str(wt), branch], repo_dir, timeout=120)
        elif local_branch.returncode == 1:
            add = _git(
                ["worktree", "add", "-b", branch, str(wt), f"origin/{base}"],
                repo_dir,
                timeout=120,
            )
        else:
            detail = (local_branch.stderr or local_branch.stdout or "git show-ref failed").strip()[:160]
            return f"FAIL {task.id}: local branch probe for {branch} ({detail})"
        if add.returncode != 0:
            detail = (add.stderr or add.stdout or "git worktree add failed").strip()[:160]
            return f"BLOCKED {task.id}: deterministic branch {branch} could not attach at {wt} ({detail})"

    status = _git(["status", "--porcelain"], wt)
    if status.returncode != 0:
        detail = (status.stderr or status.stdout or "git status failed").strip()[:160]
        return f"BLOCKED {task.id}: cannot inspect retained worktree {wt} ({detail})"
    if status.stdout.strip():
        return f"BLOCKED {task.id}: retained worktree {wt} is dirty; refusing ambiguous resume"
    head = _git(["rev-parse", "HEAD"], wt)
    base_head = _git(["rev-parse", f"origin/{base}"], wt)
    if head.returncode != 0 or base_head.returncode != 0:
        detail = (head.stderr or base_head.stderr or head.stdout or base_head.stdout or "git rev-parse failed").strip()[
            :160
        ]
        return f"BLOCKED {task.id}: cannot classify retained branch {branch} ({detail})"
    needs_commit = head.stdout.strip() == base_head.stdout.strip()
    if not needs_commit:
        commit_message = _git(["log", "-1", "--format=%B"], wt)
        expected_marker = f"limen task {task.id} (jules session {sid})"
        if commit_message.returncode != 0 or expected_marker not in commit_message.stdout:
            detail = (commit_message.stderr or commit_message.stdout or "exact Jules commit marker absent").strip()[
                :160
            ]
            return f"BLOCKED {task.id}: clean retained branch {branch} is not an exact Jules commit ({detail})"
    if needs_commit:
        pull = subprocess.run(
            [JULES, "remote", "pull", "--session", sid, "--apply"],
            cwd=str(wt),
            capture_output=True,
            text=True,
            timeout=180,
        )
        if pull.returncode != 0:
            detail = (pull.stderr or pull.stdout or "jules remote pull failed").strip()[:160]
            return f"BLOCKED {task.id}: Jules pull failed; retained state is ambiguous ({detail})"
        pulled_status = _git(["status", "--porcelain"], wt)
        if pulled_status.returncode != 0:
            detail = (pulled_status.stderr or pulled_status.stdout or "git status failed").strip()[:160]
            return f"BLOCKED {task.id}: cannot inspect Jules pull result ({detail})"
        if not pulled_status.stdout.strip():
            generated_cleanup = purge_generated_payloads(wt)
            return (
                f"no-op {task.id}: jules session {sid} produced no diff; "
                f"generated cleanup {generated_cleanup}; {retain}"
            )
        add = _git(["add", "-A"], wt)
        if add.returncode != 0:
            detail = (add.stderr or add.stdout or "git add failed").strip()[:160]
            return f"BLOCKED {task.id}: cannot stage Jules pull result ({detail})"
        staged = _git(["diff", "--cached", "--quiet"], wt)
        if staged.returncode == 0:
            return f"BLOCKED {task.id}: Jules pull left dirty but non-staged state in {wt}; refusing ambiguous no-op"
        if staged.returncode != 1:
            detail = (staged.stderr or staged.stdout or "git diff failed").strip()[:160]
            return f"BLOCKED {task.id}: cannot classify staged Jules result ({detail})"
        unmerged = _git(["ls-files", "-u"], wt)
        if unmerged.returncode != 0 or unmerged.stdout.strip():
            detail = (unmerged.stderr or unmerged.stdout or "unmerged index").strip()[:160]
            return f"BLOCKED {task.id}: Jules pull left an unmerged index ({detail})"
        message = f"{task.title}\n\nlimen task {task.id} (jules session {sid})"
        commit = _git(
            [
                "-c",
                f"user.name={os.environ.get('LIMEN_COMMIT_NAME', '4444J99')}",
                "-c",
                (
                    "user.email="
                    + os.environ.get(
                        "LIMEN_COMMIT_EMAIL",
                        "4444J99@users.noreply.github.com",
                    )
                ),
                "commit",
                "-m",
                message,
            ],
            wt,
        )
        if commit.returncode != 0:
            detail = (commit.stderr or commit.stdout or "git commit failed").strip()[:160]
            return f"BLOCKED {task.id}: commit left retained state ambiguous ({detail})"
        committed_status = _git(["status", "--porcelain"], wt)
        if committed_status.returncode != 0 or committed_status.stdout.strip():
            detail = (committed_status.stderr or committed_status.stdout or "git status failed").strip()[:160]
            return f"BLOCKED {task.id}: post-commit worktree is not clean ({detail})"
    push = _git(["push", "-u", "origin", branch], wt, timeout=300)
    if push.returncode != 0:
        generated_cleanup = purge_generated_payloads(wt)
        detail = (push.stderr or push.stdout).strip()[:120]
        return f"FAIL {task.id}: push ({detail}); generated cleanup {generated_cleanup}; {retain}"
    pushed_head = _git(["rev-parse", "HEAD"], wt)
    if pushed_head.returncode != 0 or not pushed_head.stdout.strip():
        detail = (pushed_head.stderr or pushed_head.stdout or "git rev-parse failed").strip()[:160]
        return f"FAIL {task.id}: cannot verify pushed head OID ({detail})"
    result = _create_or_adopt_pr(
        task,
        sid,
        branch,
        base,
        expected_head_oid=pushed_head.stdout.strip(),
    )
    generated_cleanup = purge_generated_payloads(wt)
    return f"{result} ; generated cleanup {generated_cleanup}; {retain}"


def landed_pr_url(message: str, fallback: str) -> str:
    """Extract the durable PR URL from a custody result."""
    if "-> " not in message:
        return fallback
    return message.split("-> ", 1)[1].split(" ; ", 1)[0].strip() or fallback
