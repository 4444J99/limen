"""Exit a stream, run one command, it reopens. The states that make the round trip round.

THE DEFECT THESE TESTS PIN. `check-session-streams.py` classified "a directory exists at
`.worktrees/<sid>`" as `running`, and the launcher consumes only the ready set — so a stream
opened once could NEVER reopen: exit the agent, the worktree (correctly) remains, the stream
reads `running` forever, and the one-command reopen the registry promises worked exactly once
per stream before jamming shut. The operator asked three times how the exit → reopen round trip
works; the honest answer was that it didn't.

The fix splits presence by the SAME liveness probe that keeps reclaim-worktrees.py from deleting
live sessions (extracted to scripts/_worktree_liveness.py — one probe, two consumers with
opposite decisions):

  live     process attached (or probe unavailable, pid -1 fail-closed) — never double-opened
  dormant  valid worktree, nothing attached — OPENABLE, labelled REOPEN
  stale    not a valid git worktree — never offered (the starter hard-errors on it); reported,
           owned by the SPRAWL-RECLAIM organ

Fail-closed direction matters in BOTH consumers: a broken probe must under-act — reclaim declines
to delete, the launcher declines to reopen. Never the reverse.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts" / "check-session-streams.py"
RECLAIM = ROOT / "scripts" / "reclaim-worktrees.py"
LIVENESS = ROOT / "scripts" / "_worktree_liveness.py"
OPEN = ROOT / "scripts" / "open-streams.sh"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


L = _load(LIVENESS, "worktree_liveness_shared")


@pytest.fixture
def M():
    """A fresh checker module per test: presence is memoized module-wide, and a stale memo would
    let one test's worktree state leak into the next."""
    return _load(CHECK, "check_session_streams_reopen")


# ── the shared probe's containment + fail-closed contract ───────────────────────────


def test_owner_in_containment_and_sentinel(tmp_path):
    inside = tmp_path / "wt" / "deep"
    inside.mkdir(parents=True)
    assert L.owner_in({inside.resolve(): 42}, tmp_path / "wt") == 42  # cwd beneath ⇒ owned
    assert L.owner_in({}, tmp_path / "wt") is None  # nothing attached
    assert L.owner_in({Path("/"): -1}, tmp_path / "wt") == -1  # probe unavailable ⇒ everything owned


def test_reclaim_still_decides_through_the_shared_rule():
    """The extraction must be bit-for-bit: reclaim's active_process_owner IS owner_in over its
    own refresh-cycled scan. If reclaim regrew a private copy, the two consumers could disagree
    about the same worktree — delete what the launcher thinks is live, or reopen what reclaim
    thinks is."""
    src = RECLAIM.read_text()
    assert "from _worktree_liveness import active_process_cwds, owner_in" in src
    assert src.count("def active_process_cwds") == 0, "reclaim regrew a private copy of the probe"


# ── presence classification ──────────────────────────────────────────────────────────


def _stream_worktree(tmp_path, sid, *, git=True):
    wt = tmp_path / sid
    wt.mkdir()
    if git:
        subprocess.run(["git", "init", "-q", str(wt)], check=True)
    return wt


def test_an_exited_stream_is_dormant_not_running(M, tmp_path, monkeypatch):
    """THE REGRESSION: a worktree with no attached process must be reopenable."""
    _stream_worktree(tmp_path, "styx")
    monkeypatch.setattr(M, "WORKTREES", str(tmp_path))
    monkeypatch.setattr(M._worktree_liveness, "process_owner", lambda d, **kw: None)
    assert M._lane_presence("styx") == ("dormant", None)
    assert M.state_of("styx", {"requires": []}, {"styx": False}) == "dormant"


def test_an_attached_stream_is_live_with_its_pid(M, tmp_path, monkeypatch):
    _stream_worktree(tmp_path, "styx")
    monkeypatch.setattr(M, "WORKTREES", str(tmp_path))
    monkeypatch.setattr(M._worktree_liveness, "process_owner", lambda d, **kw: 4242)
    assert M._lane_presence("styx") == ("live", 4242)


def test_probe_unavailable_reads_live_never_dormant(M, tmp_path, monkeypatch):
    """Fail-closed: pid -1 means 'could not look', and a launcher that cannot look must not
    reopen — double-opening a live session is the harm this whole classification prevents."""
    _stream_worktree(tmp_path, "styx")
    monkeypatch.setattr(M, "WORKTREES", str(tmp_path))
    monkeypatch.setattr(M._worktree_liveness, "process_owner", lambda d, **kw: -1)
    state, pid = M._lane_presence("styx")
    assert state == "live"
    assert pid == -1


def test_a_non_worktree_directory_is_stale_and_probed_no_further(M, tmp_path, monkeypatch):
    """start-worktree-session.sh hard-errors on a path that exists but is not a git worktree —
    offering it as reopenable would open a tmux window containing an error."""
    _stream_worktree(tmp_path, "styx", git=False)
    monkeypatch.setattr(M, "WORKTREES", str(tmp_path))
    monkeypatch.setattr(
        M._worktree_liveness,
        "process_owner",
        lambda d, **kw: pytest.fail("a stale dir must not reach the liveness probe"),
    )
    assert M._lane_presence("styx") == ("stale", None)


def test_no_worktree_means_no_probe_at_all(M, tmp_path, monkeypatch):
    """The CI gate runs the checks, never state_of — but even the views must not pay for an lsof
    scan when nothing is on disk to classify."""
    monkeypatch.setattr(M, "WORKTREES", str(tmp_path / "nowhere"))
    monkeypatch.setattr(
        M._worktree_liveness,
        "process_owner",
        lambda d, **kw: pytest.fail("no worktree on disk, yet the probe ran"),
    )
    assert M._lane_presence("styx") == (None, None)
    assert M.state_of("styx", {"requires": []}, {"styx": False}) == "ready"


def test_settled_still_outranks_presence(M, tmp_path, monkeypatch):
    """A settled domain with a leftover worktree is settled, not reopenable — the worktree is
    residue for the reclaim organ, not an invitation."""
    _stream_worktree(tmp_path, "s1-homing-spine")
    monkeypatch.setattr(M, "WORKTREES", str(tmp_path))
    assert M.state_of("s1-homing-spine", {"requires": []}, {"s1-homing-spine": True}) == "settled"


# ── the openable set: what the launcher is allowed to act on ─────────────────────────


def test_openable_is_ready_plus_dormant_never_live_or_stale(M):
    row = lambda fam: {"family": fam}  # noqa: E731
    buckets = {
        "ready": [("virgin-lane", row("constellation"))],
        "dormant": [("exited-lane", row("constellation"))],
        "live": [("attached-lane", row("constellation"))],
        "stale": [("broken-lane", row("constellation"))],
        "blocked": [],
        "settled": [],
    }
    ids = [sid for sid, _ in M._openable(buckets)]
    assert "exited-lane" in ids, "dormant is the reopen case — excluding it is the old jam"
    assert "virgin-lane" in ids
    assert "attached-lane" not in ids, "a live session must never be double-opened"
    assert "broken-lane" not in ids


def test_json_rows_say_which_opens_are_reopens(M, tmp_path, monkeypatch, capsys):
    _stream_worktree(tmp_path, "styx")
    monkeypatch.setattr(M, "WORKTREES", str(tmp_path))
    monkeypatch.setattr(M._worktree_liveness, "process_owner", lambda d, **kw: None)
    monkeypatch.setattr(M, "_settled", lambda sid, stream=None: False)
    streams = {
        "styx": {
            "family": "constellation",
            "register_tier": "T1",
            "title": "t",
            "job_class": "synthesis",
            "runway": "1d",
            "intent": "docs/continuations/styx/intent.md",
            "owner_of_record": "organs/consulting/constellation/registry.yaml",
            "max_children": 4,
            "requires": [],
            "branch_prefix": "feat",
        },
        "spiral": {
            "family": "constellation",
            "register_tier": "T1",
            "title": "t",
            "job_class": "synthesis",
            "runway": "8h",
            "intent": "docs/continuations/spiral/intent.md",
            "owner_of_record": "organs/consulting/constellation/registry.yaml",
            "max_children": 2,
            "requires": [],
            "branch_prefix": "feat",
        },
    }
    M.print_ready_json(streams)
    rows = {r["id"]: r for r in json.loads(capsys.readouterr().out)}
    assert rows["styx"]["reopen"] is True
    assert rows["spiral"]["reopen"] is False


# ── the operator-facing surfaces exist and agree ─────────────────────────────────────


def test_status_names_every_stream_exactly_once():
    proc = subprocess.run(
        [sys.executable, str(CHECK), "--status"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    import yaml

    streams = yaml.safe_load((ROOT / "institutio/governance/session-streams.yaml").read_text())["streams"]
    for sid in streams:
        assert proc.stdout.count(f"  {sid} ") == 1, f"{sid} missing or duplicated in --status"
    assert "openable" in proc.stdout


def test_the_launcher_delegates_status_to_the_registry():
    """One derivation, one home: the launcher must not grow its own state story."""
    src = OPEN.read_text()
    assert "--status" in src
    assert 'check-session-streams.py" --status' in src
