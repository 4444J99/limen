"""Shared proof-field checks for local removal acceptance ledgers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


REQUIRED_ACCEPTANCE_PROOF_FIELDS = ("accepted_at", "archive_proof", "redaction_proof")
REMOVAL_ACCEPTANCE_COVENANT_DOC = "docs/removal-acceptance-covenant.md"
REMOVAL_ACCEPTANCE_SURFACES = (
    {
        "name": "branch",
        "script": "scripts/reap-branches.py",
        "doc": "docs/branch-reap-acceptance.md",
        "ledger": "docs/branch-reap-acceptance.jsonl",
        "destructive_action": "git branch -D",
    },
    {
        "name": "clone",
        "script": "scripts/reap-clones.py",
        "doc": "docs/clone-reap-acceptance.md",
        "ledger": "docs/clone-reap-acceptance.jsonl",
        "destructive_action": "shutil.rmtree clone root",
    },
    {
        "name": "remote_branch",
        "script": "scripts/reap-remote-branches.py",
        "doc": "docs/remote-branch-reap-acceptance.md",
        "ledger": "docs/remote-branch-reap-acceptance.jsonl",
        "destructive_action": "git push origin --delete (remote ref — NOT reflog-recoverable)",
    },
    {
        "name": "worktree",
        "script": "scripts/reclaim-worktrees.py",
        "doc": "docs/worktree-reclaim-acceptance.md",
        "ledger": "docs/worktree-reclaim-acceptance.jsonl",
        "destructive_action": (
            "non-forced git worktree detach or same-filesystem recoverable quarantine "
            "through limen.worktree_abandonment.v1"
        ),
    },
    {
        "name": "antigravity_scratch",
        "script": "scripts/antigravity-scratch-bridge.py",
        "doc": "docs/antigravity-scratch-reap-acceptance.md",
        "ledger": "docs/antigravity-scratch-reap-acceptance.jsonl",
        "destructive_action": "shutil.rmtree scratch root",
    },
)


def missing_required_acceptance_proof_fields(
    event: Mapping[str, Any],
    required_fields: tuple[str, ...] = REQUIRED_ACCEPTANCE_PROOF_FIELDS,
) -> tuple[str, ...]:
    return tuple(field for field in required_fields if not str(event.get(field) or "").strip())


def has_required_acceptance_proof(
    event: Mapping[str, Any],
    required_fields: tuple[str, ...] = REQUIRED_ACCEPTANCE_PROOF_FIELDS,
) -> bool:
    return not missing_required_acceptance_proof_fields(event, required_fields)


def removal_acceptance_surface_names() -> tuple[str, ...]:
    return tuple(str(surface["name"]) for surface in REMOVAL_ACCEPTANCE_SURFACES)
