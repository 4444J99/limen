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


def test_lifecycle_measure_counts_capability_and_conversion_debt() -> None:
    module = _load_check_module()
    registry = yaml.safe_load(REGISTRY.read_text())
    ledger = json.loads((ROOT / "docs" / "github-pr-debt-ledger.json").read_text())

    unreachable = module.measure_unreachable(
        registry,
        metadata_probe=lambda _repositories, _dispositions: 0,
        rows_probe=lambda payload: payload["pull_requests"],
    )

    literal_debt = sum(registry["literal_baseline"].values())
    unarmed_ratchets = sum(value is False for value in registry["ratchets"].values())
    assert unreachable == ledger["open_pr_count"] + literal_debt + unarmed_ratchets
    assert module.failures == []


def test_capability_ineligible_prs_are_mechanically_unreachable() -> None:
    module = _load_check_module()
    dispositions = {
        "lifecycle:delivery": {"merge_eligible": True},
        "lifecycle:blocked": {"merge_eligible": False},
    }
    rows = [
        {
            "lifecycle_disposition": "lifecycle:delivery",
            "lifecycle_disposition_source": "label",
        },
        {
            "lifecycle_disposition": "lifecycle:blocked",
            "lifecycle_disposition_source": "label",
        },
        {
            "lifecycle_disposition": "lifecycle:delivery",
            "lifecycle_disposition_source": "missing-label",
        },
    ]

    assert module.mechanically_unreachable_count(rows, dispositions) == 2


def test_private_redaction_requires_matching_runtime_facts(tmp_path: Path) -> None:
    module = _load_check_module()
    ledger = {
        "pull_requests": [
            {
                "private": True,
                "repository": None,
                "number": None,
            }
        ]
    }

    rows = module._complete_census_rows(ledger, facts_path=tmp_path / "missing-facts.json")

    assert rows is None
    assert any("private PR cohort is redacted" in failure for failure in module.failures)


def test_missing_canonical_consumer_is_rejected() -> None:
    module = _load_check_module()
    registry = yaml.safe_load(REGISTRY.read_text())
    registry["consumers"].pop("merge-drain")
    registry["literal_baseline"].pop("scripts/merge-drain.py")

    module.validate_consumers(registry, set(registry["dispositions"]))

    assert any("canonical lifecycle consumers are undeclared" in failure for failure in module.failures)


def test_armed_ratchet_cannot_reverse() -> None:
    module = _load_check_module()

    module.validate_ratchet_monotonicity(
        {"estate_yaml_derives": False},
        {"ratchets": {"estate_yaml_derives": True}},
    )

    assert any("estate_yaml_derives" in failure for failure in module.failures)


def test_surplus_lifecycle_label_is_metadata_drift(monkeypatch) -> None:
    module = _load_check_module()
    payload = {
        "data": {
            "r0": {
                "labels": {
                    "nodes": [
                        {
                            "name": "lifecycle:delivery",
                            "color": "0e8a16",
                            "description": "delivery",
                        },
                        {
                            "name": "lifecycle:legacy",
                            "color": "000000",
                            "description": "undeclared",
                        },
                    ]
                }
            }
        }
    }

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, json.dumps(payload), ""),
    )
    drift = module.live_label_metadata_drift(
        {"organvm/example"},
        {
            "lifecycle:delivery": {
                "label_color": "0e8a16",
                "description": "delivery",
            }
        },
    )

    assert drift == 1
