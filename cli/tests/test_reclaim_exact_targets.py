"""Exact-target scope must never annex neighboring lifecycle roots."""

from __future__ import annotations

import hashlib
import json
import subprocess

import pytest
from test_reclaim_worktrees import load_reclaim_worktrees


def git(root, *args):
    return subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def scope(tmp_path):
    owner = tmp_path / "owner"
    owner.mkdir()
    git(owner, "init", "-q", "-b", "main")
    git(owner, "config", "user.name", "Fixture")
    git(owner, "config", "user.email", "fixture@example.invalid")
    target = tmp_path / "target"
    target.mkdir()
    git(target, "init", "-q", "-b", "main")
    git(target, "remote", "add", "origin", "https://github.com/fixture/subject.git")
    manifest = owner / "scope.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "limen.worktree_reclaim_scope.v1",
                "accepted": True,
                "authorization": "explicit operator request",
                "owner_url": "https://github.com/fixture/owner/pull/1",
                "targets": [
                    {
                        "root": target.name,
                        "repository": "fixture/subject",
                        "origin": "https://github.com/fixture/subject.git",
                        "path_sha256": hashlib.sha256(str(target).encode()).hexdigest(),
                    }
                ],
            }
        )
        + "\n"
    )
    git(owner, "add", "scope.json")
    git(owner, "commit", "-qm", "accepted scope")
    remote = tmp_path / "remote.git"
    git(owner, "clone", "--bare", str(owner), str(remote))
    git(owner, "remote", "add", "origin", str(remote))
    return owner, target, manifest


def test_only_explicit_target_is_selected(scope):
    _, target, manifest = scope
    reaper = load_reclaim_worktrees()
    targets, digest = reaper.exact_scope_targets([str(target)], manifest)
    assert [item.path for item in targets] == [target]
    assert targets[0].min_age_h == 0
    assert digest == hashlib.sha256(manifest.read_bytes()).hexdigest()


@pytest.mark.parametrize("shape", ["neighbor", "duplicate", "symlink", "origin", "uncommitted", "protected"])
def test_bad_target_blocks_entire_scope(scope, shape):
    _owner, target, manifest = scope
    reaper = load_reclaim_worktrees()
    paths = [str(target)]
    if shape == "neighbor":
        neighbor = target.parent / "unrelated"
        neighbor.mkdir()
        paths.append(str(neighbor))
    elif shape == "duplicate":
        paths.append(str(target))
    elif shape == "symlink":
        alias = target.parent / "alias"
        alias.symlink_to(target, target_is_directory=True)
        paths = [str(alias)]
    elif shape == "origin":
        git(target, "remote", "set-url", "origin", "https://github.com/fixture/other.git")
    elif shape == "uncommitted":
        manifest.write_text(manifest.read_text() + " ")
    else:
        reaper._SELF_GUARD.add(target)
    with pytest.raises(ValueError):
        reaper.exact_scope_targets(paths, manifest)


def test_unpublished_scope_fails(scope):
    owner, target, manifest = scope
    reaper = load_reclaim_worktrees()
    git(owner, "commit", "--allow-empty", "-qm", "unpublished")
    with pytest.raises(ValueError, match="published"):
        reaper.exact_scope_targets([str(target)], manifest)
