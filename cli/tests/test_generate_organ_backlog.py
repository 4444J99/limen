"""The organ-backlog generator must survive a ladder row it cannot build a PR contract for.

Measured live 2026-08-07: `generate-organ-backlog` failed on EVERY beat with

    limen.intake.IntakeContractError: cannot build PR contract without exact owner/repo and task id

because `organ-ladder.json`'s BIFRONS row carries
`"repo": "organvm/limen (beat) + organvm-engine/alchemia/ontologia (loop)"`. That organ genuinely
spans two repositories and a single `repo` field cannot say so, so its value is prose rather than a
slug — and every generated task carries a `github_pr_contract` keyed on an exact `owner/repo`.

Two things made it invisible and expensive:

  * `_organs()` promises "[] on any error (the generator must never break the feed beat)", but the
    raise happens one layer down in `_plan`, outside that protection.
  * The floor/headroom early-return skips the planning loop whenever the organ queue is already
    full. So the generator crashed exactly when it had work to do and stayed quiet when it did
    not — and nothing recorded either, until #2050 gave the beat a rung recorder and #2062 made
    the recorder honest.

The estate's own diagnosis is that the binding constraint is the SUPPLY of high-value work, which
is what this generator exists to produce. So a crash here is not cosmetic.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "generate-organ-backlog.py"

# The real shape from organ-ladder.json — an organ that spans two repos, so `repo` holds prose.
SPANNING_ORGAN = {
    "organ": "BIFRONS / Star <-> Contribution Portal",
    "repo": "organvm/limen (beat) + organvm-engine/alchemia/ontologia (loop)",
    "stage": "building",
    "rank": 1,
    "pillar": "bifrons",
    "maturity": 40,
}
GOOD_ORGAN = {
    "organ": "Observation",
    "repo": "organvm/limen",
    "stage": "building",
    "rank": 2,
    "pillar": "observation",
    "maturity": 40,
}


def _ladder(path: Path, organs: list[dict]) -> Path:
    path.write_text(json.dumps({"organs": organs}))
    return path


def _board(path: Path) -> Path:
    """A board with no organ-class open tasks, so the generator has work to do."""
    path.write_text(yaml.safe_dump({"portal": {"budget": {"daily": 100, "per_agent": {}}}, "tasks": []}))
    return path


def _run(tmp_path: Path, organs: list[dict], floor: int = 5) -> subprocess.CompletedProcess:
    ladder = _ladder(tmp_path / "organ-ladder.json", organs)
    board = _board(tmp_path / "tasks.yaml")
    env = {
        **os.environ,
        "LIMEN_ORGAN_LADDER": str(ladder),
        "LIMEN_TASKS": str(board),
        "PYTHONPATH": str(ROOT / "cli" / "src"),
    }
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--tasks", str(board), "--floor", str(floor)],
        capture_output=True,
        text=True,
        env=env,
        cwd=ROOT,
    )


def test_a_spanning_repo_row_is_skipped_and_named_not_fatal(tmp_path):
    """The regression, directly: this combination used to exit 1 with an IntakeContractError."""
    res = _run(tmp_path, [SPANNING_ORGAN, GOOD_ORGAN])
    assert res.returncode == 0, res.stdout + res.stderr
    assert "IntakeContractError" not in res.stdout + res.stderr
    assert "skipped 1 organ(s) with no exact owner/repo" in res.stdout
    assert "BIFRONS" in res.stdout


def test_the_generator_still_produces_work_for_the_remaining_organs(tmp_path):
    """Skipping must not degrade into a silent no-op — the supply valve has to stay open."""
    res = _run(tmp_path, [SPANNING_ORGAN, GOOD_ORGAN])
    assert "generating" in res.stdout, res.stdout
    assert "organvm/limen" in res.stdout


def test_a_ladder_of_only_spanning_rows_is_a_clean_no_op(tmp_path):
    """Nothing buildable is a reportable state, not a crash and not a lie about why."""
    res = _run(tmp_path, [SPANNING_ORGAN])
    assert res.returncode == 0, res.stdout + res.stderr
    assert "skipped 1 organ(s) with no exact owner/repo" in res.stdout
    assert "nothing to generate" in res.stdout


def test_the_guard_shares_the_contract_builders_definition_of_owner_repo():
    """A second definition of "exact owner/repo" would drift; the guard imports the real one.

    Asserted against the raiser itself, so this fails if either side is redefined independently.
    """
    sys.path.insert(0, str(ROOT / "cli" / "src"))
    from limen.intake import REPO_RE, IntakeContractError, github_pr_contract

    assert not REPO_RE.fullmatch(SPANNING_ORGAN["repo"])
    assert REPO_RE.fullmatch(GOOD_ORGAN["repo"])
    # The guard's predicate and the raiser's are the same object, so agreement is structural —
    # but assert the consequence anyway: what the guard admits, the builder can build.
    assert github_pr_contract(GOOD_ORGAN["repo"], "ORG-x-y-0101").receipt_target
    try:
        github_pr_contract(SPANNING_ORGAN["repo"], "ORG-x-y-0101")
    except IntakeContractError:
        pass
    else:  # pragma: no cover - would mean the raiser stopped guarding
        raise AssertionError("github_pr_contract accepted a repo the guard rejects")
