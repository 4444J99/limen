import datetime as dt
import io
import json
import time
import unittest
from unittest.mock import patch
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

class KvObservationStateTests(unittest.TestCase):
 # One test per state. Only observed and observed_zero may verify headroom.
 D1={'2026-09-24':{'rowsRead':1,'rowsWritten':1}}
 def day(self,ops,coverage='completed_utc_day'):
  kv=[{'date':'2026-09-24','coverage':coverage,'account_operations':ops,'target_namespace_operations':{}}]
  return m.build_days(kv,self.D1,dt.date(2026,9,25))[0]

 def test_observed_counts_verify_headroom(self):
  day=self.day({'read':5,'write':4,'list':3,'delete':2})
  self.assertEqual(set(day['kv_observation'].values()),{m.OBSERVED})
  self.assertTrue(day['observed_20_percent_headroom'])
  self.assertEqual(m.classify(True,[day]),'VERIFIED_WINDOW')

 def test_observed_zero_only_when_source_reports_a_zero_row(self):
  day=self.day({'read':5,'write':4,'list':3,'delete':0})
  self.assertEqual(day['kv_observation']['delete'],m.OBSERVED_ZERO)
  self.assertTrue(day['observed_20_percent_headroom'])
  self.assertEqual(day['unobserved_kv_dimensions'],[])

 def test_absent_action_is_unobserved_not_zero(self):
  day=self.day({'read':5,'write':4,'list':3})
  self.assertEqual(day['kv_observation']['delete'],m.UNOBSERVED)
  self.assertNotIn('delete',day['kv'])
  self.assertFalse(day['observed_20_percent_headroom'])
  self.assertEqual(m.classify(True,[day]),'ACTION_REQUIRED')

 def test_malformed_values_fail_closed_without_crashing(self):
  for bad in ('0',None,True,-1,float('nan'),float('inf'),[0]):
   day=self.day({'read':5,'write':4,'list':3,'delete':bad})
   self.assertEqual(day['kv_observation']['delete'],m.MALFORMED,bad)
   self.assertFalse(day['observed_20_percent_headroom'])
  # non-object operations: every action malformed
  day=self.day(['read'])
  self.assertEqual(set(day['kv_observation'].values()),{m.MALFORMED})
  self.assertFalse(day['observed_20_percent_headroom'])

 def test_incomplete_day_fails_closed_even_with_all_four_actions(self):
  day=self.day({'read':5,'write':4,'list':3,'delete':0},coverage='partial_day')
  self.assertEqual(set(day['kv_observation'].values()),{m.INCOMPLETE})
  self.assertFalse(day['observed_20_percent_headroom'])
  self.assertEqual(m.classify(True,[day]),'ACTION_REQUIRED')

 def test_over_cap_observed_value_is_not_headroom(self):
  day=self.day({'read':5,'write':4,'list':3,'delete':801})
  self.assertEqual(day['kv_observation']['delete'],m.OBSERVED)
  self.assertFalse(day['observed_20_percent_headroom'])

 def test_summarizer_errors_map_to_explicit_states(self):
  self.assertEqual(m.usage_observation('analytics_count_invalid'),m.MALFORMED)
  self.assertEqual(m.usage_observation('analytics_dimension_invalid'),m.MALFORMED)
  self.assertEqual(m.usage_observation('analytics_missing_or_truncated'),m.INCOMPLETE)
  self.assertEqual(m.usage_observation('anything_else'),m.INCOMPLETE)


class ObservationTests(unittest.TestCase):
 class Client:
  aid='test-account'
  token='test-token'
  db=None
  def __init__(self, fail=False):self.fail=fail
  def settings(self,name):
   return {'bindings':[{'type':'d1','name':'SCHED_DB','database_id':'private-scheduler-db'}]
    if name=='ops-scheduler-production' else []}
  def crons(self,name):return ['* * * * *'] if name=='ops-scheduler-production' else []
  def request(self,path,method,data):
   query=json.loads(data)['sql']
   if query==m.recovery_baseline.CONTROL:
    activation=int((dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=2)).timestamp()*1000)
    rows=[{'source_sha':m.recovery_baseline.SOURCE,'enabled':1,'activate_after':activation}]
   elif query==m.recovery_baseline.QUEUE:
    rows=[{'target':name,'oldest_pending_at':None} for name in m.TARGET_AGES]
   else:raise AssertionError(query)
   return [{'success':True,'results':rows}]
  def sql(self,statement,params):
   if self.fail:raise m.r.inv.o.SafeError('release_http_400 private-provider-body private-token')
   now=time.time()*1000
   return [{'payload':json.dumps({'targetStates':{
    name:{'lastStatus':'success','lastCompletedAt':now} for name in m.TARGET_AGES}})}]

 def public(self,name,path):
  if path=='/healthz':return 200,{'revision':m.EXPECTED_REVISION}
  return 200,{'_status_snapshot':{'revision':m.EXPECTED_REVISION,'stale':False,
   'observed_at':dt.datetime.now(dt.timezone.utc).isoformat()}}

 def analytics(self,read=5000001,complete=False):
  today=dt.datetime.now(dt.timezone.utc).date()
  days=[today.isoformat()]
  if complete:days.append((today-dt.timedelta(days=1)).isoformat())
  kv=[];d1=[]
  for day in days:
   if complete:
    kv.extend({'sum':{'requests':0},'dimensions':{'date':day,'actionType':operation,
     'namespaceId':'private-kv-id'}} for operation in ('read','write','list','delete'))
   d1.append({'sum':{'rowsRead':read,'rowsWritten':1},'dimensions':{
    'date':day,'databaseId':'private-scheduler-db'}})
  return {'data':{'viewer':{'accounts':[{'kvOperationsAdaptiveGroups':kv,
   'd1AnalyticsAdaptiveGroups':d1}]}}}

 def observe(self,client,analytics):
  def open_query(request,timeout):
   self.assertEqual(json.loads(request.data)['query'],m.QUERY)
   return io.BytesIO(json.dumps(analytics).encode())
  with patch.object(m.recovery_baseline,'NOT_BEFORE',0),patch.object(m.r,'public',side_effect=self.public),patch.object(
    m.r.inv.o.OPENER,'open',side_effect=open_query):
   return m.observe(client)

 def test_d1_failure_retains_products_topology_and_current_exhaustion(self):
  report=self.observe(self.Client(fail=True),self.analytics())
  self.assertEqual(report['state'],'ACTION_REQUIRED')
  self.assertFalse(report['runtime_ok']);self.assertFalse(report['complete_window_ok'])
  self.assertTrue(report['product_endpoints_ok'])
  self.assertEqual(len(report['products']),3)
  production=report['schedulers']['ops-scheduler-production']
  self.assertEqual(production['cron'],['* * * * *'])
  self.assertEqual(production['execution_error'],'scheduler_execution_unavailable')
  self.assertEqual(report['failed_active_jobs'],sorted(m.TARGET_AGES))
  self.assertTrue(all(not value['healthy'] for value in production['jobs'].values()))
  self.assertEqual(report['quota_now']['state'],'AT_OR_OVER_REPORTED_LIMIT')
  self.assertEqual(report['quota_now']['metrics']['d1.rowsRead']['observed'],5000001)
  self.assertEqual(report['mutations'],0)
  self.assertNotIn('private-',json.dumps(report))

 def test_database_groups_sum_account_usage_and_keep_distinct_safe_attribution(self):
  analytics=self.analytics(read=3000000)
  rows=analytics['data']['viewer']['accounts'][0]['d1AnalyticsAdaptiveGroups']
  day=rows[0]['dimensions']['date']
  for database in ('private-other-one','private-other-two'):
   rows.append({'sum':{'rowsRead':1000001,'rowsWritten':2},'dimensions':{
    'date':day,'databaseId':database}})
  report=self.observe(self.Client(),analytics)
  current=next(row for row in report['usage']['days'] if row['date']==day)
  self.assertEqual(current['d1'],{'rowsRead':5000002,'rowsWritten':5})
  attributed=current['database_operations']
  self.assertEqual(attributed['ops-scheduler-production']['rowsRead'],3000000)
  self.assertEqual(len(attributed),3)
  self.assertEqual(sum(row['rowsRead'] for row in attributed.values()),5000002)
  self.assertTrue(all(name=='ops-scheduler-production' or
   name.startswith('unattributed_database_') for name in attributed))
  self.assertNotIn('private-',json.dumps(report))
  self.assertEqual(report['quota_now']['state'],'AT_OR_OVER_REPORTED_LIMIT')

 def test_all_observed_healthy_runtime_and_complete_window_remain_verified(self):
  report=self.observe(self.Client(),self.analytics(read=1,complete=True))
  self.assertTrue(report['runtime_ok']);self.assertTrue(report['complete_window_ok'])
  self.assertEqual(report['state'],'VERIFIED_WINDOW')

 def test_invalid_database_or_date_dimension_is_not_published(self):
  for changes in ({'databaseId':None},{'date':'private-date'}):
   analytics=self.analytics()
   analytics['data']['viewer']['accounts'][0]['d1AnalyticsAdaptiveGroups'][0]['dimensions'].update(changes)
   with self.assertRaises(m.r.inv.o.SafeError) as error:
    self.observe(self.Client(),analytics)
   self.assertNotIn('private-',str(error.exception))

 def test_shared_database_is_labeled_as_a_database(self):
  owners={}
  m.record_owner(owners,'private-db','edgarflash','shared_database')
  m.record_owner(owners,'private-db','ops-scheduler-production','shared_database')
  self.assertEqual(owners['private-db'],'shared_database')

 def kv_rows(self,analytics):
  return analytics['data']['viewer']['accounts'][0]['kvOperationsAdaptiveGroups']

 def test_whole_response_malformed_is_reported_and_unobserved(self):
  analytics=self.analytics(read=1,complete=True)
  self.kv_rows(analytics)[0]['sum']['requests']='12'
  with self.assertRaises(m.r.inv.o.SafeError) as error:
   self.observe(self.Client(),analytics)
  self.assertEqual(str(error.exception),'kv_usage_malformed')

 def test_whole_response_incomplete_truncated_or_rejected(self):
  analytics=self.analytics(read=1,complete=True)
  rows=self.kv_rows(analytics)
  rows.extend([dict(rows[0])]*10000)
  with self.assertRaises(m.r.inv.o.SafeError) as error:
   self.observe(self.Client(),analytics)
  self.assertEqual(str(error.exception),'kv_usage_incomplete')
  analytics=self.analytics(read=1,complete=True);analytics['errors']=[{'message':'private-provider-text'}]
  with self.assertRaises(m.r.inv.o.SafeError) as error:
   self.observe(self.Client(),analytics)
  self.assertEqual(str(error.exception),'kv_usage_incomplete')
  self.assertNotIn('private-',str(error.exception))

 def test_main_publishes_observation_state_and_fails(self):
  for code,state in (('kv_usage_malformed','malformed'),('kv_usage_incomplete','incomplete')):
   with patch.object(m.r,'ReleaseClient'),patch.object(m,'observe',side_effect=m.r.inv.o.SafeError(code)),patch('sys.stdout',new=io.StringIO()) as out,\
     patch.dict(m.os.environ,{},clear=True):
    self.assertEqual(m.main(),1)
   report=json.loads(out.getvalue())
   self.assertEqual(report['state'],'UNOBSERVED');self.assertEqual(report['kv_observation'],state)

 def test_absent_delete_in_live_shape_stays_action_required(self):
  # Mirrors run 39049441086: read/write/list rows only, far under caps.
  analytics=self.analytics(read=1,complete=True)
  rows=self.kv_rows(analytics)
  rows[:]=[row for row in rows if row['dimensions']['actionType']!='delete']
  for row in rows:row['sum']['requests']=5
  report=self.observe(self.Client(),analytics)
  completed=[d for d in report['usage']['days'] if d['completed_post_rollout_window']]
  self.assertEqual(completed[0]['kv_observation']['delete'],m.UNOBSERVED)
  self.assertNotIn('delete',completed[0]['kv'])
  self.assertFalse(report['complete_window_ok'])
  self.assertEqual(report['state'],'ACTION_REQUIRED')

 def test_stale_workers_stay_unhealthy_whatever_the_analytics_say(self):
  # Every KV action affirmatively observed and the window verified: stale
  # edgarflash/vulnpulse must still fail runtime and the witness.
  class Stale(self.Client):
   def sql(self,statement,params):
    now=time.time()*1000
    states={name:{'lastStatus':'success','lastCompletedAt':now} for name in m.TARGET_AGES}
    states['edgarflash']={'lastStatus':'uncertain','lastCompletedAt':now-1883449000,'lastFailureCode':'unclassified_failure'}
    states['vulnpulse']={'lastStatus':'uncertain','lastCompletedAt':now-1830380000,'lastFailureCode':'timeout'}
    return [{'payload':json.dumps({'targetStates':states})}]
  for delete in (0,3):
   analytics=self.analytics(read=1,complete=True)
   for row in self.kv_rows(analytics):
    row['sum']['requests']=delete if row['dimensions']['actionType']=='delete' else 5
   report=self.observe(Stale(),analytics)
   self.assertTrue(report['complete_window_ok'])
   jobs=report['schedulers']['ops-scheduler-production']['jobs']
   self.assertFalse(jobs['edgarflash']['healthy']);self.assertFalse(jobs['vulnpulse']['healthy'])
   self.assertFalse(report['runtime_ok'])
   self.assertEqual(report['state'],'ACTION_REQUIRED')
