from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path

import pytest
from click.testing import CliRunner
from limen.personal_custody import VolumeIdentity
from limen.repository_retirement import (
    Campaign,
    RetirementError,
    Runner,
    Runtime,
    digest,
    inspect,
    manifest_binding,
    sync,
)
from limen.repository_retirement_cli import repos_group
from limen.repository_retirement_custody import PairCustody
from limen.repository_retirement_keeper import Keeper


def git(path, *args):
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "tag.gpgSign=false",
            "-c",
            "commit.gpgSign=false",
            "-c",
            "core.hooksPath=/dev/null",
            "-C",
            str(path),
            *args,
        ],
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


class Gate:
    def __init__(self):
        self.proofs = set()
        self.deadline = time.time() + 120

    def authorize(self, key, paths, review=False):
        return self.deadline

    def heartbeat(self, review=False):
        pass

    def accepted(self, proof):
        return proof in self.proofs

    def report(self, proofs, review=False):
        assert review
        self.proofs.update(proofs.values())
        return {"independent": True, "proofs": proofs}

    def accounting(self):
        return 1.0, 119.0


@pytest.fixture
def fixture(tmp_path):
    remote = tmp_path / "remote.git"
    remote.mkdir()
    git(remote, "init", "--bare", "-q", "-b", "main")
    source = tmp_path / "source"
    git(tmp_path, "clone", "-q", str(remote), str(source))
    git(source, "config", "user.name", "Test")
    git(source, "config", "user.email", "test@example.invalid")
    (source / "tracked").write_text("original\n")
    (source / ".gitignore").write_text("secret.env\n")
    git(source, "add", ".")
    git(source, "commit", "-qm", "initial")
    git(source, "push", "-qu", "origin", "main")
    archive, recovery = tmp_path / "archive", tmp_path / "recovery"
    archive.mkdir(mode=0o700)
    recovery.mkdir(mode=0o700)
    volumes = {
        archive: VolumeIdentity(str(archive), "/dev/a", "drive-a", "A"),
        recovery: VolumeIdentity(str(recovery), "/dev/b", "drive-b", "B"),
    }
    inventory = tmp_path / "inventory.json"
    inventory.write_text(
        json.dumps(
            {
                "schema": "limen.storage_evacuation_inventory.v1",
                "custody_devices": [
                    {"name": name, **{k: v for k, v in vars(volumes[root]).items() if k != "mount"}}
                    for name, root in [("Archive4T", archive), ("T7Recovery", recovery)]
                ],
            }
        )
    )
    config = {
        "inventory": str(inventory),
        "inventory_sha256": hashlib.sha256(inventory.read_bytes()).hexdigest(),
        "archive_root": str(archive),
        "recovery_root": str(recovery),
    }
    manifest = {
        "schema": "limen.repository_retirement.v1",
        "campaign_id": "batch-test",
        "deadline": datetime.fromtimestamp(time.time() + 120, UTC).isoformat(),
        "repositories": [{"path": str(source), "repository_id": 42, "owner": "test/owner#2739"}],
        "custody": config,
        "run_id": "root",
        "review_run_id": "review",
    }
    campaign = Campaign(manifest, tmp_path / "state")
    runtime = Runtime(time.time() + 120)
    custody = PairCustody(
        config,
        runtime,
        volume_probe=lambda p: volumes[p],
        encryption_probe=lambda _p: True,
        copy_tree=lambda a, b: shutil.copytree(a, b, symlinks=True, copy_function=shutil.copy2),
    )
    gate = Gate()
    runner = Runner(
        campaign,
        runtime=runtime,
        custody=custody,
        keeper=gate,
        owner_probe=lambda _p: None,
        heavy=nullcontext,
        remote_identity=lambda _r, _url: {"id": 42, "name": "test/repository", "private": True},
    )
    return source, remote, campaign, runner, gate


def test_preserve_accept_remove_and_idempotent_resume(fixture):
    source, _, campaign, runner, _gate = fixture
    (source / "tracked").write_text("unique dirty work\n")
    (source / "untracked").write_text("private payload")
    (source / "secret.env").write_text("never-public-credential")
    git(source, "checkout", "-qb", "local-only")
    (source / "history").write_text("unpublished history")
    git(source, "add", "history")
    git(source, "commit", "-qm", "local only")
    first = runner.apply()
    assert first["copies_removed"] == 0
    assert first["custody_verified"] == 1
    assert source.exists()
    runner.accept()
    second = runner.apply()
    assert second["copies_removed"] == 1
    assert second["allocated_bytes_removed"] > 0
    assert not source.exists()
    assert "never-public-credential" not in json.dumps(second)
    proof = campaign.state["candidates"][str(source)]["custody"]
    restored = (
        Path(campaign.manifest["custody"]["archive_root"])
        / "limen-private/repository-retirement"
        / proof["digest"]
        / proof["sources"][0]["key"]
    )
    assert (restored / "tracked").read_text() == "unique dirty work\n"
    assert git(restored, "log", "-1", "--format=%s") == "local only"
    assert runner.apply()["copies_removed"] == 1


def test_fast_forward_direction_and_additive_tag(fixture, tmp_path):
    source, remote, campaign, runner, _ = fixture
    producer = tmp_path / "producer"
    git(tmp_path, "clone", "-q", str(remote), str(producer))
    git(producer, "config", "user.name", "Test")
    git(producer, "config", "user.email", "test@example.invalid")
    (producer / "new").write_text("upstream")
    git(producer, "add", ".")
    git(producer, "commit", "-qm", "upstream")
    git(producer, "tag", "v1")
    git(producer, "push", "-q", "origin", "main", "v1")
    old = git(source, "rev-parse", "HEAD")
    observed = inspect(runner.runtime, campaign.manifest["repositories"][0], runner.remote_identity)
    changes = sync(runner.runtime, campaign.manifest["repositories"][0], observed)
    assert git(source, "rev-parse", "HEAD") != old
    assert git(source, "rev-parse", "HEAD") == git(producer, "rev-parse", "HEAD")
    assert len(changes) == 2
    assert git(source, "rev-parse", "v1") == git(producer, "rev-parse", "v1")


def test_linked_dirty_worktree_native_removal_keeps_store(fixture, tmp_path):
    source, _, campaign, runner, _ = fixture
    linked = tmp_path / "linked"
    git(source, "worktree", "add", "-qb", "work/local", str(linked))
    (linked / "tracked").write_text("linked unique")
    (linked / "secret.env").write_text("private ignored")
    campaign.manifest["repositories"] = [{"path": str(linked), "repository_id": 42, "owner": "test/owner#2739"}]
    campaign.hash = digest(campaign.manifest)
    runner.apply()
    runner.accept()
    result = runner.apply()
    assert result["copies_removed"] == 1, result
    assert not linked.exists()
    assert source.exists()
    assert "work/local" in git(source, "branch", "--list")
    assert len(git(source, "worktree", "list").splitlines()) == 1


def test_drift_invalidates_independent_acceptance(fixture):
    source, _, _, runner, _ = fixture
    runner.apply()
    runner.accept()
    (source / "new-change").write_text("not in accepted custody")
    result = runner.apply()
    assert result["copies_removed"] == 0
    assert source.exists()
    assert result["retained"][0]["reason"] in {"independent-acceptance-pending", "custody-source-drift"}


def test_active_and_absent_paths_never_count_as_removal(fixture):
    source, _, _, runner, _ = fixture
    runner.owner_probe = lambda _p: 999
    assert runner.apply()["retained"][0]["reason"] == "active-process-or-open-file"
    assert source.exists()
    shutil.rmtree(source)
    result = runner.apply()
    assert result["copies_removed"] == 0
    assert result["retained"][0]["reason"] == "absent-without-completed-removal-journal"


def test_custody_must_restore_both_devices(fixture):
    source, _, campaign, runner, _ = fixture
    runner.apply()
    proof = campaign.state["candidates"][str(source)]["custody"]
    recovery = (
        Path(campaign.manifest["custody"]["recovery_root"])
        / "limen-private/repository-retirement"
        / proof["digest"]
        / proof["sources"][0]["key"]
    )
    (recovery / "tracked").write_text("corrupt")
    with pytest.raises(RetirementError, match="custody-archive-content-mismatch"):
        runner.accept()
    assert source.exists()


def test_native_git_reads_have_flags_and_timeouts(fixture):
    source, _, _, runner, _ = fixture
    assert runner.runtime.text(source, "rev-parse", "HEAD")
    expired = Runtime(time.time() - 1)
    with pytest.raises(RetirementError, match="deadline-exhausted"):
        expired.git(source, "status")
    failing = runner.runtime.git(source, "not-a-command")
    assert failing.returncode != 0
    assert runner.runtime.exits[-1]["exit"] == failing.returncode


def test_status_and_preview_cli_are_exposed():
    result = CliRunner().invoke(repos_group, ["--help"])
    assert result.exit_code == 0
    assert "accept" in result.output and "retire" in result.output and "status" in result.output


def test_manifest_binding_has_no_run_id_cycle(fixture):
    _, _, campaign, _, _ = fixture
    alternate = {**campaign.manifest, "run_id": "allocated-later", "review_run_id": "allocated-child"}
    assert manifest_binding(alternate) == manifest_binding(campaign.manifest)


def test_keeper_rejects_self_acceptance_and_previous_campaign(fixture):
    _, _, campaign, _, _ = fixture
    packet = {
        "execution": {
            "repository_retirement": {
                "campaign_id": "batch-test",
                "manifest_sha256": manifest_binding(campaign.manifest),
            }
        },
        "spend": {"unit": "agent_minutes", "limit": 120},
        "deadline": campaign.manifest["deadline"],
    }
    root = {"run_id": "root", "executor_session_id": "executor", "packet": packet}
    review = {
        "run_id": "review",
        "parent_run_id": "root",
        "executor_session_id": "executor",
        "packet": {**packet, "spend": {"unit": "agent_minutes", "limit": 10}},
    }

    class Client:
        def graph(self, _run):
            return {"nodes": [root, review]}

    with pytest.raises(RetirementError, match="executor-cannot-accept-own-removal"):
        Keeper(campaign.manifest, client=Client())
    review["executor_session_id"] = "reviewer"
    packet["execution"]["repository_retirement"]["campaign_id"] = "old-stopped-campaign"
    with pytest.raises(RetirementError, match="keeper-campaign-binding-mismatch"):
        Keeper(campaign.manifest, client=Client())
