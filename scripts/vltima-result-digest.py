#!/usr/bin/env python3
"""Digest prior excavation results without letting old material govern current work.

This is the second VLTIMA excavation layer. It reads the outputs registered by
``vltima-prior-excavations.py`` and produces a redacted result brief plus a
private structured index.

The temporal contract is deliberate:

* old material is lineage, not authority;
* new material is authority, not total memory.

The script reads generated result artifacts, not raw prompt bodies, private
object-store text, credentials, or repo source trees.
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
PRIOR_INDEX = PRIVATE_ROOT / "lifecycle" / "vltima-prior-excavations.json"
DOC_PATH = ROOT / "docs" / "vltima-result-digest.md"
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "vltima-result-digest.json"

MAX_JSON_BYTES = 50 * 1024 * 1024
DEFAULT_MAX_CLAIMS = 500

RAW_SECRET_RE = re.compile(r"(SECRET[_A-Z0-9-]*|PASSWORD[_A-Z0-9-]*|TOKEN[_A-Z0-9-]*|sk-[A-Za-z0-9_-]+)")
PRIVATE_BODY_MARKERS = (
    "/objects/",
    "/corpus-command-center/objects/",
    "/full-stack-review/session-",
)
SENSITIVE_KEY_FRAGMENTS = (
    "body",
    "content",
    "credential",
    "message",
    "password",
    "prompt",
    "secret",
    "text",
    "token",
)
HAZARD_TERMS = (
    "api key",
    "auth",
    "billing",
    "credential",
    "login",
    "password",
    "private-only",
    "secret",
    "token",
)
SUPERSEDED_TERMS = (
    "default-branch-preserved",
    "landed-ancestor",
    "merged",
    "remote-merged",
    "remote-superseded",
    "superseded",
    "superseded-recorded",
    "superseded_on_origin_main",
)
AUTHORITY_ORDER = {
    "current_doctrine": 0,
    "living_lineage": 1,
    "dormant_ore": 2,
    "superseded_material": 3,
    "quarantined_ghost": 4,
}
TRUST_ORDER = {"high": 0, "medium": 1, "low": 2, "unknown": 3}
ABSORPTION_CADENCE = (
    {
        "phase": "capture",
        "cadence": "session-boundary and daily",
        "command": "python3 scripts/session-corpus-ledger.py --write --all",
        "inputs": "Claude/Codex/OpenCode/Agy/Gemini/local app stores, projects, plans, tasks, histories",
        "output": "redacted corpus/source coverage plus private inventory metadata",
        "reason": "any local AI app movement is signal, even when it is only a brainstorm through a narrow lens",
    },
    {
        "phase": "materialize-private",
        "cadence": "deliberate daily or before row-level review",
        "command": "python3 scripts/session-corpus-ledger.py --write --all --materialize",
        "inputs": "local chat/project stores and app support files",
        "output": "ignored private object store under .limen-private/session-corpus",
        "reason": "raw local material is absorbable, but it stays private and out of tracked Git",
    },
    {
        "phase": "crosswalk",
        "cadence": "after capture, before routing",
        "command": "python3 scripts/prompt-lifecycle-ledger.py --write --all",
        "inputs": "session/corpus atoms, worktrees, task snapshots, remote/cloud receipts",
        "output": "prompt/session/worktree/task/remote crosswalk",
        "reason": "brainstorms become useful when they can be related to current work without becoming authority",
    },
    {
        "phase": "classify-pressure",
        "cadence": "session end and before delegation",
        "command": "python3 scripts/session-blockers-ledger.py --write && python3 scripts/session-lifecycle-pressure.py --write",
        "inputs": "crosswalk, blockers, worktree preservation, local/remote pressure",
        "output": "parked blockers and lifecycle pressure receipts",
        "reason": "system clogs must be visible before assigning new work",
    },
    {
        "phase": "rank-and-packetize",
        "cadence": "after classification",
        "command": "python3 scripts/session-attack-paths.py --write && python3 scripts/prompt-priority-map.py --write",
        "inputs": "redacted prompt recurrence, recency, blockers, worktree evidence",
        "output": "ranked paths, priority bands, batches, and packets",
        "reason": "old ideas seed lineage; current evidence chooses action order",
    },
    {
        "phase": "distill",
        "cadence": "after current receipts are fresh",
        "command": "python3 scripts/corpus-command-center.py --write",
        "inputs": "prompts, replies, artifacts, tasks, products, inbound positioning",
        "output": "reduced principles and multiversal lens surfaces",
        "reason": "many local brainstorms can be boiled into fewer reusable principles without concatenating everything",
    },
)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def parse_time(value: Any) -> dt.datetime | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def repo_rel(path: Path, *, root: Path = ROOT) -> str:
    try:
        return str(path.expanduser().resolve().relative_to(root))
    except (OSError, ValueError):
        try:
            return str(path.expanduser().relative_to(root))
        except ValueError:
            return str(path.expanduser())


def path_from_label(label: str, *, root: Path = ROOT, private_root: Path = PRIVATE_ROOT) -> Path:
    if label.startswith(".limen-private/session-corpus/"):
        return private_root / label.removeprefix(".limen-private/session-corpus/")
    return (root / label).expanduser()


def is_private_body_path(path: Path) -> bool:
    text = str(path)
    return any(marker in text for marker in PRIVATE_BODY_MARKERS)


def safe_string(value: Any, *, limit: int = 180) -> str:
    text = str(value).replace("\n", " ").replace("\r", " ").strip()
    text = RAW_SECRET_RE.sub("[redacted]", text)
    if len(text) > limit:
        return f"{text[: limit - 1]}..."
    return text


def display_subject(value: Any) -> str:
    text = safe_string(value, limit=90)
    path_markers = ("/Users/", "/Volumes/", "~/", ".claude/worktrees", ".limen-worktrees")
    if text.startswith("/") or text.startswith("~/") or any(marker in text for marker in path_markers):
        tail = Path(text.replace("~", "")).name or "root"
        return f"local-path:{safe_string(tail, limit=60)}"
    return text


def sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in SENSITIVE_KEY_FRAGMENTS)


def redact_value(value: Any, *, key: str = "") -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if sensitive_key(key):
        return "[redacted]"
    if isinstance(value, str):
        return safe_string(value, limit=220)
    if isinstance(value, list):
        return [redact_value(item) for item in value[:20]]
    if isinstance(value, dict):
        return {safe_string(k, limit=80): redact_value(v, key=str(k)) for k, v in list(value.items())[:30]}
    return safe_string(value)


def clean_claim(claim: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in claim.items():
        if key in {"reasons"} and isinstance(value, list):
            cleaned[key] = [safe_string(item, limit=120) for item in value[:8]]
        elif key in {"metric", "claim_type", "surface", "lane", "freshness", "authority", "trust"}:
            cleaned[key] = safe_string(value, limit=80)
        elif key in {"value", "generated_at", "id", "recurrence"}:
            cleaned[key] = redact_value(value, key=key)
        else:
            cleaned[key] = redact_value(value, key=key)
    return cleaned


def freshness(generated_at: Any, *, now: dt.datetime) -> str:
    parsed = parse_time(generated_at)
    if parsed is None:
        return "unknown"
    age_days = (now - parsed).total_seconds() / 86400
    if age_days <= 14:
        return "fresh"
    if age_days <= 90:
        return "recent"
    return "lineage"


def classify_claim(claim: dict[str, Any], *, now: dt.datetime) -> dict[str, Any]:
    claim = clean_claim(claim)
    blob = " ".join(
        safe_string(claim.get(key, ""), limit=500).lower()
        for key in ("surface", "claim_type", "subject", "summary", "next_action", "source_status")
    )
    source_status = safe_string(claim.get("source_status", ""), limit=80)
    claim_freshness = freshness(claim.get("generated_at"), now=now)
    reasons = list(claim.get("reasons") or [])
    reasons.append(f"freshness:{claim_freshness}")
    reasons.append(f"source_status:{source_status or 'unknown'}")
    recurrence = int(claim.get("recurrence") or 0)

    if any(term in blob for term in SUPERSEDED_TERMS):
        authority = "superseded_material"
        trust = "low"
        reasons.append("explicit-supersession-or-preservation-term")
    elif source_status == "private-only" or any(term in blob for term in HAZARD_TERMS):
        authority = "quarantined_ghost"
        trust = "low"
        reasons.append("hazardous-or-private-only-material")
    elif source_status == "script-only":
        authority = "dormant_ore"
        trust = "low"
        reasons.append("script-exists-without-result")
    elif source_status == "stale":
        authority = "living_lineage" if recurrence > 1 else "dormant_ore"
        trust = "low"
        reasons.append("stale-result")
    elif claim_freshness == "lineage":
        authority = "living_lineage" if recurrence > 1 else "dormant_ore"
        trust = "medium" if recurrence > 1 else "low"
        reasons.append("old-result-retained-as-lineage")
    elif claim_freshness in {"fresh", "recent"} and source_status in {"current", "tracked-only"}:
        authority = "current_doctrine"
        trust = "high" if source_status == "current" and claim_freshness == "fresh" else "medium"
        reasons.append("fresh-current-result")
    else:
        authority = "dormant_ore"
        trust = "unknown"
        reasons.append("insufficient-authority-evidence")

    claim["freshness"] = claim_freshness
    claim["authority"] = authority
    claim["trust"] = trust
    claim["reasons"] = reasons
    return claim


def load_prior_index(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"missing prior index: {path}; refresh with python3 scripts/vltima-prior-excavations.py --write"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def load_json_artifact(item: dict[str, Any], *, root: Path, private_root: Path) -> Any | None:
    label = str(item.get("label") or "")
    path = Path(item.get("path") or path_from_label(label, root=root, private_root=private_root))
    if is_private_body_path(path) or path.suffix != ".json" or not path.exists():
        return None
    try:
        if path.stat().st_size > MAX_JSON_BYTES:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def base_claim(surface: dict[str, Any], claim_type: str, subject: str, **kwargs: Any) -> dict[str, Any]:
    return {
        "id": f"{surface['id']}:{claim_type}:{subject}",
        "surface": surface["id"],
        "lane": surface.get("lane") or "unknown",
        "claim_type": claim_type,
        "subject": subject,
        "summary": kwargs.pop("summary", ""),
        "metric": kwargs.pop("metric", ""),
        "value": kwargs.pop("value", None),
        "generated_at": kwargs.pop("generated_at", surface.get("generated_at")),
        "evidence_label": kwargs.pop("evidence_label", ""),
        "source_status": kwargs.pop("source_status", surface.get("status")),
        "next_action": kwargs.pop("next_action", ""),
        "recurrence": kwargs.pop("recurrence", 0),
        **kwargs,
    }


def add_count_claims(
    claims: list[dict[str, Any]],
    surface: dict[str, Any],
    source: dict[str, Any],
    *,
    claim_type: str,
    evidence_label: str,
    limit: int = 20,
) -> None:
    for key, value in list(source.items())[:limit]:
        if isinstance(value, (int, float, str, bool)):
            claims.append(
                base_claim(
                    surface,
                    claim_type,
                    safe_string(key, limit=120),
                    summary=f"{safe_string(key, limit=80)} = {safe_string(value, limit=80)}",
                    metric=safe_string(key, limit=80),
                    value=value,
                    evidence_label=evidence_label,
                    recurrence=value if isinstance(value, int) else 0,
                )
            )


def artifact_metadata_claims(surface: dict[str, Any]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for group in ("tracked", "private", "logs"):
        for item in surface.get(group, []):
            if not item.get("exists"):
                continue
            summary = item.get("summary") or {}
            evidence_label = str(item.get("label") or "")
            if summary.get("collection_counts"):
                add_count_claims(
                    claims,
                    surface,
                    dict(summary["collection_counts"]),
                    claim_type="result_collection",
                    evidence_label=evidence_label,
                )
            elif summary.get("kind") == "directory":
                claims.append(
                    base_claim(
                        surface,
                        "result_directory",
                        evidence_label,
                        summary=f"directory entries {summary.get('entries', 0)}; json files {summary.get('json_files', 0)}",
                        metric="entries",
                        value=summary.get("entries", 0),
                        evidence_label=evidence_label,
                        recurrence=int(summary.get("entries") or 0),
                    )
                )
    claims.append(
        base_claim(
            surface,
            "surface_status",
            str(surface["id"]),
            summary=f"{surface['id']} status is {surface.get('status')}; refresh mode {surface.get('refresh_mode')}",
            metric="outputs_present",
            value=int(surface.get("tracked_present", 0)) + int(surface.get("private_present", 0)) + int(surface.get("logs_present", 0)),
            evidence_label="vltima-prior-excavations",
            recurrence=1,
        )
    )
    return claims


def first_json(loaded: dict[str, Any], *needles: str) -> tuple[str, dict[str, Any]] | tuple[str, None]:
    for label, data in loaded.items():
        if not isinstance(data, dict):
            continue
        if not needles or any(needle in label for needle in needles):
            return label, data
    return "", None


def top_items(rows: list[dict[str, Any]], *, score_key: str = "score", limit: int = 25) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: (row.get(score_key) or 0, row.get("prompt_events") or 0), reverse=True)[:limit]


def extract_specific_claims(surface: dict[str, Any], loaded: dict[str, Any]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    surface_id = str(surface["id"])
    label, data = first_json(loaded)
    if data is None:
        return claims

    if surface_id == "session-corpus-ledger":
        for row in data.get("local_summary", [])[:20]:
            source = safe_string(row.get("source", "source"), limit=80)
            claims.append(
                base_claim(
                    surface,
                    "session_source",
                    source,
                    summary=f"{source}: {row.get('files', 0)} files; newest {safe_string(row.get('newest', 'unknown'), limit=40)}",
                    metric="files",
                    value=row.get("files", 0),
                    evidence_label=label,
                    recurrence=int(row.get("files") or 0),
                )
            )
        object_store = data.get("object_store") or {}
        add_count_claims(claims, surface, object_store, claim_type="private_object_store", evidence_label=label)

    elif surface_id == "prompt-lifecycle-ledger":
        add_count_claims(claims, surface, data.get("body_kind_counts") or {}, claim_type="prompt_body_mix", evidence_label=label)
        add_count_claims(claims, surface, data.get("worktree_report") or {}, claim_type="worktree_status_mix", evidence_label=label)
        for row in data.get("sources", [])[:20]:
            source = safe_string(row.get("source", "source"), limit=80)
            claims.append(
                base_claim(
                    surface,
                    "prompt_source",
                    source,
                    summary=f"{source}: {row.get('prompt_events', 0)} prompt events; newest {safe_string(row.get('newest', 'unknown'), limit=40)}",
                    metric="prompt_events",
                    value=row.get("prompt_events", 0),
                    evidence_label=label,
                    recurrence=int(row.get("prompt_events") or 0),
                )
            )

    elif surface_id == "session-lifecycle-blockers":
        add_count_claims(claims, surface, data.get("by_category") or {}, claim_type="blocker_category", evidence_label=label)
        for blocker in data.get("blockers", [])[:20]:
            subject = safe_string(blocker.get("id", "blocker"), limit=120)
            claims.append(
                base_claim(
                    surface,
                    "blocker",
                    subject,
                    summary=f"{blocker.get('category', 'blocker')} / {blocker.get('status', 'unknown')}: {safe_string(blocker.get('evidence', ''), limit=140)}",
                    metric="blocker",
                    value=1,
                    evidence_label=label,
                    next_action=safe_string(blocker.get("route", ""), limit=140),
                    recurrence=1,
                )
            )

    elif surface_id == "session-attack-paths":
        add_count_claims(claims, surface, data.get("coverage") or {}, claim_type="attack_coverage", evidence_label=label)
        add_count_claims(claims, surface, data.get("lane_counts") or {}, claim_type="attack_lane_count", evidence_label=label)
        for path in top_items(data.get("ranked_paths", []), limit=30):
            subject = safe_string(path.get("id", "path"), limit=120)
            claims.append(
                base_claim(
                    surface,
                    "ranked_attack_path",
                    subject,
                    summary=f"{path.get('lane', 'lane')} / {path.get('kind', 'kind')}; recency {path.get('recency', 'unknown')}; score {path.get('score', 0)}",
                    metric="score",
                    value=path.get("score", 0),
                    evidence_label=label,
                    next_action=safe_string(path.get("next_action", ""), limit=180),
                    recurrence=int(path.get("sessions") or path.get("prompt_events") or 0),
                )
            )

    elif surface_id == "prompt-priority-map":
        add_count_claims(claims, surface, data.get("counts") or {}, claim_type="priority_count", evidence_label=label)
        for row in data.get("lane_task_map", [])[:20]:
            lane = safe_string(row.get("lane", "lane"), limit=80)
            claims.append(
                base_claim(
                    surface,
                    "priority_lane",
                    lane,
                    summary=f"{lane}: {row.get('prompt_events', 0)} prompt events; route {safe_string(row.get('route', ''), limit=80)}",
                    metric="prompt_events",
                    value=row.get("prompt_events", 0),
                    evidence_label=label,
                    next_action=safe_string(row.get("route", ""), limit=120),
                    recurrence=int(row.get("sessions") or 0),
                )
            )
        for row in top_items(data.get("review_batches", []), score_key="max_score", limit=20):
            subject = safe_string(row.get("id", "batch"), limit=120)
            claims.append(
                base_claim(
                    surface,
                    "review_batch",
                    subject,
                    summary=f"{row.get('lane', 'lane')} / {row.get('band', 'band')}; {row.get('prompt_events', 0)} prompt events",
                    metric="max_score",
                    value=row.get("max_score", 0),
                    evidence_label=label,
                    next_action=safe_string(row.get("next_action", ""), limit=160),
                    recurrence=int(row.get("session_count") or 0),
                )
            )

    elif surface_id == "corpus-command-center":
        public_label, public = first_json(loaded, "public")
        if public is not None:
            add_count_claims(claims, surface, public.get("coverage") or {}, claim_type="corpus_coverage", evidence_label=public_label)
            add_count_claims(claims, surface, public.get("aug1") or {}, claim_type="aug1_state", evidence_label=public_label)
            add_count_claims(claims, surface, public.get("inbound") or {}, claim_type="inbound_state", evidence_label=public_label)

    elif surface_id == "repo-surface-ledger":
        for key in ("repo_count", "dirty_count", "worktree_count"):
            if key in data:
                claims.append(
                    base_claim(
                        surface,
                        "repo_surface_count",
                        key,
                        summary=f"{key} = {data[key]}",
                        metric=key,
                        value=data[key],
                        evidence_label=label,
                        recurrence=int(data[key] or 0),
                    )
                )
        claims.append(
            base_claim(
                surface,
                "duplicate_remote_groups",
                "duplicate_remotes",
                summary=f"{len(data.get('duplicate_remotes') or {})} duplicate remote groups are recorded by hash",
                metric="duplicate_remote_groups",
                value=len(data.get("duplicate_remotes") or {}),
                evidence_label=label,
                recurrence=len(data.get("duplicate_remotes") or {}),
            )
        )

    elif surface_id == "capability-substrate-ledger":
        add_count_claims(claims, surface, data.get("coverage") or {}, claim_type="capability_coverage", evidence_label=label)
        for lane, rows in list((data.get("activation_groups") or {}).items())[:20]:
            claims.append(
                base_claim(
                    surface,
                    "activation_group",
                    safe_string(lane, limit=80),
                    summary=f"{safe_string(lane, limit=80)} activation group has {len(rows)} candidates",
                    metric="candidates",
                    value=len(rows),
                    evidence_label=label,
                    recurrence=len(rows),
                )
            )

    elif surface_id == "product-ledger":
        add_count_claims(claims, surface, data.get("counts") or {}, claim_type="product_count", evidence_label=label)
        for product in data.get("next_unblocked", [])[:25]:
            subject = safe_string(product.get("title") or product.get("id") or "product", limit=120)
            claims.append(
                base_claim(
                    surface,
                    "next_unblocked_product",
                    subject,
                    summary=f"{product.get('state', 'state')} / {product.get('disposition', 'disposition')} / {product.get('outward_path', 'path')}",
                    metric="priority",
                    value=product.get("priority", 0),
                    evidence_label=label,
                    next_action=safe_string(product.get("gate", ""), limit=140),
                    recurrence=1,
                )
            )

    elif surface_id == "substrate-ledger":
        add_count_claims(claims, surface, data.get("counts") or {}, claim_type="substrate_count", evidence_label=label)
        for idx, root in enumerate(data.get("roots", [])[:20], start=1):
            status = safe_string(root.get("status", "unknown"), limit=80)
            claims.append(
                base_claim(
                    surface,
                    "substrate_root",
                    f"substrate-root-{idx}",
                    summary=f"{status}; usage {root.get('usage_pct', 'unknown')}%; free GiB {root.get('free_gib', 'unknown')}",
                    metric="usage_pct",
                    value=root.get("usage_pct"),
                    evidence_label=label,
                    next_action=safe_string(root.get("detail", ""), limit=140),
                    recurrence=1,
                )
            )

    elif surface_id == "prompt-batch-review-ledger":
        add_count_claims(claims, surface, data.get("counts", {}).get("status") or data.get("counts") or {}, claim_type="batch_status", evidence_label=label)
        for row in top_items(data.get("review_queue", []), score_key="max_score", limit=25):
            subject = safe_string(row.get("id", "batch"), limit=120)
            claims.append(
                base_claim(
                    surface,
                    "review_queue_batch",
                    subject,
                    summary=f"{row.get('lane', 'lane')} / {row.get('status', 'status')} / {row.get('band', 'band')}",
                    metric="max_score",
                    value=row.get("max_score", 0),
                    evidence_label=label,
                    next_action=safe_string(row.get("next_action", ""), limit=160),
                    recurrence=int(row.get("session_count") or 0),
                )
            )

    elif surface_id == "prompt-packet-ledger":
        add_count_claims(claims, surface, data.get("counts") or {}, claim_type="packet_count", evidence_label=label)
        for row in data.get("open_packets", [])[:20]:
            subject = safe_string(row.get("id", "packet"), limit=120)
            claims.append(
                base_claim(
                    surface,
                    "open_packet",
                    subject,
                    summary=f"{row.get('lane', 'lane')} / {row.get('packet_kind', 'kind')} / {row.get('dispatchability', 'dispatch')}",
                    metric="prompt_events",
                    value=row.get("prompt_events", 0),
                    evidence_label=label,
                    next_action=safe_string(row.get("resolution", ""), limit=160),
                    recurrence=int(row.get("prompt_events") or 0),
                )
            )

    elif surface_id == "agent-reconstruction-review":
        add_count_claims(claims, surface, data.get("counts") or {}, claim_type="reconstruction_count", evidence_label=label)
        add_count_claims(claims, surface, data.get("gap_counts") or {}, claim_type="reconstruction_gap", evidence_label=label)
        for row in top_items(data.get("analyzed_roots", []), score_key="risk_score", limit=20):
            subject = safe_string(row.get("display_root", "root"), limit=120)
            claims.append(
                base_claim(
                    surface,
                    "reconstruction_root",
                    subject,
                    summary=f"{row.get('session_count', 0)} sessions; {row.get('prompt_events', 0)} prompt events; risk {row.get('risk_score', 0)}",
                    metric="risk_score",
                    value=row.get("risk_score", 0),
                    evidence_label=label,
                    recurrence=int(row.get("session_count") or 0),
                )
            )

    elif surface_id == "agent-code-review-queue":
        add_count_claims(claims, surface, data.get("counts") or {}, claim_type="code_review_count", evidence_label=label)
        add_count_claims(claims, surface, data.get("bucket_totals") or {}, claim_type="code_review_bucket", evidence_label=label)
        for row in top_items(data.get("changed_review", []), score_key="risk_score", limit=20):
            subject = safe_string(row.get("display_root", row.get("session_id", "review")), limit=120)
            claims.append(
                base_claim(
                    surface,
                    "code_review_candidate",
                    subject,
                    summary=f"{row.get('agent', 'agent')} / {row.get('outcome', 'outcome')}; risk {row.get('risk_score', 0)}",
                    metric="risk_score",
                    value=row.get("risk_score", 0),
                    evidence_label=label,
                    recurrence=int(row.get("prompt_events") or 0),
                )
            )

    elif surface_id == "session-value-review":
        add_count_claims(claims, surface, data.get("metrics") or {}, claim_type="value_metric", evidence_label=label)
        add_count_claims(claims, surface, data.get("findings") or {}, claim_type="value_finding", evidence_label=label)
        for receipt in data.get("batch_receipts", [])[:20]:
            subject = safe_string(receipt.get("batch", "batch"), limit=120)
            claims.append(
                base_claim(
                    surface,
                    "value_batch_receipt",
                    subject,
                    summary=f"{receipt.get('lane', 'lane')} / {receipt.get('status', 'status')}; {receipt.get('prompt_events', 0)} prompt events",
                    metric="prompt_events",
                    value=receipt.get("prompt_events", 0),
                    evidence_label=label,
                    recurrence=int(receipt.get("session_count") or 0),
                )
            )

    return claims


def load_surface_json(surface: dict[str, Any], *, root: Path, private_root: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = {}
    for group in ("private", "tracked", "logs"):
        for item in surface.get(group, []):
            label = str(item.get("label") or "")
            data = load_json_artifact(item, root=root, private_root=private_root)
            if isinstance(data, dict):
                loaded[label] = data
    return loaded


def extract_claims(prior: dict[str, Any], *, root: Path, private_root: Path, max_claims: int, now: dt.datetime) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for surface in prior.get("surfaces", []):
        loaded = load_surface_json(surface, root=root, private_root=private_root)
        surface_claims = artifact_metadata_claims(surface)
        surface_claims.extend(extract_specific_claims(surface, loaded))
        for claim in surface_claims:
            claims.append(classify_claim(claim, now=now))
            if len(claims) >= max_claims:
                return claims
    return claims


def sort_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(claim: dict[str, Any]) -> tuple[int, int, int, str]:
        value = claim.get("value")
        numeric = int(value) if isinstance(value, (int, float)) else 0
        return (
            AUTHORITY_ORDER.get(str(claim.get("authority")), 9),
            TRUST_ORDER.get(str(claim.get("trust")), 9),
            -numeric,
            str(claim.get("id")),
        )

    return sorted(claims, key=key)


def build_digest(
    *,
    prior_index: Path = PRIOR_INDEX,
    root: Path = ROOT,
    private_root: Path = PRIVATE_ROOT,
    max_claims: int = DEFAULT_MAX_CLAIMS,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    private_root = private_root.expanduser()
    now = now or dt.datetime.now(dt.timezone.utc)
    prior = load_prior_index(prior_index)
    claims = sort_claims(extract_claims(prior, root=root, private_root=private_root, max_claims=max_claims, now=now))
    authority_counts = Counter(str(claim.get("authority")) for claim in claims)
    trust_counts = Counter(str(claim.get("trust")) for claim in claims)
    freshness_counts = Counter(str(claim.get("freshness")) for claim in claims)
    surface_counts = Counter(str(claim.get("surface")) for claim in claims)
    mismatch_surfaces = [
        {
            "surface": surface["id"],
            "lane": surface.get("lane"),
            "status": surface.get("status"),
            "reason": "result is not fully current/tracked-current",
        }
        for surface in prior.get("surfaces", [])
        if surface.get("status") not in {"current", "tracked-only"}
    ]
    contradictions = [
        {
            "surface": claim["surface"],
            "subject": claim["subject"],
            "authority": claim["authority"],
            "reason": "; ".join(claim.get("reasons", [])[:3]),
        }
        for claim in claims
        if claim.get("authority") in {"superseded_material", "quarantined_ghost"}
    ][:80]
    return {
        "generated_at": now_iso(),
        "decision": "result digest with temporal immune system; old material is lineage, not authority",
        "privacy": {
            "prior_index": str(prior_index),
            "tracked_output": repo_rel(DOC_PATH, root=root),
            "private_index": str(private_root / "lifecycle" / "vltima-result-digest.json"),
            "raw_bodies_read": False,
        },
        "coverage": {
            "prior_generated_at": prior.get("generated_at"),
            "prior_surface_count": len(prior.get("surfaces", [])),
            "claim_count": len(claims),
            "authority_counts": dict(sorted(authority_counts.items())),
            "trust_counts": dict(sorted(trust_counts.items())),
            "freshness_counts": dict(sorted(freshness_counts.items())),
            "surface_claim_counts": dict(sorted(surface_counts.items())),
        },
        "absorption_cadence": list(ABSORPTION_CADENCE),
        "claims": claims,
        "mismatch_surfaces": mismatch_surfaces,
        "contradictions": contradictions,
        "next_safe_sequence": [
            "Refresh prior excavations before any broad VLTIMA estate crawl.",
            "Treat current_doctrine claims as action guidance only when the owner repo/path is explicit.",
            "Use living_lineage and dormant_ore to recover forgotten ideas, not to override newer architecture.",
            "Resolve stale/private-only/script-only result mismatches before trusting those surfaces.",
            "Keep quarantined_ghost claims parked unless a bounded human-auth or secret-safe packet owns them.",
        ],
    }


def table_rows(claims: list[dict[str, Any]], authority: set[str], *, limit: int) -> list[dict[str, Any]]:
    return [claim for claim in claims if claim.get("authority") in authority][:limit]


def render_claim_table(lines: list[str], rows: list[dict[str, Any]]) -> None:
    if not rows:
        lines.append("- None recorded.")
        return
    lines.extend(["| Surface | Subject | Trust | Evidence | Next |", "|---|---|---|---|---|"])
    for claim in rows:
        summary = safe_string(claim.get("summary", ""), limit=130).replace("|", "\\|")
        next_action = safe_string(claim.get("next_action", ""), limit=110).replace("|", "\\|")
        if not next_action:
            next_action = safe_string(claim.get("authority", ""), limit=80)
        lines.append(
            f"| `{claim.get('surface')}` | `{display_subject(claim.get('subject', ''))}` | "
            f"`{claim.get('trust')}` | {summary} | {next_action} |"
        )


def render_markdown(digest: dict[str, Any]) -> str:
    coverage = digest["coverage"]
    authority_bits = ", ".join(f"`{key}` {value}" for key, value in coverage["authority_counts"].items())
    freshness_bits = ", ".join(f"`{key}` {value}" for key, value in coverage["freshness_counts"].items())
    lines = [
        "# VLTIMA Result Digest",
        "",
        f"Generated: `{digest['generated_at']}`",
        "",
        "## Canonical Decision",
        "",
        "- Read the results of prior excavations before adding another broad scanner.",
        "- Old material is lineage, not authority. New material is authority, not total memory.",
        "- This digest classifies result claims as `current_doctrine`, `living_lineage`, `dormant_ore`, `superseded_material`, or `quarantined_ghost`.",
        "- It does not read raw prompt bodies, private object-store text, repo source trees, credentials, remotes, or `tasks.yaml`.",
        "",
        "## Coverage",
        "",
        f"- Prior index generated: `{coverage.get('prior_generated_at')}`.",
        f"- Prior surfaces: `{coverage['prior_surface_count']}`.",
        f"- Result claims: `{coverage['claim_count']}`.",
        f"- Authority mix: {authority_bits or 'none'}.",
        f"- Freshness mix: {freshness_bits or 'none'}.",
        "",
        "## Continual Absorption Cadence",
        "",
        "- Local AI app chats, projects, plans, tasks, histories, and app-store movement are ongoing corpus input.",
        "- Claude has extra lifecycle phases in this workspace: projects, tasks, plans, file history, usage facets, usage session-meta, and quicken states.",
        "- The cadence absorbs movement as private/redacted evidence first; it does not let every brainstorm become current authority.",
        "",
        "| Phase | Cadence | Command | Why |",
        "|---|---|---|---|",
    ]
    for item in digest["absorption_cadence"]:
        reason = safe_string(item["reason"], limit=140).replace("|", "\\|")
        lines.append(
            f"| `{item['phase']}` | {item['cadence']} | `{item['command']}` | "
            f"{reason} |"
        )
    lines.extend(
        [
            "",
        "## Current Doctrine",
        "",
        ]
    )
    render_claim_table(lines, table_rows(digest["claims"], {"current_doctrine"}, limit=40))
    lines.extend(["", "## Lineage And Dormant Ore", ""])
    render_claim_table(lines, table_rows(digest["claims"], {"living_lineage", "dormant_ore"}, limit=40))
    lines.extend(["", "## Superseded Or Quarantined", ""])
    render_claim_table(lines, table_rows(digest["claims"], {"superseded_material", "quarantined_ghost"}, limit=40))
    lines.extend(["", "## Result Mismatches", ""])
    if digest["mismatch_surfaces"]:
        lines.extend(["| Surface | Lane | Status | Reason |", "|---|---|---|---|"])
        for item in digest["mismatch_surfaces"]:
            lines.append(f"| `{item['surface']}` | `{item['lane']}` | `{item['status']}` | {item['reason']} |")
    else:
        lines.append("- No stale/private-only/script-only surface mismatches recorded.")
    lines.extend(["", "## Next Safe Sequence", ""])
    for idx, action in enumerate(digest["next_safe_sequence"], start=1):
        lines.append(f"{idx}. {action}")
    lines.extend(
        [
            "",
            "## Privacy Contract",
            "",
            "- Tracked output is redacted and claim-level.",
            "- Private JSON stores the same sanitized claims plus path-level evidence labels.",
            "- A quarantined claim is not rejected; it is parked until a bounded human-safe packet owns it.",
            "- This digest does not authorize deletion, dedupe, branch cleanup, repo movement, archive rewrite, task-board mutation, or credential handling.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(
    digest: dict[str, Any],
    markdown: str,
    *,
    doc_path: Path = DOC_PATH,
    private_index: Path = PRIVATE_INDEX,
) -> None:
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    private_index.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(markdown, encoding="utf-8")
    private_index.write_text(json.dumps(digest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh the VLTIMA result digest.")
    parser.add_argument("--prior-index", type=Path, default=PRIOR_INDEX, help="path to vltima-prior-excavations.json")
    parser.add_argument("--max-claims", type=int, default=DEFAULT_MAX_CLAIMS, help="maximum sanitized result claims")
    parser.add_argument("--write", action="store_true", help="write tracked summary and private index")
    parser.add_argument("--json", action="store_true", help="print private-style JSON digest")
    args = parser.parse_args()
    try:
        digest = build_digest(prior_index=args.prior_index, max_claims=args.max_claims)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    markdown = render_markdown(digest)
    if args.write:
        write_outputs(digest, markdown)
        print(f"vltima-result-digest: wrote {DOC_PATH} and {PRIVATE_INDEX}")
    elif args.json:
        print(json.dumps(digest, indent=2, sort_keys=True))
    else:
        print(markdown, end="")
        print("vltima-result-digest: dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
