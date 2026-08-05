"""Tests for the ingestion-coverage diagnostic (ingest-coverage.py).

Answers "are we at 100% context?" on screen: how many items, from how many sources, how fresh, and
which known prompt-sources still have no adapter. Read-only over the manifest; fails open if absent.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ingest-coverage.py"


def _run(tmp: Path, manifest_lines: list[dict] | None) -> dict | str:
    if manifest_lines is not None:
        man = tmp / "manifest.jsonl"
        man.write_text("\n".join(json.dumps(r) for r in manifest_lines))
        env_manifest = str(man)
    else:
        env_manifest = str(tmp / "absent.jsonl")
    env = {**os.environ, "LIMEN_ROOT": str(tmp), "LIMEN_INGEST_MANIFEST": env_manifest}
    r = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, timeout=60, env=env)
    assert r.returncode == 0, r.stderr
    cov = tmp / "logs" / "ingest-coverage.json"
    return json.loads(cov.read_text()) if cov.exists() else r.stdout


def test_counts_sources_and_flags_gaps(tmp_path: Path):
    manifest = [
        {"source": "claude", "atom_count": 0, "mtime": "2026-06-10T00:00:00+00:00"},
        {"source": "chatgpt", "atom_count": 0, "mtime": "2026-06-11T00:00:00+00:00"},
        {"source": "gemini", "atom_count": 0, "mtime": "2026-06-11T00:00:00+00:00"},
    ]
    snap = _run(tmp_path, manifest)
    assert snap["blobs"] == 3 and snap["sources"] == 3
    assert 0 < snap["coverage_pct"] < 100, "not 100% — known sources still lack adapters"
    # the honest gaps must be surfaced, not hidden
    for gap in ("copilot", "ollama", "workbench", "perplexity"):
        assert gap in snap["missing_adapters"]


def test_fails_open_when_manifest_absent(tmp_path: Path):
    out = _run(tmp_path, None)
    assert isinstance(out, str) and "no manifest" in out, "absent manifest → graceful, not a crash"


def test_malformed_atom_count_falls_back(tmp_path: Path):
    manifest = [
        {"source": "claude", "atom_count": "bad", "mtime": "2026-06-10T00:00:00+00:00"},
        {"source": ["opencode"], "atom_count": True, "mtime": "2026-06-11T00:00:00+00:00"},
    ]

    snap = _run(tmp_path, manifest)

    assert snap["atoms_extracted"] == 0
    assert snap["blobs"] == 2
    assert snap["sources"] == 2
