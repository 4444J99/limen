import collections
import hashlib
import json
import sys
import time
from compression import zstd
from pathlib import Path

BASE = Path(".limen-private/prompt-sequence-study")
HEADERS = json.loads((BASE / "native-session-header-index.json").read_text())
PATHS = sorted(
    {Path(e["path"]) for e in HEADERS["entries"] if e["kind"] == "direct_candidate"},
    key=lambda p: (p.name, str(p)),
    reverse=True,
)
OFFSET = int(sys.argv[1]) if len(sys.argv) > 1 else 0
START = time.monotonic()
LIMIT = 128 * 1024 * 1024
PREFIXES = (
    "# AGENTS.md instructions",
    "<environment_context>",
    "<codex_internal_context",
    "<turn_aborted>",
    "<subagent_notification>",
    "<external_codex_apps_open_page>",
    "<skill>",
    "<session_context>",
)


def read_session(path):
    before = path.stat()
    opener = zstd.open if path.suffix == ".zst" else open
    digest = hashlib.sha256()
    byte_count = 0
    prompts = []
    excluded = []
    current = None
    last_reply = None
    metas = []
    compactions = 0
    count = 0

    def finish():
        if current is not None and not current["finals"] and last_reply:
            current["finals"].append({**last_reply, "phase_inferred": True})

    with opener(path, "rb") as stream:
        for line_no in range(1, 200001):
            if time.monotonic() - START > 20:
                raise TimeoutError("tranche_deadline")
            line = stream.readline(4 * 1024 * 1024 + 1)
            if not line:
                break
            byte_count += len(line)
            if byte_count > LIMIT:
                raise ValueError("unit_128MiB_limit")
            if len(line) > 4 * 1024 * 1024:
                raise ValueError("record_4MiB_limit")
            digest.update(line)
            r = json.loads(line)
            q = r.get("payload", {})
            count = line_no
            if r.get("type") == "session_meta":
                metas.append(q)
            if r.get("type") == "compacted":
                compactions += 1
            if r.get("type") != "response_item":
                continue
            if q.get("role") == "user":
                text = "\n".join(
                    b.get("text", "")
                    for b in q.get("content", [])
                    if isinstance(b, dict) and b.get("type") == "input_text"
                )
                if text.lstrip().startswith(PREFIXES):
                    excluded.append({"line": line_no, "reason": "harness_or_expansion"})
                    continue
                finish()
                retained = (r.get("metadata") or {}).get("retained_source")
                current = {
                    "line": line_no,
                    "id": q.get("id"),
                    "timestamp": r.get("timestamp"),
                    "text": text,
                    "media": [
                        b.get("type")
                        for b in q.get("content", [])
                        if isinstance(b, dict) and b.get("type") != "input_text"
                    ],
                    "retained_complete": retained.get("complete") if isinstance(retained, dict) else None,
                    "finals": [],
                    "tool_calls": 0,
                }
                prompts.append(current)
                last_reply = None
            elif current is not None and q.get("role") == "assistant":
                reply = "\n".join(
                    b.get("text", "")
                    for b in q.get("content", [])
                    if isinstance(b, dict) and b.get("type") == "output_text"
                )
                if reply:
                    last_reply = {"line": line_no, "text": reply}
                    if q.get("phase") in ("final_answer", "final") or q.get("channel") == "final":
                        current["finals"].append(last_reply)
            elif current is not None and q.get("type") in ("function_call", "custom_tool_call"):
                current["tool_calls"] += 1
        else:
            raise ValueError("unit_record_limit")
    finish()
    after = path.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError("native_changed_during_read")
    meta = metas[0] if metas else {}
    return {
        "id": meta.get("id", meta.get("session_id")),
        "path": str(path),
        "cwd": meta.get("cwd"),
        "decompressed_sha256": digest.hexdigest(),
        "decompressed_bytes": byte_count,
        "records": count,
        "source_eof": True,
        "compactions": compactions,
        "metadata_records": len(metas),
        "excluded": excluded,
        "prompts": prompts,
    }


sessions = []
failures = []
last = OFFSET
counts = collections.Counter()
for index, path in enumerate(PATHS[OFFSET:], OFFSET):
    if time.monotonic() - START > 18:
        break
    try:
        session = read_session(path)
        if len(session["prompts"]) >= 2:
            sessions.append(session)
        else:
            counts["fewer_than_2_candidate_prompts"] += 1
    except Exception as exc:
        failures.append(
            {
                "path": str(path),
                "reason": str(exc) if isinstance(exc, (ValueError, TimeoutError)) else type(exc).__name__,
            }
        )
        if isinstance(exc, TimeoutError):
            break
    last = index + 1
destination = BASE / ("native-stream-" + str(OFFSET).zfill(4) + ".json")
if destination.exists():
    raise SystemExit("Preserve the existing tranche; do not overwrite.")
result = {
    "offset": OFFSET,
    "next_offset": last,
    "population_files": len(PATHS),
    "sessions": sessions,
    "failures": failures,
    "counts": dict(counts),
    "elapsed_seconds": round(time.monotonic() - START, 3),
}
destination.write_text(json.dumps(result, indent=2))
destination.chmod(0o600)
print(
    json.dumps(
        {
            **{k: v for k, v in result.items() if k not in ("sessions", "failures")},
            "captured_multi_prompt_files": len(sessions),
            "captured_prompt_rows": sum(len(s["prompts"]) for s in sessions),
            "all_bodies_marked_complete_files": sum(
                all(p["retained_complete"] is True for p in s["prompts"]) for s in sessions
            ),
            "failures": len(failures),
            "failure_reasons": dict(collections.Counter(e["reason"] for e in failures)),
        }
    )
)
