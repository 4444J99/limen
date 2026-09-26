import copy,json,unittest
import execution_health as m

NOW=1790358702000
RID='edgarflash:production:1790333460000:scheduled'
VALUE={'lastStatus':'running','lastCompletedAt':NOW-1000,'lastInvokedAt':NOW-500,'lastRunId':RID,'consecutiveFailures':0}
RECEIPT={'id':RID,'target':'edgarflash','state':'running','started_at':NOW-500,'lease_until':NOW+139500,'generation':448}

class HealthTests(unittest.TestCase):
 def test_real_recent_success_and_live_current_lease_are_healthy_but_not_completed(self):
  value=m.health('edgarflash',VALUE,NOW,600000,RECEIPT)
  self.assertTrue(value['healthy']);self.assertTrue(value['in_progress']);self.assertEqual(value['last_status'],'running')
 def test_running_without_prior_completion_or_receipt_never_passes(self):
  for value,receipt in [(dict(VALUE,lastCompletedAt=0),RECEIPT),(VALUE,None),(dict(VALUE,lastCompletedAt=NOW-600001),RECEIPT)]:
   self.assertFalse(m.health('edgarflash',value,NOW,600000,receipt)['healthy'])
 def test_stale_mismatched_or_unbounded_lease_never_passes(self):
  for key,v in [('lease_until',NOW-1),('lease_until',NOW+999999),('started_at',NOW-501),('id','other'),('target','ucc-staging'),('state','uncertain'),('generation',0)]:
   self.assertFalse(m.health('edgarflash',VALUE,NOW,600000,{**RECEIPT,key:v})['healthy'])
 def test_failed_uncertain_accepted_or_future_success_never_passes(self):
  for status in ['failure','timeout','uncertain','accepted','unknown']:
   self.assertFalse(m.health('edgarflash',dict(VALUE,lastStatus=status),NOW,600000,RECEIPT)['healthy'])
  for time in [True,float('nan'),float('inf'),NOW+1,0]:
   self.assertFalse(m.health('edgarflash',dict(VALUE,lastStatus='success',lastCompletedAt=time),NOW,600000)['healthy'])
 def test_retry_in_progress_does_not_erase_a_recent_failure(self):
  for changes in [{'consecutiveFailures':1},{'lastFailureCode':'authorization'}]:
   self.assertFalse(m.health('edgarflash',{**VALUE,**changes},NOW,600000,RECEIPT)['healthy'])
 def test_success_stays_healthy_without_extra_storage(self):
  self.assertTrue(m.health('edgarflash',dict(VALUE,lastStatus='success'),NOW,600000)['healthy'])
  class NoRequest:
   def request(self,*args):raise AssertionError('unneeded storage read')
  self.assertEqual(m.read_receipts(NoRequest(),{'targetStates':{'edgarflash':dict(VALUE,lastStatus='success')}},['edgarflash']),{})
 def test_projection_does_not_publish_unexpected_private_fields(self):
  result=m.health('edgarflash',{**VALUE,'secret':'private-value'},NOW,600000,{**RECEIPT,'token':'private-value'})
  self.assertNotIn('private',json.dumps(result))
 def test_read_is_bounded_to_registered_running_ids_and_never_writes_sql(self):
  class Client:
   aid='test-account';db='test-database'
   def request(self,path,method,data):
    payload=json.loads(data);self.payload=payload
    assert payload['sql'].startswith('SELECT ')
    return [{'success':True,'results':[RECEIPT]}]
  c=Client();found=m.read_receipts(c,{'targetStates':{'edgarflash':VALUE,'not-registered':VALUE}},['edgarflash'])
  self.assertEqual(list(found),[RID]);self.assertEqual(json.loads(c.payload['params'][0]),[RID])
 def test_other_rows_or_query_failure_cannot_supply_a_lease(self):
  class Client:
   aid='a';db='d'
   def request(self,*args):return [{'success':True,'results':[{**RECEIPT,'id':'other'}]}]
  with self.assertRaises(ValueError):m.read_receipts(Client(),{'targetStates':{'edgarflash':VALUE}},['edgarflash'])

if __name__=='__main__':unittest.main()
