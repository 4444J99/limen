#!/usr/bin/env python3
"""Build the Corpus Command Center snapshots.

The command center sits above the existing prompt lifecycle ledgers. It indexes
all extractable corpus units it can reach from local session stores, tracked task
state, tracked docs, the Aug-1 gate, and inbound positioning surfaces.

Tracked/public output is redacted. Raw bodies are written only to the ignored
private object store and referenced by content hash.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
LIFECYCLE_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
PRIORITY_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-priority-map.json"
ATTACK_INDEX = PRIVATE_ROOT / "lifecycle" / "session-attack-paths.json"
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "corpus-command-center.private.json"
PUBLIC_INDEX = PRIVATE_ROOT / "lifecycle" / "corpus-command-center.public.json"
PRIVATE_HTML = PRIVATE_ROOT / "lifecycle" / "corpus-command-center.private.html"
BODY_OBJECT_ROOT = PRIVATE_ROOT / "corpus-command-center" / "objects"
DOC_PATH = ROOT / "docs" / "corpus-command-center.md"
TASKS_PATH = ROOT / "tasks.yaml"
AUG1_VIEW_PATH = ROOT / "logs" / "aug1-view.json"
VALUE_REPOS_PATH = ROOT / "value-repos.json"
POSITIONING_SEEDS_PATH = ROOT / "positioning-seeds.json"
POSITIONING_DIR = ROOT / "docs" / "positioning"
_MAX_SESSIONS_RAW = os.environ.get("LIMEN_CORPUS_MAX_SESSIONS", "").strip()
DEFAULT_MAX_SESSIONS = int(_MAX_SESSIONS_RAW) if _MAX_SESSIONS_RAW else None
PUBLIC_UNIT_LIMIT = int(os.environ.get("LIMEN_CORPUS_PUBLIC_UNIT_LIMIT", "2000"))

STOP_WORDS = {
    "about",
    "after",
    "again",
    "against",
    "also",
    "because",
    "before",
    "being",
    "between",
    "could",
    "every",
    "from",
    "have",
    "into",
    "just",
    "more",
    "need",
    "other",
    "over",
    "same",
    "should",
    "some",
    "than",
    "that",
    "their",
    "there",
    "these",
    "thing",
    "this",
    "through",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "work",
    "would",
    "your",
}
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_-]{2,}", re.IGNORECASE)


def stable_hash(text: str, length: int = 20) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:length]


def full_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return default


def rel_to_private(path: Path) -> str:
    try:
        return str(path.relative_to(PRIVATE_ROOT))
    except ValueError:
        return str(path)


def rel_to_root(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


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
        for key in ("text", "content", "message", "input", "output", "summary", "lastPrompt"):
            if key in value:
                out.extend(text_from_content(value[key]))
        return out
    return []


def read_json_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if path.suffix == ".jsonl" or path.name.endswith(".jsonl") or path.name == "history.jsonl":
        try:
            with path.open(encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(obj, dict):
                        records.append(obj)
        except OSError:
            pass
        return records
    if path.suffix == ".json":
        try:
            obj = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            return []
        if isinstance(obj, dict):
            return [obj]
        if isinstance(obj, list):
            return [item for item in obj if isinstance(item, dict)]
    return []


def tokens(text: str) -> list[str]:
    return [
        token.lower()
        for token in TOKEN_RE.findall(text)
        if len(token) >= 4 and token.lower() not in STOP_WORDS and not token.isdigit()
    ]


def atomize(text: str, *, limit: int = 18) -> list[str]:
    toks = tokens(text)
    counts = Counter(toks)
    bigrams = Counter(
        f"{a} {b}"
        for a, b in zip(toks, toks[1:])
        if a not in STOP_WORDS and b not in STOP_WORDS and a != b
    )
    atoms = [item for item, _ in counts.most_common(limit)]
    for item, _ in bigrams.most_common(max(4, limit // 3)):
        if item not in atoms:
            atoms.append(item)
    return atoms[:limit]


def signature(text: str) -> str:
    toks = tokens(text)
    if not toks:
        return "empty"
    counts = Counter(toks)
    top = sorted(token for token, _ in counts.most_common(12))
    return stable_hash(" ".join(top), 16)


def event_timestamp(obj: dict[str, Any]) -> str | None:
    for key in ("timestamp", "ts", "created_at", "updated_at"):
        if obj.get(key):
            return str(obj[key])
    payload = obj.get("payload")
    if isinstance(payload, dict):
        for key in ("timestamp", "started_at"):
            if payload.get(key):
                return str(payload[key])
    return None


def extracted_texts(source: str, obj: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Return (kind, role, text) triples from known local transcript shapes."""
    payload = obj.get("payload")
    if isinstance(payload, dict):
        ptype = payload.get("type")
        role = str(payload.get("role") or "")
        if ptype == "user_message":
            return [("prompt", "user", text) for text in text_from_content(payload.get("message")) + text_from_content(payload.get("text_elements"))]
        if ptype == "agent_message":
            return [("response", "assistant", text) for text in text_from_content(payload.get("message")) + text_from_content(payload.get("text_elements"))]
        if ptype == "message":
            kind = "prompt" if role == "user" else "response" if role == "assistant" else "system"
            return [(kind, role or "unknown", text) for text in text_from_content(payload.get("content"))]
        if ptype in {"function_call", "function_call_output"}:
            bits = text_from_content(payload.get("arguments")) + text_from_content(payload.get("output"))
            if payload.get("name"):
                bits.insert(0, str(payload["name"]))
            return [("tool", "tool", text) for text in bits]

    if source == "codex-history":
        return [("prompt", "user", text) for text in text_from_content(obj.get("text"))]

    typ = str(obj.get("type") or "")
    if source.startswith("claude"):
        if typ == "user":
            return [("prompt", "user", text) for text in text_from_content(obj.get("message"))]
        if typ == "assistant":
            return [("response", "assistant", text) for text in text_from_content(obj.get("message"))]
        if typ == "last-prompt":
            return [("prompt", "user", text) for text in text_from_content(obj.get("lastPrompt"))]
        if typ == "queue-operation" and obj.get("operation") == "enqueue":
            return [("prompt", "user", text) for text in text_from_content(obj.get("content"))]
        if typ == "attachment":
            return [("artifact", "attachment", text) for text in text_from_content(obj.get("attachment"))]

    message = obj.get("message")
    if isinstance(message, dict):
        role = str(message.get("role") or obj.get("role") or "unknown")
        kind = "prompt" if role == "user" else "response" if role == "assistant" else "message"
        return [(kind, role, text) for text in text_from_content(message)]
    return []


def write_body_object(body: str) -> str | None:
    if not body.strip():
        return None
    digest = full_hash(body)
    dest = BODY_OBJECT_ROOT / digest[:2] / f"{digest}.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.write_text(body, encoding="utf-8")
    return rel_to_private(dest)


def priority_lookups(priority: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    sessions = {}
    prompt_hash_to_cluster = {}
    for item in priority.get("session_items") or []:
        if isinstance(item, dict) and item.get("session_key"):
            sessions[str(item["session_key"])] = item
    for unit in priority.get("prompt_units") or []:
        if isinstance(unit, dict) and unit.get("prompt_hash"):
            prompt_hash_to_cluster[str(unit["prompt_hash"])] = f"prompt-{stable_hash(str(unit['prompt_hash']), 12)}"
    return sessions, prompt_hash_to_cluster


def build_session_units(
    lifecycle: dict[str, Any],
    priority: dict[str, Any],
    *,
    write_objects: bool,
    max_sessions: int | None,
) -> list[dict[str, Any]]:
    priority_sessions, prompt_clusters = priority_lookups(priority)
    units: list[dict[str, Any]] = []
    sessions = [item for item in lifecycle.get("sessions") or [] if isinstance(item, dict)]
    if max_sessions is not None:
        sessions = sessions[: max(0, max_sessions)]
    for session in sessions:
        source = str(session.get("source") or "unknown")
        session_key = str(session.get("session_key") or stable_hash(str(session.get("path") or "")))
        path = Path(str(session.get("path") or ""))
        records = read_json_records(path)
        priority_item = priority_sessions.get(session_key, {})
        lane_id = str(priority_item.get("lane") or "unrouted")
        worktree = session.get("worktree_slug") or priority_item.get("worktree_slug")
        previous_prompt_id: str | None = None
        for index, obj in enumerate(records):
            event_at = event_timestamp(obj) or session.get("mtime")
            for ordinal, (kind, role, body) in enumerate(extracted_texts(source, obj)):
                body = body.strip()
                if not body:
                    continue
                body_hash = full_hash(body)
                cluster_id = prompt_clusters.get(body_hash) or f"{kind}-{signature(body)}"
                unit_id = stable_hash(f"{session_key}:{index}:{ordinal}:{kind}:{role}:{body_hash}", 24)
                body_object = write_body_object(body) if write_objects else None
                parent_id = previous_prompt_id if kind == "response" else None
                if kind == "prompt":
                    previous_prompt_id = unit_id
                atoms = atomize(body)
                units.append(
                    {
                        "unit_id": unit_id,
                        "kind": kind,
                        "role": role,
                        "source": source,
                        "session_key": session_key,
                        "session_id_hash": session.get("session_id_hash"),
                        "event_at": event_at,
                        "hash": body_hash,
                        "signature": signature(body),
                        "cluster_id": cluster_id,
                        "parent_id": parent_id,
                        "lane_id": lane_id,
                        "worktree_slug": worktree,
                        "body_chars": len(body),
                        "body_words": len(body.split()),
                        "body_object": body_object,
                        "body_preview": body[:600],
                        "private_source_path": str(path),
                        "private_display_path": session.get("display_path"),
                        "atoms": atoms,
                        "atom_ids": [stable_hash(atom, 16) for atom in atoms],
                    }
                )
    return units


def load_tasks() -> dict[str, Any]:
    try:
        data = yaml.safe_load(TASKS_PATH.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {"tasks": []}
    return data if isinstance(data, dict) else {"tasks": []}


def build_task_units(*, write_objects: bool) -> list[dict[str, Any]]:
    data = load_tasks()
    units = []
    for task in data.get("tasks") or []:
        if not isinstance(task, dict) or not task.get("id"):
            continue
        body = "\n\n".join(
            str(task.get(key) or "")
            for key in ("title", "context")
            if str(task.get(key) or "").strip()
        ).strip()
        if not body:
            body = str(task["id"])
        body_hash = full_hash(body)
        unit_id = stable_hash(f"task:{task['id']}:{body_hash}", 24)
        atoms = atomize(body)
        units.append(
            {
                "unit_id": unit_id,
                "kind": "task",
                "role": "ledger",
                "source": "tasks.yaml",
                "session_key": None,
                "event_at": task.get("updated") or task.get("created"),
                "hash": body_hash,
                "signature": signature(body),
                "cluster_id": f"task-{signature(body)}",
                "parent_id": None,
                "lane_id": str(task.get("status") or "unknown"),
                "worktree_slug": None,
                "repo": task.get("repo"),
                "task_id": task.get("id"),
                "task_status": task.get("status"),
                "task_priority": task.get("priority"),
                "body_chars": len(body),
                "body_words": len(body.split()),
                "body_object": write_body_object(body) if write_objects else None,
                "body_preview": body[:600],
                "private_source_path": str(TASKS_PATH),
                "private_display_path": "tasks.yaml",
                "atoms": atoms,
                "atom_ids": [stable_hash(atom, 16) for atom in atoms],
            }
        )
    return units


def doc_candidates() -> list[Path]:
    explicit = [
        DOC_PATH,
        ROOT / "docs" / "prompt-lifecycle-ledger.md",
        ROOT / "docs" / "prompt-priority-map.md",
        ROOT / "docs" / "prompt-packet-ledger.md",
        ROOT / "docs" / "AUG1-10K-GATE.md",
        ROOT / "docs" / "inbound-magnet-system.md",
        POSITIONING_DIR / "public-record-data-scrapper.md",
        POSITIONING_DIR / "_frontdoor.md",
        POSITIONING_DIR / "_discoverability.md",
    ]
    generated = sorted(POSITIONING_DIR.glob("*.md")) if POSITIONING_DIR.exists() else []
    paths = []
    seen = set()
    for path in explicit + generated:
        if path.exists() and path not in seen and ".internal" not in path.name:
            paths.append(path)
            seen.add(path)
    return paths


def build_doc_units(*, write_objects: bool) -> list[dict[str, Any]]:
    units = []
    for path in doc_candidates():
        try:
            body = path.read_text(encoding="utf-8", errors="replace")
            stat = path.stat()
        except OSError:
            continue
        body_hash = full_hash(body)
        try:
            display = str(path.relative_to(ROOT))
        except ValueError:
            display = str(path)
        atoms = atomize(body)
        units.append(
            {
                "unit_id": stable_hash(f"doc:{display}:{body_hash}", 24),
                "kind": "artifact",
                "role": "doc",
                "source": "repo-docs",
                "session_key": None,
                "event_at": dt.datetime.fromtimestamp(stat.st_mtime, tz=dt.timezone.utc).isoformat(timespec="seconds"),
                "hash": body_hash,
                "signature": signature(body),
                "cluster_id": f"doc-{signature(body)}",
                "parent_id": None,
                "lane_id": "artifact-ledger",
                "worktree_slug": None,
                "artifact_path": display,
                "body_chars": len(body),
                "body_words": len(body.split()),
                "body_object": write_body_object(body) if write_objects else None,
                "body_preview": body[:600],
                "private_source_path": str(path),
                "private_display_path": display,
                "atoms": atoms,
                "atom_ids": [stable_hash(atom, 16) for atom in atoms],
            }
        )
    return units


def refresh_aug1_view() -> None:
    script = ROOT / "scripts" / "aug1-view.py"
    if not script.exists():
        return
    subprocess.run([sys.executable, str(script)], cwd=ROOT, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def aug1_panel() -> dict[str, Any]:
    refresh_aug1_view()
    view = load_json(AUG1_VIEW_PATH, {})
    legs = view.get("gate", {}).get("legs", []) if isinstance(view, dict) else []
    return {
        "generated_at": view.get("generated_at"),
        "deadline": view.get("deadline", "2026-08-01"),
        "days_left": view.get("days_left"),
        "gate_pass": bool(view.get("gate", {}).get("pass")) if isinstance(view.get("gate"), dict) else False,
        "legs_total": len(legs),
        "legs_met": sum(1 for leg in legs if isinstance(leg, dict) and leg.get("ok")),
        "next_act": view.get("next_act"),
        "ledger": view.get("ledger", {}),
    }


def inbound_panel() -> dict[str, Any]:
    value_repos = load_json(VALUE_REPOS_PATH, {}).get("repos", [])
    seeds = load_json(POSITIONING_SEEDS_PATH, {})
    repo_seeds = seeds.get("repos", {}) if isinstance(seeds, dict) else {}
    frontdoor = seeds.get("frontdoor", {}) if isinstance(seeds, dict) else {}
    scraper = POSITIONING_DIR / "public-record-data-scrapper.md"
    discoverability = POSITIONING_DIR / "_discoverability.md"
    return {
        "value_repo_count": len(value_repos) if isinstance(value_repos, list) else 0,
        "seeded_repo_count": len(repo_seeds) if isinstance(repo_seeds, dict) else 0,
        "frontdoor_present": (POSITIONING_DIR / "_frontdoor.md").exists(),
        "discoverability_present": discoverability.exists(),
        "scraper_model_present": scraper.exists(),
        "capture_contact_configured": bool(frontdoor.get("contact")) if isinstance(frontdoor, dict) else False,
        "scraper_model_unit": "public-record-data-scrapper",
    }


def build_clusters(units: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for unit in units:
        grouped[str(unit.get("cluster_id") or "unclustered")].append(unit)
    clusters = []
    cluster_atoms: dict[str, list[str]] = {}
    for cluster_id, rows in grouped.items():
        atom_counts = Counter(atom for row in rows for atom in row.get("atoms", []))
        cluster_atoms[cluster_id] = [atom for atom, _ in atom_counts.most_common(24)]
        dates = [str(row.get("event_at")) for row in rows if row.get("event_at")]
        lanes = Counter(str(row.get("lane_id") or "unknown") for row in rows)
        kinds = Counter(str(row.get("kind") or "unknown") for row in rows)
        clusters.append(
            {
                "cluster_id": cluster_id,
                "unit_count": len(rows),
                "kinds": dict(kinds.most_common()),
                "lanes": dict(lanes.most_common()),
                "first_event": min(dates) if dates else None,
                "last_event": max(dates) if dates else None,
                "atom_ids": [stable_hash(atom, 16) for atom in cluster_atoms[cluster_id]],
                "representative_unit_id": rows[0]["unit_id"],
            }
        )
    clusters.sort(key=lambda item: (-int(item["unit_count"]), str(item["cluster_id"])))
    return clusters, cluster_atoms


def build_allusions(units: list[dict[str, Any]], cluster_atoms: dict[str, list[str]]) -> list[dict[str, Any]]:
    lane_atoms: dict[str, Counter[str]] = defaultdict(Counter)
    for unit in units:
        lane_atoms[str(unit.get("lane_id") or "unknown")].update(unit.get("atoms", []))
    lane_top_atoms = {
        lane_id: [atom for atom, _ in counter.most_common(24)]
        for lane_id, counter in lane_atoms.items()
    }
    rows = []
    for unit in units:
        explicit = list(unit.get("atoms") or [])
        explicit_set = set(explicit)
        cluster = cluster_atoms.get(str(unit.get("cluster_id")), [])
        lane = lane_top_atoms.get(str(unit.get("lane_id") or "unknown"), [])
        implied = [atom for atom in cluster if atom not in explicit_set][:10]
        absent = [atom for atom in lane if atom not in explicit_set and atom not in implied][:10]
        rows.append(
            {
                "unit_id": unit["unit_id"],
                "explicit_atoms": explicit[:12],
                "implied_atoms": implied,
                "absent_adjacent_atoms": absent,
                "explicit_atom_ids": [stable_hash(atom, 16) for atom in explicit[:12]],
                "implied_atom_ids": [stable_hash(atom, 16) for atom in implied],
                "absent_adjacent_atom_ids": [stable_hash(atom, 16) for atom in absent],
            }
        )
    return rows


def build_comparisons(clusters: list[dict[str, Any]], units: list[dict[str, Any]], limit: int = 24) -> list[dict[str, Any]]:
    by_cluster: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for unit in units:
        by_cluster[str(unit.get("cluster_id"))].append(unit)
    rows = []
    for cluster in clusters:
        members = sorted(
            by_cluster.get(str(cluster["cluster_id"]), []),
            key=lambda item: (str(item.get("event_at") or ""), str(item.get("unit_id"))),
        )
        if len(members) < 2:
            continue
        left, right = members[0], members[-1]
        rows.append(
            {
                "comparison_id": stable_hash(f"{left['unit_id']}:{right['unit_id']}", 18),
                "cluster_id": cluster["cluster_id"],
                "left_unit_id": left["unit_id"],
                "right_unit_id": right["unit_id"],
                "unit_count": len(members),
                "first_event": left.get("event_at"),
                "last_event": right.get("event_at"),
                "lanes": cluster.get("lanes", {}),
                "kinds": cluster.get("kinds", {}),
            }
        )
        if len(rows) >= limit:
            break
    return rows


def redact_unit(unit: dict[str, Any]) -> dict[str, Any]:
    redacted = {
        "unit_id": unit["unit_id"],
        "kind": unit.get("kind"),
        "role": unit.get("role"),
        "source": unit.get("source"),
        "event_at": unit.get("event_at"),
        "hash": unit.get("hash"),
        "signature": unit.get("signature"),
        "cluster_id": unit.get("cluster_id"),
        "parent_id": unit.get("parent_id"),
        "lane_id": unit.get("lane_id"),
        "body_chars": unit.get("body_chars"),
        "body_words": unit.get("body_words"),
        "atom_ids": unit.get("atom_ids", []),
    }
    if unit.get("task_status"):
        redacted["task_status"] = unit.get("task_status")
    if unit.get("task_priority"):
        redacted["task_priority"] = unit.get("task_priority")
    if unit.get("artifact_path"):
        redacted["artifact_path"] = unit.get("artifact_path")
    if unit.get("worktree_slug"):
        redacted["worktree_slug_hash"] = stable_hash(str(unit.get("worktree_slug")), 16)
    if unit.get("repo"):
        redacted["repo_hash"] = stable_hash(str(unit.get("repo")), 16)
    return redacted


def validate_public_redaction(public_snapshot: dict[str, Any]) -> None:
    text = json.dumps(public_snapshot, ensure_ascii=False)
    forbidden = [
        '"body_preview"',
        '"body_object"',
        '"private_source_path"',
        '"private_display_path"',
        str(HOME),
        str(PRIVATE_ROOT),
        "dispatch_log",
        '"context"',
        '"title"',
    ]
    hits = [item for item in forbidden if item and item in text]
    if hits:
        raise ValueError(f"public corpus snapshot leaks forbidden field/text: {hits}")


def build_snapshots(*, write_objects: bool = False, max_sessions: int | None = DEFAULT_MAX_SESSIONS) -> tuple[dict[str, Any], dict[str, Any], str]:
    lifecycle = load_json(LIFECYCLE_INDEX, {})
    priority = load_json(PRIORITY_INDEX, {})
    attack = load_json(ATTACK_INDEX, {})
    units = []
    units.extend(build_session_units(lifecycle, priority, write_objects=write_objects, max_sessions=max_sessions))
    units.extend(build_task_units(write_objects=write_objects))
    units.extend(build_doc_units(write_objects=write_objects))
    units.sort(key=lambda item: (str(item.get("event_at") or ""), str(item.get("unit_id"))))
    clusters, cluster_atoms = build_clusters(units)
    public_units_source = units[:PUBLIC_UNIT_LIMIT]
    allusions = build_allusions(public_units_source, cluster_atoms)
    comparisons = build_comparisons(clusters, units)
    kind_counts = Counter(str(unit.get("kind") or "unknown") for unit in units)
    lane_counts = Counter(str(unit.get("lane_id") or "unknown") for unit in units)
    source_counts = Counter(str(unit.get("source") or "unknown") for unit in units)
    generated_at = now_iso()
    coverage = {
        "units": len(units),
        "sessions_indexed": len({unit.get("session_key") for unit in units if unit.get("session_key")}),
        "unique_hashes": len({unit.get("hash") for unit in units if unit.get("hash")}),
        "clusters": len(clusters),
        "comparisons": len(comparisons),
        "allusion_rows": len(allusions),
        "body_objects": len({unit.get("body_object") for unit in units if unit.get("body_object")}),
        "kinds": dict(kind_counts.most_common()),
        "lanes": dict(lane_counts.most_common()),
        "sources": dict(source_counts.most_common()),
    }
    private = {
        "generated_at": generated_at,
        "privacy": {
            "raw_text_location": str(BODY_OBJECT_ROOT),
            "public_contains_raw_text": False,
            "private_contains_body_previews": True,
        },
        "inputs": {
            "prompt_lifecycle_index": str(LIFECYCLE_INDEX),
            "prompt_priority_map": str(PRIORITY_INDEX),
            "session_attack_paths": str(ATTACK_INDEX),
            "tasks": str(TASKS_PATH),
        },
        "coverage": coverage,
        "units": units,
        "clusters": clusters,
        "allusions": allusions,
        "comparisons": comparisons,
        "aug1": aug1_panel(),
        "inbound": inbound_panel(),
        "attack_paths": attack.get("ranked_paths", []) if isinstance(attack, dict) else [],
    }
    allusions_by_unit = {row["unit_id"]: row for row in allusions}
    public_units = [redact_unit(unit) for unit in public_units_source]
    public_coverage = {
        **coverage,
        "private_object_count": coverage["body_objects"],
    }
    public_coverage.pop("body_objects", None)
    public = {
        "status": "ok",
        "surface": "corpus",
        "generated_at": generated_at,
        "privacy": {
            "redacted": True,
            "contains_raw_text": False,
            "private_index": rel_to_root(PRIVATE_INDEX),
            "private_html": rel_to_root(PRIVATE_HTML),
        },
        "coverage": public_coverage,
        "units": public_units,
        "truncated_units": len(units) > PUBLIC_UNIT_LIMIT,
        "clusters": clusters[:500],
        "comparisons": comparisons[:100],
        "allusions": [
            {
                "unit_id": row["unit_id"],
                "explicit_atom_ids": row["explicit_atom_ids"],
                "implied_atom_ids": row["implied_atom_ids"],
                "absent_adjacent_atom_ids": row["absent_adjacent_atom_ids"],
            }
            for row in (allusions_by_unit.get(unit["unit_id"]) for unit in public_units_source)
            if row
        ],
        "aug1": private["aug1"],
        "inbound": private["inbound"],
    }
    validate_public_redaction(public)
    markdown = render_markdown(public)
    return private, public, markdown


def render_markdown(public: dict[str, Any]) -> str:
    coverage = public["coverage"]
    aug1 = public["aug1"]
    inbound = public["inbound"]
    lines = [
        "# Corpus Command Center",
        "",
        f"Generated: `{public['generated_at']}`",
        "",
        "## Canonical Decision",
        "",
        "- Prompts, replies, artifacts, tasks, Aug-1 state, and inbound positioning are one corpus surface.",
        "- Raw bodies stay in `.limen-private/session-corpus/corpus-command-center/objects`; tracked output is redacted.",
        "- The dashboard surfaces work candidates and pressure; it does not claim tasks or mutate `tasks.yaml`.",
        "",
        "## Coverage",
        "",
        f"- Units indexed: `{coverage['units']}`.",
        f"- Unique hashes: `{coverage['unique_hashes']}`.",
        f"- Clusters: `{coverage['clusters']}`.",
        f"- Side-by-side comparisons: `{coverage['comparisons']}`.",
        f"- Private body objects: `{coverage['private_object_count']}`.",
        "",
        "## Kind Mix",
        "",
        "| Kind | Units |",
        "|---|---:|",
    ]
    for key, value in coverage["kinds"].items():
        lines.append(f"| `{key}` | {value} |")
    lines.extend(
        [
            "",
            "## Goal Panels",
            "",
            f"- Aug-1 gate: `{'pass' if aug1.get('gate_pass') else 'false'}`; legs `{aug1.get('legs_met')}` / `{aug1.get('legs_total')}`; deadline `{aug1.get('deadline')}`.",
            f"- Inbound magnet: value repos `{inbound.get('value_repo_count')}`, seeded repos `{inbound.get('seeded_repo_count')}`, scraper model present `{inbound.get('scraper_model_present')}`.",
            "",
            "## Private Outputs",
            "",
            f"- Private index: `{rel_to_root(PRIVATE_INDEX)}`.",
            f"- Private local explorer: `{rel_to_root(PRIVATE_HTML)}`.",
            f"- Public/redacted index: `{rel_to_root(PUBLIC_INDEX)}`.",
            "",
            "## Commands",
            "",
            "- Refresh the command center: `python3 scripts/corpus-command-center.py --write`",
            "- Run the full local corpus intentionally: `python3 scripts/corpus-command-center.py --write --all-sessions`",
            "- Refresh upstream ledgers first when needed: `python3 scripts/prompt-lifecycle-ledger.py --write --all && python3 scripts/prompt-priority-map.py --write`",
        ]
    )
    return "\n".join(lines) + "\n"


def render_private_html(private: dict[str, Any]) -> str:
    comparisons = private.get("comparisons", [])[:40]
    units_by_id = {unit["unit_id"]: unit for unit in private.get("units", [])}
    cards = []
    for item in comparisons:
        left = units_by_id.get(item["left_unit_id"], {})
        right = units_by_id.get(item["right_unit_id"], {})
        cards.append(
            "<section class='cmp'>"
            f"<h2>{html.escape(item['cluster_id'])}</h2>"
            "<div class='cols'>"
            f"<pre>{html.escape(str(left.get('body_preview') or ''))}</pre>"
            f"<pre>{html.escape(str(right.get('body_preview') or ''))}</pre>"
            "</div>"
            f"<p>{html.escape(str(left.get('body_object') or ''))} -> {html.escape(str(right.get('body_object') or ''))}</p>"
            "</section>"
        )
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Corpus Command Center Private</title>
<style>
body{font-family:ui-sans-serif,system-ui;margin:0;background:#f6f7f9;color:#111827}
main{max-width:1280px;margin:0 auto;padding:24px}
.cmp{background:white;border:1px solid #d9dee7;border-radius:8px;margin:14px 0;padding:14px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:12px}
pre{white-space:pre-wrap;background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;padding:12px;max-height:360px;overflow:auto}
p{color:#667085;font-size:12px}
</style>
</head>
<body><main>
<h1>Corpus Command Center Private Explorer</h1>
<p>Raw body objects live under the ignored private corpus object store. This page shows private previews for top comparisons only.</p>
""" + "\n".join(cards) + "</main></body></html>\n"


def write_outputs(private: dict[str, Any], public: dict[str, Any], markdown: str) -> None:
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_INDEX.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.write_text(json.dumps(private, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    PUBLIC_INDEX.write_text(json.dumps(public, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    DOC_PATH.write_text(markdown, encoding="utf-8")
    PRIVATE_HTML.write_text(render_private_html(private), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write private/public snapshots and tracked markdown")
    parser.add_argument("--no-body-objects", action="store_true", help="do not write raw body objects")
    parser.add_argument(
        "--max-sessions",
        type=int,
        default=DEFAULT_MAX_SESSIONS,
        help="optional debug cap; default indexes every local lifecycle session unless LIMEN_CORPUS_MAX_SESSIONS is set",
    )
    parser.add_argument("--all-sessions", action="store_true", help="ignore any session cap and index every local lifecycle session")
    args = parser.parse_args(argv)
    max_sessions = None if args.all_sessions else args.max_sessions
    private, public, markdown = build_snapshots(
        write_objects=args.write and not args.no_body_objects,
        max_sessions=max_sessions,
    )
    if args.write:
        write_outputs(private, public, markdown)
    print(
        "corpus-command-center: "
        f"{public['coverage']['units']} units, "
        f"{public['coverage']['clusters']} clusters, "
        f"{public['coverage']['comparisons']} comparisons"
    )
    if args.write:
        print(f"wrote {PRIVATE_INDEX}")
        print(f"wrote {PUBLIC_INDEX}")
        print(f"wrote {DOC_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
