from __future__ import annotations

import importlib.util
import json
import os
import stat
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "arca-file-objects.py"
SPEC = importlib.util.spec_from_file_location("arca_file_objects", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
arca = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(arca)


def fake_crypto(monkeypatch: pytest.MonkeyPatch) -> None:
    def encrypt(source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = source.read_bytes()
        target.write_bytes(b"ENC\0" + payload)

    def decrypt(source: Path, target: Path) -> None:
        payload = source.read_bytes()
        if not payload.startswith(b"ENC\0"):
            raise arca.ObjectError("test catalog unavailable")
        target.write_bytes(payload[4:])

    monkeypatch.setattr(arca.PRIVATE, "_encrypt_file", encrypt)
    monkeypatch.setattr(arca.PRIVATE, "_decrypt_file", decrypt)


def test_independent_objects_and_incremental_reuse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_crypto(monkeypatch)
    source = tmp_path / "private"
    source.mkdir()
    (source / "a.txt").write_text("same", encoding="utf-8")
    (source / "b.txt").write_text("change", encoding="utf-8")
    first = tmp_path / "first"
    result = arca.build(source, first)
    assert result["new_objects"] == 2
    assert result["reused_objects"] == 0

    (source / "b.txt").write_text("changed", encoding="utf-8")
    second = tmp_path / "second"
    result = arca.build(source, second, previous=first / "catalog.gpg")
    assert result["new_objects"] == 1
    assert result["reused_objects"] == 1
    old = json.loads((first / "catalog.gpg").read_bytes()[4:])
    new = json.loads((second / "catalog.gpg").read_bytes()[4:])
    old_entries = {row["path"]: row for row in old["entries"]}
    new_entries = {row["path"]: row for row in new["entries"]}
    assert old_entries["a.txt"]["object_id"] == new_entries["a.txt"]["object_id"]
    assert old_entries["b.txt"]["object_id"] != new_entries["b.txt"]["object_id"]
    assert (second / "objects" / f"{old_entries['a.txt']['object_id']}.gpg").read_bytes() == b"ENC\0same"
    third = tmp_path / "third"
    result = arca.build(source, third, previous=second / "catalog.gpg")
    assert result["state"] == "unchanged"
    assert result["new_objects"] == 0
    assert result["reused_objects"] == 2
    assert (third / "catalog.gpg").read_bytes() == (second / "catalog.gpg").read_bytes()


def test_inventory_preserves_symlinks_and_modes_without_following_them(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    external = tmp_path / "outside"
    external.mkdir()
    (external / "secret").write_text("external", encoding="utf-8")
    (root / "link").symlink_to(external, target_is_directory=True)
    executable = root / "run"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o700)
    rows = arca.inventory(root)
    assert {str(row["path"]) for row in rows} == {"link", "run"}
    assert next(row for row in rows if row["path"] == "link")["target"] == str(external)
    assert next(row for row in rows if row["path"] == "run")["mode"] == 0o700


def test_failed_catalog_encryption_does_not_replace_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_crypto(monkeypatch)
    source = tmp_path / "private"
    source.mkdir()
    (source / "a").write_text("payload", encoding="utf-8")
    output = tmp_path / "out"
    output.mkdir()
    catalog = output / "catalog.gpg"
    catalog.write_bytes(b"previous catalog")
    real_encrypt = arca.PRIVATE._encrypt_file

    def fail_catalog(source_path: Path, target: Path) -> None:
        if source_path.name == "catalog.json":
            raise arca.ObjectError("interrupted")
        real_encrypt(source_path, target)

    monkeypatch.setattr(arca.PRIVATE, "_encrypt_file", fail_catalog)
    with pytest.raises(arca.ObjectError, match="interrupted"):
        arca.build(source, output)
    assert catalog.read_bytes() == b"previous catalog"
    assert list((output / "objects").glob("*.gpg"))


def test_restore_reconstructs_files_symlinks_and_modes_atomically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_crypto(monkeypatch)
    source = tmp_path / "private"
    source.mkdir(mode=0o700)
    (source / "nested").mkdir()
    file = source / "nested" / "run"
    file.write_text("payload", encoding="utf-8")
    file.chmod(0o700)
    (source / "alias").symlink_to("nested/run")
    output = tmp_path / "objects-store"
    arca.build(source, output)
    restored = tmp_path / "restored"
    result = arca.restore(output / "catalog.gpg", output, restored)
    assert result["files"] == 1
    assert (restored / "nested" / "run").read_text(encoding="utf-8") == "payload"
    assert stat.S_IMODE((restored / "nested" / "run").stat().st_mode) == 0o700
    assert os.readlink(restored / "alias") == "nested/run"
    with pytest.raises(arca.ObjectError, match="already exists"):
        arca.restore(output / "catalog.gpg", output, restored)


def test_restore_rejects_unsafe_catalog_paths_before_publishing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_crypto(monkeypatch)
    source = tmp_path / "private"
    source.mkdir()
    (source / "safe").write_text("payload", encoding="utf-8")
    output = tmp_path / "objects-store"
    arca.build(source, output)
    catalog = output / "catalog.gpg"
    catalog.write_bytes(b'ENC\0{"schema":"arca-file-catalog-v1","entries":[{"path":"../escape","type":"directory","mode":448}]}')
    destination = tmp_path / "restored"
    with pytest.raises(arca.ObjectError, match="unsafe relative path"):
        arca.restore(catalog, output, destination)
    assert not destination.exists()


def test_large_encrypted_file_is_split_and_reassembled_for_restore(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_crypto(monkeypatch)
    monkeypatch.setattr(arca, "OBJECT_PART_BYTES", 5)
    source = tmp_path / "private"
    source.mkdir()
    (source / "large.bin").write_bytes(b"abcdefghijklmno")
    output = tmp_path / "objects-store"
    result = arca.build(source, output)
    catalog = json.loads((output / "catalog.gpg").read_bytes()[4:])
    entry = next(row for row in catalog["entries"] if row["path"] == "large.bin")
    assert result["new_objects"] == 4
    assert len(entry["objects"]) == 4
    restored = tmp_path / "restored"
    arca.restore(output / "catalog.gpg", output, restored)
    assert (restored / "large.bin").read_bytes() == b"abcdefghijklmno"
