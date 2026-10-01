import json
import unittest
import telemetry_probe as m
class TelemetryTests(unittest.TestCase):
 def test_query_is_bounded_to_owned_workers_and_one_hour(self):
  p=m.payload(m.TARGETS[0],3600001)
  self.assertEqual(p['limit'],100);self.assertEqual(p['timeframe'],{'from':1,'to':3600001})
  self.assertEqual(p['parameters']['filters'][0]['value'],m.TARGETS[0])
  with self.assertRaises(m.s.r.inv.o.SafeError):m.payload('unrelated',1)
 def test_private_values_are_never_projected(self):
  p=m.project([{'message':'D1_ERROR: no such column: jobs.retry_at: SQLITE_ERROR','stack':'Error\n at drainJobs (index.js:122:9)',
                'headers':{'Authorization':'private-token'},'request':{'url':'private-url'},'secret':'private-secret'}])
  self.assertNotIn('private-',json.dumps(p));self.assertEqual(p['diagnoses'],[{'category':'missing_column','schema_identifier':'jobs.retry_at'}])
  self.assertEqual(p['stack_sites'],[{'function':'drainJobs','line':122}])
 def test_runtime_limits_have_fixed_categories(self):
  self.assertEqual(m.project({'message':'D1_ERROR: Too many requests'})['signals'],['d1_request_limit'])
  self.assertEqual(m.project({'message':'Too many subrequests.'})['signals'],['subrequest_limit'])
