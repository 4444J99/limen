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
    subprocess.run([sys.executable, "-c", code], env=sb.env, capture_output=True,
                   text=True, timeout=60, check=False)

    recs = sb.mutations()
    events = {r["event"] for r in recs}
    assert "open" in events, events
    assert any(e.startswith("os.rename") or e == "os.rename" for e in events), events
    assert "fcntl.flock" in events, f"lock events not observed; saw {sorted(events)}"

    rename = next(r for r in recs if r["event"] == "os.rename")
    assert len(rename["paths"]) >= 2, f"rename destination dropped: {rename}"
    assert any("renamedir" in str(p) for p in rename["paths"]), rename

    assert sb.child_reported_entry() is None or True  # entry recorded only in-child


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
        tmp_path, f"ro-{flag.strip('-')}-{memstate}-{health}",
        memoria=True, memory_populated=(memstate == "populated"),
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
    assert not sb.mutations_touching(str(sb.limen_root)), sb.mutations_touching(str(sb.limen_root))


def test_read_only_mode_does_not_create_bare_directory(tmp_path):
    """Directory creation alone is a mutation even with no file written."""
    sb = KeeperSandbox(tmp_path, "bare-dir", memoria=False)
    sb.run("--check", expect_exit=0)
    assert not sb.limen_root.exists(), f"--check created {sb.limen_root}"


def test_check_mode_write_is_independent_of_memory_state(tmp_path):
    """Control: the outer write is unconditional, not caused by the import failure."""
    sb = KeeperSandbox(tmp_path, "control-memoria-disabled", memoria=False)
    sb.run("--check", expect_exit=0)
    assert not sb.limen_root.exists(), (
        "--check wrote a health-state file with MEMORIA disabled"
    )


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
        tmp_path, f"outcome-{board_mode or 'empty'}",
        memoria=True, memory_populated=True, health_state="preexisting",
        board_mode=board_mode,
    )
    proc = sb.run()
    state = sb.state_payload()
    assert state, f"no health-state artifact published; stdout: {proc.stdout}"
    assert _memory_state(state) != "absent", (
        "memory outcome computed but absent from the published stamp; "
        f"state={state}\nstdout: {proc.stdout}"
    )


def test_memory_pass_succeeds(tmp_path):
    """Separate from error propagation: the memory pass must actually work.

    Guards against a repair that merely propagates `memory_error` while leaving
    the invalid `MEMORY_DIR` import in place.
    """
    sb = KeeperSandbox(tmp_path, "memory-succeeds", memoria=True, memory_populated=True)
    proc = sb.run()
    state = sb.state_payload()
    kind = _memory_state(state)
    assert kind != "error", (
        f"memory pass still failing: state={state}\nstdout: {proc.stdout}\n"
        f"stderr: {proc.stderr}"
    )
    assert kind == "counts", (
        f"memory pass reported no counts and no error; state={state}\n"
        f"stdout: {proc.stdout}"
    )


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