"""A declared enforcement artifact with no runner is inert.

The defect these pin: every check-*.py verifies declaration↔file parity — the registry names a
script, the script exists, the gate literal appears in a beat source. None asks who EXECUTES that
file. `scripts/metabolize.sh` satisfies every existing check while being invoked by nothing, so 43
sensors are declared, gated on, and have never run; `verify-whole.sh` then skips three rungs on the
recorded grounds that "the beat via metabolize.sh" covers them. Neither side runs them.

The hard part is distinguishing INVOCATION from MENTION. `verify-whole.sh` names metabolize.sh in a
comment explaining why it skips work; a substring search would read that as proof the runner runs and
mask the exact bug. Half of these tests are negative controls for that.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def rc():
    spec = importlib.util.spec_from_file_location("rc_mod", ROOT / "scripts" / "check-runner-coverage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── invocation vs mention — the whole difficulty of the check ────────────────────────────────


@pytest.mark.parametrize(
    "line",
    [
        'bash "$LIMEN_ROOT/scripts/drain.sh"',
        "python3 scripts/beat-sensors.py --run",
        'exec "$PY" "$LIMEN_ROOT/scripts/creds-hydrate.py" --apply',
        "  bash scripts/verify-whole.sh || true",
        "/usr/bin/env bash scripts/metabolize.sh",
    ],
)
def test_real_invocations_are_detected(rc, line):
    assert rc.invoked_scripts(line), f"missed a real invocation: {line}"


@pytest.mark.parametrize(
    "line",
    [
        "# the env/url liveness rungs run in the beat via scripts/metabolize.sh step 0e.",
        "#   - scripts/metabolize.sh cd's into the live checkout and runs every rung",
        "# no cadence_key: runs as a scripts/metabolize.sh pre-beat check (section 0h)",
    ],
)
def test_comments_are_not_invocations(rc, line):
    """THE false positive this check exists to avoid. A comment explaining why a runner is skipped
    must never be read as proof the runner runs."""
    assert not rc.invoked_scripts(line), f"a comment was read as an invocation: {line}"


def test_prose_reference_in_a_docstring_is_not_an_invocation(rc):
    body = 'MESSAGE = "the checkout `scripts/metabolize.sh` cd\'s into and runs every rung from"'
    assert "scripts/metabolize.sh" not in rc.invoked_scripts(body)


# ── reachability closure, against the real repo ──────────────────────────────────────────────


def test_heartbeat_is_reachable_and_metabolize_is_not(rc):
    """The live defect, pinned. heartbeat-loop.sh is named by a tracked launchd plist; metabolize.sh
    is named by no plist, no workflow, and no reachable script."""
    reachable = rc.reachable_scripts()
    assert "scripts/heartbeat-loop.sh" in reachable
    assert "scripts/metabolize.sh" not in reachable


def test_reachability_is_transitive(rc):
    """drain.sh has no plist of its own — it is reachable only because heartbeat-loop.sh invokes it.
    Without the closure, every second-hop script would look orphaned."""
    assert "scripts/drain.sh" in rc.reachable_scripts()


def test_a_mentioning_but_reachable_script_does_not_confer_reachability(rc):
    """verify-whole.sh IS reachable and DOES name metabolize.sh — in a comment. If mention counted,
    the defect would be invisible precisely because the skip is documented."""
    reachable = rc.reachable_scripts()
    assert "scripts/verify-whole.sh" in reachable
    text = (ROOT / "scripts" / "verify-whole.sh").read_text()
    assert "metabolize.sh" in text, "fixture drifted — verify-whole.sh no longer mentions the runner"
    assert "scripts/metabolize.sh" not in rc.invoked_scripts(text)


def test_workflow_path_filters_do_not_confer_reachability(rc, tmp_path):
    """A workflow's `paths:` names files it WATCHES. Counting those would make every registry-listed
    script look reachable — including the one gates.yaml lists for check-sensors."""
    workflow = tmp_path / "wf.yml"
    workflow.write_text(
        "on:\n  pull_request:\n    paths: ['scripts/metabolize.sh']\n"
        "jobs:\n  a:\n    steps:\n      - run: python3 scripts/check-gates.py\n"
    )
    found = rc._workflow_invocations(workflow)
    assert "scripts/check-gates.py" in found
    assert "scripts/metabolize.sh" not in found


def test_plist_program_arguments_confer_reachability(rc, tmp_path):
    plist = tmp_path / "x.plist"
    plist.write_text(
        "<plist><dict><key>ProgramArguments</key><array>"
        "<string>/bin/bash</string><string>/x/scripts/thing.sh</string>"
        "</array></dict></plist>"
    )
    assert "scripts/thing.sh" in rc._plist_invocations(plist)


# ── hook honesty: only a PreToolUse hook can deny, and a negation is not a claim ──────────────


def test_affirmative_pretooluse_claim_is_a_claim(rc):
    assert rc.claims_to_block("# PreToolUse(Bash) hook: HARD BLOCK on rm -rf. It denies outright.")


@pytest.mark.parametrize(
    "text",
    [
        "# PreToolUse hook\n#   - never blocks session end (always exit 0)",
        "# PreToolUse hook\n#   - ALWAYS exits 0 (advisory) so it never blocks an edit",
        "# PreToolUse hook\n# cannot block a session even on a non-zero exit",
    ],
)
def test_negated_prose_is_not_a_claim(rc, text):
    """A hook documenting that it does NOT block must not be forced to delete accurate prose."""
    assert not rc.claims_to_block(text)


def test_non_pretooluse_hooks_are_never_flagged(rc):
    """SessionStart/PostToolUse hooks have no deny channel, so blocking words in them are prose."""
    assert not rc.claims_to_block("# SessionEnd hook: this blocks nothing and denies nothing.")


def test_live_hooks_all_pass(rc):
    findings: list[str] = []
    rc.check_hooks(findings)
    assert findings == [], f"a shipped hook claims to block without deciding: {findings}"


# ── the baseline ratchet ─────────────────────────────────────────────────────────────────────


def test_repo_is_green_against_its_baseline(rc, capsys):
    assert rc.main([]) == 0
    assert "no new findings" in capsys.readouterr().out


def test_a_new_finding_fails_even_with_a_populated_baseline(rc, monkeypatch, tmp_path, capsys):
    """The ratchet must catch a NEW artifact-without-a-runner, not merely tolerate the known set."""
    empty = tmp_path / "baseline.txt"
    empty.write_text("# no findings baselined\n")
    monkeypatch.setattr(rc, "BASELINE", empty)
    assert rc.main([]) == 1
    out = capsys.readouterr().out
    assert "NEW finding" in out
    assert "metabolize.sh" in out, "the live defect must be what fails an empty baseline"


def test_baselined_findings_are_the_three_known_ones(rc):
    """Named explicitly so silently widening the baseline shows up in review as a test edit."""
    baselined = rc.read_baseline()
    assert len(baselined) == 3
    joined = "\n".join(baselined)
    assert "scripts/metabolize.sh" in joined
    assert "scripts/preflight-thread-state.py" in joined
    assert "scripts/trunk-ci-health.py" in joined
