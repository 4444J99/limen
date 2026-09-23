import unittest
from unittest.mock import patch
import diagnostic_replay as m

class DiagnosticReplayTests(unittest.TestCase):
 def test_exact_index_anchor_and_idempotence(self):
  source=m.ANCHOR.encode()
  with patch.object(m.b,'scheduler_patch',side_effect=lambda b:b):
   planned=m.patch_index(source)
   self.assertEqual(m.patch_index(planned),planned)
   with self.assertRaises(m.b.r.inv.o.SafeError):m.patch_index(source+source)
 def test_source_scope_refuses_other_workers(self):
  client=object.__new__(m.Client)
  with self.assertRaises(m.b.r.inv.o.SafeError):client.source('other-worker')
 def test_unknown_live_source_is_not_rewritten(self):
  with self.assertRaises(m.b.r.inv.o.SafeError):m.patch_index(b'unknown')
  with self.assertRaises(m.b.r.inv.o.SafeError):m.patch_replay(b'unknown')
