import unittest
from unittest.mock import patch,Mock
import invocation_recovery as m
class InvocationTests(unittest.TestCase):
 def test_exact_anchor_counts_and_reversible_hash_binding(self):
  fixture='\n'.join(old+'\n' for old,new,count in m.EDITS for _ in range(count)).encode()
  with patch.object(m,'BASES',{m.b.digest(fixture)}):
   planned=m.transform(fixture)
   self.assertEqual(m.transform(planned),planned)
   with self.assertRaises(m.r.inv.o.SafeError):m.transform(planned+b'drift')
 def test_unknown_source_cannot_be_uploaded_as_repaired(self):
  with self.assertRaises(m.r.inv.o.SafeError):m.transform(b'unknown code')
 def test_scoped_endpoints_exclude_other_workers_and_data_deletion(self):
  client=object.__new__(m.Client);client.root='/fixed/';client.token='fixture'  # allow-secret: test client object, not credential material
  with self.assertRaises(m.r.inv.o.SafeError):client.send('/fixed/other','PUT',b'')
  with self.assertRaises(m.r.inv.o.SafeError):client.send('/fixed/'+m.UCC+'/schedules','DELETE',b'')
 def test_metadata_uses_inheritance_and_only_changes_the_proven_target(self):
  settings={'bindings':[{'name':'SECRET','type':'plain_text','text':'private-value'},
   {'name':'UCC_STAGING','type':'service','service':m.UCC}]}
  value=m.metadata(settings,m.SCHED)
  self.assertNotIn('private-value',str(value));self.assertEqual(value['bindings'][-1]['entrypoint'],'KvIncidentScheduledIngress')
  with self.assertRaises(m.r.inv.o.SafeError):m.metadata({'bindings':[]},m.SCHED)
