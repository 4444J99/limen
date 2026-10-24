"""Private metadata evidence must not become execution or acceptance authority."""

import base64
import copy
import hashlib
import importlib.util
import json
import os
import sqlite3
import stat
import subprocess
from pathlib import Path

import pytest


def test_private_cache_rejects_nonregular_file(tmp_path):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    fifo = private / "fifo"
    os.mkfifo(fifo, mode=0o600)
    with pytest.raises(ValueError, match="regular"):
        module()._private_path(fifo)


@pytest.mark.parametrize("interleave", ["assessments", "checkpoints"])
def test_export_is_one_consistent_read_snapshot(tmp_path, interleave):
    mod = module()
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    with mod.EvidenceStore(private / "shared.db") as reader, mod.EvidenceStore(private / "shared.db") as writer:
        reader._db.execute("PRAGMA journal_mode=WAL")  # permit a writer commit while the reader snapshot is open
        first = chat(mod)
        second = chat(mod, dict(task(), id="synthetic-second-task"), observed_at=LATER)
        reader.ingest([first])
        connection = reader._db
        appended = False

        class InterleavedConnection:
            def execute(self, sql, *args):
                nonlocal appended
                boundary = ("SELECT payload FROM assessments" if interleave == "assessments"
                            else "SELECT * FROM checkpoints")
                if sql.startswith(boundary) and not appended:
                    appended = True
                    writer.ingest([second])
                    writer.assess(second["observation_id"], status="accepted", owner_ref=second["owner_ref"],
                                  predicate="synthetic-predicate", evidence_ref="synthetic-receipt",
                                  artifact_sha256=second["artifact"]["sha256"])
                    writer.checkpoint("synthetic-source", {"observation_id": second["observation_id"]}, complete=True)
                return connection.execute(sql, *args)

            def __getattr__(self, name):
                return getattr(connection, name)

        reader._db = InterleavedConnection()
        exported = reader.export()
        assert appended
        assert (len(exported["observations"]), len(exported["assessments"]), len(exported["checkpoints"])) in {
            (1, 0, 0), (2, 1, 1)}
        identities = {row["observation_id"] for row in exported["observations"]}
        assert all(row["observation_id"] in identities for row in exported["assessments"])
        assert all(row["cursor"]["observation_id"] in identities for row in exported["checkpoints"])
        with mod.EvidenceStore(private / "restored.db") as restored:
            restored.import_snapshot(exported)
            assert restored.export() == exported
        assert len(reader.export()["observations"]) == 2


def test_export_preserves_outer_transaction_and_cleans_up_failed_read(tmp_path):
    mod = module()
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    with mod.EvidenceStore(private / "shared.db") as store:
        first = chat(mod)
        store._db.execute("BEGIN")
        store._ingest([first])
        assert len(store.export()["observations"]) == 1
        assert store._db.in_transaction
        store._db.rollback()
        assert store.export()["observations"] == []
        connection = store._db

        class BrokenRead:
            def execute(self, sql, *args):
                if sql.startswith("SELECT payload FROM assessments"):
                    raise sqlite3.OperationalError("synthetic broken SELECT")
                return connection.execute(sql, *args)

            def __getattr__(self, name):
                return getattr(connection, name)

        store._db = BrokenRead()
        with pytest.raises(sqlite3.OperationalError, match="synthetic"):
            store.export()
        assert not connection.in_transaction
        connection.execute("BEGIN")
        store._ingest([first])
        with pytest.raises(sqlite3.OperationalError, match="synthetic"):
            store.export()
        assert connection.in_transaction
        connection.rollback()

SCRIPT = Path(__file__).parents[1] / "_schedule_evidence.py"
NOW = "2026-10-23T12:00:00Z"
LATER = "2026-10-23T13:00:00Z"


def module():
    assert SCRIPT.is_file(), "schedule evidence adapter is not implemented"
    spec = importlib.util.spec_from_file_location("schedule_evidence", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def task():
    return {
        "id": "task-1", "prompt": "PRIVATE prompt", "source_ref": "native:task-1",
        "last_run": {"id": "run-2", "status": "completed",
                     "started_at": "2026-10-23T10:00:00Z",
                     "completed_at": "2026-10-23T10:02:00Z",
                     "scheduled_for": "2026-10-23T10:00:00Z"},
        "latest_result": {"id": "result-2", "run_id": "run-2",
                          "created_at": "2026-10-23T10:01:00Z",
                          "scheduled_for": "2026-10-23T11:00:00+01:00",
                          "content": "PRIVATE result", "coverage": "complete"},
    }


def chat(mod, value=None, observed_at=NOW):
    return mod.normalize_chatgpt(value or task(), observed_at=observed_at,
                                 account_ref="account:one", owner_ref="project:one")


def generic(**updates):
    return dict(provider="gemini", surface="apps", account_ref="account:one",
                owner_ref="project:one", source_ref="native:source",
                native_task_id="task-1", native_run_id="run-1",
                native_artifact_id="artifact-1", content="PRIVATE artifact",
                coverage="complete", attribution_evidence="receipt:match", **updates)


def email(body="PRIVATE email", mime="text/plain"):
    encoded = base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")
    return {"id": "gmail-1", "threadId": "thread-1", "internalDate": "1792750200000",
            "payload": {"mimeType": "multipart/mixed", "headers": [
                {"name": "From", "value": "Grok <noreply@x.ai>"}], "parts": [
                    {"mimeType": "multipart/alternative", "parts": [
                        {"mimeType": mime, "body": {"data": encoded}}]}]}}


def grok(mod, value=None):
    return mod.normalize_grok_email(value or email(), observed_at=NOW,
                                    account_ref="account:one", owner_ref="project:one")


def test_correlated_chatgpt_is_metadata_only_and_unassessed():
    row = chat(module())
    assert row["schema"] == "limen.schedule_observation.v1"
    assert row["attribution_state"] == "correlated"
    assert row["artifact"]["coverage"] == "complete"
    assert row["artifact"]["sha256"] == hashlib.sha256(b"PRIVATE result").hexdigest()
    assert row["artifact"]["byte_count"] == 14
    assert row["acceptance_state"] == "unassessed"
    assert row["delivery_state"] == row["capacity_state"] == "unknown"
    assert "PRIVATE" not in json.dumps(row)
    assert row["next_action"]


@pytest.mark.parametrize("field,value", [
    ("run_id", "old-run"), ("created_at", "2026-10-23T09:59:59Z"),
    ("scheduled_for", "2026-10-22T10:00:00Z"), ("created_at", None),
    ("created_at", "bad"), ("created_at", "2026-10-23T10:01:00"),
    ("scheduled_for", "2026-10-23T10:00:00"),
])
def test_retry_or_unknown_time_cannot_correlate(field, value):
    value_task = task()
    value_task["latest_result"][field] = value
    row = chat(module(), value_task)
    assert row["attribution_state"] == "unresolved"
    assert row["native_run_id"] == "run-2"
    assert row["artifact"]["run_id"] == value_task["latest_result"]["run_id"]
    assert row["native_artifact_id"] == "result-2"


def test_failed_run_keeps_surviving_output_and_null_history_is_unknown():
    value = task()
    value["last_run"]["status"] = "failed"
    row = chat(module(), value)
    assert row["execution_status"] == "failed"
    assert row["artifact"]["byte_count"] == 14
    value["last_run"] = value["latest_result"] = None
    row = chat(module(), value)
    assert row["execution_status"] == "unknown"
    assert row["attribution_state"] == "unresolved"


def test_stable_identity_excludes_poll_time_and_tracks_changed_facts():
    mod = module()
    assert chat(mod)["observation_id"] == chat(mod, observed_at=LATER)["observation_id"]
    changed = task()
    changed["last_run"]["status"] = "failed"
    assert chat(mod)["observation_id"] != chat(mod, changed)["observation_id"]
    changed = task()
    changed["latest_result"]["content"] = "changed"
    assert chat(mod)["observation_id"] != chat(mod, changed)["observation_id"]


def test_nested_grok_notification_is_partial_and_preserves_message_identity():
    row = grok(module())
    assert row["artifact"]["coverage"] == "partial"
    assert row["artifact"]["sha256"] == hashlib.sha256(b"PRIVATE email").hexdigest()
    assert row["native_artifact_id"] == "gmail-1"
    assert row["gmail_thread_id"] == "thread-1"
    assert row["times"]["gmail_internal_date"] == "1792750200000"
    assert row["native_run_id"] is None
    assert row["times"]["completed_at"] is None
    assert row["source_ref"] == "gmail:message:gmail-1"
    assert "PRIVATE" not in json.dumps(row)


@pytest.mark.parametrize("sender", [None, "noreply@x.ai.evil", "noreply@evil.ai",
                                       "noreply@x.ai, attacker@example.org"])
def test_grok_rejects_unverified_sender(sender):
    value = email()
    value["payload"]["headers"] = [] if sender is None else [{"name": "From", "value": sender}]
    with pytest.raises(ValueError):
        grok(module(), value)


def test_html_strips_markup_and_keeps_only_safe_native_links():
    html = ('<script>PRIVATE script</script><p>Hello &amp; welcome</p>'
            '<a href="https://grok.com/chat/safe-ID_2">Continue reading</a>'
            '<a href="https://grok.com/chat/token?secret=PRIVATE">track</a>'
            '<a href="https://grok.com/chat/id#PRIVATE">fragment</a>'
            '<a href="https://user:PRIVATE@grok.com/chat/id">credential</a>'
            '<a href="https://evil.test/unsubscribe/PRIVATE">unsubscribe</a>')
    row = grok(module(), email(html, "text/html"))
    assert row["native_links"] == ["https://grok.com/chat/safe-ID_2"]
    assert row["artifact"]["coverage"] == "partial"
    assert "PRIVATE" not in json.dumps(row)


def test_plain_text_is_preferred_over_html():
    value = email("plain")
    value["payload"]["parts"][0]["parts"].append(
        email("different", "text/html")["payload"]["parts"][0]["parts"][0])
    assert grok(module(), value)["artifact"]["sha256"] == hashlib.sha256(b"plain").hexdigest()


def test_generic_complete_artifact_requires_occurrence_and_attribution():
    mod = module()
    value = generic()
    row = mod.normalize_artifact(value, observed_at=NOW)
    assert row["attribution_state"] == "correlated"
    assert row["artifact"]["coverage"] == "complete"
    assert "PRIVATE" not in json.dumps(row)
    for field in ("native_run_id", "attribution_evidence"):
        incomplete = {**value, field: None}
        assert mod.normalize_artifact(incomplete, observed_at=NOW)["attribution_state"] == "unresolved"


@pytest.mark.parametrize("field,value", [("provider", None), ("surface", {}),
    ("account_ref", "x" * 2049), ("owner_ref", ""), ("source_ref", ["bad"]),
    ("coverage", "accepted"), ("content", {"PRIVATE": "body"}),
    ("native_run_id", {"PRIVATE": "bad"}), ("attribution_evidence", ["bad"])])
def test_generic_rejects_malformed_input_without_echoing_content(field, value):
    payload = generic()
    payload[field] = value
    with pytest.raises(ValueError) as exc:
        module().normalize_artifact(payload, observed_at=NOW)
    assert "PRIVATE" not in str(exc.value)


def test_private_store_deduplicates_polls_preserves_changed_history_and_permissions(tmp_path):
    mod = module()
    path = tmp_path / "private" / "evidence.sqlite"
    with mod.EvidenceStore(path) as store:
        assert store.ingest([chat(mod)])["inserted"] == 1
        assert store.ingest([chat(mod, observed_at=LATER)])["inserted"] == 0
        changed = task()
        changed["last_run"]["status"] = "failed"
        store.ingest([chat(mod, changed)])
        rows = store.export()["observations"]
        assert len(rows) == 2
        first = next(r for r in rows if r["execution_status"] == "completed")
        assert first["first_observed_at"] == NOW
        assert first["last_observed_at"] == LATER
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert b"PRIVATE" not in path.read_bytes()


def test_ingest_rejects_forged_id_atomically(tmp_path):
    mod = module()
    original = chat(mod)
    forged = copy.deepcopy(original)
    forged["execution_status"] = "failed"
    with mod.EvidenceStore(tmp_path / "private" / "evidence.sqlite") as store:
        with pytest.raises(ValueError):
            store.ingest([original, forged])
        assert store.export()["observations"] == []


def test_private_store_refuses_tracked_and_unignored_paths(tmp_path):
    mod = module()
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    tracked = tmp_path / "tracked.sqlite"
    tracked.touch()
    subprocess.run(["git", "-C", str(tmp_path), "add", "tracked.sqlite"], check=True)
    (tmp_path / ".gitignore").write_text("private/\ntracked.sqlite\n")
    for path in (tracked, tmp_path / "public.sqlite"):
        with pytest.raises(ValueError):
            mod.EvidenceStore(path)
    assert not (tmp_path / "public.sqlite").exists()
    with mod.EvidenceStore(tmp_path / "private" / "cache.sqlite") as store:
        assert store.export()["observations"] == []


def assess(store, row, status="accepted", **updates):
    args = dict(status=status, owner_ref="project:one", predicate="test:passed",
                evidence_ref="receipt:one", artifact_sha256=row["artifact"]["sha256"])
    args.update(updates)
    return store.assess(row["observation_id"], **args)


def test_acceptance_and_delivery_require_exact_prior_evidence(tmp_path):
    mod = module()
    row = chat(mod)
    with mod.EvidenceStore(tmp_path / "private" / "evidence.sqlite") as store:
        store.ingest([row])
        with pytest.raises(ValueError):
            assess(store, row, "delivered", destination_ref="project:destination")
        accepted = assess(store, row)
        assert accepted["status"] == "accepted"
        delivered = assess(store, row, "delivered", destination_ref="project:destination")
        assert delivered["artifact_sha256"] == row["artifact"]["sha256"]
        assert len(store.export()["assessments"]) == 2
        assert store.export()["observations"][0]["acceptance_state"] == "unassessed"


@pytest.mark.parametrize("updates", [{"artifact_sha256": "0" * 64},
    {"owner_ref": ""}, {"owner_ref": "other:owner"}, {"predicate": ""},
    {"evidence_ref": ""}, {"status": "complete"}])
def test_invalid_assessment_fails_closed(tmp_path, updates):
    mod = module()
    row = chat(mod)
    with mod.EvidenceStore(tmp_path / "private" / "evidence.sqlite") as store:
        store.ingest([row])
        with pytest.raises(ValueError):
            assess(store, row, **updates)
        assert store.export()["assessments"] == []


@pytest.mark.parametrize("kind", ["partial", "unresolved", "unknown"])
def test_partial_uncorrelated_or_unknown_output_cannot_be_accepted(tmp_path, kind):
    mod = module()
    value = task()
    if kind == "unresolved":
        value["latest_result"]["run_id"] = "other-run"
    else:
        value["latest_result"]["coverage"] = kind
    row = chat(mod, value)
    with mod.EvidenceStore(tmp_path / "private" / "evidence.sqlite") as store:
        store.ingest([row])
        with pytest.raises(ValueError):
            assess(store, row)


def test_partial_checkpoint_does_not_commit_and_snapshot_cannot_regress(tmp_path):
    mod = module()
    with mod.EvidenceStore(tmp_path / "private" / "evidence.sqlite") as store:
        assert store.checkpoint("source:one", {"page": 1}, complete=False) is False
        assert store.export()["checkpoints"] == []
        assert store.checkpoint("source:one", {"page": 1}, complete=True) is True
        older = store.export()
        store.checkpoint("source:one", {"page": 2}, complete=True)
        assert store.checkpoint("source:one", {"page": 3}, complete=False) is False
        with pytest.raises(ValueError):
            store.import_snapshot(older)
        assert store.export()["checkpoints"][-1]["cursor"] == {"page": 2}


def test_snapshot_union_preserves_history_assessments_and_rejects_forgery(tmp_path):
    mod = module()
    row = chat(mod)
    with mod.EvidenceStore(tmp_path / "one" / "evidence.sqlite") as one:
        one.ingest([row])
        assess(one, row)
        assess(one, row, "delivered", destination_ref="destination:one")
        snapshot = one.export()
    with mod.EvidenceStore(tmp_path / "two" / "evidence.sqlite") as two:
        other = task()
        other["last_run"]["status"] = "failed"
        two.ingest([chat(mod, other)])
        two.import_snapshot(snapshot)
        two.import_snapshot(snapshot)
        assert len(two.export()["observations"]) == 2
        assert len(two.export()["assessments"]) == 2
        forged = copy.deepcopy(snapshot)
        forged["assessments"][0]["artifact_sha256"] = "0" * 64
        with pytest.raises(ValueError):
            two.import_snapshot(forged)
        assert len(two.export()["assessments"]) == 2


def test_actual_connector_chatgpt_field_names_keep_old_artifact_identity():
    value = {"id": "task-native", "run_details": {
        "last_run": {"id": "attempt-new", "recorded_status": "failed",
                     "started_at": "2026-10-23T10:00:00Z",
                     "scheduled_for": "2026-10-23T10:00:00Z", "chat_ref": None},
        "latest_result": {"run_id": "attempt-old", "created_at": "2026-10-22T10:01:00Z",
                          "scheduled_for": "2026-10-22T10:00:00Z",
                          "completed_at": "2026-10-22T10:02:00Z",
                          "content_text": "PRIVATE surviving result", "content_truncated": False,
                          "chat_ref": None}, "delivery_status": "unknown"}}
    row = chat(module(), value)
    assert row["execution_status"] == "failed"
    assert row["native_run_id"] == "attempt-new"
    assert row["artifact"]["run_id"] == "attempt-old"
    assert row["attribution_state"] == "unresolved"
    assert row["artifact"]["coverage"] == "complete"
    assert row["artifact"]["ref"]
    assert row["times"]["artifact_completed_at"] == "2026-10-22T10:02:00Z"
    assert "PRIVATE" not in json.dumps(row)


def test_actual_connector_gmail_snake_case_html_body():
    value = {"id": "message-native", "thread_id": "thread-native",
             "internal_date": "1792750200000", "payload": {
                 "mime_type": "text/html", "headers": [
                     {"name": "From", "value": "Grok <noreply@x.ai>"}],
                 "body": {"content": "<p>Hello</p>", "base64_url_content": None}, "parts": []}}
    row = grok(module(), value)
    assert row["gmail_thread_id"] == "thread-native"
    assert row["artifact"]["sha256"] == hashlib.sha256(b"Hello").hexdigest()
    assert row["artifact"]["coverage"] == "partial"


def test_assessment_rejects_unknown_observation_and_missing_delivery_destination(tmp_path):
    mod = module()
    row = chat(mod)
    with mod.EvidenceStore(tmp_path / "private" / "evidence.sqlite") as store:
        with pytest.raises(ValueError):
            assess(store, row)
        store.ingest([row])
        assess(store, row)
        with pytest.raises(ValueError):
            assess(store, row, "delivered")


def test_checkpoint_conflict_rolls_back_entire_import(tmp_path):
    mod = module()
    with mod.EvidenceStore(tmp_path / "one" / "cache.sqlite") as one:
        one.ingest([chat(mod)])
        one.checkpoint("source:one", {"page": "other"}, complete=True)
        snapshot = one.export()
    with mod.EvidenceStore(tmp_path / "two" / "cache.sqlite") as two:
        two.checkpoint("source:one", {"page": "original"}, complete=True)
        with pytest.raises(ValueError):
            two.import_snapshot(snapshot)
        assert two.export()["observations"] == []
        assert two.export()["checkpoints"][0]["cursor"] == {"page": "original"}


def test_nested_private_directories_are_owner_only_and_symlinks_are_refused(tmp_path):
    mod = module()
    nested = tmp_path / "outer" / "inner" / "cache.sqlite"
    with mod.EvidenceStore(nested):
        assert stat.S_IMODE(nested.parent.parent.stat().st_mode) == 0o700
    link = tmp_path / "link"
    link.symlink_to(nested.parent, target_is_directory=True)
    with pytest.raises(ValueError):
        mod.EvidenceStore(link / "other.sqlite")


def test_store_rejects_missing_observation_time_without_partial_commit(tmp_path):
    mod = module()
    row = chat(mod)
    del row["observed_at"]
    with mod.EvidenceStore(tmp_path / "private" / "cache.sqlite") as store:
        with pytest.raises(ValueError):
            store.ingest([chat(mod), row])
        assert store.export()["observations"] == []


def test_snapshot_delivery_before_acceptance_fails_closed(tmp_path):
    mod = module()
    row = chat(mod)
    with mod.EvidenceStore(tmp_path / "one" / "cache.sqlite") as one:
        one.ingest([row])
        assess(one, row)
        assess(one, row, "delivered", destination_ref="destination:one")
        snapshot = one.export()
    snapshot["assessments"].reverse()
    with mod.EvidenceStore(tmp_path / "two" / "cache.sqlite") as two:
        with pytest.raises(ValueError):
            two.import_snapshot(snapshot)
        assert two.export()["observations"] == []
        assert two.export()["assessments"] == []


@pytest.mark.parametrize("native_type", ["chatgpt", "codex"])
def test_structured_chat_refs_preserve_native_type_and_identity(native_type):
    value = task()
    value["last_run"]["chat_ref"] = {"id": "run-chat", "type": native_type}
    value["latest_result"]["chat_ref"] = {"id": "result-chat", "type": native_type}
    row = chat(module(), value)
    assert row["native_run_ref"] == f"native:{native_type}:chat:run-chat"
    assert row["artifact"]["ref"] == f"native:{native_type}:chat:result-chat"


@pytest.mark.parametrize("reference", [
    {"id": "chat", "type": "other"}, {"id": {}, "type": "chatgpt"},
    {"id": "chat", "type": "chatgpt", "PRIVATE": "raw"}, {"type": "codex"},
    "https://chatgpt.com/c/id?token=PRIVATE", "https://user:PRIVATE@chatgpt.com/c/id",
    "https://chatgpt.com/c/id#PRIVATE",
])
def test_chatgpt_rejects_malformed_or_secret_bearing_references(reference):
    value = task()
    value["latest_result"]["chat_ref"] = reference
    with pytest.raises(ValueError) as exc:
        chat(module(), value)
    assert "PRIVATE" not in str(exc.value)


def test_null_native_run_details_is_unknown_history():
    row = chat(module(), {"id": "task-null", "run_details": None})
    assert row["execution_status"] == "unknown"
    assert row["native_run_id"] is None
    assert row["artifact"]["sha256"] is None
    assert row["attribution_state"] == "unresolved"


def test_existing_nonprivate_cache_parent_is_rejected_without_chmod(tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)
    with pytest.raises(ValueError):
        module().EvidenceStore(shared / "cache.sqlite")
    assert stat.S_IMODE(shared.stat().st_mode) == 0o755
    assert not (shared / "cache.sqlite").exists()


def test_native_truncation_caps_coverage_and_blocks_acceptance(tmp_path):
    mod = module()
    value = task()
    value["latest_result"].update(content_truncated=True, coverage="complete")
    row = chat(mod, value)
    assert row["artifact"]["coverage"] == "partial"
    assert row["artifact"]["truncated"] is True
    with mod.EvidenceStore(tmp_path / "private" / "cache.sqlite") as store:
        store.ingest([row])
        with pytest.raises(ValueError):
            assess(store, row)


@pytest.mark.parametrize("flag", [None, "false", 0, 1, {}, []])
def test_present_native_truncation_flag_requires_boolean(flag):
    value = task()
    value["latest_result"]["content_truncated"] = flag
    with pytest.raises(ValueError):
        chat(module(), value)


def rehash(row):
    """An importer can recompute hashes; hashing must not grant attribution."""
    canonical = {key: value for key, value in row.items() if key not in {
        "observation_id", "observed_at", "first_observed_at", "last_observed_at"}}
    row["observation_id"] = hashlib.sha256(json.dumps(
        canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    return row


@pytest.mark.parametrize("mutation", ["run", "created", "scheduled", "evidence", "coverage", "truncated"])
def test_rehashed_chatgpt_semantic_contradictions_cannot_be_ingested(tmp_path, mutation):
    mod = module()
    row = chat(mod)
    if mutation == "run":
        row["artifact"]["run_id"] = "older-run"
    elif mutation == "created":
        row["times"]["artifact_created_at"] = "2026-10-23T09:59:59Z"
    elif mutation == "scheduled":
        row["times"]["artifact_scheduled_for"] = "2026-10-22T10:00:00Z"
    elif mutation == "evidence":
        row["attribution_evidence"] = "unknown"
    elif mutation == "coverage":
        row["artifact"]["coverage"] = "partial"
    else:
        row["artifact"]["truncated"] = True
    rehash(row)
    with mod.EvidenceStore(tmp_path / "private" / "cache.sqlite") as store:
        with pytest.raises(ValueError):
            store.ingest([row])
        assert store.export()["observations"] == []


@pytest.mark.parametrize("mutation", ["complete", "correlated"])
def test_rehashed_grok_promotion_snapshot_is_rejected(tmp_path, mutation):
    mod = module()
    with mod.EvidenceStore(tmp_path / "private" / "cache.sqlite") as store:
        row = grok(mod)
        if mutation == "complete":
            row["artifact"]["coverage"] = "complete"
            row["collection_state"] = "complete"
        else:
            row["attribution_state"] = "correlated"
            row["attribution_evidence"] = "receipt:forged"
            row["native_run_id"] = row["artifact"]["run_id"] = "fabricated-run"
        snapshot = {"schema": "limen.schedule_snapshot.v1", "observations": [rehash(row)],
                    "assessments": [], "checkpoints": []}
        with pytest.raises(ValueError):
            store.import_snapshot(snapshot)
        assert store.export()["observations"] == []


def test_assessment_revalidates_persisted_semantics(tmp_path):
    mod = module()
    path = tmp_path / "private" / "cache.sqlite"
    with mod.EvidenceStore(path) as store:
        row = chat(mod)
        store.ingest([row])
        row["artifact"]["run_id"] = "contradictory-run"
        rehash(row)
        payload = {key: value for key, value in row.items()
                   if key not in {"observation_id", "observed_at"}}
        with sqlite3.connect(path) as connection:
            connection.execute("UPDATE observations SET id=?,payload=?",
                               (row["observation_id"], json.dumps(payload)))
        with pytest.raises(ValueError):
            assess(store, row)


def test_explicit_generic_owner_attestation_still_accepts(tmp_path):
    mod = module()
    row = mod.normalize_artifact(generic(), observed_at=NOW)
    with mod.EvidenceStore(tmp_path / "private" / "cache.sqlite") as store:
        store.ingest([row])
        assert assess(store, row)["status"] == "accepted"


def test_gmail_batch_null_parts_leaf_preserves_retrieved_body():
    value = email("retrieved notification")
    leaf = value["payload"]["parts"][0]["parts"][0]
    leaf["parts"] = None
    row = grok(module(), value)
    assert row["artifact"]["coverage"] == "partial"
    assert row["artifact"]["sha256"] == hashlib.sha256(b"retrieved notification").hexdigest()


def test_gmail_attachment_without_retrieved_bytes_stays_unavailable():
    value = email()
    leaf = value["payload"]["parts"][0]["parts"][0]
    leaf.update(body={"size": 100, "attachment_id": "attachment-native",
                      "content": None, "base64_url_content": None}, parts=None)
    row = grok(module(), value)
    assert row["collection_state"] == "unavailable"
    assert row["artifact"]["coverage"] == "unknown"
    assert row["artifact"]["sha256"] is None
    assert row["artifact"]["byte_count"] is None


@pytest.mark.parametrize("parts", ["malformed", {}, 0, False])
def test_gmail_nonnull_malformed_parts_still_reject(parts):
    value = email()
    value["payload"]["parts"][0]["parts"][0]["parts"] = parts
    with pytest.raises(ValueError):
        grok(module(), value)
