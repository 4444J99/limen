"""Integration test for scripts/capture.sh divergence handling.

Regression guard for the capture↔sync deadly-embrace in its stale-tracking-ref guise:
a busy fleet advances a repo's remote between beats, so the local tracking ref (@{u}) goes
stale. capture.sh's behind-check — the sole guard that keeps an in-place commit off a diverged
branch — then reads behind=0 and commits onto a stale base, producing an un-pushable in-place
commit (non-ff rejection) that strands work and pins disk (reap-clones refuses to reap it).

The fix: capture.sh fetches the branch before the behind-check (only when dirty), so a truly
behind branch is detected and diverted to a pushable SIDE ref (HEAD left a clean ancestor of
origin) instead of stranding an in-place commit. This test reproduces the stale-ref condition
end-to-end and asserts the diversion.
"""

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CAPTURE_SH = REPO_ROOT / "scripts" / "capture.sh"

# Deterministic identity so `git commit` needs no ambient config.
GIT_ENV = {
    "GIT_AUTHOR_NAME": "cap-test",
    "GIT_AUTHOR_EMAIL": "cap@test.local",
    "GIT_COMMITTER_NAME": "cap-test",
    "GIT_COMMITTER_EMAIL": "cap@test.local",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}


def _git(*args, cwd, env=None):
    e = {**GIT_ENV, **(env or {})}
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env={**_base_env(), **e},
        capture_output=True,
        text=True,
        check=True,
    )


def _base_env():
    import os

    return dict(os.environ)


def _has_git():
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _has_git(), reason="git not available")
@pytest.mark.skipif(not CAPTURE_SH.exists(), reason="capture.sh missing")
def test_stale_tracking_ref_diverts_to_side_ref_not_stranded(tmp_path):
    home = tmp_path / "home"  # isolate HOME so capture.sh won't source real ~/.limen.env
    home.mkdir()
    remote = tmp_path / "remote.git"  # the canonical origin (bare)
    advancer = tmp_path / "advancer"  # a second clone that advances the remote
    ws = tmp_path / "ws"  # LIMEN_WORKSPACE — capture.sh scans this
    ws.mkdir()
    victim = ws / "victim"  # the clone whose tracking ref goes stale

    # bare remote seeded with one commit on `main`
    _git("init", "--bare", "--initial-branch=main", str(remote), cwd=tmp_path)
    _git("clone", str(remote), str(advancer), cwd=tmp_path)
    (advancer / "seed.txt").write_text("seed\n")
    _git("add", "-A", cwd=advancer)
    _git("commit", "-m", "seed", cwd=advancer)
    _git("push", "origin", "main", cwd=advancer)

    # victim clones the seeded state, THEN the remote advances behind its back
    _git("clone", str(remote), str(victim), cwd=tmp_path)
    victim_base = _git("rev-parse", "HEAD", cwd=victim).stdout.strip()

    (advancer / "advance.txt").write_text("remote moved\n")
    _git("add", "-A", cwd=advancer)
    _git("commit", "-m", "advance remote", cwd=advancer)
    _git("push", "origin", "main", cwd=advancer)

    # victim is now truly behind, but has NOT fetched — its @{u} is stale (reads behind=0).
    # Make it dirty so capture.sh will try to capture.
    (victim / "local-work.txt").write_text("uncaptured local work\n")

    env = {
        "HOME": str(home),
        "LIMEN_ROOT": str(tmp_path),
        "LIMEN_WORKSPACE": str(ws),
    }
    res = subprocess.run(
        ["bash", str(CAPTURE_SH)],
        env={**_base_env(), **GIT_ENV, **env},
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"capture.sh failed: {res.stderr}\n{res.stdout}"

    # 1) victim's local main must NOT have gained a diverging in-place commit — HEAD stays the
    #    clean ancestor it was cloned at (the fix diverted instead of committing in place).
    victim_head = _git("rev-parse", "HEAD", cwd=victim).stdout.strip()
    assert victim_head == victim_base, (
        "capture stranded an in-place commit on a diverged branch "
        f"(HEAD moved {victim_base[:8]} -> {victim_head[:8]}); the stale-@{{u}} guard regressed.\n{res.stdout}"
    )

    # 2) the uncaptured work must be preserved on the stable, coalescing side ref.
    ls = _git("ls-remote", str(remote), cwd=tmp_path).stdout
    assert "refs/heads/capture/main-deferred" in ls, (
        f"expected capture/main-deferred on origin; got:\n{ls}\ncapture output:\n{res.stdout}"
    )
    side_sha = _git("rev-parse", "refs/heads/capture/main-deferred", cwd=remote).stdout.strip()
    remote_main = _git("rev-parse", "refs/heads/main", cwd=remote).stdout.strip()
    _git("merge-base", "--is-ancestor", remote_main, side_sha, cwd=victim)


@pytest.mark.skipif(not _has_git(), reason="git not available")
@pytest.mark.skipif(not CAPTURE_SH.exists(), reason="capture.sh missing")
def test_oversized_file_is_never_committed_so_push_succeeds(tmp_path):
    """A file over GitHub's 100MB limit must be dropped from the capture commit — otherwise the
    push is hard-rejected and the commit is stranded un-pushable forever (the node_modules/*.node
    disk-floor bug). The small sibling change must still be captured and pushed."""
    home = tmp_path / "home"
    home.mkdir()
    remote = tmp_path / "remote.git"
    ws = tmp_path / "ws"
    ws.mkdir()
    victim = ws / "victim"

    _git("init", "--bare", "--initial-branch=main", str(remote), cwd=tmp_path)
    seed = tmp_path / "seed"
    _git("clone", str(remote), str(seed), cwd=tmp_path)
    (seed / "seed.txt").write_text("seed\n")
    _git("add", "-A", cwd=seed)
    _git("commit", "-m", "seed", cwd=seed)
    _git("push", "origin", "main", cwd=seed)

    # victim is up to date; main still routes through the stable side branch.
    _git("clone", str(remote), str(victim), cwd=tmp_path)
    (victim / "small.txt").write_text("real captured work\n")
    # 101MB of zeros — compresses to ~nothing on the wire, but exceeds the 100MB pre-receive limit.
    (victim / "big.bin").write_bytes(b"\0" * (101 * 1024 * 1024))

    env = {"HOME": str(home), "LIMEN_ROOT": str(tmp_path), "LIMEN_WORKSPACE": str(ws)}
    res = subprocess.run(
        ["bash", str(CAPTURE_SH)],
        env={**_base_env(), **GIT_ENV, **env},
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"capture.sh failed: {res.stderr}\n{res.stdout}"

    # Preservation must succeed off-main: side tree has the small file, never the oversized one.
    main_before = _git("rev-parse", "origin/main", cwd=victim).stdout.strip()
    tree = _git("ls-tree", "-r", "--name-only", "refs/heads/capture/main-deferred", cwd=remote).stdout
    assert "small.txt" in tree, f"real work was not pushed; tree=\n{tree}\n{res.stdout}"
    assert "big.bin" not in tree, (
        f"an oversized file was committed — push would be hard-rejected and stranded; tree=\n{tree}\n{res.stdout}"
    )
    assert _git("rev-parse", "refs/heads/main", cwd=remote).stdout.strip() == main_before
