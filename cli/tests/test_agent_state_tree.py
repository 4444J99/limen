from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from limen.agent_state.crypto import EncryptedAtomPacker, verify_atom_packs
from limen.agent_state.models import MetabolismReceipt, RestoreProof
from limen.agent_state.tree import (
    atomize_file_tree,
    brctl_evict,
    evict_cloud_materializations,
    plan_cloud_materializations,
    plan_exact_retention,
    plan_retention,
    retire_cold_files,
)

KEY = "tree-test-key"


def _set_age(path: Path, *, days: int, now: float) -> None:
    timestamp = now - days * 86400
    os.utime(path, (timestamp, timestamp))


def test_retention_keeps_seven_days_under_two_gib(tmp_path: Path) -> None:
    now = time.time()
    old = tmp_path / "old.jsonl"
    old.write_bytes(b"old" * 100)
    _set_age(old, days=8, now=now)
    recent = tmp_path / "recent.jsonl"
    recent.write_bytes(b"recent" * 100)
    _set_age(recent, days=1, now=now)

    plan = plan_retention(tmp_path, now=now, maximum_hot_bytes=1024)

    assert plan.cold_paths == ("old.jsonl",)
    assert plan.hot_paths == ("recent.jsonl",)
    assert plan.cold_bytes == old.stat().st_size
    assert plan.hot_bytes == recent.stat().st_size


def test_hot_byte_ceiling_moves_older_recent_files_to_cold(tmp_path: Path) -> None:
    now = time.time()
    newest = tmp_path / "newest"
    newest.write_bytes(b"n" * 700)
    _set_age(newest, days=1, now=now)
    older = tmp_path / "older"
    older.write_bytes(b"o" * 700)
    _set_age(older, days=2, now=now)

    plan = plan_retention(tmp_path, now=now, maximum_hot_bytes=1000)

    assert plan.hot_paths == ("newest",)
    assert plan.cold_paths == ("older",)
    assert plan.hot_bytes <= 1000


def test_exact_retention_captures_every_file_except_explicit_retains(tmp_path: Path) -> None:
    retained = tmp_path / "opencode.db"
    retained.write_bytes(b"empty schema")
    (tmp_path / "tool-output").mkdir()
    output = tmp_path / "tool-output" / "payload"
    output.write_bytes(b"user-bearing output")
    log = tmp_path / "log"
    log.write_bytes(b"session log")

    plan = plan_exact_retention(tmp_path, retain_paths=("opencode.db",))

    assert plan.hot_paths == ("opencode.db",)
    assert plan.hot_bytes == retained.stat().st_size
    assert plan.cold_paths == ("log", "tool-output/payload")
    assert plan.cold_bytes == log.stat().st_size + output.stat().st_size


@pytest.mark.parametrize("relative", ("../outside", "/absolute", ".", "missing"))
def test_exact_retention_rejects_unsafe_or_missing_path(tmp_path: Path, relative: str) -> None:
    with pytest.raises((FileNotFoundError, ValueError)):
        plan_exact_retention(tmp_path, retain_paths=(relative,))


def test_exact_retention_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside"
    outside.write_bytes(b"outside")
    (tmp_path / "link").symlink_to(outside)

    with pytest.raises(ValueError, match="regular file within the root"):
        plan_exact_retention(tmp_path, retain_paths=("link",))


def test_file_tree_atoms_restore_and_deduplicate_chunks(tmp_path: Path) -> None:
    now = time.time()
    first = tmp_path / "a.jsonl"
    second = tmp_path / "b.jsonl"
    value = b"same-private-content" * 100
    first.write_bytes(value)
    second.write_bytes(value)
    _set_age(first, days=9, now=now)
    _set_age(second, days=9, now=now)
    plan = plan_retention(tmp_path, now=now)
    encrypted = tmp_path / "encrypted"
    packer = EncryptedAtomPacker(encrypted, KEY, pack_plaintext_limit=2048, chunk_limit=512)

    result = atomize_file_tree(plan, packer, chunk_size=len(value))
    packs = list(packer.close())

    assert result.file_count == 2
    assert result.duplicate_chunks == 1
    assert result.source.stable
    proof = verify_atom_packs(packs, encrypted, KEY, logical_sha256=result.logical_sha256)
    assert proof.passed


def test_mutation_during_file_capture_fails(tmp_path: Path) -> None:
    now = time.time()
    source = tmp_path / "old.jsonl"
    source.write_bytes(b"private")
    _set_age(source, days=9, now=now)
    plan = plan_retention(tmp_path, now=now)
    changed = False

    def sink(_envelope: dict[str, object], _line: bytes) -> None:
        nonlocal changed
        if not changed:
            source.write_bytes(b"changed")
            changed = True

    with pytest.raises(RuntimeError, match="mutated during capture"):
        atomize_file_tree(plan, sink)


def test_verified_cold_files_retire_but_hot_file_remains(tmp_path: Path) -> None:
    now = time.time()
    cold = tmp_path / "old.jsonl"
    cold.write_bytes(b"old")
    _set_age(cold, days=9, now=now)
    hot = tmp_path / "hot.jsonl"
    hot.write_bytes(b"hot")
    _set_age(hot, days=1, now=now)
    plan = plan_retention(tmp_path, now=now)
    packer = EncryptedAtomPacker(tmp_path / "encrypted", KEY)
    result = atomize_file_tree(plan, packer)
    packs = list(packer.close())
    receipt = MetabolismReceipt(
        schema="limen.agent_state_metabolism.v1",
        run_id="run",
        source=result.source,
        atom_count=result.atom_count,
        logical_sha256=result.logical_sha256,
        packs=packs,
        git_remote="organvm/arca",
        git_commit="a" * 40,
        git_receipt_commit="b" * 40,
        external_chunks=[packs[0].chunks[0]],
        restorations=[
            RestoreProof(scope="git-sample", passed=True),
            RestoreProof(scope="git-full-manifest", passed=True),
            RestoreProof(scope="external-full", passed=True),
        ],
    )

    deleted = retire_cold_files(receipt, plan, open_probe=lambda _root: set())

    assert deleted == 1
    assert not cold.exists()
    assert hot.exists()


def test_open_cold_file_denies_retirement(tmp_path: Path) -> None:
    now = time.time()
    cold = tmp_path / "old.jsonl"
    cold.write_bytes(b"old")
    _set_age(cold, days=9, now=now)
    plan = plan_retention(tmp_path, now=now)
    packer = EncryptedAtomPacker(tmp_path / "encrypted", KEY)
    result = atomize_file_tree(plan, packer)
    packs = list(packer.close())
    receipt = MetabolismReceipt(
        schema="limen.agent_state_metabolism.v1",
        run_id="run",
        source=result.source,
        atom_count=result.atom_count,
        logical_sha256=result.logical_sha256,
        packs=packs,
        git_remote="organvm/arca",
        git_commit="a" * 40,
        git_receipt_commit="b" * 40,
        external_chunks=[packs[0].chunks[0]],
        restorations=[
            RestoreProof(scope="git-sample", passed=True),
            RestoreProof(scope="git-full-manifest", passed=True),
            RestoreProof(scope="external-full", passed=True),
        ],
    )

    with pytest.raises(RuntimeError, match="active"):
        retire_cold_files(receipt, plan, open_probe=lambda _root: {cold.resolve()})
    assert cold.exists()


def test_active_cwd_directory_denies_descendant_retirement(tmp_path: Path) -> None:
    now = time.time()
    active = tmp_path / "session"
    nested = active / "nested"
    nested.mkdir(parents=True)
    cold_files = (active / "one.jsonl", nested / "two.jsonl")
    for cold in cold_files:
        cold.write_bytes(b"old")
        _set_age(cold, days=9, now=now)
    plan = plan_retention(tmp_path, now=now)
    packer = EncryptedAtomPacker(tmp_path / "encrypted", KEY)
    result = atomize_file_tree(plan, packer)
    packs = list(packer.close())
    receipt = MetabolismReceipt(
        schema="limen.agent_state_metabolism.v1",
        run_id="run",
        source=result.source,
        atom_count=result.atom_count,
        logical_sha256=result.logical_sha256,
        packs=packs,
        git_remote="organvm/arca",
        git_commit="a" * 40,
        git_receipt_commit="b" * 40,
        external_chunks=[packs[0].chunks[0]],
        restorations=[
            RestoreProof(scope="git-sample", passed=True),
            RestoreProof(scope="git-full-manifest", passed=True),
            RestoreProof(scope="external-full", passed=True),
        ],
    )

    with pytest.raises(RuntimeError, match="active"):
        retire_cold_files(receipt, plan, open_probe=lambda _root: {active.resolve()})
    assert all(cold.exists() for cold in cold_files)


def test_active_sibling_prefix_does_not_block_retirement(tmp_path: Path) -> None:
    now = time.time()
    active = tmp_path / "session"
    active.mkdir()
    sibling = tmp_path / "session-old"
    sibling.mkdir()
    cold = sibling / "old.jsonl"
    cold.write_bytes(b"old")
    _set_age(cold, days=9, now=now)
    plan = plan_retention(tmp_path, now=now)
    packer = EncryptedAtomPacker(tmp_path / "encrypted", KEY)
    result = atomize_file_tree(plan, packer)
    packs = list(packer.close())
    receipt = MetabolismReceipt(
        schema="limen.agent_state_metabolism.v1",
        run_id="run",
        source=result.source,
        atom_count=result.atom_count,
        logical_sha256=result.logical_sha256,
        packs=packs,
        git_remote="organvm/arca",
        git_commit="a" * 40,
        git_receipt_commit="b" * 40,
        external_chunks=[packs[0].chunks[0]],
        restorations=[
            RestoreProof(scope="git-sample", passed=True),
            RestoreProof(scope="git-full-manifest", passed=True),
            RestoreProof(scope="external-full", passed=True),
        ],
    )

    deleted = retire_cold_files(receipt, plan, open_probe=lambda _root: {active.resolve()})

    assert deleted == 1
    assert not cold.exists()
    assert active.exists()


def test_cloud_plan_never_selects_placeholder(tmp_path: Path) -> None:
    materialized = tmp_path / "materialized.mov"
    materialized.write_bytes(b"local")
    placeholder = tmp_path / "placeholder.pdf"
    placeholder.write_bytes(b"remote")

    plan = plan_cloud_materializations(
        tmp_path,
        materialized_probe=lambda path: path.name == materialized.name,
    )

    assert plan.cold_paths == ("materialized.mov",)
    assert plan.cold_bytes == materialized.stat().st_size
    assert plan.hot_paths == ("placeholder.pdf",)


def test_default_cloud_eviction_adapter_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="hidden brctl eviction was non-atomic"):
        brctl_evict(tmp_path / "payload.json")


def test_cloud_eviction_uses_file_provider_after_restore_gate(tmp_path: Path) -> None:
    materialized = tmp_path / "materialized.mov"
    materialized.write_bytes(b"local")
    plan = plan_cloud_materializations(tmp_path, materialized_probe=lambda _path: True)
    packer = EncryptedAtomPacker(tmp_path / "encrypted", KEY)
    result = atomize_file_tree(plan, packer)
    packs = list(packer.close())
    receipt = MetabolismReceipt(
        schema="limen.agent_state_metabolism.v1",
        run_id="run",
        source=result.source,
        atom_count=result.atom_count,
        logical_sha256=result.logical_sha256,
        packs=packs,
        git_remote="organvm/arca",
        git_commit="a" * 40,
        git_receipt_commit="b" * 40,
        external_chunks=[packs[0].chunks[0]],
        restorations=[
            RestoreProof(scope="git-sample", passed=True),
            RestoreProof(scope="git-full-manifest", passed=True),
            RestoreProof(scope="external-full", passed=True),
        ],
    )
    remaining = {materialized.resolve()}

    eviction = evict_cloud_materializations(
        receipt,
        plan,
        open_probe=lambda _root: set(),
        evict_command=lambda path: remaining.remove(path),
        materialized_probe=lambda path: path in remaining,
        wait=lambda _seconds: None,
    )

    assert eviction.evicted_files == 1
    assert eviction.allocated_after == 0
    assert materialized.exists()


def test_cloud_eviction_retains_non_evictable_finder_metadata(tmp_path: Path) -> None:
    metadata = tmp_path / ".DS_Store"
    metadata.write_bytes(b"finder metadata")
    materialized = tmp_path / "materialized.mov"
    materialized.write_bytes(b"local")
    plan = plan_cloud_materializations(tmp_path, materialized_probe=lambda _path: True)
    packer = EncryptedAtomPacker(tmp_path / "encrypted", KEY)
    result = atomize_file_tree(plan, packer)
    packs = list(packer.close())
    receipt = MetabolismReceipt(
        schema="limen.agent_state_metabolism.v1",
        run_id="run",
        source=result.source,
        atom_count=result.atom_count,
        logical_sha256=result.logical_sha256,
        packs=packs,
        git_remote="organvm/arca",
        git_commit="a" * 40,
        git_receipt_commit="b" * 40,
        external_chunks=[packs[0].chunks[0]],
        restorations=[
            RestoreProof(scope="git-sample", passed=True),
            RestoreProof(scope="git-full-manifest", passed=True),
            RestoreProof(scope="external-full", passed=True),
        ],
    )
    remaining = {metadata.resolve(), materialized.resolve()}

    eviction = evict_cloud_materializations(
        receipt,
        plan,
        open_probe=lambda _root: set(),
        evict_command=lambda path: remaining.remove(path),
        materialized_probe=lambda path: path in remaining,
        wait=lambda _seconds: None,
    )

    assert eviction.selected_files == 1
    assert eviction.evicted_files == 1
    assert eviction.retained_non_evictable_files == 1
    assert eviction.retained_non_evictable_bytes > 0
    assert remaining == {metadata.resolve()}


def test_cloud_eviction_denies_active_cwd_ancestor(tmp_path: Path) -> None:
    active = tmp_path / "session"
    active.mkdir()
    materialized = active / "materialized.mov"
    materialized.write_bytes(b"local")
    plan = plan_cloud_materializations(tmp_path, materialized_probe=lambda _path: True)
    packer = EncryptedAtomPacker(tmp_path / "encrypted", KEY)
    result = atomize_file_tree(plan, packer)
    packs = list(packer.close())
    receipt = MetabolismReceipt(
        schema="limen.agent_state_metabolism.v1",
        run_id="run",
        source=result.source,
        atom_count=result.atom_count,
        logical_sha256=result.logical_sha256,
        packs=packs,
        git_remote="organvm/arca",
        git_commit="a" * 40,
        git_receipt_commit="b" * 40,
        external_chunks=[packs[0].chunks[0]],
        restorations=[
            RestoreProof(scope="git-sample", passed=True),
            RestoreProof(scope="git-full-manifest", passed=True),
            RestoreProof(scope="external-full", passed=True),
        ],
    )

    with pytest.raises(RuntimeError, match="active"):
        evict_cloud_materializations(
            receipt,
            plan,
            open_probe=lambda _root: {active.resolve()},
            materialized_probe=lambda _path: True,
        )
