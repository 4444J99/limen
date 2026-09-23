#!/usr/bin/env python3
"""Repair the proven per-invocation request overflow; retain queued work and one owner."""
import hashlib,json,os,time,urllib.request,urllib.error,uuid
from pathlib import Path
from email import policy
from email.parser import BytesParser
import release as r
import budget_recovery as b
import diagnostic_replay as d

UCC='ucc-mca-edge-staging'; SCHED='ops-scheduler-production'
BASES={'5f1ae8d557bcf4dcfa0688782877f1109a267666b0dda0d9105b2993ee45b2fb','21b3c1e68750464841a2213ff4860841c175fa4e9f1965d10304e1e81b18825e'}
IMPORT="import { meterEnv as __meterEnv, splitJob as __splitJob, budgetIngress as __budgetIngress } from './bounded-jobs.mjs';\n"
ENTRY_IMPORT="import { WorkerEntrypoint as __BudgetEntry } from 'cloudflare:workers';\n"
ENTRY_SUFFIX="\n// KV_BUDGET_INGRESS\nexport class KvIncidentScheduledIngress extends __BudgetEntry {\n  fetch(request) { return __budgetIngress(request, this.env, this.ctx, src_default); }\n}\n"
EDITS=[
 ('var DRAIN_BATCH = 25;','var DRAIN_BATCH = 1;',1),
 ('var ENRICHMENT_BATCH = 50;','var ENRICHMENT_BATCH = 1;',1),
 ("SELECT id FROM prospects WHERE enrichment_confidence IS NULL LIMIT 500","SELECT id FROM prospects WHERE enrichment_confidence IS NULL LIMIT 10",1),
 ('async function processJob(env2, job, budget) {','async function processJob(env2, job, budget) {\n  job = await __splitJob(env2, job);',1),
 ('batchSize: parsedPayload.batchSize ?? void 0,','batchSize: 1,',1),
 ('await drainJobs(env2, createInvocationBudget());','await drainJobs(env2, createInvocationBudget(12));',2),
 ('await drainWebhookDeliveries(env2);','await drainWebhookDeliveries(env2, 1);',2),
 ('async function scheduled(event, env2, ctx) {','async function scheduled(event, env2, ctx) {\n  const __meter = __meterEnv(env2); env2 = __meter.env;',1),
 ('async function runScheduled(payload, env2) {','async function runScheduled(payload, env2) {\n  const __meter = __meterEnv(env2); env2 = __meter.env;',1),
 ('const tasks = scheduledTasks2("0 0,2,6,12,18 * * *", payload.scheduledTime);','const tasks = payload.drainOnly === true ? [] : scheduledTasks2("0 0,2,6,12,18 * * *", payload.scheduledTime);',1),
 ('return { ok: true, rid, durationMs };','console.log("[ucc-budget] bounded pass", __meter.stats());\n    return { ok: true, rid, durationMs, budget: __meter.stats(), drainOnly: payload.drainOnly === true };',1),
]

def transform(raw):
 text=raw.decode()
 if text.startswith(IMPORT):
  restored=text[len(IMPORT):]
  if restored.startswith(ENTRY_IMPORT):
   if not restored.endswith(ENTRY_SUFFIX):raise r.inv.o.SafeError('bounded_entrypoint_drift')
   restored=restored[len(ENTRY_IMPORT):-len(ENTRY_SUFFIX)]
  for old,new,count in reversed(EDITS):
   if restored.count(new)!=count:raise r.inv.o.SafeError('bounded_reverse_anchor_drift')
   restored=restored.replace(new,old)
  if b.digest(restored.encode()) not in BASES:raise r.inv.o.SafeError('bounded_original_identity_drift')
  return raw
 if b.digest(raw) not in BASES:raise r.inv.o.SafeError('ucc_source_identity_drift')
 add_entry='KvIncidentScheduledIngress' not in text
 for old,new,count in EDITS:
  if text.count(old)!=count:raise r.inv.o.SafeError('bounded_patch_anchor_drift')
  text=text.replace(old,new)
 return (IMPORT+(ENTRY_IMPORT if add_entry else '')+text+(ENTRY_SUFFIX if add_entry else '')).encode()


def modules(kind,raw):
 if not kind.lower().startswith('multipart/'):return {'index.js':raw}
 msg=BytesParser(policy=policy.default).parsebytes(('Content-Type: '+kind+'\r\n\r\n').encode()+raw)
 out={}
 for part in msg.iter_parts():
  name=part.get_filename() or part.get_param('name',header='content-disposition')
  if name=='metadata':continue
  if name not in ('index.js','finishline.mjs','diagnosis.mjs','bounded-jobs.mjs') or name in out:raise r.inv.o.SafeError('bounded_module_refused')
  out[name]=part.get_payload(decode=True) or b''
 return out


def metadata(settings,name):
 result=b.metadata(settings)
 result['annotations']={'workers/message':'Bound actual invocation work and retain queued continuations','workers/tag':'ucc-budget-20260923'}
 if name==SCHED:
  bindings=[v for v in settings['bindings'] if v['name']=='UCC_STAGING']
  if len(bindings)!=1 or bindings[0].get('service')!=UCC:raise r.inv.o.SafeError('canonical_binding_drift')
  result['bindings']=[v for v in result['bindings'] if v['name']!='UCC_STAGING']+[
   {'name':'UCC_STAGING','type':'service','service':UCC,'entrypoint':'KvIncidentScheduledIngress'}]
 return result

class Client(r.ReleaseClient):
 def source(self,name):return modules(*self.raw(self.root+name+'/content/v2'))
 def upload_bounded(self,name,settings,files):
  if name not in (UCC,SCHED):raise r.inv.o.SafeError('bounded_upload_target_refused')
  boundary='bounded-'+uuid.uuid4().hex;parts=[]
  for key,value in [('metadata',json.dumps(metadata(settings,name)).encode()),*files.items()]:
   if key not in ('metadata','index.js','finishline.mjs','diagnosis.mjs','bounded-jobs.mjs'):raise r.inv.o.SafeError('bounded_part_refused')
   kind='application/json' if key=='metadata' else 'application/javascript+module'
   parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"; filename="{key}"\r\nContent-Type: {kind}\r\n\r\n').encode()+value+b'\r\n')
  parts.append(f'--{boundary}--\r\n'.encode())
  self.send(self.root+name+'?bindings_inherit=strict','PUT',b''.join(parts),'multipart/form-data; boundary='+boundary)
 def send(self,path,method,data,kind='application/json'):
  allowed=method=='PUT' and path in (self.root+UCC+'?bindings_inherit=strict',self.root+SCHED+'?bindings_inherit=strict',self.root+UCC+'/schedules')
  if not allowed:raise r.inv.o.SafeError('bounded_endpoint_refused')
  request=urllib.request.Request(r.inv.o.API+path,method=method,data=data,headers={'Authorization':'Bearer '+self.token,'Content-Type':kind})
  try:
   with r.inv.o.OPENER.open(request,timeout=60) as response:value=r.inv.o.decode_response(response)
  except urllib.error.HTTPError as error:raise r.inv.o.SafeError('bounded_upload_http_'+str(error.code)) from None
  if value.get('success') is not True:raise r.inv.o.SafeError('bounded_upload_failed')


def run(client):
 folder=Path(__file__).parent;helper=(folder/'bounded-jobs.mjs').read_bytes();scheduler_helper=(folder/'bounded_finishline.mjs').read_bytes()
 saved={}
 for name in (UCC,SCHED):
  files=client.source(name);settings=client.settings(name);crons=client.crons(name);planned=dict(files)
  if name==UCC:
   if 'bounded-jobs.mjs' in files and files['bounded-jobs.mjs']!=helper:raise r.inv.o.SafeError('bounded_helper_drift')
   planned.update({'index.js':transform(files['index.js']),'bounded-jobs.mjs':helper})
   if crons not in ([],['0 0,2,6,12,18 * * *']):raise r.inv.o.SafeError('ucc_native_schedule_drift')
  else:
   d.patch_index(files['index.js'])
   if files['finishline.mjs']!=scheduler_helper:d.patch_replay(files['finishline.mjs'])
   planned['finishline.mjs']=scheduler_helper
   if crons!=['* * * * *']:raise r.inv.o.SafeError('canonical_schedule_drift')
  saved[name]={'files':files,'settings':settings,'crons':crons,'planned':planned}
 client.db=next(v['database_id'] for v in saved[SCHED]['settings']['bindings'] if v['name']=='SCHED_DB' and v['type']=='d1')
 state=json.loads(client.sql(r.STATE,('scheduler:state',))[0]['payload']);before=state['targetStates']['ucc-staging']
 if not 0<=time.time()*1000-state.get('lastTick',0)<600000:raise r.inv.o.SafeError('canonical_tick_stale')
 report={'source_commit':os.environ.get('GITHUB_SHA'),'deployed':{},'new_resources':0,'paid_changes':0}
 for name,item in saved.items():
  if client.source(name)!=item['files'] or client.settings(name)!=item['settings']:raise r.inv.o.SafeError('bounded_preupload_drift')
  if item['planned']!=item['files'] or (name==SCHED and next(v for v in item['settings']['bindings'] if v['name']=='UCC_STAGING').get('entrypoint')!='KvIncidentScheduledIngress'):
   client.upload_bounded(name,item['settings'],item['planned'])
  if client.source(name)!=item['planned'] or client.crons(name)!=item['crons']:raise r.inv.o.SafeError('bounded_source_readback_failed')
  expected={v['name']:v for v in item['settings']['bindings']}
  if name==SCHED:expected['UCC_STAGING']={**expected['UCC_STAGING'],'entrypoint':'KvIncidentScheduledIngress'}
  if {v['name']:v for v in client.settings(name)['bindings']}!=expected:raise r.inv.o.SafeError('bounded_binding_readback_failed')
  report['deployed'][name]={'source_verified':True,'bindings_verified':True}
  print(json.dumps({'phase':'bounded_invocation_deployed','worker':name}),flush=True)
 now=int(time.time()*1000);slot=(now//60000)*60000
 client.sql(r.SEED,('incident','retry-budget-20260923-v4:ucc-staging',json.dumps({'scheduledTime':slot,'drainOnly':True}),now,1))
 result={'ok':False}
 for _ in range(22):
  current=json.loads(client.sql(r.STATE,('scheduler:state',))[0]['payload'])['targetStates']['ucc-staging']
  if current.get('lastInvokedAt',0)>before.get('lastInvokedAt',0) and current.get('lastCompletedAt',0)>=now:
   result={'ok':current.get('lastStatus')=='success','failure_code':current.get('lastFailureCode')};break
  time.sleep(20)
 report['bounded_pass']=result
 if not result['ok']:return report
 # Sole scheduler ownership is established only after the bounded canonical pass.
 old=saved[UCC]['crons']
 if client.crons(UCC)!=old or client.source(UCC)!=saved[UCC]['planned']:raise r.inv.o.SafeError('ucc_pre_pause_drift')
 if old:client.send(client.root+UCC+'/schedules','PUT',b'[]')
 if client.crons(UCC) or client.crons(SCHED)!=['* * * * *']:raise r.inv.o.SafeError('sole_scheduler_readback_failed')
 report['scheduling']={'owner':SCHED,'ucc_native_crons':[],'queue_only_minutes':10,'natural_pipeline_slots':'unchanged'}
 return report


def main():
 try:
  if os.environ.get('KV_INVOCATION_APPLY')!='approved-20260923':raise r.inv.o.SafeError('bounded_apply_not_authorized')
  result=run(Client(os.environ.get('CLOUDFLARE_API_TOKEN','')))
 except r.inv.o.SafeError as error:result={'error':str(error),'state':'not_complete'}
 except Exception:result={'error':'bounded_recovery_failed','state':'not_complete'}
 print(json.dumps(result,indent=2,sort_keys=True));return int('error' in result or result.get('bounded_pass',{}).get('ok') is not True)
if __name__=='__main__':raise SystemExit(main())
