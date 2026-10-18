"""Tests for scripts/prompt-recurring-forms.py, the recurring-form index over the private ledger journal.

Every prompt string here is synthetic. Journals are built with the ledger's own occurrence and atom
functions, so the rows have the real shape, and written to a temporary private root.
"""

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prompt-recurring-forms.py"
ALIVE_SCRIPT = ROOT / "scripts" / "check-knowledge-alive.py"
CLI_SRC = ROOT / "cli" / "src"
SCRIPTS = ROOT / "scripts"
for _path in (str(CLI_SRC), str(SCRIPTS)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from limen.prompt_corpus import DEFAULT_POLICY, atoms_from_event, occurrence_from_event  # noqa: E402

SHARED_ASK = "Draft the quarterly synthetic summary for the shared fixture now."
OTHER_ASK = "Outline the synthetic migration plan with exact steps and owners."
SOLO_ASK = "Rename the synthetic widget catalog before the next review cycle."
TRIVIAL_ASK = "Keep going"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def forms():
    return _load(SCRIPT, "prompt_recurring_forms_under_test")


def journal_row(source: str, session: str, reference: str, text: str, *, locator: str | None = None, index: int = 0):
    event = {
        "source": source,
        "session_ref": session,
        "event_ref": reference,
        "event_index": index,
        "text_index": 0,
        "text": text,
        "timestamp": "2026-03-01T10:00:00Z",
        "source_locator": locator,
        "body_kind": "direct",
        "provenance": "unknown_user_input" if source.startswith("archive-") else "operator_typed",
    }
    occurrence = occurrence_from_event(event)
    atoms = atoms_from_event(occurrence, event, copy.deepcopy(DEFAULT_POLICY))
    occurrence.pop("raw_text")
    return {"occurrence": occurrence, "atoms": atoms}


def archive_row(provider: str, conversation: str, message: str, text: str, index: int = 0):
    return journal_row(
        f"archive-{provider}-messages",
        conversation,
        message,
        text,
        locator=f"{conversation}#{message}",
        index=index,
    )


def codex_row(session: str, reference: str, text: str, index: int = 0):
    return journal_row("codex-history", session, reference, text, index=index)


def write_journal(private_root: Path, rows: list[dict]) -> Path:
    directory = private_root / "prompt-atoms"
    directory.mkdir(parents=True, exist_ok=True)
    journal = directory / "prompt-events.jsonl"
    journal.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    return directory


def standard_rows() -> list[dict]:
    return [
        archive_row("chatgpt", "chatgpt-conv-one", "msg-a1", SHARED_ASK, 0),
        archive_row("claude", "claude-conv-one", "msg-b1", SHARED_ASK, 1),
        codex_row("session-one", "ref-1", SHARED_ASK, 2),
        archive_row("chatgpt", "chatgpt-conv-two", "msg-a2", OTHER_ASK, 3),
        archive_row("chatgpt", "chatgpt-conv-three", "msg-a3", OTHER_ASK, 4),
        archive_row("claude", "claude-conv-two", "msg-b2", SOLO_ASK, 5),
        archive_row("chatgpt", "chatgpt-conv-four", "msg-a4", TRIVIAL_ASK, 6),
        archive_row("claude", "claude-conv-three", "msg-b3", TRIVIAL_ASK, 7),
    ]


@pytest.fixture
def private_root(tmp_path) -> Path:
    root = tmp_path / "private"
    write_journal(root, standard_rows())
    return root


def run_cli(private_root: Path, mode: str) -> subprocess.CompletedProcess:
    env = {key: value for key, value in os.environ.items() if not key.startswith("LIMEN_")}
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(private_root.parent), "--private-root", str(private_root), mode],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        check=False,
    )


def stored_rows(private_root: Path) -> list[dict]:
    text = (private_root / "prompt-atoms" / "index-all-patterns.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def stored_report(private_root: Path) -> dict:
    return json.loads((private_root / "prompt-atoms" / "report-all-patterns.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- the build itself


def test_write_groups_the_same_ask_across_providers_and_sources(private_root):
    done = run_cli(private_root, "--write")
    assert done.returncode == 0, done.stdout
    rows = stored_rows(private_root)
    by_form: dict[str, list[dict]] = {}
    for row in rows:
        by_form.setdefault(row["form"], []).append(row)
    assert len(by_form) == 3
    shared = next(members for members in by_form.values() if len(members) == 3)
    assert {row["provider"] for row in shared} == {"chatgpt", "claude", "codex"}
    assert {row["source"] for row in shared} == {
        "archive-chatgpt-messages",
        "archive-claude-messages",
        "codex-history",
    }
    report = stored_report(private_root)
    assert report == {
        "atoms_considered": 8,
        "candidate_forms": 2,
        "forms": 3,
        "forms_spanning_providers": 2,
        "forms_spanning_sources": 2,
        "members": 7,
        "trivial_forms": 1,
        "ungrouped_atoms": 1,
    }


def test_row_fields_are_identifiers_and_counts_only(private_root):
    assert run_cli(private_root, "--write").returncode == 0
    for row in stored_rows(private_root):
        assert set(row) == {
            "atom_id",
            "authority",
            "conversation_uid",
            "form",
            "intent_words",
            "occurrence_id",
            "provider",
            "session_ref_hash",
            "source",
        }
        assert row["authority"] in {"unknown", "operator"}
        assert isinstance(row["intent_words"], int)


def test_archive_rows_name_their_conversation_and_other_sources_do_not(private_root):
    assert run_cli(private_root, "--write").returncode == 0
    rows = stored_rows(private_root)
    archive = [row for row in rows if row["source"].startswith("archive-")]
    other = [row for row in rows if not row["source"].startswith("archive-")]
    assert archive and other
    assert all(row["conversation_uid"] and "#" not in row["conversation_uid"] for row in archive)
    assert {row["conversation_uid"] for row in archive} >= {"chatgpt-conv-one", "claude-conv-one"}
    assert all(row["conversation_uid"] is None for row in other)


def test_archive_rows_carry_no_operator_authority(private_root):
    assert run_cli(private_root, "--write").returncode == 0
    assert {row["authority"] for row in stored_rows(private_root) if row["source"].startswith("archive-")} == {
        "unknown"
    }


def test_form_name_is_the_pattern_kind_plus_sixteen_hex_of_the_lineage_id(forms, private_root):
    occurrences = [row["occurrence"] for row in standard_rows()]
    atoms = [atom for row in standard_rows() for atom in row["atoms"]]
    rows, _report = forms.build(occurrences, atoms)
    lineage_by_atom = {atom["atom_id"]: atom["lineage_id"] for atom in atoms}
    assert rows
    for row in rows:
        expected = "pattern-all-" + hashlib.sha256(lineage_by_atom[row["atom_id"]].encode()).hexdigest()[:16]
        assert row["form"] == expected
        assert len(row["form"]) <= 80


def test_the_name_does_not_change_when_members_join(forms):
    first = standard_rows()[:2]
    more = standard_rows()[:3]
    first_names = {r["form"] for r in forms.build(*_split(first))[0]}
    more_names = {r["form"] for r in forms.build(*_split(more))[0]}
    assert first_names == more_names and len(first_names) == 1


def _split(rows):
    return [row["occurrence"] for row in rows], [atom for row in rows for atom in row["atoms"]]


# --------------------------------------------------------------------------- the four invariants


def test_invariant_members_plus_ungrouped_equal_atoms_considered(private_root):
    assert run_cli(private_root, "--write").returncode == 0
    report = stored_report(private_root)
    assert report["members"] + report["ungrouped_atoms"] == report["atoms_considered"]
    assert report["members"] == len(stored_rows(private_root))


def test_invariant_no_member_is_in_two_forms(private_root):
    assert run_cli(private_root, "--write").returncode == 0
    atom_ids = [row["atom_id"] for row in stored_rows(private_root)]
    assert len(atom_ids) == len(set(atom_ids))


def test_invariant_no_text_and_no_long_value_reach_the_index(private_root):
    assert run_cli(private_root, "--write").returncode == 0
    index_text = (private_root / "prompt-atoms" / "index-all-patterns.jsonl").read_text(encoding="utf-8")
    for ask in (SHARED_ASK, OTHER_ASK, SOLO_ASK, TRIVIAL_ASK):
        assert ask not in index_text
        assert ask.lower() not in index_text.lower()
    for row in stored_rows(private_root):
        assert not {"text", "raw_text", "intent", "title", "statement"} & set(row)
        assert all(len(value) <= 200 for value in row.values() if isinstance(value, str))


def test_a_very_long_conversation_uid_is_replaced_by_a_short_digest(forms, tmp_path):
    long_uid = "chatgpt-" + "x" * 400
    rows = [
        archive_row("chatgpt", long_uid, "msg-1", SHARED_ASK, 0),
        archive_row("claude", "claude-conv-one", "msg-2", SHARED_ASK, 1),
    ]
    write_journal(tmp_path / "private", rows)
    assert run_cli(tmp_path / "private", "--write").returncode == 0
    stored = stored_rows(tmp_path / "private")
    assert all(len(value) <= 200 for row in stored for value in row.values() if isinstance(value, str))
    assert any(str(row["conversation_uid"]).startswith("sha256-") for row in stored)
    assert run_cli(tmp_path / "private", "--verify").returncode == 0


def test_invariant_recomputing_twice_gives_identical_bytes(forms, private_root):
    directory = private_root / "prompt-atoms"
    _rows, _report, first_index, first_report = forms.compute(directory)
    _rows, _report, second_index, second_report = forms.compute(directory)
    assert (first_index, first_report) == (second_index, second_report)
    assert run_cli(private_root, "--write").returncode == 0
    written = (
        (directory / "index-all-patterns.jsonl").read_bytes(),
        (directory / "report-all-patterns.json").read_bytes(),
    )
    assert run_cli(private_root, "--write").returncode == 0
    again = (
        (directory / "index-all-patterns.jsonl").read_bytes(),
        (directory / "report-all-patterns.json").read_bytes(),
    )
    assert written == again == (first_index, first_report)


def test_the_bytes_do_not_depend_on_journal_order_or_location(tmp_path):
    rows = standard_rows()
    first = tmp_path / "first"
    second = tmp_path / "elsewhere" / "second"
    write_journal(first, rows)
    write_journal(second, list(reversed(rows)))
    assert run_cli(first, "--write").returncode == 0
    assert run_cli(second, "--write").returncode == 0
    for name in ("index-all-patterns.jsonl", "report-all-patterns.json"):
        assert (first / "prompt-atoms" / name).read_bytes() == (second / "prompt-atoms" / name).read_bytes()


def test_the_index_is_sorted_compact_and_newline_terminated(private_root):
    assert run_cli(private_root, "--write").returncode == 0
    raw = (private_root / "prompt-atoms" / "index-all-patterns.jsonl").read_text(encoding="utf-8")
    assert raw.endswith("\n") and not raw.endswith("\n\n")
    rows = [json.loads(line) for line in raw.splitlines()]
    assert rows == sorted(rows, key=lambda row: (row["form"], row["atom_id"]))
    assert all(line == json.dumps(json.loads(line), sort_keys=True, separators=(",", ":")) for line in raw.splitlines())


# --------------------------------------------------------------------------- verify


def test_verify_passes_after_write(private_root):
    assert run_cli(private_root, "--write").returncode == 0
    done = run_cli(private_root, "--verify")
    assert done.returncode == 0, done.stdout
    assert done.stdout.startswith("OK ")


def test_verify_fails_before_anything_is_written(private_root):
    done = run_cli(private_root, "--verify")
    assert done.returncode == 1
    assert "has not been written" in done.stdout


def test_verify_fails_when_the_ledger_has_moved_on(private_root):
    assert run_cli(private_root, "--write").returncode == 0
    journal = private_root / "prompt-atoms" / "prompt-events.jsonl"
    extra = archive_row("claude", "claude-conv-nine", "msg-z9", OTHER_ASK, 20)
    journal.write_text(journal.read_text(encoding="utf-8") + json.dumps(extra, sort_keys=True) + "\n", encoding="utf-8")
    done = run_cli(private_root, "--verify")
    assert done.returncode == 1
    assert "differ from a fresh recomputation" in done.stdout


def test_verify_names_a_text_field_in_the_index(private_root):
    assert run_cli(private_root, "--write").returncode == 0
    path = private_root / "prompt-atoms" / "index-all-patterns.jsonl"
    rows = stored_rows(private_root)
    rows[0]["text"] = "synthetic leaked words"
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    done = run_cli(private_root, "--verify")
    assert done.returncode == 1
    assert done.stdout.strip() == "FAIL the index carries a text field"
    assert "leaked" not in done.stdout


def test_verify_names_a_member_in_two_forms(private_root):
    assert run_cli(private_root, "--write").returncode == 0
    path = private_root / "prompt-atoms" / "index-all-patterns.jsonl"
    rows = stored_rows(private_root)
    rows.append({**rows[0], "form": "pattern-all-" + "0" * 16})
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    report = stored_report(private_root)
    report["members"] += 1
    report["ungrouped_atoms"] -= 1
    (private_root / "prompt-atoms" / "report-all-patterns.json").write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    done = run_cli(private_root, "--verify")
    assert done.returncode == 1
    assert done.stdout.strip() == "FAIL a member is in two forms"


def test_verify_names_a_long_value(private_root):
    assert run_cli(private_root, "--write").returncode == 0
    path = private_root / "prompt-atoms" / "index-all-patterns.jsonl"
    rows = stored_rows(private_root)
    rows[0]["conversation_uid"] = "u" * 201
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    done = run_cli(private_root, "--verify")
    assert done.returncode == 1
    assert done.stdout.strip() == "FAIL the index holds a value over the length limit"


def test_verify_names_counts_that_do_not_add_up(private_root):
    assert run_cli(private_root, "--write").returncode == 0
    path = private_root / "prompt-atoms" / "report-all-patterns.json"
    report = stored_report(private_root)
    report["ungrouped_atoms"] += 1
    path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    done = run_cli(private_root, "--verify")
    assert done.returncode == 1
    assert done.stdout.strip() == "FAIL members and ungrouped atoms do not add up to the atoms considered"


def test_verify_catches_a_single_flipped_byte_that_keeps_every_invariant(private_root):
    assert run_cli(private_root, "--write").returncode == 0
    path = private_root / "prompt-atoms" / "index-all-patterns.jsonl"
    content = path.read_text(encoding="utf-8")
    path.write_text(content.replace('"authority":"unknown"', '"authority":"derived"', 1), encoding="utf-8")
    done = run_cli(private_root, "--verify")
    assert done.returncode == 1
    assert "differ from a fresh recomputation" in done.stdout


# --------------------------------------------------------------------------- unusable input


def test_a_missing_journal_is_unusable_not_empty(tmp_path):
    for mode in ("--write", "--verify"):
        done = run_cli(tmp_path / "nothing", mode)
        assert done.returncode == 2
        assert done.stdout.strip() == "UNUSABLE the ledger journal is missing"


def test_a_damaged_journal_is_unusable(tmp_path):
    directory = write_journal(tmp_path / "private", standard_rows())
    journal = directory / "prompt-events.jsonl"
    journal.write_text(journal.read_text(encoding="utf-8") + "{not json\n", encoding="utf-8")
    done = run_cli(tmp_path / "private", "--write")
    assert done.returncode == 2
    assert "errors" in done.stdout
    assert not (directory / "index-all-patterns.jsonl").exists()


def test_an_empty_ledger_writes_an_empty_index_that_verifies(tmp_path):
    write_journal(tmp_path / "private", [])
    assert run_cli(tmp_path / "private", "--write").returncode == 0
    assert stored_rows(tmp_path / "private") == []
    assert stored_report(tmp_path / "private")["atoms_considered"] == 0
    assert run_cli(tmp_path / "private", "--verify").returncode == 0


def test_write_leaves_no_temporary_files_and_uses_private_permissions(private_root):
    assert run_cli(private_root, "--write").returncode == 0
    directory = private_root / "prompt-atoms"
    assert sorted(path.name for path in directory.iterdir()) == [
        "index-all-patterns.jsonl",
        "prompt-events.jsonl",
        "report-all-patterns.json",
    ]
    assert (directory / "index-all-patterns.jsonl").stat().st_mode & 0o077 == 0


# --------------------------------------------------------------------------- candidates


def test_candidates_list_forms_with_two_conversations_on_two_providers(private_root):
    assert run_cli(private_root, "--write").returncode == 0
    done = run_cli(private_root, "--candidates")
    assert done.returncode == 0
    entries = [json.loads(line) for line in done.stdout.splitlines()]
    assert [entry["form"] for entry in entries] == sorted(entry["form"] for entry in entries)
    assert len(entries) == 2
    shared = next(entry for entry in entries if entry["members"] == 3)
    assert shared["providers"] == ["chatgpt", "claude", "codex"]
    assert shared["conversations"] == 3
    assert shared["trivial"] is False
    assert any(entry["trivial"] for entry in entries)
    assert set(shared) == {"conversations", "form", "members", "providers", "trivial"}


def test_a_form_inside_one_provider_is_not_a_candidate(private_root):
    assert run_cli(private_root, "--write").returncode == 0
    done = run_cli(private_root, "--candidates")
    forms_listed = {json.loads(line)["form"] for line in done.stdout.splitlines()}
    one_provider = {row["form"] for row in stored_rows(private_root) if row["conversation_uid"] in {"chatgpt-conv-two"}}
    assert one_provider and not (one_provider & forms_listed)


def test_two_messages_in_one_conversation_are_one_conversation(forms):
    rows = [
        archive_row("chatgpt", "chatgpt-conv-one", "msg-1", SHARED_ASK, 0),
        archive_row("chatgpt", "chatgpt-conv-one", "msg-2", SHARED_ASK, 1),
        archive_row("claude", "claude-conv-one", "msg-3", SHARED_ASK, 2),
    ]
    built, report = forms.build(*_split(rows))
    assert report["forms"] == 1 and report["candidate_forms"] == 1
    assert report["members"] == 3
    only_chatgpt = [row for row in built if row["provider"] == "chatgpt"]
    assert not forms.is_candidate(only_chatgpt)


def test_candidates_need_the_index_to_exist(private_root):
    done = run_cli(private_root, "--candidates")
    assert done.returncode == 2
    assert done.stdout.strip() == "UNUSABLE the index has not been written"


def test_candidates_never_write_anything(private_root):
    assert run_cli(private_root, "--write").returncode == 0
    directory = private_root / "prompt-atoms"
    before = {path.name: path.read_bytes() for path in directory.iterdir()}
    assert run_cli(private_root, "--candidates").returncode == 0
    assert {path.name: path.read_bytes() for path in directory.iterdir()} == before


# --------------------------------------------------------------------------- the predicate's view


def test_the_alive_predicate_accepts_what_this_tool_writes(private_root):
    alive = _load(ALIVE_SCRIPT, "check_knowledge_alive_for_forms")
    assert run_cli(private_root, "--write").returncode == 0
    assert alive.index_problems(stored_rows(private_root)) == []
    report = stored_report(private_root)
    assert all(isinstance(report.get(key), int) for key in alive.REPORT_COUNT_KEYS)
    assert alive.FORMS_INDEX_FILE_NAME == "index-all-patterns.jsonl"
    assert alive.FORMS_REPORT_FILE_NAME == "report-all-patterns.json"


def test_the_default_form_script_of_the_predicate_is_this_tool():
    text = ALIVE_SCRIPT.read_text(encoding="utf-8")
    assert 'repo_root / "scripts" / "prompt-recurring-forms.py"' in text
