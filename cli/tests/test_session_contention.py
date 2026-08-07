"""Tests for the IF-SESSION-NON-CONTENTION organ — occupancy, the receipt, and the probe.

Three of `live_checkout_occupant`'s exclusions are load-bearing, and every one of them was found
by RUNNING the probe on the operator host rather than by reading code:

  nested worktrees   16 of this host's 31 linked worktrees sit under $LIMEN_ROOT, so the plain
                     containment rule reports the live checkout occupied in close to the modal
                     state — and the guard would freeze the sync organ permanently.
  gitignored ground  `reset --hard` only rewrites TRACKED content, so two codex plugin-cache
                     processes under .agent-runtime/ were never occupants.
  non-sessions       an MCP server and a static file server sat in tracked directories; the
                     ideal's subject is "an INTERACTIVE SESSION's cwd", not any process.

Miss any one and the guard fires constantly, the sync organ never converges, and closing this
ideal reopens IF-LIVE-TREE-COHERENCE. So each is tested as its own case, from both sides.
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "cli" / "src"))

from limen.conduct import liveness  # noqa: E402

CHECK = REPO / "scripts" / "check-session-contention.py"
ORGAN = REPO / "scripts" / "session-contention.py"

ROOT = Path("/repo")
NESTED = Path("/repo/.claude/worktrees/wt-a")


@pytest.fixture
def occupancy(monkeypatch):
    """Drive live_checkout_occupant from a synthetic process table."""

    def configure(cwds, *, linked=(NESTED,), lineage=(), sessions=True, ignored=()):
        # A cwd's value may be one pid or several. That the fixture ONCE took only a single int is
        # why the collision below shipped: the fixture mirrored the production dict[Path, int], so
        # no test could express two processes in one directory — the shape of the test data made
        # the failing state unrepresentable rather than merely untested.
        table = {path: ({v} if isinstance(v, int) else set(v)) for path, v in dict(cwds).items()}
        monkeypatch.setattr(liveness, "_process_cwds", lambda: {p: set(v) for p, v in table.items()})
        monkeypatch.setattr(liveness, "_ancestor_pids", lambda: set(lineage))
        monkeypatch.setattr(liveness, "linked_worktree_roots", lambda root: set(linked))

        # `sessions` is a blanket bool or the explicit set of pids that are sessions — needed once
        # a directory can hold both a service and a session.
        def is_session(pid):
            return sessions if isinstance(sessions, bool) else pid in set(sessions)

        monkeypatch.setattr(liveness, "_is_session", is_session)
        monkeypatch.setattr(liveness, "_is_ignored", lambda root, cwd: cwd in set(ignored))
        # NB: no patch of Path.resolve. The synthetic paths are already absolute and
        # `resolve(strict=False)` does not require existence, so the real method is correct here —
        # and patching a stdlib class method for the duration of a test is a cross-test hazard
        # that buys nothing.

    return configure


# ── occupancy: what counts, and what must not ─────────────────────────────────────


def test_a_session_in_the_live_checkout_is_an_occupant(occupancy):
    occupancy({ROOT: 4242})
    assert liveness.live_checkout_occupant(ROOT) == 4242


def test_a_session_in_a_nested_worktree_is_not_contending(occupancy):
    """Isolated BY DESIGN — this is the arrangement the charter asks for, not a violation."""
    occupancy({NESTED / "deep": 4242})
    assert liveness.live_checkout_occupant(ROOT) is None


def test_a_process_on_gitignored_ground_is_not_an_occupant(occupancy):
    """reset --hard leaves untracked runtime untouched, so it cannot disrupt this process."""
    runtime = ROOT / ".agent-runtime" / "cache"
    occupancy({runtime: 4242}, ignored=(runtime,))
    assert liveness.live_checkout_occupant(ROOT) is None


def test_a_service_is_not_an_interactive_session(occupancy):
    """An MCP server in mcp/ is a real process in tracked ground — and not the ideal's subject."""
    occupancy({ROOT / "mcp": 4242}, sessions=False)
    assert liveness.live_checkout_occupant(ROOT) is None


def test_the_callers_own_lineage_is_excluded(occupancy):
    """heartbeat-loop.sh cds to $LIMEN_ROOT at startup — without this the daemon sees itself."""
    occupancy({ROOT: 777}, lineage=(777,))
    assert liveness.live_checkout_occupant(ROOT) is None


def test_an_unavailable_probe_fails_OPEN(occupancy):
    """Inverts the sibling probe deliberately: failing closed here means never syncing again."""
    occupancy({Path("/"): -1})
    assert liveness.live_checkout_occupant(ROOT) is None


def test_an_unavailable_probe_is_distinguishable_from_a_free_tree(occupancy):
    """Fail-open is right; fail-open in the same words as success is not.

    Both of these answer `None` — that is the whole point of failing open — so a caller that only
    reads the pid cannot tell "nobody is here" from "I cannot see." Driving the organ with the
    package unimportable on 2026-08-06 produced the word `free` from a guard that was disarmed,
    and no surface anywhere said otherwise. The second value is what makes the difference sayable.
    """
    occupancy({Path("/"): -1})
    assert liveness.live_checkout_occupancy(ROOT) == (None, False)

    occupancy({Path("/elsewhere"): 4242})
    assert liveness.live_checkout_occupancy(ROOT) == (None, True)


def test_an_occupied_tree_reports_the_probe_as_available(occupancy):
    """The third arm: availability must not be a synonym for emptiness."""
    occupancy({ROOT: 4242})
    assert liveness.live_checkout_occupancy(ROOT) == (4242, True)


def test_a_process_outside_the_checkout_is_irrelevant(occupancy):
    occupancy({Path("/elsewhere"): 4242})
    assert liveness.live_checkout_occupant(ROOT) is None


# ── one directory, several processes ──────────────────────────────────────────────
#
# The guard shipped inert and every test above still passed. `sync-release.sh` does `cd "$ROOT"`
# before it probes, so the probe stands in the directory it is asking about; the process table
# kept ONE pid per directory, the probe's own pid won the slot, and the very next line excluded it
# as the caller's lineage. Free. Found by running sync-release.sh against a live occupant — it
# unparked HEAD and pushed — never by reading the code, and never by CI.
#
# Each case below is a filter that can reject the pid the dict happened to keep.


def test_the_caller_sharing_the_occupants_cwd_does_not_mask_it(occupancy):
    """THE regression. Caller and session in the same directory: the lineage filter must reject
    only the caller, not the whole directory."""
    occupancy({ROOT: (4242, 99441)}, lineage=(99441,))
    assert liveness.live_checkout_occupant(ROOT) == 4242


def test_a_service_sharing_the_cwd_does_not_mask_a_session(occupancy):
    """The session-ness filter is per-process too — stopping at one pid finds the MCP server
    sitting in the same directory and calls the checkout free.

    The service deliberately holds the HIGHER pid. lsof emits ascending, so under the old
    one-slot-per-directory table the last writer won and the service was the pid that survived to
    be tested. A service with the lower pid passes either way and proves nothing.
    """
    occupancy({ROOT: (4242, 99999)}, sessions=(4242,))
    assert liveness.live_checkout_occupant(ROOT) == 4242


def test_a_shared_cwd_does_not_mask_a_foreign_worktree_occupant(occupancy):
    """The sibling consumer filters by lineage as well, so it loses the same way — and its caller
    registers from INSIDE the worktree it probes, which is precisely the colliding case."""
    occupancy({NESTED: (4242, 99441)}, lineage=(99441,))
    assert liveness.foreign_worktree_occupant(NESTED) == 4242


def test_several_foreign_sessions_at_one_cwd_resolve_deterministically(occupancy):
    """Which one is reported is arbitrary; that it is STABLE is not — the receipt's onset dedup
    keys on (root, pid), so a pid that flapped per beat would manufacture an incident each beat."""
    occupancy({ROOT: (4243, 4242)})
    assert liveness.live_checkout_occupant(ROOT) == 4242
    assert liveness.live_checkout_occupant(ROOT) == 4242


def test_the_process_table_maps_a_directory_to_every_pid(occupancy):
    """The contract itself, asserted against the REAL enumerator: values are sets of pids. A
    revert to one-pid-per-directory reinstates the defect silently, and every filtering test above
    would keep passing on its own synthetic table."""
    observed = liveness._process_cwds()
    assert observed, "the probe observed no process at all — it cannot be exercised here"
    assert all(isinstance(pids, set) for pids in observed.values())
    assert all(isinstance(pid, int) for pids in observed.values() for pid in pids)


# ── the receipt ───────────────────────────────────────────────────────────────────


def _organ(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ORGAN), *args],
        capture_output=True,
        text=True,
        check=False,
        env={"LIMEN_ROOT": str(root), "PATH": "/usr/bin:/bin", "HOME": str(root)},
    )


def test_record_appends_one_incident(tmp_path):
    proc = _organ(tmp_path, "record", "--root", str(tmp_path), "--pid", "99", "--action", "skipped-reset-hard")
    assert proc.returncode == 0, proc.stdout + proc.stderr

    rows = [json.loads(x) for x in (tmp_path / "logs/session-contention.jsonl").read_text().splitlines() if x.strip()]
    assert len(rows) == 1
    assert rows[0]["pid"] == 99
    assert rows[0]["action"] == "skipped-reset-hard"
    assert rows[0]["shipped"] is False


def test_record_is_onset_deduped(tmp_path):
    """A session legitimately holding the tree for six hours is ONE incident, not one per beat.

    Without this the count measures session duration rather than contention, and the ideal's
    number stops meaning anything.
    """
    for _ in range(4):
        _organ(tmp_path, "record", "--root", str(tmp_path), "--pid", "99", "--action", "skipped-reset-hard")

    rows = [x for x in (tmp_path / "logs/session-contention.jsonl").read_text().splitlines() if x.strip()]
    assert len(rows) == 1, "the same session still holding the same tree is the same incident"


def test_record_distinguishes_a_new_session(tmp_path):
    _organ(tmp_path, "record", "--root", str(tmp_path), "--pid", "99", "--action", "skipped-reset-hard")
    _organ(tmp_path, "record", "--root", str(tmp_path), "--pid", "100", "--action", "skipped-stash-push")

    rows = [x for x in (tmp_path / "logs/session-contention.jsonl").read_text().splitlines() if x.strip()]
    assert len(rows) == 2, "a different occupant is a different incident"


def test_ship_dry_run_builds_the_ledger_without_committing(tmp_path):
    _organ(tmp_path, "record", "--root", str(tmp_path), "--pid", "99", "--action", "skipped-unpark")
    proc = _organ(tmp_path, "ship", "--dry-run")

    assert proc.returncode == 0, proc.stdout + proc.stderr
    ledger = json.loads(proc.stdout)
    assert ledger["incident_count"] == 1
    assert ledger["schema"] == "limen.session_contention_ledger.v1"
    assert not (tmp_path / "docs/receipts/session-contention-ledger.json").exists()


def test_ship_is_a_noop_with_nothing_recorded(tmp_path):
    proc = _organ(tmp_path, "ship", "--dry-run")
    assert proc.returncode == 0
    assert "nothing to ship" in proc.stdout


# ── the probe ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def probe(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("check_session_contention_under_test", CHECK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setattr(m, "ROOT", tmp_path)
    for spec_ in m.GUARDED_PATHS.values():
        path = tmp_path / spec_["file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"guarded via {spec_['marker']}\n", encoding="utf-8")
        arming = spec_.get("arming")
        if arming:
            witness = tmp_path / arming["file"]
            witness.parent.mkdir(parents=True, exist_ok=True)
            witness.write_text("".join(f"def {t}():\n    pass\n" for t in arming["tests"]), encoding="utf-8")
    return m


def test_probe_is_zero_when_every_path_is_guarded(probe):
    findings, unguarded = probe.check_exposure()
    assert findings == []
    assert unguarded == 0


def test_probe_flags_a_path_whose_guard_was_removed(probe, tmp_path):
    (tmp_path / "scripts/sync-release.sh").write_text("no guard here\n", encoding="utf-8")

    findings, unguarded = probe.check_exposure()
    assert unguarded == 1
    assert "occupancy guard was removed" in findings[0]


def test_probe_flags_a_guard_whose_arming_witness_is_gone(probe, tmp_path):
    """The marker can survive the disappearance of everything able to observe arming.

    That is not hypothetical: the marker was present at all three destructive sites while the
    guard was provably inert, and this predicate certified it. Deleting the witness must therefore
    cost distance, or the estate is back to grading text.
    """
    (tmp_path / "cli/tests/test_session_contention.py").unlink()

    findings, unguarded = probe.check_exposure()
    assert unguarded == 1
    assert "arming witness" in findings[0] and "missing" in findings[0]


def test_probe_flags_a_single_deleted_arming_test(probe, tmp_path):
    """Losing one case is the realistic shape — a rename, a delete during a refactor — and it is
    the one a file-exists check would wave through."""
    witness = tmp_path / "cli/tests/test_session_contention.py"
    witness.write_text("def test_the_unpark_still_fires_when_the_tree_is_free():\n    pass\n", encoding="utf-8")

    findings, unguarded = probe.check_exposure()
    assert unguarded == 1
    assert "test_the_guard_declines_the_unpark_when_a_session_holds_the_tree" in findings[0]


def test_probe_counts_unshipped_local_incidents(probe, tmp_path):
    """The review's sharpest point: a probe blind to unshipped incidents announces the ideal
    achieved at exactly the moment it is being violated."""
    log = tmp_path / "logs/session-contention.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(json.dumps({"pid": 1, "shipped": False}) + "\n", encoding="utf-8")

    findings, incidents = probe.check_incidents()
    assert incidents == 1
    assert "not yet shipped" in findings[0]


def test_probe_counts_committed_incidents(probe, tmp_path):
    ledger = tmp_path / "docs/receipts/session-contention-ledger.json"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(json.dumps({"incident_count": 3, "incidents": []}), encoding="utf-8")

    findings, incidents = probe.check_incidents()
    assert incidents == 3
    assert "3 committed" in findings[0]


def test_probe_treats_an_unreadable_ledger_as_distance(probe, tmp_path):
    ledger = tmp_path / "docs/receipts/session-contention-ledger.json"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text("{ not json", encoding="utf-8")

    findings, incidents = probe.check_incidents()
    assert incidents == 1
    assert "not valid JSON" in findings[0]


# ── the guard, end to end ─────────────────────────────────────────────────────────
#
# Everything above tests what the probe ANSWERS. Nothing tested whether sync-release.sh acts on
# the answer — and that seam is where both of this organ's real defects lived:
#
#   the probe never reported an occupant  a lossy process table (one pid per directory) let the
#                                         probe's own pid evict the session's
#   the script erased the one it got      `set -o pipefail` propagated the probe's exit 1 — its
#                                         OCCUPIED verdict, not an error — so the guard's
#                                         `|| OCCUPANT=""` fallback fired exactly when it had
#                                         found something
#
# Two independent faults, either one sufficient to render the guard inert, and every unit test
# above plus the check-session-contention gate stayed green through both. They were found by
# running the script against a live process. These cases are the cheap standing half of that
# drive: the REAL script, both verdicts, no process required.

SYNC_RELEASE = REPO / "scripts" / "sync-release.sh"


def _stub_probe(line: str, code: int) -> str:
    """session-contention.py's contract as sync-release.sh consumes it: `probe` prints one line
    and exits 0 free / 1 occupied; `record` is best-effort and says nothing."""
    return "import sys\nif 'probe' in sys.argv:\n" + f"    print({line!r})\n    sys.exit({code})\n" + "sys.exit(0)\n"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)


def _parked_checkout(tmp_path: Path, probe_line: str, probe_exit: int) -> tuple[subprocess.CompletedProcess, str]:
    """A checkout parked on a work branch + the REAL sync-release.sh, probe stubbed to a verdict.

    Parked-and-clean is the UNPARK valve's precondition, and unpark is the cheapest of the three
    destructive sites to drive: it fires before the at-release early exit, and its effect is a
    single observable fact — which branch HEAD ends up on.
    """
    origin, repo = tmp_path / "origin.git", tmp_path / "repo"
    subprocess.run(["git", "init", "--quiet", "--bare", str(origin)], check=True)

    (repo / "scripts").mkdir(parents=True)
    (repo / "logs").mkdir(parents=True)
    (repo / "tasks.yaml").write_text("placeholder\n", encoding="utf-8")
    (repo / "scripts" / "sync-release.sh").write_text(SYNC_RELEASE.read_text(encoding="utf-8"), encoding="utf-8")
    (repo / "scripts" / "session-contention.py").write_text(_stub_probe(probe_line, probe_exit), encoding="utf-8")

    _git(repo, "init", "--quiet", "-b", "main")
    _git(repo, "config", "user.email", "drive@local")
    _git(repo, "config", "user.name", "drive")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "harness base")
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "--quiet", "origin", "main")
    _git(repo, "checkout", "--quiet", "-b", "work/park")
    _git(repo, "push", "--quiet", "-u", "origin", "work/park")

    proc = subprocess.run(
        ["bash", str(repo / "scripts" / "sync-release.sh")],
        cwd=str(repo),  # load-bearing: the daemon invokes it from inside $ROOT, and the probe
        capture_output=True,  # process therefore shares the occupant's cwd — the colliding case
        text=True,
        check=False,
        env={**os.environ, "LIMEN_ROOT": str(repo), "HOME": str(tmp_path)},
    )
    return proc, _git(repo, "symbolic-ref", "--short", "HEAD").stdout.strip()


def test_the_guard_declines_the_unpark_when_a_session_holds_the_tree(tmp_path):
    """A probe that says OCCUPIED must stop the valve. It exits 1 to say so, and under pipefail
    that 1 is what used to blank the pid the guard had just parsed."""
    proc, head = _parked_checkout(tmp_path, "session-contention: /x OCCUPIED by pid 4242", 1)

    assert "declining skipped-unpark" in proc.stdout, proc.stdout + proc.stderr
    assert "pid 4242" in proc.stdout
    assert head == "work/park", "HEAD was switched out from under a live session"
    assert "UNPARKED" not in proc.stdout


def test_the_unpark_still_fires_when_the_tree_is_free(tmp_path):
    """The other half, and not a formality. A guard that fires unconditionally is the failure
    IF-LIVE-TREE-COHERENCE already records — the live checkout sat 120 commits behind for six
    days and nothing read the log. Declining to converge is as much a defect as converging over
    a live session, so both verdicts are pinned."""
    proc, head = _parked_checkout(tmp_path, "session-contention: /x free", 0)

    assert "UNPARKED" in proc.stdout, proc.stdout + proc.stderr
    assert head == "main"
    assert "declining" not in proc.stdout


def test_a_blind_probe_announces_itself_instead_of_passing_for_free(tmp_path):
    """A disarmed guard must SAY it is disarmed, and must still fail open.

    The script captures the probe's stdout into a variable and never echoes it, so a host where
    the probe cannot run — package unimportable, lsof missing — disarmed the guard and left no
    trace of it anywhere in the beat. Verified by driving the real organ with a broken PYTHONPATH
    on 2026-08-06: the probe printed `free`, sync-release unparked, and the log was indistinguishable
    from a healthy beat. Both halves are asserted here, because announcing the disarm while
    BLOCKING would be the opposite defect — this organ's contract is fail-open in capitals.
    """
    proc, head = _parked_checkout(
        tmp_path, "session-contention: /x probe UNAVAILABLE — guard disarmed, proceeding fail-open", 0
    )

    assert "DISARMED" in proc.stdout, proc.stdout + proc.stderr
    assert "UNPARKED" in proc.stdout, "fail-open is the contract — a blind probe must not block"
    assert head == "main"
    assert "declining" not in proc.stdout
