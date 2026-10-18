"""GitHub publication readback must not start a persistent SSH transport."""

import json
import subprocess
from pathlib import Path

import pytest
from limen import session_closeout as closeout

HEAD = "a" * 40
TIP = "b" * 40
BRANCH = "fix/closeout"
REF = "refs/heads/" + BRANCH


@pytest.mark.parametrize(
    "remote",
    [
        "git@github.com:owner/private.git",
        "ssh://git@github.com/owner/private.git",
        "https://github.com/owner/private.git",
    ],
)
def test_exact_github_ref_is_ephemeral_and_idempotent(monkeypatch, remote):
    calls = []

    def git(root, *args, **kwargs):
        assert args == ("remote", "get-url", "origin"), "GitHub publication must never invoke ls-remote"
        return remote

    def run(command, **kwargs):
        calls.append(command)
        return json.dumps({"ref": REF, "object": {"type": "commit", "sha": HEAD}})

    monkeypatch.setattr(closeout, "git", git)
    monkeypatch.setattr(closeout, "run", run)
    assert closeout.published(Path("/explicit/root"), HEAD, BRANCH)
    assert closeout.published(Path("/explicit/root"), HEAD, BRANCH)
    assert calls == [["gh", "api", "--method", "GET", "repos/owner/private/git/ref/heads/fix%2Fcloseout"]] * 2


@pytest.mark.parametrize(
    "value,unmeasured",
    [
        ([], True),
        ({"ref": REF}, True),
        ({"ref": REF, "object": {"type": "tag", "sha": HEAD}}, True),
        ({"ref": "refs/heads/other", "object": {"type": "commit", "sha": HEAD}}, False),
        ({"ref": REF, "object": {"type": "commit", "sha": "bad"}}, False),
        ({"ref": REF, "object": {"type": "commit", "sha": None}}, False),
    ],
)
def test_github_ref_conflicts_never_release(monkeypatch, value, unmeasured):
    monkeypatch.setattr(closeout, "git", lambda *args, **kwargs: "git@github.com:owner/private.git")
    monkeypatch.setattr(closeout, "run", lambda *args, **kwargs: json.dumps(value))
    if unmeasured:
        with pytest.raises(closeout.Unmeasured):
            closeout.published(Path("/explicit/root"), HEAD, BRANCH)
    else:
        assert not closeout.published(Path("/explicit/root"), HEAD, BRANCH)


@pytest.mark.parametrize("ancestor", [True, False])
def test_moving_github_ref_requires_exact_local_ancestry(monkeypatch, ancestor):
    def git(root, *args, **kwargs):
        if args == ("remote", "get-url", "origin"):
            return "git@github.com:owner/private.git"
        assert args == ("merge-base", "--is-ancestor", HEAD, TIP)
        if not ancestor:
            raise subprocess.CalledProcessError(1, ["git", *args])
        return ""

    monkeypatch.setattr(closeout, "git", git)
    monkeypatch.setattr(
        closeout, "run", lambda *args, **kwargs: json.dumps({"ref": REF, "object": {"type": "commit", "sha": TIP}})
    )
    assert closeout.published(Path("/explicit/root"), HEAD, BRANCH) is ancestor


def test_github_authentication_failure_never_falls_back_to_ssh(monkeypatch):
    monkeypatch.setattr(closeout, "git", lambda *args, **kwargs: "git@github.com:owner/private.git")

    def unavailable(command, **kwargs):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(closeout, "run", unavailable)
    with pytest.raises(subprocess.CalledProcessError):
        closeout.published(Path("/explicit/root"), HEAD, BRANCH)


def _not_found(command):
    return subprocess.CalledProcessError(1, command, stderr=b"gh: Not Found (HTTP 404)")


def _squash_run(*, pulls=None, pull_ref=None):
    """gh stub for a squash-merged subject whose head branch was auto-deleted."""

    def run(command, **kwargs):
        endpoint = command[4]
        if endpoint.endswith("/git/ref/heads/" + BRANCH.replace("/", "%2F")):
            raise _not_found(command)
        if endpoint == "repos/owner/private/pulls":
            assert "head=owner:" + BRANCH in command
            return json.dumps(pulls)
        if "/git/ref/pull/" in endpoint:
            if pull_ref is None:
                raise _not_found(command)
            return json.dumps(pull_ref)
        raise AssertionError(command)

    return run


def _merged_pr(number=7, repo="owner/private", merged="2026-10-18T05:08:58Z"):
    return {"number": number, "merged_at": merged, "head": {"repo": {"full_name": repo}}}


def _pull_ref(number=7, sha=HEAD, ref=None):
    return {"ref": ref or f"refs/pull/{number}/head", "object": {"type": "commit", "sha": sha}}


def test_squash_merged_branch_is_published_through_the_pull_ref(monkeypatch):
    monkeypatch.setattr(closeout, "git", lambda *a, **k: "git@github.com:owner/private.git")
    monkeypatch.setattr(closeout, "run", _squash_run(pulls=[_merged_pr()], pull_ref=_pull_ref()))
    assert closeout.published(Path("/explicit/root"), HEAD, BRANCH)


@pytest.mark.parametrize(
    "pulls,pull_ref",
    [
        ([], None),
        ([_merged_pr(merged=None)], _pull_ref()),  # closed or open, never merged
        ([_merged_pr(repo="fork/private")], _pull_ref()),  # same branch name from a fork
        ([_merged_pr()], None),  # pull ref no longer exists
        ([_merged_pr()], _pull_ref(sha=TIP)),  # ref moved and does not cover the revision
        ([_merged_pr()], _pull_ref(ref="refs/pull/7/merge")),  # wrong ref
    ],
)
def test_squash_publication_fails_closed(monkeypatch, pulls, pull_ref):
    def not_ancestor(root, *args, **kwargs):
        if args == ("remote", "get-url", "origin"):
            return "git@github.com:owner/private.git"
        raise subprocess.CalledProcessError(1, ["git", *args])

    monkeypatch.setattr(closeout, "git", not_ancestor)
    monkeypatch.setattr(closeout, "run", _squash_run(pulls=pulls, pull_ref=pull_ref))
    assert not closeout.published(Path("/explicit/root"), HEAD, BRANCH)


def test_squash_publication_never_masks_a_non_404_failure(monkeypatch):
    monkeypatch.setattr(closeout, "git", lambda *a, **k: "git@github.com:owner/private.git")

    def unauthorized(command, **kwargs):
        raise subprocess.CalledProcessError(1, command, stderr=b"gh: Bad credentials (HTTP 401)")

    monkeypatch.setattr(closeout, "run", unauthorized)
    with pytest.raises(subprocess.CalledProcessError):
        closeout.published(Path("/explicit/root"), HEAD, BRANCH)


MERGE = "c" * 40
INSPECTED = "d" * 40


def _landed_env(monkeypatch, *, ancestor_rc=1, merge_is_ancestor=True, pulls=None):
    def git(root, *args, **kwargs):
        if args == ("remote", "get-url", "origin"):
            return "git@github.com:owner/private.git"
        assert args[:2] == ("merge-base", "--is-ancestor")
        revision = args[2]
        if revision == HEAD:
            raise subprocess.CalledProcessError(ancestor_rc, ["git", *args])
        assert revision == MERGE
        if not merge_is_ancestor:
            raise subprocess.CalledProcessError(1, ["git", *args])
        return ""

    def run(command, **kwargs):
        assert command[4] == f"repos/owner/private/commits/{HEAD}/pulls"
        return json.dumps(pulls)

    monkeypatch.setattr(closeout, "git", git)
    monkeypatch.setattr(closeout, "run", run)


def _landed_pr(head_sha=HEAD, repo="owner/private", merged="2026-10-18T05:08:58Z", merge=MERGE):
    return {"merged_at": merged, "merge_commit_sha": merge, "head": {"sha": head_sha, "repo": {"full_name": repo}}}


def test_verified_head_of_a_squash_merged_pr_has_landed(monkeypatch):
    _landed_env(monkeypatch, pulls=[_landed_pr()])
    closeout.verified_head_landed(Path("/explicit/root"), HEAD, INSPECTED)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"pulls": []},
        {"pulls": [_landed_pr(head_sha=TIP)]},  # PR head moved after verification
        {"pulls": [_landed_pr(repo="fork/private")]},
        {"pulls": [_landed_pr(merged=None)]},
        {"pulls": [_landed_pr(merge="bad")]},
        {"pulls": [_landed_pr()], "merge_is_ancestor": False},  # squash commit not in the inspected head
        {"pulls": [_landed_pr()], "ancestor_rc": 128},  # object unavailable: a named blocker, not a traceback
    ],
)
def test_unlanded_verified_head_is_a_named_blocker(monkeypatch, kwargs):
    _landed_env(monkeypatch, **kwargs)
    with pytest.raises(closeout.Unmeasured):
        closeout.verified_head_landed(Path("/explicit/root"), HEAD, INSPECTED)


def test_plain_ancestry_needs_no_github_lookup(monkeypatch):
    monkeypatch.setattr(closeout, "git", lambda *a, **k: "")
    monkeypatch.setattr(closeout, "run", lambda *a, **k: pytest.fail("ancestor must not call GitHub"))
    closeout.verified_head_landed(Path("/explicit/root"), HEAD, INSPECTED)
