#!/usr/bin/env python3
"""Fixture checks for the handoff tools; no native agent state is used."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).parent
def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result
inventory = module("inventory", "inventory.py")
rollback = module("rollback", "stage-rollback.py")

class EvidenceChecks(unittest.TestCase):
    def test_deep_scan_deduplicates_aliases_and_root_overlap(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "tree"
            deep = root / "a/b/c/d/e/f/.codex"
            deep.mkdir(parents=True)
            (root / "other-codex").mkdir()
            (root / "codex-alias").symlink_to(deep)
            out = Path(raw) / "out"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(inventory.scan([str(root),str(deep)],out,30),0)
                self.assertEqual(inventory.verify(out),0)
            import json
            summary=json.loads((out/"summary.json").read_text())
            self.assertEqual(summary["codex_named_physical_directories"],2)
            self.assertEqual(summary["codex_related_aliases"],1)
            self.assertIsNone(summary["depth_limit"])
            with (out/"directories.jsonl").open("a") as handle:
                handle.write("{}\n")
            with self.assertRaises(ValueError):
                inventory.verify(out)

    def test_missing_root_is_nonzero_and_retained(self):
        with tempfile.TemporaryDirectory() as raw:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(inventory.scan([str(Path(raw)/"missing")],Path(raw)/"out",30),2)
                self.assertEqual(inventory.verify(Path(raw)/"out"),2)

    def test_stage_preserves_new_history_and_refuses_replay(self):
        with tempfile.TemporaryDirectory() as raw:
            base=Path(raw)
            backup,current=base/"backup",base/"current"
            backup.mkdir()
            current.mkdir()
            (backup/"old").write_text("older history")
            (current/"new").write_text("new history")
            (backup/"alias").symlink_to("old")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(rollback.prepare(backup,current,base/"dry",False),0)
                self.assertFalse((base/"dry").exists())
                self.assertEqual(rollback.prepare(backup,current,base/"stage",True),0)
            self.assertEqual((current/"new").read_text(),"new history")
            self.assertEqual((base/"stage/candidate/old").read_text(),"older history")
            with self.assertRaises(ValueError):
                rollback.prepare(backup,current,base/"stage",True)

    def test_failed_copy_retains_destination_and_partial(self):
        with tempfile.TemporaryDirectory() as raw:
            base=Path(raw)
            backup,current=base/"backup",base/"current"
            backup.mkdir()
            current.mkdir()
            (backup/"old").write_text("old")
            (current/"new").write_text("new")
            with mock.patch.object(rollback.subprocess,"run",side_effect=subprocess.CalledProcessError(1,"ditto")):
                with self.assertRaises(subprocess.CalledProcessError):
                    rollback.prepare(backup,current,base/"stage",True)
            self.assertEqual((current/"new").read_text(),"new")
            self.assertTrue((base/"stage/FAILED-PRESERVED").is_file())

if __name__ == "__main__":
    unittest.main()
