import hashlib
import io
import json
import unittest
from unittest.mock import patch
import release as r

class ReleaseTests(unittest.TestCase):
 def test_unknown_source_refused(self):
  for name in ('unknown','edgarflash'):
   with self.assertRaises(r.inv.o.SafeError):r.transform(name,b'export default {}')
 def test_preserved_metadata_never_copies_secret_values(self):
  settings={'compatibility_date':'2026-04-01','bindings':[
   {'name':'TOKEN','type':'plain_text','text':'private-secret'},
   {'name':'ASSETS','type':'assets'},{'name':'DB','type':'d1','database_id':'private-db'}]}
  result=r.preserved_metadata(settings,'existing-database','test')
  self.assertNotIn('private-',json.dumps(result));self.assertTrue(result['keep_assets'])
  self.assertEqual(result['bindings'][0],{'name':'TOKEN','type':'inherit'})
 def test_multipart_preserves_module_bytes(self):
  kind,raw=r.multipart({'main_module':'index.js'},{'index.js':b'export default {};','recovery.mjs':b'export const ok=1;'})
  self.assertEqual(r.modules(kind,raw),{'index.js':b'export default {};','recovery.mjs':b'export const ok=1;'})
 def test_mutation_scope_rejects_unrelated_operations(self):
  c=object.__new__(r.ReleaseClient);c.root='/accounts/'+'a'*32+'/workers/scripts/';c.aid='a'*32;c.db=None;c.seed_namespace=None;c.token='test-only'
  for path,method in [(c.root+'limen-runtime?bindings_inherit=strict','PUT'),(c.root+'ops-scheduler-production/schedules','PUT'),('/accounts','POST')]:
   with self.assertRaises(r.inv.o.SafeError):c.request(path,method)
  with self.assertRaisesRegex(r.inv.o.SafeError,'canonical_scheduler_pause_refused'):c.pause('ops-scheduler-production')
  with self.assertRaisesRegex(r.inv.o.SafeError,'release_sql_refused'):c.sql('DROP TABLE scheduler_state')
 def test_main_fails_closed_without_session_authority(self):
  with patch.dict(r.os.environ,{},clear=True),patch('sys.stdout',new_callable=io.StringIO) as out:
   self.assertEqual(r.main(),1)
  self.assertEqual(json.loads(out.getvalue())['error'],'apply_not_authorized')
