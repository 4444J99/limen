#!/usr/bin/env python3
"""Record parked lifecycle blockers without leaking raw session material.

This ledger is the "hang it, do not solve it inline" rail for the session/corpus
intake. It reads the already-redacted private lifecycle indexes, derives the
blocked workstreams that need their own owner, and writes:

* a tracked Markdown receipt with counts, owners, and routes only;
* an ignored private JSON receipt with source paths and structured evidence.

It never reads secret values and never attempts account, login, deploy, or
credential repair.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli" / "src"))

from limen.runtime_config import RUNTIME_URL_ENV_ORDER
from limen.worktree_debt import worktree_debt_report

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
DOC_PATH = ROOT / "docs" / "session-lifecycle-blockers.md"
PRIVATE_ROOT = Path(os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus"))
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "session-lifecycle-blockers.json"
PROMPT_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
CODEX_INDEX = PRIVATE_ROOT / "lifecycle" / "codex-session-lifecycle.json"
CORPUS_INVENTORY = PRIVATE_ROOT / "inventory" / "session-corpus-ledger.json"
PRESERVATION_RECEIPTS = ROOT / "docs" / "worktree-preservation-receipts.json"
PRESSURE_INDEX = ROOT / "logs" / "session-lifecycle-pressure.json"
CAPABILITY_INDEX = PRIVATE_ROOT / "lifecycle" / "capability-substrate-index.json"
CONSOLIDATION_INDEX = PRIVATE_ROOT / "lifecycle" / "consolidation-gates.json"
NETWORK_HEALTH_INDEX = PRIVATE_ROOT / "lifecycle" / "network-health.json"
DISPATCH_HEALTH_INDEX = PRIVATE_ROOT / "lifecycle" / "dispatch-health.json"
LIVE_ROOT_GATE_INDEX = PRIVATE_ROOT / "lifecycle" / "live-root-gate.json"
CAPABILITY_REPO_ROOT = Path(os.environ.get("LIMEN_CAPABILITY_REPO_ROOT", ROOT))
REMOTE_MISSING_CLOSED_REASONS = {
    "clean+merged+idle",
    "documented-residue",
    "owner-blocker",
    "remote-default-proof",
    "remote-merged",
    "remote-pr-open",
    "remote-superseded",
}
REMOTE_MISSING_CLOSED_STATUSES = {
    "cache_only_residue",
    "default_branch_preserved",
    "documented_non_source_residue",
    "empty_generated_residue",
    "history_mismatch_patch_preserved",
    "merged_pr_preserved",
    "open_pr_preserved",
    "private_patch_preserved",
    "superseded_on_origin_main",
}
PROJECT_SETTINGS = ROOT / ".claude" / "settings.json"

CLOUD_CREDENTIAL_FLAGS = (
    "CLOUDFLARE_API_TOKEN",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "LIMEN_API_TOKEN",
    "LIMEN_CLIENT_TOKEN",
    "NETLIFY_AUTH_TOKEN",
    "VERCEL_TOKEN",
)
RUNTIME_ENDPOINT_FLAGS = RUNTIME_URL_ENV_ORDER

CAPABILITY_ROOTS_ENV = "LIMEN_CAPABILITY_ROOTS"
DEFAULT_CAPABILITY_ROOTS = (
    HOME / ".codex" / "skills",
    HOME / ".codex" / "plugins",
    HOME / ".claude" / "plugins",
    HOME / "Workspace" / "organvm" / "_agent",
    HOME / "Workspace" / "organvm" / "claude-runtime-state",
    HOME / "Workspace" / "organvm" / "a-i--skills",
    HOME / "Workspace" / "a-i--skills",
    HOME / "Workspace" / "domus-genoma",
    HOME / "Workspace" / "4444J99",
    CAPABILITY_REPO_ROOT / ".agents",
    CAPABILITY_REPO_ROOT / ".claude" / "skills",
    CAPABILITY_REPO_ROOT / "mcp",
)
CAPABILITY_SKIP_DIRS = {"node_modules", ".git", ".venv", "venv", "__pycache__", ".next", "dist", "build", "portvs"}


def load_json(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    return obj if isinstance(obj, dict) else {}


def preservation_receipts_by_root() -> dict[str, dict[str, Any]]:
    data = load_json(PRESERVATION_RECEIPTS)
    receipts: dict[str, dict[str, Any]] = {}
    for receipt in data.get("receipts") or []:
        if not isinstance(receipt, dict):
            continue
        root = receipt.get("root")
        if root:
            receipts[str(root)] = receipt
    return receipts


def receipt_closes_remote_missing(receipt: dict[str, Any] | None) -> bool:
    if not receipt:
        return False
    lane = str(receipt.get("lane") or "")
    status = str(receipt.get("status") or "")
    return lane in REMOTE_MISSING_CLOSED_REASONS or status in REMOTE_MISSING_CLOSED_STATUSES


def live_scanner_defers_remote_missing(reason: str) -> bool:
    return reason in REMOTE_MISSING_CLOSED_REASONS or reason.startswith("active(<")


def current_worktree_report(prompt: dict[str, Any]) -> dict[str, Any]:
    prompt_report = prompt.get("worktree_report") or {}
    try:
        live_report = worktree_debt_report(ROOT)
    except Exception:
        return prompt_report if isinstance(prompt_report, dict) else {}
    prompt_items = [item for item in (prompt_report.get("items") if isinstance(prompt_report, dict) else []) or []]
    live_items = [item for item in live_report.get("items") or [] if isinstance(item, dict)]
    if live_items and prompt_items:
        prompt_names = {str(item.get("name") or "") for item in prompt_items if isinstance(item, dict)}
        live_names = {str(item.get("name") or "") for item in live_items}
        if prompt_names and live_names.isdisjoint(prompt_names):
            return prompt_report if isinstance(prompt_report, dict) else {}
    if live_items:
        return live_report
    return prompt_report if isinstance(prompt_report, dict) else {}


def dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for child in path.rglob("*"):
        if not child.is_file():
            continue
        try:
            total += child.stat().st_size
        except OSError:
            continue
    return total


def fmt_bytes(n: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    value = float(n)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{n} B"


def capability_roots() -> list[Path]:
    raw = os.environ.get(CAPABILITY_ROOTS_ENV)
    if raw:
        return [Path(part).expanduser() for part in raw.split(os.pathsep) if part]
    return list(DEFAULT_CAPABILITY_ROOTS)


def _walk_capability_files(root: Path, *, limit: int = 50000) -> list[Path]:
    if not root.exists():
        return []
    out: list[Path] = []
    stack = [root]
    while stack and len(out) < limit:
        current = stack.pop()
        try:
            children = sorted(current.iterdir(), key=lambda path: path.name)
        except OSError:
            continue
        for child in children:
            if child.name in CAPABILITY_SKIP_DIRS:
                continue
            if child.is_dir():
                stack.append(child)
            elif child.is_file():
                out.append(child)
                if len(out) >= limit:
                    break
    return out


def capability_substrate_snapshot() -> dict[str, Any]:
    roots = [root for root in capability_roots() if root.exists()]
    skill_files = 0
    plugin_manifests = 0
    mcp_acp_markers = 0
    scanned_files = 0
    truncated_roots = 0
    samples = []

    for root in roots:
        files = _walk_capability_files(root)
        scanned_files += len(files)
        if len(files) >= 50000:
            truncated_roots += 1
        root_skill_files = 0
        root_plugin_manifests = 0
        root_mcp_acp_markers = 0
        for path in files:
            name = path.name.lower()
            parent_names = {part.lower() for part in path.parts[-4:]}
            if path.name in {"SKILL.md", "skill.md"} or path.suffix == ".skill":
                skill_files += 1
                root_skill_files += 1
            if (
                path.name in {"plugin.json", ".mcp.json", "mcp.json"}
                or ".claude-plugin" in parent_names
                or ".codex-plugin" in parent_names
            ):
                plugin_manifests += 1
                root_plugin_manifests += 1
            if "mcp" in name or "acp" in name or "mcp" in parent_names or "acp" in parent_names:
                mcp_acp_markers += 1
                root_mcp_acp_markers += 1
        samples.append(
            {
                "root": relpath(root),
                "skill_files": root_skill_files,
                "plugin_manifests": root_plugin_manifests,
                "mcp_acp_markers": root_mcp_acp_markers,
                "scanned_files": len(files),
            }
        )

    return {
        "roots_seen": len(roots),
        "roots_sample": samples[:12],
        "skill_files": skill_files,
        "plugin_manifests": plugin_manifests,
        "mcp_acp_markers": mcp_acp_markers,
        "scanned_files": scanned_files,
        "truncated_roots": truncated_roots,
    }


def capability_receipt_status(capability: dict[str, Any]) -> dict[str, Any]:
    receipt = load_json(CAPABILITY_INDEX)
    coverage = receipt.get("coverage") or {}
    count_keys = ("roots_seen", "skill_files", "plugin_manifests", "mcp_acp_markers")
    current_counts = {key: int(capability.get(key) or 0) for key in count_keys}
    receipt_counts = {key: int(coverage.get(key) or 0) for key in count_keys}
    present = bool(receipt)
    current = present and current_counts == receipt_counts
    return {
        "path": str(CAPABILITY_INDEX),
        "present": present,
        "current": current,
        "generated_at": receipt.get("generated_at"),
        "current_counts": current_counts,
        "receipt_counts": receipt_counts,
        "activation_candidates": len(receipt.get("activation_queue") or []),
        "activation_groups": len(receipt.get("activation_groups") or {}),
    }


def relpath(path: Path) -> str:
    try:
        return "~/" + str(path.expanduser().resolve().relative_to(HOME))
    except (OSError, ValueError):
        return str(path)


def states_text(states: dict[str, Any]) -> str:
    if not states:
        return "none"
    return ", ".join(f"{state} {count}" for state, count in sorted(states.items()))


def add_blocker(
    blockers: list[dict[str, Any]],
    *,
    blocker_id: str,
    category: str,
    evidence: str,
    owner: str,
    route: str,
    status: str = "parked",
    source: str,
    details: dict[str, Any] | None = None,
) -> None:
    blockers.append(
        {
            "id": blocker_id,
            "category": category,
            "status": status,
            "evidence": evidence,
            "owner": owner,
            "route": route,
            "source": source,
            "details": details or {},
        }
    )


def codex_auth_blocker(codex: dict[str, Any], blockers: list[dict[str, Any]]) -> None:
    families = {
        str(item.get("family")): item
        for item in codex.get("families", [])
        if isinstance(item, dict) and item.get("family")
    }
    family = families.get("auth_credentials")
    sessions = int((family or {}).get("sessions") or (codex.get("by_family") or {}).get("auth_credentials") or 0)
    if sessions <= 0:
        return
    states = (family or {}).get("states") or {}
    add_blocker(
        blockers,
        blocker_id="credential-codex-auth-sessions",
        category="auth_credentials",
        evidence=f"{sessions} Codex sessions classified as auth/credential work; states: {states_text(states)}",
        owner="credential workstream",
        route="Keep parked unless a future scoped task explicitly requires the account action.",
        source="codex-session-lifecycle",
        details={"sessions": sessions, "states": states},
    )


def cloud_blockers(prompt: dict[str, Any], blockers: list[dict[str, Any]]) -> None:
    cloud = prompt.get("cloud") or {}
    if not cloud.get("enabled"):
        add_blocker(
            blockers,
            blocker_id="cloud-receipts-disabled",
            category="cloud_receipt",
            evidence="Cloud receipt collection was disabled on the last prompt lifecycle run.",
            owner="limen control plane",
            route="Refresh `prompt-lifecycle-ledger.py --write --all` before treating cloud coverage as current.",
            status="needs_refresh",
            source="prompt-lifecycle-index",
        )
        return

    flags = cloud.get("env_flags") or {}
    absent_credentials = [name for name in CLOUD_CREDENTIAL_FLAGS if flags.get(name) is False]
    present_credentials = [name for name in CLOUD_CREDENTIAL_FLAGS if flags.get(name) is True]
    if absent_credentials:
        add_blocker(
            blockers,
            blocker_id="cloud-credential-handles-unconfigured",
            category="auth_credentials",
            evidence=(
                f"{len(absent_credentials)} credential/deploy handles absent; "
                f"{len(present_credentials)} present. No values inspected."
            ),
            owner="credential workstream",
            route="Do not repair inline; open a bounded credential/setup workstream only when a cloud action requires it.",
            source="prompt-lifecycle-index",
            details={"absent_handles": absent_credentials, "present_handle_count": len(present_credentials)},
        )

    absent_runtime = [name for name in RUNTIME_ENDPOINT_FLAGS if flags.get(name) is False]
    if absent_runtime and not cloud.get("runtime_url_configured"):
        add_blocker(
            blockers,
            blocker_id="cloud-runtime-endpoint-unconfigured",
            category="cloud_runtime",
            evidence="No runtime URL was configured for the last cloud receipt probe.",
            owner="limen deployment workstream",
            route="Keep separate from session intake; configure/probe runtime only in a deploy/runtime task.",
            source="prompt-lifecycle-index",
            details={"absent_runtime_handles": absent_runtime},
        )

    probes = cloud.get("public_surface_probes") or []
    failed_public = [p for p in probes if isinstance(p, dict) and not p.get("ok")]
    if failed_public:
        add_blocker(
            blockers,
            blocker_id="cloud-public-surface-probe-failures",
            category="cloud_receipt",
            evidence=f"{len(failed_public)} public cloud surface probes failed.",
            owner="limen deployment workstream",
            route="Record as deployment/runtime receipt work; do not mix with local prompt absorption.",
            status="needs_refresh",
            source="prompt-lifecycle-index",
            details={"failed_probe_count": len(failed_public)},
        )


def unresolved_missing_remote_roots(
    prompt: dict[str, Any], worktree_report: dict[str, Any]
) -> tuple[list[str], list[str]]:
    worktrees = (prompt.get("remote") or {}).get("worktrees") or {}
    raw_missing = [
        str(receipt.get("name"))
        for receipt in worktrees.get("receipts") or []
        if isinstance(receipt, dict) and receipt.get("remote_branch") == "missing" and receipt.get("name")
    ]
    if not raw_missing:
        count = int(worktrees.get("remote_branches_missing") or 0)
        return ([f"unknown-{idx + 1}" for idx in range(count)], [])

    receipts_by_root = preservation_receipts_by_root()
    by_name = {
        str(item.get("name")): item
        for item in worktree_report.get("items") or []
        if isinstance(item, dict) and item.get("name")
    }
    if not by_name:
        closed = [root for root in raw_missing if receipt_closes_remote_missing(receipts_by_root.get(root))]
        unresolved = [root for root in raw_missing if root not in set(closed)]
        return unresolved, closed

    unresolved: list[str] = []
    closed: list[str] = []
    for root in raw_missing:
        item = by_name.get(root)
        reason = str((item or {}).get("reason") or "")
        if (
            item and not item.get("debt") and live_scanner_defers_remote_missing(reason)
        ) or receipt_closes_remote_missing(receipts_by_root.get(root)):
            closed.append(root)
        else:
            unresolved.append(root)
    return unresolved, closed


def remote_blockers(prompt: dict[str, Any], worktree_report: dict[str, Any], blockers: list[dict[str, Any]]) -> None:
    remote = prompt.get("remote") or {}
    if not remote.get("enabled"):
        add_blocker(
            blockers,
            blocker_id="remote-receipts-disabled",
            category="remote_receipt",
            evidence="Remote receipt collection was disabled on the last prompt lifecycle run.",
            owner="limen control plane",
            route="Refresh with remote enabled before using GitHub state as closure proof.",
            status="needs_refresh",
            source="prompt-lifecycle-index",
        )
        return

    task_prs = remote.get("task_prs") or {}
    counts = Counter(task_prs.get("counts") or {})
    errors = int(counts.get("ERROR", 0))
    if errors:
        add_blocker(
            blockers,
            blocker_id="remote-task-pr-receipt-errors",
            category="remote_receipt",
            evidence=f"{errors} task-board GitHub PR receipts returned API/lookup errors.",
            owner="limen/GitHub receipt workstream",
            route="Rerun or repair access separately before treating those PR refs as closure evidence.",
            status="needs_refresh",
            source="prompt-lifecycle-index",
            details={"counts": dict(counts)},
        )

    worktrees = remote.get("worktrees") or {}
    raw_missing = int(worktrees.get("remote_branches_missing") or 0)
    unresolved_missing, closed_missing = unresolved_missing_remote_roots(prompt, worktree_report)
    if unresolved_missing:
        add_blocker(
            blockers,
            blocker_id="worktree-remote-branches-missing",
            category="worktree_lifecycle",
            evidence=(
                f"{len(unresolved_missing)} git worktree roots still lack remote-branch preservation proof "
                f"({raw_missing} raw missing; {len(closed_missing)} closed by live scanner receipts)."
            ),
            owner="worktree lifecycle",
            route="Preserve each root by branch, PR, owner blocker, or documented non-source residue before cleanup.",
            source="prompt-lifecycle-index",
            details={
                "remote_branches_missing": len(unresolved_missing),
                "raw_remote_branches_missing": raw_missing,
                "closed_by_live_scanner": closed_missing,
                "unresolved_roots": unresolved_missing,
            },
        )


def task_and_worktree_blockers(
    prompt: dict[str, Any],
    worktree_report: dict[str, Any],
    blockers: list[dict[str, Any]],
) -> None:
    tasks = prompt.get("task_snapshot") or {}
    invalid = tasks.get("invalid_statuses") or []
    if invalid:
        add_blocker(
            blockers,
            blocker_id="task-board-invalid-statuses",
            category="task_board",
            evidence=f"{len(invalid)} task-board statuses are outside the canonical state set.",
            owner="limen task board",
            route="Fix state vocabulary before dispatch/harvest can be trusted.",
            status="needs_repair",
            source="prompt-lifecycle-index",
            details={"invalid_statuses": invalid},
        )

    stranded = int(tasks.get("dispatched_without_pr_receipt") or 0)
    if stranded:
        add_blocker(
            blockers,
            blocker_id="dispatched-local-no-pr-receipts",
            category="dispatch_lifecycle",
            evidence=f"{stranded} dispatched local tasks are stranded without PR receipt.",
            owner="limen dispatch",
            route="Drain through verify-dispatch/owner receipts; do not classify as done from chat alone.",
            source="prompt-lifecycle-index",
            details={"dispatched_without_pr_receipt": stranded},
        )

    debt = int(worktree_report.get("debt") or 0)
    if debt:
        add_blocker(
            blockers,
            blocker_id="worktree-lifecycle-debt",
            category="worktree_lifecycle",
            evidence=f"{debt} `.limen-worktrees` roots still carry lifecycle debt.",
            owner="worktree lifecycle",
            route="Preserve or owner-record each root; no deletion of unique work.",
            source="prompt-lifecycle-index",
            details={"debt": debt, "total": worktree_report.get("total")},
        )


def corpus_owner_blockers(corpus: dict[str, Any], blockers: list[dict[str, Any]]) -> None:
    for organ in corpus.get("organs", []) or []:
        if not isinstance(organ, dict):
            continue
        git = organ.get("git") or {}
        if git.get("dirty"):
            name = str(organ.get("name") or "unknown-organ")
            add_blocker(
                blockers,
                blocker_id=f"owner-state-dirty-{name}",
                category="owner_state",
                evidence=f"{name} has {git.get('dirty_entries', 0)} dirty entries.",
                owner=name,
                route="Preserve in that owner repo before treating corpus substrate as clean.",
                source="session-corpus-ledger",
                details={"git_summary": git.get("summary"), "dirty_entries": git.get("dirty_entries", 0)},
            )

    materialization = corpus.get("materialization")
    if not materialization:
        add_blocker(
            blockers,
            blocker_id="private-raw-materialization-not-receipted",
            category="private_absorption",
            evidence="The latest session corpus inventory did not include a materialization receipt.",
            owner="limen private cartridge",
            route="Run `session-corpus-ledger.py --write --all --materialize` when absorbing raw local files.",
            status="needs_refresh",
            source="session-corpus-ledger",
        )


def hook_and_pressure_blockers(
    prompt: dict[str, Any],
    worktree_report: dict[str, Any],
    blockers: list[dict[str, Any]],
) -> dict[str, Any]:
    pressure = load_json(PRESSURE_INDEX)
    settings_text = ""
    try:
        settings_text = PROJECT_SETTINGS.read_text(encoding="utf-8", errors="replace")
    except OSError:
        pass
    try:
        heartbeat_text = (ROOT / "scripts" / "heartbeat-loop.sh").read_text(encoding="utf-8", errors="replace")
    except OSError:
        heartbeat_text = ""
    hook_wired = (
        "session-closeout.sh" in settings_text
        and "session-lifecycle-pressure.sh" not in settings_text
        and (
            "consume-session-end-breadcrumbs.py" in heartbeat_text
            or "consume-session-end-breadcrumbs.py" in settings_text
        )
    )
    if not hook_wired:
        add_blocker(
            blockers,
            blocker_id="session-pressure-hook-not-wired",
            category="hook_lifecycle",
            evidence="SessionEnd breadcrumb production or heartbeat lifecycle consumption is not fully wired.",
            owner="limen hooks",
            route=(
                "Wire the constant-time `scripts/hooks/session-closeout.sh` producer and the heartbeat "
                "`consume-session-end-breadcrumbs.py` drain; never run lifecycle pressure synchronously."
            ),
            status="needs_repair",
            source=".claude/settings.json",
        )

    worktree_bytes = int((pressure.get("worktrees") or {}).get("bytes") or dir_size(ROOT.parent / ".limen-worktrees"))
    private_bytes = int((pressure.get("private_corpus") or {}).get("bytes") or dir_size(PRIVATE_ROOT))
    total_bytes = worktree_bytes + private_bytes
    remote = prompt.get("remote") or {}
    worktree_remote = remote.get("worktrees") or {}
    missing_remote = int(worktree_remote.get("remote_branches_missing") or 0)
    debt = int(worktree_report.get("debt") or 0)
    # Completion is exact zero debt — there is no tolerated count. Any nonzero debt is action-routed.

    if total_bytes:
        add_blocker(
            blockers,
            blocker_id="local-lifecycle-disk-pressure",
            category="local_lean",
            evidence=(
                f"Local lifecycle stores use {fmt_bytes(total_bytes)} "
                f"({fmt_bytes(worktree_bytes)} worktrees, {fmt_bytes(private_bytes)} private corpus)."
            ),
            owner="local lifecycle",
            route="Drain only after remote/default preservation proof or non-source residue receipt; keep pressure visible in SessionStart.",
            source="session-lifecycle-pressure",
            details={
                "total_bytes": total_bytes,
                "worktree_bytes": worktree_bytes,
                "private_corpus_bytes": private_bytes,
                "worktree_debt": debt,
                "worktree_debt_target": 0,
                "worktree_debt_complete": debt == 0,
                "remote_branches_missing": missing_remote,
                "hook_wired": hook_wired,
            },
        )

    return {
        "pressure_present": bool(pressure),
        "hook_wired": hook_wired,
        "worktree_bytes": worktree_bytes,
        "private_corpus_bytes": private_bytes,
        "total_bytes": total_bytes,
    }


def capability_substrate_blockers(blockers: list[dict[str, Any]]) -> dict[str, Any]:
    capability = capability_substrate_snapshot()
    receipt = capability_receipt_status(capability)
    capability["receipt"] = receipt
    capability["resurfaced"] = bool(receipt["current"])
    roots_seen = int(capability.get("roots_seen") or 0)
    if roots_seen and not receipt["current"]:
        if receipt["present"]:
            status = "needs_refresh"
            evidence_prefix = "Capability resurfacing receipt is stale"
        else:
            status = "parked"
            evidence_prefix = "Capability substrate has not been resurfaced"
        add_blocker(
            blockers,
            blocker_id="capability-substrate-not-resurfaced",
            category="capability_substrate",
            status=status,
            evidence=(
                f"{evidence_prefix}; {roots_seen} local capability roots detected; "
                f"{capability.get('skill_files', 0)} skill files, "
                f"{capability.get('plugin_manifests', 0)} plugin/MCP manifests, "
                f"{capability.get('mcp_acp_markers', 0)} MCP/ACP markers counted."
            ),
            owner="agent capability substrate",
            route=(
                "Run `python3 scripts/capability-substrate-ledger.py --write` to index names/counts "
                "and choose activation order; "
                "do not read private skill bodies, install plugins, or repair MCP/ACP auth inside session lifecycle closeout."
            ),
            source="local-capability-substrate",
            details={"capability": capability, "receipt": receipt},
        )
    return capability


def network_health_blockers(blockers: list[dict[str, Any]]) -> dict[str, Any]:
    network = load_json(NETWORK_HEALTH_INDEX)
    if not network:
        add_blocker(
            blockers,
            blocker_id="local-network-health-not-refreshed",
            category="local_network_substrate",
            status="needs_refresh",
            evidence="No current netmode/netmeter network-health receipt is available.",
            owner="local network substrate",
            route=(
                "Run `python3 scripts/network-health.py --write` before treating network failures as "
                "incidental lane flakiness or dispatching broad work."
            ),
            source="network-health",
            details={"path": str(NETWORK_HEALTH_INDEX)},
        )
        return {"present": False, "path": str(NETWORK_HEALTH_INDEX), "status": "missing"}

    status = str(network.get("status") or "unknown")
    network_blockers = [item for item in network.get("blockers") or [] if isinstance(item, dict)]
    if status != "healthy" or network_blockers:
        add_blocker(
            blockers,
            blocker_id="local-network-substrate-unhealthy",
            category="local_network_substrate",
            status="needs_repair",
            evidence=(
                f"Network-health receipt is `{status}` with {len(network_blockers)} blocker(s); "
                "do not treat route drops as one-off lane failures."
            ),
            owner="local network substrate",
            route=(
                "Repair through the netmode owner path, then refresh `python3 scripts/network-health.py --write`; "
                "do not run broad dispatch until the substrate receipt is healthy or explicitly waived."
            ),
            source="network-health",
            details={
                "status": status,
                "blocker_ids": [str(item.get("id") or "unknown") for item in network_blockers],
                "path": str(NETWORK_HEALTH_INDEX),
            },
        )

    route = network.get("route") or {}
    mode = network.get("mode") or {}
    return {
        "present": True,
        "path": str(NETWORK_HEALTH_INDEX),
        "generated_at": network.get("generated_at"),
        "status": status,
        "blockers": len(network_blockers),
        "mode": mode.get("mode"),
        "route_interface": route.get("interface"),
        "route_gateway": route.get("gateway"),
    }


def dispatch_health_blockers(blockers: list[dict[str, Any]]) -> dict[str, Any]:
    dispatch = load_json(DISPATCH_HEALTH_INDEX)
    live_gate = load_json(LIVE_ROOT_GATE_INDEX)
    if not dispatch:
        add_blocker(
            blockers,
            blocker_id="dispatch-health-not-refreshed",
            category="dispatch_lifecycle",
            status="needs_refresh",
            evidence="No current heartbeat/dispatch-health receipt is available.",
            owner="dispatch heartbeat substrate",
            route=(
                "Run `python3 scripts/dispatch-health.py --write --probe-async`; "
                "then run `python3 scripts/live-root-gate.py --write`; "
                "do not enable async or reload launchd from stale dispatch evidence."
            ),
            source="dispatch-health",
            details={"path": str(DISPATCH_HEALTH_INDEX)},
        )
        return {"present": False, "path": str(DISPATCH_HEALTH_INDEX), "status": "missing"}

    status = str(dispatch.get("status") or "unknown")
    receipt_blockers = [item for item in dispatch.get("blockers") or [] if isinstance(item, dict)]
    blocker_ids = [str(item.get("id") or "unknown") for item in receipt_blockers]
    human_gate_ids = {
        "live-root-not-at-origin-main",
        "live-root-dirty",
        "heartbeat-loaded-env-drift",
    }
    if status != "healthy" or receipt_blockers:
        needs_human = any(item in human_gate_ids for item in blocker_ids)
        add_blocker(
            blockers,
            blocker_id="dispatch-heartbeat-substrate-unhealthy",
            category="dispatch_lifecycle",
            status="needs_human_gate" if needs_human else "needs_refresh",
            evidence=(
                f"Dispatch-health receipt is `{status}` with {len(receipt_blockers)} blocker(s): "
                f"{', '.join(blocker_ids) or 'unknown'}."
            ),
            owner="dispatch heartbeat substrate",
            route=(
                "Use `docs/live-root-gate.md` to preserve/reconcile the live Limen root and reload "
                "launchd only under an explicit operator gate; stop before reset, branch switch, "
                "task-board edits, or async enablement."
                if needs_human
                else "Refresh dispatch-health and repair heartbeat/async probes before trusting dispatch receipts."
            ),
            source="dispatch-health",
            details={
                "status": status,
                "blocker_ids": blocker_ids,
                "path": str(DISPATCH_HEALTH_INDEX),
                "live_root_gate_path": str(LIVE_ROOT_GATE_INDEX),
                "live_root_gate_present": bool(live_gate),
            },
        )

    heartbeat = dispatch.get("launchd") or {}
    live_root = dispatch.get("live_root_git") or {}
    async_probe = dispatch.get("async_probe") or {}
    return {
        "present": True,
        "path": str(DISPATCH_HEALTH_INDEX),
        "generated_at": dispatch.get("generated_at"),
        "status": status,
        "blockers": len(receipt_blockers),
        "blocker_ids": blocker_ids,
        "launchd_state": heartbeat.get("state"),
        "launchd_pid": heartbeat.get("pid"),
        "live_root_branch": live_root.get("branch"),
        "live_root_matches_origin_main": live_root.get("matches_origin_main"),
        "live_root_dirty_entries": live_root.get("dirty_entries"),
        "async_probe_requested": async_probe.get("requested"),
        "async_probe_ok": async_probe.get("ok"),
    }


def live_root_gate_summary() -> dict[str, Any]:
    gate = load_json(LIVE_ROOT_GATE_INDEX)
    if not gate:
        return {"present": False, "path": str(LIVE_ROOT_GATE_INDEX), "status": "missing"}
    live = gate.get("live_root_git") or {}
    launchd = gate.get("launchd") or {}
    return {
        "present": True,
        "path": str(LIVE_ROOT_GATE_INDEX),
        "generated_at": gate.get("generated_at"),
        "status": gate.get("status"),
        "blockers": len(gate.get("blockers") or []),
        "operator_gate_required": gate.get("operator_gate_required"),
        "live_root_branch": live.get("branch"),
        "live_root_release_branch": live.get("release_branch"),
        "live_root_unique_commits": live.get("unique_commit_count"),
        "live_root_dirty_entries": live.get("dirty_entries"),
        "launchd_state": launchd.get("state"),
        "launchd_env_drift": len(gate.get("launchd_env_drift") or []),
    }


def consolidation_phase_text(source_repos: int, collisions: int, packet_complete: bool) -> tuple[str, str]:
    if collisions:
        evidence = (
            f"{source_repos} source repos remain outside `organvm`; "
            f"{collisions} name-collision groups block the transfer apply gate."
        )
        if packet_complete:
            route = (
                "Collision packet is complete; await an explicit human GitHub mutation gate to run "
                "`docs/consolidation/COLLISION-RENAMES.md`, then re-run the consolidation dry-run and "
                "require 0 collisions before transfer."
            )
        else:
            route = (
                "Resolve `docs/consolidation/COLLISION-RENAMES.md`, then require "
                "`PYTHONPATH=cli/src python3 scripts/consolidate-github.py` to report 0 collisions "
                "before any transfer."
            )
        return evidence, route

    evidence = (
        f"{source_repos} source repos remain outside `organvm`; "
        "0 name-collision groups remain, so transfer apply is ready only behind an explicit human gate."
    )
    route = (
        "Name collisions are clear; under an explicit human transfer gate, run "
        "`PYTHONPATH=cli/src python3 scripts/consolidate-github.py --apply`, then refresh gates and run "
        "`PYTHONPATH=cli/src python3 scripts/rewrite-owners.py --apply --emit-remotes /tmp/limen-remotes.sh` "
        "after transfer."
    )
    return evidence, route


def consolidation_gate_blockers(blockers: list[dict[str, Any]]) -> dict[str, Any]:
    gate = load_json(CONSOLIDATION_INDEX)
    if not gate:
        add_blocker(
            blockers,
            blocker_id="github-consolidation-gates-not-refreshed",
            category="github_consolidation",
            status="needs_refresh",
            evidence="No current GitHub consolidation gate receipt is available.",
            owner="GitHub consolidation",
            route="Run `python3 scripts/consolidation-gates.py --write` before choosing transfer, rename, owner rewrite, or App identity work.",
            source="consolidation-gates",
            details={"path": str(CONSOLIDATION_INDEX)},
        )
        return {"present": False, "path": str(CONSOLIDATION_INDEX)}

    consolidation = gate.get("consolidation") or {}
    owner_rewrite = gate.get("owner_rewrite") or {}
    app = gate.get("app_identity") or {}
    gates = gate.get("gates") or {}
    collision_packet = gate.get("collision_packet") or {}
    source_repos = int(consolidation.get("source_repos") or 0)
    collisions = int(consolidation.get("collision_groups") or 0)
    task_refs = int(owner_rewrite.get("task_repo_refs_to_rewrite") or 0)
    remotes = int(owner_rewrite.get("local_remotes_to_rewrite") or 0)

    if source_repos or collisions:
        packet_complete = bool(collision_packet.get("complete"))
        evidence, route = consolidation_phase_text(source_repos, collisions, packet_complete)
        add_blocker(
            blockers,
            blocker_id="github-consolidation-collisions",
            category="github_consolidation",
            status="needs_human_gate",
            evidence=evidence,
            owner="GitHub consolidation",
            route=route,
            source="consolidation-gates",
            details={
                "source_repos": source_repos,
                "collision_groups": collisions,
                "task_repo_refs_to_rewrite_post_transfer": task_refs,
                "local_remotes_to_rewrite_post_transfer": remotes,
                "collision_packet_complete": bool(collision_packet.get("complete")),
                "transfer_apply_gate_open": bool((gates or {}).get("can_run_transfer_apply_after_human_gate")),
                "collision_packet_missing_keepers": len(collision_packet.get("missing_keepers") or []),
                "collision_packet_missing_rename_commands": len(collision_packet.get("missing_rename_commands") or []),
                "collision_packet_target_conflicts": len(collision_packet.get("target_conflicts") or []),
                "collision_packet_target_unknown": len(collision_packet.get("target_unknown") or []),
                "blocking": gates.get("blocking") or [],
            },
        )

    if not app.get("app_token_wired"):
        installed = app.get("installed_app_slugs") or []
        add_blocker(
            blockers,
            blocker_id="github-app-limen-bot-not-wired",
            category="github_app_identity",
            status="needs_human_gate",
            evidence=(
                f"`gh-app-token --which` resolves to `{app.get('gh_app_token_which') or 'unavailable'}`; "
                f"{len(installed)} org Apps are installed, and `limen[bot]` is not wired."
            ),
            owner="limen[bot] App identity",
            route=(
                "Create/install the org GitHub App and hydrate credentials via `scripts/set-credential.sh`; "
                "verify `bash scripts/gh-app-token.sh --which` reports the App path."
            ),
            source="consolidation-gates",
            details={
                "installed_app_slugs": installed,
                "limen_app_installed": bool(app.get("limen_app_installed")),
                "app_token_wired": bool(app.get("app_token_wired")),
            },
        )

    return {
        "present": True,
        "path": str(CONSOLIDATION_INDEX),
        "generated_at": gate.get("generated_at"),
        "source_repos": source_repos,
        "collision_groups": collisions,
        "task_repo_refs_to_rewrite_post_transfer": task_refs,
        "local_remotes_to_rewrite_post_transfer": remotes,
        "collision_packet_complete": bool(collision_packet.get("complete")),
        "collision_packet_missing_keepers": len(collision_packet.get("missing_keepers") or []),
        "collision_packet_missing_rename_commands": len(collision_packet.get("missing_rename_commands") or []),
        "collision_packet_target_conflicts": len(collision_packet.get("target_conflicts") or []),
        "collision_packet_target_unknown": len(collision_packet.get("target_unknown") or []),
        "app_token_wired": bool(app.get("app_token_wired")),
        "limen_app_installed": bool(app.get("limen_app_installed")),
        "blocking": gates.get("blocking") or [],
    }


def build_snapshot() -> dict[str, Any]:
    prompt = load_json(PROMPT_INDEX)
    codex = load_json(CODEX_INDEX)
    corpus = load_json(CORPUS_INVENTORY)
    worktree_report = current_worktree_report(prompt)
    blockers: list[dict[str, Any]] = []

    codex_auth_blocker(codex, blockers)
    cloud_blockers(prompt, blockers)
    remote_blockers(prompt, worktree_report, blockers)
    task_and_worktree_blockers(prompt, worktree_report, blockers)
    corpus_owner_blockers(corpus, blockers)
    hook_pressure = hook_and_pressure_blockers(prompt, worktree_report, blockers)
    capability = capability_substrate_blockers(blockers)
    network = network_health_blockers(blockers)
    dispatch = dispatch_health_blockers(blockers)
    live_root_gate = live_root_gate_summary()
    consolidation = consolidation_gate_blockers(blockers)

    by_category = Counter(blocker["category"] for blocker in blockers)
    by_status = Counter(blocker["status"] for blocker in blockers)
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "inputs": {
            "prompt_lifecycle_index": {"path": str(PROMPT_INDEX), "present": bool(prompt)},
            "codex_session_lifecycle": {"path": str(CODEX_INDEX), "present": bool(codex)},
            "session_corpus_inventory": {"path": str(CORPUS_INVENTORY), "present": bool(corpus)},
            "consolidation_gates": {"path": str(CONSOLIDATION_INDEX), "present": bool(consolidation.get("present"))},
            "network_health": {"path": str(NETWORK_HEALTH_INDEX), "present": bool(network.get("present"))},
            "dispatch_health": {"path": str(DISPATCH_HEALTH_INDEX), "present": bool(dispatch.get("present"))},
            "live_root_gate": {"path": str(LIVE_ROOT_GATE_INDEX), "present": bool(live_root_gate.get("present"))},
        },
        "coverage": {
            "prompt_sources": prompt.get("sources") or [],
            "codex_sessions": codex.get("session_count", 0),
            "worktree_debt": worktree_report.get("debt", 0),
            "remote_enabled": bool((prompt.get("remote") or {}).get("enabled")),
            "cloud_enabled": bool((prompt.get("cloud") or {}).get("enabled")),
            "session_pressure_hook_wired": hook_pressure["hook_wired"],
            "session_pressure_present": hook_pressure["pressure_present"],
            "local_lifecycle_bytes": hook_pressure["total_bytes"],
            "capability_substrate": capability,
            "local_network_substrate": network,
            "dispatch_substrate": dispatch,
            "live_root_gate": live_root_gate,
            "github_consolidation": consolidation,
        },
        "blockers": blockers,
        "by_category": dict(sorted(by_category.items())),
        "by_status": dict(sorted(by_status.items())),
        "private_index": str(PRIVATE_INDEX),
    }


def render_markdown(snapshot: dict[str, Any]) -> str:
    inputs = snapshot["inputs"]
    coverage = snapshot["coverage"]
    blockers = snapshot["blockers"]
    prompt_sources = coverage.get("prompt_sources") or []
    total_prompt_files = sum(int(s.get("files", 0)) for s in prompt_sources if isinstance(s, dict))
    total_prompt_events = sum(int(s.get("prompt_events", 0)) for s in prompt_sources if isinstance(s, dict))
    category_bits = ", ".join(f"`{k}` {v}" for k, v in snapshot["by_category"].items()) or "none"
    status_bits = ", ".join(f"`{k}` {v}" for k, v in snapshot["by_status"].items()) or "none"

    lines = [
        "# Session Lifecycle Blockers",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        "",
        "## Canonical Handling",
        "",
        "- Auth, login, secret, key, token, password, deploy-account, and provider-access issues are parked here unless a task explicitly scopes that account action.",
        "- This receipt records handles and counts only. It does not read, print, repair, rotate, or commit secret values.",
        "- A parked blocker is not cancelled work. It is a named owner lane that must be resolved or superseded before the dependent lifecycle can close.",
        "",
        "## Intake Inputs",
        "",
        f"- Prompt lifecycle index present: `{inputs['prompt_lifecycle_index']['present']}` at `{relpath(Path(inputs['prompt_lifecycle_index']['path']))}`.",
        f"- Codex lifecycle index present: `{inputs['codex_session_lifecycle']['present']}` at `{relpath(Path(inputs['codex_session_lifecycle']['path']))}`.",
        f"- Session corpus inventory present: `{inputs['session_corpus_inventory']['present']}` at `{relpath(Path(inputs['session_corpus_inventory']['path']))}`.",
        f"- GitHub consolidation gates present: `{inputs['consolidation_gates']['present']}` at `{relpath(Path(inputs['consolidation_gates']['path']))}`.",
        f"- Network health receipt present: `{inputs['network_health']['present']}` at `{relpath(Path(inputs['network_health']['path']))}`.",
        f"- Dispatch health receipt present: `{inputs['dispatch_health']['present']}` at `{relpath(Path(inputs['dispatch_health']['path']))}`.",
        f"- Live root gate receipt present: `{inputs['live_root_gate']['present']}` at `{relpath(Path(inputs['live_root_gate']['path']))}`.",
        f"- Redacted local prompt coverage: `{total_prompt_files}` files, `{total_prompt_events}` prompt-like events.",
        f"- Codex classified sessions: `{coverage.get('codex_sessions', 0)}`.",
        f"- Worktree debt roots: `{coverage.get('worktree_debt', 0)}`.",
        f"- Remote receipts enabled: `{coverage.get('remote_enabled')}`; cloud receipts enabled: `{coverage.get('cloud_enabled')}`.",
        f"- Session pressure hook wired: `{coverage.get('session_pressure_hook_wired')}`; last pressure snapshot present: `{coverage.get('session_pressure_present')}`.",
        f"- Local lifecycle footprint: `{fmt_bytes(int(coverage.get('local_lifecycle_bytes') or 0))}`.",
        (
            "- Capability substrate detected: "
            f"`{(coverage.get('capability_substrate') or {}).get('roots_seen', 0)}` roots, "
            f"`{(coverage.get('capability_substrate') or {}).get('skill_files', 0)}` skill files, "
            f"`{(coverage.get('capability_substrate') or {}).get('plugin_manifests', 0)}` plugin/MCP manifests."
        ),
        (
            "- Capability resurfacing receipt present/current: "
            f"`{((coverage.get('capability_substrate') or {}).get('receipt') or {}).get('present', False)}`/"
            f"`{((coverage.get('capability_substrate') or {}).get('receipt') or {}).get('current', False)}`; "
            f"activation candidates "
            f"`{((coverage.get('capability_substrate') or {}).get('receipt') or {}).get('activation_candidates', 0)}`."
        ),
        (
            "- Local network substrate: "
            f"status `{(coverage.get('local_network_substrate') or {}).get('status', 'unknown')}`, "
            f"mode `{(coverage.get('local_network_substrate') or {}).get('mode') or 'unknown'}`, "
            f"route `{(coverage.get('local_network_substrate') or {}).get('route_interface') or 'unknown'}` "
            f"via `{(coverage.get('local_network_substrate') or {}).get('route_gateway') or 'unknown'}`."
        ),
        (
            "- Dispatch substrate: "
            f"status `{(coverage.get('dispatch_substrate') or {}).get('status', 'unknown')}`, "
            f"launchd `{(coverage.get('dispatch_substrate') or {}).get('launchd_state') or 'unknown'}`, "
            f"live root `{(coverage.get('dispatch_substrate') or {}).get('live_root_branch') or 'unknown'}`, "
            f"dirty entries `{(coverage.get('dispatch_substrate') or {}).get('live_root_dirty_entries', 0)}`, "
            f"async dry-run ok `{(coverage.get('dispatch_substrate') or {}).get('async_probe_ok')}`."
        ),
        (
            "- Live root gate: "
            f"status `{(coverage.get('live_root_gate') or {}).get('status', 'unknown')}`, "
            f"branch `{(coverage.get('live_root_gate') or {}).get('live_root_branch') or 'unknown'}`, "
            f"unique commits `{(coverage.get('live_root_gate') or {}).get('live_root_unique_commits', 0)}`, "
            f"dirty entries `{(coverage.get('live_root_gate') or {}).get('live_root_dirty_entries', 0)}`, "
            f"launchd env drift `{(coverage.get('live_root_gate') or {}).get('launchd_env_drift', 0)}`."
        ),
        (
            "- GitHub consolidation gate: "
            f"`{(coverage.get('github_consolidation') or {}).get('source_repos', 0)}` source repos, "
            f"`{(coverage.get('github_consolidation') or {}).get('collision_groups', 0)}` collision groups, "
            f"collision packet complete `{(coverage.get('github_consolidation') or {}).get('collision_packet_complete', False)}`, "
            f"App token wired `{(coverage.get('github_consolidation') or {}).get('app_token_wired', False)}`."
        ),
        "",
        "## Parked / Hung Workstreams",
        "",
        f"- By category: {category_bits}.",
        f"- By status: {status_bits}.",
        "",
        "| ID | Category | Status | Evidence | Owner | Route |",
        "|---|---|---|---|---|---|",
    ]
    for blocker in blockers:
        lines.append(
            f"| `{blocker['id']}` | `{blocker['category']}` | `{blocker['status']}` | "
            f"{blocker['evidence']} | {blocker['owner']} | {blocker['route']} |"
        )
    if not blockers:
        lines.append("| none | n/a | n/a | No parked blockers derived from current indexes. | n/a | n/a |")

    lines += [
        "",
        "## Private Output",
        "",
        f"- Private blocker index: `{relpath(PRIVATE_INDEX)}`.",
        "- The private index keeps structured evidence and source paths, still without secret values or raw prompt text.",
        "",
        "## Commands",
        "",
        "- Refresh source receipts first: `python3 scripts/prompt-lifecycle-ledger.py --write --all`",
        "- Refresh private absorption receipt: `python3 scripts/session-corpus-ledger.py --write --all --materialize`",
        "- Refresh capability resurfacing: `python3 scripts/capability-substrate-ledger.py --write`",
        "- Refresh local network health: `python3 scripts/network-health.py --write`",
        "- Refresh dispatch health: `python3 scripts/dispatch-health.py --write --probe-async`",
        "- Refresh live root gate: `python3 scripts/live-root-gate.py --write`",
        "- Refresh GitHub consolidation gates: `python3 scripts/consolidation-gates.py --write`",
        "- Refresh this blocker ledger: `python3 scripts/session-blockers-ledger.py --write`",
        "",
    ]
    return "\n".join(lines)


def write_outputs(snapshot: dict[str, Any], markdown: str) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(markdown, encoding="utf-8")
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh the redacted parked lifecycle blocker ledger.")
    parser.add_argument("--write", action="store_true", help="write docs and ignored private index")
    args = parser.parse_args()

    snapshot = build_snapshot()
    markdown = render_markdown(snapshot)
    if args.write:
        write_outputs(snapshot, markdown)
    else:
        print(markdown)
    msg = f"session-blockers-ledger: {len(snapshot['blockers'])} blockers"
    if args.write:
        msg += f"; wrote {DOC_PATH}"
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
