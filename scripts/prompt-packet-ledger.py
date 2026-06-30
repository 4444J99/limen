#!/usr/bin/env python3
"""Packetize open prompt-review batches into bounded owner/task packets.

This is the handoff layer after `prompt-batch-review-ledger.py`. It consumes
redacted indexes only, groups batches that need packetization into family/lane
packets, and emits:

* tracked docs/prompt-packet-ledger.md: public-safe packet queue;
* ignored .limen-private/.../prompt-packet-ledger.json: full hash/session packet evidence.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
BATCH_REVIEW_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-batch-review-ledger.json"
PRIORITY_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-priority-map.json"
ATTACK_INDEX = PRIVATE_ROOT / "lifecycle" / "session-attack-paths.json"
DOC_PATH = ROOT / "docs" / "prompt-packet-ledger.md"
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-packet-ledger.json"
RESOLUTION_RECEIPTS = ROOT / "docs" / "prompt-packet-resolution-receipts.json"

RECORDED_PACKET_STATUSES = {
    "owner-recorded",
    "current-state-recorded",
    "non-source-recorded",
    "superseded-recorded",
}

PACKET_ROUTES = {
    "worktree_lifecycle": {
        "packet_kind": "worktree-preservation",
        "owner": "worktree lifecycle",
        "agent_fit": "codex first; opencode/jules after repo+predicate narrowing",
        "route": "Resolve each listed worktree to preservation proof, owner blocker, remote/default proof, or documented non-source residue.",
        "verification": "python3 scripts/worktree-debt.py && python3 scripts/session-attack-paths.py --write && python3 scripts/prompt-batch-review-ledger.py --write",
    },
    "session_lifecycle": {
        "packet_kind": "session-owner-receipt",
        "owner": "session lifecycle",
        "agent_fit": "codex",
        "route": "Collapse stalled session receipts into owner records, supersession notes, or blocker receipts before delegation.",
        "verification": "python3 scripts/prompt-priority-map.py --write && python3 scripts/prompt-batch-review-ledger.py --write && python3 scripts/prompt-packet-ledger.py --write",
    },
    "github_review": {
        "packet_kind": "github-review-routing",
        "owner": "github review",
        "agent_fit": "codex packetization, then opencode/jules only after repo and PR are explicit",
        "route": "Map each stalled GitHub-review receipt to an owner repo, PR/issue receipt, predicate, and merge/supersession gate.",
        "verification": "python3 scripts/session-attack-paths.py --write && python3 scripts/prompt-packet-ledger.py --write",
    },
    "agent_coordination": {
        "packet_kind": "agent-coordination",
        "owner": "agent coordination",
        "agent_fit": "codex",
        "route": "Convert broad coordination residue into bounded packets; do not dispatch broad sprawl prompts.",
        "verification": "python3 scripts/prompt-batch-review-ledger.py --write && python3 scripts/prompt-packet-ledger.py --write",
    },
    "technical_debt_ci": {
        "packet_kind": "technical-debt-ci",
        "owner": "technical debt / CI",
        "agent_fit": "codex packetization, then opencode/jules after repo and predicate are explicit",
        "route": "Route CI/debt receipts to an owner repo and narrow predicate before any dispatch.",
        "verification": "python3 scripts/prompt-packet-ledger.py --write",
    },
    "uncategorized": {
        "packet_kind": "uncategorized-private-review",
        "owner": "unassigned corpus review",
        "agent_fit": "codex",
        "route": "Privately classify the receipt, then re-run priority and batch ledgers with an owner route.",
        "verification": "python3 scripts/prompt-priority-map.py --write && python3 scripts/prompt-batch-review-ledger.py --write && python3 scripts/prompt-packet-ledger.py --write",
    },
}


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


def band_rank(band: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3, "parked": 4}.get(band, 5)


def session_lookup(priority: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item["session_key"]): item
        for item in priority.get("session_items") or []
        if isinstance(item, dict) and item.get("session_key")
    }


def attack_lookup(attack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item["id"]): item
        for item in attack.get("ranked_paths") or []
        if isinstance(item, dict) and item.get("id")
    }


def resolution_lookup(receipts: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for receipt in receipts.get("receipts") or []:
        if not isinstance(receipt, dict):
            continue
        packet_id = receipt.get("packet") or receipt.get("packet_id") or receipt.get("id")
        if packet_id:
            rows[str(packet_id)] = receipt
    return rows


def packet_route(family: str) -> dict[str, str]:
    return PACKET_ROUTES.get(family, PACKET_ROUTES["uncategorized"])


def dispatchability_for_packet(packet: dict[str, Any]) -> str:
    if str(packet.get("status") or "") in RECORDED_PACKET_STATUSES:
        return "recorded-owner-receipt"
    family = str(packet.get("family") or "")
    owner_repos = packet.get("owner_repos") or []
    if family in {"worktree_lifecycle", "session_lifecycle", "agent_coordination"}:
        return "codex-owner-packet"
    if owner_repos:
        return "ready-after-predicate"
    return "needs-owner-repo"


def build_packet_key(batch: dict[str, Any], session: dict[str, Any]) -> tuple[str, str]:
    family = str(session.get("family") or "uncategorized")
    return str(batch.get("id") or "unknown-batch"), family


def summarize_resolution(receipt: dict[str, Any]) -> dict[str, Any]:
    roots = [root for root in receipt.get("roots") or [] if isinstance(root, dict)]
    root_statuses = Counter(str(root.get("status") or "unknown") for root in roots)
    root_repos = sorted({str(root.get("repo")) for root in roots if root.get("repo")})
    return {
        "status": str(receipt.get("status") or "owner-recorded"),
        "classification": str(receipt.get("classification") or ""),
        "root_count": len(roots),
        "root_statuses": dict(root_statuses.most_common()),
        "root_repos": root_repos,
        "evidence": receipt.get("evidence") or [],
        "next_action": str(receipt.get("next_action") or ""),
    }


def packet_source_batches(resolutions: dict[str, dict[str, Any]]) -> set[str]:
    batches: set[str] = set()
    for packet_id, receipt in resolutions.items():
        source_batch = receipt.get("source_batch")
        if source_batch:
            batches.add(str(source_batch))
            continue
        if packet_id.startswith("packet-"):
            # Backward-compatible fallback for older receipts without source_batch.
            for family in PACKET_ROUTES:
                suffix = f"-{family}"
                if packet_id.endswith(suffix):
                    batches.add(packet_id.removeprefix("packet-").removesuffix(suffix))
                    break
    return batches


def build_packets(
    review: dict[str, Any],
    priority: dict[str, Any],
    attack: dict[str, Any],
    resolutions: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    sessions_by_key = session_lookup(priority)
    attacks_by_id = attack_lookup(attack)
    resolved_source_batches = packet_source_batches(resolutions)
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    candidate_batches: dict[str, dict[str, Any]] = {}
    for batch in review.get("batches") or []:
        if isinstance(batch, dict) and batch.get("id"):
            candidate_batches[str(batch["id"])] = batch
    for batch in review.get("review_queue") or []:
        if isinstance(batch, dict) and batch.get("id"):
            candidate_batches[str(batch["id"])] = batch
    for batch in candidate_batches.values():
        if not isinstance(batch, dict) or batch.get("status") != "needs-packetization":
            if str(batch.get("lane") or "") != "stalled-review" or str(batch.get("id") or "") not in resolved_source_batches:
                continue
        for session_key in batch.get("session_keys") or []:
            session = sessions_by_key.get(str(session_key))
            if not session:
                continue
            key = build_packet_key(batch, session)
            family = key[1]
            route = packet_route(family)
            packet = grouped.setdefault(
                key,
                {
                    "id": f"packet-{key[0]}-{family}",
                    "source_batch": key[0],
                    "band": batch.get("band"),
                    "lane": batch.get("lane"),
                    "family": family,
                    "status": "packetized",
                    "packet_kind": route["packet_kind"],
                    "owner": route["owner"],
                    "agent_fit": route["agent_fit"],
                    "route": route["route"],
                    "verification": route["verification"],
                    "session_keys": [],
                    "prompt_hashes": [],
                    "worktrees": Counter(),
                    "sources": Counter(),
                    "states": Counter(),
                    "owners": Counter(),
                    "attack_paths": {},
                    "prompt_events": 0,
                    "unique_prompt_hashes": 0,
                    "max_score": 0,
                    "owner_repos": set(),
                },
            )
            packet["session_keys"].append(str(session_key))
            hashes = [str(value) for value in session.get("prompt_hashes") or [] if value]
            packet["prompt_hashes"].extend(hashes)
            packet["prompt_events"] += int(session.get("prompt_events") or 0)
            packet["max_score"] = max(int(packet["max_score"]), int(session.get("score") or 0))
            packet["sources"][str(session.get("source") or "unknown")] += 1
            packet["states"][str(session.get("state") or "unknown")] += 1
            packet["owners"][str(session.get("owner") or "unassigned")] += 1
            worktree = session.get("worktree_slug")
            if worktree:
                root = str(worktree)
                packet["worktrees"][root] += 1
                attack_row = attacks_by_id.get(root)
                if attack_row:
                    packet["attack_paths"][root] = {
                        "score": attack_row.get("score"),
                        "lane": attack_row.get("lane"),
                        "reason": attack_row.get("reason"),
                        "next_action": attack_row.get("next_action"),
                    }
                if root.startswith(("gen-", "cifix-", "bld-", "bld2-", "rev-", "gh-", "resolve-")):
                    # The slug is evidence, not a repo name. Keep it as a routing hint only.
                    pass
    packets = []
    for packet in grouped.values():
        packet["unique_prompt_hashes"] = len(set(packet["prompt_hashes"]))
        packet["worktrees"] = dict(packet["worktrees"].most_common())
        packet["sources"] = dict(packet["sources"].most_common())
        packet["states"] = dict(packet["states"].most_common())
        packet["owners"] = dict(packet["owners"].most_common())
        packet["owner_repos"] = sorted(packet["owner_repos"])
        resolution = resolutions.get(str(packet["id"]))
        if resolution:
            packet["resolution"] = summarize_resolution(resolution)
            packet["status"] = packet["resolution"]["status"]
        else:
            packet["resolution"] = {}
        packet["dispatchability"] = dispatchability_for_packet(packet)
        packets.append(packet)
    return sorted(
        packets,
        key=lambda item: (
            band_rank(str(item["band"])),
            -int(item["max_score"]),
            -int(item["prompt_events"]),
            str(item["source_batch"]),
            str(item["family"]),
        ),
    )


def build_snapshot(limit: int) -> dict[str, Any]:
    review = load_json(BATCH_REVIEW_INDEX)
    priority = load_json(PRIORITY_INDEX)
    attack = load_json(ATTACK_INDEX)
    resolution_receipts = load_json(RESOLUTION_RECEIPTS)
    resolutions = resolution_lookup(resolution_receipts)
    packets = build_packets(review, priority, attack, resolutions)
    recorded_packets = [
        packet for packet in packets if str(packet.get("status") or "") in RECORDED_PACKET_STATUSES
    ]
    open_packets = [
        packet for packet in packets if str(packet.get("status") or "") not in RECORDED_PACKET_STATUSES
    ]
    status_counts = Counter(str(packet["dispatchability"]) for packet in packets)
    packet_status_counts = Counter(str(packet["status"]) for packet in packets)
    family_counts = Counter(str(packet["family"]) for packet in packets)
    source_batches = Counter(str(packet["source_batch"]) for packet in packets)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    return {
        "generated_at": now,
        "inputs": {
            "prompt_batch_review_ledger": {"path": str(BATCH_REVIEW_INDEX), "present": bool(review)},
            "prompt_priority_map": {"path": str(PRIORITY_INDEX), "present": bool(priority)},
            "session_attack_paths": {"path": str(ATTACK_INDEX), "present": bool(attack)},
            "packet_resolution_receipts": {
                "path": str(RESOLUTION_RECEIPTS),
                "present": bool(resolutions),
            },
        },
        "coverage": {
            "source_review_batches": len(review.get("batches") or []),
            "needs_packetization_batches": int((review.get("counts") or {}).get("statuses", {}).get("needs-packetization", 0)),
            "packets": len(packets),
            "recorded_packets": len(recorded_packets),
            "open_packets": len(open_packets),
            "session_receipts": sum(len(packet["session_keys"]) for packet in packets),
            "prompt_events": sum(int(packet["prompt_events"]) for packet in packets),
            "unique_prompt_hash_refs": sum(int(packet["unique_prompt_hashes"]) for packet in packets),
            "packet_resolution_receipts": len(resolutions),
        },
        "counts": {
            "dispatchability": dict(status_counts.most_common()),
            "packet_statuses": dict(packet_status_counts.most_common()),
            "families": dict(family_counts.most_common()),
            "source_batches": dict(source_batches.most_common()),
        },
        "recorded_packets": recorded_packets,
        "open_packets": open_packets,
        "packets": packets,
        "private_index": str(PRIVATE_INDEX),
    }


def render_counts(counts: dict[str, int]) -> str:
    return ", ".join(f"`{key}` {value}" for key, value in counts.items()) or "none"


def render_markdown(snapshot: dict[str, Any], *, limit: int) -> str:
    coverage = snapshot["coverage"]
    recorded_packets = snapshot["recorded_packets"][:limit]
    packets = snapshot["open_packets"][:limit]
    lines = [
        "# Prompt Packet Ledger",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        "",
        "## Canonical Decision",
        "",
        "- Packets are bounded owner/task units derived from redacted batch/session hashes.",
        "- Packetization is not dispatch by itself; a packet needs an owner repo or owner ledger, a narrow predicate, no secret dependency, and an expected receipt before external delegation.",
        "- Stalled-review packets default to Codex because they require lifecycle judgment before cheaper lanes can safely execute.",
        "- This ledger contains no raw prompt or session text.",
        "",
        "## Coverage",
        "",
        f"- Source review batches: `{coverage.get('source_review_batches', 0)}`.",
        f"- Batches needing packetization: `{coverage.get('needs_packetization_batches', 0)}`.",
        f"- Packets emitted: `{coverage.get('packets', 0)}`.",
        f"- Recorded packets: `{coverage.get('recorded_packets', 0)}`.",
        f"- Open packets: `{coverage.get('open_packets', 0)}`.",
        f"- Session receipts packetized: `{coverage.get('session_receipts', 0)}`.",
        f"- Prompt events packetized: `{coverage.get('prompt_events', 0)}`.",
        f"- Unique prompt hash refs in packets: `{coverage.get('unique_prompt_hash_refs', 0)}`.",
        f"- Packet resolution receipts: `{coverage.get('packet_resolution_receipts', 0)}`.",
        f"- Packet status mix: {render_counts(snapshot['counts']['packet_statuses'])}.",
        f"- Dispatchability mix: {render_counts(snapshot['counts']['dispatchability'])}.",
        f"- Family mix: {render_counts(snapshot['counts']['families'])}.",
        "",
        "## Recorded Packets",
        "",
        "| Rank | Packet | Status | Family | Sessions | Events | Root Evidence | Gate |",
        "|---:|---|---|---|---:|---:|---|---|",
    ]
    for rank, packet in enumerate(recorded_packets, start=1):
        resolution = packet.get("resolution") or {}
        root_bits = render_counts(resolution.get("root_statuses") or {})
        gate = resolution.get("next_action") or "Recorded; no broad delegation from this packet."
        lines.append(
            f"| {rank} | `{packet['id']}` | `{packet['status']}` | `{packet['family']}` | "
            f"{len(packet['session_keys'])} | {packet['prompt_events']} | {root_bits} | {gate} |"
        )
    if not recorded_packets:
        lines.append("| 0 | none | n/a | n/a | 0 | 0 | none | n/a |")

    lines += [
        "",
        "## Packet Queue",
        "",
        "| Rank | Packet | Source Batch | Family | Dispatch Gate | Sessions | Events | Worktrees | Agent Fit | Predicate |",
        "|---:|---|---|---|---|---:|---:|---|---|---|",
    ]
    for rank, packet in enumerate(packets, start=1):
        worktrees = ", ".join(f"`{root}`" for root in list((packet.get("worktrees") or {}).keys())[:5]) or "none"
        lines.append(
            f"| {rank} | `{packet['id']}` | `{packet['source_batch']}` | `{packet['family']}` | "
            f"`{packet['dispatchability']}` | {len(packet['session_keys'])} | {packet['prompt_events']} | "
            f"{worktrees} | {packet['agent_fit']} | `{packet['verification']}` |"
        )
    if not packets:
        lines.append("| 0 | none | n/a | n/a | n/a | 0 | 0 | none | n/a | n/a |")

    lines += [
        "",
        "## Packet Routes",
        "",
        "| Packet | Owner | Route |",
        "|---|---|---|",
    ]
    for packet in packets:
        lines.append(f"| `{packet['id']}` | {packet['owner']} | {packet['route']} |")
    if not packets:
        lines.append("| none | n/a | n/a |")

    lines += [
        "",
        "## Private Output",
        "",
        f"- Prompt packet private index: `{relpath(PRIVATE_INDEX)}`.",
        "- The private index keeps packet membership, prompt hashes, session keys, worktree slugs, and attack-path evidence; it contains no prompt text.",
        f"- Public packet resolution receipts: `{RESOLUTION_RECEIPTS.relative_to(ROOT)}`.",
        "",
        "## Commands",
        "",
        "- Refresh prerequisites: `python3 scripts/prompt-batch-review-ledger.py --write && python3 scripts/prompt-priority-map.py --write`",
        "- Refresh this packet ledger: `python3 scripts/prompt-packet-ledger.py --write`",
        "- Show a wider tracked slice: `python3 scripts/prompt-packet-ledger.py --write --limit 60`",
        "",
    ]
    return "\n".join(lines)


def write_outputs(snapshot: dict[str, Any], markdown: str) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(markdown, encoding="utf-8")
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build redacted prompt packet ledger.")
    parser.add_argument("--write", action="store_true", help="write docs and ignored private index")
    parser.add_argument("--limit", type=int, default=30, help="packets to show in tracked docs")
    args = parser.parse_args()

    snapshot = build_snapshot(limit=max(1, args.limit))
    markdown = render_markdown(snapshot, limit=max(1, args.limit))
    if args.write:
        write_outputs(snapshot, markdown)
    else:
        print(markdown)
    msg = (
        "prompt-packet-ledger: "
        f"{snapshot['coverage']['packets']} packets, "
        f"{snapshot['coverage']['session_receipts']} sessions, "
        f"{snapshot['coverage']['prompt_events']} prompt events"
    )
    if args.write:
        msg += f"; wrote {DOC_PATH}"
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
