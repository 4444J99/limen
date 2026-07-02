"""Workstream channels — the purpose partition over the board.

The load-bearing claims under test: (1) the roster DERIVES from organ-ladder.json (add an organ →
get a channel); (2) Anthony's vocabulary resolves via alias (revenue → financial); (3) the field
survives the ONE record-keeper (TABVLARIVS) untouched — the whole design rests on this.
"""

import json
from datetime import date
from pathlib import Path

from limen import tabularius
from limen import workstream as ws
from limen.io import load_limen_file
from limen.models import LimenFile, Task


def _task(
    tid: str, workstream: str | None = None, labels: list[str] | None = None, status: str = "open", agent: str = "any"
) -> Task:
    return Task(
        id=tid,
        title=f"t-{tid}",
        target_agent=agent,
        status=status,
        workstream=workstream,
        labels=labels or [],
        created=date(2026, 7, 1),
    )


def _ladder(tmp_path: Path) -> Path:
    (tmp_path / "organ-ladder.json").write_text(
        json.dumps(
            {
                "organs": [
                    {"pillar": "financial", "organ": "Financial Office", "macro": "family office"},
                    {"pillar": "legal", "organ": "Legal Organism", "macro": "legal platform"},
                    {"pillar": "legal", "organ": "dup — same pillar", "macro": "dedup me"},
                ]
            }
        )
    )
    return tmp_path


def test_normalize_handle():
    assert ws.normalize_handle("Revenue!!") == "revenue"
    assert ws.normalize_handle("  Prompt Parity ") == "prompt-parity"
    assert ws.normalize_handle("") is None
    assert ws.normalize_handle(None) is None


def test_field_normalizes_on_the_model():
    assert _task("A", workstream="Prompt Parity").workstream == "prompt-parity"
    assert _task("B", workstream="   ").workstream is None
    assert _task("C").workstream is None


def test_roster_derives_meta_plus_organs(tmp_path):
    _ladder(tmp_path)
    handles = [c.handle for c in ws.derived_channels(tmp_path)]
    for meta in ("conductor", "contributions", "correspondence", "prompt-parity"):
        assert meta in handles
    assert "financial" in handles and "legal" in handles
    assert handles.count("legal") == 1  # deduped by pillar


def test_roster_without_ladder_is_meta_only(tmp_path):
    handles = [c.handle for c in ws.derived_channels(tmp_path)]  # no organ-ladder.json here
    assert handles == ["conductor", "contributions", "correspondence", "prompt-parity"]


def test_alias_resolves_revenue_to_financial(tmp_path):
    _ladder(tmp_path)
    assert ws.canonical_handle("revenue", tmp_path) == "financial"
    assert ws.canonical_handle("Money", tmp_path) == "financial"
    assert ws.canonical_handle("contributions", tmp_path) == "contributions"
    assert ws.canonical_handle("some-adhoc-lane", tmp_path) == "some-adhoc-lane"  # unknown passes through


def test_channel_of_precedence(tmp_path):
    _ladder(tmp_path)
    assert ws.channel_of(_task("A", workstream="revenue"), tmp_path) == "financial"  # field wins + alias
    assert ws.channel_of(_task("B", labels=["mail"]), tmp_path) == "correspondence"  # infer from label
    assert ws.channel_of(_task("C"), tmp_path) == ws.UNASSIGNED  # nothing → unassigned


def test_group_and_filter(tmp_path):
    _ladder(tmp_path)
    limen = LimenFile(
        tasks=[
            _task("A", workstream="contributions"),
            _task("B", workstream="revenue"),
            _task("C"),
        ]
    )
    groups = ws.group_by_channel(limen, tmp_path)
    assert [t.id for t in groups["contributions"]] == ["A"]
    assert [t.id for t in groups["financial"]] == ["B"]  # via alias
    assert [t.id for t in groups[ws.UNASSIGNED]] == ["C"]
    assert groups["legal"] == []  # empty derived channel still present

    filtered = ws.filter_board(limen, "revenue", tmp_path)
    assert [t.id for t in filtered.tasks] == ["B"]


def test_workstream_survives_tabularius_single_writer(tmp_path):
    # The whole design rests on this: the field flows through the ONE record-keeper untouched.
    board = tmp_path / "tasks.yaml"
    board.write_text('version: "1.0"\nportal:\n  name: x\ntasks: []\n')
    tabularius.submit_task_upsert(
        board,
        {"id": "W1", "title": "w", "target_agent": "any", "workstream": "Revenue", "created": "2026-07-01"},
        agent="tester",
        session_id="s",
    )
    res = tabularius.drain_once(board)
    assert res.wrote
    got = {t.id: t for t in load_limen_file(board).tasks}
    assert got["W1"].workstream == "revenue"  # normalized on submit, preserved through the seal
