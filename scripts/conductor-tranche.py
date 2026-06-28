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
import subprocess
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


def blocker_index_path() -> Path:
    return PRIVATE_ROOT / "lifecycle" / "session-lifecycle-blockers.json"


def corpus_inventory_path() -> Path:
    return PRIVATE_ROOT / "inventory" / "session-corpus-ledger.json"


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
    return None


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


def local_network_packet(path: dict[str, Any]) -> dict[str, Any]:
    return {
        "purpose": (
            "Turn local network/netmode substrate drift into a durable cross-lane receipt so future "
            "agents do not treat route drops, legacy LaunchAgents, or auth-looking network failures "
            "as single-lane flakiness."
        ),
        "repo_worktree": "`organvm/limen` conductor checkout plus read-only probes of the live netmode install.",
        "allowed_files": [
            "scripts/network-health.py",
            "scripts/netmode.sh",
            "container/launchd/com.user.netmeter.plist",
            "container/launchd/com.user.netmode.*.plist",
            "scripts/session-blockers-ledger.py",
            "scripts/session-attack-paths.py",
            "scripts/conductor-tranche.py",
            "docs/network-health.md",
            "docs/session-lifecycle-blockers.md",
            "docs/session-attack-paths.md",
            "docs/conductor-tranche.md",
            ".limen-private/session-corpus/lifecycle/network-health.json",
            ".limen-private/session-corpus/lifecycle/session-lifecycle-blockers.json",
            ".limen-private/session-corpus/lifecycle/session-attack-paths.json",
            ".limen-private/session-corpus/lifecycle/conductor-tranche.json",
        ],
        "stop_condition": (
            "Stop before changing routes, running `netmode stop`, loading/unloading LaunchAgents, "
            "editing untracked SSID/provider config, or treating a failed network probe as a credential "
            "failure unless a human explicitly opens that gate."
        ),
        "verification": [
            "bash -n scripts/netmode.sh",
            "bash scripts/netmode.sh selftest",
            "plutil -lint container/launchd/com.user.netmeter.plist",
            "python3 scripts/network-health.py --write",
            "python3 scripts/session-blockers-ledger.py --write",
            "python3 scripts/session-attack-paths.py --write",
            "python3 scripts/conductor-tranche.py --write",
        ],
        "receipt": (
            "docs/network-health.md plus the local-network-substrate row in docs/session-lifecycle-blockers.md "
            "if the substrate is missing or unhealthy."
        ),
    }


def capability_substrate_packet(path: dict[str, Any]) -> dict[str, Any]:
    return {
        "purpose": (
            "Refresh the local agent capability substrate as a public-safe receipt so skill/plugin/MCP "
            "surface area is counted and routed before any lane tries to install, port, or activate tools."
        ),
        "repo_worktree": "`organvm/limen` conductor checkout plus read-only path scans of configured capability roots.",
        "allowed_files": [
            "scripts/capability-substrate-ledger.py",
            "scripts/session-blockers-ledger.py",
            "scripts/session-attack-paths.py",
            "scripts/conductor-tranche.py",
            "docs/capability-substrate-ledger.md",
            "docs/session-lifecycle-blockers.md",
            "docs/session-attack-paths.md",
            "docs/conductor-tranche.md",
            ".limen-private/session-corpus/lifecycle/capability-substrate-index.json",
            ".limen-private/session-corpus/lifecycle/session-lifecycle-blockers.json",
            ".limen-private/session-corpus/lifecycle/session-attack-paths.json",
            ".limen-private/session-corpus/lifecycle/conductor-tranche.json",
        ],
        "stop_condition": (
            "Stop before reading private skill bodies, installing plugins/connectors, editing MCP auth, "
            "moving capability roots, or dispatching broad capability work without a scoped activation packet."
        ),
        "verification": [
            "python3 scripts/capability-substrate-ledger.py --write",
            "python3 scripts/session-blockers-ledger.py --write",
            "python3 scripts/session-attack-paths.py --write",
            "python3 scripts/conductor-tranche.py --write",
        ],
        "receipt": (
            "docs/capability-substrate-ledger.md plus refreshed blocker/attack/tranche receipts; "
            "private counts under .limen-private/session-corpus/lifecycle/."
        ),
    }


def owner_slug_from_path(path: dict[str, Any]) -> str:
    path_id = str(path.get("id") or "")
    prefix = "owner-state-dirty-"
    if path_id.startswith(prefix):
        return path_id[len(prefix) :]
    return path_id or "unknown-owner"


def find_blocker(path_id: str) -> dict[str, Any]:
    blockers = as_list(load_json(blocker_index_path()).get("blockers"))
    for blocker in blockers:
        if str(blocker.get("id") or "") == path_id:
            return blocker
    return {}


def find_corpus_organ(owner_name: str) -> dict[str, Any]:
    organs = as_list(load_json(corpus_inventory_path()).get("organs"))
    for organ in organs:
        if str(organ.get("name") or "") == owner_name:
            return organ
    return {}


def git_dirty_paths(owner_path: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(owner_path), "status", "--porcelain=v1"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    dirty: list[str] = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        if path:
            dirty.append(path)
    return sorted(dict.fromkeys(dirty))


def owner_state_packet(path: dict[str, Any]) -> dict[str, Any]:
    path_id = str(path.get("id") or "owner-state-dirty-unknown")
    blocker = find_blocker(path_id)
    owner_name = str(blocker.get("owner") or owner_slug_from_path(path))
    organ = find_corpus_organ(owner_name)
    owner_path_raw = str(organ.get("path") or "")
    owner_path = Path(owner_path_raw).expanduser() if owner_path_raw else HOME / "Workspace" / owner_name
    owner_scope = relpath(owner_path)
    dirty_paths = git_dirty_paths(owner_path)
    owner_allowed = [f"{owner_scope}/{dirty}" for dirty in dirty_paths] or [f"{owner_scope}/<dirty owner files>"]
    dirty_count = int((blocker.get("details") or {}).get("dirty_entries") or len(dirty_paths) or 0)

    return {
        "purpose": (
            f"Preserve `{path_id}` as a scoped owner-state packet for `{owner_name}` "
            "without rewriting corpus content or broadening into creative placement work."
        ),
        "repo_worktree": f"`{owner_name}` owner repo at `{owner_scope}` plus `organvm/limen` conductor receipts.",
        "allowed_files": [
            *owner_allowed,
            "docs/session-corpus-ledger.md",
            "docs/session-lifecycle-blockers.md",
            "docs/session-attack-paths.md",
            "docs/conductor-tranche.md",
            ".limen-private/session-corpus/inventory/session-corpus-ledger.json",
            ".limen-private/session-corpus/lifecycle/session-lifecycle-blockers.json",
            ".limen-private/session-corpus/lifecycle/session-attack-paths.json",
            ".limen-private/session-corpus/lifecycle/conductor-tranche.json",
        ],
        "stop_condition": (
            "Stop before content rewriting, synthesis, deletion/revert of owner changes, broad corpus "
            "convergence, owner repo push/PR, or edits outside the listed dirty owner paths unless a "
            "new explicit owner packet opens that scope."
        ),
        "verification": [
            f"git -C {owner_scope} status --branch --short",
            f"git -C {owner_scope} diff --name-status",
            f"git -C {owner_scope} diff --check",
            "python3 scripts/session-corpus-ledger.py --write --all",
            "python3 scripts/session-blockers-ledger.py --write",
            "python3 scripts/session-attack-paths.py --write",
            "python3 scripts/conductor-tranche.py --write",
        ],
        "receipt": (
            f"`{owner_name}` owner branch/commit or patch receipt, plus refreshed "
            "docs/session-corpus-ledger.md, docs/session-lifecycle-blockers.md, and docs/conductor-tranche.md."
        ),
        "owner_state": {
            "owner": owner_name,
            "owner_path": str(owner_path),
            "dirty_entries": dirty_count,
            "dirty_paths": dirty_paths,
            "blocker_source": blocker.get("source"),
        },
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
            "purpose": (
                "Record that no ranked path is autonomously actionable after skipping parked, "
                "family, human-gated, observe, and auth-only lanes."
            ),
            "repo_worktree": "`organvm/limen` conductor checkout.",
            "allowed_files": [
                "scripts/live-root-gate.py",
                "docs/session-attack-paths.md",
                "docs/session-lifecycle-blockers.md",
                "docs/live-root-gate.md",
                "docs/conductor-tranche.md",
                ".limen-private/session-corpus/lifecycle/**",
            ],
            "stop_condition": (
                "Stop before broad delegation, cleanup, GitHub mutation, credential work, or owner "
                "repo edits; resume only when a human opens a gate or a fresh actionable packet appears."
            ),
            "verification": [
                "python3 scripts/live-root-gate.py --write",
                "python3 scripts/session-blockers-ledger.py --write",
                "python3 scripts/session-attack-paths.py --write",
                "python3 scripts/conductor-tranche.py --write",
            ],
            "receipt": "docs/live-root-gate.md and docs/conductor-tranche.md record the human-gated stop state.",
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
    if category == "local_network_substrate":
        return local_network_packet(path)
    if category == "capability_substrate":
        return capability_substrate_packet(path)
    if category == "owner_state":
        return owner_state_packet(path)
    if category in {"remote_receipt", "dispatch_lifecycle", "task_board"} or lane == "remote-close":
        return dispatch_packet(path)
    return default_packet(path)


def build_snapshot() -> dict[str, Any]:
    attack = load_json(ATTACK_INDEX)
    ranked = as_list(attack.get("ranked_paths"))
    selected = select_path(ranked)
    packet = packet_for_path(selected)
    selected_id = str(
        (selected or {}).get("id")
        or ("no-autonomous-actionable-path" if ranked else "missing-ranked-path")
    )
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
        "- Close incident classes with reusable receipts and gates, not one-lane symptom patches.",
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
        "- `python3 scripts/live-root-gate.py --write`",
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
