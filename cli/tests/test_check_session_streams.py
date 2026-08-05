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

    GitHub's squash-merge USUALLY appends its own `Co-authored-by:` paragraph, which pushes an
    author-written trailer out of the final paragraph — git's trailer parser then returns nothing.
    A body-regex survives that; the trailer parser does not.

    This originally asserted the parser returns empty for *every* such commit ("9 of 9 measured").
    That was stronger than the rationale needs, and it was falsified the first time a squash landed
    WITHOUT an appended co-author paragraph (2ce472e2, #1817), leaving `Claude-Session:` in the
    final paragraph where git duly parsed it. The test then failed on `origin/main` itself and
    blocked every open PR in the repo — a red trunk caused by ordinary GitHub variance, not by any
    change to git.

    The property that actually justifies SETTLES_RE is UNRELIABILITY, not uniform failure: whether
    the parser sees an author trailer depends on what GitHub chose to append, so it cannot be
    depended on either way. One commit where it returns empty proves that. Asserting it never sees
    the trailer is a claim about GitHub's merge behavior that this repo does not control.
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
    unseen_by_parser = 0
    for record in records:
        _sha, parsed, body = record.split("\x00", 2)
        # The body always carries the line — which is exactly why a %B regex is dependable.
        assert "Claude-Session:" in body
        if not parsed.strip():
            unseen_by_parser += 1

    assert unseen_by_parser, (
        "git's trailer parser saw the trailer on EVERY sampled commit — if that is now reliable, "
        "re-evaluate whether SETTLES_RE still needs to be a body regex"
    )


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


# ── predicate_command: the argv guard ───────────────────────────────────────────────
# Settlement now RUNS something, so the registry gained a path to executing commands. The guard is
# what keeps that path from reaching an effector. Every case below is refused STATICALLY — nothing
# in this section executes any candidate argv.


def test_only_a_runner_may_be_argv0():
    for cmd in ("rm -rf /", "scripts/repo-genesis.py --name x", "gh repo create foo"):
        assert M.predicate_argv_violation(cmd), f"{cmd!r} must be refused"
    assert M.predicate_argv_violation("bash scripts/run-pytest-hermetic.sh cli/tests/x.py -q") is None


def test_act_tokens_are_refused_anywhere_in_the_argv():
    for tok in M.PREDICATE_FORBIDDEN_TOKENS:
        assert M.predicate_argv_violation(f"python3 scripts/x.py {tok}"), f"{tok} must be refused"


def test_a_mutate_by_default_effector_is_refused_without_its_neutraliser():
    """The subtle half. Blocking --apply is BACKWARDS for repo-genesis.py, whose default IS to act:
    it mints a real GitHub repo and pushes seed material unless --dry-run is passed. An argv with no
    forbidden token at all is still an effector, and a guard that only blocklists act-flags would
    wave it through."""
    assert M.predicate_argv_violation("python3 scripts/repo-genesis.py --name foo --evidence x"), (
        "an effector that mutates BY DEFAULT slipped past the guard"
    )
    assert M.predicate_argv_violation("python3 scripts/repo-genesis.py --name foo --dry-run") is None


def test_no_two_streams_may_share_a_predicate_command():
    """A shared probe cannot say WHICH domain is done — 7 of 11 rows share a `predicate` file today
    (check-convergence.py -> s3/s6/s7, check-atom-homing.py -> s1/s2, no-tasks-on-me.sh -> s4/s5)."""
    streams = M.load()
    seen = {}
    for sid, s in streams.items():
        cmd = (s or {}).get("predicate_command")
        if cmd:
            assert cmd not in seen, f"{sid} and {seen[cmd]} share predicate_command {cmd!r}"
            seen[cmd] = sid


def test_every_declared_predicate_command_is_statically_safe():
    for sid, s in M.load().items():
        cmd = (s or {}).get("predicate_command")
        if cmd:
            assert M.predicate_argv_violation(cmd) is None, f"{sid}: {M.predicate_argv_violation(cmd)}"


def test_an_unprovable_stream_is_not_settled_by_a_claim_alone():
    """The AND. A claim without a passing predicate is an assertion, which is what this replaced."""
    assert M._predicate_proven("fake", {}) is False
    assert M._predicate_proven("fake", {"predicate_command": "python3 -c 'raise SystemExit(1)'"}) is False
    assert M._predicate_proven("fake", {"predicate_command": "python3 -c 'pass'"}) is True


# ── checks G, K, L: fields that were declared and unread ────────────────────────────
# Each of these guarded nothing until 2026-07-29, and each had a live violation sitting in the
# registry the whole time. A declared field nothing reads is a field that has already drifted.


def test_check_g_rejects_a_class_the_tier_authority_cannot_see():
    """G was a LITERAL no-op: it computed the class set and never compared it. Three rows declared
    `governance` — unknown to the authority — and silently derived the cheapest default tier for a
    work domain."""
    opus = M._opus_classes()
    assert opus, "the tier authority is unreachable"
    for sid, s in M.load().items():
        assert s["job_class"] in opus, f"{sid}: {s['job_class']!r} derives the default tier silently"


def test_check_g_refuses_a_reserved_fable_class():
    """docs/fable-allotment.md makes Fable PLAN-ONLY and prohibits building on it. A row declaring
    one of these would derive a Fable pin for a build lane — recreating the defect s9 healed."""
    fable = M._fable_classes()
    assert fable, "the reserved-Fable set is unreachable"
    assert not (set(fable) & {s["job_class"] for s in M.load().values()})
    # The two sets must stay disjoint, or "reject Fable" and "require Opus" could contradict.
    assert not (set(fable) & set(M._opus_classes()))


def test_check_k_every_owner_of_record_resolves():
    """Nothing checked this. s8 pointed at institutio/governance/estate.yaml — a path that never
    existed — while its own predicate reads institutio/github/estate.yaml."""
    for sid, s in M.load().items():
        owner = s["owner_of_record"]
        assert (ROOT / owner).exists(), f"{sid}: owner_of_record {owner!r} does not exist"


def test_check_l_fanout_bound_matches_the_cartridge():
    """max_children is stated twice — here and in prose in the cartridge. The prose copy is what a
    cold session actually reads before deciding how many children to open, and it is the copy
    nothing would ever check."""
    import re as _re

    for sid, s in M.load().items():
        text = (ROOT / s["intent"]).read_text()
        stated = _re.search(r"[Aa]t most \*\*(\d+)\*\* children", text)
        if stated:
            assert int(stated.group(1)) == s["max_children"], (
                f"{sid}: registry says {s['max_children']}, cartridge says {stated.group(1)}"
            )
