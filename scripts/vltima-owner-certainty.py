#!/usr/bin/env python3
"""Derive VLTIMA owner certainty from the redacted result digest.

The digest tells us what exists. This layer decides whether a claim has a
rightful owner and whether it can become action. It never reads raw prompt
bodies and never mutates tasks.yaml.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1])).expanduser().resolve()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
).expanduser()
DIGEST_PATH = PRIVATE_ROOT / "lifecycle" / "vltima-result-digest.json"
DOC_PATH = ROOT / "docs" / "vltima-owner-certainty.md"
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "vltima-owner-certainty.json"

PARKED_AUTHORITIES = {"superseded_material", "quarantined_ghost"}
LINEAGE_AUTHORITIES = {"living_lineage", "dormant_ore"}
OWNER_RE = re.compile(r"[^a-z0-9_.:-]+")


LANE_OWNERS = {
    "archive-durability": "limen:archive-durability",
    "capability-substrate": "limen:capability-substrate",
    "hooks-orientation": "limen:hooks-orientation",
    "priority-routing": "limen:priority-routing",
    "product-surface": "limen:product-surface",
    "prompt-lifecycle": "limen:prompt-lifecycle",
    "repo-surfaces": "limen:repo-surfaces",
    "session-corpus": "limen:session-corpus",
    "worktree-preservation": "limen:worktree-preservation",
}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_text(value: Any, *, limit: int = 140) -> str:
    text = str(value or "").replace("\n", " ").replace("\r", " ")
    text = text.replace(str(Path.home()), "~").replace(str(ROOT), "$LIMEN_ROOT")
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def owner_slug(value: str) -> str:
    slug = OWNER_RE.sub("-", value.lower()).strip("-")
    return slug or "unknown"


def derive_owner(claim: dict[str, Any]) -> tuple[str, str]:
    lane = safe_text(claim.get("lane"), limit=80)
    surface = safe_text(claim.get("surface"), limit=80)
    evidence = safe_text(claim.get("evidence_label"), limit=160)

    if lane in LANE_OWNERS:
        return LANE_OWNERS[lane], f"lane:{lane}"
    if surface:
        return f"limen:{owner_slug(surface)}", f"surface:{surface}"
    if evidence.startswith("docs/") or evidence.startswith(".limen-private/"):
        return "limen:evidence-ledger", "evidence-path"
    return "", "no-owner-signal"


def classify_owner_claim(claim: dict[str, Any]) -> dict[str, Any]:
    authority = safe_text(claim.get("authority"), limit=80)
    source_status = safe_text(claim.get("source_status"), limit=80)
    owner, owner_reason = derive_owner(claim)

    if authority in PARKED_AUTHORITIES:
        owner_status = "parked"
        action_level = "parked"
    elif not owner:
        owner_status = "unowned_ore"
        action_level = "not_dispatchable"
    elif authority == "current_doctrine" and source_status == "current":
        owner_status = "owned_current"
        action_level = "packet_candidate"
    elif authority in LINEAGE_AUTHORITIES:
        owner_status = "owned_lineage"
        action_level = "review_only"
    else:
        owner_status = "owned_lineage" if owner else "unowned_ore"
        action_level = "review_only" if owner else "not_dispatchable"

    return {
        "id": safe_text(claim.get("id"), limit=180),
        "owner": owner,
        "owner_reason": owner_reason,
        "owner_status": owner_status,
        "action_level": action_level,
        "authority": authority,
        "trust": safe_text(claim.get("trust"), limit=80),
        "freshness": safe_text(claim.get("freshness"), limit=80),
        "source_status": source_status,
        "surface": safe_text(claim.get("surface"), limit=100),
        "lane": safe_text(claim.get("lane"), limit=100),
        "subject": safe_text(claim.get("subject"), limit=120),
        "summary": safe_text(claim.get("summary"), limit=180),
        "next_action": safe_text(claim.get("next_action"), limit=180),
        "evidence_label": safe_text(claim.get("evidence_label"), limit=180),
        "privacy_class": "public_redacted",
        "dispatchable": action_level == "packet_candidate",
    }


def build_certainty(
    *,
    digest_path: Path = DIGEST_PATH,
    root: Path = ROOT,
    private_root: Path = PRIVATE_ROOT,
) -> dict[str, Any]:
    digest = load_json(digest_path)
    claims = [classify_owner_claim(claim) for claim in digest.get("claims", [])]
    owner_counts = Counter(item["owner_status"] for item in claims)
    action_counts = Counter(item["action_level"] for item in claims)
    owner_top = Counter(item["owner"] for item in claims if item.get("owner"))
    unowned_dispatchable = [item for item in claims if item["dispatchable"] and item["owner_status"] == "unowned_ore"]
    return {
        "generated_at": now_iso(),
        "decision": "owner certainty gates action; unowned ore is not dispatchable",
        "privacy": {
            "raw_bodies_read": False,
            "tracked_output": "docs/vltima-owner-certainty.md",
            "private_index": str(private_root / "lifecycle" / "vltima-owner-certainty.json"),
            "source_digest": str(digest_path),
        },
        "coverage": {
            "digest_generated_at": digest.get("generated_at"),
            "claim_count": len(claims),
            "owner_status_counts": dict(sorted(owner_counts.items())),
            "action_level_counts": dict(sorted(action_counts.items())),
            "top_owners": dict(owner_top.most_common(20)),
            "unowned_dispatchable_count": len(unowned_dispatchable),
        },
        "claims": claims,
        "unowned_dispatchable": unowned_dispatchable,
    }


def render_markdown(certainty: dict[str, Any]) -> str:
    coverage = certainty["coverage"]
    status_bits = ", ".join(f"`{key}` {value}" for key, value in coverage["owner_status_counts"].items())
    action_bits = ", ".join(f"`{key}` {value}" for key, value in coverage["action_level_counts"].items())
    lines = [
        "# VLTIMA Owner Certainty",
        "",
        f"Generated: `{certainty['generated_at']}`",
        "",
        "## Canonical Decision",
        "",
        "- Every result claim must have an owner before it can become action.",
        "- Missing ownership produces `unowned_ore`, not dispatchable work.",
        "- Superseded and quarantined claims are parked until fresh evidence or a human-safe packet owns them.",
        "- This surface reads sanitized result claims only; it does not read raw private bodies or mutate `tasks.yaml`.",
        "",
        "## Coverage",
        "",
        f"- Source digest generated: `{coverage.get('digest_generated_at')}`.",
        f"- Claims classified: `{coverage['claim_count']}`.",
        f"- Owner status mix: {status_bits or 'none'}.",
        f"- Action level mix: {action_bits or 'none'}.",
        f"- Unowned dispatchable claims: `{coverage['unowned_dispatchable_count']}`.",
        "",
        "## Packet Candidates",
        "",
    ]
    candidates = [claim for claim in certainty["claims"] if claim["action_level"] == "packet_candidate"][:40]
    if not candidates:
        lines.append("- None recorded.")
    else:
        lines.extend(["| Owner | Surface | Subject | Trust | Next |", "|---|---|---|---|---|"])
        for claim in candidates:
            lines.append(
                f"| `{claim['owner']}` | `{claim['surface']}` | `{claim['subject']}` | "
                f"`{claim['trust']}` | {claim['next_action'] or claim['summary']} |"
            )
    lines.extend(["", "## Parked Or Review-Only", ""])
    parked = [claim for claim in certainty["claims"] if claim["action_level"] != "packet_candidate"][:40]
    if not parked:
        lines.append("- None recorded.")
    else:
        lines.extend(["| Status | Owner | Surface | Subject | Reason |", "|---|---|---|---|---|"])
        for claim in parked:
            lines.append(
                f"| `{claim['owner_status']}` | `{claim['owner'] or 'unowned'}` | `{claim['surface']}` | "
                f"`{claim['subject']}` | {claim['authority']} / {claim['owner_reason']} |"
            )
    lines.extend(
        [
            "",
            "## Contract",
            "",
            "- `packet_candidate` means candidate packetization only; it does not enqueue or dispatch.",
            "- Any future enqueue step must preserve owner, verification command, receipt target, and privacy class.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(
    certainty: dict[str, Any],
    markdown: str,
    *,
    doc_path: Path = DOC_PATH,
    private_index: Path = PRIVATE_INDEX,
) -> None:
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    private_index.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(markdown, encoding="utf-8")
    private_index.write_text(json.dumps(certainty, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Derive VLTIMA owner certainty from result claims.")
    parser.add_argument("--digest", type=Path, default=DIGEST_PATH, help="path to vltima-result-digest.json")
    parser.add_argument("--write", action="store_true", help="write tracked summary and private index")
    parser.add_argument("--json", action="store_true", help="print owner-certainty JSON")
    args = parser.parse_args()
    try:
        certainty = build_certainty(digest_path=args.digest)
    except FileNotFoundError:
        print(f"missing result digest: {args.digest}; refresh with python3 scripts/vltima-result-digest.py --write", file=sys.stderr)
        return 2
    markdown = render_markdown(certainty)
    if args.write:
        write_outputs(certainty, markdown)
        print(f"vltima-owner-certainty: wrote {DOC_PATH} and {PRIVATE_INDEX}")
    elif args.json:
        print(json.dumps(certainty, indent=2, sort_keys=True))
    else:
        print(markdown, end="")
        print("vltima-owner-certainty: dry-run")
    return 0 if certainty["coverage"]["unowned_dispatchable_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
