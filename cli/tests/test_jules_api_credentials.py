"""Credential delivery reuses CLAVIS and remains distinct from live activation."""

import json
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from limen.jules_api import Catalog, JulesApiError
from limen.jules_credentials import SINK, bind_ci_credential

REF = "op://fixture-vault/fixture-item/credential"
KEY = "synthetic-jules-key-for-tests-only"


class JulesCredentialBindingTests(unittest.TestCase):
    def setUp(self):
        self.clavis = Mock()
        self.clavis.load_map.return_value = [{"ref": REF, "env": ["JULES_API_KEY"], "enabled": True}]
        self.clavis.have_op.return_value = True
        self.clavis.have_gh.return_value = True
        self.clavis.op_can_read_silently.return_value = True
        self.clavis.op_read.return_value = KEY
        self.clavis.gh_sink_set.return_value = True
        self.clavis.gh_sink_present.return_value = True
        self.client = Mock()
        empty = Catalog((), 1, datetime.now(timezone.utc).isoformat())
        self.client.sources.return_value = empty
        self.client.sessions.return_value = empty
        self.factory = Mock(return_value=self.client)

    def bind(self, ref=None, apply=True):
        result = bind_ci_credential(self.clavis, ref, apply=apply, client_factory=self.factory)
        self.assertNotIn(KEY, json.dumps(result))
        self.assertNotIn(REF, json.dumps(result))
        self.assertFalse(result["activation_verified"])
        self.assertFalse(result["executor_readback_verified"])
        self.assertEqual(result["provider_mutations"], 0)
        return result

    def test_default_plan_reads_no_secrets_or_provider(self):
        self.assertEqual(self.bind(apply=False)["status"], "planned")
        self.clavis.load_service_account_token.assert_not_called()
        self.clavis.op_read.assert_not_called()
        self.factory.assert_not_called()
        self.clavis.gh_sink_set.assert_not_called()

    def test_no_source_is_invented_when_mapping_is_absent(self):
        self.clavis.load_map.return_value = [{"env": ["GH_TOKEN"], "ref": REF}]
        self.assertEqual(self.bind()["error_code"], "credential_source_unresolved")
        self.clavis.op_read.assert_not_called()

    def test_ambiguous_sources_are_not_arbitrarily_chosen(self):
        self.clavis.load_map.return_value.append(
            {"ref": "op://fixture-vault/other/credential", "env": ["JULES_API_KEY"]}
        )
        self.assertEqual(self.bind()["error_code"], "credential_source_unresolved")
        self.clavis.op_read.assert_not_called()

    def test_disabled_source_is_not_activated(self):
        self.clavis.load_map.return_value[0]["enabled"] = False
        self.assertEqual(self.bind()["error_code"], "credential_source_unresolved")

    def test_explicit_discovered_reference_is_supported(self):
        self.clavis.load_map.return_value = []
        self.assertEqual(self.bind(REF)["status"], "delivered_pending_executor_readback")
        self.clavis.op_read.assert_called_once_with(REF)

    def test_invalid_references_never_read_or_write_credentials(self):
        for ref in (
            "literal-key",
            "https://evil.test/item/field",
            "op://vault/item",
            "op://v/../field",
            "op://v/i/%0Akey",
            "op://v/i/key?q=x",
            "op://v/i/key#x",
            "op://user@v/i/key",
        ):
            with self.subTest(ref=ref):
                self.assertEqual(self.bind(ref)["error_code"], "credential_source_reference_invalid")
        self.clavis.op_read.assert_not_called()
        self.clavis.gh_sink_set.assert_not_called()

    def test_no_interactive_unlock_fallback(self):
        self.clavis.op_can_read_silently.return_value = False
        self.assertEqual(self.bind()["error_code"], "credential_runtime_unavailable")
        self.clavis.op_read.assert_not_called()

    def test_missing_gh_does_not_read_a_secret(self):
        self.clavis.have_gh.return_value = False
        self.assertEqual(self.bind()["error_code"], "credential_runtime_unavailable")
        self.clavis.op_read.assert_not_called()

    def test_unreadable_source_does_not_contact_provider(self):
        self.clavis.op_read.return_value = None
        self.assertEqual(self.bind()["error_code"], "credential_source_unreadable")
        self.factory.assert_not_called()

    def test_rejected_key_is_not_bound(self):
        self.client.sources.side_effect = JulesApiError("provider_rejected", 403)
        result = self.bind()
        self.assertEqual(result["http_status"], 403)
        self.clavis.gh_sink_set.assert_not_called()

    def test_incomplete_history_cannot_validate_delivery(self):
        self.client.sessions.side_effect = JulesApiError("pagination_deadline_exceeded")
        self.assertEqual(self.bind()["error_code"], "pagination_deadline_exceeded")
        self.clavis.gh_sink_set.assert_not_called()

    def test_valid_key_is_only_sent_to_the_declared_sink(self):
        result = self.bind()
        self.assertEqual(result["status"], "delivered_pending_executor_readback")
        self.clavis.gh_sink_set.assert_called_once_with(SINK, KEY)
        self.clavis.gh_sink_present.assert_called_once_with(SINK)
        self.clavis.write_env.assert_not_called()
        self.assertTrue(result["ci_secret_written"])
        self.assertTrue(result["ci_presence_verified"])
        self.assertEqual(result["provider_observation"]["status"], "observed")

    def test_failed_write_is_not_success(self):
        self.clavis.gh_sink_set.return_value = False
        result = self.bind()
        self.assertEqual(result["error_code"], "ci_credential_delivery_failed")
        self.assertFalse(result["ci_secret_written"])
        self.clavis.gh_sink_present.assert_not_called()

    def test_unknown_presence_preserves_the_completed_write_fact(self):
        self.clavis.gh_sink_present.return_value = None
        result = self.bind()
        self.assertEqual(result["error_code"], "ci_credential_presence_unverified")
        self.assertTrue(result["ci_secret_written"])
        self.assertFalse(result["ci_presence_verified"])

    def test_unexpected_exception_never_leaks_secret_text(self):
        self.clavis.op_read.side_effect = RuntimeError(KEY)
        self.assertEqual(self.bind()["error_code"], "credential_binding_unavailable")


if __name__ == "__main__":
    unittest.main()
