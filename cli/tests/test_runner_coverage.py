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
    assert "trunk-ci-health" in out, "the remaining live defect must be what fails an empty baseline"


def test_baselined_findings_are_the_one_known_one(rc):
    """Named explicitly so silently widening the baseline shows up in review as a test edit.

    Was three, then two, now ONE. `scripts/preflight-thread-state.py` cured finding C; then the
    heartbeat gained its metabolize sensor pass (`beat-sensors.py --run --source metabolize`,
    2026-08-06, jules-flywheel PR-E), which is a real runner for every metabolize-source sensor —
    finding A stopped reproducing and the ratchet tightened again. Editing this assertion is the
    intended review signal in BOTH directions: a baseline that grows must be argued for in a diff.
    """
    baselined = rc.read_baseline()
    assert len(baselined) == 1
    joined = "\n".join(baselined)
    assert "scripts/trunk-ci-health.py" in joined
    assert "scripts/metabolize.sh" not in joined, "the metabolize sensors have a live runner; its finding must be gone"
    assert "preflight-thread-state" not in joined, "the predicate exists; its finding must be gone"


# ── F: a declared gate must have something that RUNS it ──────────────────────────────────────


def _gates_fixture(tmp_path, gates: dict) -> Path:
    import yaml

    path = tmp_path / "gates.yaml"
    path.write_text(yaml.safe_dump({"gates": gates}, sort_keys=False))
    return path


def test_gate_runner_check_is_green_on_the_live_registry(rc):
    findings: list[str] = []
    rc.check_gate_runners(findings)
    assert findings == [], f"a declared gate runs nowhere: {findings}"


def test_the_outbound_gate_is_actually_wired_into_verify_whole(rc):
    """The fix itself, asserted against the real file rather than a fixture.

    `outbound-preflight-test` shipped `scoped: false` with no ci_job and was named by verify-whole.sh
    nowhere, so its deny matrix never ran. Both rungs must appear here or the gate is decorative.
    """
    whole = (ROOT / "scripts" / "verify-whole.sh").read_text()
    assert "scripts/tests/outbound-preflight-guard.test.sh" in whole
    assert "scripts/tests/preflight-thread-state.test.sh" in whole


def test_a_whole_only_gate_absent_from_verify_whole_is_a_finding(rc, monkeypatch, tmp_path):
    """NEGATIVE CONTROL — reproduce the exact defect. Without this the check could be vacuous."""
    gates = _gates_fixture(
        tmp_path,
        {"orphan-gate": {"command": "bash scripts/tests/nobody-runs-me.test.sh", "scoped": False}},
    )
    whole = tmp_path / "verify-whole.sh"
    whole.write_text("#!/usr/bin/env bash\nbash scripts/tests/something-else.test.sh\n")
    monkeypatch.setattr(rc, "GATES", gates)
    monkeypatch.setattr(rc, "VERIFY_WHOLE", whole)
    findings: list[str] = []
    rc.check_gate_runners(findings)
    assert len(findings) == 1
    assert "gate-unrun" in findings[0]
    assert "orphan-gate" in findings[0]


def test_naming_the_command_in_verify_whole_clears_the_finding(rc, monkeypatch, tmp_path):
    """The other half of the control: the same gate passes once something runs it."""
    gates = _gates_fixture(
        tmp_path,
        {"orphan-gate": {"command": "bash scripts/tests/nobody-runs-me.test.sh", "scoped": False}},
    )
    whole = tmp_path / "verify-whole.sh"
    whole.write_text("#!/usr/bin/env bash\nbash scripts/tests/nobody-runs-me.test.sh\n")
    monkeypatch.setattr(rc, "GATES", gates)
    monkeypatch.setattr(rc, "VERIFY_WHOLE", whole)
    findings: list[str] = []
    rc.check_gate_runners(findings)
    assert findings == []


@pytest.mark.parametrize(
    ("gate", "why"),
    [
        (
            {"command": "bash scripts/tests/x.test.sh", "paths": ["scripts/x.sh"]},
            "a scoped gate is selected by verify.py --changed; verify-whole.sh need not name it",
        ),
        (
            {"command": "bash scripts/tests/x.test.sh", "scoped": False, "ci_job": "pr-gate.yml:pr-gate"},
            "a declared ci_job is a runner",
        ),
        (
            {"command": "", "scoped": False},
            "a commandless gate is a file_set provider consumed via --print-files; nothing to run",
        ),
    ],
)
def test_legitimately_reachable_gates_are_not_flagged(rc, monkeypatch, tmp_path, gate, why):
    gates = _gates_fixture(tmp_path, {"g": gate})
    whole = tmp_path / "verify-whole.sh"
    whole.write_text("#!/usr/bin/env bash\n")
    monkeypatch.setattr(rc, "GATES", gates)
    monkeypatch.setattr(rc, "VERIFY_WHOLE", whole)
    findings: list[str] = []
    rc.check_gate_runners(findings)
    assert findings == [], why


def test_a_non_script_literal_confers_reachability(rc, monkeypatch, tmp_path):
    """`plist-lint` runs `plutil -lint container/launchd/*.plist` and names no script at all.

    A scripts-only pattern would report it unreachable while verify-whole.sh runs those exact lines —
    a false positive that would push an author to delete a correct gate.
    """
    gates = _gates_fixture(
        tmp_path,
        {"plist-lint": {"command": "plutil -lint container/launchd/com.user.netmeter.plist", "scoped": False}},
    )
    whole = tmp_path / "verify-whole.sh"
    whole.write_text("plutil -lint container/launchd/com.user.netmeter.plist\n")
    monkeypatch.setattr(rc, "GATES", gates)
    monkeypatch.setattr(rc, "VERIFY_WHOLE", whole)
    findings: list[str] = []
    rc.check_gate_runners(findings)
    assert findings == []


def test_a_scoped_gate_with_no_paths_can_never_be_selected(rc, monkeypatch, tmp_path):
    """verify.py select() matches changed paths against gate_paths(); an empty list matches nothing,
    so the gate is declared and permanently inert. Zero gates are in this state today."""
    gates = _gates_fixture(tmp_path, {"pathless": {"command": "bash scripts/tests/x.test.sh"}})
    monkeypatch.setattr(rc, "GATES", gates)
    monkeypatch.setattr(rc, "VERIFY_WHOLE", tmp_path / "absent.sh")
    findings: list[str] = []
    rc.check_gate_runners(findings)
    assert len(findings) == 1
    assert "gate-unselectable" in findings[0]
