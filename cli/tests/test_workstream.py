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


def test_workstream_survives_tabularius_single_writer(tmp_path, monkeypatch):
    # The broker receipt, not a local YAML rewrite, is the canonical projection proof.
    board = tmp_path / "tasks.yaml"
    board.write_text('version: "1.0"\nportal:\n  name: x\ntasks: []\n')
    before = board.read_bytes()
    acknowledged = []

    class Owner:
        def register(self, session):
            return session

        def submit(self, packet):
            task = dict(packet.intent["task"])
            acknowledged.append(task)
            return {
                "status": "accepted",
                "projection_receipts": [{"task_id": task["id"], "task": task}],
            }

    monkeypatch.setattr(tabularius, "client_from_env", lambda: Owner())
    tabularius.submit_task_upsert(
        board,
        {
            "id": "W1",
            "title": "w",
            "repo": "organvm/limen",
            "target_agent": "any",
            "workstream": "Revenue",
            "predicate": "pytest -q cli/tests/test_workstream.py",
            "receipt_target": "github:organvm/limen:pull-request:W1",
            "origin": "human_prompt",
            "horizon": "present",
            "value_case": "Deliver the bounded workstream task",
            "owner_surface": "organvm/limen",
            "created": "2026-07-01",
        },
        agent="tester",
        session_id="s",
    )
    res = tabularius.drain_once(board)
    assert res.applied == 1
    assert res.wrote is False
    assert board.read_bytes() == before
    assert acknowledged[0]["workstream"] == "revenue"
    assert (tabularius._archive(board) / f"{res.applied_ids[0]}.json").exists()


def _pr(number, title, branch="", draft=False):
    return ws.PullRequest(number=number, title=title, branch=branch, draft=draft)


def test_infer_channel_whole_token_only(tmp_path):
    _ladder(tmp_path)
    assert ws.infer_channel("[limen] revenue harvest packet", tmp_path) == "financial"  # alias
    assert ws.infer_channel("legal filing cleanup", tmp_path) == "legal"  # organ pillar
    assert ws.infer_channel("mail drafts for obligations", tmp_path) == "correspondence"  # meta alias
    assert ws.infer_channel("decode the render pipeline", tmp_path) == ws.UNASSIGNED  # 'decode' ≠ 'code'
    assert ws.infer_channel("test(capacity): add unit tests", tmp_path) == ws.UNASSIGNED  # no purpose token
    # "PR"/"PRs" are structural noise in PR-land — must NOT force a contributions match in free text …
    assert ws.infer_channel("Recover closed PR task: add copilot lane", tmp_path) == ws.UNASSIGNED
    # … but the task-label path still honors an intentional "pr" label (no regression to channel_of).
    assert ws.channel_of(_task("Z", labels=["pr"]), tmp_path) == "contributions"


def test_channel_of_pr_uses_title_and_branch(tmp_path):
    _ladder(tmp_path)
    assert ws.channel_of_pr(_pr(1, "wire watch subcommand", "feat/financial-report"), tmp_path) == "financial"
    assert ws.channel_of_pr(_pr(2, "Odyssey film companion", "jules/studium-film"), tmp_path) == ws.UNASSIGNED


def test_group_prs_by_channel_is_a_stable_scoreboard(tmp_path):
    _ladder(tmp_path)
    prs = [
        _pr(10, "revenue backlog sweep"),  # → financial (alias)
        _pr(11, "legal doc pass"),  # → legal (organ)
        _pr(12, "CAPFILL packet 03"),  # → unassigned
        _pr(13, "contributions drain", "feat/contrib-run"),  # → contributions
    ]
    groups = ws.group_prs_by_channel(prs, tmp_path)
    assert [p.number for p in groups["financial"]] == [10]
    assert [p.number for p in groups["legal"]] == [11]
    assert [p.number for p in groups["contributions"]] == [13]
    assert [p.number for p in groups[ws.UNASSIGNED]] == [12]
    # every derived channel present even when empty, UNASSIGNED last
    assert "correspondence" in groups and groups["correspondence"] == []
    assert list(groups)[-1] == ws.UNASSIGNED

    summary = ws.pr_roster_summary(prs, tmp_path)
    assert summary["total_open"] == 4
    fin = next(c for c in summary["channels"] if c["handle"] == "financial")
    assert fin["total"] == 1 and fin["prs"][0]["number"] == 10


def test_assign_channel_partitions_the_board(tmp_path):
    """The beat's auto-partition derivation: the field/label/token ladder PLUS the task-KIND
    fallback that actually resolves the fleet's GEN-*/DISCOVER-* backlog (the reason the board sat
    100% unassigned). Unclassifiable tasks stay honestly UNASSIGNED — never guessed into a domain."""
    root = _ladder(tmp_path)
    # 1. explicit field wins, alias-resolved (revenue → financial)
    assert ws.assign_channel(_task("A", workstream="revenue"), root) == "financial"
    # 2. a matching label
    assert ws.assign_channel(_task("B", labels=["legal"]), root) == "legal"
    # 3. a purpose token in the id — the ORG-* organ lanes that carry no field/label
    assert ws.assign_channel(_task("ORG-financial-organ-operationalize-0703"), root) == "financial"
    # 4. task-KIND prefix — the structured fleet tasks whose purpose is structural, not lexical
    assert ws.assign_channel(_task("GEN-organvm-limen-test-coverage-0620"), root) == "contributions"
    assert ws.assign_channel(_task("DISCOVER-organvm-the-actual-news"), root) == "conductor"
    # honest fallback: nothing resolves → stays unassigned (never mis-lane'd)
    assert ws.assign_channel(_task("ZZZ-unknown-kind-0703"), root) == ws.UNASSIGNED
