import datetime as dt
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

 def test_missing_completed_day_is_explicit_and_actionable(self):
  days=m.build_days([],{},dt.date(2026,9,25))
  self.assertEqual([d['date'] for d in days],['2026-09-24'])
  self.assertEqual(days[0]['coverage'],'unobserved')
  self.assertFalse(days[0]['observed_20_percent_headroom'])
  self.assertEqual(m.classify(True,days),'ACTION_REQUIRED')

 def test_missing_delete_dimension_cannot_verify_headroom(self):
  kv=[{'date':'2026-09-24','coverage':'complete',
       'account_operations':{'read':1,'write':1,'list':1},
       'target_namespace_operations':{}}]
  d1={'2026-09-24':{'rowsRead':1,'rowsWritten':1}}
  day=m.build_days(kv,d1,dt.date(2026,9,25))[0]
  self.assertFalse(day['observed_20_percent_headroom'])
  self.assertEqual(day['unobserved_kv_dimensions'],['delete'])

 def test_shared_namespace_attribution_is_preserved(self):
  owners={}
  m.record_owner(owners,'ns-1','worker-a')
  m.record_owner(owners,'ns-1','worker-a')
  self.assertEqual(owners['ns-1'],'worker-a')
  m.record_owner(owners,'ns-1','worker-b')
  self.assertEqual(owners['ns-1'],'shared_namespace')
  m.record_owner(owners,'ns-1','worker-c')
  self.assertEqual(owners['ns-1'],'shared_namespace')

 def test_real_running_projection_requires_recent_success_and_matching_live_lease(self):
  from test_execution_health import VALUE,RECEIPT,NOW,RID
  state={'targetStates':{'edgarflash':VALUE}}
  before=m.project_state(state,NOW)['edgarflash']
  self.assertFalse(before['healthy']);self.assertEqual(before['last_status'],'running')
  after=m.project_state(state,NOW,{RID:RECEIPT})['edgarflash']
  self.assertTrue(after['healthy']);self.assertEqual(after['last_status'],'running')
  self.assertTrue(after['active_lease_verified'])

 def test_running_projection_never_erases_failure_or_marks_pending_business_complete(self):
  from test_execution_health import VALUE,RECEIPT,NOW,RID
  state={'targetStates':{'edgarflash':{**VALUE,'consecutiveFailures':1,'lastFailureCode':'timeout'}}}
  result=m.project_state(state,NOW,{RID:RECEIPT})['edgarflash']
  self.assertFalse(result['healthy']);self.assertEqual(result['last_status'],'running')
