#!/usr/bin/env python3
"""Verify destructive local-removal tools remain behind archive/redaction acceptance.

Inventory and classification may run autonomously. Physical removal may not. This
predicate binds every known local removal surface to the same shared proof fields,
the human acceptance ledger, and the central covenant document.
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from reap_acceptance import (  # noqa: E402
    REMOVAL_ACCEPTANCE_COVENANT_DOC,
    REMOVAL_ACCEPTANCE_SURFACES,
    REQUIRED_ACCEPTANCE_PROOF_FIELDS,
)


HELPER_TOKENS = ("has_required_acceptance_proof", "missing_required_acceptance_proof_fields")
NO_SHORTCUT_PHRASE = "Do not create that JSONL as a cleanup shortcut"
DIRECT_REMOVAL_BANS = {
    "cli/src/limen/dispatch.py": ("worktree remove", "branch -D", "--delete-branch"),
    "cli/src/limen/jules_landing_custody.py": (
        "worktree remove",
        "branch -D",
        "--delete-branch",
    ),
    "scripts/cells.sh": ("worktree remove", "branch -D", "--delete-branch"),
    "scripts/jules-land.py": ("worktree remove", "branch -D", "--delete-branch"),
    "scripts/ship-docs.sh": ("worktree remove", "branch -D", "--delete-branch"),
    "scripts/merge-ready.sh": ("--delete-branch",),
    "scripts/merge-drain.py": ("--delete-branch",),
    "scripts/done-insight-cadence.sh": ("rm -rf", "rm -f"),
    "scripts/done-session-orient.sh": ("rm -rf",),
    "scripts/clone-maintenance.sh": ("shutil.rmtree(nm", "--delete-branch"),
    "scripts/library-preserve.py": ("shutil.rmtree",),
    "scripts/cvstos-organ.py": ("shutil.rmtree", ".unlink()"),
    "scripts/setup-rulesets.py": ("delete_branch_on_merge=true",),
    "CLAUDE.md": ("--delete-branch",),
    "docs/MERGE-READY.md": ("--delete-branch", "deletes the branches"),
    "docs/RULESETS-DRYRUN.md": ("delete_branch_on_merge=true", "script flips it on"),
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _squash(text: str) -> str:
    return " ".join(text.split())


def check_surface(root: Path, surface: dict[str, str]) -> list[str]:
    errors: list[str] = []
    script = root / surface["script"]
    doc = root / surface["doc"]
    ledger = surface["ledger"]

    if not script.exists():
        return [f"{surface['name']}: missing script {surface['script']}"]
    if not doc.exists():
        return [f"{surface['name']}: missing doc {surface['doc']}"]

    script_text = _read(script)
    doc_text = _read(doc)

    if not any(token in script_text for token in HELPER_TOKENS):
        errors.append(f"{surface['name']}: script does not call the shared acceptance-proof helper")
    if Path(ledger).name not in script_text:
        errors.append(f"{surface['name']}: script does not name acceptance ledger {ledger}")
    if ledger not in doc_text:
        errors.append(f"{surface['name']}: doc does not name acceptance ledger {ledger}")
    if NO_SHORTCUT_PHRASE not in _squash(doc_text):
        errors.append(f"{surface['name']}: doc does not forbid shortcut JSONL creation")

    for field in REQUIRED_ACCEPTANCE_PROOF_FIELDS:
        if field not in doc_text:
            errors.append(f"{surface['name']}: doc does not require proof field {field}")

    return errors


def check_covenant(root: Path) -> list[str]:
    path = root / REMOVAL_ACCEPTANCE_COVENANT_DOC
    if not path.exists():
        return [f"missing covenant doc {REMOVAL_ACCEPTANCE_COVENANT_DOC}"]

    text = _read(path)
    errors: list[str] = []
    for field in REQUIRED_ACCEPTANCE_PROOF_FIELDS:
        if field not in text:
            errors.append(f"covenant: missing required proof field {field}")
    for surface in REMOVAL_ACCEPTANCE_SURFACES:
        for key in ("script", "doc", "ledger"):
            if surface[key] not in text:
                errors.append(f"covenant: missing {surface['name']} {key} {surface[key]}")
    return errors


def check_direct_removal_bans(
    root: Path,
    bans: dict[str, tuple[str, ...]] = DIRECT_REMOVAL_BANS,
) -> list[str]:
    errors: list[str] = []
    for rel, tokens in bans.items():
        path = root / rel
        if not path.exists():
            errors.append(f"direct-removal-ban: missing guarded path {rel}")
            continue
        text = _read(path)
        for token in tokens:
            if token in text:
                errors.append(f"direct-removal-ban: {rel} contains forbidden token {token!r}")
    return errors


def check_all(root: Path = ROOT) -> list[str]:
    errors = check_covenant(root)
    for surface in REMOVAL_ACCEPTANCE_SURFACES:
        errors.extend(check_surface(root, surface))
    errors.extend(check_direct_removal_bans(root))
    return errors


def main() -> int:
    errors = check_all(ROOT)
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"removal acceptance contracts verified: {len(REMOVAL_ACCEPTANCE_SURFACES)} surfaces")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
