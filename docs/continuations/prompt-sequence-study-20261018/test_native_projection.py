"""Projection fidelity checks use isolated SQLite fixtures, never native state."""

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("native_projection", BASE / "capture-native-projection.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def user(item_id, text, turn="t1", ordinal=1, extra=()):
    value = {
        "type": "userMessage",
        "id": item_id,
        "clientId": "client",
        "content": [{"type": "text", "text": text, "text_elements": []}, *extra],
    }
    return {"item_id": item_id, "turn_id": turn, "rollout_ordinal": ordinal, "item_type": "userMessage", "item": value}


def reply(text, turn="t1", ordinal=2):
    return {
        "item_id": "r" + str(ordinal),
        "turn_id": turn,
        "rollout_ordinal": ordinal,
        "item_type": "agentMessage",
        "item": {"type": "agentMessage", "id": "r" + str(ordinal), "text": text, "phase": "final_answer"},
    }


def test_exact_text_and_structured_parts_survive():
    text = "line one\n<quoted markup> & exact spaces  "
    extra = (
        {"type": "localImage", "path": "/private/example.png", "detail": "high"},
        {"type": "skill", "name": "closeout", "path": "/private/SKILL.md"},
    )
    result = MODULE.project_rows([user("u1", text, extra=extra)])
    prompt = result["prompts"][0]
    assert prompt["text"] == text
    assert prompt["extra_parts"] == list(extra)
    assert prompt["source_ref"] == {
        "kind": "native-history-item",
        "item_id": "u1",
        "turn_id": "t1",
        "rollout_ordinal": 1,
    }
    assert prompt["retained_complete"] is None


def test_late_reply_stays_with_its_native_turn():
    result = MODULE.project_rows(
        [
            user("u1", "continue", "t1", 1),
            user("u2", "status", "t2", 2),
            reply("first result", "t1", 3),
            reply("second result", "t2", 4),
        ]
    )
    assert result["prompts"][0]["finals"][0]["text"] == "first result"
    assert result["prompts"][1]["finals"][0]["text"] == "second result"


def test_two_user_items_in_one_turn_keep_ambiguous_attribution_visible():
    result = MODULE.project_rows(
        [user("u1", "first", ordinal=1), user("u2", "second", ordinal=2), reply("shared", ordinal=3)]
    )
    assert len(result["prompts"]) == 2
    assert all(p["response_attribution"] == "shared-native-turn" for p in result["prompts"])


def test_oversized_item_keeps_its_place_as_a_gap():
    item = user("u1", "not fetched")
    item["item"] = None
    item["source_error"] = "projection_item_4MiB_limit"
    result = MODULE.project_rows([item, user("u2", "next", "t2", 2)])
    assert len(result["prompts"]) == 2
    assert result["prompts"][0]["native_item_complete"] is False
    assert result["gaps"] == 1


def test_derived_goal_frame_is_retained_separately():
    result = MODULE.project_rows(
        [
            user("u1", "<codex_internal_context source='goal'>continue</codex_internal_context>"),
            user("u2", "real follow-up", "t2", 2),
        ]
    )
    assert [p["text"] for p in result["prompts"]] == ["real follow-up"]
    assert result["frames"][0]["source_ref"]["item_id"] == "u1"


def test_unknown_user_block_fails_closed():
    row = user("u1", "text", extra=({"type": "futureMeaning", "payload": "preserve me"},))
    with pytest.raises(ValueError, match="unsupported_user_content"):
        MODULE.project_rows([row])


def test_equal_ordinals_do_not_claim_known_order():
    result = MODULE.project_rows([user("u1", "a", "t1", 1), user("u2", "b", "t2", 1)])
    assert result["order_ambiguous"] is True


def test_sqlite_capture_is_target_bound_and_read_only(tmp_path):
    path = tmp_path / "history.sqlite"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE thread_items(thread_id TEXT,turn_id TEXT,item_id TEXT,rollout_ordinal INTEGER,item_type TEXT,item_json TEXT)"
    )
    rows = [user("u1", "retained"), reply("result")]
    for row in rows:
        connection.execute(
            "INSERT INTO thread_items VALUES(?,?,?,?,?,?)",
            (
                "wanted",
                row["turn_id"],
                row["item_id"],
                row["rollout_ordinal"],
                row["item_type"],
                json.dumps(row["item"]),
            ),
        )
    connection.execute(
        "INSERT INTO thread_items VALUES(?,?,?,?,?,?)",
        ("other", "x", "secret", 1, "userMessage", json.dumps(user("secret", "outside target")["item"])),
    )
    connection.commit()
    connection.close()
    before = path.read_bytes()
    result = MODULE.capture_database(path, ["wanted"])
    assert [s["id"] for s in result["sessions"]] == ["wanted"]
    assert result["sessions"][0]["prompts"][0]["text"] == "retained"
    assert path.read_bytes() == before


def test_utf8_byte_limit_does_not_count_only_characters(tmp_path):
    path = tmp_path / "history.sqlite"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE thread_items(thread_id TEXT,turn_id TEXT,item_id TEXT,rollout_ordinal INTEGER,item_type TEXT,item_json TEXT)"
    )
    raw = json.dumps(user("u1", "界" * 50)["item"], ensure_ascii=False)
    connection.execute("INSERT INTO thread_items VALUES(?,?,?,?,?,?)", ("wanted", "t1", "u1", 1, "userMessage", raw))
    connection.commit()
    connection.close()
    limit = len(raw) + 1
    assert len(raw.encode()) > limit
    result = MODULE.capture_database(path, ["wanted"], max_item_bytes=limit)
    assert result["sessions"][0]["gaps"] == 1


def native_message(role, text, turn, phase=None):
    payload = {
        "type": "message",
        "id": role + text[:4],
        "role": role,
        "content": [{"type": "input_text" if role == "user" else "output_text", "text": text}],
    }
    if turn is not None:
        payload["internal_chat_message_metadata_passthrough"] = {"turn_id": turn}
    if phase is not None:
        payload["phase"] = phase
    return {"type": "response_item", "payload": payload}


def test_rollout_goal_reply_does_not_become_human_outcome():
    rows = [
        native_message("user", "human opener", "t1"),
        native_message("assistant", "human result", "t1", "final_answer"),
        native_message("user", "<codex_internal_context>automatic continuation</codex_internal_context>", "goal2"),
        native_message("assistant", "automatic result", "goal2", "final_answer"),
        native_message("user", "status", "t3"),
        native_message("assistant", "status result", "t3", "final_answer"),
    ]
    result = MODULE.project_rollout_records(rows)
    assert [p["text"] for p in result["prompts"]] == ["human opener", "status"]
    assert [r["text"] for r in result["prompts"][0]["finals"]] == ["human result"]
    assert result["frames"][0]["finals"][0]["text"] == "automatic result"


def test_rollout_transport_echo_is_not_a_second_operator_prompt():
    primary = native_message("user", "continue", "t1")
    result = MODULE.project_rollout_records(
        [primary, {"type": "event_msg", "payload": {"type": "user_message", "message": "continue"}}]
    )
    assert len(result["prompts"]) == 1
    assert result["transport_echo_records"] == 1


def test_rollout_missing_native_turn_is_explicitly_unmeasured():
    result = MODULE.project_rollout_records(
        [native_message("user", "continue", None), native_message("assistant", "reported done", None, "final_answer")]
    )
    assert result["prompts"][0]["response_attribution"] == "adjacent-unbound"


def test_later_prompt_does_not_receive_an_earlier_native_turn_reply():
    result = MODULE.project_rows(
        [
            user("u1", "first", ordinal=1),
            reply("earlier outcome", ordinal=2),
            user("u2", "follow-up", ordinal=3),
            reply("later outcome", ordinal=4),
        ]
    )
    later = result["prompts"][1]
    assert [r["text"] for r in later["finals"]] == ["later outcome"]
    assert [r["rollout_ordinal"] for r in later["excluded_preceding_reply_refs"]] == [2]


def test_later_prompt_without_later_reply_keeps_its_outcome_missing():
    result = MODULE.project_rows(
        [user("u1", "first", ordinal=1), reply("earlier outcome", ordinal=2), user("u2", "follow-up", ordinal=3)]
    )
    later = result["prompts"][1]
    assert later["finals"] == []
    assert later["excluded_preceding_reply_refs"][0]["rollout_ordinal"] == 2


def test_rollout_later_commentary_does_not_inherit_an_earlier_final():
    result = MODULE.project_rollout_records(
        [
            native_message("user", "first", "t1"),
            native_message("assistant", "earlier outcome", "t1", "final_answer"),
            native_message("user", "follow-up", "t1"),
            native_message("assistant", "later commentary", "t1", "commentary"),
        ]
    )
    later = result["prompts"][1]
    assert [r["text"] for r in later["finals"]] == ["later commentary"]
    assert later["finals"][0]["phase_inferred"] is True
    excluded = later["excluded_preceding_reply_refs"][0]
    assert excluded["kind"] == "native-rollout-message"
    assert excluded["source_line"] == 2
