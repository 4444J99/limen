import unittest
import monitor as m

class MonitorTests(unittest.TestCase):
 def test_missing_jobs_are_unknown_not_healthy(self):
  state=m.project_state({},1000000)
  self.assertEqual(len(state),6)
  self.assertTrue(all(not row['healthy'] for row in state.values()))
 def test_failed_or_stale_jobs_remain_actionable(self):
  state={'targetStates':{'edgarflash':{'lastStatus':'failure','lastCompletedAt':999999},
                          'bountyscope':{'lastStatus':'success','lastCompletedAt':1}}}
  result=m.project_state(state,20000000)
  self.assertFalse(result['edgarflash']['healthy']);self.assertFalse(result['bountyscope']['healthy'])
 def test_current_success_is_healthy(self):
  state={'targetStates':{n:{'lastStatus':'success','lastCompletedAt':1000000} for n in m.TARGET_AGES}}
  self.assertTrue(all(v['healthy'] for v in m.project_state(state,1000100).values()))
 def test_private_state_fields_are_not_projected(self):
  state={'targetStates':{'edgarflash':{'lastStatus':'private-secret','token':'private-token'}}}
  self.assertNotIn('private',str(m.project_state(state,1000100)))

 def test_window_failure_not_disguised_as_waiting(self):
  self.assertEqual(m.classify(True,[{'observed_20_percent_headroom':False}]),'ACTION_REQUIRED')
 def test_window_cannot_complete_before_full_day(self):
  self.assertEqual(m.classify(True,[]),'OBSERVING')
  self.assertEqual(m.classify(False,[{'observed_20_percent_headroom':True}]),'ACTION_REQUIRED')
 def test_completed_runtime_and_window_have_explicit_success(self):
  self.assertEqual(m.classify(True,[{'observed_20_percent_headroom':True}]),'VERIFIED_WINDOW')
