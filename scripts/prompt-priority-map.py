#!/usr/bin/env python3
"""Build a redacted priority/task map for the full prompt corpus.

This is the layer above `prompt-lifecycle-ledger.py`: it does not read raw app
session files or prompt text. It consumes existing redacted/private indexes,
scores session receipts and prompt hashes, and writes:

* tracked docs/prompt-priority-map.md: public-safe review batches and routes;
* ignored .limen-private/.../prompt-priority-map.json: complete hash/session map.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
PROMPT_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
CODEX_INDEX = PRIVATE_ROOT / "lifecycle" / "codex-session-lifecycle.json"
ATTACK_INDEX = PRIVATE_ROOT / "lifecycle" / "session-attack-paths.json"
BLOCKER_INDEX = PRIVATE_ROOT / "lifecycle" / "session-lifecycle-blockers.json"
CAPABILITY_INDEX = PRIVATE_ROOT / "lifecycle" / "capability-substrate-index.json"
DOC_PATH = ROOT / "docs" / "prompt-priority-map.md"
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-priority-map.json"

SOURCE_WEIGHTS = {
    "codex-sessions": 8,
    "codex-history": 3,
    "claude-projects": 5,
    "claude-tasks": 4,
    "claude-plans": 2,
    "claude-file-history": 0,
    "codex-attachments": 0,
}

STATE_WEIGHTS = {
    "ALIVE": 18,
    "STALLED": 26,
    "PARKED": -22,
    "CLOSED": -8,
}

PARKED_SECRET_FAMILIES = {"auth_credentials"}


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


def parse_ts(value: Any) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def recency_score(value: Any, now: dt.datetime) -> tuple[int, str]:
    parsed = parse_ts(value)
    if parsed is None:
        return 0, "unknown"
    age = now - parsed
    if age.total_seconds() < 0:
        return 18, "future/clock-skew"
    days = age.total_seconds() / 86400
    if days <= 1:
        return 20, "<=1d"
    if days <= 7:
        return 14, "<=7d"
    if days <= 30:
        return 8, "<=30d"
    if days <= 120:
        return 3, "<=120d"
    return 1, ">120d"


def priority_band(score: int) -> str:
    if score >= 90:
        return "critical"
    if score >= 70:
        return "high"
    if score >= 50:
        return "medium"
    if score >= 30:
        return "low"
    return "parked"


def band_rank(band: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3, "parked": 4}.get(band, 5)


def compact_counts(counter: Counter[str], *, limit: int = 5) -> dict[str, int]:
    return dict(counter.most_common(limit))


def public_counts(counter: Counter[str], *, limit: int = 3) -> str:
    bits = [f"`{key}` {value}" for key, value in counter.most_common(limit)]
    return ", ".join(bits) if bits else "none"


def codex_lookups(codex: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_key = {}
    by_session_hash = {}
    by_path = {}
    for session in codex.get("sessions") or []:
        if not isinstance(session, dict):
            continue
        key = session.get("session_key")
        if key:
            by_key[str(key)] = session
        session_id_hash = session.get("session_id_hash")
        if session_id_hash:
            by_session_hash[str(session_id_hash)] = session
        path = session.get("path")
        if path:
            by_path[str(path)] = session
    return by_key, by_session_hash, by_path


def codex_meta_for_session(
    session: dict[str, Any],
    by_key: dict[str, dict[str, Any]],
    by_session_hash: dict[str, dict[str, Any]],
    by_path: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    session_key = str(session.get("session_key") or "")
    if session_key in by_key:
        return by_key[session_key]
    session_id_hash = str(session.get("session_id_hash") or "")
    if session_id_hash:
        for codex_hash, meta in by_session_hash.items():
            if codex_hash.startswith(session_id_hash) or session_id_hash.startswith(codex_hash):
                return meta
    path = str(session.get("path") or "")
    return by_path.get(path, {})


def attack_lookups(attack: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    worktrees = {}
    families = {}
    for path in attack.get("ranked_paths") or []:
        if not isinstance(path, dict):
            continue
        kind = path.get("kind")
        path_id = path.get("id")
        if not path_id:
            continue
        if kind == "worktree":
            worktrees[str(path_id)] = path
        elif kind == "family":
            families[str(path_id)] = path
    return worktrees, families


def lane_for_session(
    session: dict[str, Any],
    codex_meta: dict[str, Any],
    worktree_path: dict[str, Any] | None,
    family_path: dict[str, Any] | None,
) -> str:
    family = str(codex_meta.get("family") or "uncategorized")
    state = str(codex_meta.get("state") or "")
    if family in PARKED_SECRET_FAMILIES:
        return "parked-secret"
    if worktree_path:
        return str(worktree_path.get("lane") or "worktree-review")
    if family == "uncategorized" and session.get("worktree_slug"):
        return "historical-worktree-review"
    if state == "STALLED":
        return "stalled-review"
    if family_path:
        return str(family_path.get("lane") or "family-review")
    if str(session.get("source") or "").startswith("claude"):
        return "legacy-session-review"
    return "hash-review"


def next_action_for_session(
    session: dict[str, Any],
    codex_meta: dict[str, Any],
    worktree_path: dict[str, Any] | None,
    family_path: dict[str, Any] | None,
    lane: str,
) -> str:
    family = str(codex_meta.get("family") or "uncategorized")
    if family in PARKED_SECRET_FAMILIES:
        return "Keep parked unless a scoped account/setup task directly requires non-secret prep."
    if worktree_path and worktree_path.get("next_action"):
        return str(worktree_path["next_action"])
    if family_path and family_path.get("next_action"):
        return str(family_path["next_action"])
    if lane == "stalled-review":
        return "Privately inspect the session receipt, then promote a task packet or write a blocker receipt."
    if lane == "historical-worktree-review":
        return "Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof."
    if lane == "legacy-session-review":
        return "Sample the private source file, extract durable atoms, then route to an owner ledger."
    source = str(session.get("source") or "unknown")
    return f"Review the redacted `{source}` receipt privately and assign an owner route before delegation."


def score_session(
    session: dict[str, Any],
    codex_meta: dict[str, Any],
    worktree_path: dict[str, Any] | None,
    family_path: dict[str, Any] | None,
    now: dt.datetime,
) -> tuple[int, str]:
    prompt_hashes = [str(value) for value in session.get("prompt_hashes") or [] if value]
    prompt_events = int(session.get("prompt_event_count") or len(prompt_hashes))
    unique_prompts = len(set(prompt_hashes))
    duplicate_events = max(0, prompt_events - unique_prompts)
    source = str(session.get("source") or "unknown")
    family = str(codex_meta.get("family") or "uncategorized")
    state = str(codex_meta.get("state") or "")
    score = 10
    score += SOURCE_WEIGHTS.get(source, 1)
    score += min(20, prompt_events // 5)
    score += min(14, unique_prompts // 5)
    score += min(10, int(session.get("prompt_bytes") or 0) // 50000)
    score += min(10, duplicate_events // 3)
    recent_score, recent_label = recency_score(
        session.get("last_event") or session.get("mtime") or codex_meta.get("mtime"),
        now,
    )
    score += recent_score
    score += STATE_WEIGHTS.get(state, 0)
    if worktree_path:
        score += int(int(worktree_path.get("score") or 0) * 0.45)
        lane = str(worktree_path.get("lane") or "")
        if lane == "documented-residue":
            score -= 35
        elif lane == "observe":
            score -= 18
        elif lane == "owner-blocker":
            score += 8
    elif family_path:
        score += int(int(family_path.get("score") or 0) * 0.40)
    if session.get("worktree_slug"):
        score += 10
    if state == "STALLED":
        score += 8
    if family == "uncategorized":
        score += 12
    if family in PARKED_SECRET_FAMILIES:
        score -= 45
    return score, recent_label


def build_session_items(
    prompt: dict[str, Any],
    codex: dict[str, Any],
    attack: dict[str, Any],
    now: dt.datetime,
) -> list[dict[str, Any]]:
    codex_by_key, codex_by_session_hash, codex_by_path = codex_lookups(codex)
    worktree_paths, family_paths = attack_lookups(attack)
    items = []
    for session in prompt.get("sessions") or []:
        if not isinstance(session, dict):
            continue
        prompt_hashes = [str(value) for value in session.get("prompt_hashes") or [] if value]
        prompt_events = int(session.get("prompt_event_count") or len(prompt_hashes))
        if prompt_events <= 0:
            continue
        session_key = str(session.get("session_key") or "")
        codex_meta = codex_meta_for_session(session, codex_by_key, codex_by_session_hash, codex_by_path)
        worktree_slug = str(session.get("worktree_slug") or "")
        family = str(codex_meta.get("family") or "uncategorized")
        worktree_path = worktree_paths.get(worktree_slug) if worktree_slug else None
        family_path = family_paths.get(family) if family != "uncategorized" else None
        score, recency = score_session(session, codex_meta, worktree_path, family_path, now)
        lane = lane_for_session(session, codex_meta, worktree_path, family_path)
        if lane == "parked-secret":
            score = min(score, 29)
        item = {
            "session_key": session_key,
            "session_id_hash": session.get("session_id_hash"),
            "source": session.get("source") or "unknown",
            "family": family,
            "state": codex_meta.get("state") or "unclassified",
            "owner": codex_meta.get("owner") or "unassigned",
            "route": codex_meta.get("route") or "",
            "worktree_slug": worktree_slug or None,
            "cwd_hash": session.get("cwd_hash") or codex_meta.get("cwd_hash"),
            "score": score,
            "band": priority_band(score),
            "lane": lane,
            "recency": recency,
            "prompt_events": prompt_events,
            "unique_prompt_hashes": len(set(prompt_hashes)),
            "duplicate_prompt_events": max(0, prompt_events - len(set(prompt_hashes))),
            "event_count": int(session.get("event_count") or 0),
            "prompt_bytes": int(session.get("prompt_bytes") or 0),
            "first_event": session.get("first_event") or codex_meta.get("first_event"),
            "last_event": session.get("last_event") or codex_meta.get("last_event") or session.get("mtime"),
            "first_prompt_hash": session.get("first_prompt_hash"),
            "last_prompt_hash": session.get("last_prompt_hash"),
            "prompt_hashes": prompt_hashes,
            "next_action": next_action_for_session(session, codex_meta, worktree_path, family_path, lane),
            "attack_path": {
                "kind": (worktree_path or family_path or {}).get("kind"),
                "id": (worktree_path or family_path or {}).get("id"),
                "score": (worktree_path or family_path or {}).get("score"),
            },
            "private_source_path": session.get("path"),
            "private_display_path": session.get("display_path"),
        }
        items.append(item)
    return sorted(
        items,
        key=lambda item: (
            band_rank(str(item["band"])),
            -int(item["score"]),
            str(item["lane"]),
            str(item["session_key"]),
        ),
    )


def build_prompt_units(session_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    units: dict[str, dict[str, Any]] = {}
    for session in session_items:
        seen_in_session = set()
        for prompt_hash in session["prompt_hashes"]:
            item = units.setdefault(
                prompt_hash,
                {
                    "prompt_hash": prompt_hash,
                    "occurrences": 0,
                    "session_keys": set(),
                    "sources": Counter(),
                    "families": Counter(),
                    "lanes": Counter(),
                    "bands": Counter(),
                    "worktrees": Counter(),
                    "max_score": int(session["score"]),
                    "representative_session_key": session["session_key"],
                    "latest_event": session.get("last_event"),
                },
            )
            item["occurrences"] += 1
            item["session_keys"].add(session["session_key"])
            item["sources"][str(session["source"])] += 1
            item["families"][str(session["family"])] += 1
            item["lanes"][str(session["lane"])] += 1
            item["bands"][str(session["band"])] += 1
            if session.get("worktree_slug"):
                item["worktrees"][str(session["worktree_slug"])] += 1
            if int(session["score"]) > int(item["max_score"]):
                item["max_score"] = int(session["score"])
                item["representative_session_key"] = session["session_key"]
            if (
                session.get("last_event")
                and (not item.get("latest_event") or str(session["last_event"]) > str(item["latest_event"]))
            ):
                item["latest_event"] = session["last_event"]
            seen_in_session.add(prompt_hash)
        for prompt_hash in seen_in_session:
            units[prompt_hash]["session_count"] = len(units[prompt_hash]["session_keys"])
    rows = []
    for item in units.values():
        rows.append(
            {
                "prompt_hash": item["prompt_hash"],
                "occurrences": item["occurrences"],
                "session_count": len(item["session_keys"]),
                "session_keys": sorted(item["session_keys"]),
                "sources": dict(item["sources"].most_common()),
                "families": dict(item["families"].most_common()),
                "lanes": dict(item["lanes"].most_common()),
                "bands": dict(item["bands"].most_common()),
                "worktrees": dict(item["worktrees"].most_common()),
                "max_score": item["max_score"],
                "representative_session_key": item["representative_session_key"],
                "latest_event": item.get("latest_event"),
            }
        )
    return sorted(rows, key=lambda row: (-int(row["max_score"]), -int(row["occurrences"]), row["prompt_hash"]))


def build_review_batches(session_items: list[dict[str, Any]], *, batch_size: int) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in session_items:
        grouped[(str(item["band"]), str(item["lane"]))].append(item)

    batches = []
    for (band, lane), rows in grouped.items():
        rows = sorted(rows, key=lambda item: (-int(item["score"]), str(item["session_key"])))
        for index in range(0, len(rows), batch_size):
            chunk = rows[index : index + batch_size]
            prompt_hashes = {h for item in chunk for h in item["prompt_hashes"]}
            source_counts = Counter(str(item["source"]) for item in chunk)
            family_counts = Counter(str(item["family"]) for item in chunk)
            worktree_counts = Counter(str(item["worktree_slug"]) for item in chunk if item.get("worktree_slug"))
            batch_number = index // batch_size + 1
            scores = [int(item["score"]) for item in chunk]
            top = chunk[0]
            batches.append(
                {
                    "id": f"prompt-batch-{band}-{lane}-{batch_number:03d}",
                    "band": band,
                    "lane": lane,
                    "session_count": len(chunk),
                    "prompt_events": sum(int(item["prompt_events"]) for item in chunk),
                    "unique_prompt_hashes": len(prompt_hashes),
                    "max_score": max(scores),
                    "avg_score": round(sum(scores) / len(scores), 1),
                    "sources": compact_counts(source_counts),
                    "families": compact_counts(family_counts),
                    "worktrees": compact_counts(worktree_counts),
                    "top_session_key": top["session_key"],
                    "next_action": top["next_action"],
                    "session_keys": [item["session_key"] for item in chunk],
                    "prompt_hashes": sorted(prompt_hashes),
                }
            )
    return sorted(
        batches,
        key=lambda item: (
            band_rank(str(item["band"])),
            -int(item["max_score"]),
            -int(item["prompt_events"]),
            str(item["lane"]),
            str(item["id"]),
        ),
    )


def lane_task_map(session_items: list[dict[str, Any]], batches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_lane: dict[str, list[dict[str, Any]]] = defaultdict(list)
    batch_counts = Counter(str(batch["lane"]) for batch in batches)
    for item in session_items:
        by_lane[str(item["lane"])].append(item)
    rows = []
    for lane, items in by_lane.items():
        sorted_items = sorted(items, key=lambda item: (-int(item["score"]), str(item["session_key"])))
        top = sorted_items[0]
        rows.append(
            {
                "lane": lane,
                "sessions": len(items),
                "prompt_events": sum(int(item["prompt_events"]) for item in items),
                "batches": int(batch_counts.get(lane, 0)),
                "top_band": top["band"],
                "top_score": int(top["score"]),
                "dominant_family": Counter(str(item["family"]) for item in items).most_common(1)[0][0],
                "dominant_source": Counter(str(item["source"]) for item in items).most_common(1)[0][0],
                "route": top["next_action"],
            }
        )
    return sorted(rows, key=lambda item: (band_rank(str(item["top_band"])), -int(item["top_score"]), item["lane"]))


def build_snapshot(batch_size: int) -> dict[str, Any]:
    prompt = load_json(PROMPT_INDEX)
    codex = load_json(CODEX_INDEX)
    attack = load_json(ATTACK_INDEX)
    blockers = load_json(BLOCKER_INDEX)
    capability = load_json(CAPABILITY_INDEX)
    now = dt.datetime.now(dt.timezone.utc)
    session_items = build_session_items(prompt, codex, attack, now)
    prompt_units = build_prompt_units(session_items)
    batches = build_review_batches(session_items, batch_size=max(1, batch_size))
    lane_map = lane_task_map(session_items, batches)
    source_counts = Counter(str(item["source"]) for item in session_items)
    family_counts = Counter(str(item["family"]) for item in session_items)
    lane_counts = Counter(str(item["lane"]) for item in session_items)
    band_counts = Counter(str(item["band"]) for item in session_items)
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "inputs": {
            "prompt_lifecycle_index": {"path": str(PROMPT_INDEX), "present": bool(prompt)},
            "codex_session_lifecycle": {"path": str(CODEX_INDEX), "present": bool(codex)},
            "session_attack_paths": {"path": str(ATTACK_INDEX), "present": bool(attack)},
            "session_lifecycle_blockers": {"path": str(BLOCKER_INDEX), "present": bool(blockers)},
            "capability_substrate": {"path": str(CAPABILITY_INDEX), "present": bool(capability)},
        },
        "coverage": {
            "prompt_index_files": sum(int(s.get("files", 0)) for s in prompt.get("sources", []) if isinstance(s, dict)),
            "prompt_index_events": sum(
                int(s.get("prompt_events", 0)) for s in prompt.get("sources", []) if isinstance(s, dict)
            ),
            "prioritized_sessions": len(session_items),
            "prioritized_prompt_events": sum(int(item["prompt_events"]) for item in session_items),
            "unique_prompt_hashes": len(prompt_units),
            "review_batches": len(batches),
            "codex_classified_sessions": codex.get("session_count", 0),
            "attack_paths": len(attack.get("ranked_paths") or []),
            "blockers": len(blockers.get("blockers") or []),
            "capability_activation_items": len(capability.get("activation_queue") or []),
        },
        "counts": {
            "sources": dict(source_counts.most_common()),
            "families": dict(family_counts.most_common()),
            "lanes": dict(lane_counts.most_common()),
            "bands": dict(band_counts.most_common()),
        },
        "lane_task_map": lane_map,
        "review_batches": batches,
        "session_items": session_items,
        "prompt_units": prompt_units,
        "private_index": str(PRIVATE_INDEX),
    }


def render_markdown(snapshot: dict[str, Any], *, limit: int) -> str:
    coverage = snapshot["coverage"]
    counts = snapshot["counts"]
    batches = snapshot["review_batches"][:limit]
    sessions = snapshot["session_items"][:limit]
    lines = [
        "# Prompt Priority Map",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        "",
        "## Canonical Decision",
        "",
        "- The long-running unit is a review batch, not a chat-length mega-prompt.",
        "- Every prompt-like event is represented by a hash in the private map; tracked docs show only counts, session keys, lanes, and routes.",
        "- A batch becomes dispatchable only after it has an owner repo or owner ledger, bounded next action, no raw-secret dependency, and a verification or blocker receipt.",
        "- Credential/auth/secret lanes stay parked unless a scoped task directly requires non-secret preparation.",
        "",
        "## Coverage",
        "",
        f"- Prompt lifecycle source files: `{coverage.get('prompt_index_files', 0)}`.",
        f"- Prompt-like events from source ledger: `{coverage.get('prompt_index_events', 0)}`.",
        f"- Prioritized session receipts: `{coverage.get('prioritized_sessions', 0)}`.",
        f"- Prioritized prompt events: `{coverage.get('prioritized_prompt_events', 0)}`.",
        f"- Unique prompt hashes: `{coverage.get('unique_prompt_hashes', 0)}`.",
        f"- Review batches: `{coverage.get('review_batches', 0)}`.",
        f"- Codex classified sessions: `{coverage.get('codex_classified_sessions', 0)}`.",
        f"- Attack paths / blockers / capability items: `{coverage.get('attack_paths', 0)}` / `{coverage.get('blockers', 0)}` / `{coverage.get('capability_activation_items', 0)}`.",
        f"- Source mix: {public_counts(Counter(counts.get('sources') or {}))}.",
        f"- Band mix: {public_counts(Counter(counts.get('bands') or {}), limit=5)}.",
        f"- Lane mix: {public_counts(Counter(counts.get('lanes') or {}), limit=6)}.",
        "",
        "## Priority Model",
        "",
        "- Highest: stalled or active receipts tied to high-ranked attack paths, worktree preservation risk, repeated prompt hashes, and recent activity.",
        "- Middle: legacy Claude/Codex sessions that need private sampling and owner-ledger promotion.",
        "- Lowest: closed, already-parked, or credential/auth work unless directly blocking a selected path.",
        "- The private JSON keeps the complete sorted hash/session map; this Markdown intentionally shows a bounded operator slice.",
        "",
        "## Review Batches",
        "",
        "| Rank | Batch | Band | Lane | Sessions | Prompt Events | Unique Prompts | Dominant Mix | Route |",
        "|---:|---|---|---|---:|---:|---:|---|---|",
    ]
    for rank, batch in enumerate(batches, start=1):
        source_bits = ", ".join(f"{key} {value}" for key, value in batch["sources"].items()) or "none"
        family_bits = ", ".join(f"{key} {value}" for key, value in batch["families"].items()) or "none"
        lines.append(
            f"| {rank} | `{batch['id']}` | `{batch['band']}` | `{batch['lane']}` | "
            f"{batch['session_count']} | {batch['prompt_events']} | {batch['unique_prompt_hashes']} | "
            f"sources {source_bits}; families {family_bits} | {batch['next_action']} |"
        )
    if not batches:
        lines.append("| 0 | none | n/a | n/a | 0 | 0 | 0 | none | n/a |")

    lines += [
        "",
        "## Top Session Receipts",
        "",
        "| Rank | Session Key | Band | Lane | Score | Source | Family / State | Worktree | Prompt Events | Next Action |",
        "|---:|---|---|---|---:|---|---|---|---:|---|",
    ]
    for rank, session in enumerate(sessions, start=1):
        worktree = session.get("worktree_slug") or "none"
        lines.append(
            f"| {rank} | `{session['session_key']}` | `{session['band']}` | `{session['lane']}` | "
            f"{session['score']} | `{session['source']}` | `{session['family']}` / `{session['state']}` | "
            f"`{worktree}` | {session['prompt_events']} | {session['next_action']} |"
        )
    if not sessions:
        lines.append("| 0 | none | n/a | n/a | 0 | n/a | n/a | n/a | 0 | n/a |")

    lines += [
        "",
        "## Lane Task Map",
        "",
        "| Lane | Top Band | Sessions | Prompt Events | Batches | Dominant Source | Dominant Family | Route |",
        "|---|---|---:|---:|---:|---|---|---|",
    ]
    for lane in snapshot["lane_task_map"]:
        lines.append(
            f"| `{lane['lane']}` | `{lane['top_band']}` | {lane['sessions']} | {lane['prompt_events']} | "
            f"{lane['batches']} | `{lane['dominant_source']}` | `{lane['dominant_family']}` | {lane['route']} |"
        )
    if not snapshot["lane_task_map"]:
        lines.append("| none | n/a | 0 | 0 | 0 | n/a | n/a | n/a |")

    lines += [
        "",
        "## Private Output",
        "",
        f"- Prompt priority private map: `{relpath(PRIVATE_INDEX)}`.",
        "- The private map contains prompt hashes, session keys, source paths, lanes, scores, and batch membership; it contains no prompt text.",
        "",
        "## Commands",
        "",
        "- Refresh prerequisites: `python3 scripts/prompt-lifecycle-ledger.py --write --all && python3 scripts/session-attack-paths.py --write`",
        "- Refresh this priority map: `python3 scripts/prompt-priority-map.py --write`",
        "- Refresh prompt batch review ledger: `python3 scripts/prompt-batch-review-ledger.py --write`",
        "- Show a wider tracked slice: `python3 scripts/prompt-priority-map.py --write --limit 60`",
        "",
    ]
    return "\n".join(lines)


def write_outputs(snapshot: dict[str, Any], markdown: str) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(markdown, encoding="utf-8")
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a redacted prompt priority/task map.")
    parser.add_argument("--write", action="store_true", help="write docs and ignored private index")
    parser.add_argument("--limit", type=int, default=30, help="batches and sessions to show in tracked docs")
    parser.add_argument("--batch-size", type=int, default=25, help="session receipts per review batch")
    args = parser.parse_args()

    snapshot = build_snapshot(batch_size=max(1, args.batch_size))
    markdown = render_markdown(snapshot, limit=max(1, args.limit))
    if args.write:
        write_outputs(snapshot, markdown)
    else:
        print(markdown)
    msg = (
        "prompt-priority-map: "
        f"{snapshot['coverage']['prioritized_prompt_events']} prompt events, "
        f"{snapshot['coverage']['unique_prompt_hashes']} unique hashes, "
        f"{snapshot['coverage']['review_batches']} batches"
    )
    if args.write:
        msg += f"; wrote {DOC_PATH}"
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
