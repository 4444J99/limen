#!/usr/bin/env python3
"""Turn the whole current Codex session into planner and executor packets.

This does not launch paid agents. It writes receipts/packet specs when asked,
and defaults to dry-run so banked resets or credits cannot be consumed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

CODE_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("LIMEN_ROOT", CODE_ROOT))
HOME = Path.home()
PRIVATE_ROOT = Path(os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus"))
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "current-session-fanout.json"
DOC_PATH = ROOT / "docs" / "current-session-fanout.md"
sys.path.insert(0, str(CODE_ROOT / "cli" / "src"))

try:
    from limen.io import load_limen_file  # noqa: E402
    from limen.intake import contract_fields, github_pr_contract  # noqa: E402
    from limen.tabularius import pending_task_ids, submit_task_upsert  # noqa: E402
except Exception:  # pragma: no cover - import fallback for hermetic tests
    load_limen_file = None
    contract_fields = None
    github_pr_contract = None
    pending_task_ids = None
    submit_task_upsert = None

try:
    from limen.capacity import PAID_AGENT_ORDER, canonical_agent, capacity_census, select_lanes  # noqa: E402
    from limen.dispatch import _down_lanes  # noqa: E402
    from limen.workstream_contract import DEFAULT_RUNWAY, ContractError, packet_contract  # noqa: E402
except Exception:  # pragma: no cover - lane-selection fallback
    PAID_AGENT_ORDER = ()
    capacity_census = None
    canonical_agent = lambda value: str(value).strip().replace("-", "_")  # noqa: E731
    select_lanes = None
    _down_lanes = None
    DEFAULT_RUNWAY = "1d"
    ContractError = ValueError
    packet_contract = None

THEMES = [
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

FALLBACK_LANE_ALIASES = {
    "actions": "github_actions",
    "gha": "github_actions",
    "github-actions": "github_actions",
    "antigravity": "agy",
}
PREFERRED_EXECUTOR_THEMES = {
    "github_actions": "repo-salvage-consolidation",
}

PROPOSED_PLAN_RE = re.compile(
    r"<proposed_plan>\s*(.*?)(?:\s*</proposed_plan>|$)",
    re.IGNORECASE | re.DOTALL,
)
MARKDOWN_H1_RE = re.compile(r"(?m)^#\s+(.+?)\s*$")
PRIOR_PLAN_MARKERS = (
    "a previous agent produced the plan below",
    "previous agent produced the plan below",
)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def stable_hash(text: str, length: int = 18) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:length]


def runway_arg(value: str) -> str:
    if packet_contract is None:
        raise argparse.ArgumentTypeError("workstream contract module unavailable")
    try:
        return str(packet_contract(value)["runway"]["requested"])
    except ContractError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def admitted_packet_contract(runway: str) -> dict[str, Any]:
    """Reuse the parent capsule admission, or admit one standalone snapshot now."""

    started_raw = os.environ.get("LIMEN_WORKSTREAM_STARTED_EPOCH")
    deadline_raw = os.environ.get("LIMEN_WORKSTREAM_DEADLINE_EPOCH")
    if started_raw is None and deadline_raw is None:
        return packet_contract(runway)
    if started_raw is None or deadline_raw is None:
        raise ContractError("parent workstream timing is partial")
    try:
        started_epoch = int(started_raw)
        deadline_epoch = int(deadline_raw)
    except ValueError as exc:
        raise ContractError("parent workstream timing is not integer epoch state") from exc
    contract = packet_contract(
        runway,
        started_epoch=started_epoch,
        deadline_epoch=deadline_epoch,
    )
    if deadline_epoch - int(time.time()) <= 0:
        raise ContractError("parent workstream runway is exhausted; emit a successor before packetization")
    return contract


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


def user_texts_from_obj(obj: dict[str, Any]) -> list[str]:
    if obj.get("role") == "user":
        return text_from_content(obj.get("content") or obj.get("text"))
    payload = obj.get("payload")
    if isinstance(payload, dict):
        if payload.get("type") == "user_message":
            return text_from_content(payload.get("message")) + text_from_content(payload.get("text_elements"))
        if payload.get("type") == "message" and payload.get("role") == "user":
            return text_from_content(payload.get("content"))
    if obj.get("type") == "message" and obj.get("role") == "user":
        return text_from_content(obj.get("content"))
    return []


def role_texts_from_obj(obj: dict[str, Any]) -> list[tuple[str, str]]:
    payload = obj.get("payload")
    if obj.get("role") in {"user", "assistant"}:
        role = str(obj["role"])
        return [(role, text) for text in text_from_content(obj.get("content") or obj.get("text"))]
    if isinstance(payload, dict):
        if payload.get("type") == "message" and payload.get("role") in {"user", "assistant"}:
            role = str(payload["role"])
            return [(role, text) for text in text_from_content(payload.get("content"))]
        if payload.get("type") == "user_message":
            return [("user", text) for text in text_from_content(payload.get("message"))]
        if payload.get("type") == "agent_message":
            return [("assistant", text) for text in text_from_content(payload.get("message"))]
    if obj.get("type") == "message" and obj.get("role") in {"user", "assistant"}:
        role = str(obj["role"])
        return [(role, text) for text in text_from_content(obj.get("content"))]
    return []


def read_session_messages(path: Path) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return messages
    for idx, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        timestamp = obj.get("timestamp")
        for text in user_texts_from_obj(obj):
            messages.append(
                {
                    "line": idx,
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
    marker_index = -1
    for marker in PRIOR_PLAN_MARKERS:
        marker_index = lower_text.find(marker)
        if marker_index != -1:
            break
    if marker_index == -1:
        return None
    match = MARKDOWN_H1_RE.search(text, marker_index)
    if not match:
        return None
    return text[match.start() :]


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
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return events
    for idx, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        timestamp = obj.get("timestamp")
        for role, text in role_texts_from_obj(obj):
            if not text.strip():
                continue
            message_key = (role, text, timestamp)
            if message_key in seen_messages:
                continue
            seen_messages.add(message_key)
            ordinal = 1
            if role == "user":
                block = user_prior_plan_block(text)
                if block:
                    events.append(
                        plan_event(
                            line=idx,
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
                            line=idx,
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
    newest_first = sorted(
        events,
        key=lambda event: (int(event["line"]), str(event["timestamp"] or "")),
        reverse=True,
    )
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
    if path_arg:
        path = Path(path_arg).expanduser()
    else:
        path = latest_codex_session()
    if path is None or not path.exists():
        raise FileNotFoundError("no Codex session JSONL found; set LIMEN_CURRENT_SESSION_JSONL or pass --session")
    return path


def matched_themes(messages: list[dict[str, Any]], plan_events: list[dict[str, Any]] | None = None) -> list[str]:
    body = "\n".join(str(msg["text"]).lower() for msg in messages)
    if plan_events:
        body += "\n" + "\n".join(str(event.get("title", "")).lower() for event in plan_events)
    found = [name for name, needles in THEMES if any(needle in body for needle in needles)]
    return found or ["current-session-intake"]


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def _normalize_lane_rows(rows: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        remaining = _row_value(row, "remaining")
        detail = str(_row_value(row, "detail", "") or "")
        reachable = bool(_row_value(row, "reachable", False))
        if reachable:
            status = "active"
        elif remaining == 0:
            status = "depleted"
        elif any(needle in detail.lower() for needle in ("not set", "auth", "assignable", "no model pulled")):
            status = "human-gated"
        else:
            status = str(_row_value(row, "status", "") or "down")
        normalized.append(
            {
                "agent": str(_row_value(row, "agent", "") or ""),
                "kind": str(_row_value(row, "kind", "") or ""),
                "status": status,
                "reachable": reachable,
                "remaining": remaining,
                "detail": detail,
            }
        )
    return normalized


def lane_rows() -> list[dict[str, Any]]:
    if capacity_census is None or load_limen_file is None:
        return []
    try:
        board = load_limen_file(ROOT / "tasks.yaml")
        return _normalize_lane_rows(list(capacity_census(board)))
    except Exception:
        return _normalize_lane_rows([])


def lane_selection(selector: str, rows: list[dict[str, Any]] | None = None) -> list[str]:
    if selector and selector not in {"auto", "all"}:
        lanes = [
            FALLBACK_LANE_ALIASES.get(item.strip(), item.strip())
            for item in re.split(r"[,:\s]+", selector)
            if item.strip()
        ]
        if lanes:
            return list(dict.fromkeys(lanes))
    if rows is not None:
        by_agent = {row["agent"]: row for row in rows}
        if selector == "all":
            return [str(agent) for agent in PAID_AGENT_ORDER]
        active = [str(agent) for agent in PAID_AGENT_ORDER if by_agent.get(str(agent), {}).get("status") == "active"]
        return active
    if select_lanes is None or load_limen_file is None or _down_lanes is None:
        return []
    try:
        board = load_limen_file(ROOT / "tasks.yaml")
        return list(select_lanes(selector, board=board, down_lanes=_down_lanes()))
    except Exception:
        return []


def packet_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-")
    return slug or "packet"


def origin_repo_slug() -> str:
    explicit = os.environ.get("LIMEN_CURRENT_SESSION_FANOUT_REPO")
    if explicit:
        return explicit
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "organvm/limen"
    if result.returncode != 0:
        return "organvm/limen"
    remote = result.stdout.strip()
    match = re.search(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?$", remote)
    if not match:
        return "organvm/limen"
    return f"{match.group(1)}/{match.group(2)}"


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
    if theme == "repo-salvage-consolidation":
        return {
            "owner_repo": "organvm/limen",
            "owner_ledger": "docs/current-session-fanout/repo-salvage-consolidation-plan-04.md",
            "criteria": [
                "derive repo roots from configured substrate paths, not a fixed drive name or hand-maintained list",
                "record nested repos, duplicate remotes, dirty state, test/build/deploy surfaces, and hash-only product surfaces",
                "collapse duplicate remotes/product surfaces into one canonical owner cluster with a disposition",
                "keep blocked local work item-scoped while global product selection continues",
                "preserve raw prompt and plan bodies outside tracked files; public packet provenance stays hash-only",
                "stage GitHub/org/App/credential/deploy mutations as blockers unless a human gate is present",
            ],
            "verification_predicates": [
                "python3 -m py_compile scripts/repo-surface-ledger.py scripts/salvage-yard-map.py scripts/product-ledger.py scripts/current-session-fanout.py",
                "PYTHONPATH=cli/src python3 -m pytest cli/tests/test_substrate_repo_product_fanout.py -q",
                "python3 scripts/repo-surface-ledger.py --refresh --dry-run",
                "python3 scripts/salvage-yard-map.py --dry-run",
                "python3 scripts/product-ledger.py --dry-run",
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
    source_plan_hashes: list[str] | None = None,
) -> list[dict[str, Any]]:
    seed_themes = list(themes)
    idx = 1
    while len(seed_themes) < min_codex:
        seed_themes.append(f"product-factory-{idx:02d}")
        idx += 1
    prompt_hashes = [msg["hash"] for msg in messages]
    plan_hashes = list(source_plan_hashes or [])
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
                "source_plan_hashes": list(plan_hashes),
                "owner_packet": owner,
                "acceptance": [
                    "derive owner packets from the full session, not just the latest turn",
                    "emit executor criteria and verification predicates",
                    "record blocked local work without stopping global product selection",
                ],
                "executor_criteria": [
                    "name the owner repo or owner ledger, allowed files, stop condition, receipt target, and target lane before dispatch",
                    "use source_prompt_hashes and source_plan_hashes as provenance instead of pasting raw prompt or plan text",
                    "split local blockers into owner-recorded work while keeping other unblocked product rows eligible",
                ],
                "verification_predicates": [
                    "python3 scripts/current-session-fanout.py --session <source-session-jsonl> --min-codex-planners 12 --executor-lanes auto --include-contrib --no-reset-spend --dry-run",
                    "python3 scripts/product-ledger.py --refresh --redacted-summary",
                    "PYTHONPATH=cli/src python3 -m pytest cli/tests/test_substrate_repo_product_fanout.py -q",
                ],
            }
        )
    return packets


def executor_packets(
    themes: list[str],
    lanes: list[str],
    include_contrib: bool,
    no_reset_spend: bool,
    source_plan_hashes: list[str] | None = None,
) -> list[dict[str, Any]]:
    packets: list[dict[str, Any]] = []
    work_themes = list(themes)
    plan_hashes = list(source_plan_hashes or [])
    if include_contrib and "contrib-mirror" not in work_themes:
        work_themes.append("contrib-mirror")
    reserved_themes = {
        theme for lane, theme in PREFERRED_EXECUTOR_THEMES.items() if lane in lanes and theme in work_themes
    }
    for lane in lanes:
        if lane == "codex":
            continue
        preferred_theme = PREFERRED_EXECUTOR_THEMES.get(lane)
        if preferred_theme in work_themes:
            theme = preferred_theme
        else:
            selectable_themes = [theme for theme in work_themes if theme not in reserved_themes] or work_themes
            theme = selectable_themes[len(packets) % len(selectable_themes)] if selectable_themes else "product-factory"
        owner = owner_packet_for_theme(theme)
        packets.append(
            {
                "id": f"EXEC-{lane}-{stable_hash(theme, 8)}",
                "packet_type": "executor_packet",
                "target_agent": lane,
                "theme": theme,
                "spend_guard": "no-reset-spend" if no_reset_spend and lane == "codex" else "lane-policy",
                "source_plan_hashes": list(plan_hashes),
                "acceptance": [
                    "bounded reversible work only",
                    "return changed paths, predicate, PR/deploy/receipt, and blocker if any",
                    "do not perform outbound sends or credential/credit mutations",
                ],
                "executor_criteria": [
                    "execute only after a planner packet has named owner scope and a narrow predicate",
                    "write changed paths, predicate result, and receipt or blocker into the owner surface",
                    "treat failed local prerequisites as lane/blocker records, not as a stop for global product selection",
                ],
                "verification_predicates": [
                    *(owner.get("verification_predicates") or ["run the owner predicate named by the planner packet"]),
                    "python3 scripts/product-ledger.py --refresh --redacted-summary",
                ],
            }
        )
    return packets


def task_seed_id(session_hash: str, packet_id: str) -> str:
    stem = re.sub(r"[^A-Z0-9-]+", "-", packet_id.upper()).strip("-")
    return f"CSF-{session_hash[:8].upper()}-{stem}"[:120]


def task_seed_context(
    *,
    snapshot: dict[str, Any],
    packet: dict[str, Any],
    phase: str,
) -> str:
    acceptance = "\n".join(f"- {item}" for item in packet.get("acceptance", []))
    executor_criteria = "\n".join(f"- {item}" for item in packet.get("executor_criteria", []))
    verification_predicates = "\n".join(f"- {item}" for item in packet.get("verification_predicates", []))
    plan_hashes = ", ".join(str(value) for value in snapshot.get("source_plan_hashes", []))
    prompt_hashes = ", ".join(str(value) for value in snapshot.get("prompt_hashes", [])[:12])
    if len(snapshot.get("prompt_hashes", [])) > 12:
        prompt_hashes += ", ..."
    workstream_contract = packet.get("workstream_contract") or snapshot.get("workstream_contract") or {}
    contract_json = json.dumps(workstream_contract, sort_keys=True, separators=(",", ":"))
    return (
        f"Current-session fanout {phase} packet.\n"
        f"Packet id: {packet['id']}\n"
        f"Theme: {packet.get('theme', 'current-session-intake')}\n"
        f"Source session: {snapshot['session_path']}\n"
        f"Source plan hashes: {plan_hashes or 'none'}\n"
        f"Source prompt hashes: {prompt_hashes or 'none'}\n"
        f"Workstream contract: {contract_json}\n"
        "Full approval: proceed without confirmation for in-scope reversible work. Destructive, "
        "credential, paid-spend, public-send, and runtime/host mutations remain gated. Re-check "
        "remaining runway before each bounded packet and stop or successor-route before zero.\n"
        "Do not paste raw private prompt or plan bodies into public files, commits, PRs, "
        "task logs, or outbound systems. Use the hashes above as provenance.\n"
        "Acceptance:\n"
        f"{acceptance}\n"
        "Executor criteria:\n"
        f"{executor_criteria}\n"
        "Verification predicates:\n"
        f"{verification_predicates}"
    )


def task_seed_specs(snapshot: dict[str, Any], repo: str | None = None) -> list[dict[str, Any]]:
    repo = repo or origin_repo_slug()
    created = dt.date.today().isoformat()
    session_hash = str(snapshot["session_hash"])
    seed: list[dict[str, Any]] = []
    planner_task_ids: dict[str, str] = {}
    runway_seconds = int(snapshot["workstream_contract"]["runway"]["duration_seconds"])
    runway_label = f"profile:runway-seconds:{runway_seconds}"

    for packet in snapshot.get("planner_packets", []):
        task_id = task_seed_id(session_hash, str(packet["id"]))
        planner_task_ids.setdefault(str(packet.get("theme")), task_id)
        seed.append(
            {
                "id": task_id,
                "title": f"Plan current-session fanout stream: {packet.get('theme')}",
                "description": "Derive a bounded owner packet and verification predicate from the proofed session fanout.",
                "repo": repo,
                "type": "code",
                "target_agent": packet["target_agent"],
                "priority": "high",
                "budget_cost": 1,
                "status": "open",
                "labels": [
                    "current-session-fanout",
                    "planner",
                    "generated",
                    "product",
                    "ship-order",
                    "no-reset-spend",
                    runway_label,
                ],
                "urls": [],
                "context": task_seed_context(snapshot=snapshot, packet=packet, phase="planner"),
                **contract_fields(github_pr_contract(repo, task_id)),
                "depends_on": [],
                "created": created,
                "dispatch_log": [],
                "packet_id": packet["id"],
                "packet_type": packet["packet_type"],
                "theme": packet.get("theme"),
                "source_plan_hashes": list(packet.get("source_plan_hashes", [])),
                "executor_criteria": list(packet.get("executor_criteria", [])),
                "verification_predicates": list(packet.get("verification_predicates", [])),
                "workstream_contract": dict(packet.get("workstream_contract") or {}),
            }
        )

    fallback_planner = seed[0]["id"] if seed else None
    for packet in snapshot.get("executor_packets", []):
        task_id = task_seed_id(session_hash, str(packet["id"]))
        depends_on = [planner_task_ids.get(str(packet.get("theme")), fallback_planner)]
        depends_on = [task_id for task_id in depends_on if task_id]
        seed.append(
            {
                "id": task_id,
                "title": f"Execute current-session fanout stream: {packet.get('theme')}",
                "description": "Run the bounded executor lane after the matching planner packet lands.",
                "repo": repo,
                "type": "code",
                "target_agent": packet["target_agent"],
                "priority": "high",
                "budget_cost": 1,
                "status": "open",
                "labels": [
                    "current-session-fanout",
                    "executor",
                    "generated",
                    "product",
                    "ship-order",
                    runway_label,
                ],
                "urls": [],
                "context": task_seed_context(snapshot=snapshot, packet=packet, phase="executor"),
                **contract_fields(github_pr_contract(repo, task_id)),
                "depends_on": depends_on,
                "created": created,
                "dispatch_log": [],
                "packet_id": packet["id"],
                "packet_type": packet["packet_type"],
                "theme": packet.get("theme"),
                "source_plan_hashes": list(packet.get("source_plan_hashes", [])),
                "executor_criteria": list(packet.get("executor_criteria", [])),
                "verification_predicates": list(packet.get("verification_predicates", [])),
                "workstream_contract": dict(packet.get("workstream_contract") or {}),
            }
        )
    return seed


def task_model_payload(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        key: spec[key]
        for key in (
            "id",
            "title",
            "description",
            "repo",
            "type",
            "target_agent",
            "priority",
            "budget_cost",
            "status",
            "labels",
            "urls",
            "context",
            "predicate",
            "receipt_target",
            "depends_on",
            "created",
            "dispatch_log",
            "workstream_contract",
        )
        if key in spec
    }


def apply_task_seed(snapshot: dict[str, Any], tasks_path: Path) -> dict[str, Any]:
    if load_limen_file is None or pending_task_ids is None or submit_task_upsert is None:
        return {"status": "blocked", "reason": "limen task model unavailable", "appended": 0, "skipped": 0}
    seed = list(snapshot.get("task_seed", []))
    if not seed:
        return {"status": "ready", "reason": "no task seed requested", "appended": 0, "skipped": 0}
    appended = 0
    skipped = 0
    fresh = load_limen_file(tasks_path)
    existing = {task.id for task in fresh.tasks} | pending_task_ids(tasks_path)
    session_id = os.environ.get("LIMEN_SESSION_ID", "current-session-fanout")
    for spec in seed:
        if spec["id"] in existing:
            skipped += 1
            continue
        submit_task_upsert(
            tasks_path,
            task_model_payload(spec),
            agent="current-session-fanout",
            session_id=session_id,
        )
        existing.add(spec["id"])
        appended += 1
    return {
        "status": "ready",
        "appended": appended,
        "skipped": skipped,
        "tasks_path": str(tasks_path),
        "mode": "tabularius-ticket",
    }


def digest_blockers() -> list[dict[str, str]]:
    path = ROOT / "docs" / "NEEDS-HUMAN-DIGEST.md"
    if not path.exists():
        return []
    blockers: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        match = re.match(r"##\s+\d+\.\s+(.+?)(?:\s+—\s+(.+))?$", line)
        if match:
            blockers.append(
                {
                    "source": "docs/NEEDS-HUMAN-DIGEST.md",
                    "item": match.group(1),
                    "impact": match.group(2) or "",
                }
            )
        elif line.startswith("- ASK-"):
            parts = line.removeprefix("- ").split("—", 1)
            blockers.append(
                {
                    "source": "docs/NEEDS-HUMAN-DIGEST.md",
                    "item": parts[0].strip(),
                    "impact": parts[1].strip() if len(parts) > 1 else "",
                }
            )
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


def fanout_verification_command(
    *,
    session: Path,
    min_codex_planners: int,
    executor_lanes: str,
    include_contrib: bool,
    no_reset_spend: bool,
    runway: str = DEFAULT_RUNWAY,
) -> str:
    args = [
        "python3",
        "scripts/current-session-fanout.py",
        "--session",
        str(session),
        "--min-codex-planners",
        str(min_codex_planners),
        "--executor-lanes",
        executor_lanes,
        "--runway",
        runway,
    ]
    if include_contrib:
        args.append("--include-contrib")
    args.append("--no-reset-spend" if no_reset_spend else "--allow-reset-spend")
    args.append("--dry-run")
    return " ".join(args)


def set_run_verification_predicate(
    packets: list[dict[str, Any]],
    *,
    session: Path,
    args: argparse.Namespace,
    no_reset_spend: bool,
) -> None:
    command = fanout_verification_command(
        session=session,
        min_codex_planners=args.min_codex_planners,
        executor_lanes=args.executor_lanes,
        include_contrib=args.include_contrib,
        no_reset_spend=no_reset_spend,
        runway=getattr(args, "runway", DEFAULT_RUNWAY),
    )
    for packet in packets:
        predicates = list(packet.get("verification_predicates") or [])
        if predicates:
            predicates[0] = command
        else:
            predicates = [command]
        packet["verification_predicates"] = predicates


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    session = find_session(args.session)
    messages = read_session_messages(session)
    plan_events = read_session_plan_events(session)
    unique_sources = unique_plan_sources(plan_events)
    source_plan_hashes = [str(event["hash"]) for event in unique_sources]
    themes = matched_themes(messages, plan_events)
    rows = lane_rows()
    try:
        lanes = lane_selection(args.executor_lanes, rows)
    except TypeError:
        lanes = lane_selection(args.executor_lanes)
    no_reset_spend = not args.allow_reset_spend
    if packet_contract is None:
        raise ContractError("workstream contract module unavailable")
    workstream = admitted_packet_contract(getattr(args, "runway", DEFAULT_RUNWAY))
    planners = planner_packets(
        themes,
        messages,
        args.min_codex_planners,
        no_reset_spend,
        source_plan_hashes,
    )
    executors = executor_packets(
        themes,
        lanes,
        args.include_contrib,
        no_reset_spend,
        source_plan_hashes,
    )
    for packet in planners + executors:
        packet["workstream_contract"] = workstream
    set_run_verification_predicate(planners, session=session, args=args, no_reset_spend=no_reset_spend)
    packet_plan_hashes = packet_plan_hash_intersection(planners + executors)
    unconsolidated_plan_hashes = [plan_hash for plan_hash in source_plan_hashes if plan_hash not in packet_plan_hashes]
    for event in plan_events:
        event["included"] = str(event["hash"]) in packet_plan_hashes
    for event in unique_sources:
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
        "plan_hashes": source_plan_hashes,
        "unconsolidated_plan_hashes": unconsolidated_plan_hashes,
        "themes": themes,
        "executor_lanes": lanes,
        "no_reset_spend": no_reset_spend,
        "workstream_contract": workstream,
        "planner_packets": planners,
        "executor_packets": executors,
        "blocked_local_work": blockers,
        "global_product_selection": {
            "status": global_status,
            "reason": "planner packets remain eligible while local blockers are owner-recorded",
        },
        "status": "ready" if messages and planners and not unconsolidated_plan_hashes else "blocked",
    }
    if getattr(args, "seed_tasks", False) or getattr(args, "apply_task_seed", False):
        seed = task_seed_specs(snapshot)
        snapshot["task_seed"] = seed
        snapshot["task_seed_count"] = len(seed)
        snapshot["task_seed_repo"] = seed[0]["repo"] if seed else origin_repo_slug()
    else:
        snapshot["task_seed"] = []
        snapshot["task_seed_count"] = 0
        snapshot["task_seed_repo"] = None
    return snapshot


def markdown_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(snapshot: dict[str, Any]) -> str:
    lines = [
        "# Current Session Fanout",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        f"Status: `{snapshot['status']}`",
        f"User messages: `{snapshot['user_messages']}`",
        f"Prompt bytes: `{snapshot['prompt_bytes']}`",
        f"No reset spend: `{snapshot['no_reset_spend']}`",
        "",
        "## Themes",
        "",
    ]
    for theme in snapshot["themes"]:
        lines.append(f"- `{theme}`")
    lines += [
        "",
        "## Plan Source Proof",
        "",
        f"Plan events: {snapshot.get('plan_event_count', 0)}",
        f"Unique plan sources: {snapshot.get('unique_plan_count', 0)}",
        f"Duplicate plan events: {snapshot.get('duplicate_plan_count', 0)}",
        f"Unconsolidated plan events: {len(snapshot.get('unconsolidated_plan_hashes', []))}",
        "",
        "| Title | Timestamp | Transcript line | Hash | Duplicate | Included |",
        "|---|---|---:|---|---|---|",
    ]
    for event in snapshot.get("plan_events", []):
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
        "| Packet | Agent | Worktree | Theme |",
        "|---|---|---|---|",
    ]
    for packet in snapshot["planner_packets"]:
        lines.append(
            f"| `{packet['id']}` | `{packet['target_agent']}` | `{packet['worktree_slug']}` | `{packet['theme']}` |"
        )
    lines += [
        "",
        "## Executor Packets",
        "",
        "| Packet | Agent | Theme |",
        "|---|---|---|",
    ]
    for packet in snapshot["executor_packets"]:
        lines.append(f"| `{packet['id']}` | `{packet['target_agent']}` | `{packet['theme']}` |")
    lines += [
        "",
        "## Executor Criteria",
        "",
        "| Packet | Criteria | Verification predicates |",
        "|---|---|---|",
    ]
    for packet in snapshot["planner_packets"] + snapshot["executor_packets"]:
        criteria = "<br>".join(markdown_cell(item) for item in packet.get("executor_criteria", [])) or "none"
        predicates = (
            "<br>".join(f"`{markdown_cell(item)}`" for item in packet.get("verification_predicates", [])) or "none"
        )
        lines.append(f"| `{packet['id']}` | {criteria} | {predicates} |")
    full_fleet = next(
        (packet for packet in snapshot["planner_packets"] if packet.get("theme") == "full-fleet-overnight"),
        None,
    )
    if full_fleet:
        owner = full_fleet.get("owner_packet", {})
        lines += [
            "",
            "## Full-Fleet Overnight Owner Packet",
            "",
            f"Owner repo: `{owner.get('owner_repo', 'unknown')}`",
            f"Owner ledger: `{owner.get('owner_ledger', 'unknown')}`",
            "",
            "Executor criteria:",
        ]
        lines.extend(f"- {item}" for item in owner.get("criteria", []))
        lines += ["", "Verification predicates:"]
        lines.extend(f"- `{item}`" for item in owner.get("verification_predicates", []))
    lines += [
        "",
        "## Global Product Selection",
        "",
        f"Global product selection remains `{snapshot['global_product_selection']['status']}`.",
    ]
    if snapshot.get("blocked_local_work"):
        lines += ["", "Blocked local work:"]
        for blocker in snapshot["blocked_local_work"]:
            impact = blocker.get("impact") or "recorded"
            lines.append(f"- {markdown_cell(blocker.get('item'))}: {markdown_cell(impact)}")
    if snapshot.get("task_seed"):
        lines += [
            "",
            "## Task Seed",
            "",
            f"Seed tasks: {snapshot.get('task_seed_count', 0)}",
            f"Seed repo: `{snapshot.get('task_seed_repo')}`",
        ]
        if snapshot.get("task_seed_apply"):
            apply_result = snapshot["task_seed_apply"]
            lines.append(
                "Apply result: "
                f"`{apply_result.get('status')}` "
                f"(appended {apply_result.get('appended', 0)}, skipped {apply_result.get('skipped', 0)})"
            )
        lines += [
            "",
            "| Task | Type | Agent | Depends on | Theme |",
            "|---|---|---|---|---|",
        ]
        for spec in snapshot["task_seed"]:
            depends_on = ", ".join(f"`{task_id}`" for task_id in spec.get("depends_on", [])) or "none"
            lines.append(
                f"| `{spec['id']}` | `{spec['packet_type']}` | `{spec['target_agent']}` | "
                f"{depends_on} | `{spec.get('theme')}` |"
            )
    lines += [
        "",
        "## Contract",
        "",
        "- Planner packets are Codex conductor work; executor packets go to active fleet lanes.",
        "- Every packet carries the validated finite runway into the typed execution profile and the no-modal authorization contract into its prompt.",
        "- Task seeding submits only `open` queue items through Tabularius; `dispatch-async.py` or `limen dispatch` launches them after the keeper folds the tickets.",
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
    parser.add_argument(
        "--runway",
        type=runway_arg,
        default=os.environ.get(
            "LIMEN_WORKSTREAM_REQUESTED",
            os.environ.get("LIMEN_WORKSTREAM_RUNWAY", DEFAULT_RUNWAY),
        ),
    )
    parser.add_argument("--include-contrib", action="store_true")
    parser.add_argument("--no-reset-spend", dest="allow_reset_spend", action="store_false", default=False)
    parser.add_argument("--allow-reset-spend", action="store_true", default=False)
    parser.add_argument("--seed-tasks", action="store_true", help="derive deterministic open task specs from packets")
    parser.add_argument("--apply-task-seed", action="store_true", help="append derived open tasks to tasks.yaml")
    parser.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS", str(ROOT / "tasks.yaml")))
    parser.add_argument("--dry-run", action="store_true", help="print only; never write")
    parser.add_argument("--write", action="store_true", help="write packet receipts")
    args = parser.parse_args()
    snapshot = build_snapshot(args)
    if args.apply_task_seed and not args.dry_run:
        snapshot["task_seed_apply"] = apply_task_seed(snapshot, Path(args.tasks))
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
