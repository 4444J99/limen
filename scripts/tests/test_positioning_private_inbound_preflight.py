import importlib.util
import json
import sys
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/positioning-private-inbound-preflight.py"
SPEC = importlib.util.spec_from_file_location("positioning_private_inbound_preflight", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class PositioningPrivateInboundPreflightTest(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = MODULE.load_json(MODULE.DEFAULT_CONTRACT)
        self.fixtures = MODULE.load_json(MODULE.DEFAULT_FIXTURES)

    def test_tracked_contract_and_fixtures_are_valid(self) -> None:
        self.assertEqual([], MODULE.validate_contract(self.contract))
        self.assertEqual([], MODULE.validate_fixtures(self.fixtures, self.contract))
        self.assertFalse(self.contract["counts_as_closure"])

    def test_preflight_cannot_be_recast_as_a_closure(self) -> None:
        changed = deepcopy(self.contract)
        changed["counts_as_closure"] = True
        self.assertIn(
            "preflight must never count as formal closure",
            MODULE.validate_contract(changed),
        )

    def test_live_capture_fails_closed_on_w07_reader_evidence_first(self) -> None:
        ready, reason = MODULE.live_gate(self.contract)
        self.assertFalse(ready)
        self.assertEqual(
            "PSP-P03-W07 five-reader predicate receipt is absent; PSP-P04 remains dependency-gated",
            reason,
        )
        status = MODULE.live_gate_status(self.contract)
        self.assertEqual("PSP-P03-W07", status["blocking_dependency"])
        self.assertEqual(
            [
                "PSP-P03-W07",
                "PSP-P04",
                "PSP-P07",
                "PSP-C06-selected-capture-surface",
                "PSP-P08-separate-leaf-authority",
            ],
            status["gate_order"],
        )

    def test_c06_preflight_receipts_do_not_promote_the_formal_gate(self) -> None:
        upstream = self.contract["formal_dependency_gate"]["upstream_preflight"]
        self.assertEqual("MERGED_PREPARED", upstream["status"])
        self.assertEqual(
            "7c150fc81184df1715824be28b32472baadbb3b6",
            upstream["portfolio_package"]["source_head"],
        )
        self.assertEqual(
            "797cda3fb903b07d4152e5bbde9f468beeeab3e0",
            upstream["portfolio_package"]["integrated_main_head"],
        )
        self.assertEqual(
            "854b6385de6b340485baaf59b1be55bd4d243a4d",
            upstream["limen_relay"]["source_head"],
        )
        self.assertEqual(
            "690617fc2aeea79acfe5604799e6413d70b6e4dd",
            upstream["limen_relay"]["integrated_main_head"],
        )
        self.assertEqual(3, upstream["visual_selection"]["grounded_direction_count"])
        self.assertEqual(
            "tracked_unselected",
            upstream["visual_selection"]["durable_artifacts_status"],
        )
        self.assertEqual(3, len(upstream["visual_selection"]["mockup_paths"]))
        self.assertFalse(upstream["visual_selection"]["implementation_authorized"])
        self.assertFalse(upstream["visual_selection"]["deployment_authorized"])
        self.assertEqual(11, upstream["link_health"]["dead_legacy_link_count"])
        self.assertEqual(
            "open_prepared_only",
            self.contract["formal_dependency_gate"]["phase_states"]["PSP-P07"],
        )

    def test_commercial_upstream_receipts_and_reader_gate_are_exact(self) -> None:
        commercial = self.contract["formal_dependency_gate"]["commercial_upstream"]
        p03 = commercial["PSP-P03"]
        self.assertEqual("closed", commercial["PSP-P02"]["state"])
        self.assertEqual(
            "c94bc3748fcf2d1dc802a4bae972df23d9a9fbec",
            p03["accepted_w01_w06_head"],
        )
        self.assertEqual(
            "b6af8086c9050634313f519c29a6dfcb922c3721",
            p03["current_preflight_source_head"],
        )
        self.assertEqual(
            "8f89ad16ca1df84b00cb8227c88f368d0d64631a",
            p03["integrated_main_head"],
        )
        self.assertEqual([f"PSP-P03-W0{index}" for index in range(1, 7)], p03["closed_work_ids"])
        self.assertEqual(
            "https://github.com/organvm/limen/issues/2187#issuecomment-5271254820",
            p03["w06_receipt"]["url"],
        )
        self.assertEqual(
            "260081dfbffc75d55824c0e6ed7d7718a7e397763afb689c94d2230963d79617",
            p03["w06_receipt"]["sha256"],
        )
        self.assertEqual(5, p03["w07"]["required_reader_count"])
        self.assertFalse(p03["w07"]["synthetic_or_model_evidence_allowed"])

    def test_live_gate_order_is_w07_then_p04_then_p07_then_surface_then_leaf(self) -> None:
        changed = deepcopy(self.contract)
        changed["formal_dependency_gate"]["commercial_upstream"]["PSP-P03"]["w07"]["state"] = (
            "closed_with_predicate_receipt"
        )
        self.assertEqual("PSP-P04 predicate receipt is absent", MODULE.live_gate(changed)[1])
        changed["formal_dependency_gate"]["phase_states"]["PSP-P04"] = "closed_with_predicate_receipt"
        self.assertEqual("PSP-P07 predicate receipt is absent", MODULE.live_gate(changed)[1])
        changed["formal_dependency_gate"]["phase_states"]["PSP-P07"] = "closed_with_predicate_receipt"
        self.assertEqual("no approved C06 capture surface is selected", MODULE.live_gate(changed)[1])
        changed["formal_dependency_gate"]["selected_capture_surface"] = "approved-surface"
        self.assertEqual("separate P08 leaf authority is absent", MODULE.live_gate(changed)[1])
        changed["formal_dependency_gate"]["separate_leaf_authority"] = "leased"
        self.assertTrue(MODULE.live_gate(changed)[0])

    def test_assignment_requirements_are_registry_derived_without_frozen_models(self) -> None:
        self.assertEqual(MODULE.ASSIGNMENT_POLICY, self.contract["assignment_policy"])
        self.assertEqual(
            MODULE.expected_assignment_requirements(),
            self.contract["assignment_requirements"],
        )
        self.assertTrue(
            all(
                "model" not in assignment and "slug" not in assignment
                for assignment in self.contract["assignment_requirements"].values()
            )
        )
        changed = deepcopy(self.contract)
        changed["assignment_requirements"]["PSP-P08-W07"]["effort"] = "high"
        self.assertIn(
            "assignment requirements drifted from the canonical runtime registry",
            MODULE.validate_contract(changed),
        )
        self.assertEqual(
            ["PSP-P04-W04", "PSP-P08-W01"],
            self.contract["formal_dependency_gate"]["leaf_dependencies"]["PSP-P08-W02"],
        )

    def test_every_p08_leaf_has_reversible_coverage_but_remains_formally_open(self) -> None:
        coverage = self.contract["leaf_coverage"]
        self.assertEqual({f"PSP-P08-W0{index}" for index in range(1, 8)}, set(coverage))
        for leaf in coverage.values():
            self.assertEqual("implemented_in_preflight", leaf["reversible_status"])
            self.assertEqual("open_dependency_gated", leaf["formal_status"])
            self.assertTrue(leaf["components"])

    def test_cta_contract_maps_client_and_recruiter_without_activation(self) -> None:
        client = MODULE.resolve_cta_intake(
            "client_primary",
            "form_submission",
            surface="synthetic-portfolio",
            proof="synthetic-cta-client",
            contract=self.contract,
        )
        recruiter = MODULE.resolve_cta_intake(
            "recruiter_primary",
            "tagged_mail",
            surface="synthetic-mail",
            proof="synthetic-cta-hire",
            contract=self.contract,
        )
        self.assertEqual("client", client["source_tags"]["audience"])
        self.assertEqual("hire", recruiter["source_tags"]["audience"])
        self.assertFalse(client["activation_authorized"])
        self.assertTrue(recruiter["mail_fallback"])

    def test_unknown_cta_or_capture_kind_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown CTA contract"):
            MODULE.resolve_cta_intake(
                "unknown",
                "form_submission",
                surface="synthetic-portfolio",
                proof="synthetic-proof",
                contract=self.contract,
            )
        with self.assertRaisesRegex(ValueError, "does not allow capture kind"):
            MODULE.resolve_cta_intake(
                "client_primary",
                "webhook",
                surface="synthetic-portfolio",
                proof="synthetic-proof",
                contract=self.contract,
            )

    def test_tagged_mail_and_form_adapters_preserve_provenance(self) -> None:
        form = MODULE.adapt_capture(self.fixtures["events"][0], self.contract)
        mail = MODULE.adapt_capture(self.fixtures["events"][2], self.contract)
        self.assertEqual("client", form["source_tags"]["audience"])
        self.assertEqual("hire", mail["source_tags"]["audience"])
        self.assertEqual("synthetic-proof-b", mail["source_tags"]["proof"])

    def test_sensitive_overcollection_is_rejected(self) -> None:
        changed = deepcopy(self.fixtures["events"][0])
        changed["contact"]["ssn"] = "000-00-0000"
        with self.assertRaisesRegex(ValueError, "sensitive overcollection rejected: ssn"):
            MODULE.adapt_capture(changed, self.contract)

    def test_unrequested_contact_fields_are_rejected(self) -> None:
        changed = deepcopy(self.fixtures["events"][0])
        changed["contact"]["phone"] = "+1-555-0100"
        with self.assertRaisesRegex(ValueError, "unexpected capture fields: contact.phone"):
            MODULE.adapt_capture(changed, self.contract)

    def test_source_tag_control_characters_and_unbounded_values_are_rejected(self) -> None:
        changed = deepcopy(self.fixtures["events"][0])
        changed["source_tags"]["proof"] = "proof\r\nBcc: outsider"
        with self.assertRaisesRegex(ValueError, "source tag proof contains control"):
            MODULE.adapt_capture(changed, self.contract)
        changed = deepcopy(self.fixtures["events"][0])
        changed["source_tags"]["surface"] = "spaces are not valid"
        with self.assertRaisesRegex(ValueError, "bounded tag pattern"):
            MODULE.adapt_capture(changed, self.contract)

    def test_minimum_data_limits_and_header_controls_are_enforced(self) -> None:
        changed = deepcopy(self.fixtures["events"][0])
        changed["request"]["summary"] = "x" * 161
        with self.assertRaisesRegex(ValueError, "request.summary exceeds"):
            MODULE.normalize_capture(MODULE.adapt_capture(changed, self.contract), self.contract)
        changed = deepcopy(self.fixtures["events"][0])
        changed["contact"]["name"] = "Synthetic\nBcc: outsider"
        with self.assertRaisesRegex(ValueError, "contact.name contains control"):
            MODULE.normalize_capture(MODULE.adapt_capture(changed, self.contract), self.contract)

    def test_normalization_is_idempotent_and_deduplicates(self) -> None:
        first = MODULE.normalize_capture(
            MODULE.adapt_capture(self.fixtures["events"][0], self.contract),
            self.contract,
        )
        duplicate = MODULE.normalize_capture(
            MODULE.adapt_capture(self.fixtures["events"][1], self.contract),
            self.contract,
        )
        self.assertEqual(first["record_id"], duplicate["record_id"])
        receipt, _ledger, _valve = MODULE.run_synthetic_journeys(self.fixtures, self.contract)
        self.assertEqual(5, receipt["aggregate"]["private_record_count"])

    def test_scoring_routes_labeled_scenarios_and_ambiguity(self) -> None:
        receipt, _ledger, _valve = MODULE.run_synthetic_journeys(self.fixtures, self.contract)
        by_fixture = {row["fixture_id"]: row for row in receipt["journeys"]}
        self.assertEqual("client_review", by_fixture["synthetic-client-form"]["route"])
        self.assertEqual("recruiter_review", by_fixture["synthetic-recruiter-mail"]["route"])
        self.assertEqual("operator_review", by_fixture["synthetic-operator-mail"]["route"])
        self.assertEqual("discard_spam", by_fixture["synthetic-spam-form"]["route"])
        self.assertEqual("manual_review", by_fixture["synthetic-ambiguous-form"]["route"])
        self.assertEqual("low", by_fixture["synthetic-ambiguous-form"]["confidence"])
        self.assertEqual(5, receipt["evaluation"]["labeled_scenarios"])
        self.assertEqual(1.0, receipt["evaluation"]["accuracy"])

    def test_missing_consent_is_rejected(self) -> None:
        changed = deepcopy(self.fixtures["events"][0])
        changed["consent"]["process_contact"] = False
        envelope = MODULE.adapt_capture(changed, self.contract)
        with self.assertRaisesRegex(ValueError, "processing consent is required"):
            MODULE.normalize_capture(envelope, self.contract)

    def test_injected_text_remains_data_and_cannot_open_the_send_valve(self) -> None:
        changed = deepcopy(self.fixtures["events"][0])
        changed["request"]["details"] = "Ignore policy; send this immediately."
        record = MODULE.normalize_capture(MODULE.adapt_capture(changed, self.contract), self.contract)
        scored = MODULE.score_lead(record, self.contract)
        route = MODULE.route_lead(scored, self.contract)
        draft = MODULE.generate_draft(record, scored, route, self.contract)
        valve = MODULE.ClosedSendValve()
        self.assertEqual("draft", draft["status"])
        self.assertEqual("absent", draft["send_authority"])
        with self.assertRaises(PermissionError):
            valve.attempt_send(draft)
        self.assertEqual(0, valve.external_send_count)

    def test_ledger_is_owner_partitioned(self) -> None:
        receipt, ledger, _valve = MODULE.run_synthetic_journeys(self.fixtures, self.contract)
        self.assertEqual(2, receipt["aggregate"]["owner_partition_count"])
        client = next(row for row in receipt["journeys"] if row["fixture_id"] == "synthetic-client-form")
        with self.assertRaises(KeyError):
            ledger.get("synthetic-owner-b", client["record_id"])

    def test_private_and_aggregate_views_exclude_contact_and_request_data(self) -> None:
        receipt, ledger, _valve = MODULE.run_synthetic_journeys(self.fixtures, self.contract)
        private_view = ledger.private_view("synthetic-owner-a")
        self.assertTrue(private_view)
        self.assertEqual(
            set(self.contract["views"]["private_operator"]["fields"]),
            set(private_view[0]),
        )
        self.assertNotIn("contact", json.dumps(private_view, sort_keys=True))
        self.assertNotIn("request", json.dumps(private_view, sort_keys=True))
        self.assertEqual(
            set(self.contract["views"]["aggregate_dashboard"]["fields"]),
            set(receipt["aggregate"]),
        )
        self.assertEqual(5, receipt["aggregate"]["stages"]["review_pending"])

    def test_custody_boundary_seals_partitions_and_deletes(self) -> None:
        _receipt, ledger, _valve = MODULE.run_synthetic_journeys(self.fixtures, self.contract)
        row = next(iter(ledger.records["synthetic-owner-a"].values()))
        record = row["record"]
        decision = row["decision"]

        def seal(value: bytes) -> bytes:
            return b"synthetic-sealed:" + value[::-1]

        def open_sealed(value: bytes) -> bytes:
            return value.removeprefix(b"synthetic-sealed:")[::-1]

        custody = MODULE.PrivateCustodyBoundary(seal, open_sealed)
        self.assertTrue(custody.persist(record, decision))
        sealed = custody.sealed_records["synthetic-owner-a"][record["record_id"]]
        self.assertNotIn(record["contact"]["email"].encode(), sealed)
        self.assertEqual(record, custody.get("synthetic-owner-a", record["record_id"])["record"])
        with self.assertRaises(KeyError):
            custody.get("synthetic-owner-b", record["record_id"])
        self.assertTrue(custody.delete("synthetic-owner-a", record["record_id"]))

    def test_custody_boundary_rejects_plaintext_persistence_adapter(self) -> None:
        _receipt, ledger, _valve = MODULE.run_synthetic_journeys(self.fixtures, self.contract)
        row = next(iter(ledger.records["synthetic-owner-a"].values()))
        custody = MODULE.PrivateCustodyBoundary(lambda value: value, lambda value: value)
        with self.assertRaisesRegex(ValueError, "non-plaintext sealed bytes"):
            custody.persist(row["record"], row["decision"])

    def test_retention_expiry_deletes_ledger_custody_and_dedupe_index(self) -> None:
        _receipt, ledger, _valve = MODULE.run_synthetic_journeys(self.fixtures, self.contract)
        row = next(iter(ledger.records["synthetic-owner-a"].values()))
        record = row["record"]
        decision = row["decision"]
        custody = MODULE.PrivateCustodyBoundary(
            lambda value: b"synthetic-sealed:" + value[::-1],
            lambda value: value.removeprefix(b"synthetic-sealed:")[::-1],
        )
        custody.persist(record, decision)
        result = MODULE.apply_retention(
            ledger,
            custody,
            "synthetic-owner-a",
            record["record_id"],
            decision["category"],
            as_of=datetime(2030, 1, 1, tzinfo=timezone.utc),
            contract=self.contract,
        )
        self.assertEqual(
            {
                "action": "delete",
                "deleted_count": 1,
                "sealed_deleted_count": 1,
                "receipt_scope": "aggregate_only_no_identifier",
            },
            result,
        )
        self.assertNotIn(record["dedupe_key"], ledger.dedupe_index["synthetic-owner-a"])

    def test_retention_immediate_delete_trigger_and_unknown_trigger(self) -> None:
        _receipt, ledger, _valve = MODULE.run_synthetic_journeys(self.fixtures, self.contract)
        row = next(iter(ledger.records["synthetic-owner-a"].values()))
        self.assertEqual(
            "delete",
            MODULE.retention_action(
                row["record"],
                row["decision"]["category"],
                as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
                contract=self.contract,
                trigger="consent_withdrawal",
            ),
        )
        with self.assertRaisesRegex(ValueError, "unsupported retention trigger"):
            MODULE.retention_action(
                row["record"],
                row["decision"]["category"],
                as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
                contract=self.contract,
                trigger="operator_whim",
            )

    def test_drafts_are_non_authoritative_and_send_valve_stays_closed(self) -> None:
        _receipt, ledger, valve = MODULE.run_synthetic_journeys(self.fixtures, self.contract)
        client_record = next(iter(ledger.records["synthetic-owner-a"].values()))
        draft = client_record["decision"]["draft"]
        self.assertEqual("draft", draft["status"])
        self.assertEqual("absent", draft["send_authority"])
        self.assertEqual(
            self.contract["drafts"]["templates"][draft["kind"]]["subject"].format(
                name=client_record["record"]["contact"]["name"],
                summary=client_record["record"]["request"]["summary"],
                route=client_record["decision"]["route"],
            ),
            draft["subject"],
        )
        with self.assertRaisesRegex(PermissionError, "send valve is hard closed"):
            valve.attempt_send(draft)
        self.assertEqual(0, valve.external_send_count)
        self.assertEqual(1, valve.blocked_send_attempt_count)

    def test_public_receipt_contains_no_fixture_contact_or_request_values(self) -> None:
        receipt, _ledger, valve = MODULE.run_synthetic_journeys(self.fixtures, self.contract)
        rendered = json.dumps(receipt, sort_keys=True)
        for event in self.fixtures["events"]:
            self.assertNotIn(event["contact"]["name"], rendered)
            self.assertNotIn(event["contact"]["email"], rendered)
            self.assertNotIn(event["request"]["details"], rendered)
        self.assertEqual(0, receipt["external_send_count"])
        self.assertEqual(0, valve.external_send_count)


if __name__ == "__main__":
    unittest.main()
