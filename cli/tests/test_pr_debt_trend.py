"""IF-AMALGAMATION's probe: is open-PR debt going down, and is anyone still looking?

The registry row carried `probe: null` with an exact reason — "the ideal is a monotonic TREND, not
a level… a real probe needs a committed series, so the debt-trend recorder is this row's next
form." The series was already committed. `gitvs.py` writes `open_pr_count` into
`docs/github-pr-debt-ledger.json` and every write is a commit, so five observations sat in
`git log` for eleven days unread. Nothing had to be built; something had to be READ.

Two properties matter and the second is the one a naive trend predicate gets wrong:

  1. growth is measured across the series, not between two arbitrary points;
  2. STALENESS IS NOT AT-IDEAL. A debt series nobody records is not a debt trend that improved.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "pr-debt-trend.py"
LEDGER_REL = "docs/github-pr-debt-ledger.json"


@pytest.fixture()
def mod(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("pr_debt_trend", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["pr_debt_trend"] = module
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    return module


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "docs").mkdir()
    return tmp_path


def _observe(root: Path, count: int, stamp: str) -> None:
    """One recorded observation — exactly the shape gitvs.py writes."""
    (root / LEDGER_REL).write_text(
        json.dumps({"open_pr_count": count, "generated_at": f"{stamp}T12:00:00Z"}), encoding="utf-8"
    )
    _git(root, "add", LEDGER_REL)
    _git(root, "-c", "user.name=t", "commit", "-q", "-m", f"obs {count}", f"--date={stamp}T12:00:00")


def test_the_series_is_read_out_of_git_not_stored_anywhere(mod, repo):
    """A recorder writing its own series file would be a second copy of a number git versions."""
    for n, day in ((1059, "2026-07-22"), (1111, "2026-07-23"), (1164, "2026-07-25")):
        _observe(repo, n, day)
    rows = mod.series()
    assert [n for _, n, _ in rows] == [1059, 1111, 1164], "oldest first — a series reads forward"
    assert not (repo / "logs").exists(), "nothing is written; the observations were already committed"


def test_growth_is_reported_with_its_sign_and_the_probe_fails_on_it(mod, repo, capsys, monkeypatch):
    monkeypatch.setenv("LIMEN_PR_DEBT_MAX_AGE_DAYS", "3650")  # isolate growth from freshness
    for n, day in ((1059, "2026-07-22"), (1164, "2026-07-25")):
        _observe(repo, n, day)
    monkeypatch.setattr(sys, "argv", ["pr-debt-trend.py", "--check"])
    assert mod.main() == 1
    out = capsys.readouterr().out
    assert "debt_growth=+105" in out
    assert "the debt GREW by 105" in out


def test_a_falling_debt_is_at_ideal(mod, repo, capsys, monkeypatch):
    monkeypatch.setenv("LIMEN_PR_DEBT_MAX_AGE_DAYS", "3650")
    for n, day in ((1164, "2026-07-22"), (900, "2026-07-25")):
        _observe(repo, n, day)
    monkeypatch.setattr(sys, "argv", ["pr-debt-trend.py", "--check"])
    assert mod.main() == 0
    assert "debt_growth=-264" in capsys.readouterr().out


def test_silence_is_not_improvement(mod, repo, capsys, monkeypatch):
    """The half that matters. The debt fell, but nobody has looked in a year — that is not a pass.

    Without this the predicate would go GREEN the moment the producer died, which is the exact
    failure mode the ideal exists to prevent: debt accretes fastest when nothing is watching.
    """
    monkeypatch.setenv("LIMEN_PR_DEBT_MAX_AGE_DAYS", "3")
    for n, day in ((1164, "2025-01-01"), (900, "2025-01-04")):
        _observe(repo, n, day)
    _git(repo, "commit", "-q", "--allow-empty", "-m", "much later work")  # moves "today"
    monkeypatch.setattr(sys, "argv", ["pr-debt-trend.py", "--check"])
    assert mod.main() == 1
    out = capsys.readouterr().out
    assert "STALE" in out
    assert "silence is not improvement" in out
    assert "gitvs.py reconcile" in out or "gitvs.py" in out, "the failure must name its producer"


def test_a_single_observation_is_unmeasurable_and_that_is_a_failure(mod, repo, capsys, monkeypatch):
    """Not 'at ideal' and not drift in the probe — the evidence is absent, which is the state
    this row sat in for eleven days while reporting nothing at all."""
    _observe(repo, 1164, "2026-07-25")
    monkeypatch.setattr(sys, "argv", ["pr-debt-trend.py", "--check"])
    assert mod.main() == 1
    assert "UNMEASURABLE" in capsys.readouterr().out


def test_no_ledger_at_all_is_unmeasurable_not_green(mod, repo, capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["pr-debt-trend.py", "--check"])
    assert mod.main() == 1
    assert "UNMEASURABLE" in capsys.readouterr().out


def test_an_uncommitted_observation_still_counts(mod, repo, monkeypatch):
    """gitvs writes the file before anything commits it; freshness is about what the PRODUCER did."""
    _observe(repo, 1164, "2026-07-25")
    (repo / LEDGER_REL).write_text(
        json.dumps({"open_pr_count": 800, "generated_at": "2026-08-02T09:00:00Z"}), encoding="utf-8"
    )
    rows = mod.series()
    assert rows[-1] == ("2026-08-02", 800, "worktree")


def test_a_corrupt_snapshot_is_skipped_rather_than_crashing_the_series(mod, repo):
    _observe(repo, 1059, "2026-07-22")
    (repo / LEDGER_REL).write_text("{ not json", encoding="utf-8")
    _git(repo, "add", LEDGER_REL)
    _git(repo, "commit", "-q", "-m", "corrupt")
    _observe(repo, 1164, "2026-07-25")
    assert [n for _, n, _ in mod.series()] == [1059, 1164]


def test_the_registry_row_actually_names_this_script(mod):
    """A probe wired to a script that does not exist is the vacuum wearing a costume.

    check-ideal-forms.py's check C already asserts the file exists; this pins the pairing so a
    rename of either side cannot quietly leave IF-AMALGAMATION unprobed again.
    """
    import yaml

    row = yaml.safe_load((ROOT / "institutio/governance/ideal-forms.yaml").read_text())["ideals"]["IF-AMALGAMATION"]
    probe = row.get("probe")
    assert probe, "IF-AMALGAMATION must not go back to `probe: null`"
    assert "pr-debt-trend.py" in probe["command"]
    assert probe["at_ideal_when"] == "exit_zero"
    assert probe["environment"] == "host", "a shallow CI checkout truncates git history — never read that as at-ideal"
