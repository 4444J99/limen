"""Generated admission commits must not publish the owner's private email."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "remote",
    [
        "https://github.com/owner/repo.git",
        "git@github.com:owner/repo.git",
        "ssh://git@github.com/owner/repo.git",
        "https://token@github.com/owner/repo.git",
        "local-fixture.git",
    ],
)
@pytest.mark.parametrize("lookup", ["valid", "failed", "invalid"])
def test_admitted_receipt_identity(tmp_path, remote, lookup):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()

    git("init", "-q")
    git("config", "user.name", "Fixture Owner")
    git("config", "user.email", "private@example.invalid")
    git("remote", "add", "origin", remote)
    (tmp_path / "receipt.json").write_text("{}\n")
    git("add", "receipt.json")
    capsule = tmp_path / "capsule"
    capsule.mkdir()
    shutil.copyfile(ROOT / "cli/src/limen/workstream_contract.py", capsule / "workstream-contract.py")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    gh = fake_bin / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        + {
            "valid": "printf '%s\\n' '123+fixture@users.noreply.github.com'\n",
            "failed": "exit 1\n",
            "invalid": "printf '%s\\n' 'private@example.invalid'\n",
        }[lookup]
    )
    gh.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "LIMEN_CAPSULE_DIR": str(capsule),
        "GIT_AUTHOR_EMAIL": "inherited-author@example.invalid",
        "GIT_COMMITTER_EMAIL": "inherited-committer@example.invalid",
    }
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; workstream_commit_admitted_receipt -qm receipt -- receipt.json',
            "test",
            str(ROOT / "scripts/lib/workstream-capsule.sh"),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    github = remote != "local-fixture.git"
    if github and lookup != "valid":
        assert result.returncode != 0
        assert (
            subprocess.run(["git", "rev-parse", "--verify", "HEAD"], cwd=tmp_path, capture_output=True).returncode != 0
        )
    else:
        assert result.returncode == 0, result.stderr
        expected = (
            ("123+fixture@users.noreply.github.com\n" * 2).strip()
            if github
            else ("inherited-author@example.invalid\ninherited-committer@example.invalid")
        )
        assert git("log", "-1", "--format=%ae%n%ce") == expected
    assert git("config", "user.email") == "private@example.invalid"
