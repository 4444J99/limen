from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from click.testing import CliRunner
from limen.personal_custody import VolumeIdentity
from limen.repository_archive_custody import ArchiveCustody, EnvelopePairCustody, allowlist
from limen.repository_retirement import RetirementError, Runner, Runtime, digest
from limen.repository_retirement_cli import repos_group

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="Native macOS archive metadata")


def git(root, *args):
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "commit.gpgSign=false",
            "-c",
            "core.fsmonitor=false",
            "-C",
            str(root),
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return result.stdout.strip()


@pytest.fixture
def archive_case(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir(mode=0o700)
    git(source, "init", "-q")
    git(source, "config", "user.name", "Custody Test")
    git(source, "config", "user.email", "test@example.invalid")
    (source / "tracked").write_text("tracked\n")
    (source / ".gitignore").write_text("ignored\n")
    git(source, "add", "tracked", ".gitignore")
    git(source, "commit", "-qm", "source")
    git(source, "update-ref", "refs/recovery/custom", "HEAD")
    (source / "ignored").write_text("private ignored payload\n")
    (source / "untracked").write_text("untracked payload\n")
    (source / "link").symlink_to("tracked")
    subprocess.run(
        ["/usr/bin/xattr", "-wx", "com.example.custody", b"binary\x00metadata".hex(), str(source / "tracked")],
        check=True,
    )
    subprocess.run(["/bin/chmod", "+a", "everyone allow read", str(source / "tracked")], check=True)
    git(source, "hash-object", "-w", "untracked")  # genuinely unreachable object
    roots = [tmp_path / "archive", tmp_path / "recovery"]
    for root in roots:
        root.mkdir(mode=0o700)
    volumes = {p: VolumeIdentity(str(p), f"/dev/test-{i}", f"independent-{i}", str(i)) for i, p in enumerate(roots)}
    inventory = tmp_path / "inventory.json"
    inventory.write_text(
        json.dumps(
            {
                "schema": "limen.storage_evacuation_inventory.v1",
                "custody_devices": [
                    {"name": name, **vars(volumes[p])} for name, p in zip(("Archive4T", "T7Recovery"), roots)
                ],
            }
        )
    )
    config = {
        "inventory": str(inventory),
        "inventory_sha256": hashlib.sha256(inventory.read_bytes()).hexdigest(),
        "archive_root": str(roots[0]),
        "recovery_root": str(roots[1]),
    }
    monkeypatch.setattr(os.path, "ismount", lambda p: Path(p) in roots)
    engine = ArchiveCustody(
        Runtime(time.time() + 90),
        tmp_path / "scratch",
        key_provider=lambda: "test-only-key",
        volume_probe=lambda p: volumes[p],
        encrypted_probe=lambda p: True,
    )
    entry = {"path": str(source), "gitdir": str(source / ".git"), "common": str(source / ".git")}
    state = tmp_path / "state"
    return engine, entry, config, state, roots


def test_complete_git_payload_metadata_restored_on_both_devices(archive_case):
    engine, entry, config, state, roots = archive_case
    result = engine.capture(entry, "binding", config, state)
    assert len(result["restorations"]) == 2
    assert all(p["passed"] for p in result["restorations"])
    assert result["retirement_authorized"] is False
    assert Path(entry["path"]).exists()
    for root in roots:
        files = list(root.rglob("*"))
        assert not any(p.name in {"tracked", "manifest.json", "payload-000.tar"} for p in files)
        assert not any(b"private ignored payload" in p.read_bytes() for p in files if p.is_file())


def test_unchanged_second_capture_changes_nothing(archive_case):
    engine, entry, config, state, roots = archive_case
    engine.capture(entry, "binding", config, state)
    before = {str(p): p.stat().st_mtime_ns for r in roots for p in r.rglob("*") if p.is_file()}
    assert engine.capture(entry, "binding", config, state)["changed"] is False
    assert before == {str(p): p.stat().st_mtime_ns for r in roots for p in r.rglob("*") if p.is_file()}


def test_broken_pointer_payload_restored_without_fake_git_proof(archive_case):
    engine, entry, config, state, _ = archive_case
    import shutil

    shutil.rmtree(Path(entry["path"]) / ".git")
    missing = Path(entry["path"]).parent / "missing-store"
    (Path(entry["path"]) / ".git").write_text(f"gitdir: {missing}\n")
    entry.update(gitdir=str(missing), common=str(missing))
    assert engine.preview([entry])[0]["git_coverage"] == "filesystem-only"
    result = engine.capture(entry, "binding", config, state)
    assert len(result["restorations"]) == 2
    assert not result["retirement_authorized"]


@pytest.mark.parametrize("tamper", ["ciphertext", "volume", "key"])
def test_verification_fails_closed(archive_case, tamper):
    engine, entry, config, state, roots = archive_case
    engine.capture(entry, "binding", config, state)
    locator = json.loads((state / f"{digest(entry['path'])[:16]}.json").read_text())
    if tamper == "ciphertext":
        p = roots[1] / "limen-private/repository-archives" / locator["archive_digest"] / "payload-000.enc"
        p.write_bytes(p.read_bytes()[:-1])
    elif tamper == "volume":
        locator["volumes"][0]["physical_device"] = "swapped-device"
    else:
        engine.key_provider = lambda: "incorrect-key"
    with pytest.raises(RetirementError):
        engine.verify(locator, config)
    assert Path(entry["path"]).exists()


def test_nested_unlisted_repository_rejected(archive_case):
    engine, entry, _config, _state, _roots = archive_case
    nested = Path(entry["path"]) / "other"
    nested.mkdir()
    git(nested, "init", "-q")
    assert engine.preview([entry])[0]["reason"] == "archive-unlisted-nested-repository"


def test_source_drift_never_creates_valid_local_receipt(archive_case, monkeypatch):
    engine, entry, config, state, _ = archive_case
    original = engine.verify

    def changed(*args):
        result = original(*args)
        (Path(entry["path"]) / "untracked").write_text("changed\n")
        return result

    monkeypatch.setattr(engine, "verify", changed)
    with pytest.raises(RetirementError, match="archive-source-drift"):
        engine.capture(entry, "binding", config, state)
    assert not (state / f"{digest(entry['path'])[:16]}.json").exists()


def test_no_plaintext_staging_on_unencrypted_scratch(archive_case):
    engine, entry, config, state, roots = archive_case
    engine.encrypted_probe = lambda p: False
    with pytest.raises(RetirementError, match="scratch-encryption-unverified"):
        engine.capture(entry, "binding", config, state)
    assert not any(p.is_file() for r in roots for p in r.rglob("*"))


def test_allowlist_rejects_overlap_and_duplicates(tmp_path):
    manifest = tmp_path / "allowlist.json"
    for paths in (["/a", "/a/b"], ["/a", "/a"], ["relative"]):
        manifest.write_text(json.dumps({"repositories": [{"path": p} for p in paths]}))
        with pytest.raises(RetirementError):
            allowlist(manifest)


def test_preview_has_no_custody_side_effects(archive_case, monkeypatch):
    engine, entry, _config, state, roots = archive_case
    assert engine.preview([entry])[0]["status"] == "preservable"
    assert not state.exists()
    assert not engine.scratch.exists()
    assert not any(p.is_file() for r in roots for p in r.rglob("*"))
    assert CliRunner().invoke(repos_group, ["custody", "--help"]).exit_code == 0


def test_retirement_adapter_binds_restored_records_to_private_proof(archive_case):
    engine, entry, config, state, _roots = archive_case
    backend = EnvelopePairCustody(config, engine.runtime)
    backend.engine, backend.state = engine, state
    proof = backend.capture([Path(entry["path"])], journal_root=state / "removals")
    backend.verify(proof, restore=False)
    proof["sources"][0]["records"][0]["mode"] = 0
    proof["digest"] = digest({k: v for k, v in proof.items() if k != "digest"})
    with pytest.raises(RetirementError, match="source-proof-mismatch"):
        backend.verify(proof)


def test_local_key_restore_cannot_authorize_acceptance_or_removal():
    from types import SimpleNamespace

    runner = object.__new__(Runner)
    runner.campaign = SimpleNamespace(manifest={"custody": {"mode": "arca-envelope"}})
    for review in (False, True):
        with pytest.raises(RetirementError, match="independent-key-recovery-proof-required"):
            runner._verify_current({}, {}, review=review)
