import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import capture as m

class CaptureTest(unittest.TestCase):
    def test_only_ciphertext_is_written_and_report_is_redacted(self):
        class Fake:
            def account(self): return 'private-account'
            def raw(self,path):
                assert path.endswith('/content/v2')
                return 'application/javascript',b'const value="private-source";'
            def inventory_result(self,path):
                assert path.endswith('/settings')
                return {'bindings':[{'type':'plain_text','text':'private-setting'}]}
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'output.cms'
            def run(argv,**kwargs):
                data=json.loads(kwargs['input'])
                self.assertEqual(sorted(data['workers']),sorted(m.TARGETS))
                self.assertNotIn('private-account',kwargs['input'].decode())
                self.assertIn('private-setting',kwargs['input'].decode())
                out.write_bytes(b'ciphertext')
                return SimpleNamespace(returncode=0)
            with patch.object(m.subprocess,'run',side_effect=run):
                report=m.capture(Fake(),out)
            self.assertEqual(out.read_bytes(),b'ciphertext')
            self.assertNotIn('private-',json.dumps(report))
            self.assertEqual(list(Path(folder).iterdir()),[out])
    def test_content_v2_is_the_only_content_read_endpoint(self):
        from unittest.mock import MagicMock
        response=MagicMock()
        response.__enter__.return_value=response
        response.read.return_value=b'export default {}'
        response.headers={'Content-Type':'application/javascript'}
        path='/accounts/'+'a'*32+'/workers/scripts/edgarflash/content/v2'
        with patch.object(m.inv.o.OPENER,'open',return_value=response) as call:
            m.inv.InventoryClient('test-only').raw(path)
        self.assertTrue(call.call_args.args[0].full_url.endswith('/content/v2'))
        with self.assertRaises(m.inv.o.SafeError):
            m.inv.InventoryClient('test-only').raw(path.removesuffix('/v2'))

if __name__=='__main__': unittest.main()
