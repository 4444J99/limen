import json
from datetime import datetime
from zoneinfo import ZoneInfo

from limen.operating_system_evidence import review, visual_cause, link_receipts, compressed_patterns, provider_inventory

ZONE = ZoneInfo("America/New_York")
START = datetime(2026, 4, 12, tzinfo=ZONE)
END = datetime(2026, 10, 13, tzinfo=ZONE)


def test_compressed_history_cannot_capture_recursive_sessions_and_all_providers_are_visible(tmp_path):
    import zstandard

    raw = (json.dumps({"timestamp": "2026-09-01T12:00:00Z", "content": "runtime quota blocked"}) + "\n").encode()
    (tmp_path / "history.jsonl").write_bytes(raw)
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "rollout.jsonl.zst").write_bytes(zstandard.ZstdCompressor().compress(raw))
    public, _ = review([("codex-history", tmp_path, compressed_patterns(("history.jsonl",)))], START, END)
    assert public["coverage"][0]["months"]["2026-09"]["records"] == 1
    provider_inventory(
        {
            "codex": {"path": tmp_path},
            "opaque-app": {"path": tmp_path, "opaque_payload": True},
            "unavailable-app": {"path": tmp_path / "absent"},
        },
        public,
    )
    providers = {row["provider"]: row for row in public["provider_coverage"]}
    assert providers["opaque-app"]["boundary"] == "opaque_payload_contract"
    assert providers["opaque-app"]["months"]["2026-09"]["scope"] == "content_not_reviewed"
    assert providers["unavailable-app"]["estate"] == "missing"


def test_boundaries_dedup_corrections_gaps_and_redaction(tmp_path):
    def row(stamp, text):
        return json.dumps({"timestamp": stamp, "payload": {"type": "function_call_output", "output": text}}) + "\n"

    first = row(
        "2026-04-12T04:00:00Z", "runtime quota blocked PRIVATE SECRET https://github.com/4444J99/limen/pull/2840"
    )
    (tmp_path / "events.jsonl").write_text(
        row("2026-04-12T03:59:59Z", "runtime quota blocked")
        + first
        + first
        + row("2026-10-13T03:59:59Z", "runtime quota corrected")
        + row("2026-10-13T04:00:00Z", "runtime quota blocked")
        + "{}\ninvalid\n"
    )
    public, private = review(
        [("codex", tmp_path, ("*.jsonl",)), ("missing", tmp_path / "absent", ("*.jsonl",))], START, END
    )
    symptom = next(item for item in public["symptoms"] if item["key"] == "runtime_storage")
    assert len(symptom["occurrences"]) == 2
    assert symptom["occurrences"][0]["receipt_candidates"] == ["https://github.com/4444J99/limen/pull/2840"]
    assert symptom["occurrences"][0]["timestamp"] < symptom["occurrences"][1]["timestamp"]
    assert "PRIVATE SECRET" not in json.dumps(public)
    assert str(tmp_path) not in json.dumps(public)
    assert len(private) == 3
    assert {item["reason"] for item in public["gaps"]} == {"source_missing", "undated_record", "unparsed_record"}
    assert (
        next(item for item in public["coverage"] if item["source"] == "codex")["months"]["2026-05"]["status"]
        == "no_observed_records"
    )


def test_visual_classification_preserves_platform_guard():
    assert visual_cause("Computer Use is not allowed to use the app for safety reasons")["cause"] == "platform_policy"
    assert visual_cause("cgWindowNotFound")["cause"] == "missing_window"
    assert visual_cause("screen recording permission denied")["cause"] == "macos_permission"
    assert visual_cause("execution_priority_not_approved")["cause"] == "host_admission"


def test_native_json_and_sqlite_parts_have_real_message_dates(tmp_path):
    import sqlite3

    stamp = "2026-09-01T12:00:00Z"
    (tmp_path / "gemini.json").write_text(
        json.dumps({"messages": [{"timestamp": stamp, "role": "user", "content": "runtime quota should be shared"}]})
    )
    with sqlite3.connect(tmp_path / "opencode.db") as connection:
        connection.execute("CREATE TABLE message(id TEXT, data TEXT)")
        connection.execute("CREATE TABLE part(id TEXT, message_id TEXT, data TEXT)")
        connection.execute(
            "INSERT INTO message VALUES (?,?)",
            ("m", json.dumps({"role": "assistant", "time": {"created": 1788264000000}})),
        )
        connection.execute(
            "INSERT INTO part VALUES (?,?,?)",
            ("p", "m", json.dumps({"type": "tool", "state": {"error": "runtime quota blocked"}})),
        )
    public, private = review([("native", tmp_path, ("*.json", "*.db"))], START, END)
    symptom = next(item for item in public["symptoms"] if item["key"] == "runtime_storage")
    assert symptom["counts"] == {"operator_input": 1, "observed_failure": 1}
    assert any(row["correction_input"] for row in symptom["occurrences"])
    assert not public["gaps"]
    assert any(row["line"] == "part:p" for row in private)


def test_losslessly_compressed_rollouts_preserve_evidence_and_dedup(tmp_path):
    import zstandard

    raw = (
        json.dumps(
            {
                "timestamp": "2026-06-01T12:00:00Z",
                "role": "user",
                "uuid": "private-id",
                "parentUuid": "private-parent",
                "content": "runtime quota should be shared",
            }
        )
        + "\n"
    ).encode()
    (tmp_path / "a.jsonl").write_bytes(raw)
    (tmp_path / "b.jsonl.zst").write_bytes(zstandard.ZstdCompressor().compress(raw))
    public, _ = review([("codex", tmp_path, ("*.jsonl", "*.jsonl.zst"))], START, END)
    symptom = next(item for item in public["symptoms"] if item["key"] == "runtime_storage")
    assert len(symptom["occurrences"]) == 1
    assert "private-id" not in json.dumps(public)
    assert set(symptom["occurrences"][0]["lineage"]) == {"uuid", "parentUuid", "capsule"}


def test_receipt_linkage_requires_exact_identity_and_preserves_unavailable():
    urls = ["https://github.com/4444J99/limen/pull/2849", "https://github.com/4444J99/limen/commit/" + "a" * 40]
    public = {"symptoms": [{"occurrences": [{"receipt_candidates": urls}]}]}

    def resolve(url):
        return {"sha": "b" * 40, "state": "open", "merged": False} if "/pull/" in url else {}

    link_receipts(public, resolve)
    rows = {row["url"]: row for row in public["receipt_verifications"]}
    assert rows[urls[0]]["sha"] == "b" * 40
    assert rows[urls[0]]["merged"] is False
    assert rows[urls[1]]["status"] == "identity_unavailable"
