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
