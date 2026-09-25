import io
import unittest
from unittest.mock import patch
from ingress_status import UCC, describe, unpack, main_module, health_proof

class ProvenanceTests(unittest.TestCase):
    def test_runtime_bundle_is_parsed_without_assuming_index_filename(self):
        raw = b'--x\r\nContent-Disposition: form-data; name="runtime.js"\r\n\r\nabc\r\n--x--\r\n'
        result = unpack('multipart/form-data; boundary=x', raw)
        self.assertEqual(result, {'runtime.js': b'abc'})
        self.assertEqual(main_module(result), 'runtime.js')

    def test_unknown_or_ambiguous_main_stays_rejected(self):
        for value in ({}, {'secret.txt': b'a'}, {'runtime.js': b'a', 'index.js': b'b'}):
            with self.assertRaises(ValueError): main_module(value)

    def test_canonical_bundle_provenance_without_raw_settings(self):
        sha = 'a' * 40
        report = describe(UCC, {'bindings': [{'name': 'DEPLOYMENT_SHA', 'type': 'plain_text', 'text': sha}]},
                          {'runtime.js': b'KvIncidentScheduledIngress prds-scheduler-contract-v1 invocation_database_budget_exhausted'}, b'legacy')
        self.assertTrue(report['canonical_bundle_markers_present'])
        self.assertFalse(report['helper_present'])
        self.assertEqual(report['deployment_revision'], sha)

    def test_invalid_revision_is_not_echoed(self):
        for revision in ('private-token', None, ['bad']):
            report = describe(UCC, {'bindings': [{'name': 'DEPLOYMENT_SHA', 'type': 'plain_text', 'text': revision}]},
                              {'runtime.js': b'code'}, b'legacy')
            self.assertIsNone(report['deployment_revision'])

    def test_public_health_get_never_receives_provider_credential(self):
        import observe
        sha = 'a' * 40
        response = io.BytesIO(('{"revision":"' + sha + '"}').encode())
        response.status = 200
        with patch.object(observe.OPENER, 'open', return_value=response) as call:
            report = health_proof(sha)
        self.assertTrue(report['matches_deployed_revision'])
        self.assertIsNone(call.call_args.args[0].get_header('Authorization'))

    def test_health_revision_mismatch_is_not_success(self):
        import observe
        response = io.BytesIO(b'{"revision":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}')
        response.status = 200
        with patch.object(observe.OPENER, 'open', return_value=response):
            self.assertFalse(health_proof('a' * 40)['matches_deployed_revision'])

if __name__ == '__main__': unittest.main()
