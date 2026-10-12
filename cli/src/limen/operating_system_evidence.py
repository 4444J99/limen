"""Redacted, bounded operating-system review over existing native corpus sources.

Occurrences are evidence candidates, not task completion or automatic policy.
Raw bodies never leave their existing private source. Event time owns coverage.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import sqlite3
from contextlib import ExitStack
from urllib.parse import quote
from collections import Counter, defaultdict
from datetime import UTC, datetime
from zoneinfo import ZoneInfo
import zstandard

RULES = {
    "runtime_storage": (
        r"(?:codex|claude|gemini|opencode|total)_quota|runtime.{0,30}quota|quota.{0,30}headroom",
        "4444J99/domus-genoma",
        "runtime-pool",
    ),
    "chezmoi_source": (
        r"chezmoi.{0,100}(?:conflict|inconsistent|overwrite|drift)|(?:conflict|inconsistent).{0,100}chezmoi",
        "4444J99/domus-genoma",
        "claude-source-parity",
    ),
    "native_visual": (
        r"(?:computer use|screenshot|native visual|screen capture).{0,150}(?:denied|blocked|not allowed|unavailable|permission)|not allowed to use the app",
        "4444J99/domus-genoma",
        "native-visual-smoke",
    ),
    "host_admission": (
        r"execution_priority_not_approved|swap-fraction|disk-throughput|host.admission.{0,100}(?:denied|blocked)",
        "4444J99/limen",
        "host-admission",
    ),
    "deployment_drift": (
        r"No such command.{0,30}runtime-quota|immutable.{0,60}runtime.{0,60}(?:stale|missing|unavailable)|source.{0,50}live.{0,50}drift",
        "4444J99/limen",
        "runtime-deployment-parity",
    ),
}
COMPILED = {key: re.compile(pattern, re.IGNORECASE | re.DOTALL) for key, (pattern, _, _) in RULES.items()}
PREFILTERS = {
    "runtime_storage": ("quota",),
    "chezmoi_source": ("chezmoi",),
    "native_visual": ("computer use", "screenshot", "native visual", "screen capture", "not allowed to use the app"),
    "host_admission": ("execution_priority_not_approved", "swap-fraction", "disk-throughput", "admission"),
    "deployment_drift": ("runtime", "drift"),
}


def matches_symptom(text, lowered, symptom):
    # Every rule is bounded to fewer than 200 characters around these anchors.
    # Searching only those neighborhoods avoids regex backtracking over embedded
    # tool dumps and image payloads while retaining the complete native record.
    for needle in PREFILTERS[symptom]:
        offset = 0
        while (found := lowered.find(needle, offset)) >= 0:
            if COMPILED[symptom].search(text[max(0, found - 200) : found + len(needle) + 200]):
                return True
            offset = found + len(needle)
    return False


FAILURE = re.compile(r"denied|blocked|not allowed|inconsistent state|error|failed|unavailable|exceeded", re.IGNORECASE)
RECEIPT = re.compile(r"https://github\.com/4444J99/(?:limen|domus-genoma)/(?:pull/\d+|commit/[a-f0-9]{40})(?![a-f0-9])")


def visual_cause(text):
    """Classify evidence without turning harness safeguards into local repairs."""
    lowered = text.lower()
    cases = (
        ("platform_policy", ("for safety reasons", "harness policy"), "platform_permission"),
        ("host_admission", ("execution_priority_not_approved", "swap-fraction"), "host-admission"),
        ("local_policy", ("limen_execution_policy", "managed policy", "local policy"), "source-policy-review"),
        (
            "macos_permission",
            ("accessibility permission", "screen recording permission", "tcc denied"),
            "domus-agent-host-permission",
        ),
        ("missing_window", ("cgwindownotfound",), "permitted-app-with-window"),
        ("tool_unavailable", ("tool unavailable", "tool not found"), "supported-tool-availability"),
    )
    for cause, needles, predicate in cases:
        if any(needle in lowered for needle in needles):
            return {"cause": cause, "acceptance_predicate": predicate, "automatic_permission_bypass": False}
    return {
        "cause": "unclassified",
        "acceptance_predicate": "inspect-exact-denial",
        "automatic_permission_bypass": False,
    }


def event_time(record):
    values = [record.get(key) for key in ("timestamp", "ts", "created_at", "observed_at", "generated_at", "run_at_iso")]
    payload = record.get("payload")
    if isinstance(payload, dict):
        values.extend((payload.get("timestamp"), payload.get("ts")))
    for value in values:
        try:
            if isinstance(value, (int, float)):
                return datetime.fromtimestamp(value / 1000 if value > 10**12 else value, UTC)
            if isinstance(value, str):
                result = datetime.fromisoformat(value)
                if result.tzinfo is not None:
                    return result
        except (ValueError, OverflowError, OSError):
            pass
    return None


def classify(record):
    payload = record.get("payload", record)
    if not isinstance(payload, dict):
        payload = record
    role = payload.get("role") or record.get("type")
    message = record.get("message")
    if isinstance(message, dict):
        role = message.get("role", role)
    kind = payload.get("type", record.get("type"))
    text = json.dumps(record, ensure_ascii=False)
    tool = (
        kind in {"function_call_output", "custom_tool_call_output", "tool_result", "tool"}
        or '"type": "tool_result"' in text
    )
    disposition = (
        "observed_failure"
        if tool and FAILURE.search(text)
        else "operator_input"
        if role in {"user", "user_message"}
        else "reported_context"
    )
    return text, disposition


def native_records(path, source, gaps, deadline):
    """Read native message containers and JSONL without modifying source stores."""
    if path.suffix in {".db", ".sqlite"}:
        try:
            with sqlite3.connect(
                "file:" + quote(str(path.resolve()), safe="/") + "?mode=ro", uri=True, timeout=5
            ) as connection:
                connection.execute("PRAGMA query_only=ON")
                connection.execute("BEGIN")
                connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 10000)
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {"message", "part"} <= tables:
                    gaps[(source, "unsupported_sqlite_schema")] += 1
                    return
                # OpenCode's message and part JSON are the native authoritative carriers.
                for table in ("message", "part"):
                    query = (
                        "SELECT p.id,p.data,m.data FROM part p LEFT JOIN message m ON m.id=p.message_id ORDER BY p.id"
                        if table == "part"
                        else "SELECT id,data,NULL FROM message ORDER BY id"
                    )
                    for row_id, raw, parent_raw in connection.execute(query):
                        try:
                            record = json.loads(raw)
                            if table == "part":
                                metadata = json.loads(parent_raw) if parent_raw else {}
                                record = {
                                    "timestamp": metadata.get("time", {}).get("created"),
                                    "role": metadata.get("role"),
                                    "payload": record,
                                }
                            elif isinstance(record.get("time"), dict):
                                record = {**record, "timestamp": record["time"].get("created")}
                            yield table + ":" + str(row_id), record, hashlib.sha256(raw.encode()).hexdigest()
                        except (ValueError, TypeError, AttributeError):
                            gaps[(source, "unparsed_record")] += 1
        except sqlite3.Error:
            gaps[(source, "sqlite_snapshot_error")] += 1
        return
    if path.suffix == ".json":
        # Gemini stores pretty-printed session objects with individually dated messages.
        if path.stat().st_size > 128 * 1024 * 1024:
            gaps[(source, "oversized_container")] += 1
            return
        try:
            document = json.loads(path.read_bytes())
            rows = document if isinstance(document, list) else document.get("messages", [document])
            for number, record in enumerate(rows, 1):
                if isinstance(record, dict):
                    yield number, record, hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
                else:
                    gaps[(source, "unparsed_record")] += 1
        except (ValueError, TypeError, AttributeError):
            gaps[(source, "unparsed_container")] += 1
        return
    with ExitStack() as stack:
        stream = stack.enter_context(path.open("rb"))
        if path.name.endswith(".jsonl.zst"):
            import io

            stream = stack.enter_context(io.BufferedReader(zstandard.ZstdDecompressor().stream_reader(stream)))
        number = 0
        while raw := stream.readline(128 * 1024 * 1024 + 1):
            number += 1
            if time.monotonic() >= deadline:
                gaps[(source, "deadline_reached")] += 1
                return
            if len(raw) > 128 * 1024 * 1024:
                while raw and not raw.endswith(b"\n"):
                    raw = stream.readline(8 * 1024 * 1024)
                gaps[(source, "oversized_record")] += 1
                continue
            try:
                record = json.loads(raw)
                if not isinstance(record, dict):
                    gaps[(source, "unparsed_record")] += 1
                    continue
                yield number, record, hashlib.sha256(raw).hexdigest()
            except (ValueError, UnicodeError):
                gaps[(source, "unparsed_record")] += 1


def review(sources, start, end, *, seconds=180):
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("explicit ordered aware date boundaries required")
    zone = ZoneInfo("America/New_York")
    months = []
    current = start.astimezone(zone).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while current < end:
        months.append(current.strftime("%Y-%m"))
        current = current.replace(year=current.year + (current.month == 12), month=current.month % 12 + 1)
    counts = defaultdict(Counter)
    gaps = Counter()
    occurrences = defaultdict(dict)
    private = []
    files = set()
    deadline = time.monotonic() + seconds
    for source, root, patterns in sources:
        # Reuse declared corpus roots; process only timestamped JSON/JSONL.
        if not root.exists():
            gaps[(source, "source_missing")] += 1
            continue
        source_deadline = min(deadline, time.monotonic() + max(2, seconds / len(sources)))
        for pattern in patterns:
            for path in root.rglob(pattern) if root.is_dir() else [root]:
                if time.monotonic() >= source_deadline:
                    gaps[(source, "deadline_reached")] += 1
                    break
                if not path.is_file():
                    continue
                if path.suffix not in {".jsonl", ".json", ".db", ".sqlite"} and not path.name.endswith(".jsonl.zst"):
                    gaps[(source, "unsupported_format")] += 1
                    continue
                try:
                    info = path.stat()
                    key = (info.st_dev, info.st_ino)
                    if key in files:
                        continue
                    files.add(key)
                    for number, record, fingerprint in native_records(path, source, gaps, source_deadline):
                        stamp = event_time(record)
                        if stamp is None:
                            gaps[(source, "undated_record")] += 1
                            continue
                        if not start <= stamp < end:
                            continue
                        month = stamp.astimezone(zone).strftime("%Y-%m")
                        counts[source][month] += 1
                        text, disposition = classify(record)
                        lowered = text.lower()
                        for symptom in COMPILED:
                            if not matches_symptom(text, lowered, symptom):
                                continue
                            occurrence = {
                                "id": fingerprint[:20],
                                "source": source,
                                "timestamp": stamp.isoformat(),
                                "disposition": disposition,
                                "receipt_candidates": sorted(set(RECEIPT.findall(text))),
                            }
                            lineage = {
                                key: hashlib.sha256(str(record[key]).encode()).hexdigest()[:20]
                                for key in ("sessionId", "session_id", "uuid", "parentUuid", "messageID", "turn_id")
                                if record.get(key) is not None
                            }
                            lineage["capsule"] = hashlib.sha256(
                                str(path.resolve()).removesuffix(".zst").encode()
                            ).hexdigest()[:20]
                            occurrence["lineage"] = lineage
                            occurrence["correction_input"] = disposition == "operator_input" and bool(
                                re.search(
                                    r"\b(?:instead|correction|correct|preserve|don't|do not|should|must)\b", text, re.I
                                )
                            )
                            if symptom == "native_visual":
                                occurrence["visual_classification"] = visual_cause(text)
                            occurrences[symptom][fingerprint] = occurrence
                            private.append(
                                {"symptom": symptom, "sha256": fingerprint, "path": str(path), "line": number}
                            )
                except (OSError, zstandard.ZstdError):
                    gaps[(source, "read_error")] += 1
    providers = sorted({source for source, _, _ in sources})
    public = {
        "schema": "limen.operating_system_evidence.v1",
        "observed_at": datetime.now(UTC).isoformat(),
        "window": {"start": start.isoformat(), "end_exclusive": end.isoformat()},
        "scope": "Declared native JSONL, message JSON and OpenCode SQLite snapshot census; missing or non-message artifacts remain explicit. No observed records is not absence of failures.",
        "coverage": [
            {
                "source": source,
                "months": {
                    month: {
                        "records": counts[source][month],
                        "status": "observed" if counts[source][month] else "no_observed_records",
                    }
                    for month in months
                },
            }
            for source in providers
        ],
        "gaps": [
            {"source": source, "reason": reason, "count": count} for (source, reason), count in sorted(gaps.items())
        ],
        "symptoms": [],
    }
    for symptom, (_, owner, predicate) in RULES.items():
        rows = sorted(occurrences[symptom].values(), key=lambda row: (row["timestamp"], row["id"]))
        preceding = {}
        for row in rows:
            capsule = row["lineage"].get("capsule")
            if row["correction_input"] and capsule in preceding:
                row["correction_after"] = preceding[capsule]
            if row["disposition"] == "operator_input":
                preceding[capsule] = row["id"]
        public["symptoms"].append(
            {
                "key": symptom,
                "owner": owner,
                "predicate": predicate,
                "status": "requires_live_reconciliation",
                "counts": dict(Counter(row["disposition"] for row in rows)),
                "occurrences": rows,
            }
        )
    return public, private


def link_receipts(public, resolve):
    """Bind repository-qualified candidates to exact live identities, never completion."""
    urls = sorted(
        {url for symptom in public["symptoms"] for row in symptom["occurrences"] for url in row["receipt_candidates"]}
    )
    receipts = []
    for url in urls:
        try:
            identity = resolve(url)
            if not isinstance(identity, dict) or not re.fullmatch("[0-9a-f]{40}", identity.get("sha", "")):
                raise ValueError()
            receipts.append({"url": url, "status": "identity_verified", **identity})
        except (OSError, ValueError, TimeoutError):
            receipts.append({"url": url, "status": "identity_unavailable"})
    public["receipt_verifications"] = receipts
    public["receipt_verified_at"] = datetime.now(UTC).isoformat()
    return public


def render(public):
    lines = [
        "# Shared operating-system evidence review",
        "",
        f"Window: {public['window']['start']} to {public['window']['end_exclusive']} (exclusive).",
        "",
        public["scope"],
        "",
        "| Source | " + " | ".join(next(iter(public["coverage"]), {"months": {}})["months"]) + " |",
        "|---|" + "---|" * len(next(iter(public["coverage"]), {"months": {}})["months"]),
    ]
    for row in public["coverage"]:
        lines.append(
            "| " + row["source"] + " | " + " | ".join(str(cell["records"]) for cell in row["months"].values()) + " |"
        )
    lines.extend(
        [
            "",
            "Zero means no observed records, never proof of no failures.",
            "",
            "| Symptom | Observed tool failures | Operator input | Reported context | Owner |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for row in public["symptoms"]:
        lines.append(
            f"| {row['key']} | {row['counts'].get('observed_failure', 0)} | {row['counts'].get('operator_input', 0)} | {row['counts'].get('reported_context', 0)} | {row['owner']} |"
        )
    lines.extend(
        [
            "",
            "Coverage gaps: " + json.dumps(public["gaps"], sort_keys=True),
            "",
            "Receipt candidates require repository-qualified live head verification. Chronological occurrences preserve corrections without automatically superseding prior intent.",
            "",
        ]
    )
    return "\n".join(lines)
