"""Tests for scripts/routine-freshness-audit.py."""

from __future__ import annotations

import datetime
import importlib.util
import json
from pathlib import Path

from limen.io import load_limen_file

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "routine-freshness-audit.py"
MANIFEST = ROOT / "cloud-routines.json"


def _load(monkeypatch=None, *, root=None):
    spec = importlib.util.spec_from_file_location("routine_freshness_audit", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    if root is not None and monkeypatch is not None:
        monkeypatch.setenv("LIMEN_ROOT", str(root))
    spec.loader.exec_module(mod)
    return mod


# ── helpers ──────────────────────────────────────────────────────────────────


def _utc(*args) -> datetime.datetime:
    return datetime.datetime(*args, tzinfo=datetime.timezone.utc)


def _row(name="test-routine", cls="delta-gated", max_days=7, issue=42, repo="owner/repo", may_be_silent=False):
    row = {
        "name": name,
        "class": cls,
        "max_silent_days": max_days,
        "issue": issue,
        "issue_repo": repo,
        "enabled": True,
    }
    if may_be_silent:
        row["may_be_silent"] = True
    return row


# ── classify tests ────────────────────────────────────────────────────────────


def test_classify_green():
    mod = _load()
    now = _utc(2026, 7, 8, 12, 0, 0)
    last = _utc(2026, 7, 6, 12, 0, 0)  # 2 days ago, max=7
    verdict, age = mod.classify(_row(), last, "comment", now)
    assert verdict == "green"
    assert age is not None and age < 7


def test_classify_stale_10_days_max_7():
    mod = _load()
    now = _utc(2026, 7, 8, 12, 0, 0)
    last = _utc(2026, 6, 28, 12, 0, 0)  # 10 days ago; max=7; 2x=14 → stale
    verdict, age = mod.classify(_row(), last, "comment", now)
    assert verdict == "stale"
    assert 9.9 < age < 10.1


def test_classify_down_20_days_max_7():
    mod = _load()
    now = _utc(2026, 7, 8, 12, 0, 0)
    last = _utc(2026, 6, 18, 12, 0, 0)  # 20 days ago; max=7; 2x=14 → down
    verdict, age = mod.classify(_row(), last, "comment", now)
    assert verdict == "down"
    assert age > 14


def test_classify_unknown_on_error():
    mod = _load()
    now = _utc(2026, 7, 8, 12, 0, 0)
    verdict, age = mod.classify(_row(), None, "error", now)
    assert verdict == "unknown"
    assert age is None


def test_classify_unmonitored_pr_delivery():
    mod = _load()
    now = _utc(2026, 7, 8, 12, 0, 0)
    r = _row(cls="pr-delivery", issue=None, repo=None)
    verdict, age = mod.classify(r, None, "unmonitored", now)
    assert verdict == "unmonitored"
    assert age is None


def test_classify_unmonitored_null_issue():
    mod = _load()
    now = _utc(2026, 7, 8, 12, 0, 0)
    r = _row(issue=None, repo=None)
    verdict, age = mod.classify(r, None, "unmonitored", now)
    assert verdict == "unmonitored"


def test_unmonitored_never_down(monkeypatch):
    """A pr-delivery routine must never be classified down regardless of time."""
    mod = _load()
    now = _utc(2026, 7, 8, 12, 0, 0)
    r = _row(cls="pr-delivery", issue=None, repo=None)
    # Even if somehow last_ts is very old — unmonitored wins
    verdict, _ = mod.classify(r, None, "unmonitored", now)
    assert verdict != "down"


def test_gh_failure_gives_unknown_not_down(monkeypatch):
    mod = _load()
    now = _utc(2026, 7, 8, 12, 0, 0)
    verdict, age = mod.classify(_row(), None, "error", now)
    assert verdict == "unknown"
    assert age is None


# ── may_be_silent → quiet tests (limen#894: healthy-silent must not read as "down") ───────────


def test_classify_quiet_when_may_be_silent_and_would_be_down():
    """A may_be_silent routine silent past 2x max reads 'quiet', NOT 'down' — no operator atom."""
    mod = _load()
    now = _utc(2026, 7, 8, 12, 0, 0)
    last = _utc(2026, 6, 13, 12, 0, 0)  # 25 days ago; max=7; 2x=14 → would be down for a normal row
    verdict, age = mod.classify(_row(may_be_silent=True), last, "comment", now)
    assert verdict == "quiet"
    assert age is not None and age > 14


def test_classify_quiet_when_may_be_silent_and_would_be_stale():
    """may_be_silent collapses the stale tier to quiet too — silence at any age is not a defect."""
    mod = _load()
    now = _utc(2026, 7, 8, 12, 0, 0)
    last = _utc(2026, 6, 28, 12, 0, 0)  # 10 days ago; max=7; would be stale for a normal row
    verdict, _ = mod.classify(_row(may_be_silent=True), last, "comment", now)
    assert verdict == "quiet"


def test_classify_may_be_silent_recent_still_green():
    """A may_be_silent routine that DID post recently still reads green — the flag only caps silence."""
    mod = _load()
    now = _utc(2026, 7, 8, 12, 0, 0)
    last = _utc(2026, 7, 6, 12, 0, 0)  # 2 days ago, max=7
    verdict, _ = mod.classify(_row(may_be_silent=True), last, "comment", now)
    assert verdict == "green"


def test_classify_may_be_silent_never_delivered_is_quiet():
    """Never-delivered (no comments) on a may_be_silent routine is quiet, not down/stale."""
    mod = _load()
    now = _utc(2026, 7, 8, 12, 0, 0)
    # no-comments path with unresolvable issue age → quiet (not stale) for a may_be_silent routine
    verdict, _ = mod.classify(_row(may_be_silent=True, repo=None), None, "no-comments", now)
    assert verdict == "quiet"


def test_classify_without_flag_still_down():
    """Regression guard: a routine WITHOUT may_be_silent keeps today's 'down' behavior (organ still
    catches genuinely-dead routines — the flag does not leak to un-flagged rows)."""
    mod = _load()
    now = _utc(2026, 7, 8, 12, 0, 0)
    last = _utc(2026, 6, 13, 12, 0, 0)  # 25 days ago; max=7 → down
    verdict, _ = mod.classify(_row(may_be_silent=False), last, "comment", now)
    assert verdict == "down"


# ── hang_down_atoms tests ────────────────────────────────────────────────────

_TASK_YAML_TEMPLATE = """\
version: '1.0'
tasks: []
"""


def test_hang_down_atoms_creates_task(tmp_path, monkeypatch):
    mod = _load()
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text(_TASK_YAML_TEMPLATE, encoding="utf-8")
    monkeypatch.setattr(mod, "LEDGER", tasks)

    r = _row(name="atom-backlog-triage")
    r["_days_silent"] = 25.0
    result = mod.hang_down_atoms([r])

    assert "ASK-routine-atom-backlog-triage" in result.get("created", [])

    data = tasks.read_text(encoding="utf-8")
    assert "ASK-routine-atom-backlog-triage" in data
    assert "needs_human" in data
    assert "routine-freshness" in data


def test_hang_down_atoms_idempotent(tmp_path, monkeypatch):
    """Run twice; only one task should be created (idempotent)."""
    mod = _load()
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text(_TASK_YAML_TEMPLATE, encoding="utf-8")
    monkeypatch.setattr(mod, "LEDGER", tasks)

    r = _row(name="atom-backlog-triage")
    r["_days_silent"] = 25.0

    mod.hang_down_atoms([r])
    result2 = mod.hang_down_atoms([r])

    # second run: task already exists → should be homed or refreshed, NOT created again
    assert "ASK-routine-atom-backlog-triage" not in result2.get("created", [])

    task_ids = [task.id for task in load_limen_file(tasks).tasks]
    assert task_ids.count("ASK-routine-atom-backlog-triage") == 1


def test_hang_down_atoms_gh_failure_no_atom(tmp_path, monkeypatch):
    """A gh-failure (unknown verdict) must not produce an atom."""
    mod = _load()
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text(_TASK_YAML_TEMPLATE, encoding="utf-8")
    monkeypatch.setattr(mod, "LEDGER", tasks)

    # unknown verdict rows are NOT passed to hang_down_atoms at all (only "down" rows are)
    result = mod.hang_down_atoms([])  # empty — no unknown rows trigger atoms
    assert result["created"] == []


# ── retire_recovered_atoms tests (the symmetric half: condition clears → atom retracts) ────────


def test_retire_recovered_atom_and_idempotent(tmp_path, monkeypatch):
    """A routine that was down and is now healthy has its ASK-routine atom retired (→done), once."""
    mod = _load()
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text(_TASK_YAML_TEMPLATE, encoding="utf-8")
    monkeypatch.setattr(mod, "LEDGER", tasks)

    r = _row(name="omega-scorecard")
    r["_days_silent"] = 25.0
    mod.hang_down_atoms([r])  # opens the atom
    assert "ASK-routine-omega-scorecard" in tasks.read_text(encoding="utf-8")

    # routine no longer down → retire
    res1 = mod.retire_recovered_atoms(set(), ["omega-scorecard"])
    assert res1["retired"] == ["ASK-routine-omega-scorecard"]
    retired = load_limen_file(tasks).tasks[0]
    assert retired.dispatch_log[-1].lifecycle_repair == "routine-recovered"
    assert retired.dispatch_log[-1].routine_name == "omega-scorecard"
    assert retired.dispatch_log[-1].routine_observed_state == "recovered"

    # second run: already done → not retired again (idempotent)
    res2 = mod.retire_recovered_atoms(set(), ["omega-scorecard"])
    assert res2["retired"] == []


def test_retire_skips_still_down_routine(tmp_path, monkeypatch):
    """A routine still in the down set keeps its atom — retirement must not race the alert."""
    mod = _load()
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text(_TASK_YAML_TEMPLATE, encoding="utf-8")
    monkeypatch.setattr(mod, "LEDGER", tasks)

    r = _row(name="omega-scorecard")
    r["_days_silent"] = 25.0
    mod.hang_down_atoms([r])

    res = mod.retire_recovered_atoms({"omega-scorecard"}, ["omega-scorecard"])
    assert res["retired"] == []


def test_retire_ignores_non_organ_task(tmp_path, monkeypatch):
    """Only atoms this organ created (labelled 'routine-freshness') are retired — never a human's."""
    mod = _load()
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text(_TASK_YAML_TEMPLATE, encoding="utf-8")
    monkeypatch.setattr(mod, "LEDGER", tasks)

    import sys as _sys

    _sys.path.insert(0, str(ROOT / "cli" / "src"))
    from datetime import date, datetime, timezone

    from limen.io import load_limen_file, save_limen_file
    from limen.models import Task

    lf = load_limen_file(tasks)
    lf.tasks.append(
        Task(
            id="ASK-routine-foreign",
            title="human-made, not the organ's",
            type="ops",
            target_agent="human",
            priority="high",
            status="needs_human",
            labels=["user-ask"],  # NOT routine-freshness
            context="mine",
            created=date.today(),
            updated=datetime.now(timezone.utc),
        )
    )
    save_limen_file(tasks, lf)

    res = mod.retire_recovered_atoms(set(), ["foreign"])
    assert res["retired"] == []

    reread = {t.id: t for t in load_limen_file(tasks).tasks}
    assert reread["ASK-routine-foreign"].status == "needs_human"  # untouched


# ── throttle short-circuit test ───────────────────────────────────────────────


def test_throttle_short_circuit(tmp_path, monkeypatch, capsys):
    """If the artifact is younger than throttle, main() should print 'throttled' and return 0."""
    mod = _load()

    # Write a fresh artifact
    out = tmp_path / "routine-freshness.json"
    out.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(mod, "OUT", out)
    monkeypatch.setattr(mod, "MANIFEST", MANIFEST)

    import sys as _sys

    orig_argv = _sys.argv[:]
    _sys.argv = ["routine-freshness-audit.py", "--throttle", "99999"]
    try:
        rc = mod.main()
    finally:
        _sys.argv = orig_argv

    out_text, _ = capsys.readouterr()
    assert rc == 0
    assert "throttled" in out_text


# ── manifest integrity test ───────────────────────────────────────────────────


def test_manifest_has_13_enabled_rows_with_required_keys():
    """The checked-in cloud-routines.json must have exactly 13 enabled rows with required keys."""
    data = json.loads(MANIFEST.read_text())
    rows = [r for r in data.get("routines", []) if r.get("enabled", True)]
    assert len(rows) == 13, f"expected 13 enabled rows, got {len(rows)}"
    required = {"name", "issue_repo", "issue", "cadence", "class", "max_silent_days", "enabled"}
    for row in rows:
        missing = required - set(row.keys())
        assert not missing, f"row {row.get('name')} missing keys: {missing}"


def test_omega_scorecard_is_may_be_silent_and_flag_is_opt_in():
    """limen#894: omega-scorecard (posts only on fixed-point change) carries may_be_silent so it stops
    manufacturing false 'down' atoms. The flag must be OPT-IN — NOT blanket-applied to every
    delta-gated row, or the organ goes blind to genuinely-dead routines. Guard both facts."""
    data = json.loads(MANIFEST.read_text())
    rows = data.get("routines", [])
    by_name = {r["name"]: r for r in rows}
    assert by_name["omega-scorecard"].get("may_be_silent") is True

    delta_gated = [r for r in rows if r.get("class") == "delta-gated"]
    flagged = [r for r in delta_gated if r.get("may_be_silent")]
    # opt-in, deliberate: only the proven case carries it, not the whole class
    assert 0 < len(flagged) < len(delta_gated), (
        "may_be_silent must be a deliberate per-routine opt-in, not applied to every delta-gated row"
    )
