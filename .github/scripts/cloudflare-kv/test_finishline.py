import hashlib
import json
import unittest
import apply_finishline as m

class FinishlineTests(unittest.TestCase):
 def test_unknown_source_refused(self):
  for name in (*m.BASE,'unknown'):
   with self.assertRaises(m.r.inv.o.SafeError):m.transform(name,b'not-the-live-source')
 def test_binding_metadata_preserves_secret_and_changes_only_named_target(self):
  settings={'bindings':[{'name':'SECRET','type':'secret_text','text':'private-value'},
    {'name':'UCC_STAGING','type':'service','service':'ucc-mca-edge-staging'}]}
  meta=m.metadata(settings,'ops-scheduler-production')
  self.assertNotIn('private-value',json.dumps(meta))
  self.assertEqual(meta['bindings'][0],{'name':'SECRET','type':'inherit'})
  self.assertEqual(meta['bindings'][1]['entrypoint'],m.ENTRYPOINT)
 def test_multipart_and_readback_agree(self):
  files={'index.js':b'export default {};','finishline.mjs':b'export const ok=1;'}
  self.assertEqual(m.decode_modules(*m.multipart({'main_module':'index.js'},files)),files)
 def test_changed_binding_and_unknown_modules_refused(self):
  with self.assertRaises(m.r.inv.o.SafeError):m.metadata({'bindings':[]},'ops-scheduler-production')
  with self.assertRaises(m.r.inv.o.SafeError):m.multipart({}, {'unknown.js':b''})
 def test_patch_anchor_count_is_exact(self):
  with self.assertRaises(m.r.inv.o.SafeError):m.once('duplicate duplicate','duplicate','replacement')

class ConcurrentClaimTests(unittest.TestCase):
 def test_single_winner_across_independent_sqlite_connections(self):
  import concurrent.futures
  import sqlite3
  import tempfile
  import threading
  from pathlib import Path
  query="UPDATE cf_kv_recovery SET next_refresh=0 WHERE product='incident' AND key=? AND next_refresh=1 RETURNING payload"
  self.assertIn(query,Path(__file__).with_name('finishline.mjs').read_text())
  with tempfile.TemporaryDirectory() as folder:
   path=str(Path(folder)/'claims.db')
   with sqlite3.connect(path) as db:
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE cf_kv_recovery(product TEXT,key TEXT,payload TEXT,next_refresh INTEGER,PRIMARY KEY(product,key))')
    db.execute('INSERT INTO cf_kv_recovery VALUES(?,?,?,1)',('incident','claim','payload'))
   barrier=threading.Barrier(8)
   def claim(_):
    with sqlite3.connect(path,timeout=5) as connection:
     barrier.wait()
     return connection.execute(query,('claim',)).fetchone()
   with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    results=list(pool.map(claim,range(8)))
   self.assertEqual(sum(result is not None for result in results),1)
