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
