#!/usr/bin/env python3
"""Resolve hash-review prompt batches into public-safe receipts.

This resolver reads only redacted/private metadata indexes. It does not open
source session JSONL files or write raw prompt, assistant, tool-result, account,
credential, billing, health, or secret text.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
PRIORITY_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-priority-map.json"
SESSION_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
BATCH_RESOLUTION_RECEIPTS = ROOT / "docs" / "prompt-batch-resolution-receipts.json"

OWNER_REPO = "organvm/limen"
SUPPORTED_LANE = "hash-review"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def batch_by_id(priority: dict[str, Any], batch_id: str) -> dict[str, Any]:
    for batch in priority.get("review_batches") or []:
        if isinstance(batch, dict) and batch.get("id") == batch_id:
            return batch
    raise SystemExit(f"batch not found: {batch_id}")


def sessions_by_key(index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("session_key")): row
        for row in index.get("sessions") or []
        if isinstance(row, dict) and row.get("session_key")
    }


def priority_items_by_key(priority: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("session_key")): row
        for row in priority.get("session_items") or []
        if isinstance(row, dict) and row.get("session_key")
    }


def render_counts(counts: dict[str, Any]) -> str:
    return ", ".join(f"{key} {value}" for key, value in counts.items()) or "none"


def source_root_prefix(source: str) -> str:
    if source == "codex-history":
        return "codex-history"
    if source == "codex-sessions":
        return "codex-session"
    return "prompt-hash-session"


def source_owner_lane(source: str, cwd: str) -> str:
    if source == "codex-history":
        return "private-codex-history-corpus-index"
    if source == "codex-sessions" and cwd.endswith("/limen"):
        return "private-codex-session-limen-corpus-index"
    if source == "codex-sessions":
        return "private-codex-session-corpus-index"
    return "private-prompt-hash-corpus-index"


def source_status(source: str) -> str:
    if source == "codex-history":
        return "hash_receipt_sensitive_context_recorded"
    return "codex_session_sensitive_context_recorded"


def int_field(*values: Any) -> int:
    for value in values:
        try:
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def list_field(*values: Any) -> list[Any]:
    for value in values:
        if isinstance(value, list):
            return value
    return []


def classify_session(
    key: str,
    batch: dict[str, Any],
    priority_item: dict[str, Any] | None,
    session: dict[str, Any] | None,
) -> dict[str, Any]:
    source = str((priority_item or {}).get("source") or (session or {}).get("source") or "codex-sessions")
    cwd = str((session or {}).get("cwd") or "")
    prompt_hashes = list_field((priority_item or {}).get("prompt_hashes"), (session or {}).get("prompt_hashes"))
    prompt_events = int_field((priority_item or {}).get("prompt_events"), (session or {}).get("prompt_event_count"))
    unique_hashes = int_field((priority_item or {}).get("unique_prompt_hashes"), len(set(prompt_hashes)))
    duplicate_events = int_field((priority_item or {}).get("duplicate_prompt_events"), max(prompt_events - unique_hashes, 0))
    first_hash = str((priority_item or {}).get("first_prompt_hash") or (session or {}).get("first_prompt_hash") or "")
    last_hash = str((priority_item or {}).get("last_prompt_hash") or (session or {}).get("last_prompt_hash") or "")

    row: dict[str, Any] = {
        "root": f"{source_root_prefix(source)}-{key}",
        "session_key": key,
        "status": source_status(source),
        "owner_lane": source_owner_lane(source, cwd),
        "repo": OWNER_REPO,
        "source": source,
        "prompt_events": prompt_events,
        "unique_prompt_hashes": unique_hashes,
        "duplicate_prompt_events": duplicate_events,
        "evidence": (
            "Metadata-only review recorded aggregate prompt counts, prompt hash refs, "
            "and private corpus ownership; no prompt body or transcript text was copied."
        ),
        "next_action": (
            "Retain in the private Limen prompt-corpus index. Require a new explicit owner "
            "packet before creating repo work from this hash aggregate."
        ),
    }
    if first_hash:
        row["first_prompt_hash"] = first_hash
    if last_hash:
        row["last_prompt_hash"] = last_hash
    if cwd.endswith("/limen"):
        row["cwd_owner"] = "limen"
    if not prompt_hashes and batch.get("prompt_hashes"):
        row["batch_hash_refs_available"] = True
    return row


def build_receipt(batch_id: str) -> dict[str, Any]:
    priority = load_json(PRIORITY_INDEX)
    sessions = sessions_by_key(load_json(SESSION_INDEX))
    priority_items = priority_items_by_key(priority)
    batch = batch_by_id(priority, batch_id)
    lane = str(batch.get("lane") or "")
    if lane != SUPPORTED_LANE:
        raise SystemExit(f"{batch_id} is lane {lane!r}; supported lane: {SUPPORTED_LANE}")

    roots = []
    for session_key in batch.get("session_keys") or []:
        key = str(session_key)
        roots.append(classify_session(key, batch, priority_items.get(key), sessions.get(key)))

    source_counts = Counter(str(row.get("source") or "unknown") for row in roots)
    status_counts = Counter(str(row.get("status") or "unknown") for row in roots)
    duplicate_prompt_events = sum(int(row.get("duplicate_prompt_events") or 0) for row in roots)
    first_hash = next((str(row["first_prompt_hash"]) for row in roots if row.get("first_prompt_hash")), "")
    last_hash = next((str(row["last_prompt_hash"]) for row in reversed(roots) if row.get("last_prompt_hash")), "")
    prompt_hash_refs = list_field(batch.get("prompt_hashes"))

    evidence = [
        (
            f"private redacted batch metadata listed {len(roots)} hash-review session(s) "
            f"with source mix {render_counts(dict(source_counts.most_common()))}"
        ),
        (
            f"priority metadata represented {int_field(batch.get('prompt_events'))} prompt events, "
            f"{int_field(batch.get('unique_prompt_hashes'))} unique prompt hashes, and "
            f"{duplicate_prompt_events} duplicate prompt events"
        ),
        (
            "review used only metadata fields: batch id, source, session key, prompt-event counts, "
            "hash counts, first/last prompt hash refs, and private corpus owner lane"
        ),
        (
            f"recorded {len(prompt_hash_refs)} batch prompt hash ref(s) privately; tracked receipt keeps "
            "only aggregate counts and first/last refs"
        ),
        "no raw user, assistant, last-prompt, credential, account, billing, financial, health, or secret text was copied into this tracked receipt",
    ]

    receipt: dict[str, Any] = {
        "generated_at": utc_now(),
        "batch": batch_id,
        "band": batch.get("band"),
        "lane": lane,
        "status": "owner-recorded",
        "classification": (
            "private Codex hash-review aggregate routed to the Limen prompt-corpus index; "
            "raw session and history text remains private and is not delegated"
        ),
        "session_count": int_field(batch.get("session_count"), len(roots)),
        "session_keys": [str(key) for key in batch.get("session_keys") or []],
        "sources": dict(source_counts.most_common()),
        "prompt_events": int_field(batch.get("prompt_events")),
        "unique_prompt_hashes": int_field(batch.get("unique_prompt_hashes")),
        "duplicate_prompt_events": duplicate_prompt_events,
        "root_statuses": dict(status_counts.most_common()),
        "evidence": evidence,
        "next_action": (
            "Keep as private aggregate prompt-corpus context. Do not delegate, rehydrate, or paste raw text "
            "unless a later owner packet names a repo, path, predicate, and privacy-safe extraction boundary."
        ),
        "roots": roots,
    }
    if len(source_counts) == 1:
        receipt["source"] = next(iter(source_counts))
    if first_hash:
        receipt["first_prompt_hash"] = first_hash
    if last_hash:
        receipt["last_prompt_hash"] = last_hash
    return receipt


def receipt_exists(batch_id: str) -> bool:
    data = load_json(BATCH_RESOLUTION_RECEIPTS)
    return any(
        isinstance(row, dict) and str(row.get("batch") or row.get("batch_id") or row.get("id")) == batch_id
        for row in data.get("receipts") or []
    )


def append_receipt(receipt: dict[str, Any], *, replace: bool) -> None:
    data = load_json(BATCH_RESOLUTION_RECEIPTS)
    batch_id = str(receipt.get("batch"))
    if receipt_exists(batch_id) and not replace:
        raise SystemExit(f"receipt already exists for {batch_id}; pass --replace to update it")
    receipts = [
        row
        for row in data.get("receipts") or []
        if isinstance(row, dict) and str(row.get("batch") or row.get("batch_id") or row.get("id")) != batch_id
    ]
    receipts.append(receipt)
    data["generated_at"] = utc_now()
    data["receipts"] = receipts
    write_json(BATCH_RESOLUTION_RECEIPTS, data)


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve a hash-review prompt batch into a public-safe receipt.")
    parser.add_argument("batch_id")
    parser.add_argument("--write", action="store_true", help="append the receipt to docs/prompt-batch-resolution-receipts.json")
    parser.add_argument("--replace", action="store_true", help="replace an existing receipt for the same batch")
    args = parser.parse_args()

    if args.write and not args.replace and receipt_exists(args.batch_id):
        raise SystemExit(f"receipt already exists for {args.batch_id}; pass --replace to update it")
    receipt = build_receipt(args.batch_id)
    if args.write:
        append_receipt(receipt, replace=args.replace)
        print(f"wrote receipt for {args.batch_id} to {BATCH_RESOLUTION_RECEIPTS}")
    else:
        json.dump(receipt, sys.stdout, indent=2, sort_keys=True)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
