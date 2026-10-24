import json
import collections
import hashlib
import importlib.util
from pathlib import Path

repo = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("native_registry", repo / "scripts/insight-cross-vendor-ingest.py")
registry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registry)
roots = [
    Path(p).resolve()
    for p in registry.VENDOR_REGISTRY["codex"]["sessions_roots"]
    if Path(p).name == "archived_sessions"
]
paths = sorted({p for root in roots for p in root.rglob("rollout-*.jsonl")}, key=lambda p: p.name, reverse=True)
out = []
total = 0
skipped = collections.Counter()
scanned = 0
for p in paths:
    size = p.stat().st_size
    if size > 8 * 1024 * 1024:
        skipped["over_8MiB"] += 1
        continue
    if total + size > 64 * 1024 * 1024 or len(out) >= 12:
        break
    before = p.stat()
    data = p.read_bytes()
    after = p.stat()
    total += size
    scanned += 1
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        skipped["changed_during_read"] += 1
        continue
    try:
        rows = [json.loads(x) for x in data.splitlines()]
    except (json.JSONDecodeError, UnicodeDecodeError):
        skipped["invalid_jsonl"] += 1
        continue
    meta = next((r.get("payload", {}) for r in rows if r.get("type") == "session_meta"), {})
    sid = meta.get("id", meta.get("session_id"))
    if (
        meta.get("forked_from_id")
        or meta.get("parent_thread_id")
        or meta.get("thread_source") == "subagent"
        or isinstance(meta.get("source"), dict)
    ):
        skipped["fork_or_subagent"] += 1
        continue
    users = []
    excluded = []
    current = None
    for i, r in enumerate(rows):
        q = r.get("payload", {})
        if r.get("type") != "response_item":
            continue
        if q.get("role") == "user":
            text = "\n".join(
                b.get("text", "") for b in q.get("content", []) if isinstance(b, dict) and b.get("type") == "input_text"
            )
            prefix = text.lstrip()
            if prefix.startswith(
                (
                    "# AGENTS.md instructions",
                    "<environment_context>",
                    "<codex_internal_context",
                    "<turn_aborted>",
                    "<subagent_notification>",
                    "<external_codex_apps_open_page>",
                    "<skill>",
                    "<session_context>",
                )
            ):
                excluded.append({"line": i + 1, "reason": "harness_or_skill_expansion"})
                continue
            if not text.strip() and not q.get("content"):
                continue
            retained = (r.get("metadata") or {}).get("retained_source")
            current = {
                "line": i + 1,
                "id": q.get("id"),
                "text": text,
                "media": [
                    b.get("type") for b in q.get("content", []) if isinstance(b, dict) and b.get("type") != "input_text"
                ],
                "retained_complete": retained.get("complete") if isinstance(retained, dict) else None,
                "timestamp": r.get("timestamp"),
                "finals": [],
                "tool_calls": 0,
            }
            users.append(current)
        elif (
            current is not None
            and q.get("role") == "assistant"
            and (q.get("phase") in ("final_answer", "final") or q.get("channel") == "final")
        ):
            current["finals"].append(
                {
                    "line": i + 1,
                    "text": "\n".join(
                        b.get("text", "")
                        for b in q.get("content", [])
                        if isinstance(b, dict) and b.get("type") == "output_text"
                    ),
                }
            )
        elif current is not None and q.get("type") in ("function_call", "custom_tool_call"):
            current["tool_calls"] += 1
    if len(users) < 3:
        skipped["fewer_than_3_candidate_prompts"] += 1
        continue
    out.append(
        {
            "id": sid,
            "path": str(p),
            "source_sha256": hashlib.sha256(data).hexdigest(),
            "cwd": meta.get("cwd"),
            "originator": meta.get("originator"),
            "source": meta.get("source"),
            "bytes": size,
            "compactions": sum(r.get("type") == "compacted" for r in rows),
            "excluded": excluded,
            "prompts": users,
        }
    )
destination = repo / ".limen-private/prompt-sequence-study/native-archive-snapshot.json"
destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
if destination.exists():
    raise SystemExit("Snapshot already exists; preserve it and create a new reviewed tranche.")
destination.write_text(
    json.dumps(
        {
            "archive_population": len(paths),
            "files_read": scanned,
            "bytes_read": total,
            "skipped": dict(skipped),
            "sessions": out,
        },
        indent=2,
    )
)
destination.chmod(0o600)
print(
    json.dumps(
        {
            "population": len(paths),
            "files_read": scanned,
            "bytes_read": total,
            "skipped": dict(skipped),
            "sessions": [
                {
                    "id": s["id"],
                    "prompts": len(s["prompts"]),
                    "incomplete": sum(p["retained_complete"] is False for p in s["prompts"]),
                    "unknown": sum(p["retained_complete"] is None for p in s["prompts"]),
                    "finals": sum(len(p["finals"]) for p in s["prompts"]),
                    "opener": s["prompts"][0]["text"][:70],
                }
                for s in out
            ],
        }
    )
)
