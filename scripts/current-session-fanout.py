#!/usr/bin/env python3
"""Build redacted planner and executor packets from a Codex session JSONL.

The public receipt contains titles, hashes, line numbers, criteria, predicates,
and blocker summaries. Raw prompt and plan bodies stay in the ignored private
JSON snapshot only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "current-session-fanout.json"
DOC_PATH = ROOT / "docs" / "current-session-fanout.md"

sys.path.insert(0, str(ROOT / "cli" / "src"))

try:
    from limen.capacity import PAID_AGENT_ORDER, capacity_census, canonical_agent
except Exception:  # pragma: no cover - hermetic fallback
    PAID_AGENT_ORDER = ("codex",)

    def capacity_census(board: object = None) -> list[dict[str, Any]]:
        return [
            {
                "agent": "codex",
                "kind": "local-cli",
                "reachable": True,
                "detail": "fallback",
                "remaining": None,
                "limit": None,
                "spent": 0,
            }
        ]

    def canonical_agent(agent: str | None) -> str:
        return str(agent or "")

THEMES: list[tuple[str, tuple[str, ...]]] = [
    ("alpha-omega-product-ledger", ("1000", "alpha", "omega", "product", "shipped")),
    ("full-fleet-overnight", ("fleet", "overnight", "all night", "lane", "jules")),
    ("dynamic-substrate", ("drive", "mounted", "hard-coded", "archive", "substrate")),
    ("repo-salvage-consolidation", ("400 repos", "repo", "consolidated", "same app", "salvage")),
    ("money-inbound-seo", ("money", "cash", "seo", "organic", "lead", "sell")),
    ("contrib-mirror", ("contrib", "external", "community", "github contrib", "mirror")),
    ("quota-reset-guard", ("reset", "weekly limit", "free reset", "credits", "usage")),
    ("current-session-intake", ("this session", "beginning of this session", "hold everything")),
    ("domus-preflight-noise", ("domus", "homebrew", "preflight", "atuin", "cursor position")),
    ("private-sauce-boundary", ("private", "secret", "sauce", "hide")),
    ("codex-planner-worktrees", ("10 worktrees", "codex only", "planner", "worktree")),
    ("autopoietic-conductor", ("autopoetic", "autopoietic", "forever", "tokens")),
]

PROPOSED_PLAN_RE = re.compile(r"<proposed_plan>\s*(.*?)(?:\s*</proposed_plan>|$)", re.I | re.S)
MARKDOWN_H1_RE = re.compile(r"(?m)^#\s+(.+?)\s*$")
PRIOR_PLAN_MARKERS = (
    "a previous agent produced the plan below",
    "previous agent produced the plan below",
)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def stable_hash(text: str, length: int = 18) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:length]


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


def role_texts_from_obj(obj: dict[str, Any]) -> list[tuple[str, str]]:
    payload = obj.get("payload")
    if isinstance(payload, dict):
        if payload.get("type") == "message" and payload.get("role") in {"user", "assistant"}:
            return [
                (str(payload["role"]), text)
                for text in text_from_content(payload.get("content"))
            ]
        if payload.get("type") == "user_message":
            return [("user", text) for text in text_from_content(payload.get("message"))]
        if payload.get("type") == "agent_message":
            return [("assistant", text) for text in text_from_content(payload.get("message"))]
    if obj.get("role") in {"user", "assistant"}:
        return [
            (str(obj["role"]), text)
            for text in text_from_content(obj.get("content") or obj.get("text"))
        ]
    return []


def user_texts_from_obj(obj: dict[str, Any]) -> list[str]:
    return [text for role, text in role_texts_from_obj(obj) if role == "user"]


def read_jsonl(path: Path) -> list[tuple[int, dict[str, Any]]]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    records: list[tuple[int, dict[str, Any]]] = []
    for idx, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            records.append((idx, obj))
    return records


def read_session_messages(path: Path) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for line, obj in read_jsonl(path):
        timestamp = obj.get("timestamp")
        for text in user_texts_from_obj(obj):
            messages.append(
                {
                    "line": line,
                    "timestamp": timestamp,
                    "hash": stable_hash(text, 24),
                    "bytes": len(text.encode("utf-8", errors="replace")),
                    "text": text,
                }
            )
    return messages


def plan_title(text: str) -> str:
    match = MARKDOWN_H1_RE.search(text)
    return match.group(1).strip() if match else "Untitled Plan"


def user_prior_plan_block(text: str) -> str | None:
    lower_text = text.lower()
    marker_index = min(
        (idx for marker in PRIOR_PLAN_MARKERS if (idx := lower_text.find(marker)) != -1),
        default=-1,
    )
    if marker_index == -1:
        return None
    match = MARKDOWN_H1_RE.search(text, marker_index)
    return text[match.start() :] if match else None


def plan_event(
    *,
    line: int,
    timestamp: str | None,
    role: str,
    source_type: str,
    text: str,
    ordinal: int,
) -> dict[str, Any]:
    plan_hash = stable_hash(text, 12)
    return {
        "id": f"PLAN-SRC-{line}-{ordinal}-{plan_hash}",
        "title": plan_title(text),
        "timestamp": timestamp,
        "line": line,
        "role": role,
        "source_type": source_type,
        "hash": plan_hash,
        "bytes": len(text.encode("utf-8", errors="replace")),
        "duplicate": False,
        "duplicate_of": None,
        "included": False,
        "text": text,
    }


def read_session_plan_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    seen_messages: set[tuple[str, str, str | None]] = set()
    for line, obj in read_jsonl(path):
        timestamp = obj.get("timestamp")
        for role, text in role_texts_from_obj(obj):
            if not text.strip():
                continue
            message_key = (role, text, str(timestamp) if timestamp is not None else None)
            if message_key in seen_messages:
                continue
            seen_messages.add(message_key)
            ordinal = 1
            if role == "user":
                block = user_prior_plan_block(text)
                if block:
                    events.append(
                        plan_event(
                            line=line,
                            timestamp=timestamp,
                            role=role,
                            source_type="user_supplied_prior_plan",
                            text=block,
                            ordinal=ordinal,
                        )
                    )
                    ordinal += 1
            if role == "assistant":
                for match in PROPOSED_PLAN_RE.finditer(text):
                    block = match.group(1)
                    if not MARKDOWN_H1_RE.search(block):
                        continue
                    events.append(
                        plan_event(
                            line=line,
                            timestamp=timestamp,
                            role=role,
                            source_type="assistant_proposed_plan",
                            text=block,
                            ordinal=ordinal,
                        )
                    )
                    ordinal += 1
    return mark_plan_duplicates(events)


def mark_plan_duplicates(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    newest_first = sorted(events, key=lambda event: (int(event["line"]), str(event["timestamp"] or "")), reverse=True)
    seen: dict[str, str] = {}
    for event in newest_first:
        plan_hash = str(event["hash"])
        if plan_hash in seen:
            event["duplicate"] = True
            event["duplicate_of"] = seen[plan_hash]
        else:
            seen[plan_hash] = str(event["id"])
    return newest_first


def unique_plan_sources(plan_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event for event in plan_events if not event["duplicate"]]


def latest_codex_session() -> Path | None:
    explicit = os.environ.get("LIMEN_CURRENT_SESSION_JSONL")
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.exists() else None
    root = HOME / ".codex" / "sessions"
    if not root.exists():
        return None
    try:
        files = [path for path in root.rglob("*.jsonl") if path.is_file()]
    except OSError:
        return None
    return max(files, key=lambda path: path.stat().st_mtime) if files else None


def find_session(path_arg: str | None) -> Path:
    path = Path(path_arg).expanduser() if path_arg else latest_codex_session()
    if path is None or not path.exists():
        raise FileNotFoundError("no Codex session JSONL found; set LIMEN_CURRENT_SESSION_JSONL or pass --session")
    return path


def matched_themes(messages: list[dict[str, Any]], plan_events: list[dict[str, Any]]) -> list[str]:
    body = "\n".join(
        [str(msg["text"]).lower() for msg in messages]
        + [str(event.get("text") or "").lower() for event in plan_events]
    )
    found = [name for name, needles in THEMES if any(needle in body for needle in needles)]
    return found or ["current-session-intake"]


def lane_rows() -> list[dict[str, Any]]:
    try:
        rows = list(capacity_census(None))
    except Exception:
        rows = []
    normalized: list[dict[str, Any]] = []
    for row in rows:
        remaining = row.get("remaining")
        detail = str(row.get("detail") or "")
        if row.get("reachable"):
            status = "active"
        elif remaining == 0:
            status = "depleted"
        elif any(needle in detail.lower() for needle in ("not set", "auth", "assignable", "no model pulled")):
            status = "human-gated"
        else:
            status = "down"
        normalized.append(
            {
                "agent": str(row.get("agent") or ""),
                "kind": str(row.get("kind") or ""),
                "status": status,
                "reachable": bool(row.get("reachable")),
                "remaining": remaining,
                "detail": detail,
            }
        )
    if not normalized:
        normalized.append(
            {
                "agent": "codex",
                "kind": "local-cli",
                "status": "active",
                "reachable": True,
                "remaining": None,
                "detail": "fallback",
            }
        )
    return normalized


def lane_selection(selector: str, rows: list[dict[str, Any]]) -> list[str]:
    value = (selector or "auto").strip()
    by_agent = {row["agent"]: row for row in rows}
    if value == "all":
        return [str(agent) for agent in PAID_AGENT_ORDER]
    if value == "auto":
        active = [str(agent) for agent in PAID_AGENT_ORDER if by_agent.get(str(agent), {}).get("status") == "active"]
        return active or ["codex"]
    selected: list[str] = []
    for raw in value.split(","):
        agent = canonical_agent(raw.strip())
        if agent and agent in PAID_AGENT_ORDER and agent not in selected:
            selected.append(agent)
    return selected or ["codex"]


def packet_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-") or "packet"


def owner_packet_for_theme(theme: str) -> dict[str, Any]:
    if theme == "full-fleet-overnight":
        return {
            "owner_repo": "organvm/limen",
            "owner_ledger": "docs/current-session-fanout.md",
            "criteria": [
                "derive lane inventory from PAID_AGENT_ORDER, not hand-written local lists",
                "`auto` selects active reachable lanes while down/depleted/human-gated lanes stay visible in receipts",
                "`all` preserves every registered lane for audit without pretending down lanes are runnable",
                "async dry-runs do not launch live dispatch or spend resets/credits",
                "blocked local gates are recorded as local blockers while global product selection remains active",
            ],
            "verification_predicates": [
                "LIMEN_ROOT=$PWD LIMEN_TASKS=$PWD/tasks.yaml python3 scripts/current-session-fanout.py --session <session.jsonl> --min-codex-planners 10 --executor-lanes auto --include-contrib --no-reset-spend --dry-run",
                "PYTHONPATH=cli/src python3 -m pytest cli/tests/test_current_session_fanout.py -q",
                "PYTHONPATH=cli/src python3 -c \"from limen.capacity import PAID_AGENT_ORDER; required={'codex','claude','opencode','agy','gemini','ollama','jules','copilot','warp','oz','github_actions'}; assert required <= set(PAID_AGENT_ORDER)\"",
                "LIMEN_ROOT=$PWD LIMEN_TASKS=$PWD/tasks.yaml PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes auto --dry-run",
                "bash scripts/verify-whole.sh",
            ],
        }
    return {
        "owner_repo": "organvm/limen",
        "owner_ledger": "docs/current-session-fanout.md",
        "criteria": [
            "derive this owner packet from all user turns and all detected plan sources",
            "include executor acceptance, blocker behavior, and at least one verification predicate",
            "preserve raw private bodies outside tracked files",
        ],
        "verification_predicates": [
            "PYTHONPATH=cli/src python3 -m pytest cli/tests/test_current_session_fanout.py -q",
            "python3 -m py_compile scripts/current-session-fanout.py",
        ],
    }


def planner_packets(
    themes: list[str],
    messages: list[dict[str, Any]],
    min_codex: int,
    no_reset_spend: bool,
    source_plan_hashes: list[str],
) -> list[dict[str, Any]]:
    seed_themes = list(themes)
    idx = 1
    while len(seed_themes) < min_codex:
        seed_themes.append(f"product-factory-{idx:02d}")
        idx += 1
    prompt_hashes = [msg["hash"] for msg in messages]
    packets: list[dict[str, Any]] = []
    for idx, theme in enumerate(seed_themes, start=1):
        owner = owner_packet_for_theme(theme)
        packets.append(
            {
                "id": f"PLAN-{idx:02d}-{stable_hash(theme, 8)}",
                "packet_type": "planner_packet",
                "target_agent": "codex",
                "theme": theme,
                "worktree_slug": packet_slug(f"planner-{idx:02d}-{theme}")[:80],
                "spend_guard": "no-reset-spend" if no_reset_spend else "operator-allowed-reset-spend",
                "source_prompt_hashes": prompt_hashes,
                "source_plan_hashes": list(source_plan_hashes),
                "owner_packet": owner,
                "acceptance": [
                    "derive owner packets from the full session, not just the latest turn",
                    "emit executor criteria and verification predicates",
                    "record blocked local work without stopping global product selection",
                ],
            }
        )
    return packets


def executor_packet_predicates(theme: str) -> list[str]:
    if theme == "full-fleet-overnight":
        return owner_packet_for_theme(theme)["verification_predicates"]
    return [
        "PYTHONPATH=cli/src python3 -m pytest cli/tests/test_current_session_fanout.py -q",
        "python3 -m py_compile scripts/current-session-fanout.py",
    ]


def executor_packets(
    themes: list[str],
    lanes: list[str],
    include_contrib: bool,
    no_reset_spend: bool,
    source_plan_hashes: list[str],
) -> list[dict[str, Any]]:
    packets: list[dict[str, Any]] = []
    work_themes = list(themes)
    if include_contrib and "contrib-mirror" not in work_themes:
        work_themes.append("contrib-mirror")
    for lane in lanes:
        if lane == "codex":
            continue
        theme = work_themes[len(packets) % len(work_themes)] if work_themes else "product-factory"
        packets.append(
            {
                "id": f"EXEC-{lane}-{stable_hash(theme, 8)}",
                "packet_type": "executor_packet",
                "target_agent": lane,
                "theme": theme,
                "spend_guard": "no-reset-spend" if no_reset_spend and lane == "codex" else "lane-policy",
                "source_plan_hashes": list(source_plan_hashes),
                "executor_criteria": [
                    "bounded reversible work only",
                    "return changed paths, predicate result, PR/deploy/receipt, and blocker if any",
                    "do not perform outbound sends, credential minting, purchases, deletes, or mass merges",
                    "if this lane is blocked, record the blocker and continue global product selection",
                ],
                "verification_predicates": executor_packet_predicates(theme),
            }
        )
    return packets


def digest_blockers() -> list[dict[str, str]]:
    path = ROOT / "docs" / "NEEDS-HUMAN-DIGEST.md"
    if not path.exists():
        return []
    blockers: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        match = re.match(r"##\s+\d+\.\s+(.+?)(?:\s+—\s+(.+))?$", line)
        if match:
            blockers.append({"source": "docs/NEEDS-HUMAN-DIGEST.md", "item": match.group(1), "impact": match.group(2) or ""})
        elif line.startswith("- ASK-"):
            parts = line.removeprefix("- ").split("—", 1)
            blockers.append({"source": "docs/NEEDS-HUMAN-DIGEST.md", "item": parts[0].strip(), "impact": parts[1].strip() if len(parts) > 1 else ""})
    return blockers


def blocked_local_work(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    blockers.extend(digest_blockers())
    for row in rows:
        if row["status"] != "active":
            blockers.append(
                {
                    "source": "capacity_census",
                    "item": f"{row['agent']} lane {row['status']}",
                    "impact": row["detail"],
                }
            )
    return blockers


def packet_plan_hash_intersection(packets: list[dict[str, Any]]) -> set[str]:
    if not packets:
        return set()
    covered = set(str(plan_hash) for plan_hash in packets[0].get("source_plan_hashes", []))
    for packet in packets[1:]:
        covered &= set(str(plan_hash) for plan_hash in packet.get("source_plan_hashes", []))
    return covered


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    session = find_session(args.session)
    messages = read_session_messages(session)
    plan_events = read_session_plan_events(session)
    unique_sources = unique_plan_sources(plan_events)
    source_plan_hashes = [str(event["hash"]) for event in unique_sources]
    themes = matched_themes(messages, plan_events)
    rows = lane_rows()
    lanes = lane_selection(args.executor_lanes, rows)
    no_reset_spend = not args.allow_reset_spend
    planners = planner_packets(themes, messages, args.min_codex_planners, no_reset_spend, source_plan_hashes)
    executors = executor_packets(themes, lanes, args.include_contrib, no_reset_spend, source_plan_hashes)
    all_packets = planners + executors
    packet_plan_hashes = packet_plan_hash_intersection(all_packets)
    unconsolidated_plan_hashes = [
        plan_hash for plan_hash in source_plan_hashes if plan_hash not in packet_plan_hashes
    ]
    for event in plan_events:
        event["included"] = str(event["hash"]) in packet_plan_hashes
    blockers = blocked_local_work(rows)
    global_status = "active" if planners else "blocked"
    snapshot = {
        "generated_at": now_iso(),
        "session_path": str(session),
        "session_hash": stable_hash(str(session), 24),
        "user_messages": len(messages),
        "prompt_bytes": sum(int(msg["bytes"]) for msg in messages),
        "prompt_hashes": [msg["hash"] for msg in messages],
        "plan_events": plan_events,
        "unique_plan_sources": unique_sources,
        "plan_event_count": len(plan_events),
        "unique_plan_count": len(unique_sources),
        "duplicate_plan_count": len(plan_events) - len(unique_sources),
        "source_plan_hashes": source_plan_hashes,
        "unconsolidated_plan_hashes": unconsolidated_plan_hashes,
        "themes": themes,
        "lane_classification": rows,
        "executor_lanes": lanes,
        "no_reset_spend": no_reset_spend,
        "planner_packets": planners,
        "executor_packets": executors,
        "blocked_local_work": blockers,
        "global_product_selection": {
            "status": global_status,
            "reason": "local blockers are recorded per owner/lane; unblocked planner packets remain selectable",
        },
        "status": "ready" if messages and planners and not unconsolidated_plan_hashes else "blocked",
    }
    return snapshot


def public_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Drop raw private text fields before rendering/public tests inspect output."""
    text_fields = {"text"}

    def cleanse(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: cleanse(v) for k, v in value.items() if k not in text_fields}
        if isinstance(value, list):
            return [cleanse(item) for item in value]
        return value

    return cleanse(snapshot)


def markdown_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(snapshot: dict[str, Any]) -> str:
    public = public_snapshot(snapshot)
    lines = [
        "# Current Session Fanout",
        "",
        f"Generated: `{public['generated_at']}`",
        f"Status: `{public['status']}`",
        f"User messages: `{public['user_messages']}`",
        f"Prompt bytes: `{public['prompt_bytes']}`",
        f"No reset spend: `{public['no_reset_spend']}`",
        f"Global product selection: `{public['global_product_selection']['status']}`",
        "",
        "## Themes",
        "",
    ]
    for theme in public["themes"]:
        lines.append(f"- `{theme}`")
    lines += [
        "",
        "## Plan Source Proof",
        "",
        f"Plan events: {public.get('plan_event_count', 0)}",
        f"Unique plan sources: {public.get('unique_plan_count', 0)}",
        f"Duplicate plan events: {public.get('duplicate_plan_count', 0)}",
        f"Unconsolidated plan events: {len(public.get('unconsolidated_plan_hashes', []))}",
        "",
        "| Title | Timestamp | Transcript line | Hash | Duplicate | Included |",
        "|---|---|---:|---|---|---|",
    ]
    for event in public.get("plan_events", []):
        duplicate_status = "duplicate" if event.get("duplicate") else "unique"
        included_status = "included" if event.get("included") else "missing"
        lines.append(
            "| "
            f"{markdown_cell(event.get('title'))} | "
            f"`{markdown_cell(event.get('timestamp'))}` | "
            f"`{markdown_cell(event.get('line'))}` | "
            f"`{markdown_cell(event.get('hash'))}` | "
            f"{duplicate_status} | "
            f"{included_status} |"
        )
    lines += [
        "",
        "## Planner Packets",
        "",
        "| Packet | Agent | Worktree | Theme | Criteria |",
        "|---|---|---|---|---|",
    ]
    for packet in public["planner_packets"]:
        criteria = "; ".join(packet["owner_packet"].get("criteria", [])[:2])
        lines.append(
            f"| `{packet['id']}` | `{packet['target_agent']}` | `{packet['worktree_slug']}` | "
            f"`{packet['theme']}` | {markdown_cell(criteria)} |"
        )
    lines += [
        "",
        "## Executor Packets",
        "",
        "| Packet | Agent | Theme | Criteria | Predicate |",
        "|---|---|---|---|---|",
    ]
    for packet in public["executor_packets"]:
        criteria = "; ".join(packet.get("executor_criteria", [])[:2])
        predicate = (packet.get("verification_predicates") or [""])[0]
        lines.append(
            f"| `{packet['id']}` | `{packet['target_agent']}` | `{packet['theme']}` | "
            f"{markdown_cell(criteria)} | `{markdown_cell(predicate)}` |"
        )
    focused = [packet for packet in public["planner_packets"] if packet["theme"] == "full-fleet-overnight"]
    if focused:
        packet = focused[0]
        lines += [
            "",
            "## Full-Fleet Overnight Owner Packet",
            "",
            f"Packet: `{packet['id']}`",
            f"Owner repo: `{packet['owner_packet']['owner_repo']}`",
            f"Owner ledger: `{packet['owner_packet']['owner_ledger']}`",
            "",
            "Executor criteria:",
            "",
        ]
        lines.extend(f"- {item}" for item in packet["owner_packet"]["criteria"])
        lines += ["", "Verification predicates:", ""]
        lines.extend(f"- `{item}`" for item in packet["owner_packet"]["verification_predicates"])
    lines += [
        "",
        "## Lane Classification",
        "",
        "| Agent | Kind | Status | Detail |",
        "|---|---|---|---|",
    ]
    for row in public["lane_classification"]:
        lines.append(
            f"| `{row['agent']}` | `{row['kind']}` | `{row['status']}` | {markdown_cell(row['detail'])} |"
        )
    lines += [
        "",
        "## Blocked Local Work",
        "",
        f"Global product selection remains `{public['global_product_selection']['status']}`.",
        "",
        "| Source | Item | Impact |",
        "|---|---|---|",
    ]
    for blocker in public["blocked_local_work"]:
        lines.append(
            f"| `{markdown_cell(blocker.get('source'))}` | {markdown_cell(blocker.get('item'))} | "
            f"{markdown_cell(blocker.get('impact'))} |"
        )
    lines += [
        "",
        "## Contract",
        "",
        "- Planner packets are Codex conductor work; executor packets go to active fleet lanes.",
        "- Down, depleted, or human-gated lanes are receipts, not a global stop condition.",
        "- This command never applies Codex resets, credits, top-ups, or paid overages.",
        "- Outbound identity-bearing actions remain human-gated.",
    ]
    return "\n".join(lines) + "\n"


def write_outputs(snapshot: dict[str, Any], markdown: str) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(markdown, encoding="utf-8")
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create current-session planner and executor fanout packets.")
    parser.add_argument("--session", help="Codex session JSONL path; defaults to latest session")
    parser.add_argument("--min-codex-planners", type=int, default=int(os.environ.get("LIMEN_MIN_CODEX_PLANNERS", "10")))
    parser.add_argument("--executor-lanes", default=os.environ.get("LIMEN_LANES", "auto"))
    parser.add_argument("--include-contrib", action="store_true")
    parser.add_argument("--no-reset-spend", dest="allow_reset_spend", action="store_false", default=False)
    parser.add_argument("--allow-reset-spend", action="store_true", default=False)
    parser.add_argument("--dry-run", action="store_true", help="print only; never write")
    parser.add_argument("--write", action="store_true", help="write packet receipts")
    args = parser.parse_args()

    snapshot = build_snapshot(args)
    markdown = render_markdown(snapshot)
    if args.write and not args.dry_run:
        write_outputs(snapshot, markdown)
        print(f"current-session-fanout: {snapshot['status']}; wrote {DOC_PATH} and {PRIVATE_INDEX}")
    else:
        print(markdown, end="")
        print(f"current-session-fanout: {snapshot['status']}; dry-run")
    return 0 if snapshot["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
