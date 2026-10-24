"""Capture scoped native user/agent items without changing native SQLite state.

A complete projected item is not proof that its original prompt or logical session
survived retention. Source gaps and ambiguous response attribution remain visible.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3
import time

MAX_ITEM_BYTES = 4 * 1024 * 1024
DERIVED_PREFIXES = (
    "<codex_internal_context",
    "<environment_context>",
    "# AGENTS.md instructions",
    "<subagent_notification>",
    "<turn_aborted>",
    "<skill>",
    "<session_context>",
    "<external_codex_apps_open_page>",
)


def reference(row):
    return {
        "kind": "native-history-item",
        "item_id": row["item_id"],
        "turn_id": row["turn_id"],
        "rollout_ordinal": row["rollout_ordinal"],
    }


def project_rows(rows):
    rows = sorted(rows, key=lambda r: (r["rollout_ordinal"], r["item_id"]))
    ordinals = [r["rollout_ordinal"] for r in rows]
    prompts, frames = [], []
    users_by_turn = defaultdict(list)
    replies_by_turn = defaultdict(list)
    gaps = 0
    for row in rows:
        item = row.get("item")
        if item is not None and item.get("type") != row["item_type"]:
            raise ValueError("projection_item_type_mismatch")
        if row["item_type"] == "userMessage":
            if item is None:
                text, extra = "", []
                gaps += 1
            else:
                if set(item) != {"type", "id", "clientId", "content"} or not isinstance(item["content"], list):
                    raise ValueError("unsupported_user_item_schema")
                texts, extra = [], []
                for block in item["content"]:
                    if not isinstance(block, dict):
                        raise ValueError("unsupported_user_content")
                    if block.get("type") == "text":
                        if set(block) != {"type", "text", "text_elements"} or not isinstance(block["text"], str):
                            raise ValueError("unsupported_user_content")
                        texts.append(block["text"])
                    elif block.get("type") == "localImage" and set(block) == {"type", "path", "detail"}:
                        extra.append(block)
                    elif block.get("type") == "skill" and set(block) == {"type", "name", "path"}:
                        extra.append(block)
                    else:
                        raise ValueError("unsupported_user_content")
                text = "\n".join(texts)
            prompt = {
                "id": row["item_id"],
                "line": row["rollout_ordinal"],
                "source_label": "Native projection ordinal " + str(row["rollout_ordinal"]),
                "source_ref": reference(row),
                "text": text,
                "extra_parts": extra,
                "media": [p["type"] for p in extra],
                "retained_complete": None,
                "native_item_complete": item is not None,
                "source_error": row.get("source_error"),
                "finals": [],
                "tool_calls": 0,
            }
            users_by_turn[row["turn_id"]].append(prompt)
            (frames if text.lstrip().startswith(DERIVED_PREFIXES) else prompts).append(prompt)
        elif row["item_type"] == "agentMessage":
            if item is None:
                gaps += 1
                replies_by_turn[row["turn_id"]].append(
                    {
                        "text": "",
                        "source_ref": reference(row),
                        "native_item_complete": False,
                        "source_error": row.get("source_error"),
                    }
                )
            else:
                if not isinstance(item.get("text"), str):
                    raise ValueError("unsupported_agent_text")
                replies_by_turn[row["turn_id"]].append(
                    {
                        "text": item["text"],
                        "source_ref": reference(row),
                        "phase": item.get("phase"),
                        "native_item_complete": True,
                        "native_fields": {k: v for k, v in item.items() if k not in {"text", "type", "id"}},
                    }
                )
        else:
            raise ValueError("unsupported_projection_item_type")
    primary_ids = {id(prompt) for prompt in prompts}
    for turn_id, users in users_by_turn.items():
        replies = replies_by_turn[turn_id]
        turn_finals = [r for r in replies if r.get("phase") in {"final_answer", "final"}]
        if not turn_finals and replies:
            turn_finals = [{**replies[-1], "phase_inferred": True}]
        for prompt in users:
            ordinal = prompt["source_ref"]["rollout_ordinal"]
            later_replies = [r for r in replies if r["source_ref"]["rollout_ordinal"] > ordinal]
            finals = [r for r in later_replies if r.get("phase") in {"final_answer", "final"}]
            if not finals and later_replies:
                finals = [{**later_replies[-1], "phase_inferred": True}]
            preceding = [r["source_ref"].copy() for r in turn_finals if r["source_ref"]["rollout_ordinal"] <= ordinal]
            if preceding:
                prompt["excluded_preceding_reply_refs"] = preceding
            prompt["finals"] = finals
            prompt["response_attribution"] = (
                "shared-native-turn" if sum(id(user) in primary_ids for user in users) > 1 else "native-turn"
            )
    return {
        "prompts": prompts,
        "frames": frames,
        "gaps": gaps,
        "native_user_items": len(prompts) + len(frames),
        "order_ambiguous": len(ordinals) != len(set(ordinals)),
        "unpaired_agent_turns": len(set(replies_by_turn) - set(users_by_turn)),
    }


def project_rollout_records(records):
    """Use native message turn IDs; adjacency is explicitly unbound."""
    rows = []
    source = {}
    tools = Counter()
    transport_echoes = 0
    active_turn = None
    for number, entry in enumerate(records, 1):
        line, record = entry if isinstance(entry, tuple) else (number, entry)
        payload = record.get("payload") or {}
        if not isinstance(payload, dict):
            raise ValueError("unsupported_native_payload")
        if record.get("type") == "event_msg" and payload.get("type") == "user_message":
            transport_echoes += 1
            continue
        if record.get("type") != "response_item":
            continue
        metadata = payload.get("internal_chat_message_metadata_passthrough") or {}
        turn = metadata.get("turn_id") if isinstance(metadata, dict) else None
        if payload.get("type") in {"function_call", "custom_tool_call"}:
            tools[turn or active_turn] += 1
            continue
        role = payload.get("role")
        if payload.get("type") != "message" or role not in {"user", "assistant"}:
            continue
        bound = isinstance(turn, str) and bool(turn)
        if role == "assistant" and payload.get("phase", payload.get("channel")) in {"analysis", "reasoning"}:
            continue
        if role == "user":
            turn = turn or ("unbound-source-line:" + str(line))
            active_turn = turn
        else:
            turn = turn or active_turn or ("unbound-agent-line:" + str(line))
        item_id = payload.get("id") or ("source-line:" + str(line))
        blocks = payload.get("content") or []
        if not isinstance(blocks, list):
            raise ValueError("unsupported_native_content")
        extras = []
        texts = []
        unsupported = []
        for index, block in enumerate(blocks):
            if not isinstance(block, dict):
                raise ValueError("unsupported_native_content")
            text_type = "input_text" if role == "user" else "output_text"
            if block.get("type") == text_type and isinstance(block.get("text"), str):
                texts.append(block["text"])
            elif role == "user":
                extras.append(
                    {
                        "type": block.get("type"),
                        "source_block": index,
                        "sha256": hashlib.sha256(json.dumps(block, sort_keys=True).encode()).hexdigest(),
                    }
                )
                if block.get("type") != "input_image":
                    unsupported.append(block.get("type"))
        if role == "user":
            item = {
                "type": "userMessage",
                "id": item_id,
                "clientId": None,
                "content": [{"type": "text", "text": text, "text_elements": []} for text in texts],
            }
            retained = (record.get("metadata") or {}).get("retained_source")
        else:
            item = {
                "type": "agentMessage",
                "id": item_id,
                "text": "\n".join(texts),
                "phase": payload.get("phase", payload.get("channel")),
            }
            retained = None
        source[line] = {
            "bound": bound,
            "extra_parts": extras,
            "unsupported_parts": unsupported,
            "retained_complete": retained.get("complete") if isinstance(retained, dict) else None,
            "native_ordinal": record.get("ordinal"),
        }
        rows.append(
            {"item_id": item_id, "turn_id": turn, "rollout_ordinal": line, "item_type": item["type"], "item": item}
        )
    result = project_rows(rows)
    result["transport_echo_records"] = transport_echoes
    for prompt in [*result["prompts"], *result["frames"]]:
        line = prompt["source_ref"]["rollout_ordinal"]
        detail = source[line]
        prompt["retained_complete"] = detail["retained_complete"]
        prompt["extra_parts"] = detail["extra_parts"]
        prompt["media"] = [p["type"] for p in detail["extra_parts"]]
        prompt["unsupported_parts"] = detail["unsupported_parts"]
        if detail["unsupported_parts"]:
            prompt["native_item_complete"] = False
        prompt["tool_calls"] = tools[prompt["source_ref"]["turn_id"]]
        if not detail["bound"]:
            prompt["response_attribution"] = "adjacent-unbound"
        prompt["source_label"] = "Native rollout line " + str(line)
        prompt["source_ref"]["kind"] = "native-rollout-message"
        prompt["source_ref"]["source_line"] = line
        prompt["source_ref"]["native_ordinal"] = detail["native_ordinal"]
        for reply in prompt["finals"]:
            reply_line = reply["source_ref"]["rollout_ordinal"]
            reply["source_ref"]["kind"] = "native-rollout-message"
            reply["source_ref"]["source_line"] = reply_line
            if not source[reply_line]["bound"]:
                prompt["response_attribution"] = "adjacent-unbound"
        for excluded in prompt.get("excluded_preceding_reply_refs", []):
            excluded["kind"] = "native-rollout-message"
            excluded["source_line"] = excluded["rollout_ordinal"]
    return result


def capture_database(path, session_ids, max_item_bytes=MAX_ITEM_BYTES):
    if not 0 < max_item_bytes <= MAX_ITEM_BYTES:
        raise ValueError("projection_item_limit_invalid")
    targets = sorted(set(session_ids))
    if not targets:
        raise ValueError("projection_targets_empty")
    deadline = time.monotonic() + 20
    connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
    sessions = []
    try:
        connection.execute("BEGIN")
        query_only = connection.execute("PRAGMA query_only").fetchone()[0]
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for sid in targets:
            if time.monotonic() >= deadline:
                raise TimeoutError("projection_capture_deadline")
            query = """SELECT turn_id,item_id,rollout_ordinal,item_type,
                length(CAST(item_json AS BLOB)) AS source_bytes,
                CASE WHEN length(CAST(item_json AS BLOB)) <= ? THEN item_json END AS body
                FROM thread_items WHERE thread_id=? AND item_type IN ('userMessage','agentMessage')
                ORDER BY rollout_ordinal,item_id LIMIT 20001"""
            rows = []
            digest = hashlib.sha256()
            for record in connection.execute(query, (max_item_bytes, sid)):
                if len(rows) >= 20000:
                    raise ValueError("projection_record_limit")
                raw = record["body"]
                row = {
                    "turn_id": record["turn_id"],
                    "item_id": record["item_id"],
                    "rollout_ordinal": record["rollout_ordinal"],
                    "item_type": record["item_type"],
                    "source_bytes": record["source_bytes"],
                    "item": json.loads(raw) if raw is not None else None,
                }
                if raw is None:
                    row["source_error"] = "projection_item_4MiB_limit"
                digest.update(json.dumps(row, sort_keys=True, ensure_ascii=True).encode())
                rows.append(row)
            session = {"id": sid, "provider": "codex", "source_kind": "native-history-projection", **project_rows(rows)}
            tools = dict(
                connection.execute(
                    "SELECT turn_id,count(*) FROM thread_items WHERE thread_id=? AND item_type IN ('commandExecution','mcpToolCall') GROUP BY turn_id",
                    (sid,),
                ).fetchall()
            )
            for prompt in [*session["prompts"], *session["frames"]]:
                prompt["tool_calls"] = tools.get(prompt["source_ref"]["turn_id"], 0)
            if "thread_history_projection_state" in tables:
                cursor = connection.execute(
                    "SELECT next_rollout_byte_offset,next_rollout_ordinal FROM thread_history_projection_state WHERE thread_id=?",
                    (sid,),
                ).fetchone()
                session["native_cursor"] = dict(cursor) if cursor else None
            session["projection_items_sha256"] = digest.hexdigest()
            session["logical_session_complete"] = None
            sessions.append(session)
        connection.rollback()
    finally:
        connection.close()
    return {
        "schema": "limen.native_projection_snapshot.v1",
        "query_only": query_only == 1,
        "consistent_read_transaction": True,
        "max_item_bytes": max_item_bytes,
        "sessions": sessions,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[3]
    private = repo / ".limen-private/prompt-sequence-study"
    destination = args.output.resolve()
    if not destination.is_relative_to(private.resolve()) or destination.exists():
        raise SystemExit("Use a new file inside this checkout's private study root.")
    probes = []
    for filename in ("source-limit-db-probe.json", "missing-native-db-probe.json"):
        probes.extend(json.loads((private / filename).read_text()))
    ids = {r["session_id"] for r in probes if r.get("projected_user_items", 0) > 0}
    snapshot = capture_database(args.database, ids)
    headers = json.loads((private / "native-session-header-index.json").read_text())
    directories = {r["id"]: r["cwd"] for r in headers["entries"]}
    for session in snapshot["sessions"]:
        session["cwd"] = directories.get(session["id"])
        session["path"] = "native-projection:" + session["id"]
    destination.write_text(json.dumps(snapshot, indent=2))
    destination.chmod(0o600)
    print(
        json.dumps(
            {
                "target_threads": len(snapshot["sessions"]),
                "native_user_items": sum(s["native_user_items"] for s in snapshot["sessions"]),
                "candidate_prompts": sum(len(s["prompts"]) for s in snapshot["sessions"]),
                "derived_frames": sum(len(s["frames"]) for s in snapshot["sessions"]),
                "gaps": sum(s["gaps"] for s in snapshot["sessions"]),
                "ambiguous_order_threads": sum(s["order_ambiguous"] for s in snapshot["sessions"]),
                "logical_session_completeness": "unproven",
            }
        )
    )


if __name__ == "__main__":
    main()
