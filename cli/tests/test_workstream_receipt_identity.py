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
        assert git("diff", "--cached", "--name-only") == "receipt.json"
    else:
        assert result.returncode == 0, result.stderr
        expected = (
            ("123+fixture@users.noreply.github.com\n" * 2).strip()
            if github
            else ("inherited-author@example.invalid\ninherited-committer@example.invalid")
        )
        assert git("log", "-1", "--format=%ae%n%ce") == expected
    assert git("config", "user.email") == "private@example.invalid"


def test_admitted_receipt_uses_push_url(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()

    git("init", "-q")
    git("config", "user.name", "Fixture Owner")
    git("config", "user.email", "private@example.invalid")
    git("remote", "add", "origin", "local-fixture.git")
    git("remote", "set-url", "--push", "origin", "git@github.com:owner/repo.git")
    (tmp_path / "receipt.json").write_text("{}\n")
    capsule = tmp_path / "capsule"
    capsule.mkdir()
    shutil.copyfile(ROOT / "cli/src/limen/workstream_contract.py", capsule / "workstream-contract.py")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    gh = fake_bin / "gh"
    gh.write_text("#!/bin/sh\nprintf '%s\\n' '123+fixture@users.noreply.github.com'\n")
    gh.chmod(0o755)
    env = {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}", "LIMEN_CAPSULE_DIR": str(capsule)}
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; email="$(workstream_github_receipt_email)" && '
            'git add receipt.json && workstream_commit_admitted_receipt "$email" -qm receipt -- receipt.json',
            "test",
            str(ROOT / "scripts/lib/workstream-capsule.sh"),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert git("log", "-1", "--format=%ae%n%ce") == (
        "123+fixture@users.noreply.github.com\n123+fixture@users.noreply.github.com"
    )


@pytest.mark.parametrize(
    ("machine", "expected"),
    [
        ("actions", "41898282+github-actions[bot]@users.noreply.github.com"),
        ("app", "999+fixture-app[bot]@users.noreply.github.com"),
    ],
)
def test_admitted_receipt_supports_machine_identity(tmp_path, machine, expected):
    capsule = tmp_path / "capsule"
    capsule.mkdir()
    shutil.copyfile(ROOT / "cli/src/limen/workstream_contract.py", capsule / "workstream-contract.py")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    gh = fake_bin / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        '  *" user --jq "*) exit 1 ;;\n'
        "  *github-actions*) printf '%s\\n' '41898282+github-actions[bot]@users.noreply.github.com' ;;\n"
        "  *\" app --jq .slug\"*) printf '%s\\n' 'fixture-app' ;;\n"
        "  *fixture-app*) printf '%s\\n' '999+fixture-app[bot]@users.noreply.github.com' ;;\n"
        "  *) exit 1 ;;\n"
        "esac\n"
    )
    gh.chmod(0o755)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "remote", "add", "origin", "git@github.com:owner/repo.git"], cwd=tmp_path, check=True)
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "LIMEN_CAPSULE_DIR": str(capsule),
        "GITHUB_ACTIONS": "true" if machine == "actions" else "false",
    }
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; workstream_github_receipt_email',
            "test",
            str(ROOT / "scripts/lib/workstream-capsule.sh"),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected
