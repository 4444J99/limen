"""Tests for scripts/check-ledger-custody.py — custody for a governed measurement document.

`tasks.yaml` has had a keeper for a long time: a sole logical writer, SHA compare-and-swap, and
`scripts/task-writer-audit.py` to catch a bypass writer before it can race the projection. Every
other document recording durable truth had a convention instead — and the difference is on the
record. `docs/IDEAL-FORMS-LEDGER.md` reports that five of the six observations in the open-PR debt
series were side effects of unrelated feature PRs that happened to regenerate the ledger, and that
the series stopped when that unrelated work did.

The three checks answer three different ways a series gets diluted, so each is tested from both
sides — the violation it must catch, and the legitimate shape it must not flag. A custody
predicate that only ever goes green is indistinguishable from no predicate at all, which is
precisely the state the ledger was already in.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts" / "check-ledger-custody.py"

LEDGER_REL = "docs/github-pr-debt-ledger.json"
KEEPER_REL = "scripts/pr-debt-trend.py"
PRODUCER_REL = "scripts/gitvs.py"
READER_REL = "scripts/diurnal.py"
KEEPER_SUBJECT = "docs(gitvs): record open-PR debt observation (1293 open)"


@pytest.fixture
def mod(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("check_ledger_custody_under_test", CHECK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setattr(m, "ROOT", tmp_path)
    return m


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(root), check=True, capture_output=True, text=True)


def _commit(root: Path, subject: str) -> str:
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q", "-m", subject)
    out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(root), capture_output=True, text=True, check=True)
    return out.stdout.strip()


def _write_ledger(root: Path, count: int, stamp: str) -> None:
    path = root / LEDGER_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"open_pr_count": count, "generated_at": stamp}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_registry(root: Path, **overrides) -> None:
    entry = {
        "path": LEDGER_REL,
        "owner": "gitvs",
        "note": "test fixture",
        "keeper": KEEPER_REL,
        "producer": PRODUCER_REL,
        "readers": [READER_REL],
        "commit_subject": r"^docs\(gitvs\): record open-PR debt observation \(\d+ open\)",
        "baseline": "institutio/governance/ledger-custody-baseline.txt",
        "series_key": "generated_at",
        "count_key": "open_pr_count",
    }
    entry.update(overrides)
    path = root / "institutio" / "governance" / "ledger-custody.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump({"schema_version": 0.1, "ledgers": {"github-pr-debt": entry}}),
        encoding="utf-8",
    )


def _write_baseline(root: Path, *lines: str) -> None:
    path = root / "institutio" / "governance" / "ledger-custody-baseline.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# baseline\n" + "".join(f"{line}\n" for line in lines), encoding="utf-8")


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    for rel in (KEEPER_REL, PRODUCER_REL, READER_REL):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        # Each declared role names the ledger, exactly as the real ones do — so check B is
        # exercised against files that WOULD trip it if the declaration were not honoured.
        path.write_text(f'LEDGER = "{LEDGER_REL}"\n', encoding="utf-8")
    _write_registry(tmp_path)
    _write_baseline(tmp_path)
    _commit(tmp_path, "chore: scaffold")
    return tmp_path


def _findings(mod, prefix: str) -> list[str]:
    ledgers = mod.load_registry()
    spec = ledgers["github-pr-debt"]
    baseline = mod.load_baseline(spec.get("baseline"))
    if prefix == "A":
        return mod.check_a_passengers("github-pr-debt", spec, baseline)
    if prefix == "B":
        return mod.check_b_touchers("github-pr-debt", spec)
    return mod.check_c_series("github-pr-debt", spec, baseline)


# ── A: the recorded defect — an unrelated commit carrying the ledger ──────────────


def test_a_flags_a_commit_that_carried_the_ledger_as_a_passenger(mod, repo):
    _write_ledger(repo, 1293, "2026-08-06T03:17:46Z")
    _commit(repo, "feat: close PR lifecycle estate at fixed point")

    found = _findings(mod, "A")
    assert len(found) == 1, "an unrelated subject touching the ledger is the whole defect class"
    assert "passenger" in found[0]


def test_a_accepts_a_keeper_ship(mod, repo):
    _write_ledger(repo, 1293, "2026-08-06T03:17:46Z")
    _commit(repo, KEEPER_SUBJECT)

    assert _findings(mod, "A") == []


def test_a_exempts_a_baselined_commit_but_not_its_successor(mod, repo):
    _write_ledger(repo, 1059, "2026-07-22T10:00:00Z")
    historic = _commit(repo, "feat: add uncapped exact PR debt census")
    _write_baseline(repo, f"{historic} github-pr-debt")
    _commit(repo, "chore: baseline it")

    assert _findings(mod, "A") == [], "history is recorded, not rewritten"

    _write_ledger(repo, 1115, "2026-07-24T10:00:00Z")
    _commit(repo, "feat: some later unrelated work")
    found = _findings(mod, "A")
    assert len(found) == 1, "the ratchet is shrink-only — a fresh passenger is never grandfathered"


# ── B: the next dilution, pre-empted — an undeclared toucher ──────────────────────


def test_b_flags_an_undeclared_toucher(mod, repo):
    (repo / "scripts" / "some-new-organ.py").write_text(f'LEDGER = "{LEDGER_REL}"\n', encoding="utf-8")

    found = _findings(mod, "B")
    assert len(found) == 1
    assert "scripts/some-new-organ.py" in found[0]


def test_b_accepts_every_declared_role(mod, repo):
    assert _findings(mod, "B") == [], "keeper, producer and readers all name the path by design"


def test_b_ignores_tests(mod, repo):
    path = repo / "scripts" / "tests" / "some-organ.test.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'LEDGER = "{LEDGER_REL}"\n', encoding="utf-8")

    assert _findings(mod, "B") == [], "a test exercising the keeper is not competing with it"


# ── C: integrity of the series itself ─────────────────────────────────────────────


def test_c_flags_two_commits_claiming_one_census(mod, repo):
    """The write-side twin of the phantom `[worktree]` row that reported +182 instead of +234."""
    stamp = "2026-08-06T03:17:46Z"
    _write_ledger(repo, 1293, stamp)
    _commit(repo, KEEPER_SUBJECT)
    _write_ledger(repo, 1301, stamp)
    _commit(repo, KEEPER_SUBJECT)

    found = _findings(mod, "C")
    assert len(found) == 1
    assert "two rows, one observation" in found[0]


def test_c_flags_an_out_of_order_series(mod, repo):
    _write_ledger(repo, 1293, "2026-08-06T03:17:46Z")
    _commit(repo, KEEPER_SUBJECT)
    _write_ledger(repo, 1301, "2026-08-05T01:00:00Z")
    _commit(repo, KEEPER_SUBJECT)

    found = _findings(mod, "C")
    assert len(found) == 1
    assert "out of order" in found[0]


def test_c_accepts_a_forward_series(mod, repo):
    for count, stamp in ((1059, "2026-07-22T10:00:00Z"), (1293, "2026-08-06T03:17:46Z")):
        _write_ledger(repo, count, stamp)
        _commit(repo, KEEPER_SUBJECT)

    assert _findings(mod, "C") == []


def test_c_exempts_an_immutable_baselined_duplicate_but_not_a_fresh_one(mod, repo):
    stamp = "2026-08-06T03:17:46Z"
    _write_ledger(repo, 1293, stamp)
    _commit(repo, KEEPER_SUBJECT)
    _write_ledger(repo, 1301, stamp)
    historic = _commit(repo, "feat: merged passenger")
    _write_baseline(repo, f"{historic} github-pr-debt")
    _commit(repo, "chore: record immutable history")

    assert _findings(mod, "C") == []

    _write_ledger(repo, 1302, stamp)
    _commit(repo, KEEPER_SUBJECT)
    found = _findings(mod, "C")
    assert len(found) == 1
    assert "two rows, one observation" in found[0]


def test_c_keeps_a_baselined_row_as_duplicate_state(mod, repo):
    stamp = "2026-08-06T03:17:46Z"
    _write_ledger(repo, 1293, stamp)
    historic = _commit(repo, "feat: immutable historical census")
    _write_baseline(repo, f"{historic} github-pr-debt")
    _commit(repo, "chore: record immutable history")

    _write_ledger(repo, 1301, stamp)
    _commit(repo, KEEPER_SUBJECT)

    found = _findings(mod, "C")
    assert len(found) == 1
    assert "two rows, one observation" in found[0]


def test_c_keeps_a_baselined_row_as_ordering_state(mod, repo):
    _write_ledger(repo, 1293, "2026-08-06T03:17:46Z")
    historic = _commit(repo, "feat: immutable historical census")
    _write_baseline(repo, f"{historic} github-pr-debt")
    _commit(repo, "chore: record immutable history")

    _write_ledger(repo, 1301, "2026-08-05T01:00:00Z")
    _commit(repo, KEEPER_SUBJECT)

    found = _findings(mod, "C")
    assert len(found) == 1
    assert "out of order" in found[0]


# ── the predicate as a whole, through its real surface ────────────────────────────


def test_main_exits_nonzero_on_a_violation_and_zero_when_custody_holds(repo, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(repo))
    _write_ledger(repo, 1293, "2026-08-06T03:17:46Z")
    _commit(repo, "feat: unrelated work that regenerated the ledger")

    proc = subprocess.run([sys.executable, str(CHECK)], cwd=str(repo), capture_output=True, text=True, check=False)
    assert proc.returncode == 1, proc.stdout
    assert "FAIL" in proc.stdout

    _write_baseline(
        repo,
        subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(repo), capture_output=True, text=True, check=True
        ).stdout.strip()
        + " github-pr-debt",
    )
    _commit(repo, "chore: record history")

    proc = subprocess.run([sys.executable, str(CHECK)], cwd=str(repo), capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stdout
    assert "OK" in proc.stdout
