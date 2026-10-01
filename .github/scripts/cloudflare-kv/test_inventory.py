import io
import json
import unittest
from unittest.mock import patch
import inventory as m

class InventoryTests(unittest.TestCase):
    def test_endpoint_bound(self):
        client=m.InventoryClient('test-only')
        for path in ['/accounts','/accounts/'+'a'*32+'/workers/scripts/x/secrets',
                     '/accounts/'+'a'*32+'/workers/scripts/../settings']:
            with self.assertRaises(m.o.SafeError): client.raw(path)
    def test_source_summary_does_not_publish_source_or_secret(self):
        result=m.source_summary('application/javascript',b'const secret="private-secret"; export { Foo as SchedulerEntrypoint, worker as default };')
        self.assertEqual(result['exported_symbols'],['SchedulerEntrypoint','default'])
        self.assertNotIn('private-secret',json.dumps(result))
    def test_live_topology_keeps_identifiers_private(self):
        class Fake:
            def account(self): return 'private-account'
            def inventory_result(self,path):
                if path.endswith('/scripts'): return [{'id':'edgarflash'}]
                if path.endswith('/settings'): return {'bindings':[
                    {'type':'kv_namespace','namespace_id':'private-ns'},
                    {'type':'plain_text','name':'secret','text':'private-secret'},
                    {'type':'service','service':'dispatcher','entrypoint':'Job'}]}
                if path.endswith('/schedules'): return {'schedules':[]}
                raise AssertionError(path)
            def raw(self,path): return 'application/javascript',b'export { worker as default }'
            def call(self,*args): return {'data':{'viewer':{'accounts':[{'kvOperationsAdaptiveGroups':[]}]}}}
        report=m.collect(Fake())
        self.assertNotIn('private-',json.dumps(report))
        self.assertEqual(report['workers'][0]['service_bindings'],[{'target':'dispatcher','entrypoint':'Job'}])
    def test_unexpected_errors_are_sanitized(self):
        with patch.object(m,'collect',side_effect=ValueError('private-secret')):
            with patch.dict(m.os.environ,{'CLOUDFLARE_API_TOKEN':'test-only'},clear=True):
                with patch('sys.stdout',new_callable=io.StringIO) as out:
                    self.assertEqual(m.main(),1)
                self.assertNotIn('private-secret',out.getvalue())

if __name__=='__main__': unittest.main()
