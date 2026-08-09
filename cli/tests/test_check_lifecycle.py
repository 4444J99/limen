from __future__ import annotations

import hashlib
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
    assert registry["cohorts"]["dependabot"]["arm_decision"]["outcome"] == "arm"
    assert registry["cohorts"]["dependabot"]["arm_decision"]["accepted_receipt"]["disposition"] == "lifecycle:delivery"
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
        repositories_probe=lambda _ledger, _rows: {"organvm/example"},
    )

    literal_debt = sum(registry["literal_baseline"].values())
    unarmed_ratchets = sum(value is False for value in registry["ratchets"].values())
    assert unreachable == ledger["open_pr_count"] + literal_debt + unarmed_ratchets
    assert module.failures == []


def test_delivery_without_admission_evidence_is_unreachable() -> None:
    module = _load_check_module()
    dispositions = {"lifecycle:delivery": {"merge_eligible": True}}
    row = {
        "lifecycle_disposition": "lifecycle:delivery",
        "lifecycle_disposition_source": "label",
        "lifecycle_label_matches": ["lifecycle:delivery"],
    }

    assert module.mechanically_unreachable_count([row], dispositions) == 1


def test_cohort_selector_schema_is_closed_and_covered() -> None:
    module = _load_check_module()
    registry = yaml.safe_load(REGISTRY.read_text())
    registry["cohorts"]["draft"]["selector"] = {"draft": False}
    registry["cohorts"]["all"]["selector"] = {"all": True, "private": False}

    module.validate_cohorts(registry, set(registry["dispositions"]))

    assert any("draft cohort selector must be exactly" in failure for failure in module.failures)
    assert any("all cohort selector must be exactly" in failure for failure in module.failures)


def test_new_consumer_requires_zero_initial_baseline() -> None:
    module = _load_check_module()
    registry = yaml.safe_load(REGISTRY.read_text())
    registry["consumers"]["new-consumer"] = {
        "path": "scripts/check-lifecycle.py",
        "derives": ["labels"],
        "loader_markers": ["lifecycle.yaml"],
        "ratchet": "new_consumer_derives",
    }
    registry["ratchets"]["new_consumer_derives"] = False
    registry["literal_baseline"]["scripts/check-lifecycle.py"] = 1

    module.validate_consumers(registry, set(registry["dispositions"]))

    assert any("new consumer requires an explicit zero" in failure for failure in module.failures)


def test_preservation_ceiling_cannot_regrow_from_previous_registry(monkeypatch) -> None:
    module = _load_check_module()
    registry = yaml.safe_load(REGISTRY.read_text())
    registry["live_baseline"]["preservation_materialization_missing_labels"] = 125
    monkeypatch.setattr(
        module,
        "previous_registry",
        lambda: {
            "live_baseline": {
                "preservation_materialization_missing_labels": 124,
            }
        },
    )

    module.measure_unreachable(
        registry,
        metadata_probe=lambda _repositories, _dispositions: 0,
        rows_probe=lambda payload: payload["pull_requests"],
        repositories_probe=lambda _ledger, _rows: {"organvm/example"},
    )

    assert any("ceiling regrew" in failure for failure in module.failures)


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
            "lifecycle_label_matches": ["lifecycle:delivery"],
            "admission": {
                "draft": False,
                "mergeable": True,
                "required_checks": "green",
                "conflicts": "none",
            },
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


def test_private_redaction_accepts_unredacted_runtime_coordinates(tmp_path: Path) -> None:
    module = _load_check_module()
    private_key = hashlib.sha256(b"secret/private#7").hexdigest()
    ledger = {
        "generated_at": "2026-08-08T12:00:00Z",
        "open_pr_count": 2,
        "pull_requests": [
            {"private": True, "repository": None, "number": None, "pr_key": private_key},
            {"private": False, "repository": "organvm/public", "number": 1},
        ],
    }
    facts = {
        "exhaustive": True,
        "generated_at": ledger["generated_at"],
        "open_pr_count": ledger["open_pr_count"],
        "pull_requests": [
            {"private": True, "repository": "secret/private", "number": 7},
            {"private": False, "repository": "organvm/public", "number": 1},
        ],
    }
    facts_path = tmp_path / "gitvs-pr-debt-facts.json"
    facts_path.write_text(json.dumps(facts), encoding="utf-8")

    rows = module._complete_census_rows(ledger, facts_path=facts_path)

    assert rows == facts["pull_requests"]
    assert module.failures == []


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


def test_preservation_derivation_contract_is_required() -> None:
    module = _load_check_module()
    registry = yaml.safe_load(REGISTRY.read_text())
    registry["dispositions"]["lifecycle:preservation"]["derived_from"]["materialize"] = False

    module.validate_dispositions(registry)

    assert any("derived_from.materialize must be true" in failure for failure in module.failures)


def test_armed_cohort_requires_a_matching_arm_receipt() -> None:
    module = _load_check_module()
    registry = yaml.safe_load(REGISTRY.read_text())
    registry["cohorts"]["dependabot"].pop("arm_decision")

    module.validate_cohorts(registry, set(registry["dispositions"]))

    assert any("explicit arm outcome and accepted receipt" in failure for failure in module.failures)


def test_consumer_markers_ignore_comments_and_docstrings() -> None:
    module = _load_check_module()
    markers, lifecycle_literals = module._source_markers(
        '"""lifecycle:legacy lifecycle.yaml"""\n'
        "# lifecycle:comment\n"
        'value = "lifecycle:legacy"\n'
        "name = lifecycle_name\n"
        'path = "lifecycle.yaml"\n'
    )

    assert "lifecycle.yaml" in markers
    assert "lifecycle_name" in markers
    assert lifecycle_literals == {"lifecycle:legacy"}


def test_complete_estate_repository_census_reconciles_connections(tmp_path: Path) -> None:
    module = _load_check_module()
    source_report = {
        "exhaustive": True,
        "generated_at": "2026-08-08T19:14:15.797769Z",
        "content_sha256": "tracked-estate-sha",
    }
    facts = {
        "source_report": source_report,
        "summary": {"repository_count": 1},
        "cursors": [
            {"repository": "organvm/example", "kind": kind, "exhaustive": True, "error": None}
            for kind in ("pull_requests", "issues", "branches", "checks")
        ],
    }
    facts_path = tmp_path / "github-estate-census-facts.json"
    facts_path.write_text(json.dumps(facts))
    tracked_path = tmp_path / "github-estate-census.json"
    tracked_path.write_text(json.dumps({"source_report": source_report}))

    assert module._complete_estate_repositories(
        facts_path=facts_path,
        tracked_path=tracked_path,
    ) == {"organvm/example"}
    assert module.failures == []


def test_lifecycle_ideal_probe_is_reciprocal() -> None:
    module = _load_check_module()
    registry = yaml.safe_load(REGISTRY.read_text())
    ideals = yaml.safe_load((ROOT / "institutio" / "governance" / "ideal-forms.yaml").read_text())
    ideals["ideals"]["IF-PR-LIFECYCLE"]["probe"]["extract"] = "wrong: ([0-9]+)"
    module.load_yaml = lambda _path: ideals

    module.validate_self_reference(registry)

    assert any("probe.extract" in failure for failure in module.failures)
