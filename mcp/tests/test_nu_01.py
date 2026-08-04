import unittest

from limen_mcp import server


class Nu01McpReadToolsTests(unittest.TestCase):
    owner = "owner:arya@partition-a"
    collaborator = "collab:maya@partition-a"
    auditor = "auditor:io@partition-a"

    def test_unknown_principal_denied(self) -> None:
        response = server.nu01_entities("ghost:unknown@partition-a", "partition-a")
        self.assertFalse(response["allowed"])
        self.assertEqual(response["policyReceipt"]["reasonCode"], "DENY_UNKNOWN_PRINCIPAL")

    def test_collaborator_can_read_entities_and_timelines(self) -> None:
        entities = server.nu01_entities(self.collaborator, "partition-a")
        self.assertTrue(entities["allowed"])
        self.assertEqual(len(entities["data"]), 2)
        self.assertNotIn("contactEmail", entities["data"][0])

        timeline = server.nu01_timeline(self.collaborator, "partition-a", "person-arya")
        self.assertTrue(timeline["allowed"])
        self.assertEqual(len(timeline["data"]), 2)

    def test_collaborator_denied_source_receipts(self) -> None:
        receipts = server.nu01_source_receipts(self.collaborator, "partition-a")
        self.assertFalse(receipts["allowed"])
        self.assertEqual(receipts["policyReceipt"]["reasonCode"], "DENY_RESOURCE_SCOPE")

    def test_owner_sees_source_receipts_with_sensitive_data(self) -> None:
        receipts = server.nu01_source_receipts(self.owner, "partition-a")
        self.assertTrue(receipts["allowed"])
        self.assertTrue(receipts["data"])
        self.assertIn("rawPayload", receipts["data"][0])

    def test_search_tool_and_resource_share_scope_and_receipts(self) -> None:
        tool = server.nu01_search(
            principal_id=self.owner,
            partition_id="partition-a",
            query="Commit",
            limit=10,
            correlation_id="corr-shared-01",
        )
        resource = server.nu01_resource_search(
            principal_id=self.owner,
            partition_id="partition-a",
            query="Commit",
        )

        self.assertEqual(tool["allowed"], True)
        self.assertEqual(resource["allowed"], True)
        self.assertEqual(tool["policyReceipt"]["principalId"], self.owner)
        self.assertEqual(resource["policyReceipt"]["principalId"], self.owner)
        self.assertEqual(tool["correlationId"], "corr-shared-01")
        self.assertGreater(len(tool["data"]), 0)
        self.assertGreater(len(resource["data"]), 0)


class Nu02McpMutationToolsTests(unittest.TestCase):
    owner = "owner:arya@partition-a"
    collaborator = "collab:maya@partition-a"

    def test_owner_capture_is_proposed_and_idempotent(self) -> None:
        response = server.nu02_capture(
            principal_id=self.owner,
            partition_id="partition-a",
            capture_type="meeting-note",
            title="Week-start brief",
            body="Initial synthesis for partition-a.",
            idempotency_key="idem-capture-1",
            source_partition_id="partition-a",
            correlation_id="corr-a",
        )
        self.assertTrue(response["allowed"])
        self.assertEqual(response["mutationReceipt"]["status"], "proposed")
        self.assertEqual(response["mutationReceipt"]["operation"], "capture")
        self.assertEqual(response["mutationReceipt"]["correlationId"], "corr-a")

        replay = server.nu02_capture(
            principal_id=self.owner,
            partition_id="partition-a",
            capture_type="meeting-note",
            title="Week-start brief",
            body="Initial synthesis for partition-a.",
            idempotency_key="idem-capture-1",
            source_partition_id="partition-a",
            correlation_id="corr-b",
        )
        self.assertTrue(replay["allowed"])
        self.assertEqual(replay["mutationReceipt"]["status"], "replayed")
        self.assertEqual(replay["mutationReceipt"]["mutationId"], response["mutationReceipt"]["mutationId"])
        self.assertEqual(replay["correlationId"], "corr-b")

    def test_collaborator_denied_decision_mutation(self) -> None:
        response = server.nu02_decision(
            principal_id=self.collaborator,
            partition_id="partition-a",
            summary="Approve risk posture",
            result="approved",
            idempotency_key="idem-decision-1",
            target_partition_id="partition-a",
        )
        self.assertFalse(response["allowed"])
        self.assertEqual(response["mutationReceipt"]["reasonCode"], "DENY_OPERATION_SCOPE")

    def test_missing_idempotency_key_denied(self) -> None:
        response = server.nu02_task(
            principal_id=self.owner,
            partition_id="partition-a",
            title="Draft contract",
            owner="owner:arya@partition-a",
            due_at="2026-08-15",
            idempotency_key="",
            source_partition_id="partition-a",
        )
        self.assertFalse(response["allowed"])
        self.assertEqual(response["policyReceipt"]["reasonCode"], "DENY_MISSING_IDEMPOTENCY_KEY")

    def test_cross_partition_reference_rejected(self) -> None:
        response = server.nu02_link(
            principal_id=self.owner,
            partition_id="partition-a",
            left_entity_id="person-arya",
            right_entity_id="org-sigma",
            left_entity_partition_id="partition-a",
            right_entity_partition_id="partition-b",
            idempotency_key="idem-link-cross",
        )
        self.assertFalse(response["allowed"])
        self.assertEqual(response["mutationReceipt"]["reasonCode"], "DENY_CROSS_PARTITION_REFERENCE")


if __name__ == "__main__":
    unittest.main()
