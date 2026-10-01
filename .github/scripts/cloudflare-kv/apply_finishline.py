#!/usr/bin/env python3
"""Preserve exact live code; repair scheduler auth and execute two bounded retries."""
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
import uuid
from email import policy
from email.parser import BytesParser
import release as r

BASE = {
 'ucc-mca-edge-staging':'5f1ae8d557bcf4dcfa0688782877f1109a267666b0dda0d9105b2993ee45b2fb',
 'ops-scheduler-production':'8fa029e703baa5af8c5a4f30337a7f700d1964fcf9d347d785253ff4186028e1',
}
ENTRYPOINT='KvIncidentScheduledIngress'
RETRY_KEY='retry-auth-20260923-v1:'


def once(text, old, new):
 if text.count(old)!=1: raise r.inv.o.SafeError('source_patch_anchor_mismatch')
 return text.replace(old,new,1)


def transform(name, raw):
 if name not in BASE or hashlib.sha256(raw).hexdigest()!=BASE[name]:
  raise r.inv.o.SafeError('source_identity_mismatch')
 text=raw.decode()
 if name=='ucc-mca-edge-staging':
  text="import { WorkerEntrypoint as __IncidentEntry } from 'cloudflare:workers';\nimport { scheduledIngress as __scheduledIngress } from './finishline.mjs';\n"+text
  text+='\nexport class '+ENTRYPOINT+' extends __IncidentEntry {\n  fetch(request) { return __scheduledIngress(request, this.env, this.ctx, src_default); }\n}\n'
 else:
  text="import { appendRecoveryTargets as __appendRecoveryTargets, failureCode as __failureCode } from './finishline.mjs';\n"+text
  text=once(text,'const dueTargets = getDueTargets(scheduledTime);',
    'const dueTargets = await __appendRecoveryTargets(env2, getDueTargets(scheduledTime), scheduledTime, getTargetByName);')
  text=once(text,'state.targetStates[targetName] = targetState;',
    'targetState.lastFailureCode = result.ok ? null : __failureCode(result.error);\n  state.targetStates[targetName] = targetState;')
 return text.encode()


def decode_modules(kind,raw):
 if not kind.lower().startswith('multipart/'): return {'index.js':raw}
 message=BytesParser(policy=policy.default).parsebytes(('Content-Type: '+kind+'\r\n\r\n').encode()+raw)
 result={}
 for part in message.iter_parts():
  name=part.get_filename() or part.get_param('name',header='content-disposition')
  if name=='metadata':continue
  if name not in ('index.js','recovery.mjs','finishline.mjs') or name in result:raise r.inv.o.SafeError('unexpected_module')
  result[name]=part.get_payload(decode=True) or b''
 if 'index.js' not in result:raise r.inv.o.SafeError('main_missing')
 return result


def metadata(settings,name):
 result={k:v for k,v in settings.items() if k in ('compatibility_date','compatibility_flags','usage_model','logpush','observability','placement','tail_consumers','tags','limits') and v is not None}
 bindings=settings['bindings']
 result.update(main_module='index.js',bindings=[{'name':b['name'],'type':'inherit'} for b in bindings],annotations={'workers/message':'KV scheduler authenticated recovery','workers/tag':'kv-finishline-20260923-v1'})
 if any(b['type']=='assets' for b in bindings):result['keep_assets']=True
 if name=='ops-scheduler-production':
  old=[b for b in bindings if b['name']=='UCC_STAGING' and b['type']=='service' and b['service']=='ucc-mca-edge-staging']
  if len(old)!=1:raise r.inv.o.SafeError('scheduler_target_binding_drift')
  result['bindings']=[b for b in result['bindings'] if b['name']!='UCC_STAGING']+[
   {'name':'UCC_STAGING','type':'service','service':'ucc-mca-edge-staging','entrypoint':ENTRYPOINT}]
 return result


def multipart(meta,files):
 boundary='incident-'+uuid.uuid4().hex;chunks=[]
 for name,value in [('metadata',json.dumps(meta).encode()),*files.items()]:
  if name not in ('metadata','index.js','finishline.mjs'):raise r.inv.o.SafeError('upload_part_refused')
  kind='application/json' if name=='metadata' else 'application/javascript+module'
  chunks.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{name}"\r\nContent-Type: {kind}\r\n\r\n').encode()+value+b'\r\n')
 chunks.append(f'--{boundary}--\r\n'.encode())
 return 'multipart/form-data; boundary='+boundary,b''.join(chunks)


class Client(r.ReleaseClient):
 def source(self,name):return decode_modules(*self.raw(self.root+name+'/content/v2'))
 def upload_scoped(self,name,settings,files):
  if name not in BASE:raise r.inv.o.SafeError('upload_target_refused')
  kind,body=multipart(metadata(settings,name),files)
  req=urllib.request.Request(r.inv.o.API+self.root+name+'?bindings_inherit=strict',method='PUT',data=body,
   headers={'Authorization':'Bearer '+self.token,'Content-Type':kind})
  try:
   with r.inv.o.OPENER.open(req,timeout=60) as response:result=r.inv.o.decode_response(response)
  except urllib.error.HTTPError as error:raise r.inv.o.SafeError('upload_http_'+str(error.code)) from None
  if result.get('success') is not True:raise r.inv.o.SafeError('upload_rejected')


def run(client):
 helper=Path(__file__).with_name('finishline.mjs').read_bytes();records={}
 for name in BASE:
  settings=client.settings(name);files=client.source(name)
  original=files['index.js']
  if 'finishline.mjs' in files:
   # The expected transformed hash is checked against the readback manifest.
   expected=json.loads(Path(__file__).with_name('finishline-hashes.json').read_text())[name]
   if hashlib.sha256(original).hexdigest()!=expected or files['finishline.mjs']!=helper:raise r.inv.o.SafeError('deployed_patch_drift')
   planned=files
  else:planned={'index.js':transform(name,original),'finishline.mjs':helper}
  records[name]={'settings':settings,'files':files,'planned':planned,'crons':client.crons(name)}
 scheduler=records['ops-scheduler-production']['settings']
 client.db=next(b['database_id'] for b in scheduler['bindings'] if b['name']=='SCHED_DB' and b['type']=='d1')
 state=json.loads(client.sql(r.STATE,('scheduler:state',))[0]['payload'])
 if not 0<=time.time()*1000-state.get('lastTick',0)<600000:raise r.inv.o.SafeError('scheduler_not_live')
 if records['ops-scheduler-production']['crons']!=['* * * * *']:raise r.inv.o.SafeError('scheduler_cron_drift')
 report={'source_commit':os.environ.get('GITHUB_SHA'),'deployed':{},'new_secrets':0,'paid_changes':0}
 for name,item in records.items():
  if client.source(name)!=item['files'] or client.settings(name)!=item['settings']:raise r.inv.o.SafeError('preupload_drift')
  if item['files']!=item['planned']:client.upload_scoped(name,item['settings'],item['planned'])
  if client.source(name)!=item['planned'] or client.crons(name)!=item['crons']:raise r.inv.o.SafeError('source_or_schedule_readback_failed')
  after=client.settings(name)
  old={b['name']:b for b in item['settings']['bindings']};new={b['name']:b for b in after['bindings']}
  if name=='ops-scheduler-production':
   old['UCC_STAGING']={**old['UCC_STAGING'],'entrypoint':ENTRYPOINT}
  if old!=new:raise r.inv.o.SafeError('binding_readback_failed')
  report['deployed'][name]={'source_verified':True,'bindings_verified':True,'schedule_preserved':True}
  print(json.dumps({'phase':'deployed','worker':name}),flush=True)
 # No fake state completion: the existing scheduler executes and records each
 # real result. A conditional claim permits at most one replay per target.
 for name in ('ucc-staging','vulnpulse'):
  row=state['targetStates'].get(name,{})
  if row.get('lastStatus')=='success':continue
  last=row.get('lastInvokedAt',0);due=(int(last)//3600000)*3600000
  if not 0<=time.time()*1000-due<86400000:raise r.inv.o.SafeError('failed_job_outside_replay_window')
  client.sql(r.SEED,('incident',RETRY_KEY+name,json.dumps({'scheduledTime':due}),int(time.time()*1000),1))
 report['replay']='enqueued_once_for_existing_scheduler'
 # Observe the results of these bounded, explicitly queued jobs; never mark a
 # record successful merely because the queue or the deployment succeeded.
 results={}
 for attempt in range(11):
  fresh=json.loads(client.sql(r.STATE,('scheduler:state',))[0]['payload'])
  for name in ('ucc-staging','vulnpulse'):
   before=state['targetStates'].get(name,{})
   item=fresh['targetStates'].get(name,{})
   if item.get('lastInvokedAt',0)>before.get('lastInvokedAt',0):
    results[name]={'ok':item.get('lastStatus')=='success','failure_code':item.get('lastFailureCode')}
  if len(results)==2:break
  time.sleep(20)
 report['replay_results']=results
 report['all_replays_succeeded']=len(results)==2 and all(v['ok'] for v in results.values())
 return report


def main():
 try:
  if os.environ.get('KV_FINISHLINE_APPLY')!='approved-20260923':raise r.inv.o.SafeError('apply_not_authorized')
  report=run(Client(os.environ.get('CLOUDFLARE_API_TOKEN','')))
 except r.inv.o.SafeError as e:report={'error':str(e),'state':'not_complete'}
 except Exception:report={'error':'finishline_unexpected_failure','state':'not_complete'}
 print(json.dumps(report,indent=2,sort_keys=True));return int('error' in report or report.get('all_replays_succeeded') is not True)
if __name__=='__main__':raise SystemExit(main())
