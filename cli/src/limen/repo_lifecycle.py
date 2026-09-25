"""Session-scoped repository residency entry points.

Acquisition is serialized across processes and keyed by immutable GitHub ID. Release
is deliberately investigative: it records the request and preserves any uncertain
checkout. Destructive retirement remains delegated to the existing evidence-gated
worktree abandonment workflow.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from limen.worktree_initialization import WorktreeInitializationError, initialize_worktree
from limen.worktree_roots import dispatch_clone_cache_root, effective_worktree_root


class RepositoryLifecycleError(RuntimeError):
    """Repository identity or residency could not be established safely."""


def _git(path: Path, *args: str, timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RepositoryLifecycleError("Git inspection failed; residency retained") from exc
    if result.returncode:
        raise RepositoryLifecycleError((result.stderr or result.stdout or "git-command-failed").strip())
    return result.stdout.strip()


def _common_git_dir(path: Path) -> Path:
    return Path(_git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()


def _gh(*args: str, timeout: int = 15) -> str:
    result = subprocess.run(
        ["gh", "api", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    if result.returncode:
        raise RepositoryLifecycleError("authenticated GitHub identity lookup failed")
    return result.stdout.strip()


def _repository(repository_id: int | str) -> tuple[int, str]:
    raw = str(repository_id).strip()
    if not raw.isdecimal() or int(raw) <= 0:
        raise RepositoryLifecycleError("repo_id must be an immutable positive GitHub repository ID")
    stable_id = int(raw)
    try:
        live = json.loads(_gh(f"repositories/{stable_id}"))
        live_id = int(live["id"])
        coordinate = str(live["full_name"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RepositoryLifecycleError("GitHub returned an invalid repository identity") from exc
    if live_id != stable_id or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", coordinate):
        raise RepositoryLifecycleError("GitHub immutable identity mismatch")
    # The authenticated immutable-ID endpoint is authority; registry aliases are discovery hints.
    return stable_id, coordinate


def _verify_store_origin(store: Path, stable_id: int) -> None:
    """Never adopt a store on coordinate or registry-alias resemblance alone."""
    from limen.dispatch import _github_slug_from_remote

    origin = _git(store, "remote", "get-url", "origin")
    slug = _github_slug_from_remote(origin)
    if slug is None:
        raise RepositoryLifecycleError("canonical store origin is not a GitHub repository")
    try:
        observed = int(json.loads(_gh(f"repos/{slug}"))["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RepositoryLifecycleError("canonical store origin identity is unavailable; retained") from exc
    if observed != stable_id:
        raise RepositoryLifecycleError("canonical store origin immutable identity mismatch; retained")


def _atomic_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def _locked(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def ensure(repository_id: int | str, revision: str, session_id: str) -> dict[str, str]:
    """Acquire an isolated checkout for a session; repeated calls are idempotent."""
    if not session_id.strip() or "\x00" in session_id:
        raise RepositoryLifecycleError("session_id must be nonblank")
    if not revision.strip() or "\x00" in revision or revision.startswith("-"):
        raise RepositoryLifecycleError("revision must be a nonblank Git revision")
    stable_id, coordinate = _repository(repository_id)
    cache = dispatch_clone_cache_root()
    if cache is None:
        raise RepositoryLifecycleError("managed repository cache is unavailable")
    cache.mkdir(parents=True, exist_ok=True)
    store = cache / f"github-{stable_id}"
    state = cache / ".limen-residency" / str(stable_id)
    leases = state / "leases"
    lease_id = f"{stable_id}-{_digest(session_id)[:32]}"
    lease_file = leases / f"{lease_id}.json"
    lock = state / "acquire.lock"
    with _locked(lock):
        root = effective_worktree_root().expanduser()
        worktree = root / f"repo-{stable_id}-{_digest(session_id)[:16]}"
        branch = f"limen/session-{stable_id}-{_digest(session_id)[:12]}"
        if store.exists():
            _verify_store_origin(store, stable_id)
        else:
            try:
                # gh starts Git and its transport as children. Reuse dispatch's
                # process-group timeout so a child holding the output pipe cannot
                # outlive the acquisition deadline.
                from limen.dispatch import _run_capture

                result = _run_capture(["gh", "repo", "clone", coordinate, str(store)], timeout=600)
            except (OSError, subprocess.SubprocessError) as exc:
                raise RepositoryLifecycleError("repository acquisition failed; no lease was issued") from exc
            if result.returncode:
                raise RepositoryLifecycleError("repository acquisition failed; no lease was issued")
            _verify_store_origin(store, stable_id)
        if lease_file.exists():
            record = json.loads(lease_file.read_text(encoding="utf-8"))
            if (
                record.get("repository_id") != stable_id
                or record.get("session_digest") != _digest(session_id)
                or record.get("revision") != revision
                or record.get("store") != str(store)
                or record.get("worktree") != str(worktree)
                or record.get("branch") != branch
                or worktree.is_symlink()
                or worktree.parent.resolve() != root.resolve()
                or not worktree.is_dir()
            ):
                raise RepositoryLifecycleError("existing lease is inconsistent; residency retained")
            if _common_git_dir(worktree) != _common_git_dir(store):
                raise RepositoryLifecycleError("existing checkout does not belong to its canonical store; retained")
            if record.get("state") != "active":
                raise RepositoryLifecycleError("session lease was released; reacquisition requires a new session ID")
            head = _git(worktree, "rev-parse", "HEAD")
            return {
                "repository_id": str(stable_id),
                "lease_id": lease_id,
                "store": str(store),
                "worktree": str(worktree),
                "branch": str(record.get("branch", "")),
                "head": head,
            }
        try:
            from limen.dispatch import _run_capture

            revision_result = _run_capture(
                ["git", "-C", str(store), "fetch", "origin", revision],
                timeout=300,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RepositoryLifecycleError("requested revision fetch was interrupted; residency retained") from exc
        if revision_result.returncode:
            raise RepositoryLifecycleError("requested revision could not be fetched; residency retained")
        target = _git(store, "rev-parse", "--verify", "FETCH_HEAD^{commit}")
        root.mkdir(parents=True, exist_ok=True)
        try:
            initialized = initialize_worktree(store, worktree, branch=branch, checkout_ref=target, task_id=lease_id)
        except WorktreeInitializationError as exc:
            raise RepositoryLifecycleError(f"worktree initialization retained at {exc.journal_path}") from exc
        new_record: dict[str, object] = {
            "schema": "limen.repository_lease.v1",
            "lease_id": lease_id,
            "repository_id": stable_id,
            "coordinate": coordinate,
            "session_digest": _digest(session_id),
            "revision": revision,
            "head": initialized.expected_head,
            "branch": branch,
            "store": str(store),
            "worktree": str(worktree),
            "state": "active",
            "created_at": datetime.now(UTC).isoformat(),
        }
        _atomic_json(lease_file, new_record)
        return {
            "repository_id": str(stable_id),
            "lease_id": lease_id,
            "store": str(store),
            "worktree": str(worktree),
            "branch": branch,
            "head": initialized.expected_head,
        }


def release(lease_id: str) -> dict[str, str]:
    """Release a lease into investigation; uncertain or dirty work is retained."""
    if not re.fullmatch(r"[1-9][0-9]*-[a-f0-9]{32}", lease_id):
        raise RepositoryLifecycleError("invalid lease_id")
    stable_id = int(lease_id.split("-", 1)[0])
    cache = dispatch_clone_cache_root()
    if cache is None:
        raise RepositoryLifecycleError("managed repository cache is unavailable")
    state = cache / ".limen-residency" / str(stable_id)
    path = state / "leases" / f"{lease_id}.json"
    with _locked(state / "acquire.lock"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RepositoryLifecycleError("lease record unavailable; checkout retained") from exc
        if record.get("lease_id") != lease_id or record.get("repository_id") != stable_id:
            raise RepositoryLifecycleError("lease identity mismatch; checkout retained")
        worktree = Path(str(record["worktree"]))
        root = effective_worktree_root().expanduser()
        store = cache / f"github-{stable_id}"
        expected_worktree = root / f"repo-{stable_id}-{lease_id.split('-', 1)[1][:16]}"
        if (
            record.get("store") != str(store)
            or record.get("worktree") != str(expected_worktree)
            or worktree != expected_worktree
            or worktree.is_symlink()
            or worktree.parent.resolve() != root.resolve()
        ):
            raise RepositoryLifecycleError("lease path is outside managed worktree root; checkout retained")
        if record.get("state") != "active":
            return {"lease_id": lease_id, "state": str(record.get("state")), "worktree": str(worktree)}
        try:
            if _common_git_dir(worktree) != _common_git_dir(store):
                raise RepositoryLifecycleError("lease checkout does not belong to canonical store; retained")
        except RepositoryLifecycleError as exc:
            raise RepositoryLifecycleError("lease Git identity unavailable; checkout retained") from exc
        try:
            status = subprocess.run(
                ["git", "-C", str(worktree), "status", "--porcelain=v1", "--untracked-files=all"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                stdin=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError):
            status = None
        if status is None or status.returncode or status.stdout:
            state_name = "retained-dirty-or-unavailable"
        else:
            state_name = "released-awaiting-custody-investigation"
        record["state"] = state_name
        record["released_at"] = datetime.now(UTC).isoformat()
        _atomic_json(path, record)
        return {"lease_id": lease_id, "state": state_name, "worktree": str(worktree)}
