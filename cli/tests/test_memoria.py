"""Tests for MEMORIA — the single-writer record-keeper for the memory dir (limen.memoria).

Every test runs against a TEMP memory dir via the LIMEN_MEMORY_DIR override — the real memory dir
(~/.claude/…) is NEVER touched. What is under test: a session hands the keeper an immutable memory
ticket in a lock-free inbox, and the keeper is the ONLY writer of the memory dir — it drains, folds
each ticket into MEMORY.md + its atom in order, and archives the ticket. The invariants that make it
safe to run every beat:
  * an empty inbox is a no-op that never touches the memory dir;
  * a submitted ticket creates its atom (0600) + appends the index line + writes a receipt + is archived;
  * an update REPLACES the atom's index line IN PLACE — the surrounding curated order is byte-identical;
  * MEMORY.md is NEVER re-sorted;
  * one malformed ticket is quarantined with a reason while its siblings still apply;
  * a re-drain of an empty inbox writes nothing (idempotent);
  * with LIMEN_MEMORIA unset the organ memory pass is a total no-op.
"""

from __future__ import annotations

import json
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from limen.memoria import (
    MemoryTicket,
    drain_memory_once,
    new_ticket_id,
    resolve_memdir,
    submit_memory_ticket,
)

_NOW = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def memdir(tmp_path: Path) -> Path:
    """A temp memory dir wired via the LIMEN_MEMORY_DIR override (never the real one)."""
    d = tmp_path / "memory"
    d.mkdir()
    os.environ["LIMEN_MEMORY_DIR"] = str(d)
    return d


def _ticket(slug: str, *, offset: int = 0, **over) -> MemoryTicket:
    now = _NOW + timedelta(seconds=offset)
    base = dict(
        ticket_id=new_ticket_id("sess", now),
        timestamp=now,
        agent="session",
        session_id="sess",
        slug=slug,
        title=f"Title {slug}",
        desc=f"desc for {slug}",
    )
    base.update(over)
    return MemoryTicket(**base)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_resolve_memdir_honors_override(memdir: Path):
    assert resolve_memdir() == memdir
    assert resolve_memdir("/tmp/elsewhere") == Path("/tmp/elsewhere")


def test_submit_then_drain_round_trip(memdir: Path):
    submit_memory_ticket(_ticket("alpha-atom"))
    result = drain_memory_once()
    assert result.applied == 1
    assert result.rejected == 0
    assert result.wrote is True

    atom = memdir / "alpha-atom.md"
    assert atom.exists()
    # atom is chmod 0600
    assert stat.S_IMODE(atom.stat().st_mode) == 0o600
    content = _read(atom)
    assert "name: alpha-atom" in content
    assert "type: project" in content

    # index line appended
    index = _read(memdir / "MEMORY.md")
    assert "- [Title alpha-atom](alpha-atom.md) — desc for alpha-atom" in index

    # a receipt line written — slug + hash only, no body text
    receipts = (memdir / ".covenant-receipts.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(receipts) == 1
    rec = json.loads(receipts[0])
    assert rec["slug"] == "alpha-atom"
    assert rec["op"] == "created"
    assert rec["keeper"] == "tabularius"
    assert len(rec["body_hash"]) == 64
    assert "desc for" not in receipts[0]  # no body text leaks into the receipt

    # ticket archived, inbox empty
    assert list((memdir / ".covenant-inbox").glob("*.json")) == []
    assert len(list((memdir / ".covenant-archive").glob("*.json"))) == 1


def test_verbatim_body_used_when_provided(memdir: Path):
    body = "---\nname: beta-atom\ndescription: \"custom\"\nmetadata:\n  node_type: memory\n  type: project\n---\n\nverbatim body text\n"
    submit_memory_ticket(_ticket("beta-atom", body=body))
    drain_memory_once()
    assert _read(memdir / "beta-atom.md") == body


def test_star_prefixes_the_title(memdir: Path):
    submit_memory_ticket(_ticket("starred-atom", star=True))
    drain_memory_once()
    index = _read(memdir / "MEMORY.md")
    assert "- [★Title starred-atom](starred-atom.md) — desc for starred-atom" in index


def test_update_replaces_line_in_place_order_identical(memdir: Path):
    # pre-seed a curated multi-line MEMORY.md whose order carries meaning
    seed = (
        "- [First](first.md) — the first atom\n"
        "- [Target](target.md) — original summary\n"
        "- [Third](third.md) — the third atom\n"
    )
    (memdir / "MEMORY.md").write_text(seed, encoding="utf-8")

    # create the target atom via a first ticket... actually seed the atom too so this is an UPDATE
    (memdir / "target.md").write_text("original atom body\n", encoding="utf-8")

    submit_memory_ticket(
        _ticket("target", title="Target", desc="UPDATED summary", body="new atom body\n")
    )
    result = drain_memory_once()
    assert result.applied == 1

    index = _read(memdir / "MEMORY.md")
    lines = index.splitlines()
    # the target line is replaced IN PLACE (still line index 1) — surrounding order byte-identical
    assert lines[0] == "- [First](first.md) — the first atom"
    assert lines[1] == "- [Target](target.md) — UPDATED summary"
    assert lines[2] == "- [Third](third.md) — the third atom"
    # atom body overwritten by the provided body
    assert _read(memdir / "target.md") == "new atom body\n"

    rec = json.loads((memdir / ".covenant-receipts.jsonl").read_text(encoding="utf-8").strip())
    assert rec["op"] == "updated"


def test_update_without_body_leaves_atom_untouched(memdir: Path):
    (memdir / "keep.md").write_text("existing atom body — keep me\n", encoding="utf-8")
    (memdir / "MEMORY.md").write_text("- [Keep](keep.md) — old\n", encoding="utf-8")
    submit_memory_ticket(_ticket("keep", title="Keep", desc="new desc"))  # no body
    drain_memory_once()
    assert _read(memdir / "keep.md") == "existing atom body — keep me\n"
    assert _read(memdir / "MEMORY.md") == "- [Keep](keep.md) — new desc\n"


def test_order_preservation_new_atom_appends(memdir: Path):
    seed = "- [One](one.md) — a\n- [Two](two.md) — b\n"
    (memdir / "MEMORY.md").write_text(seed, encoding="utf-8")
    submit_memory_ticket(_ticket("three", title="Three", desc="c"))
    drain_memory_once()
    index = _read(memdir / "MEMORY.md")
    assert index == "- [One](one.md) — a\n- [Two](two.md) — b\n- [Three](three.md) — c\n"


def test_malformed_ticket_quarantined_siblings_apply(memdir: Path):
    inbox = memdir / ".covenant-inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    # a good sibling
    submit_memory_ticket(_ticket("good-atom"))
    # a garbage ticket dropped straight into the inbox (unparseable JSON)
    (inbox / "20260716T120000_000000Z-x-deadbeef.json").write_text("{ not json", encoding="utf-8")

    result = drain_memory_once()
    assert result.applied == 1
    assert result.rejected == 1

    # good atom landed
    assert (memdir / "good-atom.md").exists()
    # garbage quarantined with a reason
    rejected_dir = memdir / ".covenant-rejected"
    assert (rejected_dir / "20260716T120000_000000Z-x-deadbeef.json").exists()
    reason = _read(rejected_dir / "20260716T120000_000000Z-x-deadbeef.json.reason.txt")
    assert "unparseable" in reason


def test_invalid_slug_rejected_at_construction():
    with pytest.raises(ValueError):
        _ticket("Not A Slug")
    with pytest.raises(ValueError):
        _ticket("../escape")


def test_empty_inbox_is_noop(memdir: Path):
    result = drain_memory_once()
    assert result.applied == 0
    assert result.wrote is False
    # nothing created
    assert not (memdir / "MEMORY.md").exists()


def test_idempotent_redrain_writes_nothing(memdir: Path):
    (memdir / "MEMORY.md").write_text("- [One](one.md) — a\n", encoding="utf-8")
    submit_memory_ticket(_ticket("solo-atom"))
    drain_memory_once()
    index_after_first = _read(memdir / "MEMORY.md")
    receipts_after_first = _read(memdir / ".covenant-receipts.jsonl")

    # inbox is now empty; a re-drain is a pure no-op
    result = drain_memory_once()
    assert result.applied == 0
    assert result.wrote is False
    assert _read(memdir / "MEMORY.md") == index_after_first  # byte-identical
    assert _read(memdir / ".covenant-receipts.jsonl") == receipts_after_first


def test_ordering_by_timestamp(memdir: Path):
    # two new atoms submitted out of timestamp order still append in (timestamp) order
    submit_memory_ticket(_ticket("later", offset=100, title="Later", desc="later"))
    submit_memory_ticket(_ticket("earlier", offset=0, title="Earlier", desc="earlier"))
    drain_memory_once()
    index = _read(memdir / "MEMORY.md")
    assert index == "- [Earlier](earlier.md) — earlier\n- [Later](later.md) — later\n"


def test_organ_memory_pass_noop_when_flag_off(memdir: Path, tmp_path: Path):
    """The tabularius-organ memory hook is a total no-op when LIMEN_MEMORIA is unset."""
    import importlib.util

    os.environ.pop("LIMEN_MEMORIA", None)
    # submit a ticket that WOULD be folded if the flag were on
    submit_memory_ticket(_ticket("would-fold"))
    before = sorted(p.name for p in memdir.iterdir())

    organ_path = Path(__file__).resolve().parents[2] / "scripts" / "tabularius-organ.py"
    spec = importlib.util.spec_from_file_location("tabularius_organ_test", organ_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod.MEMORIA_ENABLED is False
    result = mod._memory_pass(check=False, dry_run=False)
    assert result == {}  # nothing returned, nothing done

    # the memory dir is untouched — the ticket is still pending in the inbox, unfolded
    after = sorted(p.name for p in memdir.iterdir())
    assert after == before
    assert not (memdir / "would-fold.md").exists()
    assert len(list((memdir / ".covenant-inbox").glob("*.json"))) == 1
