"""Regression tests for the TABVLARIVS keeper memory pass (issue #2866).

These assert the DESIRED contract. They are expected to FAIL on the defective
baseline and PASS after the bounded repair.

Two independent defects are covered:

1. `--check` and `--dry-run` are documented as non-mutating, but the outer
   `_stamp()` creates `ROOT/logs/` and writes `tabularius-organ-state.json`
   regardless of whether the memory pass ran, failed, or was disabled.
2. Normal mode computes the memory result and discards it, so a failing memory
   pass is invisible in published status.

Three classes of false green are guarded against, because a no-write assertion
can pass without observing anything:

- a child that never reached the entry point (`run()` enforces a case-specific
  exit status plus positive entry-point evidence);
- an observer that recorded nothing (`write_attempts()` raises rather than
  returning an empty list);
- a memory pass that is still broken but whose error was merely propagated
  (`test_memory_outcome_is_never_silently_absent` is separate from
  `test_memory_pass_succeeds`).

Observation limits: PEP 578 audit hooks observe child-interpreter events only.
They are not an OS-wide write trace and not a sandbox, cannot detect a
concurrent external writer, and cannot exclude a create-then-delete between
snapshots. `test_observation_limits_are_documented` keeps that caveat attached.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tabularius_organ_fixtures import (
    OBSERVATION_LIMITS_DOC,
    STATE_RELPATH,
    VALID_TICKET,
    ChildDidNotStart,
    KeeperSandbox,
    ObservationUnavailable,
)

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

MEMORY_COUNT_KEYS = ("memory_pending", "memory_applied", "memory_rejected")
MEMORY_ERROR_KEYS = ("memory_error",)


# --- observer self-tests (guard the guard) ------------------------------------


def test_observer_records_known_mutations(tmp_path):
    """The observer must see create, rename-both-endpoints, and a real lock."""
    sb = KeeperSandbox(tmp_path, "observer-self-test")
    probe = sb.root / "probe"
    code = (
        "import os, fcntl, json\n"
        f"os.makedirs({str(sb.root / 'renamedir')!r}, exist_ok=True)\n"
        f"open({str(probe)!r}, 'w').write('x')\n"
        f"os.rename({str(probe)!r}, {str(sb.root / 'renamedir' / 'probe')!r})\n"
        f"fd = os.open({str(sb.root / 'renamedir' / 'probe')!r}, os.O_RDWR)\n"
        "fcntl.flock(fd, fcntl.LOCK_EX)\n"
        "fcntl.flock(fd, fcntl.LOCK_UN)\n"
        "os.close(fd)\n"
    )
    import subprocess

    subprocess.run([sys.executable, "-c", code], env=sb.env, capture_output=True, text=True, timeout=60, check=False)

    recs = sb.mutations()
    events = {r["event"] for r in recs}
    assert "open" in events, events
    assert any(e.startswith("os.rename") or e == "os.rename" for e in events), events
    assert "fcntl.flock" in events, f"lock events not observed; saw {sorted(events)}"

    rename = next(r for r in recs if r["event"] == "os.rename")
    assert len(rename["paths"]) >= 2, f"rename destination dropped: {rename}"
    assert any("renamedir" in str(p) for p in rename["paths"]), rename

    # The observer must self-report; a silent observer proves nothing.
    assert sb.child_reported_entry() is not None, "observer did not self-report"
    assert sb.child_reported_modules() is not None


def test_observer_refuses_to_satisfy_a_no_write_assertion(tmp_path):
    """Missing observer evidence must raise, never look like 'no writes'."""
    sb = KeeperSandbox(tmp_path, "observer-unavailable")
    with pytest.raises(ObservationUnavailable):
        sb.write_attempts(require=True)


def test_observation_limits_are_documented():
    """A no-write assertion must never be read as a sandbox guarantee."""
    joined = " ".join(OBSERVATION_LIMITS_DOC).lower()
    assert "not a sandbox" in joined or "not an operating-system-wide write trace" in joined
    assert "concurrent" in joined


def test_guard_rejects_child_that_never_reached_entry_point(tmp_path):
    """A child exiting early or by signal must not yield a vacuous pass."""
    sb = KeeperSandbox(tmp_path, "guard-negative")

    # Simulate a child that produced no output and a wrong exit status.
    class FakeProc:
        returncode = 9
        stdout = ""
        stderr = ""

    with pytest.raises(ChildDidNotStart):
        sb._guard(FakeProc(), expect_exit=0)

    class SignalProc:
        returncode = -9
        stdout = "partial"
        stderr = ""

    with pytest.raises(ChildDidNotStart):
        sb._guard(SignalProc(), expect_exit=0)


def test_guard_rejects_unrelated_output(tmp_path):
    """Printing something unrelated must not satisfy the identity guard.

    A substring-on-stdout check accepted a child that merely printed text. The
    guard now requires the observer's structured record of the executed entry
    point, so an unrelated-printing child is rejected.
    """
    sb = KeeperSandbox(tmp_path, "guard-unrelated-output", memoria=True)

    class ChattyProc:
        returncode = 0
        stdout = "not the keeper"
        stderr = ""

    with pytest.raises(ChildDidNotStart):
        sb._guard(ChattyProc(), expect_exit=0)

    # And the negative control from review: a real child with no observer
    # identity recorded must also be rejected.
    proc = subprocess.run(
        [sys.executable, "-c", "print('not the keeper')"],
        env=sb.env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    sb.last_proc = proc
    with pytest.raises(ChildDidNotStart):
        sb._guard(proc, expect_exit=0)


# --- fixture integrity --------------------------------------------------------


def test_fixture_state_path_agrees_with_limen_root(tmp_path):
    sb = KeeperSandbox(tmp_path, "path-agreement")
    assert sb.state_path == sb.limen_root / STATE_RELPATH
    assert sb.env["LIMEN_ROOT"] == str(sb.limen_root)


def test_valid_synthetic_ticket_has_required_model_fields(tmp_path):
    """A partial ticket is malformed input and cannot prove a successful drain."""
    required = {"ticket_id", "timestamp", "agent", "slug", "title", "desc"}
    assert required <= set(VALID_TICKET), required - set(VALID_TICKET)


# --- 1. no-write contract: full absent/populated x absent/pre-existing --------


@pytest.mark.parametrize("flag", ["--check", "--dry-run"])
@pytest.mark.parametrize("memstate", ["absent", "populated"])
@pytest.mark.parametrize("health", ["absent", "preexisting"])
def test_read_only_mode_leaves_protected_areas_unchanged(tmp_path, flag, memstate, health):
    """A non-mutating mode must not create, overwrite, or add anything.

    Compares whole-area inventories, so a new atom, receipt, lockfile, or bare
    directory is caught, not just a single known file.
    """
    sb = KeeperSandbox(
        tmp_path,
        f"ro-{flag.strip('-')}-{memstate}-{health}",
        memoria=True,
        memory_populated=(memstate == "populated"),
        health_state=health,
    )
    before = sb.protected_inventory()
    sb.run(flag, expect_exit=0)
    after = sb.protected_inventory()

    assert before == after, (
        f"{flag} mutated a protected area (mem={memstate}, health={health})\n"
        f"created : {sorted(set(after['root']) - set(before['root']))}\n"
        f"changed : {sorted(k for k in set(before['root']) & set(after['root']) if before['root'][k] != after['root'][k])}\n"
        f"mem new : {sorted(set(after['mem']) - set(before['mem']))}"
    )
    # Assert against every protected area, not just LIMEN_ROOT, and reject any
    # mutation the observer could not attribute to a path.
    sb.assert_no_protected_mutations()


def test_read_only_mode_does_not_create_bare_directory(tmp_path):
    """Directory creation alone is a mutation even with no file written."""
    sb = KeeperSandbox(tmp_path, "bare-dir", memoria=False)
    sb.run("--check", expect_exit=0)
    assert not sb.limen_root.exists(), f"--check created {sb.limen_root}"


def test_check_mode_write_is_independent_of_memory_state(tmp_path):
    """Control: the outer write is unconditional, not caused by the import failure."""
    sb = KeeperSandbox(tmp_path, "control-memoria-disabled", memoria=False)
    sb.run("--check", expect_exit=0)
    assert not sb.limen_root.exists(), "--check wrote a health-state file with MEMORIA disabled"


# --- 2. memory-result propagation ---------------------------------------------


def _memory_state(state: dict) -> str:
    """Classify the memory outcome present in a state stamp."""
    if any(k in state for k in MEMORY_ERROR_KEYS):
        return "error"
    if any(k in state for k in MEMORY_COUNT_KEYS):
        return "counts"
    return "absent"


@pytest.mark.parametrize("board_mode", [None, "deferred", "processed"])
def test_memory_outcome_is_never_silently_absent(tmp_path, board_mode):
    """Normal mode must publish the memory outcome it computed.

    Covers the empty, deferred, and processed board branches. Deferred and
    processed stub only the external board boundary; the real entry point and
    the real state writer are exercised.
    """
    sb = KeeperSandbox(
        tmp_path,
        f"outcome-{board_mode or 'empty'}",
        memoria=True,
        memory_populated=True,
        health_state="preexisting",
        board_mode=board_mode,
    )
    proc = sb.run()
    state = sb.state_payload()
    assert state, f"no health-state artifact published; stdout: {proc.stdout}"
    _assert_board_branch(state, board_mode)
    assert _memory_state(state) != "absent", (
        f"memory outcome computed but absent from the published stamp; state={state}\nstdout: {proc.stdout}"
    )


def _assert_board_branch(state: dict, board_mode) -> None:
    """Prove the requested board branch actually ran.

    Without this, a silently dead board-boundary injection makes every
    parameterised case fall through to the same empty-inbox branch and the
    three-branch coverage claim is false.
    """
    if board_mode == "deferred":
        assert state.get("deferred") is True, f"deferred branch not reached: {state}"
        assert state.get("pending") == 3, f"deferred pending not injected: {state}"
    elif board_mode == "processed":
        assert "deferred" not in state, f"processed branch not reached: {state}"
        assert state.get("applied") == 2, f"processed applied not injected: {state}"
        assert state.get("rejected") == 1, f"processed rejected not injected: {state}"
        assert state.get("wrote") == 2, f"processed wrote not injected: {state}"
    else:
        assert "deferred" not in state, f"empty branch expected: {state}"
        assert state.get("pending") == 0, f"empty pending expected: {state}"


def test_memory_pass_succeeds(tmp_path):
    """Separate from error propagation: the memory pass must actually work.

    Guards against a repair that merely propagates `memory_error` while leaving
    the invalid import in place. A valid ticket is pending, so an all-zero
    result is NOT success and must not satisfy this assertion.
    """
    sb = KeeperSandbox(tmp_path, "memory-succeeds", memoria=True, memory_populated=True)
    proc = sb.run()
    state = sb.state_payload()
    kind = _memory_state(state)
    assert kind != "error", f"memory pass still failing: state={state}\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    assert kind == "counts", f"memory pass reported no counts and no error; state={state}\nstdout: {proc.stdout}"
    assert state.get("memory_pending", 0) >= 1, (
        f"expected a pending ticket to be counted: state={state}\nstdout: {proc.stdout}"
    )


def test_valid_ticket_lifecycle_is_applied_then_idempotent(tmp_path):
    """The synthetic lifecycle: applied content, then no duplicate on re-run.

    Idempotence concerns the ticket's effects. The liveness `updated` timestamp
    legitimately changes on a second normal-mode run, so only ticket-derived
    content is compared.
    """
    sb = KeeperSandbox(tmp_path, "lifecycle", memoria=True, memory_populated=True)
    proc = sb.run()
    state = sb.state_payload()
    assert state.get("memory_applied", 0) >= 1, (
        f"pending valid ticket was not applied: state={state}\nstdout: {proc.stdout}"
    )
    atom = sb.memory_dir / f"{VALID_TICKET['slug']}.md"
    assert atom.exists(), f"expected atom {atom}; store={sorted(p.name for p in sb.memory_dir.iterdir())}"
    first = atom.read_bytes()

    proc2 = sb.run()
    state2 = sb.state_payload()
    assert state2.get("memory_applied", 0) == 0, f"re-run re-applied the same ticket: {state2}\nstdout: {proc2.stdout}"
    assert atom.read_bytes() == first, "atom content changed on a no-op re-run"


# --- lifecycle (temporary stores only) ----------------------------------------


@pytest.mark.parametrize("flag", ["--check", "--dry-run"])
def test_read_only_mode_does_not_consume_pending_ticket(tmp_path, flag):
    sb = KeeperSandbox(tmp_path, f"consume-{flag.strip('-')}", memoria=True, memory_populated=True)
    ticket = sb.memory_dir / ".covenant-inbox" / "synthetic.json"
    before = ticket.read_bytes()
    sb.run(flag, expect_exit=0)
    assert ticket.exists(), f"{flag} consumed a pending memory ticket"
    assert ticket.read_bytes() == before, f"{flag} mutated a pending memory ticket"


def test_pending_ticket_is_a_valid_ticket_on_disk(tmp_path):
    sb = KeeperSandbox(tmp_path, "ticket-valid", memoria=True, memory_populated=True)
    raw = json.loads((sb.memory_dir / ".covenant-inbox" / "synthetic.json").read_text())
    assert set(VALID_TICKET) <= set(raw), "fixture ticket is missing required fields"


def test_lock_events_are_attributed_to_the_protected_file(tmp_path):
    """A recorded lock must resolve to a path, not merely exist.

    The observer previously emitted `paths: []` when descriptor resolution
    failed, so a lock could be recorded yet never satisfy a path-based
    assertion. This asserts attribution, which event capture alone does not.
    """
    sb = KeeperSandbox(tmp_path, "lock-attribution", memoria=False)
    target = sb.limen_root / "protected.bin"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"x")
    code = (
        "import fcntl, os\n"
        f"fd = os.open({str(target)!r}, os.O_RDWR)\n"
        "fcntl.flock(fd, fcntl.LOCK_EX)\n"
        "fcntl.flock(fd, fcntl.LOCK_UN)\n"
        "os.close(fd)\n"
    )
    subprocess.run([sys.executable, "-c", code], env=sb.env, capture_output=True, text=True, timeout=60, check=False)

    locks = [r for r in sb.mutations() if r["event"] == "fcntl.flock"]
    assert locks, "no fcntl.flock event observed"
    attributed = [r for r in locks if r.get("attributed")]
    assert attributed, f"lock events were recorded but none attributed: {locks}"
    assert sb.mutations_touching(str(target)), f"lock was attributed but mutations_touching missed it: {attributed}"
    assert not sb.unattributed_mutations(), sb.unattributed_mutations()


def test_an_unresolved_descriptor_cannot_satisfy_a_no_write_assertion(tmp_path):
    """An observer that saw a lock but could not place it must be surfaced, not ignored."""
    sb = KeeperSandbox(tmp_path, "lock-unresolved", memoria=False)
    code = (
        "import fcntl, os\n"
        # Close the descriptor first, so /dev/fd resolution cannot succeed.
        "fd = os.open(os.devnull, os.O_RDWR)\n"
        "os.close(fd)\n"
        "try:\n"
        "    fcntl.flock(fd, fcntl.LOCK_EX)\n"
        "except OSError:\n"
        "    pass\n"
    )
    subprocess.run([sys.executable, "-c", code], env=sb.env, capture_output=True, text=True, timeout=60, check=False)

    # Whether or not a lock event fired, the assertion helper must never treat an
    # unattributed record as clean evidence.
    if sb.unattributed_mutations():
        with pytest.raises(AssertionError):
            sb.assert_no_protected_mutations()
    else:
        # Force the shape directly: an unattributed record must always raise.
        recs = sb.mutations()
        sb.write_log.write_text(
            "\n".join(
                [
                    *[str(r).replace("'", '"') for r in recs],
                    '{"kind": "mutation", "event": "fcntl.flock", "paths": [], "attributed": false}',
                ]
            )
            + "\n"
        )
        with pytest.raises(AssertionError):
            sb.assert_no_protected_mutations()
