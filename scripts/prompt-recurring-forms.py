#!/usr/bin/env python3
"""Recurring-form index: which asks keep coming back, across providers and conversations.

The prompt-atom ledger gives every atom a `lineage_id`; atoms that share one are the same ask in
different places. This tool groups the atoms of the private ledger journal by that id and writes a
byte-stable index beside the journal. A "form" is a group of two or more member atoms; an atom alone in
its group is "ungrouped". Nothing here writes to a public tree and nothing here reads or writes a prompt
body: the index carries identifiers, counts and fixed vocabulary words only.

  python3 scripts/prompt-recurring-forms.py --write       # recompute and write the index and the report
  python3 scripts/prompt-recurring-forms.py --verify      # recompute, byte-compare, check the invariants
  python3 scripts/prompt-recurring-forms.py --candidates  # forms worth a person's distillation, as JSON lines

Add `--root R --private-root P` to point at another ledger (the defaults are the repository and the
private session corpus the ledger itself resolves). Atoms come from the private event journal
(`<P>/prompt-atoms/prompt-events.jsonl`): the ledger snapshot beside it holds only counts and digests, so
the journal is the one source of atoms. Outputs, in the same directory:

  index-all-patterns.jsonl    one row per member atom, sorted by (form, atom_id)
  report-all-patterns.json    counts only

Row fields: form, atom_id, occurrence_id, source, provider, conversation_uid (the archive conversation
uid for an `archive-*` source, else null), session_ref_hash, authority, intent_words (a count). A form is
named `pattern-all-<first 16 hex of SHA-256 over the lineage_id>`; it has no date, so the name never
changes as members join.

Four invariants, each checked by `--verify` (and by `check-knowledge-alive.py`, check 7):

  1. members + ungrouped == atoms considered
  2. no member is in two forms
  3. no text field, and no value longer than 200 characters, in the index
  4. recomputing twice gives identical bytes (and the files on disk equal that recomputation)

Exit codes: 0 ok, 1 invariant or byte mismatch (the output names the first failure), 2 unusable input
(the journal is missing or unreadable, or the index does not exist for `--candidates`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.prompt_corpus import LedgerPaths, load_event_journal, normalize_intent  # noqa: E402

INDEX_FILE_NAME = "index-all-patterns.jsonl"
REPORT_FILE_NAME = "report-all-patterns.json"
FORM_NAME_PREFIX = "pattern-all-"
FORM_NAME_PATTERN = re.compile(r"pattern-all-[0-9a-f]{16}")
ARCHIVE_SOURCE_PATTERN = re.compile(r"archive-([a-z0-9]+)-messages")
MAXIMUM_VALUE_LENGTH = 200
TRIVIAL_WORD_LIMIT = 3
MINIMUM_FORM_MEMBERS = 2
MINIMUM_CANDIDATE_CONVERSATIONS = 2
MINIMUM_CANDIDATE_PROVIDERS = 2
FORBIDDEN_ROW_KEYS = frozenset({"text", "raw_text", "intent", "title", "statement", "task_body"})
REPORT_COUNT_KEYS = (
    "atoms_considered",
    "candidate_forms",
    "forms",
    "forms_spanning_providers",
    "forms_spanning_sources",
    "members",
    "trivial_forms",
    "ungrouped_atoms",
)

Row = dict[str, Any]


class Unusable(Exception):
    """The input cannot be read at all; distinct from an index that is merely wrong."""


# --------------------------------------------------------------------------- reading the ledger


def provider_of(source: str) -> str:
    """The provider word for a source family: the archive provider, else the family's first word."""
    archive = ARCHIVE_SOURCE_PATTERN.fullmatch(source)
    if archive:
        return archive.group(1)
    return source.split("-", 1)[0] if source else "unknown"


def bounded(value: str) -> str:
    """Keep every index value inside the length limit without ever storing the long original."""
    if len(value) <= MAXIMUM_VALUE_LENGTH:
        return value
    return "sha256-" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def conversation_uid_of(occurrence: Row) -> str | None:
    """The archive conversation uid, taken from the `<uid>#<message id>` locator; null for other sources."""
    if not str(occurrence.get("source") or "").startswith("archive-"):
        return None
    locator = str(occurrence.get("source_locator") or "")
    uid = locator.split("#", 1)[0]
    return bounded(uid) if uid else None


def form_name(lineage_id: str) -> str:
    return FORM_NAME_PREFIX + hashlib.sha256(lineage_id.encode("utf-8")).hexdigest()[:16]


def load_ledger(private_dir: Path) -> tuple[list[Row], list[Row]]:
    journal = private_dir / "prompt-events.jsonl"
    if not journal.is_file():
        raise Unusable("the ledger journal is missing")
    try:
        occurrences, atoms, errors = load_event_journal(journal)
    except (OSError, ValueError) as error:
        raise Unusable("the ledger journal is unreadable") from error
    if errors:
        raise Unusable(f"the ledger journal has {len(errors)} errors")
    return occurrences, atoms


# --------------------------------------------------------------------------- building the index


def intent_words(atom: Row) -> int:
    return len(normalize_intent(str(atom.get("intent") or "")).split())


def build(occurrences: list[Row], atoms: list[Row]) -> tuple[list[Row], Row]:
    """Group atoms by lineage id; return the sorted member rows and the counts-only report."""
    by_occurrence = {str(row.get("occurrence_id")): row for row in occurrences}
    groups: dict[str, list[Row]] = defaultdict(list)
    for atom in atoms:
        lineage_id = str(atom.get("lineage_id") or "")
        if lineage_id:
            groups[lineage_id].append(atom)
    names: dict[str, str] = {}
    rows: list[Row] = []
    for lineage_id, members in groups.items():
        if len(members) < MINIMUM_FORM_MEMBERS:
            continue
        name = form_name(lineage_id)
        if name in names and names[name] != lineage_id:
            raise ValueError("two lineage ids share one form name")
        names[name] = lineage_id
        for atom in members:
            occurrence = by_occurrence.get(str(atom.get("occurrence_id")), {})
            source = str(atom.get("source") or occurrence.get("source") or "")
            rows.append(
                {
                    "form": name,
                    "atom_id": str(atom["atom_id"]),
                    "occurrence_id": str(atom.get("occurrence_id") or ""),
                    "source": bounded(source),
                    "provider": provider_of(source),
                    "conversation_uid": conversation_uid_of({**occurrence, "source": source}),
                    "session_ref_hash": str(atom.get("session_ref_hash") or occurrence.get("session_ref_hash") or ""),
                    "authority": str(atom.get("authority") or "unknown"),
                    "intent_words": intent_words(atom),
                }
            )
    rows.sort(key=lambda row: (row["form"], row["atom_id"]))
    return rows, summarize(rows, len(atoms))


def members_by_form(rows: list[Row]) -> dict[str, list[Row]]:
    forms: dict[str, list[Row]] = {}
    for row in rows:
        forms.setdefault(str(row["form"]), []).append(row)
    return forms


def conversation_key(row: Row) -> str:
    return str(row.get("conversation_uid") or row.get("session_ref_hash") or row.get("occurrence_id") or "")


def is_candidate(members: list[Row]) -> bool:
    conversations = {conversation_key(row) for row in members}
    providers = {str(row.get("provider") or "") for row in members} - {""}
    return len(conversations) >= MINIMUM_CANDIDATE_CONVERSATIONS and len(providers) >= MINIMUM_CANDIDATE_PROVIDERS


def is_trivial(members: list[Row]) -> bool:
    return max(int(row.get("intent_words") or 0) for row in members) < TRIVIAL_WORD_LIMIT


def summarize(rows: list[Row], atoms_considered: int) -> Row:
    forms = members_by_form(rows)
    return {
        "atoms_considered": atoms_considered,
        "candidate_forms": sum(1 for members in forms.values() if is_candidate(members)),
        "forms": len(forms),
        "forms_spanning_providers": sum(
            1 for members in forms.values() if len({str(row["provider"]) for row in members}) >= 2
        ),
        "forms_spanning_sources": sum(
            1 for members in forms.values() if len({str(row["source"]) for row in members}) >= 2
        ),
        "members": len(rows),
        "trivial_forms": sum(1 for members in forms.values() if is_trivial(members)),
        "ungrouped_atoms": atoms_considered - len(rows),
    }


def render(rows: list[Row], report: Row) -> tuple[bytes, bytes]:
    """The exact bytes of both files; the only place the on-disk format is defined."""
    lines = (json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for row in rows)
    index = "".join(f"{line}\n" for line in lines)
    summary = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    return index.encode("utf-8"), summary.encode("utf-8")


def compute(private_dir: Path) -> tuple[list[Row], Row, bytes, bytes]:
    occurrences, atoms = load_ledger(private_dir)
    rows, report = build(occurrences, atoms)
    index_bytes, report_bytes = render(rows, report)
    return rows, report, index_bytes, report_bytes


# --------------------------------------------------------------------------- invariants


def too_long(value: Any) -> bool:
    if isinstance(value, str):
        return len(value) > MAXIMUM_VALUE_LENGTH
    if isinstance(value, (list, tuple)):
        return any(too_long(item) for item in value)
    if isinstance(value, dict):
        return any(too_long(key) or too_long(item) for key, item in value.items())
    return False


def invariant_problems(rows: list[Row], report: Row) -> list[str]:
    """Violations of the four stored-file invariants, by name, in a fixed order. Empty means they hold."""
    problems: list[str] = []
    members = [str(row.get("atom_id") or "") for row in rows]
    count_keys_ok = all(isinstance(report.get(key), int) for key in REPORT_COUNT_KEYS)
    if not count_keys_ok:
        problems.append("the report is missing a count")
    elif report["members"] + report["ungrouped_atoms"] != report["atoms_considered"] or report["members"] != len(rows):
        problems.append("members and ungrouped atoms do not add up to the atoms considered")
    if not all(members) or len(set(members)) != len(members):
        problems.append("a member is in two forms")
    if any(FORBIDDEN_ROW_KEYS & set(row) for row in rows):
        problems.append("the index carries a text field")
    if any(too_long(value) for row in rows for value in row.values()):
        problems.append("the index holds a value over the length limit")
    if not all(FORM_NAME_PATTERN.fullmatch(str(row.get("form") or "")) for row in rows):
        problems.append("a form name is malformed")
    forms = members_by_form(rows)
    if any(len(group) < MINIMUM_FORM_MEMBERS for group in forms.values()):
        problems.append("a form has fewer than two members")
    if count_keys_ok and report["forms"] != len(forms):
        problems.append("the report disagrees with the index")
    return problems


def read_index(private_dir: Path) -> list[Row]:
    path = private_dir / INDEX_FILE_NAME
    rows: list[Row] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("an index row is not an object")
            rows.append(row)
    return rows


# --------------------------------------------------------------------------- commands


def write_atomically(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def command_write(private_dir: Path) -> int:
    rows, report, index_bytes, report_bytes = compute(private_dir)
    problems = invariant_problems(rows, report)
    if problems:
        print(f"FAIL {problems[0]}")
        return 1
    write_atomically(private_dir / INDEX_FILE_NAME, index_bytes)
    write_atomically(private_dir / REPORT_FILE_NAME, report_bytes)
    print(f"WROTE {report['forms']} forms, {report['members']} members, {report['ungrouped_atoms']} ungrouped")
    return 0


def command_verify(private_dir: Path) -> int:
    rows, report, index_bytes, report_bytes = compute(private_dir)
    _rows_again, _report_again, index_again, report_again = compute(private_dir)
    if (index_bytes, report_bytes) != (index_again, report_again):
        print("FAIL recomputing gives different bytes")
        return 1
    index_path = private_dir / INDEX_FILE_NAME
    report_path = private_dir / REPORT_FILE_NAME
    if not index_path.is_file() or not report_path.is_file():
        print("FAIL the index or the report has not been written")
        return 1
    try:
        stored_rows = read_index(private_dir)
        stored_report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("FAIL the index or the report is unreadable")
        return 1
    problems = invariant_problems(stored_rows, stored_report if isinstance(stored_report, dict) else {})
    problems += invariant_problems(rows, report)
    if problems:
        print(f"FAIL {problems[0]}")
        return 1
    if index_path.read_bytes() != index_bytes or report_path.read_bytes() != report_bytes:
        print("FAIL the files on disk differ from a fresh recomputation")
        return 1
    print(f"OK {report['forms']} forms, {report['members']} members, {report['ungrouped_atoms']} ungrouped")
    return 0


def command_candidates(private_dir: Path) -> int:
    if not (private_dir / INDEX_FILE_NAME).is_file():
        raise Unusable("the index has not been written")
    try:
        rows = read_index(private_dir)
    except (OSError, ValueError) as error:
        raise Unusable("the index is unreadable") from error
    for name, members in sorted(members_by_form(rows).items()):
        if not is_candidate(members):
            continue
        entry = {
            "conversations": len({conversation_key(row) for row in members}),
            "form": name,
            "members": len(members),
            "providers": sorted({str(row["provider"]) for row in members}),
            "trivial": is_trivial(members),
        }
        print(json.dumps(entry, sort_keys=True, separators=(",", ":")))
    return 0


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--root", type=Path, default=Path(os.environ.get("LIMEN_ROOT") or ROOT))
    parser.add_argument("--private-root", type=Path, default=None)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="recompute and write the index and the report")
    mode.add_argument("--verify", action="store_true", help="recompute, byte-compare and check the invariants")
    mode.add_argument("--candidates", action="store_true", help="list forms worth a person's distillation")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    private_dir = LedgerPaths.for_root(args.root, private_root=args.private_root).private_dir
    try:
        if args.write:
            return command_write(private_dir)
        if args.verify:
            return command_verify(private_dir)
        return command_candidates(private_dir)
    except Unusable as error:
        print(f"UNUSABLE {error}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
