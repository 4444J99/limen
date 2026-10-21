#!/usr/bin/env python3
"""Read-only post-release witness: real jobs and both storage budgets."""
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import urllib.request
import release as r
from quota_status import annotate, safe_failure
from execution_health import health, read_receipts
import recovery_baseline

FIRST_COMPLETE_DAY = '2026-09-24'
EXPECTED_REVISION = 'kv-recovery-d1-20260923-v2'
TARGET_AGES = {'edgarflash':600000,'bountyscope':7200000,'trendpulse':28800000,
               'vulnpulse':172800000,'ucc-staging':43200000,'ucc-production':43200000}
QUERY = '''query RecoveryUsage($account: string!, $start: Date!, $end: Date!) {
 viewer { accounts(filter:{accountTag:$account}) {
  kvOperationsAdaptiveGroups(limit:10000,filter:{date_geq:$start,date_leq:$end}) {
   sum {requests} dimensions {date actionType namespaceId}
  }
  d1AnalyticsAdaptiveGroups(limit:10000,filter:{date_geq:$start,date_leq:$end}) {
   sum {rowsRead rowsWritten} dimensions {date databaseId}
  }
 } }
}'''

def project_state(state, now, receipts=None):
 out={}
 for name,limit in TARGET_AGES.items():
  value=state.get('targetStates',{}).get(name,{})
  receipt=(receipts or {}).get(value.get('lastRunId'))
  out[name]={**safe_failure(value), **health(name,value,now,limit,receipt)}
 return out


def record_owner(owners, namespace_id, name, shared_label='shared_namespace'):
 current=owners.get(namespace_id)
 if current is None:
  owners[namespace_id]=name
 elif current != name:
  owners[namespace_id]=shared_label


# KV observation semantics (per UTC day, per actionType). Cloudflare's
# kvOperationsAdaptiveGroups is an adaptive-sampled group-by over recorded
# operation events: group results list only dimension tuples that had data,
# and counts are estimates. Cloudflare documents no zero-row or
# expected-dimension contract (developers.cloudflare.com/kv/observability/
# metrics-analytics, /analytics/graphql-api/sampling), so an absent actionType
# row is silence, not an affirmative zero. Comparing an ungrouped total with
# the per-action sum adds no evidence (both aggregate the same events), and an
# actionType filter is not documented to return a zero row. Therefore:
#   observed       a well-formed row reported a positive count
#   observed_zero  the source itself returned a well-formed row whose count is 0
#                  (the only affirmative zero; never synthesized by this script)
#   unobserved     no row for the action: NOT zero, so headroom stays unverified
#   malformed      the reported value has the wrong type/shape: fail closed
#   incomplete     the day's KV evidence is partial (query rejected, truncated
#                  at the row limit, or a non-final UTC day): fail closed
# Only observed and observed_zero may verify headroom. Whole-response
# malformed/incomplete answers are reported via usage_observation() below.
KV_ACTIONS=('read','write','list','delete')
KV_CAPS={'read':80000,'write':800,'list':800,'delete':800}
OBSERVED,OBSERVED_ZERO,UNOBSERVED,MALFORMED,INCOMPLETE=(
 'observed','observed_zero','unobserved','malformed','incomplete')
VERIFIABLE=frozenset((OBSERVED,OBSERVED_ZERO))


def kv_observation(ops, action, coverage='completed_utc_day'):
 if not isinstance(ops,dict):return MALFORMED
 if coverage in ('partial_day',INCOMPLETE):return INCOMPLETE
 if action not in ops:return UNOBSERVED
 value=ops[action]
 if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
  return MALFORMED
 return OBSERVED_ZERO if value==0 else OBSERVED


def build_days(kv_days, d1, today, database_days=None, first_complete_day=FIRST_COMPLETE_DAY):
 by_date={row['date']:row for row in kv_days}
 previous=today-dt.timedelta(days=1)
 expected={previous.isoformat()} if first_complete_day and previous>=dt.date.fromisoformat(first_complete_day) else set()
 days=[]
 for date in sorted(set(by_date)|set(d1)|expected):
  row=by_date.get(date,{})
  ops=row.get('account_operations',{})
  storage=d1.get(date)
  complete=bool(first_complete_day and date<today.isoformat() and date>=first_complete_day)
  # A row from an earlier summarizer run that labelled a past day partial is
  # still incomplete evidence; a past day with no row at all is unobserved.
  coverage=row.get('coverage','unobserved')
  states={a:kv_observation(ops,a,coverage if row else 'completed_utc_day') for a in KV_ACTIONS}
  within=(complete and all(state in VERIFIABLE for state in states.values()) and storage is not None
    and all(ops[a]<=KV_CAPS[a] for a in KV_ACTIONS)
    and storage['rowsRead']<=4000000 and storage['rowsWritten']<=80000)
  keys=ops.keys() if isinstance(ops,dict) else ()
  days.append({'date':date,'coverage':coverage,'kv':ops,'d1':storage,
               'database_operations':(database_days or {}).get(date,{}),
               'namespace_operations':row.get('target_namespace_operations',{}),
               'completed_post_rollout_window':complete,'observed_20_percent_headroom':bool(within),
               'kv_observation':states,
               'unobserved_kv_dimensions':sorted(set(KV_ACTIONS)-set(keys))})
 return days


# Fixed SafeError codes from the shared KV summarizer, mapped to observation
# states. Anything unrecognised is incomplete: never a pass, never a zero.
MALFORMED_CODES=frozenset(('analytics_dimension_invalid','analytics_count_invalid',
 'analytics_namespace_invalid','provider_rows_invalid','provider_object_invalid'))


def usage_observation(code):
 return MALFORMED if code in MALFORMED_CODES else INCOMPLETE


def summarize_kv(rows, owners, today):
 try:return r.inv.o.summarize_operations(rows,owners,today)
 except r.inv.o.SafeError as error:
  raise r.inv.o.SafeError('kv_usage_'+usage_observation(str(error))) from None


def usage(client, owners, database_owners=None, first_complete_day=FIRST_COMPLETE_DAY):
 now=dt.datetime.now(dt.timezone.utc)
 params={'query':QUERY,'variables':{'account':client.aid,
   'start':(now.date()-dt.timedelta(days=1)).isoformat(),'end':now.date().isoformat()}}
 request=urllib.request.Request(r.inv.o.API+'/graphql',data=json.dumps(params).encode(),
  headers={'Authorization':'Bearer '+client.token,'Content-Type':'application/json'})
 with r.inv.o.OPENER.open(request,timeout=20) as response:body=r.inv.o.decode_response(response)
 # A rejected query is incomplete KV evidence, never an empty (zero) answer.
 if body.get('errors'):raise r.inv.o.SafeError('kv_usage_incomplete')
 accounts=body['data']['viewer']['accounts']
 if len(accounts)!=1:raise r.inv.o.SafeError('usage_account_invalid')
 data=accounts[0]
 kv=summarize_kv(data.get('kvOperationsAdaptiveGroups'),owners,now.date().isoformat())
 rows=data.get('d1AnalyticsAdaptiveGroups')
 if not isinstance(rows,list) or len(rows)>=10000:raise r.inv.o.SafeError('d1_usage_incomplete')
 d1={};database_days={}
 for row in rows:
  values=row['sum'];date=row['dimensions']['date']
  try:valid_date=dt.date.fromisoformat(date).isoformat()==date
  except (TypeError,ValueError):valid_date=False
  if not valid_date:raise r.inv.o.SafeError('d1_date_dimension_invalid')
  if any(isinstance(values.get(k),bool) or not isinstance(values.get(k),(int,float)) or not math.isfinite(values[k]) or values[k]<0 for k in ('rowsRead','rowsWritten')):
   raise r.inv.o.SafeError('d1_usage_invalid')
  database=row['dimensions'].get('databaseId')
  if not isinstance(database,str) or not database or len(database)>128:
   raise r.inv.o.SafeError('d1_database_dimension_invalid')
  owner=(database_owners or {}).get(database,
   'unattributed_database_'+hashlib.sha256(database.encode()).hexdigest()[:12])
  total=d1.setdefault(date,{'rowsRead':0,'rowsWritten':0})
  attributed=database_days.setdefault(date,{}).setdefault(owner,{'rowsRead':0,'rowsWritten':0})
  for key in ('rowsRead','rowsWritten'):
   total[key]+=values[key];attributed[key]+=values[key]
 return {'days':build_days(kv['days'],d1,now.date(),database_days,first_complete_day),
         'qualification':'adaptive analytics, not exact billing or proof of successful operations; absent operation dimensions remain unobserved',
         'semantics':'observed|observed_zero verify headroom; unobserved, malformed and incomplete fail closed; absence is never zero'}


def observe(client):
 report={'observed_at':dt.datetime.now(dt.timezone.utc).isoformat(),'mode':'read_only',
         'mutations':0,'products':{},'schedulers':{},'first_complete_day':FIRST_COMPLETE_DAY}
 owners={};database_owners={};baseline=None
 for name in r.PRODUCTS:
  for binding in client.settings(name)['bindings']:
   if binding['type']=='kv_namespace':record_owner(owners,binding['namespace_id'],name)
   if binding['type']=='d1':record_owner(database_owners,binding['database_id'],name,'shared_database')
  code,body=r.public(name,'/healthz');sc,status=r.public(name,'/api/status')
  snapshot=status.get('_status_snapshot',{})
  report['products'][name]={'liveness_http':code,'status_http':sc,
   'revision_verified':body.get('revision')==EXPECTED_REVISION and snapshot.get('revision')==EXPECTED_REVISION,
   'snapshot_stale':snapshot.get('stale'),'snapshot_observed_at':snapshot.get('observed_at')}
 for name in (*r.DUPLICATES,'ops-scheduler-production'):
  entry={'cron':client.crons(name)}
  settings=client.settings(name)
  for binding in settings['bindings']:
   if binding['type']=='kv_namespace':record_owner(owners,binding['namespace_id'],name)
   if binding['type']=='d1':record_owner(database_owners,binding['database_id'],name,'shared_database')
  databases=[b for b in settings['bindings'] if b['type']=='d1' and b['name']=='SCHED_DB']
  if databases:
   client.db=databases[0]['database_id']
   try:
    rows=client.sql(r.STATE,('scheduler:state',))
    state=json.loads(rows[0]['payload']) if rows else {}
    # A busy worker is not a failed worker. Require both an actual recent
    # completion and the exact still-live lease; never call the new run done.
    receipts=read_receipts(client,state,TARGET_AGES) if name=='ops-scheduler-production' else {}
    entry['jobs']=project_state(state,time.time()*1000,receipts)
    if name=='ops-scheduler-production':
     baseline=recovery_baseline.read(client,TARGET_AGES,time.time()*1000)
     entry['recovery']=baseline
     for target,job in entry['jobs'].items():
      completed=state.get('targetStates',{}).get(target,{}).get('lastCompletedAt',0)
      job['completed_after_activation']=type(completed) in (int,float) and completed>=baseline['activate_after']
      job['healthy']=job['healthy'] and job['completed_after_activation']
   except Exception:
    # D1 exhaustion must not erase independent product, topology or analytics
    # observations. Exception/provider text stays private; unknown jobs fail closed.
    entry['execution_error']='scheduler_execution_unavailable'
    entry['jobs']=project_state({},time.time()*1000)
  report['schedulers'][name]=entry
 report['first_complete_day']=baseline['first_complete_day'] if baseline else None
 report['usage']=usage(client, owners, database_owners,report['first_complete_day'])
 products_ok=all(v['liveness_http']==200 and v['status_http']==200 and v['revision_verified'] and v['snapshot_stale'] is False for v in report['products'].values())
 topology_ok=all(report['schedulers'][n]['cron']==[] for n in r.DUPLICATES) and report['schedulers']['ops-scheduler-production']['cron']==['* * * * *']
 jobs=report['schedulers']['ops-scheduler-production'].get('jobs',{})
 jobs_ok=len(jobs)==len(TARGET_AGES) and all(v['healthy'] for v in jobs.values())
 window_ok=any(d['observed_20_percent_headroom'] for d in report['usage']['days'])
 report['runtime_ok']=products_ok and topology_ok and jobs_ok
 report['complete_window_ok']=window_ok
 completed=[d for d in report['usage']['days'] if d['completed_post_rollout_window']]
 report['state']=classify(report['runtime_ok'],completed)
 return annotate(report)


def classify(runtime_ok, completed):
 if not runtime_ok or any(not d['observed_20_percent_headroom'] for d in completed):
  return 'ACTION_REQUIRED'
 return 'VERIFIED_WINDOW' if completed else 'OBSERVING'

def main():
 try:report=observe(r.ReleaseClient(os.environ.get('CLOUDFLARE_API_TOKEN','')))
 except r.inv.o.SafeError as error:
  report={'state':'UNOBSERVED','error':str(error),'mutations':0}
  if str(error).startswith('kv_usage_'):report['kv_observation']=str(error)[len('kv_usage_'):]
 except Exception:report={'state':'UNOBSERVED','error':'witness_failed','mutations':0}
 text=json.dumps(report,indent=2,sort_keys=True)
 print(text)
 if os.environ.get('RUNNER_TEMP'):
  (Path(os.environ['RUNNER_TEMP'])/'kv-recovery-witness.json').write_text(text)
 if os.environ.get('GITHUB_STEP_SUMMARY'):
  with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:f.write('## KV recovery witness\n```json\n'+text+'\n```\n')
 return int(report.get('state') in ('UNOBSERVED','ACTION_REQUIRED'))

if __name__=='__main__':sys.exit(main())
