"""Tests for settlement in scripts/check-session-streams.py — the registry's most forgeable claim.

`settled` decides the ready-set, which decides what an operator opens. It was derived by
`git log origin/main --grep=<id> --fixed-strings`: unanchored, so a commit merely MENTIONING an id
settled it. That is not a theoretical hole — it fired on `s10-axis-coverage` within a day, off a
docs commit whose entire subject was that s10 owns work a plan should *not* do. The domain read
`settled` and left the ready set with none of its work built.

These tests exist because the defect was invisible: the checker had no tests at all, and check F's
docstring asserted the stronger property it does not have ("there is no field to lie in") while the
lie had simply relocated into a commit message.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts" / "check-session-streams.py"


def _mod():
    spec = importlib.util.spec_from_file_location("check_session_streams_settlement", CHECK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


M = _mod()


# ── the anchor itself: pure, no git, so these can never be flaky ────────────────────


@pytest.mark.parametrize(
    "body,expected",
    [
        # THE REGRESSION. Verbatim subject of 0a17877b, which settled s10 under the old rule.
        ("docs(plans): the omega rung belongs to s10-axis-coverage, not to this plan (#1624)", []),
        # A mention in prose, however emphatic, is still a mention.
        ("fix: unblock s6-registry-correction\n\nThis does NOT settle s6-registry-correction.", []),
        # The claim, made properly.
        ("feat: whatever\n\nSettles: s6-registry-correction", ["s6-registry-correction"]),
        # Indented ⇒ not a claim. Column 0 is the whole point of the anchor: quoted or
        # code-fenced text inside a body must never be able to settle anything.
        ("feat: whatever\n\n    Settles: s6-registry-correction", []),
        # Mid-line ⇒ not a claim.
        ("feat: whatever\n\nsee also Settles: s6-registry-correction", []),
        # One commit may honestly settle several ids.
        (
            "feat: x\n\nSettles: s2-public-distillation, s3-governance-case-law",
            ["s2-public-distillation, s3-governance-case-law"],
        ),
    ],
)
def test_only_an_anchored_claim_counts(body, expected):
    assert M.SETTLES_RE.findall(body) == expected


def test_the_trailer_is_read_from_the_body_not_gits_trailer_parser():
    """Locks in WHY this is a regex over %B and not `%(trailers:key=Settles)`.

    GitHub's squash-merge appends its own `Co-authored-by:` paragraph, which pushes an
    author-written trailer out of the final paragraph — git's trailer parser then returns nothing.
    Measured on this repo: 9 of 9 commits carrying a `Claude-Session:` line yield EMPTY from
    `%(trailers:key=Claude-Session,valueonly)`. A body-regex survives that; the trailer parser does
    not. If this ever starts failing, git's parser has changed and the choice can be revisited.
    """
    out = subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "log",
            "origin/main",
            "--grep",
            "Claude-Session:",
            "--fixed-strings",
            "--max-count=9",
            "--format=%H%x00%(trailers:key=Claude-Session,valueonly)%x00%B%x01",
        ],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    records = [r for r in out.split("\x01") if r.count("\x00") >= 2]
    if not records:
        pytest.skip("no Claude-Session commits reachable here")
    for record in records:
        _sha, parsed, body = record.split("\x00", 2)
        assert "Claude-Session:" in body
        assert parsed.strip() == "", "git's trailer parser now sees it — re-evaluate SETTLES_RE"


# ── bookkeeping cannot settle a stream ─────────────────────────────────────────────


def test_a_registry_only_commit_does_no_real_work():
    """The registry may not talk a row into `settled`.

    Uses the real commit that shipped this very registry's docs-only correction — a commit that
    names a stream id and touches nothing but docs/plans.
    """
    assert M._does_real_work("0a17877b") is False


def test_a_commit_that_ships_code_does_real_work():
    # 7ba07525 is #1619: cli/src/limen/workstream_contract.py, cli.py, tests.
    assert M._does_real_work("7ba07525") is True


# ── the live registry stays honest ─────────────────────────────────────────────────


def test_the_real_registry_is_green():
    proc = subprocess.run([sys.executable, str(CHECK)], cwd=ROOT, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_s10_is_not_settled_by_the_commit_that_merely_named_it():
    """The regression, asserted against live state rather than a fixture.

    s10-axis-coverage has no `Settles:` claim and no settled_by, so it must be openable. If this
    fails, either someone genuinely settled s10 (then delete this test WITH its row) or the anchor
    has regressed to substring matching.
    """
    assert M._settled("s10-axis-coverage") is False


def test_the_backfill_is_bounded_and_every_entry_is_real():
    backfill = M._settled_by_backfill()
    assert len(backfill) <= M.MAX_SETTLED_BY
    for sid, sha in backfill.items():
        assert M._does_real_work(sha), f"{sid}: settled_by {sha} is bookkeeping, not work"
        # Reachable from origin/main — an unmerged SHA would list itself here.
        unreached = subprocess.run(
            ["git", "-C", str(ROOT), "rev-list", "--max-count=1", sha, "^origin/main"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        assert unreached == "", f"{sid}: settled_by {sha} is not on origin/main"
