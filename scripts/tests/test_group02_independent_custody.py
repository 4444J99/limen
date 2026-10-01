"""Reject archive escapes before private custody restoration."""

import importlib.util
import io
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "independent_custody", Path(__file__).resolve().parents[1] / "check-group02-independent-custody.py"
)
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


class ArchiveBoundaryTests(unittest.TestCase):
    def test_replica_writer_never_overwrites_existing_payload(self):
        with tempfile.TemporaryDirectory() as root:
            mount = Path(root)
            source = mount / "source"
            source.write_bytes(b"ciphertext")
            target = mount / "private/replicas/cipher.enc"
            with patch.object(CHECK, "REPLICA_MOUNTS", (mount,)):
                CHECK.write_replica(source, target)
                with self.assertRaises(FileExistsError):
                    CHECK.write_replica(source, target)
            self.assertEqual(target.read_bytes(), b"ciphertext")
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_replica_parent_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            mount = Path(root)
            destination = mount / "elsewhere"
            destination.mkdir()
            os.symlink(destination, mount / "private")
            with patch.object(CHECK, "REPLICA_MOUNTS", (mount,)), self.assertRaises(ValueError):
                CHECK.private_replica_parent(mount / "private/replicas")
            self.assertFalse((destination / "replicas").exists())

    def test_captured_link_schema_matches_inventory_without_following(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            link = directory / "link"
            target = directory / "missing-external-target"
            os.symlink(target, link)
            entries = CHECK.RESTORE.inventory(directory)
            entries["link"]["kind"] = "link"
            CHECK.RESTORE.verify_tree(directory, CHECK.normalized_entries(entries))
            self.assertFalse(target.exists())

    def archive(self, name: str, kind: bytes = tarfile.REGTYPE, target: str = ""):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w") as archive:
            member = tarfile.TarInfo(name)
            member.type = kind
            member.linkname = target
            archive.addfile(member)
        data.seek(0)
        return tarfile.open(fileobj=data)

    def test_traversal_and_hardlink_rejected(self):
        for name, kind in (("source/../outside", tarfile.REGTYPE), ("source/link", tarfile.LNKTYPE)):
            with self.archive(name, kind) as archive, self.assertRaises(ValueError):
                CHECK.safe_members(archive, "source")

    def test_external_symlink_cannot_escape_restore(self):
        with (
            self.archive("source/link", tarfile.SYMTYPE, "../../outside") as archive,
            tempfile.TemporaryDirectory() as root,
            self.assertRaises(tarfile.FilterError),
        ):
            archive.extractall(root, members=CHECK.safe_members(archive, "source"), filter="data")


if __name__ == "__main__":
    unittest.main()
