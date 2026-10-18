"""Vendor archive prompt feed route, operator-authority guard and recurrence authority knob.

Every string here is synthetic. No real conversation text appears in this file.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "cli" / "src" / "limen" / "prompt_corpus.py"
SCRIPT = ROOT / "scripts" / "prompt-atom-ledger.py"

PROVIDER = "chatgpt"
FINGERPRINT = "0123456789abcdef" + "f" * 48
FINGERPRINT_NAME = hashlib.sha256(FINGERPRINT.encode("utf-8")).hexdigest()[:16]
DAY = "20261017"


def _load():
    spec = importlib.util.spec_from_file_location("limen_prompt_corpus_archive_feed", MODULE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _row(index: int, text: str, *, provider: str = PROVIDER, **changes) -> dict:
    row = {
        "source": f"archive-{provider}-messages",
        "session_ref": f"{provider}-conversation-{index // 2}",
        "event_ref": f"message-{provider}-{index:016x}",
        "event_index": index,
        "text_index": 0,
        "text": text,
        "timestamp": f"2026-07-11T12:{index:02d}:00Z",
        "source_locator": f"{provider}-conversation-{index // 2}#message-{index}",
        "body_kind": "direct",
        "provenance": "unknown_user_input",
    }
    row.update(changes)
    return row


def _write_feed(
    directory: Path,
    rows: list[dict],
    *,
    provider: str = PROVIDER,
    receipt_changes: dict | None = None,
    receipt_name: str | None = None,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    feed = directory / f"feed-{provider}-prompts.jsonl"
    content = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows).encode("utf-8")
    feed.write_bytes(content)
    receipt = {
        "feed_sha256": hashlib.sha256(content).hexdigest(),
        "rows": len(rows),
        "source_fingerprint": FINGERPRINT,
        "naming_version": 1,
    }
    receipt.update(receipt_changes or {})
    name = receipt_name or f"receipt-{provider}-prompts-{FINGERPRINT_NAME}-{DAY}.json"
    (directory / name).write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
    return feed


def _operator_event(text: str, *, event_ref: str, source: str = "fixture") -> dict:
    return {
        "source": source,
        "session_ref": "session-one",
        "event_ref": event_ref,
        "timestamp": "2026-07-11T12:00:00Z",
        "text": text,
        "body_kind": "direct",
        "provenance": "operator_typed",
    }


# ---------------------------------------------------------------------------
# load_archive_feed: receipt verification, source and provenance checks
# ---------------------------------------------------------------------------


def test_verified_feed_loads_every_row_in_order(tmp_path: Path):
    corpus = _load()
    rows = [_row(0, "Name the first synthetic ask."), _row(1, "Name the second synthetic ask.")]
    feed = _write_feed(tmp_path, rows)

    assert corpus.load_archive_feed(feed) == rows


def test_empty_feed_with_matching_receipt_loads_nothing(tmp_path: Path):
    corpus = _load()
    assert corpus.load_archive_feed(_write_feed(tmp_path, [])) == []


@pytest.mark.parametrize("name", ["prompts.jsonl", "feed-chatgpt-prompts.json", "feed-ChatGPT-prompts.jsonl"])
def test_feed_must_follow_the_naming_convention(tmp_path: Path, name: str):
    corpus = _load()
    feed = tmp_path / name
    feed.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="feed-<provider>-prompts.jsonl"):
        corpus.load_archive_feed(feed)


def test_feed_without_a_receipt_is_refused(tmp_path: Path):
    corpus = _load()
    feed = _write_feed(tmp_path, [_row(0, "A synthetic ask.")])
    next(tmp_path.glob("receipt-*.json")).unlink()
    with pytest.raises(ValueError, match="no receipt"):
        corpus.load_archive_feed(feed)


def test_feed_changed_after_its_receipt_is_refused(tmp_path: Path):
    corpus = _load()
    feed = _write_feed(tmp_path, [_row(0, "A synthetic ask.")])
    feed.write_bytes(feed.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="no receipt"):
        corpus.load_archive_feed(feed)


def test_row_count_must_match_the_receipt(tmp_path: Path):
    corpus = _load()
    feed = _write_feed(tmp_path, [_row(0, "A synthetic ask.")], receipt_changes={"rows": 2})
    with pytest.raises(ValueError, match="row count"):
        corpus.load_archive_feed(feed)


def test_boolean_row_count_is_not_a_count(tmp_path: Path):
    corpus = _load()
    feed = _write_feed(tmp_path, [_row(0, "A synthetic ask.")], receipt_changes={"rows": True})
    with pytest.raises(ValueError, match="row count"):
        corpus.load_archive_feed(feed)


def test_receipt_name_fingerprint_must_match_its_body(tmp_path: Path):
    corpus = _load()
    feed = _write_feed(tmp_path, [_row(0, "A synthetic ask.")], receipt_changes={"source_fingerprint": "e" * 64})
    with pytest.raises(ValueError, match="fingerprint"):
        corpus.load_archive_feed(feed)


def test_receipt_with_a_malformed_name_is_ignored(tmp_path: Path):
    corpus = _load()
    feed = _write_feed(
        tmp_path,
        [_row(0, "A synthetic ask.")],
        receipt_name=f"receipt-{PROVIDER}-prompts-nothex-{DAY}.json",
    )
    with pytest.raises(ValueError, match="no receipt"):
        corpus.load_archive_feed(feed)


def test_receipt_with_an_impossible_day_is_ignored(tmp_path: Path):
    corpus = _load()
    feed = _write_feed(
        tmp_path,
        [_row(0, "A synthetic ask.")],
        receipt_name=f"receipt-{PROVIDER}-prompts-{FINGERPRINT_NAME}-20261345.json",
    )
    with pytest.raises(ValueError, match="no receipt"):
        corpus.load_archive_feed(feed)


def test_two_receipts_for_the_same_bytes_are_ambiguous(tmp_path: Path):
    corpus = _load()
    feed = _write_feed(tmp_path, [_row(0, "A synthetic ask.")])
    receipt = next(tmp_path.glob("receipt-*.json"))
    (tmp_path / f"receipt-{PROVIDER}-prompts-{FINGERPRINT_NAME}-20261018.json").write_text(
        receipt.read_text(encoding="utf-8"), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="more than one"):
        corpus.load_archive_feed(feed)


def test_a_stale_receipt_for_older_bytes_does_not_block_the_current_one(tmp_path: Path):
    corpus = _load()
    stale = tmp_path / f"receipt-{PROVIDER}-prompts-{'a' * 16}-20260101.json"
    stale.write_text(json.dumps({"feed_sha256": "0" * 64, "rows": 9, "source_fingerprint": "a" * 64}))
    rows = [_row(0, "A synthetic ask.")]
    assert corpus.load_archive_feed(_write_feed(tmp_path, rows)) == rows


def test_a_receipt_for_another_provider_is_not_used(tmp_path: Path):
    corpus = _load()
    feed = _write_feed(tmp_path, [_row(0, "A synthetic ask.")])
    receipt = next(tmp_path.glob("receipt-*.json"))
    receipt.rename(tmp_path / f"receipt-claude-prompts-{FINGERPRINT_NAME}-{DAY}.json")
    with pytest.raises(ValueError, match="no receipt"):
        corpus.load_archive_feed(feed)


def test_row_from_a_non_archive_source_rejects_the_feed(tmp_path: Path):
    corpus = _load()
    feed = _write_feed(tmp_path, [_row(0, "A synthetic ask.", source="claude-projects")])
    with pytest.raises(ValueError, match="source other than archive-chatgpt-messages"):
        corpus.load_archive_feed(feed)


def test_row_from_another_providers_archive_source_rejects_the_feed(tmp_path: Path):
    corpus = _load()
    feed = _write_feed(tmp_path, [_row(0, "A synthetic ask.", source="archive-claude-messages")])
    with pytest.raises(ValueError, match="source other than"):
        corpus.load_archive_feed(feed)


@pytest.mark.parametrize("provenance", ["operator_typed", "delegated_task_frame", "transport_echo", None])
def test_row_with_any_other_provenance_rejects_the_feed(tmp_path: Path, provenance):
    corpus = _load()
    row = _row(0, "A synthetic ask.")
    if provenance is None:
        del row["provenance"]
    else:
        row["provenance"] = provenance
    with pytest.raises(ValueError, match="provenance must be unknown_user_input"):
        corpus.load_archive_feed(_write_feed(tmp_path, [row]))


def test_errors_never_echo_row_text(tmp_path: Path):
    corpus = _load()
    sentinel = "synthetic-sentinel-text-that-must-not-leak"
    feed = _write_feed(tmp_path, [_row(0, sentinel, provenance="operator_typed")])
    with pytest.raises(ValueError) as caught:
        corpus.load_archive_feed(feed)
    assert sentinel not in str(caught.value)


def test_repeated_event_reference_rejects_the_feed(tmp_path: Path):
    corpus = _load()
    rows = [_row(0, "First synthetic ask."), _row(1, "Second synthetic ask.", event_ref=_row(0, "")["event_ref"])]
    rows[1]["session_ref"] = rows[0]["session_ref"]
    with pytest.raises(ValueError, match="repeats an event reference"):
        corpus.load_archive_feed(_write_feed(tmp_path, rows))


def test_malformed_and_non_object_rows_reject_the_feed(tmp_path: Path):
    corpus = _load()
    for body in (b"{not json}\n", b"[1, 2]\n"):
        feed = tmp_path / f"{body[:2].hex()}" / f"feed-{PROVIDER}-prompts.jsonl"
        feed.parent.mkdir()
        feed.write_bytes(body)
        (feed.parent / f"receipt-{PROVIDER}-prompts-{FINGERPRINT_NAME}-{DAY}.json").write_text(
            json.dumps(
                {
                    "feed_sha256": hashlib.sha256(body).hexdigest(),
                    "rows": 1,
                    "source_fingerprint": FINGERPRINT,
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="not valid JSON|not an object"):
            corpus.load_archive_feed(feed)


def _write_raw_feed(directory: Path, content: bytes, *, rows: int) -> Path:
    """A feed whose exact bytes the test controls, with a receipt that names them."""

    directory.mkdir(parents=True, exist_ok=True)
    feed = directory / f"feed-{PROVIDER}-prompts.jsonl"
    feed.write_bytes(content)
    (directory / f"receipt-{PROVIDER}-prompts-{FINGERPRINT_NAME}-{DAY}.json").write_text(
        json.dumps(
            {"feed_sha256": hashlib.sha256(content).hexdigest(), "rows": rows, "source_fingerprint": FINGERPRINT}
        ),
        encoding="utf-8",
    )
    return feed


# ---------------------------------------------------------------------------
# The frozen row key list: nothing outside it reaches the ledger events
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["existing_occurrence_id", "atoms", "task_body", "duplicate_of", "authority"])
def test_row_with_a_key_outside_the_contract_rejects_the_feed(tmp_path: Path, key: str):
    corpus = _load()
    sentinel = "synthetic-sentinel-value-that-must-not-leak"
    rows = [_row(0, "First synthetic ask."), _row(1, "Second synthetic ask.", **{key: sentinel})]
    with pytest.raises(ValueError) as caught:
        corpus.load_archive_feed(_write_feed(tmp_path, rows))
    message = str(caught.value)
    assert repr(key) in message
    assert "outside the feed contract" in message
    assert message.endswith("feed-chatgpt-prompts.jsonl:2")
    assert sentinel not in message


def test_the_branch_key_is_the_one_optional_key(tmp_path: Path):
    corpus = _load()
    rows = [_row(0, "A synthetic ask."), _row(1, "An alternate synthetic ask.", branch="alternate")]
    assert corpus.load_archive_feed(_write_feed(tmp_path, rows)) == rows


@pytest.mark.parametrize(
    "key",
    [
        "body_kind",
        "event_index",
        "event_ref",
        "session_ref",
        "source_locator",
        "text",
        "text_index",
        "timestamp",
    ],
)
def test_row_missing_a_required_key_rejects_the_feed(tmp_path: Path, key: str):
    corpus = _load()
    row = _row(0, "A synthetic ask.")
    del row[key]
    with pytest.raises(ValueError, match="missing the key") as caught:
        corpus.load_archive_feed(_write_feed(tmp_path, [row]))
    assert repr(key) in str(caught.value)
    assert str(caught.value).endswith("feed-chatgpt-prompts.jsonl:1")


@pytest.mark.parametrize("value", [None, 7, ["a synthetic ask"], {"text": "a synthetic ask"}, True])
def test_row_text_must_be_a_string(tmp_path: Path, value):
    corpus = _load()
    row = _row(0, "A synthetic ask.")
    row["text"] = value
    with pytest.raises(ValueError, match="text is not a string") as caught:
        corpus.load_archive_feed(_write_feed(tmp_path, [row]))
    assert str(caught.value).endswith("feed-chatgpt-prompts.jsonl:1")


def test_a_feed_that_is_not_valid_utf8_is_refused_without_the_decoder_message(tmp_path: Path):
    corpus = _load()
    feed = _write_raw_feed(tmp_path, b'{"text": "\xff\xfe synthetic"}\n', rows=1)
    with pytest.raises(ValueError) as caught:
        corpus.load_archive_feed(feed)
    message = str(caught.value)
    assert message == "archive feed is not valid UTF-8: feed-chatgpt-prompts.jsonl"
    assert "0xff" not in message and "position" not in message
    assert caught.value.__cause__ is None and caught.value.__suppress_context__


def test_zero_row_feed_is_verified_against_its_receipt(tmp_path: Path):
    corpus = _load()
    feed = _write_raw_feed(tmp_path, b"", rows=0)
    assert feed.stat().st_size == 0
    assert corpus.load_archive_feed(feed) == []


def test_zero_row_feed_still_needs_a_receipt_that_says_zero(tmp_path: Path):
    corpus = _load()
    feed = _write_raw_feed(tmp_path, b"", rows=1)
    with pytest.raises(ValueError, match="row count differs"):
        corpus.load_archive_feed(feed)


# ---------------------------------------------------------------------------
# The script option end to end
# ---------------------------------------------------------------------------


def _run_script(tmp_path: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--root",
            str(tmp_path),
            "--private-root",
            str(tmp_path / "private"),
            "--public-markdown",
            str(tmp_path / "ledger.md"),
            "--public-snapshot",
            str(tmp_path / "ledger.json"),
            *extra,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_script_ingests_a_verified_feed_with_unknown_authority(tmp_path: Path):
    feed = _write_feed(
        tmp_path / "feeds",
        [_row(0, "Summarize the synthetic status report."), _row(1, "Draft the synthetic release note.")],
    )
    result = _run_script(tmp_path, "--archive-feed", str(feed), "--write")
    assert result.returncode == 0, result.stdout + result.stderr

    journal = tmp_path / "private" / "prompt-atoms" / "prompt-events.jsonl"
    occurrences = [
        row["occurrence"] for row in map(json.loads, journal.read_text(encoding="utf-8").splitlines()) if row
    ]
    assert len(occurrences) == 2
    assert {row["authority"] for row in occurrences} == {"unknown"}
    assert {row["provenance"] for row in occurrences} == {"unknown_user_input"}
    assert {row["source"] for row in occurrences} == {"archive-chatgpt-messages"}


def test_script_ingest_is_idempotent_for_the_same_feed(tmp_path: Path):
    feed = _write_feed(tmp_path / "feeds", [_row(0, "Summarize the synthetic status report.")])
    assert _run_script(tmp_path, "--archive-feed", str(feed), "--write").returncode == 0
    journal = tmp_path / "private" / "prompt-atoms" / "prompt-events.jsonl"
    before = journal.read_bytes()
    assert _run_script(tmp_path, "--archive-feed", str(feed), "--write").returncode == 0
    assert journal.read_bytes() == before


def test_script_accepts_the_option_more_than_once(tmp_path: Path):
    first = _write_feed(tmp_path / "one", [_row(0, "Summarize the synthetic status report.")])
    second = _write_feed(
        tmp_path / "two",
        [_row(0, "Summarize the synthetic status report.", provider="claude")],
        provider="claude",
    )
    result = _run_script(tmp_path, "--archive-feed", str(first), "--archive-feed", str(second), "--write")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 occurrences" in result.stdout


def test_script_refuses_a_tampered_feed_and_writes_nothing(tmp_path: Path):
    feed = _write_feed(tmp_path / "feeds", [_row(0, "Summarize the synthetic status report.")])
    feed.write_bytes(feed.read_bytes().replace(b"Summarize", b"Rewritten"))
    result = _run_script(tmp_path, "--archive-feed", str(feed), "--write")
    assert result.returncode == 2
    assert "cannot read archive feed" in result.stderr
    assert not (tmp_path / "private").exists()


def test_script_dry_run_verifies_the_feed_too(tmp_path: Path):
    feed = _write_feed(tmp_path / "feeds", [_row(0, "A synthetic ask.", provenance="operator_typed")])
    result = _run_script(tmp_path, "--archive-feed", str(feed))
    assert result.returncode == 2


def test_script_refuses_a_row_that_tries_to_alter_a_stored_record(tmp_path: Path):
    sentinel = "synthetic-sentinel-value-that-must-not-leak"
    feed = _write_feed(
        tmp_path / "feeds",
        [_row(0, "A synthetic ask.", existing_occurrence_id=sentinel, atoms=[{"text": sentinel}])],
    )
    result = _run_script(tmp_path, "--archive-feed", str(feed), "--write")
    assert result.returncode == 2
    assert "outside the feed contract" in result.stderr
    assert sentinel not in result.stdout + result.stderr
    assert not (tmp_path / "private").exists()


def test_script_reports_a_feed_that_is_not_valid_utf8_without_bytes(tmp_path: Path):
    feed = _write_raw_feed(tmp_path / "feeds", b"\xff\xfe\xfd\n", rows=1)
    result = _run_script(tmp_path, "--archive-feed", str(feed), "--write")
    assert result.returncode == 2
    assert "not valid UTF-8" in result.stderr
    assert "0xff" not in result.stderr and "position" not in result.stderr
    assert not (tmp_path / "private").exists()


def test_script_accepts_a_zero_row_feed_and_reports_zero_rows(tmp_path: Path):
    feed = _write_raw_feed(tmp_path / "feeds", b"", rows=0)
    dry = _run_script(tmp_path, "--archive-feed", str(feed))
    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert "verified: 0 row(s)" in dry.stdout
    written = _run_script(tmp_path, "--archive-feed", str(feed), "--write")
    assert written.returncode == 0, written.stdout + written.stderr
    assert "verified: 0 row(s)" in written.stdout


def test_events_jsonl_option_still_takes_operator_rows_for_other_sources(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    events.write_text(json.dumps(_operator_event("Keep the operator route open.", event_ref="one")) + "\n")
    result = _run_script(tmp_path, "--events-jsonl", str(events), "--write")
    assert result.returncode == 0, result.stdout + result.stderr


def test_events_jsonl_cannot_smuggle_operator_authority_into_an_archive_source(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    events.write_text(
        json.dumps(_operator_event("A synthetic ask.", event_ref="one", source="archive-chatgpt-messages")) + "\n"
    )
    result = _run_script(tmp_path, "--events-jsonl", str(events), "--write")
    assert result.returncode == 1
    assert "operator provenance is not permitted" in result.stderr
    assert "A synthetic ask." not in result.stdout + result.stderr


# ---------------------------------------------------------------------------
# The authority guard inside the ledger update
# ---------------------------------------------------------------------------


def test_guard_rejects_a_new_operator_occurrence_from_an_archive_source(tmp_path: Path):
    corpus = _load()
    with pytest.raises(ValueError, match="operator provenance is not permitted"):
        corpus.update_ledger(
            corpus.LedgerPaths.for_root(tmp_path),
            events=[_operator_event("A synthetic ask.", event_ref="one", source="archive-claude-messages")],
        )


def test_guard_rejects_every_archive_prefixed_family(tmp_path: Path):
    corpus = _load()
    with pytest.raises(ValueError, match="operator provenance is not permitted"):
        corpus.update_ledger(
            corpus.LedgerPaths.for_root(tmp_path),
            events=[_operator_event("A synthetic ask.", event_ref="one", source="archive-anything")],
        )


def test_guard_leaves_unknown_provenance_archive_rows_alone(tmp_path: Path):
    corpus = _load()
    event = _operator_event("A synthetic ask.", event_ref="one", source="archive-chatgpt-messages")
    event["provenance"] = "unknown_user_input"
    snapshot = corpus.update_ledger(corpus.LedgerPaths.for_root(tmp_path), events=[event])
    assert snapshot["coverage"]["occurrences"] == 1
    assert snapshot["coverage"]["operator_occurrences"] == 0


def test_guard_leaves_operator_rows_from_other_families_alone(tmp_path: Path):
    corpus = _load()
    snapshot = corpus.update_ledger(
        corpus.LedgerPaths.for_root(tmp_path),
        events=[_operator_event("Keep the operator route open.", event_ref="one")],
    )
    assert snapshot["coverage"]["operator_occurrences"] == 1


def test_guard_rejects_a_revision_that_would_make_an_archive_occurrence_operator(tmp_path: Path):
    corpus = _load()
    paths = corpus.LedgerPaths.for_root(tmp_path)
    text = "A synthetic ask that later gets revised."
    archived = _operator_event(text, event_ref="one", source="archive-chatgpt-messages")
    archived["provenance"] = "unknown_user_input"
    first = corpus.update_ledger(paths, events=[archived])
    occurrence_id = first["occurrences"][0]["occurrence_id"]

    # The revision names the stored archive occurrence but labels itself with an eligible source and operator
    # provenance. The proposal alone looks legitimate; only the resolved record carries the archive family.
    revision = _operator_event(text, event_ref="one", source="fixture")
    revision["existing_occurrence_id"] = occurrence_id
    revision["atoms"] = [{"text": text, "kind": "ask", "classifier_provenance": "fixture-adapter"}]
    with pytest.raises(ValueError, match="operator provenance is not permitted"):
        corpus.update_ledger(paths, events=[revision])

    stored, _atoms, errors = corpus.load_event_journal(paths.event_journal)
    assert errors == []
    assert {row["authority"] for row in stored if row["occurrence_id"] == occurrence_id} == {"unknown"}


def test_guard_rejects_a_revision_that_names_an_archive_source_directly(tmp_path: Path):
    corpus = _load()
    paths = corpus.LedgerPaths.for_root(tmp_path)
    text = "A synthetic ask that later gets revised."
    archived = _operator_event(text, event_ref="one", source="archive-chatgpt-messages")
    archived["provenance"] = "unknown_user_input"
    occurrence_id = corpus.update_ledger(paths, events=[archived])["occurrences"][0]["occurrence_id"]

    revision = _operator_event(text, event_ref="one", source="archive-chatgpt-messages")
    revision["existing_occurrence_id"] = occurrence_id
    revision["atoms"] = [{"text": text, "kind": "ask", "classifier_provenance": "fixture-adapter"}]
    with pytest.raises(ValueError, match="operator provenance is not permitted"):
        corpus.update_ledger(paths, events=[revision])


def test_eligibility_helper_reads_the_declared_prefixes():
    corpus = _load()
    assert corpus.source_family_operator_eligible("claude-projects") is True
    assert corpus.source_family_operator_eligible("fixture") is True
    assert corpus.source_family_operator_eligible("archive-chatgpt-messages") is False
    assert corpus.source_family_operator_eligible("") is True


@pytest.mark.parametrize("label", ["Archive-chatgpt-messages", "ARCHIVE-claude-messages", "  archive-chatgpt-messages"])
def test_eligibility_helper_ignores_case_and_padding_in_the_label(label: str):
    corpus = _load()
    assert corpus.source_family_operator_eligible(label) is False


def test_guard_rejects_an_archive_label_written_with_other_case_or_padding(tmp_path: Path):
    corpus = _load()
    with pytest.raises(ValueError, match="operator provenance is not permitted"):
        corpus.update_ledger(
            corpus.LedgerPaths.for_root(tmp_path),
            events=[_operator_event("A synthetic ask.", event_ref="one", source=" Archive-Chatgpt-Messages")],
        )


# ---------------------------------------------------------------------------
# recurrence_authorities
# ---------------------------------------------------------------------------


def _archive_event(text: str, *, event_ref: str) -> dict:
    event = _operator_event(text, event_ref=event_ref, source="archive-chatgpt-messages")
    event["provenance"] = "unknown_user_input"
    return event


def _recurrence_by_text(corpus, snapshot: dict) -> dict[tuple[str, str], float]:
    """Recurrence keyed by (occurrence authority, ask text); snapshot atoms carry the lineage id, not text."""

    occurrences = {row["occurrence_id"]: row for row in snapshot["occurrences"]}
    by_lineage = {
        (occurrences[atom["occurrence_id"]]["authority"], atom["lineage_id"]): atom["dimensions"]["recurrence"]
        for atom in snapshot["atoms"]
    }

    class Scores(dict):
        def __getitem__(self, key):
            authority, text = key
            return by_lineage[(authority, corpus.stable_id("pl", corpus.normalize_intent(text), length=24))]

    return Scores()


def _recurrence_events() -> list[dict]:
    # One operator ask also asked three times in the vendor archive, plus an archive-only ask asked four times.
    events = [_operator_event("Ship the synthetic owner receipt.", event_ref="operator-one")]
    events += [_archive_event("Ship the synthetic owner receipt.", event_ref=f"shared-{i}") for i in range(3)]
    events += [_archive_event("Tidy the synthetic scratch notes.", event_ref=f"archive-only-{i}") for i in range(4)]
    return events


def test_default_policy_has_no_recurrence_key_so_existing_digests_stay_put(tmp_path: Path):
    corpus = _load()
    policy = corpus.load_policy(tmp_path / "absent-policy.json")
    assert "recurrence_authorities" not in policy
    assert "recurrence_authorities" not in corpus.DEFAULT_POLICY
    assert corpus.recurrence_authorities(policy) == ("operator", "unknown", "derived")


def test_default_recurrence_counts_every_authority_as_before(tmp_path: Path):
    corpus = _load()
    snapshot = corpus.update_ledger(corpus.LedgerPaths.for_root(tmp_path), events=_recurrence_events())
    scores = _recurrence_by_text(corpus, snapshot)
    # Archive-only lineage is the maximum (4); the shared lineage has 1 operator + 3 archive = 4 too.
    assert scores[("operator", "Ship the synthetic owner receipt.")] == 1.0
    assert scores[("unknown", "Tidy the synthetic scratch notes.")] == 1.0


def test_operator_only_recurrence_stops_vendor_asks_rescaling_operator_atoms(tmp_path: Path):
    corpus = _load()
    paths = corpus.LedgerPaths.for_root(tmp_path)
    paths.policy.parent.mkdir(parents=True, exist_ok=True)
    paths.policy.write_text(json.dumps({"recurrence_authorities": ["operator"]}), encoding="utf-8")
    snapshot = corpus.update_ledger(paths, events=_recurrence_events())
    scores = _recurrence_by_text(corpus, snapshot)
    # Only the one operator ask counts, so it is the maximum; vendor-only lineages contribute nothing.
    assert scores[("operator", "Ship the synthetic owner receipt.")] == 1.0
    assert scores[("unknown", "Tidy the synthetic scratch notes.")] == 0.0
    assert scores[("unknown", "Ship the synthetic owner receipt.")] == 1.0


def test_operator_only_knob_changes_the_operator_score_when_the_vendor_lineage_dominates(tmp_path: Path):
    corpus = _load()
    events = [_operator_event("Ship the synthetic owner receipt.", event_ref="operator-one")]
    events += [_archive_event("Tidy the synthetic scratch notes.", event_ref=f"archive-only-{i}") for i in range(4)]

    default_snapshot = corpus.update_ledger(corpus.LedgerPaths.for_root(tmp_path / "default"), events=events)
    default_scores = _recurrence_by_text(corpus, default_snapshot)
    assert default_scores[("operator", "Ship the synthetic owner receipt.")] == 0.25

    knob_paths = corpus.LedgerPaths.for_root(tmp_path / "knob")
    knob_paths.policy.parent.mkdir(parents=True, exist_ok=True)
    knob_paths.policy.write_text(json.dumps({"recurrence_authorities": ["operator"]}), encoding="utf-8")
    knob_scores = _recurrence_by_text(corpus, corpus.update_ledger(knob_paths, events=events))
    assert knob_scores[("operator", "Ship the synthetic owner receipt.")] == 1.0


@pytest.mark.parametrize(
    "value, expected",
    [
        (["operator"], ("operator",)),
        (["derived", "operator"], ("operator", "derived")),
        (["operator", "bogus"], ("operator", "unknown", "derived")),
        ([], ("operator", "unknown", "derived")),
        ("operator", ("operator", "unknown", "derived")),
        (None, ("operator", "unknown", "derived")),
    ],
)
def test_recurrence_authorities_value_is_validated(tmp_path: Path, value, expected):
    corpus = _load()
    policy_file = tmp_path / "policy.json"
    policy_file.write_text(json.dumps({"recurrence_authorities": value}), encoding="utf-8")
    policy = corpus.load_policy(policy_file)
    assert corpus.recurrence_authorities(policy) == expected


def test_shipped_policy_file_does_not_set_the_knob():
    shipped = json.loads((ROOT / "docs" / "prompt-corpus-policy.json").read_text(encoding="utf-8"))
    assert "recurrence_authorities" not in shipped
