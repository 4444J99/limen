import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import capture_reconcile as m

class ReadbackTests(unittest.TestCase):
    def test_read_only_exact_components(self):
        calls = []
        class Fake:
            def settings(self, name):
                calls.append(('settings', name))
                return {'bindings': [{'name': 'SCHED_DB', 'type': 'd1', 'database_id': 'private-db'}]}
            def source(self, name):
                calls.append(('source', name))
                return {'index.js': b'private-live-code'}
            def crons(self, name):
                return []
            def sql(self, query, params):
                self_query = 'SELECT payload FROM scheduler_state WHERE id=?'
                assert query == self_query and params == ('scheduler:state',)
                return [{'payload': '{"lastError":"private-error"}'}]
        result = m.collect(Fake())
        self.assertEqual(set(result['workers']), set(m.TARGETS))
        self.assertEqual(len(calls), 2 * len(m.TARGETS))
        self.assertNotIn('CLOUDFLARE_API_TOKEN', json.dumps(result))

    def test_encryption_only_writes_ciphertext(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'capture.cms'
            def fake(args, **kwargs):
                self.assertIn('private-payload', kwargs['input'].decode())
                output.write_bytes(b'ciphertext')
                return type('Result', (), {'returncode': 0})()
            with patch.object(m.subprocess, 'run', side_effect=fake):
                digest = m.encrypt({'source': 'private-payload'}, output, Path('public-cert'))
            self.assertEqual(output.read_bytes(), b'ciphertext')
            self.assertEqual(list(Path(tmp).iterdir()), [output])
            self.assertEqual(len(digest), 64)

    def test_main_does_not_emit_error_details(self):
        with patch.dict(os.environ, {}, clear=True), patch('sys.stdout', new_callable=io.StringIO) as out:
            self.assertEqual(m.main(), 1)
        self.assertEqual(json.loads(out.getvalue()), {'error': 'encrypted_readback_failed', 'mutations': 0})

if __name__ == '__main__': unittest.main()
