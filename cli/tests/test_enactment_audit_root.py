"""The enactment audit's liveness rung must read the wiring of the checkout the daemon RUNS from.

``heartbeat_pid()`` is ``pgrep -f heartbeat-loop.sh`` — host-GLOBAL, so it finds the one real daemon
no matter which checkout the audit is invoked from. The wiring mtime was read from ``LIVE_ROOT``,
which defaults to the checkout the script lives in — per-WORKTREE. Git stamps a linked worktree's
files at checkout time, which is essentially always AFTER the daemon started, so comparing a global
process against a worktree-local file fabricated a RED every time this ran from a worktree.

Measured 2026-08-07 from a session worktree: ``daemon pid 59319 started 11973s ago but its wiring
changed 984s more recently — running stale env``. The live checkout's copy was stamped 14:42:29, the
daemon started 15:20:25, and the two files were byte-identical — the daemon was carrying its wiring
correctly. The 984s was exactly the worktree's checkout time minus the daemon's start.

A false RED is not the harmless direction. ``.claude/skills/verify`` names this organ as how a
session decides whether a merged loop-body edit is actually live, and sessions work in worktrees by
charter — so the reading was wrong precisely where it is most used.

The existing ``scripts/tests/enactment-audit.test.sh`` cannot cover this: it runs ``--wiring-only``
on purpose, which skips the liveness rung so the code-contract test does not flap between CI and the
live host. These cases drive the rung directly with the host probes stubbed, so they are
deterministic with no daemon present.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "scripts" / "enactment-audit.py"

FLEET_VAR = "LIMEN_FAKE_FLEET_FLAG_FOR_TESTS"
# Deliberately a name nothing real assigns: ~/.limen.env is also a wiring file on the live host, and
# a real flag name would let the developer's own environment decide the verdict.
PARAMS = {"parameters": {FLEET_VAR: {"fleet_runtime": 1}}}

PID = 4242
DAEMON_START = 1_000_000.0
BEFORE = DAEMON_START - 600  # wiring predates the daemon → daemon is current
AFTER = DAEMON_START + 600  # wiring postdates the daemon → genuinely stale


def _load():
    """Import the hyphenated script as a module — the repo's convention for scripts/*.py siblings."""
    spec = importlib.util.spec_from_file_location("enactment_audit_under_test", AUDIT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def mod(monkeypatch: pytest.MonkeyPatch):
    """The module with its host probes stubbed: a daemon that exists, at a known start time."""
    m = _load()
    monkeypatch.setattr(m, "heartbeat_pid", lambda: PID)
    monkeypatch.setattr(m, "process_start_epoch", lambda pid: DAEMON_START)
    return m


def _wiring_file(root: Path, mtime: float) -> Path:
    path = root / "scripts" / "heartbeat-loop.sh"
    path.parent.mkdir(parents=True, exist_ok=True)
    # Must genuinely ASSIGN the flag — file_assigns_any() is what makes the rung ignore files the
    # beat churns without touching the flag (~/.limen.env is re-hydrated every beat).
    path.write_text(f"{FLEET_VAR}=1\n")
    os.utime(path, (mtime, mtime))
    return path


def _status(rows: list[dict]) -> str:
    assert len(rows) == 1, rows
    return rows[0]["status"]


# ----------------------------------------------------------------- the rung reads the resolved root
def test_a_freshly_checked_out_worktree_does_not_fabricate_a_stale_daemon(
    mod, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE regression, with the measured mtime ordering: live copy old, worktree copy new.

    LIVE_ROOT is pinned to the worktree alongside SCRIPT_ROOT because that is the real defect's
    shape — LIMEN_ROOT unset means LIVE_ROOT defaults to SCRIPT_ROOT, so both name the worktree.
    Pinning only SCRIPT_ROOT made this case pass against the BUGGY code for an unrelated reason:
    the pre-fix rung read the real repository's heartbeat-loop.sh, which does not assign this
    deliberately-fake flag name, so no file counted as wiring and the verdict was GREEN by
    accident. The test named the defect and could not see it. Caught by reverting the fix and
    watching this case pass anyway — which is the only thing that distinguishes a regression test
    from a comment.
    """
    primary = tmp_path / "primary"
    worktree = tmp_path / "worktree"
    _wiring_file(primary, BEFORE)  # what the daemon actually launched from
    _wiring_file(worktree, AFTER)  # stamped by `git worktree add`, long after the daemon started

    monkeypatch.setattr(mod, "SCRIPT_ROOT", worktree)
    monkeypatch.setattr(mod, "LIVE_ROOT", worktree)
    monkeypatch.setattr(mod, "live_checkout", lambda: primary)

    assert _status(mod.liveness_rung(PARAMS)) == mod.GREEN


def test_a_genuinely_stale_daemon_is_still_red(mod, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The negative control. Removing a false RED must not cost the true one.

    Without this, the fix is indistinguishable from deleting the check — and a false GREEN in a
    staleness auditor is strictly worse than the false RED it replaced.
    """
    primary = tmp_path / "primary"
    _wiring_file(primary, AFTER)

    monkeypatch.setattr(mod, "SCRIPT_ROOT", primary)
    monkeypatch.setattr(mod, "LIVE_ROOT", primary)
    monkeypatch.setattr(mod, "live_checkout", lambda: primary)

    rows = mod.liveness_rung(PARAMS)
    assert _status(rows) == mod.RED
    assert "running stale env" in rows[0]["detail"]


def test_an_unresolvable_root_skips_rather_than_reds(mod, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail toward SKIP. The defect being removed is a fabricated RED; no new path may create one."""
    monkeypatch.setattr(mod, "live_checkout", lambda: None)
    rows = mod.liveness_rung(PARAMS)
    assert _status(rows) == mod.SKIP
    assert "LIMEN_ROOT" in rows[0]["detail"], "the SKIP must say how to get a real answer from here"


# ------------------------------------------------------------------------ root resolution itself
def _git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        timeout=60,
    )


def test_live_checkout_resolves_a_real_linked_worktree_to_its_primary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercises the actual `git rev-parse --git-common-dir` derivation, not a mock of it.

    A linked worktree's `.git` is a FILE pointing at `<primary>/.git/worktrees/<name>`; the common
    dir resolves to `<primary>/.git`, whose parent is the checkout the daemon runs from.
    """
    primary = tmp_path / "primary"
    primary.mkdir()
    _git("init", "-q", "-b", "main", ".", cwd=primary)
    _wiring_file(primary, BEFORE)
    _git("add", "-A", cwd=primary)
    _git("commit", "-qm", "seed", cwd=primary)

    worktree = tmp_path / "wt"
    _git("worktree", "add", "-q", str(worktree), cwd=primary)

    m = _load()
    monkeypatch.setattr(m, "SCRIPT_ROOT", worktree)
    monkeypatch.setattr(m, "ROOT_IS_EXPLICIT", False)

    assert m.live_checkout() == primary.resolve()


def test_an_explicit_limen_root_is_never_silently_overridden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """_root.resolve() states the rule: explicit configuration wins, even from a worktree."""
    m = _load()
    monkeypatch.setattr(m, "ROOT_IS_EXPLICIT", True)
    monkeypatch.setattr(m, "LIVE_ROOT", tmp_path / "explicitly-chosen")
    assert m.live_checkout() == tmp_path / "explicitly-chosen"


def test_a_primary_without_the_loop_script_resolves_to_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The derivation is never trusted blindly — a relocated git dir has no checkout beside it."""
    primary = tmp_path / "primary"
    primary.mkdir()
    _git("init", "-q", "-b", "main", ".", cwd=primary)
    (primary / "seed.txt").write_text("x\n")
    _git("add", "-A", cwd=primary)
    _git("commit", "-qm", "seed", cwd=primary)

    worktree = tmp_path / "wt"
    _git("worktree", "add", "-q", str(worktree), cwd=primary)

    m = _load()
    monkeypatch.setattr(m, "SCRIPT_ROOT", worktree)
    monkeypatch.setattr(m, "ROOT_IS_EXPLICIT", False)

    assert m.live_checkout() is None


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
