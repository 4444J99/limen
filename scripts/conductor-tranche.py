#!/usr/bin/env python3
"""Select the next bounded Limen conductor tranche.

This is the small bridge between "ranked attack paths" and an actual
one-to-two-hour direct-session work packet. It reads redacted ranked path
evidence, skips parked/family/human-gate/auth-only lanes, and writes a public-safe packet with:

* purpose;
* repo/worktree scope;
* allowed files;
* stop condition;
* verification;
* receipt target.

It never claims tasks, dispatches agents, mutates GitHub, or reads raw prompt
text.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
ATTACK_INDEX = PRIVATE_ROOT / "lifecycle" / "session-attack-paths.json"
DOC_PATH = ROOT / "docs" / "conductor-tranche.md"
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "conductor-tranche.json"
PORTVS_PATH = HOME / "Workspace" / "4444J99" / "portvs"

SKIP_LANES = {"family", "human-gate", "observe", "parked"}
SKIP_CATEGORIES = {"auth_credentials"}


def load_json(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    return obj if isinstance(obj, dict) else {}


def relpath(path: Path) -> str:
    try:
        return "~/" + str(path.expanduser().resolve().relative_to(HOME))
    except (OSError, ValueError):
        return str(path)


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "unknown"


def as_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value or [] if isinstance(item, dict)]


def is_actionable(path: dict[str, Any]) -> bool:
    lane = str(path.get("lane") or "")
    category = str(path.get("category") or "")
    if lane in SKIP_LANES:
        return False
    if category in SKIP_CATEGORIES:
        return False
    return True


def select_path(paths: list[dict[str, Any]]) -> dict[str, Any] | None:
    for path in paths:
        if is_actionable(path):
            return path
    return paths[0] if paths else None


def worktree_packet(path: dict[str, Any]) -> dict[str, Any]:
    root = str(path.get("id") or "worktree-lifecycle")
    return {
        "purpose": (
            f"Resolve `{root}` to a preservation proof, owner blocker, remote/default proof, "
            "or documented non-source residue without deleting unique work."
        ),
        "repo_worktree": f"Owner worktree `{root}` under `~/Workspace/.limen-worktrees` plus Limen receipts.",
        "allowed_files": [
            "docs/worktree-lifecycle-ledger.md",
            "docs/worktree-preservation-receipts.json",
            "docs/session-attack-paths.md",
            "docs/session-lifecycle-blockers.md",
            "docs/conductor-tranche.md",
            ".limen-private/session-corpus/lifecycle/**",
        ],
        "stop_condition": (
            "Stop before deletion, force-push, merge, or owner-repo source edits unless a narrower "
            "owner packet names the repo, branch, predicate, and receipt."
        ),
        "verification": [
            "python3 scripts/worktree-debt.py --json",
            "python3 scripts/session-lifecycle-pressure.py --write",
            "python3 scripts/session-blockers-ledger.py --write",
            "python3 scripts/session-attack-paths.py --write",
            "python3 scripts/conductor-tranche.py --write",
        ],
        "receipt": "Update the owning worktree lifecycle receipt and regenerate docs/conductor-tranche.md.",
    }


def worktree_lifecycle_packet(path: dict[str, Any]) -> dict[str, Any]:
    return {
        "purpose": (
            "Resolve the remaining worktree lifecycle blocker by converting affected roots into "
            "preservation proof, owner blockers, remote/default proof, or documented non-source residue."
        ),
        "repo_worktree": (
            "`organvm/limen` conductor checkout plus read-only inspection of "
            "`~/Workspace/.limen-worktrees`."
        ),
        "allowed_files": [
            "cli/src/limen/worktree_debt.py",
            "cli/tests/test_worktree_debt.py",
            "scripts/worktree-debt.py",
            "scripts/*lifecycle*.py",
            "docs/worktree-lifecycle-ledger.md",
            "docs/worktree-preservation-receipts.json",
            "docs/session-lifecycle-blockers.md",
            "docs/session-attack-paths.md",
            "docs/conductor-tranche.md",
            ".limen-private/session-corpus/lifecycle/**",
        ],
        "stop_condition": (
            "Stop before deletion, force-push, merge, or owner-repo source edits unless a narrower "
            "owner packet names the repo, branch, predicate, and receipt."
        ),
        "verification": [
            "python3 scripts/worktree-debt.py --json",
            "python3 scripts/session-lifecycle-pressure.py --write",
            "python3 scripts/session-blockers-ledger.py --write",
            "python3 scripts/session-attack-paths.py --write",
            "python3 scripts/conductor-tranche.py --write",
        ],
        "receipt": "docs/worktree-lifecycle-ledger.md and docs/worktree-preservation-receipts.json.",
    }


def local_lean_packet(path: dict[str, Any]) -> dict[str, Any]:
    return {
        "purpose": (
            "Drive local lifecycle pressure down by converting the highest-risk roots into owner "
            "receipts, preservation proof, or explicit human-gated reclaim packets."
        ),
        "repo_worktree": (
            "`organvm/limen` conductor checkout plus read-only inspection of "
            "`~/Workspace/.limen-worktrees`."
        ),
        "allowed_files": [
            "scripts/*lifecycle*.py",
            "scripts/worktree-debt.py",
            "docs/worktree-lifecycle-ledger.md",
            "docs/worktree-preservation-receipts.json",
            "docs/session-lifecycle-blockers.md",
            "docs/session-attack-paths.md",
            "docs/conductor-tranche.md",
            ".limen-private/session-corpus/lifecycle/**",
        ],
        "stop_condition": (
            "Stop before local reclaim/deletion, broad generated build-out, GitHub merge/close, "
            "or any owner repo mutation not covered by a fresh owner receipt."
        ),
        "verification": [
            "python3 scripts/worktree-debt.py --json",
            "python3 scripts/session-lifecycle-pressure.py --write",
            "python3 scripts/session-blockers-ledger.py --write",
            "python3 scripts/session-attack-paths.py --write",
            "python3 scripts/conductor-tranche.py --write",
        ],
        "receipt": (
            "docs/worktree-lifecycle-ledger.md or docs/worktree-preservation-receipts.json for "
            "owner state; docs/conductor-tranche.md for the current packet."
        ),
    }


def dispatch_packet(path: dict[str, Any]) -> dict[str, Any]:
    return {
        "purpose": (
            "Repair dispatch/remote proof drift so the queue can distinguish healthy async work, "
            "stranded claims, merged PRs, and real blockers."
        ),
        "repo_worktree": "`organvm/limen` conductor checkout only.",
        "allowed_files": [
            "scripts/dispatch*.py",
            "scripts/verify-dispatch.py",
            "scripts/heal-dispatch.py",
            "cli/tests/test_async_dispatch.py",
            "docs/DISPATCH-ARCHITECTURE.md",
            "docs/conductor-tranche.md",
        ],
        "stop_condition": (
            "Stop before changing task states, launching live dispatch, or touching credentials unless "
            "the packet explicitly includes that gate."
        ),
        "verification": [
            "pytest -q cli/tests/test_async_dispatch.py",
            "python3 scripts/verify-dispatch.py",
            "python3 scripts/conductor-tranche.py --write",
        ],
        "receipt": "docs/DISPATCH-ARCHITECTURE.md and docs/conductor-tranche.md.",
    }


def consolidation_packet(path: dict[str, Any]) -> dict[str, Any]:
    return {
        "purpose": (
            "Advance the GitHub/org consolidation enforcement path by refreshing dry-run gates, "
            "surfacing collisions, and packetizing the exact human-gated rename/transfer/rewrite sequence."
        ),
        "repo_worktree": "`organvm/limen` conductor checkout only; GitHub/org state is read-only.",
        "allowed_files": [
            "scripts/consolidation-gates.py",
            "scripts/consolidate-github.py",
            "scripts/rewrite-owners.py",
            "scripts/session-blockers-ledger.py",
            "scripts/session-attack-paths.py",
            "scripts/conductor-tranche.py",
            "docs/consolidation/RUNBOOK.md",
            "docs/consolidation/COLLISION-RENAMES.md",
            "docs/consolidation/GATES.md",
            "docs/session-lifecycle-blockers.md",
            "docs/session-attack-paths.md",
            "docs/conductor-tranche.md",
            ".limen-private/session-corpus/lifecycle/consolidation-gates.json",
            ".limen-private/session-corpus/lifecycle/session-lifecycle-blockers.json",
            ".limen-private/session-corpus/lifecycle/session-attack-paths.json",
            ".limen-private/session-corpus/lifecycle/conductor-tranche.json",
        ],
        "stop_condition": (
            "Stop before `gh repo rename`, `consolidate-github.py --apply`, "
            "`rewrite-owners.py --apply`, GitHub App install, or credential writes unless a human "
            "explicitly opens that gate in-session."
        ),
        "verification": [
            "python3 scripts/consolidation-gates.py --write",
            "python3 scripts/session-blockers-ledger.py --write",
            "python3 scripts/session-attack-paths.py --write",
            "python3 scripts/conductor-tranche.py --write",
            "PYTHONPATH=cli/src python3 scripts/consolidate-github.py",
            "PYTHONPATH=cli/src python3 scripts/rewrite-owners.py",
            "bash scripts/gh-app-token.sh --which",
        ],
        "receipt": (
            "docs/consolidation/GATES.md plus docs/conductor-tranche.md; private parsed gate receipt "
            "under .limen-private/session-corpus/lifecycle/."
        ),
    }


def github_app_identity_packet(path: dict[str, Any]) -> dict[str, Any]:
    return {
        "purpose": (
            "Clearly block limen[bot] until the GitHub App exists, is installed on `organvm`, "
            "and local/CI credentials are hydrated without exposing secret values."
        ),
        "repo_worktree": "`organvm/limen` conductor checkout only; GitHub App state is read-only.",
        "allowed_files": [
            "scripts/consolidation-gates.py",
            "scripts/gh-app-token.sh",
            "docs/github-app-architecture.md",
            "docs/consolidation/SCOPE-AND-APP.md",
            "docs/consolidation/GATES.md",
            "docs/session-lifecycle-blockers.md",
            "docs/session-attack-paths.md",
            "docs/conductor-tranche.md",
            ".limen-private/session-corpus/lifecycle/consolidation-gates.json",
        ],
        "stop_condition": (
            "Stop before creating/installing the GitHub App, calling `scripts/set-credential.sh`, "
            "writing any PEM/key material, or changing GitHub secrets without explicit human approval."
        ),
        "verification": [
            "python3 scripts/consolidation-gates.py --write",
            "bash scripts/gh-app-token.sh --which",
            "python3 scripts/session-blockers-ledger.py --write",
            "python3 scripts/session-attack-paths.py --write",
            "python3 scripts/conductor-tranche.py --write",
        ],
        "receipt": "docs/consolidation/GATES.md and docs/session-lifecycle-blockers.md record the blocked App identity.",
    }


def default_packet(path: dict[str, Any]) -> dict[str, Any]:
    path_id = str(path.get("id") or "selected-path")
    return {
        "purpose": f"Turn `{path_id}` into an owner-recorded packet or resolve the blocker locally.",
        "repo_worktree": "`organvm/limen` conductor checkout unless a narrower owner packet says otherwise.",
        "allowed_files": [
            "docs/session-attack-paths.md",
            "docs/session-lifecycle-blockers.md",
            "docs/prompt-packet-ledger.md",
            "docs/conductor-tranche.md",
            ".limen-private/session-corpus/lifecycle/**",
        ],
        "stop_condition": (
            "Stop before broad delegation, credential work, destructive cleanup, or owner repo mutation "
            "without a scoped packet."
        ),
        "verification": [
            "python3 scripts/session-blockers-ledger.py --write",
            "python3 scripts/session-attack-paths.py --write",
            "python3 scripts/conductor-tranche.py --write",
        ],
        "receipt": "The owner ledger named by the selected path plus docs/conductor-tranche.md.",
    }


def packet_for_path(path: dict[str, Any] | None) -> dict[str, Any]:
    if path is None:
        return {
            "purpose": "Refresh the conductor indexes until a ranked path exists.",
            "repo_worktree": "`organvm/limen` conductor checkout.",
            "allowed_files": [
                "docs/session-attack-paths.md",
                "docs/session-lifecycle-blockers.md",
                "docs/conductor-tranche.md",
                ".limen-private/session-corpus/lifecycle/**",
            ],
            "stop_condition": "Stop if prerequisite indexes are absent or unreadable after refresh.",
            "verification": [
                "python3 scripts/session-blockers-ledger.py --write",
                "python3 scripts/session-attack-paths.py --write",
                "python3 scripts/conductor-tranche.py --write",
            ],
            "receipt": "docs/conductor-tranche.md records the missing-input state.",
        }
    category = str(path.get("category") or "")
    kind = str(path.get("kind") or "")
    lane = str(path.get("lane") or "")
    if category == "local_lean" or str(path.get("id")) == "local-lifecycle-disk-pressure":
        return local_lean_packet(path)
    if category == "worktree_lifecycle":
        return worktree_lifecycle_packet(path)
    if kind == "worktree":
        return worktree_packet(path)
    if category == "github_consolidation":
        return consolidation_packet(path)
    if category == "github_app_identity":
        return github_app_identity_packet(path)
    if category in {"remote_receipt", "dispatch_lifecycle", "task_board"} or lane == "remote-close":
        return dispatch_packet(path)
    return default_packet(path)


def build_snapshot() -> dict[str, Any]:
    attack = load_json(ATTACK_INDEX)
    ranked = as_list(attack.get("ranked_paths"))
    selected = select_path(ranked)
    packet = packet_for_path(selected)
    selected_id = str((selected or {}).get("id") or "missing-ranked-path")
    skipped = [path.get("id") for path in ranked if path is not selected and not is_actionable(path)]
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "inputs": {
            "session_attack_paths": {
                "path": str(ATTACK_INDEX),
                "present": bool(attack),
                "generated_at": attack.get("generated_at"),
                "ranked_paths": len(ranked),
            }
        },
        "selection_policy": {
            "skip_lanes": sorted(SKIP_LANES),
            "skip_categories": sorted(SKIP_CATEGORIES),
        },
        "selected_path": selected or {},
        "skipped_unactionable_path_ids": [str(item) for item in skipped if item],
        "packet": {
            "id": f"tranche-{slugify(selected_id)}",
            "human_cadence": "one-to-two-hour direct-session tranche",
            "selected_path_id": selected_id,
            "forbidden": [
                str(PORTVS_PATH),
                "creative placement work",
                "plaintext secrets or credential values",
                "irreversible GitHub transfer/rename/App install/credential actions",
                "task-board mutation unless the direct request explicitly requires it",
            ],
            **packet,
        },
        "private_index": str(PRIVATE_INDEX),
    }


def render_markdown(snapshot: dict[str, Any]) -> str:
    packet = snapshot["packet"]
    selected = snapshot["selected_path"]
    inputs = snapshot["inputs"]["session_attack_paths"]
    selected_id = packet["selected_path_id"]
    lane = str(selected.get("lane") or "n/a")
    kind = str(selected.get("kind") or "n/a")
    score = selected.get("score", "n/a")
    next_action = str(selected.get("next_action") or packet["purpose"])
    allowed = "\n".join(f"- `{item}`" for item in packet["allowed_files"])
    forbidden = "\n".join(f"- `{item}`" for item in packet["forbidden"])
    verification = "\n".join(f"- `{item}`" for item in packet["verification"])
    skipped = ", ".join(f"`{item}`" for item in snapshot["skipped_unactionable_path_ids"]) or "none"
    lines = [
        "# Conductor Tranche",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        "",
        (
            f"Summary: `{packet['id']}` -> `{selected_id}` (`{lane}`); "
            f"stop before: {packet['stop_condition']}"
        ),
        "",
        "## Cadence Contract",
        "",
        "- Work in one-to-two-hour direct-session tranches.",
        "- Start from current receipts, not memory.",
        "- Implement reversible local fixes first.",
        "- Leave owner receipts and exact verification commands before stopping.",
        "",
        "## Selected Trench",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Packet | `{packet['id']}` |",
        f"| Selected path | `{selected_id}` |",
        f"| Kind | `{kind}` |",
        f"| Lane | `{lane}` |",
        f"| Score | `{score}` |",
        f"| Agent fit | `{selected.get('agent_fit', 'n/a')}` |",
        f"| Attack index generated | `{inputs.get('generated_at') or 'unknown'}` |",
        f"| Ranked paths read | `{inputs.get('ranked_paths', 0)}` |",
        f"| Skipped family/human-gate/parked/observe/auth paths | {skipped} |",
        "",
        "## Work Packet",
        "",
        f"Purpose: {packet['purpose']}",
        "",
        f"Repo/worktree: {packet['repo_worktree']}",
        "",
        "Allowed files:",
        "",
        allowed,
        "",
        "Forbidden:",
        "",
        forbidden,
        "",
        f"Stop condition: {packet['stop_condition']}",
        "",
        f"Receipt: {packet['receipt']}",
        "",
        "Verification:",
        "",
        verification,
        "",
        "## Source Next Action",
        "",
        next_action,
        "",
        "## Refresh",
        "",
        "- `python3 scripts/consolidation-gates.py --write`",
        "- `python3 scripts/session-lifecycle-pressure.py --write`",
        "- `python3 scripts/session-blockers-ledger.py --write`",
        "- `python3 scripts/session-attack-paths.py --write`",
        "- `python3 scripts/conductor-tranche.py --write`",
        "",
    ]
    return "\n".join(lines)


def write_outputs(snapshot: dict[str, Any], markdown: str) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(markdown, encoding="utf-8")
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Select the next bounded conductor tranche.")
    parser.add_argument("--write", action="store_true", help="write tracked and private tranche receipts")
    args = parser.parse_args()
    snapshot = build_snapshot()
    markdown = render_markdown(snapshot)
    if args.write:
        write_outputs(snapshot, markdown)
    else:
        print(markdown)
    msg = f"conductor-tranche: {snapshot['packet']['id']} from {snapshot['packet']['selected_path_id']}"
    if args.write:
        msg += f"; wrote {DOC_PATH}"
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
