#!/usr/bin/env python3
"""Turn a native agent session into capability-selected planner/executor packets.

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
PRIVATE_ROOT = Path(os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus"))
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "current-session-fanout.json"
DOC_PATH = ROOT / "docs" / "current-session-fanout.md"
sys.path.insert(0, str(CODE_ROOT / "cli" / "src"))

try:
    from limen.io import load_limen_file  # noqa: E402
    from limen.intake import contract_fields, github_pr_contract  # noqa: E402
except Exception:  # pragma: no cover - import fallback for hermetic tests
    load_limen_file = None
    contract_fields = None
    github_pr_contract = None

try:
    from limen.capacity import canonical_agent, capacity_census  # noqa: E402
    from limen.census import execution_profiles, paid_agent_order  # noqa: E402
    from limen.conduct import (  # noqa: E402
        AgentIdentityV1,
        AuthorityEnvelopeV1,
        FanoutBoundsV1,
        ResourceClaimV1,
        RetryPolicyV1,
        SpendEnvelopeV1,
        WorkPacketV1,
    )
    from limen.conduct.client import client_from_env  # noqa: E402
    from limen.session_sources import (  # noqa: E402
        SessionSource,
        child_identity_environment,
        read_session_records,
        resolve_session,
    )
    from limen.workstream_contract import DEFAULT_RUNWAY, ContractError, packet_contract  # noqa: E402
except Exception:  # pragma: no cover - import failure is surfaced by the relevant operation
    capacity_census = None
    canonical_agent = lambda value: str(value).strip().replace("-", "_")  # noqa: E731
    execution_profiles = None
    paid_agent_order = None
    AgentIdentityV1 = None
    AuthorityEnvelopeV1 = None
    FanoutBoundsV1 = None
    ResourceClaimV1 = None
    RetryPolicyV1 = None
    SpendEnvelopeV1 = None
    WorkPacketV1 = None
    client_from_env = None
    SessionSource = Any
    child_identity_environment = None
    read_session_records = None
    resolve_session = None
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
    ("peer-planner-worktrees", ("10 worktrees", "planner", "worktree", "peer conductor")),
    ("autopoietic-conductor", ("autopoetic", "autopoietic", "forever", "tokens")),
]

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


def _session_objects(source: SessionSource | Path) -> list[dict[str, Any]]:
    if isinstance(source, Path):
        try:
            lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []
        objects: list[dict[str, Any]] = []
        for line in lines:
            try:
                value = json.loads(line)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                objects.append(value)
        return objects
    if read_session_records is None:
        raise RuntimeError("native session source adapters are unavailable")
    return list(read_session_records(source))


def read_session_messages(source: SessionSource | Path) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for idx, obj in enumerate(_session_objects(source), start=1):
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


def read_session_plan_events(source: SessionSource | Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    seen_messages: set[tuple[str, str, str | None]] = set()
    for idx, obj in enumerate(_session_objects(source), start=1):
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


def find_session(path_arg: str | None, source_agent: str = "auto") -> SessionSource:
    if resolve_session is None:
        raise RuntimeError("native session source adapters are unavailable")
    explicit = path_arg or os.environ.get("LIMEN_CURRENT_SESSION")
    return resolve_session(explicit, source_agent=canonical_agent(source_agent))


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


def lane_selection(
    selector: str,
    rows: list[dict[str, Any]] | None = None,
    *,
    capability: str = "execute",
) -> list[str]:
    """Select lanes from the canonical capability register plus live health."""

    if execution_profiles is None or paid_agent_order is None:
        raise RuntimeError("canonical lane census is unavailable")
    profiles = execution_profiles()
    inventory = [agent for agent in paid_agent_order() if capability in profiles[agent].capabilities]
    if selector and selector not in {"auto", "all"}:
        selected: list[str] = []
        for value in re.split(r"[,:\s]+", selector):
            if not value.strip():
                continue
            agent = canonical_agent(value.strip())
            if agent not in profiles:
                raise ValueError(f"unknown lane: {value}")
            if capability not in profiles[agent].capabilities:
                raise ValueError(f"lane {agent} lacks required capability: {capability}")
            if agent not in selected:
                selected.append(agent)
        return selected
    if selector == "all":
        return inventory
    live_rows = rows if rows is not None else lane_rows()
    by_agent = {canonical_agent(row["agent"]): row for row in live_rows}
    return [agent for agent in inventory if by_agent.get(agent, {}).get("status") == "active"]


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
                "derive lane inventory and role eligibility from canonical census execution profiles",
                "`auto` selects active reachable lanes while down/depleted/human-gated lanes stay visible in receipts",
                "`all` preserves every registered lane for audit without pretending down lanes are runnable",
                "async dry-runs do not launch live dispatch or spend resets/credits",
                "blocked local gates are recorded as local blockers while global product selection remains active",
            ],
            "verification_predicates": [
                "LIMEN_ROOT=$PWD LIMEN_TASKS=$PWD/tasks.yaml python3 scripts/current-session-fanout.py --session <native-session> --source-agent <agent> --min-planners 10 --planner-lanes auto --executor-lanes auto --include-contrib --no-reset-spend --dry-run",
                "PYTHONPATH=cli/src python3 -m pytest cli/tests/test_current_session_fanout.py -q",
                "PYTHONPATH=cli/src python3 -c \"from limen.census import execution_profiles; assert all(p.capabilities for p in execution_profiles().values())\"",
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
    min_planners: int,
    planner_lanes: list[str],
    no_reset_spend: bool,
    *,
    initiator_agent: str,
    conductor_agent: str,
    root_run_id: str,
    source_plan_hashes: list[str] | None = None,
) -> list[dict[str, Any]]:
    if not planner_lanes:
        return []
    seed_themes = list(themes)
    idx = 1
    while len(seed_themes) < min_planners:
        seed_themes.append(f"product-factory-{idx:02d}")
        idx += 1
    prompt_hashes = [msg["hash"] for msg in messages]
    plan_hashes = list(source_plan_hashes or [])
    packets: list[dict[str, Any]] = []
    for idx, theme in enumerate(seed_themes, start=1):
        owner = owner_packet_for_theme(theme)
        target_agent = planner_lanes[(idx - 1) % len(planner_lanes)]
        run_id = f"{root_run_id}/plan/{idx:02d}-{stable_hash(theme, 8)}"
        runtime_env = child_identity_environment(
            executor_agent=target_agent,
            initiator_agent=initiator_agent,
            conductor_agent=conductor_agent,
            root_run_id=root_run_id,
            parent_run_id=root_run_id,
            run_id=run_id,
        )
        packets.append(
            {
                "id": f"PLAN-{idx:02d}-{stable_hash(theme, 8)}",
                "packet_type": "planner_packet",
                "target_agent": target_agent,
                "native_identity": target_agent,
                "initiator_agent": initiator_agent,
                "conductor_agent": conductor_agent,
                "root_run_id": root_run_id,
                "parent_run_id": root_run_id,
                "run_id": run_id,
                "runtime_env": runtime_env,
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
                    "python3 scripts/current-session-fanout.py --session <native-session> --source-agent <agent> --min-planners 12 --planner-lanes auto --executor-lanes auto --include-contrib --no-reset-spend --dry-run",
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
    *,
    initiator_agent: str,
    conductor_agent: str,
    root_run_id: str,
    planner_packets_by_theme: dict[str, dict[str, Any]],
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
        preferred_theme = PREFERRED_EXECUTOR_THEMES.get(lane)
        if preferred_theme in work_themes:
            theme = preferred_theme
        else:
            selectable_themes = [theme for theme in work_themes if theme not in reserved_themes] or work_themes
            theme = selectable_themes[len(packets) % len(selectable_themes)] if selectable_themes else "product-factory"
        owner = owner_packet_for_theme(theme)
        parent = planner_packets_by_theme.get(theme) or next(iter(planner_packets_by_theme.values()), None)
        parent_run_id = str(parent["run_id"]) if parent else root_run_id
        run_id = f"{root_run_id}/execute/{lane}-{stable_hash(theme, 8)}"
        runtime_env = child_identity_environment(
            executor_agent=lane,
            initiator_agent=initiator_agent,
            conductor_agent=conductor_agent,
            root_run_id=root_run_id,
            parent_run_id=parent_run_id,
            run_id=run_id,
        )
        packets.append(
            {
                "id": f"EXEC-{lane}-{stable_hash(theme, 8)}",
                "packet_type": "executor_packet",
                "target_agent": lane,
                "native_identity": lane,
                "initiator_agent": initiator_agent,
                "conductor_agent": conductor_agent,
                "root_run_id": root_run_id,
                "parent_run_id": parent_run_id,
                "run_id": run_id,
                "runtime_env": runtime_env,
                "theme": theme,
                "spend_guard": "no-reset-spend" if no_reset_spend else "lane-policy",
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
        f"Initiator agent: {packet['initiator_agent']}\n"
        f"Conductor agent: {packet['conductor_agent']}\n"
        f"Run lineage: {packet['root_run_id']} -> {packet['parent_run_id']} -> {packet['run_id']}\n"
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
                "initiator_agent": packet["initiator_agent"],
                "conductor_agent": packet["conductor_agent"],
                "root_run_id": packet["root_run_id"],
                "parent_run_id": packet["parent_run_id"],
                "run_id": packet["run_id"],
                "runtime_env": dict(packet["runtime_env"]),
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
                "initiator_agent": packet["initiator_agent"],
                "conductor_agent": packet["conductor_agent"],
                "root_run_id": packet["root_run_id"],
                "parent_run_id": packet["parent_run_id"],
                "run_id": packet["run_id"],
                "runtime_env": dict(packet["runtime_env"]),
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
            "initiator_agent",
            "conductor_agent",
            "root_run_id",
            "parent_run_id",
            "run_id",
            "runtime_env",
            "workstream_contract",
        )
        if key in spec
    }


class FanoutReservationError(RuntimeError):
    """The conduct graph was not reserved completely, so no child may launch."""


def _conductor_identity(client: Any, snapshot: dict[str, Any]) -> Any:
    capabilities = client.capabilities()
    sessions = capabilities.get("sessions", []) if isinstance(capabilities, dict) else []
    desired_session = os.environ.get("LIMEN_CONDUCTOR_SESSION_ID", "").strip()
    candidates: list[dict[str, Any]] = []
    for row in sessions:
        if not isinstance(row, dict):
            continue
        identity = row.get("identity")
        if not isinstance(identity, dict):
            continue
        if not row.get("healthy") or not row.get("accepting_work", True):
            continue
        if "conduct" not in set(row.get("capabilities") or []):
            continue
        if desired_session and str(row.get("session_id")) != desired_session:
            continue
        candidates.append(row)
    if desired_session and not candidates:
        raise FanoutReservationError(
            f"configured conductor session is unavailable or unhealthy: {desired_session}"
        )
    if not candidates:
        raise FanoutReservationError("no healthy registered conduct session is available")
    preferred_agent = str(snapshot.get("conductor_agent") or "")
    initiator_agent = str(snapshot.get("initiator_agent") or "")
    candidates.sort(
        key=lambda row: (
            0 if row["identity"].get("agent") == preferred_agent else 1,
            0 if row["identity"].get("agent") == initiator_agent else 1,
            int(row.get("active_leases", 0)),
            str(row["identity"].get("agent") or ""),
            str(row.get("session_id") or ""),
        )
    )
    return AgentIdentityV1.model_validate(candidates[0]["identity"])


def _fanout_authority(snapshot: dict[str, Any]) -> Any:
    repositories = {
        str(packet.get("owner_packet", {}).get("owner_repo") or origin_repo_slug())
        for packet in snapshot.get("planner_packets", []) + snapshot.get("executor_packets", [])
    }
    repositories.discard("")
    return AuthorityEnvelopeV1(
        actions=frozenset({"code", "conduct", "execute", "inspect", "plan", "review"}),
        repositories=frozenset(repositories or {origin_repo_slug()}),
        path_prefixes=frozenset({"*"}),
        may_delegate=True,
    )


def _packet_predicate(packet: dict[str, Any]) -> str:
    predicates = packet.get("verification_predicates") or []
    return str(predicates[0]) if predicates else "python3 -m py_compile scripts/current-session-fanout.py"


def _packet_receipt_target(packet: dict[str, Any]) -> str:
    owner = packet.get("owner_packet") or owner_packet_for_theme(str(packet.get("theme") or ""))
    repo = str(owner.get("owner_repo") or origin_repo_slug())
    ledger = str(owner.get("owner_ledger") or "docs/current-session-fanout.md")
    return f"git:{repo}:{ledger}"


def _work_packet(
    snapshot: dict[str, Any],
    packet: dict[str, Any],
    *,
    initiator: Any,
    conductor: Any,
    authority: Any,
    deadline: dt.datetime,
    parent_run_id: str,
    root_run_id: str,
    depth: int,
    child_count: int,
) -> Any:
    phase = "planner" if packet["packet_type"] == "planner_packet" else "executor"
    task_id = task_seed_id(str(snapshot["session_hash"]), str(packet["id"]))
    repo = str((packet.get("owner_packet") or {}).get("owner_repo") or origin_repo_slug())
    claims = (
        ()
        if phase == "planner"
        else (ResourceClaimV1(key=f"repo/{repo}/write", mode="exclusive"),)
    )
    return WorkPacketV1(
        root_run_id=root_run_id,
        parent_run_id=parent_run_id,
        work_id=task_id,
        work_key=f"current-session-fanout/{snapshot['session_hash']}/{packet['id']}",
        intent={
            "packet_id": packet["id"],
            "packet_type": packet["packet_type"],
            "theme": packet.get("theme"),
            "source_prompt_hashes": packet.get("source_prompt_hashes", []),
            "source_plan_hashes": packet.get("source_plan_hashes", []),
        },
        execution={
            "adapter": "native-conduct",
            "phase": phase,
            "preferred_agent": packet["target_agent"],
            "worktree_slug": packet.get("worktree_slug"),
            "acceptance": packet.get("acceptance", []),
            "executor_criteria": packet.get("executor_criteria", []),
        },
        initiator=initiator,
        conductor=conductor,
        preferred_agent=str(packet["target_agent"]),
        required_capabilities=frozenset({"conduct" if phase == "planner" else "execute"}),
        resource_claims=claims,
        predicate=_packet_predicate(packet),
        receipt_target=_packet_receipt_target(packet),
        authority=authority,
        deadline=deadline,
        spend=SpendEnvelopeV1(limit=max(1, child_count)),
        retry=RetryPolicyV1(max_attempts=1),
        depth=depth,
        fanout=FanoutBoundsV1(max_children=child_count, max_depth=2),
        effect="read" if phase == "planner" else "write",
        task_id=task_id,
    )


def _reserved_result(result: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise FanoutReservationError(f"{label} reservation returned a non-object response")
    status = str(result.get("status") or "")
    if status != "reserved":
        detail = result.get("busy_receipt_id") or result.get("run_id") or status or "unknown"
        raise FanoutReservationError(f"{label} reservation failed closed: {status} ({detail})")
    lease = result.get("lease")
    if (
        not isinstance(lease, dict)
        or not result.get("run_id")
        or not result.get("root_run_id")
        or not result.get("executor_session_id")
        or not result.get("capability_token")
        or not lease.get("lease_id")
        or not lease.get("generation")
        or not isinstance(lease.get("executor"), dict)
    ):
        raise FanoutReservationError(f"{label} reservation omitted required lease identity")
    return result


def _cancel_reservations(client: Any, accepted: list[dict[str, Any]], session_id: str) -> list[str]:
    failures: list[str] = []
    for result in reversed(accepted):
        try:
            client.cancel(str(result["run_id"]), session_id)
        except Exception as exc:  # pragma: no cover - best-effort rollback evidence
            failures.append(f"{result.get('run_id')}: {exc}")
    return failures


def _inject_reservation(
    packet: dict[str, Any],
    work_packet: Any,
    result: dict[str, Any],
    *,
    initiator_agent: str,
    conductor_agent: str,
) -> None:
    lease = result["lease"]
    executor = lease["executor"]
    packet["target_agent"] = str(executor["agent"])
    packet["native_identity"] = str(executor["agent"])
    packet["root_run_id"] = str(result["root_run_id"])
    packet["parent_run_id"] = str(work_packet.parent_run_id)
    packet["run_id"] = str(result["run_id"])
    packet["task_id"] = str(work_packet.task_id)
    packet["execution_hash"] = str(work_packet.execution_hash)
    packet["lease_id"] = str(lease["lease_id"])
    packet["lease_generation"] = int(lease["generation"])
    packet["executor_session_id"] = str(result["executor_session_id"])
    packet["runtime_env"] = child_identity_environment(
        executor_agent=str(executor["agent"]),
        initiator_agent=initiator_agent,
        conductor_agent=conductor_agent,
        root_run_id=str(result["root_run_id"]),
        parent_run_id=str(work_packet.parent_run_id),
        run_id=str(result["run_id"]),
        task_id=str(work_packet.task_id),
        lease_id=str(lease["lease_id"]),
        lease_generation=int(lease["generation"]),
        execution_hash=str(work_packet.execution_hash),
        capability_token=str(result["capability_token"]),
    )
    packet["work_packet"] = work_packet.model_dump(mode="json")
    packet["reservation"] = {
        key: value for key, value in result.items() if key != "capability_token"
    }


def reserve_fanout(snapshot: dict[str, Any], client: Any | None = None) -> dict[str, Any]:
    """Atomically reserve the graph or roll back every accepted not-started lease."""

    if snapshot.get("status") != "ready":
        raise FanoutReservationError("fanout snapshot is not ready for live reservation")
    try:
        if client is None:
            if client_from_env is None:
                raise FanoutReservationError("conduct client is unavailable")
            client = client_from_env()
        conductor = _conductor_identity(client, snapshot)
    except FanoutReservationError:
        raise
    except Exception as exc:
        raise FanoutReservationError(f"conduct broker unavailable during preflight: {exc}") from exc
    initiator = AgentIdentityV1(
        agent=str(snapshot["initiator_agent"]),
        surface="session-corpus",
        session_id=f"source-{snapshot['session_hash']}",
        native_run_id=str(snapshot.get("session_source", {}).get("session_id") or "") or None,
    )
    authority = _fanout_authority(snapshot)
    runway = int(os.environ.get("LIMEN_FANOUT_RUNWAY_SECONDS", "3600"))
    if runway <= 0 or runway > 86400:
        raise FanoutReservationError("LIMEN_FANOUT_RUNWAY_SECONDS must be between 1 and 86400")
    deadline = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=runway)
    planners = list(snapshot.get("planner_packets", []))
    executors = list(snapshot.get("executor_packets", []))
    proposed_parent = {str(packet["run_id"]): packet for packet in planners}
    fallback_planner = planners[0] if planners else None
    children_by_planner: dict[str, list[dict[str, Any]]] = {
        str(packet["id"]): [] for packet in planners
    }
    for packet in executors:
        parent = proposed_parent.get(str(packet.get("parent_run_id"))) or fallback_planner
        if parent is None:
            raise FanoutReservationError("executor packet has no planner parent")
        children_by_planner[str(parent["id"])].append(packet)
    root_budget = sum(
        max(1, len(children_by_planner[str(packet["id"])])) for packet in planners
    )
    root_task_id = f"CSF-{str(snapshot['session_hash'])[:8].upper()}-ROOT"
    root_packet = WorkPacketV1(
        work_id=root_task_id,
        work_key=f"current-session-fanout/{snapshot['session_hash']}/root",
        intent={
            "objective": "reserve current-session peer fanout",
            "session_hash": snapshot["session_hash"],
            "packet_ids": [packet["id"] for packet in planners + executors],
        },
        execution={"adapter": "native-conduct", "phase": "root"},
        initiator=initiator,
        conductor=conductor,
        preferred_agent=conductor.agent,
        required_capabilities=frozenset({"conduct"}),
        predicate="python3 -m py_compile scripts/current-session-fanout.py",
        receipt_target=f"git:{origin_repo_slug()}:docs/current-session-fanout.md",
        authority=authority,
        deadline=deadline,
        spend=SpendEnvelopeV1(limit=max(1, root_budget)),
        retry=RetryPolicyV1(max_attempts=1),
        fanout=FanoutBoundsV1(
            max_children=max(
                len(planners),
                max((len(children) for children in children_by_planner.values()), default=0),
            ),
            max_depth=2,
        ),
        effect="read",
        task_id=root_task_id,
    )
    accepted: list[dict[str, Any]] = []
    planner_reservations: dict[str, tuple[Any, dict[str, Any]]] = {}
    executor_reservations: dict[str, tuple[Any, dict[str, Any]]] = {}
    try:
        root_result = _reserved_result(client.submit(root_packet), label="root")
        accepted.append(root_result)
        actual_root = str(root_result["root_run_id"])
        for packet in planners:
            children = children_by_planner[str(packet["id"])]
            work_packet = _work_packet(
                snapshot,
                packet,
                initiator=initiator,
                conductor=conductor,
                authority=authority,
                deadline=deadline,
                parent_run_id=str(root_result["run_id"]),
                root_run_id=actual_root,
                depth=1,
                child_count=len(children),
            )
            result = _reserved_result(
                client.split(str(root_result["run_id"]), work_packet),
                label=str(packet["id"]),
            )
            accepted.append(result)
            planner_reservations[str(packet["id"])] = (work_packet, result)
        for packet in executors:
            parent = proposed_parent.get(str(packet.get("parent_run_id"))) or fallback_planner
            _, parent_result = planner_reservations[str(parent["id"])]
            work_packet = _work_packet(
                snapshot,
                packet,
                initiator=initiator,
                conductor=conductor,
                authority=authority,
                deadline=deadline,
                parent_run_id=str(parent_result["run_id"]),
                root_run_id=actual_root,
                depth=2,
                child_count=0,
            )
            result = _reserved_result(
                client.split(str(parent_result["run_id"]), work_packet),
                label=str(packet["id"]),
            )
            accepted.append(result)
            executor_reservations[str(packet["id"])] = (work_packet, result)
    except Exception as exc:
        rollback_failures = _cancel_reservations(client, accepted, conductor.session_id)
        suffix = f"; rollback failures: {rollback_failures}" if rollback_failures else ""
        if isinstance(exc, FanoutReservationError):
            raise FanoutReservationError(f"{exc}{suffix}") from exc
        raise FanoutReservationError(f"conduct broker unavailable or rejected fanout: {exc}{suffix}") from exc
    snapshot["root_run_id"] = str(root_result["root_run_id"])
    snapshot["conductor_agent"] = conductor.agent
    for packet in planners:
        work_packet, result = planner_reservations[str(packet["id"])]
        _inject_reservation(
            packet,
            work_packet,
            result,
            initiator_agent=initiator.agent,
            conductor_agent=conductor.agent,
        )
    for packet in executors:
        work_packet, result = executor_reservations[str(packet["id"])]
        _inject_reservation(
            packet,
            work_packet,
            result,
            initiator_agent=initiator.agent,
            conductor_agent=conductor.agent,
        )
    snapshot["conduct"] = {
        "status": "reserved",
        "root": {key: value for key, value in root_result.items() if key != "capability_token"},
        "root_runtime_env": child_identity_environment(
            executor_agent=str(root_result["lease"]["executor"]["agent"]),
            initiator_agent=initiator.agent,
            conductor_agent=conductor.agent,
            root_run_id=str(root_result["root_run_id"]),
            parent_run_id="",
            run_id=str(root_result["run_id"]),
            task_id=root_task_id,
            lease_id=str(root_result["lease"]["lease_id"]),
            lease_generation=int(root_result["lease"]["generation"]),
            execution_hash=str(root_packet.execution_hash),
            capability_token=str(root_result["capability_token"]),
        ),
        "reserved_children": len(planners) + len(executors),
        "root_execution_hash": root_packet.execution_hash,
    }
    return snapshot["conduct"]


def apply_task_seed(snapshot: dict[str, Any], tasks_path: Path) -> dict[str, Any]:
    return {
        "status": "blocked",
        "reason": (
            "direct task-seed activation is retired; reserve the graph with --conduct "
            "and launch only from its leased child envelopes"
        ),
        "appended": 0,
        "skipped": 0,
        "tasks_path": str(tasks_path),
        "mode": "conduct-required",
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
    session: SessionSource,
    min_planners: int,
    planner_lanes: str,
    executor_lanes: str,
    include_contrib: bool,
    no_reset_spend: bool,
    runway: str = DEFAULT_RUNWAY,
) -> str:
    args = [
        "python3",
        "scripts/current-session-fanout.py",
        "--session",
        session.locator,
        "--source-agent",
        session.agent,
        "--min-planners",
        str(min_planners),
        "--planner-lanes",
        planner_lanes,
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
    session: SessionSource,
    args: argparse.Namespace,
    no_reset_spend: bool,
) -> None:
    command = fanout_verification_command(
        session=session,
        min_planners=args.min_planners,
        planner_lanes=args.planner_lanes,
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
    session = find_session(args.session, args.source_agent)
    messages = read_session_messages(session)
    plan_events = read_session_plan_events(session)
    unique_sources = unique_plan_sources(plan_events)
    source_plan_hashes = [str(event["hash"]) for event in unique_sources]
    themes = matched_themes(messages, plan_events)
    rows = lane_rows()
    planner_lanes = lane_selection(args.planner_lanes, rows, capability="conduct")
    executor_lanes = lane_selection(args.executor_lanes, rows, capability="execute")
    conductors = lane_selection(args.conductor_agent, rows, capability="conduct")
    conductor_agent = session.agent if session.agent in conductors else (conductors[0] if conductors else "")
    root_run_id = os.environ.get("LIMEN_ROOT_RUN_ID") or f"fanout-{stable_hash(session.locator, 24)}"
    no_reset_spend = not args.allow_reset_spend
    if packet_contract is None:
        raise ContractError("workstream contract module unavailable")
    workstream = admitted_packet_contract(getattr(args, "runway", DEFAULT_RUNWAY))
    planners = planner_packets(
        themes,
        messages,
        args.min_planners,
        planner_lanes,
        no_reset_spend,
        initiator_agent=session.agent,
        conductor_agent=conductor_agent,
        root_run_id=root_run_id,
        source_plan_hashes=source_plan_hashes,
    )
    planner_packets_by_theme = {str(packet["theme"]): packet for packet in planners}
    executors = executor_packets(
        themes,
        executor_lanes,
        args.include_contrib,
        no_reset_spend,
        initiator_agent=session.agent,
        conductor_agent=conductor_agent,
        root_run_id=root_run_id,
        planner_packets_by_theme=planner_packets_by_theme,
        source_plan_hashes=source_plan_hashes,
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
    global_status = "active" if planners and conductor_agent else "blocked"
    snapshot = {
        "generated_at": now_iso(),
        "session_path": session.locator,
        "session_hash": stable_hash(session.locator, 24),
        "session_source": {
            "agent": session.agent,
            "session_id": session.session_id,
            "format": session.format,
        },
        "initiator_agent": session.agent,
        "conductor_agent": conductor_agent,
        "root_run_id": root_run_id,
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
        "planner_lanes": planner_lanes,
        "executor_lanes": executor_lanes,
        "no_reset_spend": no_reset_spend,
        "workstream_contract": workstream,
        "planner_packets": planners,
        "executor_packets": executors,
        "blocked_local_work": blockers,
        "global_product_selection": {
            "status": global_status,
            "reason": "planner packets remain eligible while local blockers are owner-recorded",
        },
        "status": (
            "ready"
            if messages and planners and conductor_agent and not unconsolidated_plan_hashes
            else "blocked"
        ),
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
        f"Source agent: `{snapshot['initiator_agent']}`",
        f"Conductor agent: `{snapshot['conductor_agent']}`",
        f"Root run: `{snapshot['root_run_id']}`",
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
    if snapshot.get("conduct"):
        conduct = snapshot["conduct"]
        lines += [
            "",
            "## Conduct Reservation",
            "",
            f"Status: `{conduct.get('status')}`",
        ]
        if conduct.get("root"):
            lines.append(f"Root run: `{conduct['root'].get('root_run_id')}`")
            lines.append(f"Reserved children: `{conduct.get('reserved_children', 0)}`")
    lines += [
        "",
        "## Contract",
        "",
        "- Planner and executor lanes are selected from the canonical live capability census.",
        "- Each child receives its native executor identity plus explicit initiator, conductor, and root/parent/run lineage.",
        "- Every packet carries the validated finite runway and no-modal authorization contract.",
        "- Dry-run may render proposed packets; live activation first reserves the root and every child through conduct submit/split.",
        "- Direct task-seed activation is retired; no native child may launch from an unleased dictionary packet.",
        "- This command never applies provider resets, credits, top-ups, or paid overages.",
        "- Outbound identity-bearing actions remain human-gated.",
    ]
    return "\n".join(lines) + "\n"


def write_outputs(snapshot: dict[str, Any], markdown: str) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    DOC_PATH.write_text(markdown, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create current-session planner and executor fanout packets.")
    parser.add_argument("--session", help="native session locator; defaults to the newest supported corpus")
    parser.add_argument(
        "--source-agent",
        default=os.environ.get("LIMEN_SESSION_SOURCE_AGENT", "auto"),
        help="auto or the native corpus owner",
    )
    parser.add_argument(
        "--min-planners",
        type=int,
        default=int(os.environ.get("LIMEN_MIN_PLANNERS", "10")),
    )
    parser.add_argument("--planner-lanes", default=os.environ.get("LIMEN_PLANNER_LANES", "auto"))
    parser.add_argument("--executor-lanes", default=os.environ.get("LIMEN_LANES", "auto"))
    parser.add_argument("--conductor-agent", default=os.environ.get("LIMEN_CONDUCTOR_AGENT", "auto"))
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
    parser.add_argument(
        "--apply-task-seed",
        action="store_true",
        help="retired live path; use --conduct to reserve leased children",
    )
    parser.add_argument("--conduct", action="store_true", help="reserve root and children through the conduct broker")
    parser.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS", str(ROOT / "tasks.yaml")))
    parser.add_argument("--dry-run", action="store_true", help="print only; never write")
    parser.add_argument("--write", action="store_true", help="write packet receipts")
    args = parser.parse_args()
    if args.apply_task_seed and not args.dry_run:
        print(
            "current-session-fanout: direct task-seed activation is retired; use --conduct --write",
            file=sys.stderr,
        )
        return 2
    if args.conduct and not args.dry_run and not args.write:
        print(
            "current-session-fanout: --conduct requires --write so lease tokens have private custody",
            file=sys.stderr,
        )
        return 2
    if args.conduct and args.seed_tasks and not args.dry_run:
        print(
            "current-session-fanout: --seed-tasks is dry-run only and cannot accompany live --conduct",
            file=sys.stderr,
        )
        return 2
    snapshot = build_snapshot(args)
    if args.conduct and args.dry_run:
        snapshot["conduct"] = {"status": "unreserved-dry-run"}
    elif args.conduct:
        try:
            reserve_fanout(snapshot)
        except Exception as exc:
            print(f"current-session-fanout: conduct reservation failed closed: {exc}", file=sys.stderr)
            return 2
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
