"""capture.sh routes capture/* custody refs to a mapped PRIVATE sibling.

Repos listed in config/capture-private-siblings.tsv (or LIMEN_CAPTURE_SIBLING_MAP) keep
sensitive material in a "<repo>--private" sibling. Their capture/* side refs must land in the
sibling and never in the original. Unmapped repos keep pushing capture/* to origin.
"""

import subprocess
from pathlib import Path

import pytest
from test_capture_divergence import CAPTURE_SH, GIT_ENV, _base_env, _git, _has_git

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIPPED_MAP = REPO_ROOT / "config" / "capture-private-siblings.tsv"


def _seed_remote(tmp_path, remote):
    _git("init", "--bare", "--initial-branch=main", str(remote), cwd=tmp_path)
    seed = tmp_path / f"seed-{remote.parent.name}-{remote.name}"
    _git("clone", str(remote), str(seed), cwd=tmp_path)
    (seed / "seed.txt").write_text("seed\n")
    _git("add", "-A", cwd=seed)
    _git("commit", "-m", "seed", cwd=seed)
    _git("push", "origin", "main", cwd=seed)


def _run(tmp_path, ws, sibling_map, *args):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {
        "HOME": str(home),
        "LIMEN_ROOT": str(tmp_path),
        "LIMEN_WORKSPACE": str(ws),
        "LIMEN_CAPTURE_SIBLING_MAP": str(sibling_map),
    }
    return subprocess.run(
        ["bash", str(CAPTURE_SH), *args],
        check=False,
        env={**_base_env(), **GIT_ENV, **env},
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(not _has_git(), reason="git not available")
@pytest.mark.skipif(not CAPTURE_SH.exists(), reason="capture.sh missing")
def test_mapped_repo_captures_to_private_sibling_only(tmp_path):
    origin = tmp_path / "Owner" / "secret-repo.git"
    origin.parent.mkdir()
    sibling = tmp_path / "Owner" / "secret-repo--private.git"
    plain_origin = tmp_path / "Owner" / "plain-repo.git"
    _seed_remote(tmp_path, origin)
    _seed_remote(tmp_path, plain_origin)
    _git("init", "--bare", "--initial-branch=main", str(sibling), cwd=tmp_path)

    ws = tmp_path / "ws"
    ws.mkdir()
    mapped = ws / "secret-repo"
    plain = ws / "plain-repo"
    _git("clone", str(origin), str(mapped), cwd=tmp_path)
    _git("clone", str(plain_origin), str(plain), cwd=tmp_path)
    (mapped / "private-notes.md").write_text("sensitive work\n")
    (plain / "notes.md").write_text("ordinary work\n")

    sibling_map = tmp_path / "siblings.tsv"
    # Case-insensitive owner/repo match, comments and blank lines ignored.
    sibling_map.write_text(f"# comment\n\nowner/SECRET-REPO\t{sibling}\n")

    # Dry run names the sibling and pushes nothing.
    dry = _run(tmp_path, ws, sibling_map, "--dry-run")
    assert dry.returncode == 0, dry.stderr + dry.stdout
    assert f"private-sibling({sibling})/capture/main-deferred" in dry.stdout, dry.stdout
    assert "plain-repo: WOULD preserve main through origin/capture/main-deferred" in dry.stdout, dry.stdout
    assert "capture/" not in _git("ls-remote", str(sibling), cwd=tmp_path).stdout

    res = _run(tmp_path, ws, sibling_map)
    assert res.returncode == 0, res.stderr + res.stdout

    # Mapped repo: custody lands in the sibling, never in the original.
    sib_refs = _git("ls-remote", str(sibling), cwd=tmp_path).stdout
    orig_refs = _git("ls-remote", str(origin), cwd=tmp_path).stdout
    assert "refs/heads/capture/main-deferred" in sib_refs, res.stdout
    assert "capture/" not in orig_refs, f"capture ref leaked to the original:\n{orig_refs}"
    tree = _git("ls-tree", "-r", "--name-only", "refs/heads/capture/main-deferred", cwd=sibling).stdout
    assert "private-notes.md" in tree

    # Unmapped repo: unchanged behavior, custody on its own origin.
    assert "refs/heads/capture/main-deferred" in _git("ls-remote", str(plain_origin), cwd=tmp_path).stdout


def test_shipped_map_lists_the_private_siblings():
    rows = [
        line.split()
        for line in SHIPPED_MAP.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    mapping = {r[0].lower(): r[1] for r in rows}
    for repo in ("portfolio", "vox--architectura-gubernatio", "narratological-algorithmic-lenses"):
        assert mapping[f"4444j99/{repo}"] == f"https://github.com/4444J99/{repo}--private.git"
