from __future__ import annotations

import importlib.util
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
    delivery = dispositions["lifecycle:delivery"]
    assert delivery["admits"] == {
        "draft": False,
        "mergeable": True,
        "required_checks": "green",
        "conflicts": "none",
    }
    assert registry["cohort_precedence"][0] == "draft"
    assert registry["cohort_precedence"][1] == "archived-repo"
    assert registry["cohort_precedence"][-1] == "all"
    assert registry["cohorts"]["draft"]["default_disposition"] is None
    assert registry["cohorts"]["draft"]["owner_lever"] in lever_ids
    assert registry["cohorts"]["archived-repo"]["default_disposition"] == "lifecycle:blocked"
    assert registry["cohorts"]["dependabot"]["default_disposition"] == "lifecycle:blocked"
    assert registry["cohorts"]["dependabot"]["owner_lever"] == "L-DEPENDABOT-DELIVERY-ARM"
    assert registry["cohorts"]["dependabot"]["armed_disposition"] == "lifecycle:delivery"
    assert all(row["ratchet"] in registry["ratchets"] for row in registry["consumers"].values())
    assert all(row["loader_markers"] for row in registry["consumers"].values())
    assert isinstance(registry["ratchets"]["estate_yaml_derives"], bool)


def _load_check_module():
    spec = importlib.util.spec_from_file_location("check_lifecycle_test", CHECK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lifecycle_measure_includes_every_unwritten_disposition() -> None:
    module = _load_check_module()
    registry = yaml.safe_load(REGISTRY.read_text())

    unreachable = module.measure_unreachable(
        registry,
        metadata_probe=lambda _repositories, _dispositions: 0,
    )

    assert unreachable == 145
    assert module.failures == []

