from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts" / "positioning-p14-control-plane.py"
MANIFEST = ROOT / "institutio" / "positioning" / "p14" / "control-plane.json"
LEDGER = ROOT / "institutio" / "positioning" / "p14" / "dependency-ledger.json"
OPERATIONS = ROOT / "institutio" / "positioning" / "p14" / "operations.json"
FIXTURE = ROOT / "cli" / "tests" / "fixtures" / "positioning-p14" / "synthetic-cycle.json"
OPERATION_FIXTURE = ROOT / "cli" / "tests" / "fixtures" / "positioning-p14" / "operational-cycle.json"


def _load():
    spec = importlib.util.spec_from_file_location("positioning_p14_control_plane_uut", MODULE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_contract_covers_every_p14_stage_and_refuses_predecessor_replay():
    module = _load()
    contract = module.load_contract(MANIFEST)

    assert set(contract["stage_order"]) == set(module.WORK_IDS)
    assert contract["stage_order"][-1] == "PSP-P14-W09"
    assert contract["predecessor_policy"] == {
        "mode": "receipt-only",
        "execute_commands": False,
        "description": "Consume current durable receipts; never replay a predecessor merely to accumulate reassurance.",
    }
    assert len(contract["events"]) == 18
    assert len(contract["metrics"]) == 9
    assert contract["schema_version"] == "limen.positioning_p14_control_plane.v3"
    assert set(contract["public_evidence_contract"]["deny_keys"]) == module.EXPECTED_DENY_KEYS


def test_dependency_ledger_binds_full_dag_assignments_and_current_frontier():
    module = _load()
    contract = module.load_contract(MANIFEST)
    ledger = module.load_dependency_ledger(LEDGER, contract)
    report = module.dependency_report(ledger)

    assert [row["chunk_id"] for row in ledger["predecessor_chunks"]] == list(module.PREDECESSOR_CHUNK_IDS)
    assert len(ledger["terminal_nodes"]) == 23
    assert report["predecessor_blocker_count"] == 9
    assert report["execution_frontier"] == [
        {
            "work_id": "PSP-P03-W07",
            "issue": "https://github.com/organvm/limen/issues/2188",
            "state": "open",
            "assignment": {"slug": "gpt-5.4-mini", "effort": "low"},
            "acceptance_boundary": "Five genuine independent target-like readers; model, author, coached, or fabricated responses do not count.",
        }
    ]
    assert report["formal_execution_frontier"] == report["execution_frontier"]
    assert [row["chunk_id"] for row in report["reversible_preparation_frontier"]] == [
        f"PSP-C{number:02d}" for number in range(4, 13)
    ]
    assert all(row["counts_as_closure"] is False for row in report["reversible_preparation_frontier"])
    assert all(row["pull_request"] and row["branch"] for row in report["reversible_preparation_frontier"])
    assert report["frontier_invariant"] == {
        "independent": True,
        "formal_gate_suppresses_reversible_preparation": False,
        "owner_branches_or_pull_requests_count_as_closure": False,
    }
    assert ledger["predecessor_chunks"][-1]["evidence"] == [
        {
            "target": "limen",
            "pull_request": 2319,
            "head": "db0d991af5bfbfdec19e9fa3b0f5a89d9337e114",
        }
    ]
    assert all(row["counts_as_closure"] is False for row in ledger["predecessor_chunks"])
    assert all(row["counts_as_closure"] is False for row in ledger["p14_stages"])


def test_open_formal_reader_gate_cannot_empty_reversible_preparation_frontier():
    module = _load()
    contract = module.load_contract(MANIFEST)
    ledger = module._load_json(LEDGER)

    assert ledger["predecessor_chunks"][0]["frontier_work"][0]["work_id"] == "PSP-P03-W07"
    ledger["preparation_owners"] = []
    with pytest.raises(module.P14Error, match="canonical C04-C12 order"):
        module.validate_dependency_ledger(ledger, contract)


def test_dependency_ledger_fails_closed_on_registry_assignment_drift():
    module = _load()
    contract = module.load_contract(MANIFEST)
    ledger = module._load_json(LEDGER)
    ledger["p14_stages"][-1]["assignment"]["effort"] = "max"
    with pytest.raises(module.P14Error, match="PSP-P14-W09 dependency, issue, assignment, or closure drift"):
        module.validate_dependency_ledger(ledger, contract)


def test_synthetic_cycle_exercises_return_loops_without_claiming_live_outcomes():
    module = _load()
    contract = module.load_contract(MANIFEST)
    result = module.run_synthetic(contract, module._load_json(FIXTURE))

    assert result["status"] == "synthetic-pass"
    assert result["executed_predecessor_commands"] == []
    assert result["reused_predecessor_receipts"] == [
        {
            "work_id": "PSP-P00-W07",
            "receipt_sha256": "8ae84e77d685aacbf18e70a24cb3fd4e07f07162121a24471f56c6853e48619c",
        }
    ]
    assert result["stages"]["PSP-P14-W01"]["metrics"]["qualified_demand_rate"]["value"] == 0.5
    assert result["stages"]["PSP-P14-W02"]["live_receipts_observed"] == 0
    assert result["stages"]["PSP-P14-W03"]["live_receipts_observed"] == 0
    assert result["stages"]["PSP-P14-W04"]["live_receipts_observed"] == 0
    assert result["stages"]["PSP-P14-W09"]["status"] == "synthetic-pass"
    assert "Omega" in result["not_evidence_for"]
    assert "real client outcomes" in result["not_evidence_for"]


def test_claim_incident_quarantines_every_dependency_before_corrected_restore():
    module = _load()
    contract = module.load_contract(MANIFEST)
    result = module.run_synthetic(contract, module._load_json(FIXTURE))
    incident = result["stages"]["PSP-P14-W05"]

    assert incident["quarantined_surfaces"] == [
        "surface-portfolio-fixture",
        "surface-profile-fixture",
    ]
    assert incident["blocked_republish"] is True
    assert incident["corrected_evidence"]["version"] == "evidence-v2"
    assert incident["timeline"].index("republish-blocked") < incident["timeline"].index("evidence-corrected")


def test_release_recovery_restores_exact_release_and_capture_owner():
    module = _load()
    contract = module.load_contract(MANIFEST)
    result = module.run_synthetic(contract, module._load_json(FIXTURE))
    recovery = result["stages"]["PSP-P14-W06"]

    assert recovery["before_release_ids"] == recovery["restored_release_ids"]
    assert recovery["bad_release_ids"] != recovery["restored_release_ids"]
    assert recovery["capture_continuity"] is True
    assert set(recovery["health_checks"].values()) == {"healthy"}


def test_feedback_preserves_history_and_leaves_real_and_human_proof_open():
    module = _load()
    contract = module.load_contract(MANIFEST)
    result = module.run_synthetic(contract, module._load_json(FIXTURE))
    sales = result["stages"]["PSP-P14-W07"]
    delivery = result["stages"]["PSP-P14-W08"]

    assert sales["outcome_ids"] == sales["retained_outcome_ids"]
    assert sales["before_offer_version"] != sales["after_offer_version"]
    assert sales["human_gate"] == {"gate_id": "HG-PRICE-ANCHORS", "status": "pending"}
    assert sales["real_demand_claimed"] is False
    assert delivery["outcome_receipts_preserved"] is True
    assert delivery["real_delivery_claimed"] is False
    assert delivery["real_operator_outcome_claimed"] is False
    assert {item["outcome_id"] for item in delivery["portfolio_impacts"]} == {
        item["outcome_id"] for item in delivery["outcomes"]
    }


def test_two_pass_verifier_requires_distinct_observations_of_one_digest():
    module = _load()
    contract = module.load_contract(MANIFEST)
    result = module.run_synthetic(contract, module._load_json(FIXTURE))
    pair = result["stages"]["PSP-P14-W09"]["pair"]

    verified = module.verify_omega_pair(pair, required_scope="synthetic")
    assert verified["status"] == "pass"
    assert verified["observed_at"][0] != verified["observed_at"][1]

    repeated = deepcopy(pair)
    repeated["passes"][1]["observed_at"] = repeated["passes"][0]["observed_at"]
    with pytest.raises(module.P14Error, match="distinct observations"):
        module.verify_omega_pair(repeated, required_scope="synthetic")

    drifted = deepcopy(pair)
    drifted["passes"][1]["state_digest"] = "f" * 64
    with pytest.raises(module.P14Error, match="digests differ"):
        module.verify_omega_pair(drifted, required_scope="synthetic")

    with pytest.raises(module.P14Error, match="synthetic evidence cannot satisfy live Omega"):
        module.verify_omega_pair(pair, required_scope="live")


def test_live_two_pass_requires_canonical_clean_passes_and_two_receipts():
    module = _load()
    digest = "a" * 64

    def passing(number: int, observed_at: str):
        return {
            "schema_version": module.OMEGA_PASS_SCHEMA,
            "status": "pass",
            "pass": number,
            "state_digest": digest,
            "observed_at": observed_at,
            "ok": True,
            "parity": {
                "expected": 127,
                "observed": 127,
                "missing": [],
                "orphan": [],
                "drift": [],
                "ok": True,
            },
            "open": [],
            "verified_receipts": 126,
            "failures": [],
        }

    pair = {
        "schema_version": module.PAIR_SCHEMA,
        "scope": "live",
        "passes": [
            passing(1, "2026-08-12T12:00:00Z"),
            passing(2, "2026-08-12T12:01:00Z"),
        ],
        "evidence_urls": ["https://example.test/pass/1", "https://example.test/pass/2"],
    }
    assert module.verify_omega_pair(pair, required_scope="live")["state_digest"] == digest

    missing_parity = deepcopy(pair)
    del missing_parity["passes"][1]["parity"]
    with pytest.raises(module.P14Error, match="missing canonical live fields"):
        module.verify_omega_pair(missing_parity, required_scope="live")

    reversed_pair = deepcopy(pair)
    reversed_pair["passes"][1]["observed_at"] = "2026-08-12T11:59:00Z"
    with pytest.raises(module.P14Error, match="strictly ordered"):
        module.verify_omega_pair(reversed_pair, required_scope="live")


def test_terminal_predicate_names_every_missing_external_outcome():
    module = _load()
    contract = module.load_contract(MANIFEST)
    report = module.terminal_report(contract, {})

    assert report["status"] == "blocked"
    assert report["terminal"] is False
    assert report["p14_missing_count"] == len(contract["terminal_requirements"])
    assert report["p14_missing_count"] == 23
    assert report["predecessor_blocker_count"] == 9
    assert report["missing_count"] == 32
    assert {item["code"] for item in report["missing_external_outcomes"]} == {
        requirement["code"] for requirement in contract["terminal_requirements"]
    }
    assert all(item["owner"] and item["required"] and item["observed"] for item in report["missing_external_outcomes"])
    assert report["next_terminal_predicate"] == ("python3 scripts/positioning-program.py --omega --require-two-pass")


def test_time_based_receipts_must_be_distinct_and_consecutive():
    module = _load()
    contract = module.load_contract(MANIFEST)
    requirement = next(
        item for item in contract["terminal_requirements"] if item["code"] == "WEEKLY_LIVE_CYCLES_MISSING"
    )
    records = [
        {
            "scope": "live",
            "period_start": period,
            "decision": "keep",
            "owner": "fixture-owner",
            "next_predicate": "fixture-predicate",
            "evidence_url": f"https://example.test/review/{index}",
        }
        for index, period in enumerate(("2026-01-01", "2026-01-08", "2026-01-15", "2026-01-22"), start=1)
    ]

    assert module._valid_records(records, requirement) == (True, "4/4 valid")
    records[3]["period_start"] = "2026-01-29"
    valid, reason = module._valid_records(records, requirement)
    assert valid is False
    assert "not distinct consecutive weekly periods" in reason

    monthly_requirement = next(
        item for item in contract["terminal_requirements"] if item["code"] == "MONTHLY_LIVE_CYCLES_MISSING"
    )
    monthly = [
        {
            "scope": "live",
            "period_start": period,
            "verdict": "pass",
            "unowned_stale_claims": 0,
            "unowned_broken_links": 0,
            "unowned_private_leaks": 0,
            "unowned_surface_parity_defects": 0,
            "evidence_url": f"https://example.test/monthly/{index}",
        }
        for index, period in enumerate(("2026-01-01", "2026-02-01"), start=1)
    ]
    assert module._valid_records(monthly, monthly_requirement) == (True, "2/2 valid")
    monthly[1]["unowned_private_leaks"] = 1
    valid, reason = module._valid_records(monthly, monthly_requirement)
    assert valid is False
    assert "unowned truth/link/privacy/parity defect" in reason


def test_terminal_drill_receipts_hold_correction_and_exact_restore_semantics():
    module = _load()
    contract = module.load_contract(MANIFEST)
    requirements = {item["code"]: item for item in contract["terminal_requirements"]}
    claim = {
        "status": "pass",
        "quarantined_surfaces": ["surface-1"],
        "blocked_republish": True,
        "corrected_evidence": {"status": "verified"},
        "evidence_url": "https://example.test/claim-drill",
    }
    release = {
        "status": "pass",
        "resolved_repositories": ["fixture/repository-one", "fixture/repository-two"],
        "before_release_ids": ["good-one", "good-two"],
        "bad_release_ids": ["bad-one", "bad-two"],
        "restored_release_ids": ["good-one", "good-two"],
        "health_checks": {"repository-one:surface": "healthy", "repository-two:surface": "healthy"},
        "capture_continuity": True,
        "evidence_url": "https://example.test/release-drill",
    }

    assert module._valid_record(claim, requirements["CLAIM_INCIDENT_DRILL_MISSING"]) == (True, "valid")
    assert module._valid_record(release, requirements["RELEASE_RECOVERY_DRILL_MISSING"]) == (True, "valid")

    claim["blocked_republish"] = False
    assert module._valid_record(claim, requirements["CLAIM_INCIDENT_DRILL_MISSING"])[0] is False
    release["restored_release_ids"] = ["different"]
    assert module._valid_record(release, requirements["RELEASE_RECOVERY_DRILL_MISSING"])[0] is False


def test_commercial_terminal_requires_paid_receipt_or_five_documented_no_outcomes():
    module = _load()
    contract = module.load_contract(MANIFEST)
    requirement = next(
        item for item in contract["terminal_requirements"] if item["code"] == "COMMERCIAL_SUCCESS_OUTCOME_MISSING"
    )
    record = {
        "status": "validated",
        "scope": "live",
        "mode": "documented_no",
        "outcome_ids": [f"outcome-{index}" for index in range(5)],
        "evidence_url": "https://example.test/commercial-outcome",
    }

    assert module._valid_record(record, requirement) == (True, "valid")
    record["outcome_ids"].pop()
    valid, reason = module._valid_record(record, requirement)
    assert valid is False
    assert "requires five outcome receipts" in reason


def test_program_omega_receipt_binds_digest_head_time_and_output():
    module = _load()
    contract = module.load_contract(MANIFEST)
    requirement = next(
        item for item in contract["terminal_requirements"] if item["code"] == "PROGRAM_OMEGA_RECEIPT_MISSING"
    )
    record = {
        "status": "pass",
        "scope": "live",
        "command": "python3 scripts/positioning-program.py --omega --require-two-pass",
        "exit_code": 0,
        "output_sha256": "a" * 64,
        "state_digest": "b" * 64,
        "observed_head": "c" * 40,
        "observed_at": "2026-08-12T12:02:00Z",
        "evidence_url": "https://example.test/program-omega",
    }
    assert module._valid_record(record, requirement) == (True, "valid")
    record["observed_head"] = "short"
    assert module._valid_record(record, requirement)[0] is False


def test_terminal_cross_binds_program_receipt_to_pair_digest_and_time():
    module = _load()
    contract = module.load_contract(MANIFEST)
    digest = "a" * 64

    def passing(number: int, observed_at: str):
        return {
            "schema_version": module.OMEGA_PASS_SCHEMA,
            "status": "pass",
            "pass": number,
            "state_digest": digest,
            "observed_at": observed_at,
            "ok": True,
            "parity": {
                "expected": 127,
                "observed": 127,
                "missing": [],
                "orphan": [],
                "drift": [],
                "ok": True,
            },
            "open": [],
            "verified_receipts": 126,
            "failures": [],
        }

    evidence = {
        "schema_version": module.EVIDENCE_SCHEMA,
        "scope": "live",
        "omega_pair": {
            "schema_version": module.PAIR_SCHEMA,
            "scope": "live",
            "passes": [
                passing(1, "2026-08-12T12:00:00Z"),
                passing(2, "2026-08-12T12:01:00Z"),
            ],
            "evidence_urls": ["https://example.test/pass/1", "https://example.test/pass/2"],
        },
        "program_omega": {
            "status": "pass",
            "scope": "live",
            "command": "python3 scripts/positioning-program.py --omega --require-two-pass",
            "exit_code": 0,
            "output_sha256": "b" * 64,
            "state_digest": "c" * 64,
            "observed_head": "d" * 40,
            "observed_at": "2026-08-12T12:02:00Z",
            "evidence_url": "https://example.test/program-omega",
        },
    }
    report = module.terminal_report(contract, evidence)
    missing = {row["code"]: row for row in report["missing_external_outcomes"]}
    assert "does not match the verified two-pass digest" in missing["PROGRAM_OMEGA_RECEIPT_MISSING"]["observed"]

    evidence["program_omega"]["state_digest"] = digest
    evidence["program_omega"]["observed_at"] = "2026-08-12T11:59:00Z"
    report = module.terminal_report(contract, evidence)
    missing = {row["code"]: row for row in report["missing_external_outcomes"]}
    assert "predates the second verified pass" in missing["PROGRAM_OMEGA_RECEIPT_MISSING"]["observed"]


def test_public_evidence_denylist_blocks_nested_private_keys():
    module = _load()
    contract = module.load_contract(MANIFEST)
    evidence = {
        "schema_version": module.EVIDENCE_SCHEMA,
        "scope": "live",
        "nested": {"accessToken": "must-not-be-public"},
    }
    report = module.terminal_report(contract, evidence)
    assert report["evidence_envelope"]["public_safe"] is False
    assert report["evidence_envelope"]["privacy_violations"] == ["nested.accessToken"]
    assert report["privacy_blocker_count"] == 1


def test_preflight_is_green_only_when_terminal_truth_remains_blocked():
    module = _load()
    contract = module.load_contract(MANIFEST)
    result = module.preflight(contract, module._load_json(FIXTURE), {})

    assert result["status"] == "pass"
    assert result["synthetic_fixture"] == "synthetic-pass"
    assert result["predecessor_commands_executed"] == []
    assert result["terminal_status"] == "blocked"
    assert len(result["missing_external_outcomes"]) == 23
    assert result["predecessor_blocker_count"] == 9
    assert result["blocking_total"] == 32


def test_operations_contract_binds_every_schema_template_and_runner_mapping():
    module = _load()
    operations = module.load_operations(OPERATIONS)

    assert set(operations["schemas"]) == module.EXPECTED_OPERATION_SCHEMAS
    assert {row["id"] for row in operations["runners"]} == module.EXPECTED_RUNNER_IDS
    assert all(row["counts_as_closure"] is False for row in operations["runners"])

    drifted = deepcopy(operations)
    drifted["schemas"]["weekly_review"] = drifted["schemas"]["monthly_audit"]
    with pytest.raises(module.P14Error, match="schema path mapping drift"):
        module.validate_operations_contract(drifted)

    remapped = deepcopy(operations)
    next(row for row in remapped["runners"] if row["id"] == "demand_projection")["work_id"] = "PSP-P14-W01"
    with pytest.raises(module.P14Error, match="demand_projection mapping drift"):
        module.validate_operations_contract(remapped)


def test_operational_fixture_executes_every_reversible_stage_without_live_or_closure_claims():
    module = _load()
    contract = module.load_contract(MANIFEST)
    operations = module.load_operations(OPERATIONS)
    result = module.run_operational_fixture(contract, operations, module._load_json(OPERATION_FIXTURE))

    assert set(result["stages"]) == set(module.WORK_IDS)
    assert result["status"] == "synthetic-pass"
    assert result["terminal"] is False
    assert result["counts_as_live_outcomes"] is False
    assert result["counts_as_closure"] is False
    assert result["executed_predecessor_commands"] == []
    assert result["stages"]["PSP-P14-W01"]["metrics"]["qualified_demand_rate"]["value"] == 0.5
    assert len(result["stages"]["PSP-P14-W06"]["resolved_repositories"]) == 2
    assert result["stages"]["PSP-P14-W09"]["counts_as_live_omega"] is False
    assert "Omega" in result["not_evidence_for"]


def test_operational_fixture_rejects_missing_fields_nested_live_scope_and_head_drift():
    module = _load()
    contract = module.load_contract(MANIFEST)
    operations = module.load_operations(OPERATIONS)
    fixture = module._load_json(OPERATION_FIXTURE)

    missing = deepcopy(fixture)
    del missing["event_bundle"]
    with pytest.raises(module.P14Error, match="missing required fields"):
        module.run_operational_fixture(contract, operations, missing)

    mixed = deepcopy(fixture)
    mixed["weekly_review"]["scope"] = "live"
    mixed["weekly_review"]["evidence_url"] = "https://example.test/receipt"
    with pytest.raises(module.P14Error, match="weekly_review must remain synthetic"):
        module.run_operational_fixture(contract, operations, mixed)

    head_drift = deepcopy(fixture)
    head_drift["omega_observations"][1]["observed_head"] = "c" * 40
    with pytest.raises(module.P14Error, match="exact head mismatch"):
        module.run_operational_fixture(contract, operations, head_drift)


def test_metric_collector_recomputes_denominators_and_requires_live_source_receipts():
    module = _load()
    contract = module.load_contract(MANIFEST)
    operations = module.load_operations(OPERATIONS)
    bundle = module._load_json(OPERATION_FIXTURE)["event_bundle"]

    result = module.collect_metrics(contract, operations, bundle)
    metric = result["metrics"]["qualified_demand_rate"]
    assert metric["numerator"] == 1
    assert metric["denominator"] == 2
    assert metric["source"]["numerator"] == "qualification receipt"
    assert metric["decision_use"] and metric["guardrail"]
    assert result["counts_as_live_outcomes"] is False

    live = deepcopy(bundle)
    live["scope"] = "live"
    for event in live["events"]:
        event["scope"] = "live"
    with pytest.raises(module.P14Error, match="requires an HTTPS source_receipt_url"):
        module.collect_metrics(contract, operations, live)

    mixed = deepcopy(bundle)
    mixed["events"][0]["scope"] = "live"
    with pytest.raises(module.P14Error, match="scope differs"):
        module.collect_metrics(contract, operations, mixed)

    orphan_numerator = deepcopy(bundle)
    extra = deepcopy(next(event for event in orphan_numerator["events"] if event["type"] == "claim.current"))
    extra["event_id"] = "op-evt-extra-current"
    extra["entity_id"] = "claim-fixture-orphan"
    orphan_numerator["events"].append(extra)
    with pytest.raises(module.P14Error, match="not a subset"):
        module.collect_metrics(contract, operations, orphan_numerator)


def test_review_runners_are_replay_safe_and_never_self_certify_terminal_evidence():
    module = _load()
    operations = module.load_operations(OPERATIONS)
    fixture = module._load_json(OPERATION_FIXTURE)

    weekly = module.run_weekly_review(operations, fixture["weekly_review"])
    assert weekly["counts_as_live_cycle"] is False
    assert weekly["counts_as_terminal_evidence"] is False
    live_weekly = deepcopy(fixture["weekly_review"])
    live_weekly["scope"] = "live"
    live_weekly["evidence_url"] = "https://example.test/live-weekly-source"
    prepared_live_weekly = module.run_weekly_review(operations, live_weekly)
    assert prepared_live_weekly["source_scope_live"] is True
    assert prepared_live_weekly["counts_as_live_cycle"] is False
    assert prepared_live_weekly["counts_as_terminal_evidence"] is False
    replay = deepcopy(fixture["weekly_review"])
    replay["closed_work_ids"].append(replay["ready_work"][0]["work_id"])
    with pytest.raises(module.P14Error, match="replay already-closed work"):
        module.run_weekly_review(operations, replay)

    monthly = module.run_monthly_audit(operations, fixture["monthly_audit"])
    assert monthly["verdict"] == "pass"
    assert monthly["counts_as_terminal_evidence"] is False
    unowned = deepcopy(fixture["monthly_audit"])
    unowned["findings"]["privacy"][0]["status"] = "leak"
    unowned["findings"]["privacy"][0]["owner"] = None
    unowned["findings"]["privacy"][0]["next_predicate"] = None
    assert module.run_monthly_audit(operations, unowned)["verdict"] == "blocked"

    missing_packet = deepcopy(fixture["monthly_audit"])
    missing_packet["correction_packets"].pop()
    with pytest.raises(module.P14Error, match="lack correction packets"):
        module.run_monthly_audit(operations, missing_packet)

    quarterly = module.run_quarterly_decision(operations, fixture["quarterly_decision"])
    assert quarterly["prior_strategy_version"] != quarterly["proposed_strategy_version"]
    rollback_drift = deepcopy(fixture["quarterly_decision"])
    rollback_drift["proposed_strategy_version"] = rollback_drift["prior_strategy_version"]
    with pytest.raises(module.P14Error, match="distinct proposed version"):
        module.run_quarterly_decision(operations, rollback_drift)


def test_claim_and_multi_repository_release_drills_fail_closed_on_bad_restore():
    module = _load()
    contract = module.load_contract(MANIFEST)
    operations = module.load_operations(OPERATIONS)
    fixture = module._load_json(OPERATION_FIXTURE)

    claim = module.run_claim_incident(contract, operations, fixture["claim_incident"])
    assert claim["blocked_republish"] is True
    assert claim["counts_as_terminal_evidence"] is False
    same_evidence = deepcopy(fixture["claim_incident"])
    same_evidence["correction"]["version"] = same_evidence["claim"]["version"]
    with pytest.raises(module.P14Error, match="new evidence version"):
        module.run_claim_incident(contract, operations, same_evidence)

    recovery = module.run_release_recovery(contract, operations, fixture["release_recovery"])
    assert recovery["before_release_ids"] == recovery["restored_release_ids"]
    assert len(set(recovery["resolved_repositories"])) == 2
    duplicate = deepcopy(fixture["release_recovery"])
    duplicate["repositories"][1]["repository_id"] = duplicate["repositories"][0]["repository_id"]
    with pytest.raises(module.P14Error, match="duplicate release recovery repository"):
        module.run_release_recovery(contract, operations, duplicate)

    wrong_restore = deepcopy(fixture["release_recovery"])
    wrong_restore["repositories"][1]["restored_release_id"] = "not-the-known-green-release"
    with pytest.raises(module.P14Error, match="exactly restore"):
        module.run_release_recovery(contract, operations, wrong_restore)


def test_private_ledger_projection_is_public_safe_and_does_not_promote_synthetic_outcomes():
    module = _load()
    operations = module.load_operations(OPERATIONS)
    ledgers = module._load_json(OPERATION_FIXTURE)["private_ledgers"]

    for kind, private_key in (
        ("demand", "private_identity_ref"),
        ("delivery", "private_evidence_ref"),
        ("operator", "private_operator_ref"),
    ):
        projection = module.project_private_ledger(operations, kind, ledgers[kind])
        assert projection["counts_as_real_outcomes"] is False
        assert projection["counts_as_terminal_evidence"] is False
        assert private_key not in repr(projection)
        assert all(row["counts_as_terminal_evidence"] is False for row in projection["records"])

    live = deepcopy(ledgers["demand"])
    live["scope"] = "live"
    with pytest.raises(module.P14Error, match="requires an HTTPS evidence_url"):
        module.project_private_ledger(operations, "demand", live)


def test_evidence_envelope_preserves_scope_head_privacy_and_non_closure():
    module = _load()
    contract = module.load_contract(MANIFEST)
    operations = module.load_operations(OPERATIONS)
    operational = module.run_operational_fixture(contract, operations, module._load_json(OPERATION_FIXTURE))
    envelope = operational["evidence_envelope"]

    assert envelope["scope"] == "synthetic"
    assert envelope["counts_as_live_evidence"] is False
    assert envelope["counts_as_terminal_evidence"] is False
    assert envelope["counts_as_closure"] is False
    assert not module._privacy_violations(envelope, module.EXPECTED_DENY_KEYS)
    assert module.terminal_report(contract, envelope)["terminal"] is False

    source = {
        "schema_version": "limen.positioning_p14_evidence_source_bundle.v1",
        "scope": "synthetic",
        "observed_head": "a" * 40,
        "work_receipts": {},
        "review_receipts": {"weekly": [], "monthly": [], "quarterly": []},
        "private_ledgers": module._load_json(OPERATION_FIXTURE)["private_ledgers"],
        "omega_pair": {
            "schema_version": module.PAIR_SCHEMA,
            "scope": "synthetic",
            "observed_head": "c" * 40,
            "passes": [],
        },
    }
    with pytest.raises(module.P14Error, match="Omega pair exact head mismatch"):
        module.build_evidence_envelope(contract, operations, source)


def test_omega_observation_builder_requires_two_unchanged_exact_head_passes():
    module = _load()
    operations = module.load_operations(OPERATIONS)
    observations = module._load_json(OPERATION_FIXTURE)["omega_observations"]

    result = module.assemble_omega_pair(operations, observations)
    assert result["observed_head"] == "a" * 40
    assert result["counts_as_live_omega"] is False
    assert result["counts_as_terminal_evidence"] is False
    assert result["counts_as_closure"] is False

    drifted = deepcopy(observations)
    drifted[1]["observed_head"] = "c" * 40
    with pytest.raises(module.P14Error, match="one unchanged exact head"):
        module.assemble_omega_pair(operations, drifted)

    reversed_passes = list(reversed(deepcopy(observations)))
    with pytest.raises(module.P14Error, match="pass-1 then pass-2"):
        module.assemble_omega_pair(operations, reversed_passes)


def test_cli_exposes_and_dispatches_operational_modes(capsys):
    module = _load()

    assert module.main(["--frontiers"]) == 0
    frontiers = capsys.readouterr().out
    assert '"formal_execution_frontier"' in frontiers
    assert '"reversible_preparation_frontier"' in frontiers

    assert module.main(["--run-operational-fixture", str(OPERATION_FIXTURE)]) == 0
    operational = capsys.readouterr().out
    assert '"status": "synthetic-pass"' in operational

    demand = module._load_json(OPERATION_FIXTURE)["private_ledgers"]["demand"]
    temp_path = ROOT / "cli" / "tests" / "fixtures" / "positioning-p14" / "operational-cycle.json"
    assert demand["schema_version"] == "limen.positioning_p14_demand_private_ledger.v1"
    assert module.main(["--project-private-ledger", str(temp_path)]) == 2
    error = capsys.readouterr().err
    assert "requires --ledger-kind" in error
