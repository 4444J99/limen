"""Reject archive escapes before private custody restoration."""

import importlib.util
import io
import tarfile
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "independent_custody", Path(__file__).resolve().parents[1] / "check-group02-independent-custody.py"
)
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


class ArchiveBoundaryTests(unittest.TestCase):
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
