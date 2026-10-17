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
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tabularius_organ_fixtures import (
    CHILD_INTERPRETER,
    ENTRY_POINT,
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

    sb.run_raw([sys.executable, "-c", code])

    recs = sb.mutations()
    events = {r["event"] for r in recs}
    assert "open" in events, events
    assert any(e.startswith("os.rename") or e == "os.rename" for e in events), events
    assert "fcntl.flock" in events, f"lock events not observed; saw {sorted(events)}"
    # Every record is attributable to the child that emitted it.
    assert {r.get("pid") for r in recs} == {sb.child_pid}, recs

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


def test_a_deferred_memory_pass_is_published_as_deferred_not_as_success(tmp_path):
    """A held-lock deferral must never read as a completed pass.

    `drain_memory_once` defers while the memory lock is held and reports pending with
    nothing applied and nothing rejected. `_memory_pass` dropped `deferred` and `note`,
    so the stamp carried `memory_pending/0 applied/0 rejected` — indistinguishable
    from an empty inbox, and rendered "pass OK" on the only channel `--dry-run` has.
    """
    sb = KeeperSandbox(tmp_path, "memory-deferred", memoria=True, memory_populated=True)
    proc = _run_with_deferred_memory_lock(sb)
    state = sb.state_payload()

    assert state, f"no health-state artifact published; stdout: {proc.stdout}"
    assert _memory_state(state) != "error", f"unexpected memory error: {state}\nstdout: {proc.stdout}"
    # The deferral itself is preserved, as a readable string.
    assert state.get("memory_deferred"), f"deferral dropped from the stamp: {state}\nstdout: {proc.stdout}"
    assert "memory lock" in str(state["memory_deferred"]), state
    # ...and the outcome is not claimed as a pass.
    assert "DEFERRED" in proc.stdout, f"deferred pass reported as success on stdout: {proc.stdout!r}"
    assert "pass OK" not in proc.stdout, f"deferral rendered as 'pass OK': {proc.stdout!r}"
    # Nothing was consumed: a deferral applies nothing.
    ticket = sb.memory_dir / ".covenant-inbox" / "synthetic.json"
    assert ticket.exists(), "a deferred drain consumed a pending ticket"


def _run_with_deferred_memory_lock(sb) -> subprocess.CompletedProcess:
    """Run normally with the memory lock already held, forcing a real deferral.

    A second process holds `flock` on the memory lock file for the duration of the
    keeper run, so the real `drain_memory_once` takes its documented deferral path.
    No stubbing: the deferral must come from the production code under test.
    """
    memdir = sb.memory_dir
    memdir.mkdir(parents=True, exist_ok=True)
    # The exact lock path memoria.py's `_lockfile` derives; a different name would
    # leave the lock uncontended and the test would silently assert nothing.
    lock = memdir / ".covenant.lock"
    holder = subprocess.Popen(
        [
            "python3",
            "-c",
            "import fcntl,sys,time\nfd=open(sys.argv[1],'a')\nfcntl.flock(fd, fcntl.LOCK_EX)\ntime.sleep(60)\n",
            str(lock),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        # Give the holder time to take the lock before the keeper runs.
        deadline = time.monotonic() + 20
        import fcntl as _fcntl

        while time.monotonic() < deadline:
            probe = open(lock, "a")
            try:
                _fcntl.flock(probe.fileno(), _fcntl.LOCK_EX | _fcntl.LOCK_NB)
                _fcntl.flock(probe.fileno(), _fcntl.LOCK_UN)
            except OSError:
                break  # holder has it
            finally:
                probe.close()
            time.sleep(0.1)
        return sb.run()
    finally:
        holder.terminate()
        holder.wait(timeout=30)


def test_dry_run_counts_are_labelled_would_be_not_completed(tmp_path):
    """`--dry-run` writes nothing, so its counts are would-be, not completions.

    `drain_memory_once(dry_run=True)` reports how many tickets are *applicable* and
    how many are *unparseable*. `_describe` rendered them "applied"/"rejected",
    reporting work that never happened on the only channel `--dry-run` publishes.
    """
    sb = KeeperSandbox(tmp_path, "dry-run-would-be", memoria=True, memory_populated=True)
    proc = sb.run("--dry-run", expect_exit=0)
    out = proc.stdout

    assert "WOULD APPLY" in out, f"dry-run counts not labelled would-be: {out!r}"
    assert "would apply" in out, f"dry-run applied count not labelled would-be: {out!r}"
    # The bare completed-tense form must be absent for the same numbers.
    assert " applied " not in out, f"dry-run reported an applied count as completed: {out!r}"
    # ...and nothing was actually written.
    assert not sb.state_path.exists(), "--dry-run wrote a health-state stamp"
    ticket = sb.memory_dir / ".covenant-inbox" / "synthetic.json"
    assert ticket.exists(), "--dry-run consumed a pending memory ticket"
    assert not (sb.memory_dir / f"{VALID_TICKET['slug']}.md").exists(), "--dry-run wrote a memory atom"


def test_check_dry_run_count_is_not_relabelled_would_be(tmp_path):
    """The control for the would-be label: a real count stays a real count.

    `--check` counts pending tickets; it does not simulate a drain, so labelling its
    output "WOULD APPLY" would misreport a measurement. The dry-run fact therefore
    travels in the memory outcome rather than being re-derived from the caller's flag.
    """
    sb = KeeperSandbox(tmp_path, "check-dry-run", memoria=True, memory_populated=True)
    proc = sb.run("--check", "--dry-run", expect_exit=0)
    out = proc.stdout

    assert "WOULD APPLY" not in out, f"--check count relabelled would-be: {out!r}"
    assert "1 pending" in out, f"--check did not report the pending count: {out!r}"


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
    # The key must be PRESENT before its value is asserted zero. `dict.get(k, 0) == 0`
    # is satisfied by a missing key, so a second run that recorded no memory outcome at
    # all — the pass errored, or the field was dropped — read as a clean no-op.
    assert "memory_applied" in state2, (
        f"re-run recorded no memory_applied; a missing field is not a zero: {state2}\nstdout: {proc2.stdout}"
    )
    assert state2.get("memory_applied", 0) == 0, f"re-run re-applied the same ticket: {state2}\nstdout: {proc2.stdout}"
    assert atom.read_bytes() == first, "atom content changed on a no-op re-run"


def test_observer_readers_are_scoped_to_the_current_child(tmp_path):
    """Evidence from one run must never satisfy an assertion about another.

    `writes.jsonl` is append-only and shared by every child the sandbox runs. The
    readers used to take the FIRST matching record, so after a second run they
    reported the first run's mutations — and its markers — as the second run's. A run
    that observed nothing therefore inherited the previous run's proof that
    something was observed.
    """
    sb = KeeperSandbox(tmp_path, "run-scoping", memoria=True, memory_populated=True)

    sb.run()
    first_muts = sb.mutations()
    first_entry = sb.child_reported_entry()
    assert first_muts, "first run observed nothing; the fixture cannot prove scoping"
    assert first_entry, "first run reported no entry point; scoping would be untestable"

    # Second run: different pid, same append-only log.
    sb.run()
    second_muts = sb.mutations()
    second_entry = sb.child_reported_entry()

    assert second_entry is not None, "second run reported no entry point"
    assert {r.get("pid") for r in second_muts} <= {sb.child_pid}, (
        f"second run's reader surfaced another child's records: {second_muts}"
    )
    # The log really did accumulate: scoping must narrow, not silently truncate.
    all_pids = {r.get("pid") for r in sb.write_attempts() if r.get("kind") == "mutation"}
    assert len(all_pids) >= 2, f"expected two runs' records in the log; saw pids={all_pids}"
    assert not ({r.get("pid") for r in second_muts} & {r.get("pid") for r in first_muts}), (
        "the two runs' mutation sets overlap after scoping"
    )


def test_a_later_run_cannot_inherit_an_earlier_runs_observer_markers(tmp_path):
    """The marker check must be run-scoped, or 'evidence available' always passes.

    `write_attempts(require=True)` required that both markers appear in the log. Once
    any earlier run had written them, a later run whose observer never installed or
    never flushed still satisfied the requirement — turning "no usable evidence" into
    a silent pass.
    """
    sb = KeeperSandbox(tmp_path, "marker-scoping", memoria=True, memory_populated=True)

    sb.run()
    assert sb.write_attempts(require=True), "first run produced no evidence"

    # A child whose observer never installed contributes nothing of its own: point it
    # at a write log that is never created, leaving the shared log holding run 1 only.
    sb.run_raw(
        [CHILD_INTERPRETER, str(ENTRY_POINT), "--check"],
        env={**sb.env, "REPRO_WRITE_LOG": str(sb.root / "auditor" / "unwritten.jsonl")},
    )
    with pytest.raises(ObservationUnavailable):
        sb.write_attempts(require=True)


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
    sb.run_raw([sys.executable, "-c", code])

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
    sb.run_raw([sys.executable, "-c", code])

    # Whether or not a lock event fired, the assertion helper must never treat an
    # unattributed record as clean evidence.
    if sb.unattributed_mutations():
        with pytest.raises(AssertionError):
            sb.assert_no_protected_mutations()
    else:
        # Force the shape directly: an unattributed record must always raise. It
        # carries the current pid, so the run-scoped reader cannot filter it away
        # and quietly turn this negative control back into a pass.
        recs = sb.mutations()
        forced = {
            "kind": "mutation",
            "event": "fcntl.flock",
            "paths": [],
            "attributed": False,
            "pid": sb.child_pid,
        }
        sb.write_log.write_text("\n".join([*(json.dumps(r) for r in recs), json.dumps(forced)]) + "\n")
        with pytest.raises(AssertionError):
            sb.assert_no_protected_mutations()
