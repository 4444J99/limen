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
        monkeypatch.setattr(liveness, "_process_cwds", lambda: dict(cwds))
        monkeypatch.setattr(liveness, "_ancestor_pids", lambda: set(lineage))
        monkeypatch.setattr(liveness, "linked_worktree_roots", lambda root: set(linked))
        monkeypatch.setattr(liveness, "_is_session", lambda pid: sessions)
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
