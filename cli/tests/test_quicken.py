from __future__ import annotations

import importlib.util
from pathlib import Path


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


def test_hang_residue_does_not_refresh_unchanged_human_ask(tmp_path, monkeypatch):
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
    assert result["refreshed"] == []
    assert result["homed"] == [f"{atom} \u2192 ASK-quicken-credential"]
    assert tasks.read_text(encoding="utf-8") == before


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
