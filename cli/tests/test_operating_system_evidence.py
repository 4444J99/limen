import json
from datetime import datetime
from zoneinfo import ZoneInfo

from limen.operating_system_evidence import review, visual_cause

ZONE = ZoneInfo("America/New_York")
START = datetime(2026, 4, 12, tzinfo=ZONE)
END = datetime(2026, 10, 13, tzinfo=ZONE)


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
