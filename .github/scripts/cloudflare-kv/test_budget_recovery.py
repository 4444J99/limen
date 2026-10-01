import hashlib
import io
import json
import unittest
from unittest.mock import patch,Mock
import budget_recovery as m

class BudgetTests(unittest.TestCase):
 def test_scheduler_change_is_exact_scoped_and_idempotent(self):
  source=('function invoke(target){'+m.OLD_TIMER+'throw new Error('+m.OLD_MESSAGE+');}').encode()
  with patch.object(m,'SCHEDULER_BASE',m.digest(source)):
   result=m.scheduler_patch(source)
   self.assertIn(b"target.name === 'ucc-staging' ? 300000",result)
   self.assertEqual(m.scheduler_patch(result),result)
   with self.assertRaises(m.r.inv.o.SafeError):m.scheduler_patch(result+b' changed')
 def test_unknown_scheduler_and_replay_helper_are_refused(self):
  with self.assertRaises(m.r.inv.o.SafeError):m.scheduler_patch(b'not source')
  with self.assertRaises(m.r.inv.o.SafeError):m.replay_patch(b'not source')
 def test_preserved_binding_metadata_contains_no_values(self):
  value=m.metadata({'bindings':[{'name':'SECRET','type':'plain_text','text':'private-secret'},{'name':'DB','type':'d1','database_id':'private-id'}]})
  self.assertNotIn('private-',json.dumps(value));self.assertTrue(all(b['type']=='inherit' for b in value['bindings']))
 def test_four_module_readback_roundtrip(self):
  files={name:b'content' for name in ('index.js','finishline.mjs','recovery.mjs','subscriber-cache.mjs')}
  self.assertEqual(m.parse_modules(*m.multipart({'bindings':[]},files)),files)
 def test_upload_uses_its_scoped_transport_not_legacy_product_allowlist(self):
  c=object.__new__(m.Client);c.root='/accounts/'+'a'*32+'/workers/scripts/';c.token='fixture-token'
  c.request=Mock(side_effect=AssertionError('legacy transport must not be used'))
  response=io.BytesIO(b'{"success":true}')
  with patch.object(m.r.inv.o.OPENER,'open',return_value=response) as send:
   c.upload(m.SCHEDULER,{'bindings':[]},{'index.js':b'code'})
  req=send.call_args.args[0];self.assertEqual(req.get_method(),'PUT');self.assertTrue(req.full_url.endswith('/ops-scheduler-production?bindings_inherit=strict'))
  c.request.assert_not_called()
  with self.assertRaises(m.r.inv.o.SafeError):c.upload('unrelated-worker',{'bindings':[]},{})
 def test_forbidden_sql_and_namespace_are_refused(self):
  c=object.__new__(m.Client)
  with self.assertRaises(m.r.inv.o.SafeError):c.cache_sql('DROP TABLE unrelated')
  with self.assertRaises(m.r.inv.o.SafeError):c.subscriber_seed('../unrelated')
 def test_no_authority_no_mutation(self):
  with patch.dict(m.os.environ,{},clear=True),patch('sys.stdout',new_callable=io.StringIO):self.assertEqual(m.main(),1)

class CacheDatabaseRaceTests(unittest.TestCase):
 def test_independent_connections_share_one_list_lease(self):
  import sqlite3,tempfile,threading,concurrent.futures
  from pathlib import Path
  query='UPDATE cf_kv_list_cache SET next_refresh=? WHERE product=? AND key=? AND next_refresh<=? RETURNING payload,updated_at,generation'
  self.assertIn(query,Path(__file__).with_name('subscriber-cache.mjs').read_text())
  with tempfile.TemporaryDirectory() as folder:
   path=str(Path(folder)/'cache.db')
   with sqlite3.connect(path) as db:
    db.execute('PRAGMA journal_mode=WAL');db.execute(m.SCHEMA);db.execute(m.SEED,('edgarflash',m.CACHE_KEY,'null',0,0))
   barrier=threading.Barrier(8)
   def claim(_):
    with sqlite3.connect(path,timeout=5) as db:
     barrier.wait();return db.execute(query,(300000,'edgarflash',m.CACHE_KEY,1000)).fetchone()
   with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(claim,range(8)))
   self.assertEqual(sum(x is not None for x in results),1)
