import unittest
import monitor
from quota_status import safe_failure
from test_execution_health import VALUE, RECEIPT, NOW, RID

class RunningDiagnosticsTests(unittest.TestCase):
 def test_verified_running_job_does_not_receive_an_invented_failure(self):
  result=monitor.project_state({'targetStates':{'edgarflash':VALUE}},NOW,{RID:RECEIPT})['edgarflash']
  self.assertTrue(result['healthy']);self.assertEqual(result['last_status'],'running')
  self.assertIsNone(result['failure_code']);self.assertIsNone(result['failure_category'])
 def test_no_failure_label_does_not_make_a_missing_lease_healthy(self):
  result=monitor.project_state({'targetStates':{'edgarflash':VALUE}},NOW)['edgarflash']
  self.assertFalse(result['healthy']);self.assertIsNone(result['failure_code'])
 def test_actual_failures_and_unknown_counters_remain_visible(self):
  for changes in [{'consecutiveFailures':1},{'consecutiveFailures':None},{'consecutiveFailures':False},
    {'lastFailureCode':'authorization'},{'lastFailureDetail':{'category':'timeout'}},
    {'lastStatus':'uncertain'},{'lastStatus':'failure'},{'lastStatus':'accepted'}]:
   self.assertIsNotNone(safe_failure({**VALUE,**changes})['failure_code'])
  self.assertEqual(safe_failure({**VALUE,'lastFailureCode':'authorization'})['failure_code'],'authorization')
 def test_diagnostics_do_not_relax_the_complete_quota_window(self):
  self.assertEqual(monitor.classify(True,[{'observed_20_percent_headroom':False}]),'ACTION_REQUIRED')

if __name__=='__main__':unittest.main()
