#!/usr/bin/env python3
"""Hermetic relocated Insights discovery and capture regression tests."""

import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InsightsRuntimeTests(unittest.TestCase):
    def test_effective_and_distinct_legacy_stores_survive_alias_deduplication(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            active = home / "active"
            legacy = home / ".claude" / "projects"
            for path in [active / "projects", active / "sessions", legacy]:
                path.mkdir(parents=True)
            (home / ".codex").symlink_to(active)
            with patch.dict(os.environ, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(active), "CODEX_HOME": str(active)}):
                ingest = load("ingest_runtime_test", "insight-cross-vendor-ingest.py")
                engine = load("engine_runtime_test", "vendor-insights.py")
            ingest.VENDOR_REGISTRY["claude"]["extra_root_globs"] = [str(active / "projects")]
            self.assertEqual(set(ingest.claude_estate_roots()), {active / "projects", legacy})
            roots = engine._codex_roots(ingest)
            self.assertEqual(len(roots), 1)
            self.assertEqual(roots[0].resolve(), (active / "sessions").resolve())
            self.assertEqual(ingest.VENDOR_REGISTRY["codex"]["path"], active / "history.jsonl")

    def test_capture_passes_effective_report_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            active = home / "active config"
            for config in [active, home / ".claude"]:
                (config / "usage-data").mkdir(parents=True)
                (config / "usage-data" / "report.html").write_text("report")
            tool = home / ".local" / "bin" / "insights-snapshot"
            tool.parent.mkdir(parents=True)
            tool.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "$HOME/args"\n')
            tool.chmod(0o755)
            env = dict(os.environ, HOME=str(home), CLAUDE_CONFIG_DIR=str(active))
            subprocess.run(["bash", str(ROOT / "scripts/hooks/insights-capture.sh")], env=env, check=True)
            self.assertEqual((home / "args").read_text().splitlines(), ["--src", str(active / "usage-data/report.html"), "--only-if-newer", "--quiet"])
            self.assertTrue((active / "usage-data/.capture.log").exists())
            self.assertFalse((home / ".claude/usage-data/.capture.log").exists())


if __name__ == "__main__":
    unittest.main()
