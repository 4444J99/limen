import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('observer', Path(__file__).with_name('observe.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class ObserverTests(unittest.TestCase):
    def test_missing_credential(self):
        with self.assertRaisesRegex(m.SafeError, '^credential_missing$'):
            m.Client('')

    def test_mutation_and_arbitrary_path_rejected(self):
        c = m.Client('test-only-token')
        for path in ['/accounts', '/accounts/' + 'a'*32 + '/workers/scripts/limen-runtime/settings',
                     '/accounts/' + 'a'*32 + '/storage/kv/namespaces', '//evil.example/']:
            with self.assertRaisesRegex(m.SafeError, 'endpoint_not_allowlisted'):
                c.call(path)
        with self.assertRaisesRegex(m.SafeError, 'mutations_refused'):
            c.call('/accounts?per_page=50', {'mutate': True})
        with self.assertRaisesRegex(m.SafeError, 'endpoint_not_allowlisted'):
            c.call('/graphql', {'query': 'mutation { unsafe }'})

    def test_redirect_refused(self):
        with self.assertRaisesRegex(m.SafeError, 'redirect_refused'):
            m.NoRedirect().redirect_request(None, None, 302, None, None, 'https://evil.example')

    def test_size_and_json_bounds(self):
        with self.assertRaisesRegex(m.SafeError, 'response_too_large'):
            m.decode_response(io.BytesIO(b'a'*100), 10)
        with self.assertRaisesRegex(m.SafeError, 'invalid_json'):
            m.decode_response(io.BytesIO(b'not-json'))

    def test_sanitized_aggregation_and_partial_day(self):
        def row(date, op, ns, n):
            return {'dimensions': {'date': date, 'actionType': op, 'namespaceId': ns}, 'sum': {'requests': n}}
        rows = [row('2026-09-22', 'list', 'private-namespace', 900),
                row('2026-09-23', 'write', 'private-other', 7)]
        result = m.summarize_operations(rows, {'private-namespace':'edgarflash'}, '2026-09-23')
        self.assertNotIn('private-', json.dumps(result))
        self.assertEqual(result['days'][0]['account_operations'], {'list':900})
        self.assertEqual(result['days'][1]['coverage'], 'partial_day')
        self.assertNotIn('read', result['days'][1]['account_operations'])

    def test_invalid_analytics_never_become_zero(self):
        for rows in [None, [{}]*10000, [{'dimensions': {'date':'2026-09-23','actionType':'write'},'sum': {'requests':float('nan')}}]]:
            with self.assertRaises(m.SafeError):
                m.summarize_operations(rows, {}, '2026-09-23')

    def test_raw_settings_and_secrets_not_reported(self):
        class Fake:
            def account(self): return 'private-account'
            def result(self, path):
                if path.endswith('/settings'):
                    return {'bindings':[{'type':'kv_namespace','name':'STATE','namespace_id':'private-ns'},
                                        {'type':'plain_text','name':'SECRET','text':'private-secret'}],
                            'compatibility_date':'2026-04-01'}
                if path.endswith('/schedules'): return {'schedules':[{'cron':'0 12 * * *'}]}
                if path.endswith('/deployments'): return {'deployments':[]}
                raise AssertionError(path)
            def call(self, path, payload):
                assert path == '/graphql'
                return {'data':{'viewer':{'accounts':[{'kvOperationsAdaptiveGroups':[]}]}}}
        with patch.object(m,'public_probe',return_value={'http':503}):
            report=m.observe(Fake())
        self.assertNotIn('private-', json.dumps(report))
        self.assertEqual(report['mutations'],0)
        self.assertEqual(len(report['workers']),3)

if __name__ == '__main__':
    unittest.main()
