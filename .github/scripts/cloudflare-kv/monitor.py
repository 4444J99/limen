#!/usr/bin/env python3
"""Read-only post-release witness: real jobs and both storage budgets."""
import datetime as dt
import json
import math
import os
from pathlib import Path
import sys
import time
import urllib.request
import release as r

FIRST_COMPLETE_DAY = '2026-09-24'
TARGET_AGES = {'edgarflash':600000,'bountyscope':7200000,'trendpulse':28800000,
               'vulnpulse':172800000,'ucc-staging':43200000,'ucc-production':43200000}
QUERY = '''query RecoveryUsage($account: string!, $start: Date!, $end: Date!) {
 viewer { accounts(filter:{accountTag:$account}) {
  kvOperationsAdaptiveGroups(limit:10000,filter:{date_geq:$start,date_leq:$end}) {
   sum {requests} dimensions {date actionType namespaceId}
  }
  d1AnalyticsAdaptiveGroups(limit:10000,filter:{date_geq:$start,date_leq:$end}) {
   sum {rowsRead rowsWritten} dimensions {date}
  }
 } }
}'''

def project_state(state, now):
 out={}
 for name,limit in TARGET_AGES.items():
  value=state.get('targetStates',{}).get(name,{})
  completed=value.get('lastCompletedAt',0)
  age=now-completed if isinstance(completed,(float,int)) and completed else None
  status=value.get('lastStatus')
  out[name]={'last_status':status if status in ('success','failure','timeout','skipped') else 'unknown',
             'last_completion_age_seconds':round(age/1000) if age is not None else None,
             'healthy':status=='success' and age is not None and 0<=age<=limit}
 return out


def record_owner(owners, namespace_id, name):
 current=owners.get(namespace_id)
 if current is None:
  owners[namespace_id]=name
 elif current != name:
  owners[namespace_id]='shared_namespace'


def build_days(kv_days, d1, today):
 by_date={row['date']:row for row in kv_days}
 previous=today-dt.timedelta(days=1)
 expected={previous.isoformat()} if previous>=dt.date.fromisoformat(FIRST_COMPLETE_DAY) else set()
 days=[]
 for date in sorted(set(by_date)|expected):
  row=by_date.get(date,{})
  ops=row.get('account_operations',{})
  storage=d1.get(date)
  complete=date<today.isoformat() and date>=FIRST_COMPLETE_DAY
  required={'read','write','list','delete'}
  within=(complete and required.issubset(ops) and storage is not None
    and ops['read']<=80000 and ops['write']<=800 and ops['list']<=800
    and ops['delete']<=800 and storage['rowsRead']<=4000000 and storage['rowsWritten']<=80000)
  days.append({'date':date,'coverage':row.get('coverage','unobserved'),'kv':ops,'d1':storage,
               'namespace_operations':row.get('target_namespace_operations',{}),
               'completed_post_rollout_window':complete,'observed_20_percent_headroom':bool(within),
               'unobserved_kv_dimensions':sorted(required-ops.keys())})
 return days


def usage(client, owners):
 now=dt.datetime.now(dt.timezone.utc)
 params={'query':QUERY,'variables':{'account':client.aid,
   'start':(now.date()-dt.timedelta(days=1)).isoformat(),'end':now.date().isoformat()}}
 request=urllib.request.Request(r.inv.o.API+'/graphql',data=json.dumps(params).encode(),
  headers={'Authorization':'Bearer '+client.token,'Content-Type':'application/json'})
 with r.inv.o.OPENER.open(request,timeout=20) as response:body=r.inv.o.decode_response(response)
 if body.get('errors'):raise r.inv.o.SafeError('usage_query_rejected')
 accounts=body['data']['viewer']['accounts']
 if len(accounts)!=1:raise r.inv.o.SafeError('usage_account_invalid')
 data=accounts[0]
 kv=r.inv.o.summarize_operations(data.get('kvOperationsAdaptiveGroups'),owners,now.date().isoformat())
 rows=data.get('d1AnalyticsAdaptiveGroups')
 if not isinstance(rows,list) or len(rows)>=10000:raise r.inv.o.SafeError('d1_usage_incomplete')
 d1={}
 for row in rows:
  values=row['sum'];date=row['dimensions']['date']
  if any(isinstance(values.get(k),bool) or not isinstance(values.get(k),(int,float)) or not math.isfinite(values[k]) or values[k]<0 for k in ('rowsRead','rowsWritten')):
   raise r.inv.o.SafeError('d1_usage_invalid')
  d1[date]={k:values[k] for k in ('rowsRead','rowsWritten')}
 return {'days':build_days(kv['days'],d1,now.date()),
         'qualification':'adaptive analytics, not exact billing or proof of successful operations; absent operation dimensions remain unobserved'}


def observe(client):
 report={'observed_at':dt.datetime.now(dt.timezone.utc).isoformat(),'mode':'read_only',
         'mutations':0,'products':{},'schedulers':{},'first_complete_day':FIRST_COMPLETE_DAY}
 owners={}
 for name in r.PRODUCTS:
  for binding in client.settings(name)['bindings']:
   if binding['type']=='kv_namespace':record_owner(owners,binding['namespace_id'],name)
  code,body=r.public(name,'/healthz');sc,status=r.public(name,'/api/status')
  snapshot=status.get('_status_snapshot',{})
  report['products'][name]={'liveness_http':code,'status_http':sc,
   'revision_verified':body.get('revision')==r.REVISION and snapshot.get('revision')==r.REVISION,
   'snapshot_stale':snapshot.get('stale'),'snapshot_observed_at':snapshot.get('observed_at')}
 for name in (*r.DUPLICATES,'ops-scheduler-production'):
  entry={'cron':client.crons(name)}
  settings=client.settings(name)
  for binding in settings['bindings']:
   if binding['type']=='kv_namespace':record_owner(owners,binding['namespace_id'],name)
  databases=[b for b in settings['bindings'] if b['type']=='d1' and b['name']=='SCHED_DB']
  if databases:
   client.db=databases[0]['database_id']
   rows=client.sql(r.STATE,('scheduler:state',))
   entry['jobs']=project_state(json.loads(rows[0]['payload']) if rows else {},time.time()*1000)
  report['schedulers'][name]=entry
 report['usage']=usage(client, owners)
 products_ok=all(v['liveness_http']==200 and v['status_http']==200 and v['revision_verified'] and v['snapshot_stale'] is False for v in report['products'].values())
 topology_ok=all(report['schedulers'][n]['cron']==[] for n in r.DUPLICATES) and report['schedulers']['ops-scheduler-production']['cron']==['* * * * *']
 jobs=report['schedulers']['ops-scheduler-production'].get('jobs',{})
 jobs_ok=len(jobs)==len(TARGET_AGES) and all(v['healthy'] for v in jobs.values())
 window_ok=any(d['observed_20_percent_headroom'] for d in report['usage']['days'])
 report['runtime_ok']=products_ok and topology_ok and jobs_ok
 report['complete_window_ok']=window_ok
 completed=[d for d in report['usage']['days'] if d['completed_post_rollout_window']]
 report['state']=classify(report['runtime_ok'],completed)
 return report


def classify(runtime_ok, completed):
 if not runtime_ok or any(not d['observed_20_percent_headroom'] for d in completed):
  return 'ACTION_REQUIRED'
 return 'VERIFIED_WINDOW' if completed else 'OBSERVING'

def main():
 try:report=observe(r.ReleaseClient(os.environ.get('CLOUDFLARE_API_TOKEN','')))
 except r.inv.o.SafeError as error:report={'state':'UNOBSERVED','error':str(error),'mutations':0}
 except Exception:report={'state':'UNOBSERVED','error':'witness_failed','mutations':0}
 text=json.dumps(report,indent=2,sort_keys=True)
 print(text)
 if os.environ.get('RUNNER_TEMP'):
  (Path(os.environ['RUNNER_TEMP'])/'kv-recovery-witness.json').write_text(text)
 if os.environ.get('GITHUB_STEP_SUMMARY'):
  with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:f.write('## KV recovery witness\n```json\n'+text+'\n```\n')
 return int(report.get('state') in ('UNOBSERVED','ACTION_REQUIRED'))

if __name__=='__main__':sys.exit(main())
