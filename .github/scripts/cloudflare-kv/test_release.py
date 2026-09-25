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
  with self.assertRaisesRegex(r.inv.o.SafeError,'canonical_scheduler_pause_refused'):c.pause('ops-scheduler-production',[])
  with self.assertRaisesRegex(r.inv.o.SafeError,'release_sql_refused'):c.sql('DROP TABLE scheduler_state')
 def test_main_fails_closed_without_session_authority(self):
  with patch.dict(r.os.environ,{},clear=True),patch('sys.stdout',new_callable=io.StringIO) as out:
   self.assertEqual(r.main(),1)
  self.assertEqual(json.loads(out.getvalue())['error'],'apply_not_authorized')

class PauseReviewTests(unittest.TestCase):
 def test_concurrent_schedule_change_refuses_remote_write(self):
  c=object.__new__(r.ReleaseClient);c.root='fixed-root/'
  from unittest.mock import Mock
  c.crons=Mock(return_value=['*/5 * * * *']);c.request=Mock()
  with self.assertRaisesRegex(r.inv.o.SafeError,'duplicate_schedule_prewrite_drift'):
   c.pause('ops-scheduler',['* * * * *'])
  c.request.assert_not_called()
 def test_paused_is_no_write_fixed_point(self):
  c=object.__new__(r.ReleaseClient);c.root='fixed-root/'
  from unittest.mock import Mock
  c.crons=Mock(return_value=[]);c.request=Mock()
  c.pause('ops-scheduler',[]);c.request.assert_not_called()
 def test_unchanged_expected_schedule_mutates_once_and_reads_back(self):
  c=object.__new__(r.ReleaseClient);c.root='fixed-root/'
  from unittest.mock import Mock
  c.crons=Mock(side_effect=[['* * * * *'],[]]);c.request=Mock()
  c.pause('ops-scheduler',['* * * * *'])
  c.request.assert_called_once_with('fixed-root/ops-scheduler/schedules','PUT',b'[]')

class StatusClaimConcurrencyTest(unittest.TestCase):
 def test_actual_status_update_has_one_winner_across_eight_connections(self):
  import concurrent.futures, sqlite3, tempfile, threading
  from pathlib import Path
  query="UPDATE cf_kv_recovery SET next_refresh=? WHERE product=? AND key='status' AND next_refresh<=? RETURNING key"
  self.assertIn(query,Path(__file__).with_name('recovery.mjs').read_text())
  with tempfile.TemporaryDirectory() as folder:
   path=str(Path(folder)/'status.db')
   with sqlite3.connect(path) as db:
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE cf_kv_recovery(product TEXT,key TEXT,next_refresh INTEGER,PRIMARY KEY(product,key))')
    db.execute("INSERT INTO cf_kv_recovery VALUES('edgarflash','status',0)")
   barrier=threading.Barrier(8)
   def claim(_):
    with sqlite3.connect(path,timeout=5) as db:
     barrier.wait()
     return db.execute(query,(3600000,'edgarflash',1000)).fetchone()
   with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    results=list(pool.map(claim,range(8)))
   self.assertEqual(sum(x is not None for x in results),1)
