"""Use real Git objects to prove candidate working files are never executable input."""

from __future__ import annotations

import hashlib
import os
import subprocess

import pytest

from limen.conduct.assessor_source import ASSESSOR_PATH, MAX_SOURCE_BYTES, AssessorSourceError, capture_assessor


@pytest.fixture
def source_repo(tmp_path):
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_SYSTEM=os.devnull,
        GIT_AUTHOR_NAME="Fixture",
        GIT_COMMITTER_NAME="Fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
    )

    def git(*args):
        return (
            subprocess.check_output(["git", "-C", str(tmp_path), *args], env=env, stderr=subprocess.DEVNULL)
            .decode()
            .strip()
        )

    git("init")
    path = tmp_path / ASSESSOR_PATH
    path.parent.mkdir()
    source = b"print('fixture only; never executed')\n"
    path.write_bytes(source)
    git("add", ASSESSOR_PATH)
    git("commit", "-m", "fixture")
    return tmp_path, path, source, git


def test_captures_pinned_bytes_despite_working_tree_edits_and_ambient_git_dir(source_repo, monkeypatch):
    root, path, source, git = source_repo
    head = git("rev-parse", "HEAD")
    path.write_bytes(b"raise RuntimeError('untrusted working file')\n")
    monkeypatch.setenv("GIT_DIR", "/missing/ambient/repository")
    snapshot = capture_assessor(root, head, hashlib.sha256(source).hexdigest())
    assert snapshot.source == source
    assert snapshot.source_commit == head
    assert path.read_bytes().startswith(b"raise RuntimeError")


def test_wrong_digest_unknown_commit_and_noncommit_fail_closed(source_repo):
    root, _path, source, git = source_repo
    digest = hashlib.sha256(source).hexdigest()
    for head, expected in [
        (git("rev-parse", "HEAD"), "0" * 64),
        ("0" * 40, digest),
        (git("rev-parse", "HEAD:" + ASSESSOR_PATH), digest),
    ]:
        with pytest.raises(AssessorSourceError):
            capture_assessor(root, head, expected)


def test_symlink_blob_and_oversized_source_are_rejected(source_repo):
    root, path, source, git = source_repo
    path.unlink()
    path.symlink_to("/unread/private/source")
    git("add", ASSESSOR_PATH)
    git("commit", "-m", "symlink")
    with pytest.raises(AssessorSourceError, match="regular blob"):
        capture_assessor(root, git("rev-parse", "HEAD"), hashlib.sha256(source).hexdigest())
    path.unlink()
    path.write_bytes(b"x" * (MAX_SOURCE_BYTES + 1))
    git("add", ASSESSOR_PATH)
    git("commit", "-m", "oversize")
    with pytest.raises(AssessorSourceError, match="size bound"):
        capture_assessor(root, git("rev-parse", "HEAD"), "0" * 64)


def test_local_replace_ref_cannot_substitute_reviewed_commit(source_repo):
    root, path, source, git = source_repo
    reviewed = git("rev-parse", "HEAD")
    path.write_bytes(b"print('replacement must not run')\n")
    git("add", ASSESSOR_PATH)
    git("commit", "-m", "replacement")
    git("replace", reviewed, git("rev-parse", "HEAD"))
    captured = capture_assessor(root, reviewed, hashlib.sha256(source).hexdigest())
    assert captured.source == source


@pytest.mark.parametrize("commit,digest", [(None, "0" * 64), ("0" * 40, None), (True, [])])
def test_malformed_pins_fail_closed(tmp_path, commit, digest):
    with pytest.raises(AssessorSourceError, match="pin is invalid"):
        capture_assessor(tmp_path, commit, digest)
