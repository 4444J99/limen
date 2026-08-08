from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts" / "check-lifecycle.py"
REGISTRY = ROOT / "institutio" / "governance" / "lifecycle.yaml"


def test_lifecycle_registry_offline_predicate_is_green() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECK), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "literal debt=25" in result.stdout


def test_lifecycle_capabilities_and_draft_owner_are_declared() -> None:
    registry = yaml.safe_load(REGISTRY.read_text())
    dispositions = registry["dispositions"]
    merge_eligible = [name for name, row in dispositions.items() if row["merge_eligible"]]
    lever_ids = {row["id"] for row in json.loads((ROOT / "his-hand-levers.json").read_text())["levers"]}

    assert merge_eligible == ["lifecycle:delivery"]
    assert registry["cohorts"]["draft"]["default_disposition"] is None
    assert registry["cohorts"]["draft"]["owner_lever"] in lever_ids
    assert all(row["ratchet"] in registry["ratchets"] for row in registry["consumers"].values())
