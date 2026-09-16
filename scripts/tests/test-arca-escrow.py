#!/usr/bin/env python3
"""Hermetic escrow recovery boundary tests; no actual vault access."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "arca_escrow", Path(__file__).resolve().parents[1] / "check-arca-escrow.py")
arca = importlib.util.module_from_spec(spec)
spec.loader.exec_module(arca)


def archive(content=b"recovery evidence"):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as tar:
        info = tarfile.TarInfo("private/source")
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    return output.getvalue()


class EscrowTests(unittest.TestCase):
    def test_regular_content_is_read_without_extraction(self):
        self.assertEqual(arca.inspect_tar(archive(b"abc")),
                         {"regular_files": 1, "plaintext_bytes": 3})

    def test_malformed_empty_and_oversized_fail(self):
        for data in (b"", b"bad", b"x" * (arca.LIMIT + 1), b"\0" * 10240):
            with self.subTest(length=len(data)):
                with self.assertRaises((ValueError, tarfile.TarError)):
                    arca.inspect_tar(data)

    def test_truncated_regular_member_fails(self):
        with self.assertRaises(tarfile.TarError):
            arca.inspect_tar(archive(b"x" * 1024)[:600])

    def test_member_count_bound(self):
        with patch.object(arca, "LIMIT", 1024 * 1024):
            output = io.BytesIO()
            with tarfile.open(fileobj=output, mode="w") as tar:
                for n in range(1025):
                    info = tarfile.TarInfo(str(n))
                    info.type = tarfile.DIRTYPE
                    tar.addfile(info)
            with self.assertRaises(ValueError):
                arca.inspect_tar(output.getvalue())

    def test_mismatched_manifest_stops_before_key_read(self):
        manifest = json.dumps({"_private": {"parts": 0, "bytes": 32}}).encode()
        with patch.object(arca, "run", side_effect=[b"a" * 40, b"100", manifest, b"64"]) as run:
            with self.assertRaisesRegex(ValueError, "size mismatch"):
                arca.recover(Path("/unused"))
            self.assertFalse(any(call.args[0][0] == "op" for call in run.call_args_list))

    def test_provider_failure_is_redacted(self):
        failure = subprocess.CalledProcessError(1, "private", stderr=b"SECRET")
        with patch.object(arca, "recover", side_effect=failure), patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(arca.main(), 1)
            self.assertNotIn("SECRET", out.getvalue())
            self.assertFalse(json.loads(out.getvalue())["accepted"])


if __name__ == "__main__":
    unittest.main()
