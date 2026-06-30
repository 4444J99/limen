#!/usr/bin/env python3
"""Emit redacted owner packets for a current-session fanout planner beat.

The source session is private. This script reads the full JSONL session, derives
hash-only evidence across every turn, and emits public-safe owner packets with
executor criteria and verification predicates.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
DOC_DIR = ROOT / "docs" / "current-session-fanout"
PRIVATE_DIR = PRIVATE_ROOT / "lifecycle" / "current-session-fanout"

RAW_PROMPT_SENTINELS = (
    "RAW_PRIVATE",
    "SECRET_PROMPT_TEXT",
    "PRIVATE_PROMPT_BODY",
    "RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR",
)

THEME_KEYWORDS = {
    "quota_reset_guard": (
        "quota",
        "reset",
        "reserve",
        "usage",
        "rate-limit",
        "rate_limit",
        "429",
        "runway",
        "headroom",
        "effective_reserve",
        "per_agent_reset",
    ),
    "fanout_capacity": (
        "fanout",
        "capacity",
        "dispatch",
        "route",
        "lane",
        "ollama",
        "local floor",
        "paid lane",
    ),
    "blocked_local_work": (
        "blocked",
        "needs_human",
        "permission",
        "tcc",
        "auth",
        "credential",
        "warp_api_key",
        "cloudflare",
        "gh_token",
        "missing",
    ),
    "global_product_selection": (
        "product selection",
        "product",
        "discover-value",
        "value discovery",
        "revenue",
        "global",
        "score-dispatch",
    ),
}

KNOWN_SCOPE_FILES = (
    "scripts/usage-telemetry.py",
    "cli/src/limen/capacity.py",
    "cli/src/limen/dispatch.py",
    "scripts/route.py",
    "scripts/dispatch-health.py",
    "scripts/conductor-tranche.py",
    "scripts/current-session-fanout.py",
    "scripts/current-session-fanout-plan.py",
    "scripts/discover-value.py",
    "scripts/score-dispatch.py",
    "docs/NEEDS-HUMAN-DIGEST.md",
)

FILE_RE = re.compile(
    r"(?:(?:/Users/[^\s'\"`]+/Workspace/limen/)|(?:\./))?"
    r"((?:cli|scripts|docs|mcp|web|container|spec)/[A-Za-z0-9_./@+-]+|"
    r"tasks\.yaml|AGENTS\.md)"
)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def stable_hash(text: str, length: int = 24) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:length]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "packet"


def relpath(path: Path) -> str:
    try:
        return "~/" + str(path.expanduser().resolve().relative_to(HOME))
    except (OSError, ValueError):
        return str(path)


def split_hash_args(values: list[str] | None) -> list[str]:
    out: list[str] = []
    for value in values or []:
        for part in str(value).split(","):
            part = part.strip()
            if part:
                out.append(part)
    return out


def text_from_content(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(text_from_content(item))
        return out
    if isinstance(value, dict):
        out: list[str] = []
        for key in ("text", "content", "message", "input"):
            if key in value:
                out.extend(text_from_content(value[key]))
        return out
    return []


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict):
                records.append(obj)
    return records


def item_texts(item: dict[str, Any]) -> list[str]:
    if item.get("type") == "message":
        return text_from_content(item.get("content"))
    if item.get("type") in {"function_call", "custom_tool_call"}:
        return text_from_content(item.get("arguments")) + text_from_content(item.get("input"))
    if item.get("type") in {"function_call_output", "custom_tool_call_output"}:
        return text_from_content(item.get("output"))
    return []


def public_file_refs(text: str) -> list[str]:
    refs: set[str] = set()
    for match in FILE_RE.findall(text):
        cleaned = match.lstrip("./")
        if "/.limen-private/" in cleaned:
            continue
        if cleaned not in KNOWN_SCOPE_FILES and cleaned not in {"tasks.yaml", "AGENTS.md"}:
            if not Path(cleaned).suffix:
                continue
        refs.add(cleaned)
    for known in KNOWN_SCOPE_FILES:
        if known in text:
            refs.add(known)
    return sorted(refs)


def keyword_hits(text: str) -> Counter[str]:
    lower = text.lower()
    hits: Counter[str] = Counter()
    for family, words in THEME_KEYWORDS.items():
        for word in words:
            if word in lower:
                hits[family] += lower.count(word)
    return hits


def new_turn(turn_id: str, timestamp: str | None = None, cwd: str | None = None) -> dict[str, Any]:
    return {
        "turn_id": turn_id,
        "first_timestamp": timestamp,
        "last_timestamp": timestamp,
        "cwd_hash": stable_hash(cwd, 20) if cwd else None,
        "counts": Counter(),
        "keywords": Counter(),
        "tools": Counter(),
        "files": Counter(),
        "prompt_hashes": [],
        "plan_hashes": [],
    }


def current_item(payload: dict[str, Any]) -> dict[str, Any]:
    item = payload.get("item")
    if isinstance(item, dict):
        return item
    return payload


def summarize_session(records: list[dict[str, Any]], session: Path) -> dict[str, Any]:
    turns: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    prompt_hashes: list[str] = []
    plan_hashes: list[str] = []
    tools: Counter[str] = Counter()
    files: Counter[str] = Counter()
    keywords: Counter[str] = Counter()
    counts: Counter[str] = Counter()
    raw_bytes = 0

    for idx, obj in enumerate(records):
        typ = str(obj.get("type") or "unknown")
        payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
        timestamp = str(obj.get("timestamp") or "")
        if typ == "turn_context":
            turn_id = str(payload.get("turn_id") or f"turn-{len(turns) + 1}")
            current = new_turn(turn_id, timestamp, str(payload.get("cwd") or ""))
            turns.append(current)
        if current is None:
            current = new_turn("prelude", timestamp)
            turns.append(current)

        current["last_timestamp"] = timestamp or current["last_timestamp"]
        current["counts"][typ] += 1
        counts[typ] += 1

        texts: list[str] = []
        if typ == "response_item":
            item = current_item(payload)
            item_type = str(item.get("type") or "unknown")
            if item_type in {"function_call", "custom_tool_call"}:
                tool = str(item.get("name") or "unknown")
                tools[tool] += 1
                current["tools"][tool] += 1
            if item_type == "message" and item.get("role") == "user":
                for text in text_from_content(item.get("content")):
                    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
                    prompt_hashes.append(digest[:24])
                    current["prompt_hashes"].append(digest[:24])
                    raw_bytes += len(text.encode("utf-8", errors="replace"))
                    texts.append(text)
            else:
                texts.extend(item_texts(item))
        elif typ == "event_msg":
            msg = str(payload.get("message") or "")
            texts.append(msg)
            if "plan" in msg.lower():
                digest = stable_hash(msg, 12)
                plan_hashes.append(digest)
                current["plan_hashes"].append(digest)
        elif typ == "compacted":
            texts.extend(text_from_content(payload.get("summary")))

        for text in texts:
            hits = keyword_hits(text)
            keywords.update(hits)
            current["keywords"].update(hits)
            for ref in public_file_refs(text):
                files[ref] += 1
                current["files"][ref] += 1

    public_turns = []
    for turn in turns:
        public_turns.append(
            {
                "turn_id": turn["turn_id"],
                "first_timestamp": turn["first_timestamp"],
                "last_timestamp": turn["last_timestamp"],
                "cwd_hash": turn["cwd_hash"],
                "counts": dict(turn["counts"].most_common()),
                "keywords": dict(turn["keywords"].most_common()),
                "tools": dict(turn["tools"].most_common()),
                "files": dict(turn["files"].most_common()),
                "prompt_hash_count": len(turn["prompt_hashes"]),
                "prompt_hashes": list(dict.fromkeys(turn["prompt_hashes"]))[:12],
                "plan_hashes": list(dict.fromkeys(turn["plan_hashes"]))[:12],
            }
        )

    return {
        "session_basename": session.name,
        "session_display_path": relpath(session),
        "session_sha256": sha256_file(session),
        "records": len(records),
        "turn_contexts": sum(1 for record in records if record.get("type") == "turn_context"),
        "turns_scanned": len(turns),
        "full_session_derived": len(turns) > 1,
        "event_counts": dict(counts.most_common()),
        "tool_counts": dict(tools.most_common()),
        "keyword_counts": dict(keywords.most_common()),
        "file_refs": dict(files.most_common()),
        "prompt_hashes": list(dict.fromkeys(prompt_hashes)),
        "prompt_events": len(prompt_hashes),
        "prompt_bytes": raw_bytes,
        "derived_plan_hashes": list(dict.fromkeys(plan_hashes)),
        "turns": public_turns,
    }


def evidence_turns(session_summary: dict[str, Any], family: str) -> list[str]:
    turns = []
    for turn in session_summary.get("turns") or []:
        if (turn.get("keywords") or {}).get(family):
            turns.append(str(turn.get("turn_id")))
    return list(dict.fromkeys(turns))


def scope_files(session_summary: dict[str, Any], wanted: tuple[str, ...]) -> list[str]:
    refs = session_summary.get("file_refs") or {}
    scoped = [path for path in wanted if path in refs]
    for path in wanted:
        if path in KNOWN_SCOPE_FILES and path not in scoped:
            scoped.append(path)
    return scoped


def owner_packets(
    packet_id: str,
    theme: str,
    session_summary: dict[str, Any],
    source_plan_hashes: list[str],
    source_prompt_hashes: list[str],
) -> list[dict[str, Any]]:
    provided_or_derived_plans = source_plan_hashes or session_summary["derived_plan_hashes"][:10]
    provided_or_derived_prompts = source_prompt_hashes or session_summary["prompt_hashes"][:24]
    source = {
        "session_sha256": session_summary["session_sha256"],
        "plan_hashes": provided_or_derived_plans,
        "prompt_hashes": provided_or_derived_prompts,
        "turns_scanned": session_summary["turns_scanned"],
        "records_scanned": session_summary["records"],
    }

    quota_files = scope_files(
        session_summary,
        (
            "scripts/usage-telemetry.py",
            "cli/src/limen/capacity.py",
            "cli/src/limen/dispatch.py",
            "scripts/route.py",
            "scripts/dispatch-health.py",
            "scripts/current-session-fanout-plan.py",
        ),
    )
    packets = [
        {
            "id": f"{packet_id}-quota-reset-guard",
            "theme": theme,
            "owner": "limen usage and dispatch",
            "repo": "organvm/limen",
            "target_agent": "codex",
            "status": "ready-for-executor",
            "dispatch_gate": "execute only inside a Limen checkout; no paid reset, top-up, or outward dispatch",
            "scope_files": quota_files,
            "source": source,
            "evidence_turns": evidence_turns(session_summary, "quota_reset_guard"),
            "executor_criteria": [
                "Use the full source session evidence, not the latest turn only; quota/reset mentions must be traceable across recorded turn ids.",
                "Derive reset runway from live usage and board reset fields such as per_agent_reset and vendor windows; do not pin reset times or model names.",
                "Mark a paid lane hard-down only from real recent rate-limit or exhausted count evidence; local transcript spend is a pacing signal, not proof that the vendor is unavailable.",
                "Emit reset-aware reserve fields that can be audited, including time_left_frac, effective_reserve_pct, will_expire, required_rate_per_h, and health.",
                "Fanout must cascade to the next healthy lane or local floor when one lane is low, blocked, or rate-limited.",
                "Keep raw prompt and plan bodies out of tracked docs, task logs, commits, and outbound systems; use hashes for provenance.",
            ],
            "verification_predicates": [
                "python3 scripts/current-session-fanout-plan.py --session <source-session> --packet-id <packet-id> --theme quota-reset-guard --write",
                "PYTHONPATH=cli/src python3 -m pytest cli/tests/test_current_session_fanout_plan.py -q",
                "PYTHONPATH=cli/src python3 -m pytest cli/tests/test_usage_telemetry.py cli/tests/test_usage_gate.py -q",
                "python3 -m py_compile scripts/current-session-fanout-plan.py",
            ],
        },
        {
            "id": f"{packet_id}-blocked-local-work",
            "theme": "blocked-local-work",
            "owner": "local substrate and his-hand registry",
            "repo": "organvm/limen",
            "target_agent": "codex",
            "status": "blocked-local-recorded",
            "dispatch_gate": "record local blocker once, then keep unrelated global product-selection packets eligible",
            "scope_files": scope_files(
                session_summary,
                (
                    "docs/NEEDS-HUMAN-DIGEST.md",
                    "scripts/usage-telemetry.py",
                    "scripts/dispatch-health.py",
                    "scripts/conductor-tranche.py",
                ),
            ),
            "source": source,
            "evidence_turns": evidence_turns(session_summary, "blocked_local_work"),
            "global_stop": False,
            "executor_criteria": [
                "Classify local blockers as local facts, not global product-selection blockers.",
                "If a credential, macOS permission, missing mounted volume, or unavailable local state is required, record the cheapest durable owner path in the owning registry.",
                "Do not re-prompt for the same human action in each packet; cite the registry entry and continue other lanes.",
                "Do not include credentials, personal data, or raw prompt text in the blocker record.",
            ],
            "verification_predicates": [
                "test -f docs/NEEDS-HUMAN-DIGEST.md",
                "python3 scripts/usage-telemetry.py",
                "python3 scripts/dispatch-health.py --help >/dev/null",
            ],
        },
        {
            "id": f"{packet_id}-global-product-selection",
            "theme": "global-product-selection",
            "owner": "value discovery and product selection",
            "repo": "organvm/limen",
            "target_agent": "codex",
            "status": "ready-for-executor",
            "dispatch_gate": "not blocked by local machine or credential residue unless the selected product itself needs that gate",
            "scope_files": scope_files(
                session_summary,
                (
                    "scripts/discover-value.py",
                    "scripts/score-dispatch.py",
                    "value-repos.json",
                    "positioning-seeds.json",
                    "tasks.yaml",
                ),
            ),
            "source": source,
            "evidence_turns": evidence_turns(session_summary, "global_product_selection"),
            "depends_on_blocked_local_work": False,
            "executor_criteria": [
                "Keep global product selection moving from unblocked repos and tasks even when a local substrate packet records blocked work.",
                "Select product work from measured value signals, discovery gaps, revenue labels, and dispatch-return scoring, not from a static allowlist.",
                "Use dry-run/read-only selection unless explicitly asked to append or dispatch tasks.",
                "A blocked product can be recorded without making the whole product ledger blocked.",
            ],
            "verification_predicates": [
                "LIMEN_DISCOVER_REPOS=organvm/limen python3 scripts/discover-value.py --tasks tasks.yaml --floor 1 --max-new 1",
                "python3 scripts/score-dispatch.py --print --limit 1",
            ],
        },
    ]
    return packets


def coverage_from_packets(session_summary: dict[str, Any], packets: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "records_scanned": session_summary["records"],
        "turn_contexts": session_summary["turn_contexts"],
        "turns_scanned": session_summary["turns_scanned"],
        "full_session_derived": session_summary["full_session_derived"],
        "prompt_events": session_summary["prompt_events"],
        "unique_prompt_hashes": len(session_summary["prompt_hashes"]),
        "owner_packets": len(packets),
        "packets_with_executor_criteria": sum(1 for packet in packets if packet.get("executor_criteria")),
        "packets_with_verification_predicates": sum(1 for packet in packets if packet.get("verification_predicates")),
        "blocked_local_packets": sum(1 for packet in packets if packet.get("status") == "blocked-local-recorded"),
        "global_product_selection_unblocked": any(
            packet.get("theme") == "global-product-selection"
            and packet.get("depends_on_blocked_local_work") is False
            for packet in packets
        ),
    }


def build_snapshot(
    session_path: Path,
    packet_id: str,
    theme: str,
    *,
    source_plan_hashes: list[str] | None = None,
    source_prompt_hashes: list[str] | None = None,
) -> dict[str, Any]:
    records = read_jsonl(session_path)
    session_summary = summarize_session(records, session_path)
    packets = owner_packets(
        packet_id,
        theme,
        session_summary,
        source_plan_hashes or [],
        source_prompt_hashes or [],
    )
    return {
        "generated_at": now_iso(),
        "packet_id": packet_id,
        "theme": theme,
        "source_session": {
            "basename": session_summary["session_basename"],
            "display_path": session_summary["session_display_path"],
            "sha256": session_summary["session_sha256"],
        },
        "coverage": coverage_from_packets(session_summary, packets),
        "session_evidence": session_summary,
        "owner_packets": packets,
    }


def render_counts(data: dict[str, Any], *, limit: int = 8) -> str:
    if not data:
        return "none"
    items = list(data.items())[:limit]
    return ", ".join(f"`{key}` {value}" for key, value in items)


def render_list(items: list[str]) -> str:
    return ", ".join(f"`{item}`" for item in items) if items else "none"


def render_markdown(snapshot: dict[str, Any]) -> str:
    coverage = snapshot["coverage"]
    evidence = snapshot["session_evidence"]
    source = snapshot["source_session"]
    packet_source = (snapshot["owner_packets"][0].get("source") if snapshot["owner_packets"] else {}) or {}
    lines = [
        f"# Current Session Fanout Plan: {snapshot['packet_id']}",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        f"Theme: `{snapshot['theme']}`",
        f"Source session: `{source['basename']}`",
        f"Source session SHA-256: `{source['sha256']}`",
        "",
        "## Privacy Contract",
        "",
        "- This receipt is derived from the full session JSONL and contains no raw prompt or plan bodies.",
        "- Provenance is expressed with session, prompt, and plan hashes.",
        "- Blocked local work is recorded as local state and does not stop global product selection.",
        "",
        "## Coverage",
        "",
        f"- Records scanned: `{coverage['records_scanned']}`.",
        f"- Turn contexts: `{coverage['turn_contexts']}`.",
        f"- Turns scanned: `{coverage['turns_scanned']}`.",
        f"- Full-session derived: `{coverage['full_session_derived']}`.",
        f"- Prompt events hashed: `{coverage['prompt_events']}`.",
        f"- Unique prompt hashes: `{coverage['unique_prompt_hashes']}`.",
        f"- Owner packets emitted: `{coverage['owner_packets']}`.",
        f"- Packets with executor criteria: `{coverage['packets_with_executor_criteria']}`.",
        f"- Packets with verification predicates: `{coverage['packets_with_verification_predicates']}`.",
        f"- Global product selection unblocked: `{coverage['global_product_selection_unblocked']}`.",
        "",
        "## Session Signals",
        "",
        f"- Event counts: {render_counts(evidence.get('event_counts') or {})}.",
        f"- Tool counts: {render_counts(evidence.get('tool_counts') or {})}.",
        f"- Keyword families: {render_counts(evidence.get('keyword_counts') or {})}.",
        f"- File refs: {render_counts(evidence.get('file_refs') or {}, limit=12)}.",
        f"- Prompt hashes: {render_list(evidence.get('prompt_hashes', [])[:24])}.",
        f"- Plan hashes: {render_list(evidence.get('derived_plan_hashes', [])[:24])}.",
        "",
        "## Source Provenance",
        "",
        f"- Source plan hashes: {render_list((packet_source.get('plan_hashes') or [])[:24])}.",
        f"- Source prompt hashes: {render_list((packet_source.get('prompt_hashes') or [])[:24])}.",
        "",
        "## Owner Packets",
        "",
        "| Packet | Status | Owner | Gate | Evidence Turns | Predicates |",
        "|---|---|---|---|---|---:|",
    ]
    for packet in snapshot["owner_packets"]:
        lines.append(
            f"| `{packet['id']}` | `{packet['status']}` | {packet['owner']} | "
            f"{packet['dispatch_gate']} | {render_list(packet.get('evidence_turns') or [])} | "
            f"{len(packet.get('verification_predicates') or [])} |"
        )
    for packet in snapshot["owner_packets"]:
        lines.extend(
            [
                "",
                f"### {packet['id']}",
                "",
                f"- Repo: `{packet['repo']}`.",
                f"- Target agent: `{packet['target_agent']}`.",
                f"- Scope files: {render_list(packet.get('scope_files') or [])}.",
                "",
                "Executor criteria:",
            ]
        )
        for criterion in packet.get("executor_criteria") or []:
            lines.append(f"- {criterion}")
        lines.extend(["", "Verification predicates:"])
        for predicate in packet.get("verification_predicates") or []:
            lines.append(f"- `{predicate}`")
    lines.append("")
    rendered = "\n".join(lines)
    for sentinel in RAW_PROMPT_SENTINELS:
        if sentinel in rendered:
            raise ValueError(f"raw prompt sentinel leaked into markdown: {sentinel}")
    return rendered


def write_outputs(snapshot: dict[str, Any], markdown: str) -> tuple[Path, Path]:
    packet_slug = slugify(str(snapshot["packet_id"]))
    doc_path = DOC_DIR / f"{packet_slug}.md"
    private_path = PRIVATE_DIR / f"{packet_slug}.json"
    DOC_DIR.mkdir(parents=True, exist_ok=True)
    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(markdown, encoding="utf-8")
    private_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    return doc_path, private_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a redacted current-session fanout plan.")
    parser.add_argument("--session", required=True, help="source Codex session JSONL")
    parser.add_argument("--packet-id", required=True, help="planner packet id")
    parser.add_argument("--theme", required=True, help="planner packet theme")
    parser.add_argument("--source-plan-hash", action="append", default=[], help="known source plan hash; comma-separated accepted")
    parser.add_argument("--source-prompt-hash", action="append", default=[], help="known source prompt hash; comma-separated accepted")
    parser.add_argument("--write", action="store_true", help="write tracked markdown and ignored private JSON")
    args = parser.parse_args()

    session_path = Path(args.session).expanduser()
    snapshot = build_snapshot(
        session_path,
        args.packet_id,
        args.theme,
        source_plan_hashes=split_hash_args(args.source_plan_hash),
        source_prompt_hashes=split_hash_args(args.source_prompt_hash),
    )
    markdown = render_markdown(snapshot)
    if args.write:
        doc_path, private_path = write_outputs(snapshot, markdown)
        print(f"current-session-fanout-plan: wrote {doc_path} and {private_path}")
    else:
        print(markdown)
    print(
        "current-session-fanout-plan: "
        f"{snapshot['coverage']['owner_packets']} packets, "
        f"{snapshot['coverage']['turns_scanned']} turns, "
        f"{snapshot['coverage']['prompt_events']} prompt events"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
