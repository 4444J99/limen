from __future__ import annotations

from pathlib import Path

from limen.conduct import liveness
from limen.conduct.liveness import foreign_worktree_occupant


def test_own_lineage_is_not_a_foreign_occupant(monkeypatch, tmp_path) -> None:
    # The claimant registers from INSIDE the worktree it claims: its own boot chain must not
    # read as an occupant, or succession would always be refused.
    monkeypatch.setattr(liveness, "_ancestor_pids", lambda: {100, 200})
    monkeypatch.setattr(liveness, "_process_cwds", lambda: {tmp_path: {100}, tmp_path / "sub": {200}})
    assert foreign_worktree_occupant(tmp_path) is None


def test_foreign_process_in_worktree_blocks_succession(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(liveness, "_ancestor_pids", lambda: {100})
    monkeypatch.setattr(liveness, "_process_cwds", lambda: {tmp_path / "deep": {999}})
    assert foreign_worktree_occupant(tmp_path) == 999


def test_the_caller_sharing_a_cwd_does_not_mask_the_occupant(monkeypatch, tmp_path) -> None:
    # A DIRECTORY HOLDS EVERY PID, NOT ONE. The two preceding cases put the caller and the
    # occupant in separate directories, which is the arrangement that cannot fail: the whole
    # difficulty is that this probe's caller runs inside the worktree it is asking about, so it
    # routinely shares a cwd with what it is looking for. While _process_cwds kept one pid per
    # directory the caller's own pid evicted the occupant's, the lineage filter then discarded
    # the survivor, and the probe answered "unoccupied" — succession granted over a live session.
    monkeypatch.setattr(liveness, "_ancestor_pids", lambda: {100})
    monkeypatch.setattr(liveness, "_process_cwds", lambda: {tmp_path: {100, 999}})
    assert foreign_worktree_occupant(tmp_path) == 999


def test_process_outside_worktree_is_ignored(monkeypatch, tmp_path) -> None:
    elsewhere = tmp_path.parent
    monkeypatch.setattr(liveness, "_ancestor_pids", lambda: {100})
    monkeypatch.setattr(liveness, "_process_cwds", lambda: {elsewhere: {999}})
    assert foreign_worktree_occupant(tmp_path) is None


def test_unavailable_probe_fails_closed(monkeypatch, tmp_path) -> None:
    # pid -1 is the probe's own unavailability sentinel: it must surface as "occupied" so a
    # broken probe can only refuse succession, never steal a live session's worktree.
    monkeypatch.setattr(liveness, "_ancestor_pids", lambda: {100})
    monkeypatch.setattr(liveness, "_process_cwds", lambda: {Path("/"): {-1}})
    assert foreign_worktree_occupant(tmp_path) == -1


def test_real_probe_sees_this_test_process_as_own_lineage(tmp_path) -> None:
    # Unmocked end-to-end shape check: the current process's cwd is NOT under tmp_path, and
    # nothing foreign lives there, so a fresh temporary directory reads unoccupied — unless the
    # host probe itself is unavailable, in which case fail-closed (-1) is the correct answer.
    assert foreign_worktree_occupant(tmp_path) in (None, -1)


def test_probe_from_inside_the_worktree_does_not_see_its_own_scanner(tmp_path) -> None:
    # The 2026-07-30 reopen incident, pinned end-to-end: the claimant registers from INSIDE the
    # worktree it claims, and the probe's lsof child inherits that cwd — so on macOS the scanner
    # listed ITSELF as a live foreign occupant and succession was refused deterministically.
    # A real subprocess (not a mock) with cwd inside the worktree must read it as unoccupied.
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from pathlib import Path\n"
            "from limen.conduct.liveness import foreign_worktree_occupant\n"
            "print(foreign_worktree_occupant(Path('.')))",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    assert result.stdout.strip() in {"None", "-1"}


# ── non-interactive runtime subcommands (#1987) ───────────────────────────────
#
# `claude bg-spare`, `claude bg-pty-host` and `claude agents` are byte-identical to a real session
# in argv[0], so argv[0]-only matching counted daemon-spawned spares, their pty hosts and the
# FleetView viewer as sessions occupying the live checkout — and sync-release declined the
# fast-forward on eight consecutive beats while the tree stood 37 commits behind. The exclusion has
# to stay NARROW: it is the only thing between "the guard ignores a service" and "the guard ignores
# a session", and widening it silently is unobservable from the guard's own output.


def _fake_ps(invocations: dict[int, str], *, command_fails: bool = False):
    """Stand in for `ps`, answering `comm=` and `command=` from one invocation string."""

    class Result:
        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    def fake_run(argv, **_kwargs):
        invocation = invocations.get(int(argv[-1]), "")
        if "command=" in argv:
            if command_fails:
                raise OSError("ps unavailable")
            return Result(invocation)
        return Result(invocation.split()[0] if invocation else "")

    return fake_run


def test_non_interactive_subcommands_are_not_sessions(monkeypatch) -> None:
    invocations = {
        1: "/Users/x/.local/bin/claude bg-spare",
        2: "/Users/x/.local/bin/claude bg-pty-host",
        3: "/Users/x/.local/bin/claude agents",
    }
    monkeypatch.setattr(liveness.subprocess, "run", _fake_ps(invocations))
    for pid, invocation in invocations.items():
        assert liveness._is_session(pid) is False, invocation


def test_a_genuine_session_is_still_a_session(monkeypatch) -> None:
    invocations = {
        10: "/Users/x/.local/bin/claude",
        11: "/Users/x/.local/bin/claude resume",
        12: "/Users/x/.local/bin/claude --resume abc",
    }
    monkeypatch.setattr(liveness.subprocess, "run", _fake_ps(invocations))
    for pid, invocation in invocations.items():
        assert liveness._is_session(pid) is True, invocation


def test_a_leading_flag_keeps_the_conservative_default(monkeypatch) -> None:
    # An unparseable invocation must accuse, not excuse: `-u` is not a bare subcommand, so the
    # runtime match stands and the pid still reads as a session.
    monkeypatch.setattr(liveness.subprocess, "run", _fake_ps({20: "/x/claude -u resume"}))
    assert liveness._is_session(20) is True


def test_a_near_miss_subcommand_is_not_swallowed(monkeypatch) -> None:
    # Exact match only. A future real subcommand that merely STARTS WITH an excluded name
    # (`bg-spare-inspect`) must not inherit the exemption.
    monkeypatch.setattr(liveness.subprocess, "run", _fake_ps({30: "/x/claude bg-spare-inspect"}))
    assert liveness._is_session(30) is True


def test_unreadable_argv_accuses_no_one_of_being_a_service(monkeypatch) -> None:
    # If the argv read fails, the runtime check must stand — silently reclassifying a session as a
    # service would disarm the guard with no signal anywhere.
    monkeypatch.setattr(
        liveness.subprocess,
        "run",
        _fake_ps({40: "/x/claude resume"}, command_fails=True),
    )
    assert liveness._is_session(40) is True


def test_a_non_runtime_program_is_never_a_session(monkeypatch) -> None:
    monkeypatch.setattr(liveness.subprocess, "run", _fake_ps({50: "/bin/cat bg-spare", 51: "/x/node agents"}))
    assert liveness._is_session(50) is False
    assert liveness._is_session(51) is False
