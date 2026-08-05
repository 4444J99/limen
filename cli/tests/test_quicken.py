from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "quicken.py"


def _load():
    spec = importlib.util.spec_from_file_location("quicken", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_malformed_numeric_env_falls_back(monkeypatch):
    monkeypatch.setenv("LIMEN_QUICKEN_STALE_MIN", "not-an-int")
    monkeypatch.setenv("LIMEN_QUICKEN_HORIZON_DAYS", "0")
    monkeypatch.setenv("LIMEN_QUICKEN_CLOSED_HRS", "-1")

    quicken = _load()

    assert quicken.STALE_MIN == 20
    assert quicken.HORIZON_DAYS == 3
    assert quicken.CLOSED_HRS == 18


def test_breathe_numeric_env_falls_back(monkeypatch, capsys):
    monkeypatch.setenv("LIMEN_QUICKEN_BREATHE_CAP", "bad")
    monkeypatch.setenv("LIMEN_QUICKEN_BREATHE_TIMEOUT", "0")
    quicken = _load()

    quicken.breathe([], "all", dry=True)

    assert "within cap=1" in capsys.readouterr().out


def test_hang_residue_backfills_work_loan_once_then_converges(tmp_path, monkeypatch):
    quicken = _load()
    tasks = tmp_path / "tasks.yaml"
    atom = "land the credential/secret (your account/identity)"
    title = "Audit Codex handoff and validate token-accountin"
    context = (
        f"Cheapest path \u2192 {atom}. Unblocks: {title}. "
        "Auto-hung by QUICKEN (finish-not-park); refreshes each beat until you act."
    )
    before = f"""version: '1.0'
tasks:
- id: ASK-quicken-credential
  title: {atom}
  type: ops
  target_agent: human
  priority: high
  budget_cost: 1
  status: needs_human
  labels:
  - user-ask
  - quicken-residue
  - needs-human
  urls: []
  context: "{context}"
  depends_on: []
  created: '2026-06-26'
  updated: '2026-07-04T19:36:24.651929Z'
  dispatch_log: []
"""
    tasks.write_text(before, encoding="utf-8")
    monkeypatch.setattr(quicken, "LEDGER", tasks)

    result = quicken.hang_residue(
        [
            {
                "state": "STALLED",
                "title": title,
                "decision": {"residue": atom},
            }
        ]
    )

    assert result["created"] == []
    assert result["refreshed"] == ["ASK-quicken-credential"]
    task = yaml.safe_load(tasks.read_text(encoding="utf-8"))["tasks"][0]
    assert task["origin"] == "human_prompt"
    assert task["horizon"] == "present"
    assert task["value_case"] == f"Resolve the irreducible operator atom: {atom}"
    assert task["owner_surface"] == "organvm/limen"

    after_backfill = tasks.read_text(encoding="utf-8")
    repeated = quicken.hang_residue([{"state": "STALLED", "title": title, "decision": {"residue": atom}}])
    assert repeated["refreshed"] == []
    assert repeated["homed"] == [f"{atom} \u2192 ASK-quicken-credential"]
    assert tasks.read_text(encoding="utf-8") == after_backfill


def test_write_residue_splits_queued_unblocks_before_deduping(monkeypatch):
    quicken = _load()
    atom = "send the drafted message (never auto-send)"
    monkeypatch.setattr(
        quicken,
        "_queue_residue_atoms",
        lambda: {atom: ["effort-level-ultracode, nous research outreach p"]},
    )

    doc = quicken.write_residue(
        [
            {
                "state": "STALLED",
                "title": "effort-level-ultracode",
                "decision": {"residue": atom},
            }
        ]
    )

    assert "effort-level-ultracode, effort-level-ultracode" not in doc
    assert "unblocks: effort-level-ultracode, nous research outreach p" in doc


def test_reap_done_apply_delegates_without_removing_worktree(tmp_path, monkeypatch):
    quicken = _load()
    worktree = tmp_path / ".claude" / "worktrees" / "spent"
    worktree.mkdir(parents=True)
    calls: list[tuple[str, ...]] = []

    def fake_git(_cwd: str, *args: str) -> tuple[int, str, str]:
        calls.append(args)
        if args == ("status", "--porcelain"):
            return 0, "", ""
        if args == ("rev-parse", "--abbrev-ref", "HEAD"):
            return 0, "spent-branch", ""
        if args[:2] in {("worktree", "remove"), ("branch", "-D")}:
            raise AssertionError(f"quicken must not physically remove roots: {args}")
        return 1, "", "unexpected"

    monkeypatch.setattr(quicken, "_git", fake_git)
    monkeypatch.setattr(quicken, "_branch_merged", lambda _cwd, _branch: (True, "0 commits ahead of origin/main"))

    result = quicken.reap_done(
        [
            {
                "state": "DONE",
                "cwd": str(worktree),
                "title": "Spent finished session",
                "is_self": False,
            }
        ],
        self_cwd=str(tmp_path / "other"),
        apply=True,
    )

    assert result["reaped"] == []
    assert result["delegated"] == [("Spent finished session", "spent-branch", "0 commits ahead of origin/main")]
    assert worktree.exists()
    assert ("worktree", "remove", str(worktree)) not in calls
    assert ("branch", "-D", "spent-branch") not in calls


def _stalled_row(sid: str, cwd: str, title: str = "repeat offender session") -> dict:
    return {
        "sessionId": sid,
        "title": title,
        "last_prompt": "Resume and FINISH your original purpose",
        "cwd": cwd,
        "moved": 0.0,
        "state": "STALLED",
        "is_self": False,
        "decision": {"residue": None, "layer": "ideal-form", "n_done": 0, "n_pending": 0},
    }


def _journal_with_breathes(tmp_path, sid: str, n: int):
    journal = tmp_path / "session-lifecycle.jsonl"
    lines = [f'{{"ts": 1, "breathed": "{sid}", "ok": true}}' for _ in range(n)]
    lines.append("not json at all {{{")  # malformed lines must be ignored (fail-open)
    journal.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return journal


def test_breathe_counts_ignores_malformed_lines(tmp_path, monkeypatch):
    quicken = _load()
    sid = "aaaabbbb-1111-2222-3333-444455556666"
    monkeypatch.setattr(quicken, "JOURNAL", _journal_with_breathes(tmp_path, sid, 2))

    assert quicken._breathe_counts() == {sid: 2}


def test_breathe_escalates_repeat_offender_idempotently(tmp_path, monkeypatch, capsys):
    quicken = _load()
    sid = "aaaabbbb-1111-2222-3333-444455556666"
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text("version: '1.0'\ntasks: []\n", encoding="utf-8")
    monkeypatch.setattr(quicken, "JOURNAL", _journal_with_breathes(tmp_path, sid, 2))
    monkeypatch.setattr(quicken, "LEDGER", tasks)
    row = _stalled_row(sid, str(tmp_path))

    quicken.breathe([row], "all", dry=False)

    out = capsys.readouterr().out
    assert f"ESCALATE {sid[:8]}" in out
    assert "0 session(s) within cap" in out  # removed from the breathe list, cap freed
    body = tasks.read_text(encoding="utf-8")
    assert f"ASK-quicken-escalate-{sid[:8]}" in body
    assert "quicken-escalate" in body
    assert f"claude --resume {sid}" in body
    # journal recorded the escalation
    assert any(e.get("escalated") == sid for e in quicken._read_jsonl(quicken.JOURNAL))

    # second run: already homed — no duplicate task, no crash
    before = tasks.read_text(encoding="utf-8")
    quicken.breathe([row], "all", dry=False)
    assert tasks.read_text(encoding="utf-8").count(f"ASK-quicken-escalate-{sid[:8]}") == before.count(
        f"ASK-quicken-escalate-{sid[:8]}"
    )


def test_breathe_under_threshold_still_breathes(tmp_path, monkeypatch, capsys):
    quicken = _load()
    sid = "ccccdddd-1111-2222-3333-444455556666"
    monkeypatch.setattr(quicken, "JOURNAL", _journal_with_breathes(tmp_path, sid, 1))
    row = _stalled_row(sid, str(tmp_path))

    quicken.breathe([row], "all", dry=True)

    out = capsys.readouterr().out
    assert f"DRY would breathe {sid}" in out
    assert "ESCALATE" not in out


def test_breathe_escalate_after_env_respected(tmp_path, monkeypatch, capsys):
    quicken = _load()
    sid = "eeeeffff-1111-2222-3333-444455556666"
    monkeypatch.setenv("LIMEN_QUICKEN_ESCALATE_AFTER", "5")
    monkeypatch.setattr(quicken, "JOURNAL", _journal_with_breathes(tmp_path, sid, 3))
    row = _stalled_row(sid, str(tmp_path))

    quicken.breathe([row], "all", dry=True)

    out = capsys.readouterr().out
    assert f"DRY would breathe {sid}" in out
    assert "ESCALATE" not in out


def test_breathe_named_sid_honored_over_escalation(tmp_path, monkeypatch, capsys):
    quicken = _load()
    sid = "abcdabcd-1111-2222-3333-444455556666"
    monkeypatch.setattr(quicken, "JOURNAL", _journal_with_breathes(tmp_path, sid, 4))
    row = _stalled_row(sid, str(tmp_path))

    quicken.breathe([row], sid, dry=True)

    out = capsys.readouterr().out
    assert f"DRY would breathe {sid}" in out
    assert "ESCALATE" not in out


def test_breathe_drops_lever_blocked_session(tmp_path, monkeypatch, capsys):
    """Loop-terminator regression (the 2026-07-10 closeout-loop fix): a STALLED session whose cascade
    landed on a reserved human lever (decision.residue set) is filed ONCE by hang_residue and must
    NEVER be re-breathed — re-breathing a filed-blocked session is the endless loop the 'BLOCKED once,
    then stop' rule forbids. A reversible (residue-free) session still breathes. High cap ensures the
    FILTER, not the cap, is what drops the blocked one."""
    monkeypatch.setenv("LIMEN_QUICKEN_BREATHE_CAP", "5")
    quicken = _load()
    monkeypatch.setattr(quicken, "JOURNAL", tmp_path / "journal.jsonl")

    clean_cwd = tmp_path / "clean"
    blocked_cwd = tmp_path / "blocked"
    clean_cwd.mkdir()  # _contended() drops any cwd that is not a real present dir
    blocked_cwd.mkdir()
    clean = _stalled_row("cleanaaaa-1111-2222-3333-444455556666", str(clean_cwd))
    blocked = _stalled_row("blockedbb-2222-3333-4444-555566667777", str(blocked_cwd))
    blocked["decision"] = {"residue": "land the credential (your account)", "layer": "protocol"}

    quicken.breathe([clean, blocked], "all", dry=True)
    out = capsys.readouterr().out

    assert "cleanaaaa" in out  # reversible session IS breathed
    assert "blockedbb" not in out  # lever-blocked session is filed-once, never re-breathed (no loop)
