import unittest
from ingress_status import UCC, SCHEDULER, describe, unpack

class IngressStatusTests(unittest.TestCase):
    def test_expected_binding_and_helper(self):
        got = describe(SCHEDULER, {'bindings': [{'name': 'UCC_STAGING', 'type': 'service',
            'service': UCC, 'entrypoint': 'KvIncidentScheduledIngress'}]},
            {'index.js': b'export default {};', 'finishline.mjs': b'helper'}, b'helper')
        self.assertTrue(got['ucc_binding_target_correct'])
        self.assertTrue(got['ucc_binding_entrypoint_correct'])
        self.assertTrue(got['helper_matches_accepted_source'])

    def test_default_binding_drift_is_explicit(self):
        got = describe(SCHEDULER, {'bindings': [{'name': 'UCC_STAGING', 'type': 'service', 'service': UCC}]},
            {'index.js': b'original'}, b'helper')
        self.assertEqual(got['ucc_binding_entrypoint_state'], 'default')
        self.assertFalse(got['ucc_binding_entrypoint_correct'])
        self.assertFalse(got['helper_present'])

    def test_source_and_secret_values_never_projected(self):
        got = describe(UCC, {'bindings': [{'name': 'SCHEDULER_SECRET', 'type': 'plain_text', 'text': 'private-token'}]},
            {'index.js': b"const value='private-source'; class KvIncidentScheduledIngress {}"}, b'helper')
        self.assertTrue(got['scheduler_secret_binding_present'])
        self.assertTrue(got['named_ingress_declared'])
        self.assertNotIn('private', str(got))

    def test_malformed_bindings_rejected(self):
        for value in (None, {}, [None]):
            with self.assertRaises(ValueError): describe(UCC, {'bindings': value}, {'index.js': b'a'}, b'b')

    def test_raw_module_and_multipart_parser(self):
        self.assertEqual(unpack('application/javascript', b'abc'), {'index.js': b'abc'})
        raw = b'--x\r\nContent-Disposition: form-data; name="index.js"; filename="index.js"\r\n\r\nabc\r\n--x--\r\n'
        self.assertEqual(unpack('multipart/form-data; boundary=x', raw), {'index.js': b'abc'})
        with self.assertRaises(ValueError): unpack('multipart/form-data; boundary=x', raw.replace(b'index.js', b'secrets.txt'))

if __name__ == '__main__': unittest.main()
