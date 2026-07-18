"""Owner-repo and raw-export custody proofs for research outputs."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from .contracts import (
    ResearchContractError,
    ResearchRequest,
    owner_path,
    safe_owner_reference,
)


def _remote_slug(remote: str) -> str | None:
    value = remote.strip().removesuffix(".git")
    patterns = (
        r"^https?://github\.com/(?P<slug>[^/]+/[^/]+)$",
        r"^git@github\.com:(?P<slug>[^/]+/[^/]+)$",
        r"^ssh://git@github\.com/(?P<slug>[^/]+/[^/]+)$",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, value)
        if match:
            return match.group("slug")
    return None


def verify_owner_root(owner_root: Path, request: ResearchRequest) -> Path:
    root = owner_root.expanduser().resolve()
    if not (root / ".git").exists():
        # Worktrees use a .git file, while ordinary repositories use a directory.
        raise ResearchContractError("owner-root is not a Git repository or worktree")
    result = subprocess.run(
        ["git", "-C", str(root), "remote", "get-url", "origin"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ResearchContractError("owner-root has no queryable origin remote")
    slug = _remote_slug(result.stdout)
    if slug != request.owner_repo:
        raise ResearchContractError(f"owner-root remote {slug or 'unknown'} does not match {request.owner_repo}")
    return root


def _is_tracked(root: Path, path: Path) -> bool:
    relative = path.relative_to(root)
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--error-unmatch", "--", str(relative)],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _is_ignored(root: Path, path: Path) -> bool:
    relative = path.relative_to(root)
    result = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "-q", "--", str(relative)],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def verify_raw_export_custody(
    export_file: Path,
    owner_root: Path,
    request: ResearchRequest,
    *,
    raw_owner_root: Path | None = None,
) -> None:
    """Prove the export's exact location against its declared custody reference."""

    export = export_file.expanduser().resolve()
    raw_ref = request.raw_export_ref
    if not raw_ref:
        if raw_owner_root is not None:
            raise ResearchContractError("raw-owner-root cannot be supplied when raw_export_ref is null")
        return

    if not raw_ref.startswith("private-owner://"):
        if raw_owner_root is not None:
            raise ResearchContractError("raw-owner-root is only valid for private-owner raw exports")
        expected = owner_path(owner_root, raw_ref)
        if export != expected:
            raise ResearchContractError("tracked raw export does not match output_contract.raw_export_ref")
        return

    parsed = urlparse(raw_ref)
    if (
        parsed.scheme != "private-owner"
        or not parsed.netloc
        or not parsed.path
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ResearchContractError("private-owner raw_export_ref is malformed")
    expected_owner_id = request.owner_repo.rsplit("/", 1)[-1]
    if parsed.netloc != expected_owner_id:
        raise ResearchContractError("private-owner authority does not match the request owner")
    if raw_owner_root is None:
        raise ResearchContractError("private-owner raw export requires a designated raw-owner-root")
    private_root = raw_owner_root.expanduser().resolve()
    if not private_root.is_dir():
        raise ResearchContractError("raw-owner-root is not a directory")
    relative_ref = safe_owner_reference(parsed.path.lstrip("/"), field_name="output_contract.raw_export_ref path")
    expected = owner_path(private_root, relative_ref)
    if export != expected:
        raise ResearchContractError("private raw export does not match its designated owner reference")

    try:
        export.relative_to(owner_root)
    except ValueError:
        return
    if _is_tracked(owner_root, export) or not _is_ignored(owner_root, export):
        raise ResearchContractError("private raw export inside owner-root must be untracked and ignored")
