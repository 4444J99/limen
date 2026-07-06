#!/usr/bin/env python3
"""Turn owned VLTIMA claims into bounded action packets.

This is packetization only. It does not enqueue, edit tasks.yaml, delete, push,
or dispatch. The output is the reviewable boundary between doctrine and work.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1])).expanduser().resolve()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
).expanduser()
OWNER_INDEX = PRIVATE_ROOT / "lifecycle" / "vltima-owner-certainty.json"
DIGEST_PATH = PRIVATE_ROOT / "lifecycle" / "vltima-result-digest.json"
DOC_PATH = ROOT / "docs" / "vltima-action-packets.md"
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "vltima-action-packets.json"
VERIFY_COMMAND = "python3 scripts/vltima-organ.py --check"


def _load_owner_module():
    script = ROOT / "scripts" / "vltima-owner-certainty.py"
    spec = importlib.util.spec_from_file_location("vltima_owner_certainty_runtime", script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_text(value: Any, *, limit: int = 140) -> str:
    text = str(value or "").replace("\n", " ").replace("\r", " ").strip()
    text = text.replace(str(Path.home()), "~").replace(str(ROOT), "$LIMEN_ROOT")
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def load_or_build_certainty(owner_index: Path = OWNER_INDEX, digest_path: Path = DIGEST_PATH) -> dict[str, Any]:
    if owner_index.exists():
        return load_json(owner_index)
    owner = _load_owner_module()
    return owner.build_certainty(digest_path=digest_path)


def packet_id(index: int, claim: dict[str, Any]) -> str:
    subject = safe_text(claim.get("subject"), limit=60).lower()
    subject = "".join(ch if ch.isalnum() else "-" for ch in subject).strip("-") or "claim"
    return f"VLTIMA-PACKET-{index:03d}-{subject[:48]}"


def mutation_level(claim: dict[str, Any]) -> str:
    next_action = safe_text(claim.get("next_action"), limit=180).lower()
    if any(word in next_action for word in ("delete", "remove", "purge", "credential", "secret", "send", "spend")):
        return "human_gated"
    if next_action:
        return "bounded_write"
    return "review_only"


def build_packets(certainty: dict[str, Any], *, limit: int = 40) -> dict[str, Any]:
    candidates = [
        claim
        for claim in certainty.get("claims", [])
        if claim.get("action_level") == "packet_candidate"
        and claim.get("owner_status") == "owned_current"
        and claim.get("owner")
    ]
    packets: list[dict[str, Any]] = []
    for idx, claim in enumerate(candidates[:limit], start=1):
        level = mutation_level(claim)
        packets.append(
            {
                "id": packet_id(idx, claim),
                "status": "candidate",
                "owner": claim["owner"],
                "target_repo": "$LIMEN_ROOT",
                "target_worktree": "$LIMEN_ROOT",
                "surface": claim.get("surface"),
                "subject": claim.get("subject"),
                "summary": claim.get("summary"),
                "next_action": claim.get("next_action") or "review current doctrine and choose the smallest bounded next action",
                "mutation_level": level,
                "privacy_class": claim.get("privacy_class", "public_redacted"),
                "verification_command": VERIFY_COMMAND,
                "receipt_target": "docs/vltima-action-packets.md",
                "source_claim": claim.get("id"),
                "evidence_label": claim.get("evidence_label"),
                "enqueue": False,
            }
        )
    level_counts = Counter(packet["mutation_level"] for packet in packets)
    owner_counts = Counter(packet["owner"] for packet in packets)
    return {
        "generated_at": now_iso(),
        "decision": "bounded packets are the only bridge from doctrine to work",
        "privacy": {
            "raw_bodies_read": False,
            "tracked_output": "docs/vltima-action-packets.md",
            "private_index": str(PRIVATE_INDEX),
            "source_owner_index": str(OWNER_INDEX),
        },
        "coverage": {
            "source_claim_count": certainty.get("coverage", {}).get("claim_count", len(certainty.get("claims", []))),
            "candidate_claim_count": len(candidates),
            "packet_count": len(packets),
            "mutation_level_counts": dict(sorted(level_counts.items())),
            "owner_counts": dict(owner_counts.most_common(20)),
            "truncated": len(candidates) > limit,
        },
        "packets": packets,
        "non_dispatch_contract": {
            "enqueue_supported": False,
            "tasks_yaml_mutated": False,
            "remote_push": False,
        },
    }


def render_markdown(packet_index: dict[str, Any]) -> str:
    coverage = packet_index["coverage"]
    level_bits = ", ".join(f"`{key}` {value}" for key, value in coverage["mutation_level_counts"].items())
    lines = [
        "# VLTIMA Action Packets",
        "",
        f"Generated: `{packet_index['generated_at']}`",
        "",
        "## Canonical Decision",
        "",
        "- Result doctrine does not dispatch directly.",
        "- A packet is only a bounded candidate with owner, scope, verification, and receipt target.",
        "- v1 never mutates `tasks.yaml`; enqueue remains a future explicit gate.",
        "",
        "## Coverage",
        "",
        f"- Source claims: `{coverage['source_claim_count']}`.",
        f"- Candidate claims: `{coverage['candidate_claim_count']}`.",
        f"- Packets emitted: `{coverage['packet_count']}`.",
        f"- Mutation levels: {level_bits or 'none'}.",
        f"- Truncated: `{coverage['truncated']}`.",
        "",
        "## Packets",
        "",
    ]
    packets = packet_index["packets"]
    if not packets:
        lines.append("- No packet candidates recorded.")
    else:
        lines.extend(["| Packet | Owner | Mutation | Subject | Next | Verify |", "|---|---|---|---|---|---|"])
        for packet in packets:
            lines.append(
                f"| `{packet['id']}` | `{packet['owner']}` | `{packet['mutation_level']}` | "
                f"`{safe_text(packet['subject'], limit=80)}` | {safe_text(packet['next_action'], limit=120)} | "
                f"`{packet['verification_command']}` |"
            )
    lines.extend(
        [
            "",
            "## Contract",
            "",
            "- `candidate` is not `queued`.",
            "- `human_gated` packets require a separate explicit approval path before mutation.",
            "- Every packet must preserve its receipt target and verification command if later converted into a task.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(
    packet_index: dict[str, Any],
    markdown: str,
    *,
    doc_path: Path = DOC_PATH,
    private_index: Path = PRIVATE_INDEX,
) -> None:
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    private_index.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(markdown, encoding="utf-8")
    private_index.write_text(json.dumps(packet_index, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Packetize VLTIMA owner-certified claims.")
    parser.add_argument("--owner-index", type=Path, default=OWNER_INDEX, help="path to vltima-owner-certainty.json")
    parser.add_argument("--digest", type=Path, default=DIGEST_PATH, help="fallback digest path when owner index is absent")
    parser.add_argument("--limit", type=int, default=40, help="maximum packet candidates to emit")
    parser.add_argument("--write", action="store_true", help="write tracked summary and private index")
    parser.add_argument("--json", action="store_true", help="print packet index JSON")
    args = parser.parse_args()
    try:
        certainty = load_or_build_certainty(owner_index=args.owner_index, digest_path=args.digest)
    except FileNotFoundError:
        print(f"missing owner index or digest; refresh with python3 scripts/vltima-owner-certainty.py --write", file=sys.stderr)
        return 2
    packet_index = build_packets(certainty, limit=args.limit)
    markdown = render_markdown(packet_index)
    if args.write:
        write_outputs(packet_index, markdown)
        print(f"vltima-packetize: wrote {DOC_PATH} and {PRIVATE_INDEX}")
    elif args.json:
        print(json.dumps(packet_index, indent=2, sort_keys=True))
    else:
        print(markdown, end="")
        print("vltima-packetize: dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
