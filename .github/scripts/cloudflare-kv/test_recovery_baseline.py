import datetime as dt
import json
import sqlite3
import unittest
from unittest.mock import patch
import monitor as m
import recovery_baseline as b

class RecoveryTests(unittest.TestCase):
 def read(self, activation, source=b.SOURCE, enabled=1):
  class Client:
   aid='fixture';db='fixture'
   def request(self,path,method,data):
    query=json.loads(data)
    assert method=='POST'
    if query['sql']==b.CONTROL:
     rows=[{'source_sha':source,'activate_after':activation,'enabled':enabled}]
    else:
     assert 'INDEXED BY ops_pending_target_order' in query['sql']
     rows=[{'target':name,'oldest_pending_at':activation-60000} for name in m.TARGET_AGES]
    return [{'success':True,'results':rows}]
  return b.read(Client(),m.TARGET_AGES,1791763200000)
 def test_partial_activation_day_cannot_qualify(self):
  baseline=self.read(1791591360000)
  self.assertEqual(baseline['first_complete_day'],'2026-10-11')
  kv=[{'date':'2026-10-10','account_operations':dict.fromkeys(('read','write','list','delete'),0)}]
  days=m.build_days(kv,{'2026-10-10':{'rowsRead':1,'rowsWritten':1}},dt.date(2026,10,11),first_complete_day=baseline['first_complete_day'])
  self.assertFalse(any(d['completed_post_rollout_window'] for d in days))
 def test_midnight_activation_allows_that_utc_day(self):
  self.assertEqual(self.read(1791590400000)['first_complete_day'],'2026-10-10')
 def test_prior_source_old_activation_disabled_or_invalid_fail_closed(self):
  for args in ((1791590400000,'old'),(1791504000000,),(1791590400000,b.SOURCE,0),(float('nan'),)):
   with self.assertRaises(ValueError):self.read(*args)
 def test_queue_age_has_six_bounded_targets(self):
  baseline=self.read(1791590400000)
  self.assertEqual(set(baseline['oldest_pending_age_seconds']),set(m.TARGET_AGES))
  self.assertTrue(all(age>0 for age in baseline['oldest_pending_age_seconds'].values()))
 def test_actual_queue_query_uses_one_ordered_pending_lookup_per_target(self):
  with sqlite3.connect(':memory:') as db:
   db.executescript("CREATE TABLE ops_runs(target,scheduled_at,id,state); CREATE INDEX ops_pending_target_order ON ops_runs(target,scheduled_at,id) WHERE state='pending';")
   db.executemany('INSERT INTO ops_runs VALUES(?,?,?,?)', [('edgarflash',100,1,'completed'),('edgarflash',200,2,'pending'),('edgarflash',300,3,'pending')])
   params=(json.dumps(list(m.TARGET_AGES)),)
   rows=db.execute(b.QUEUE,params).fetchall()
   self.assertEqual(dict(rows)['edgarflash'],200)
   self.assertEqual(len(rows),6)
   plan=[r[3] for r in db.execute('EXPLAIN QUERY PLAN '+b.QUEUE,params)]
   self.assertTrue(any('SEARCH ops_runs USING' in p and 'INDEX ops_pending_target_order (target=?)' in p for p in plan),plan)
   self.assertFalse(any('SCAN ops_runs' in p for p in plan),plan)
