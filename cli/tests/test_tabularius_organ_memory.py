"""Regression tests for the TABVLARIVS keeper memory pass (issue #2866).

These assert the DESIRED contract and are expected to FAIL on the defective
baseline revision 24da5bffeefb855f1968e0c830c1ca5445a291cf. They are deliberately
red there: passing them by expecting the unwanted state write, by suppressing
`_stamp()`, or by weakening an assertion would hide the defect.

Historical evidence that the defect occurs is preserved separately as the
11-case reproduction bundle, not as a passing test here.

Two independent defects are covered:

1. `--check` and `--dry-run` are documented as non-mutating, but the outer
   `_stamp()` creates `ROOT/logs/` and writes `tabularius-organ-state.json`
   regardless of whether the memory pass ran, failed, or was disabled.
2. Normal mode computes the memory result and then discards it: the outcome is
   absent from every state stamp and from every return decision, so a failing
   memory pass is invisible in published status.

Observation limits: PEP 578 audit hooks observe events raised by the child
interpreter only. They are not an OS-wide write trace and not a sandbox, they
cannot detect a concurrent external writer, and a create-then-delete between
snapshots leaves no persistent trace. `test_write_observer_limits_are_documented`
keeps that caveat attached to the suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tabularius_organ_fixtures import (  # noqa: E402
    OBSERVATION_LIMITS,
    STATE_RELPATH,
    KeeperSandbox,
    provenance,
)

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def test_provenance_is_recorded():
    """The executed entry point and the child interpreter must be identifiable."""
    prov = provenance()
    assert Path(prov["entry_point"]).exists(), prov
    assert Path(prov["child_interpreter"]).exists(), prov
    assert prov["child_python_version"], prov
    # The child must not depend on user-site resolution, which the sandbox
    # disables by redirecting HOME.
    assert not str(Path(prov["child_interpreter"])).startswith(
        str(Path.home() / "Library")
    ), f"child interpreter relies on user site-packages: {prov}"


# --- 1. no-write contract -----------------------------------------------------

@pytest.mark.parametrize("flag", ["--check", "--dry-run"])
def test_mode_does_not_create_health_state(tmp_path, flag):
    """A non-mutating mode must not create the health-state directory or file."""
    sb = KeeperSandbox(tmp_path, f"create-{flag.strip('-')}")
    assert not sb.state_path.exists(), "precondition: health-state file absent"
    proc = sb.run(flag)
    assert not sb.state_path.exists(), (
        f"{flag} created {sb.state_path} despite a non-mutating contract\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    assert not sb.write_attempts_in(str(sb.state_path)), (
        f"{flag} opened the health-state file for writing:\n"
        + "\n".join(sb.write_attempts_in(str(sb.state_path)))
    )


@pytest.mark.parametrize("flag", ["--check", "--dry-run"])
def test_mode_does_not_overwrite_existing_health_state(tmp_path, flag):
    """A non-mutating mode must leave an existing health-state file byte-identical."""
    sb = KeeperSandbox(tmp_path, f"overwrite-{flag.strip('-')}", health_state="preexisting")
    before = sb.state_path.read_bytes()
    before_mtime = sb.state_path.stat().st_mtime_ns
    proc = sb.run(flag)
    assert sb.state_path.read_bytes() == before, (
        f"{flag} overwrote an existing health-state file\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    assert sb.state_path.stat().st_mtime_ns == before_mtime, (
        f"{flag} rewrote an existing health-state file\n"
        f"stdout: {proc.stdout}"
    )


def test_check_mode_writes_independently_of_memory_enabled(tmp_path):
    """Characterisation: the outer write does not depend on the memory pass.

    Documents that the no-write violation is a separate defect from the broken
    memory import, not a consequence of it.
    """
    sb = KeeperSandbox(tmp_path, "control-memoria-disabled", memoria=False)
    proc = sb.run("--check")
    # On the defective baseline this writes; the assertion documents the control.
    wrote = sb.state_path.exists()
    assert wrote is False, (
        "--check wrote a health-state file with MEMORIA disabled, confirming the "
        "outer write is unconditional rather than caused by the memory failure\n"
        f"stdout: {proc.stdout}"
    )


# --- 2. memory-result propagation ---------------------------------------------

def _memory_evidence(state: dict) -> bool:
    """True when the stamp carries a memory outcome (counts or an error)."""
    if any(k.startswith("memory_") for k in state):
        return True
    return any(k in state for k in ("memory_pending", "memory_applied", "memory_rejected"))


@pytest.mark.parametrize("board_mode", [None, "deferred", "processed"])
def test_normal_mode_propagates_memory_outcome(tmp_path, board_mode):
    """Normal execution must publish the memory outcome it computed.

    Covers the empty, deferred, and processed board branches. The deferred and
    processed branches stub only the external board boundary; the real entry
    point and the real state writer are exercised.
    """
    name = f"propagate-{board_mode or 'empty'}"
    sb = KeeperSandbox(
        tmp_path, name, memoria=True, memory_populated=True,
        health_state="preexisting", board_mode=board_mode,
    )
    proc = sb.run()
    state = sb.state_payload()
    assert state, f"no health-state artifact was published; stdout: {proc.stdout}"
    assert _memory_evidence(state), (
        "the memory outcome was computed but is absent from the published state "
        f"stamp; state={state}\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    )


# --- protective: the keeper must not mutate the memory store -------------------

@pytest.mark.parametrize("flag", ["--check", "--dry-run"])
def test_memory_store_is_not_mutated(tmp_path, flag):
    """Protective regression: the keeper must not alter the memory store."""
    sb = KeeperSandbox(tmp_path, f"memstore-{flag.strip('-')}", memory_populated=True)
    ticket = sb.memory_dir / ".covenant-inbox" / "synthetic.json"
    before = ticket.read_bytes()
    sb.run(flag)
    assert ticket.exists(), f"{flag} consumed a pending memory ticket"
    assert ticket.read_bytes() == before, f"{flag} mutated a pending memory ticket"


# --- observation-limit guard ---------------------------------------------------

def test_write_observer_limits_are_documented():
    """A no-write assertion must never be read as a sandbox guarantee."""
    assert OBSERVATION_LIMITS, "observation limits must stay attached to the suite"
    joined = " ".join(OBSERVATION_LIMITS).lower()
    assert "not a sandbox" in joined or "not an os-wide write trace" in joined


def test_state_relpath_is_the_documented_location():
    assert STATE_RELPATH == "logs/tabularius-organ-state.json"


def test_fixture_state_path_agrees_with_limen_root(tmp_path):
    """Guard against a path drift that would make no-write assertions vacuous.

    The entry point resolves STATE as LIMEN_ROOT / STATE_RELPATH. If the sandbox
    ever checks a different location, every "did not write" test would pass
    without observing anything.
    """
    sb = KeeperSandbox(tmp_path, "path-agreement")
    expected = sb.limen_root / STATE_RELPATH
    assert sb.state_path == expected, (sb.state_path, expected)
    assert sb.env["LIMEN_ROOT"] == str(sb.limen_root)