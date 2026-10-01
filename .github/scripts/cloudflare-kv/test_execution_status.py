import unittest
from execution_status import project

class ExecutionTests(unittest.TestCase):
    def test_attempts_and_completions_are_distinct(self):
        got = project({'targetStates': {'ucc-staging': {'lastInvokedAt': 2000,
          'lastCompletedAt': 1000, 'lastStatus': 'failure', 'consecutiveFailures': 3}}}, '', {})
        self.assertEqual(got['jobs']['ucc-staging']['lastInvokedAt'], 2000)
        self.assertEqual(got['jobs']['ucc-staging']['lastCompletedAt'], 1000)
        self.assertEqual(got['jobs']['ucc-staging']['consecutiveFailures'], 3)
    def test_arbitrary_fields_and_source_never_emitted(self):
        got = project({'targetStates': {'ucc-staging': {'lastStatus': 'private-secret',
          'token': 'private-token', 'lastInvokedAt': 'private-source'}}},
          'const key="private-value"; var INVOCATION_TIMEOUT_MS = 30000;', {})
        self.assertNotIn('private', str(got))
        self.assertEqual(got['default_invocation_timeout_ms'], 30000)
    def test_unknown_or_invalid_numeric_data_not_coerced(self):
        for value in (None, float('nan'), float('inf'), True, -1, '5000'):
            got = project({'targetStates': {'ucc-staging': {'lastInvokedAt': value}}}, '', {})
            self.assertNotIn('lastInvokedAt', got['jobs']['ucc-staging'])
    def test_only_known_job_acknowledgements_projected(self):
        got = project({}, '', {'vulnpulse': {'ok': True, 'completed_at': 123, 'key': 'private'},
                               'unknown-private': {'ok': True}})
        self.assertNotIn('private', str(got))
        self.assertEqual(got['product_acknowledgements']['vulnpulse'], {'completed_at': 123, 'ok': True})
    def test_missing_acknowledgement_never_becomes_success(self):
        got=project({}, '', {})
        self.assertEqual(got['product_acknowledgements'], {})
        self.assertEqual(got['jobs']['vulnpulse']['last_status'], 'unknown')
    def test_malformed_job_containers_refused(self):
        for state in ({'targetStates': []}, {'targetStates': {'ucc-staging': None}}):
            with self.assertRaises(ValueError): project(state, '', {})

if __name__=='__main__': unittest.main()
