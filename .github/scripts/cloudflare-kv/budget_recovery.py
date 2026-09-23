#!/usr/bin/env python3
"""Bound remaining LIST traffic and apply a target-specific measured deadline."""
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

REVISION='kv-recovery-d1-20260923-v2'
SCHEDULER='ops-scheduler-production'
SCHEDULER_BASE='8612e88a4e08f046fbc78ca4dfe5fa02c8309081f9b5b0de65bd935268e1d9ac'
ORIGINAL_HELPER='55d7760f63e148b3e9e00fa9f94896cb9d91ab2becfa5e455f0b71ed3e4d721e'
FINISHLINE_BLOB='81c1b2aacdb9352f8a88a197bba285ee6501f471'
RETRY_V1='retry-auth-20260923-v1:'
RETRY_V2='retry-auth-20260923-v2:'
OLD_TIMER='const timeoutId = setTimeout(() => controller.abort(), INVOCATION_TIMEOUT_MS);'
NEW_TIMER="const timeoutId = setTimeout(() => controller.abort(), target.name === 'ucc-staging' ? 300000 : INVOCATION_TIMEOUT_MS);"
OLD_MESSAGE='`TIMEOUT after ${INVOCATION_TIMEOUT_MS}ms`'
NEW_MESSAGE="`TIMEOUT after ${target.name === 'ucc-staging' ? 300000 : INVOCATION_TIMEOUT_MS}ms`"
SCHEMA='CREATE TABLE IF NOT EXISTS cf_kv_list_cache(product TEXT NOT NULL,key TEXT NOT NULL,payload TEXT NOT NULL,updated_at INTEGER NOT NULL,next_refresh INTEGER NOT NULL,generation INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(product,key))'
SEED='INSERT INTO cf_kv_list_cache(product,key,payload,updated_at,next_refresh,generation) VALUES(?,?,?,?,?,0) ON CONFLICT(product,key) DO NOTHING'
SELECT='SELECT payload FROM cf_kv_list_cache WHERE product=? AND key=?'
ALIGN='UPDATE cf_kv_recovery SET next_refresh=MIN(next_refresh,?) WHERE product=? AND key=\'status\''
CACHE_KEY='subscriber-index:v1'


def digest(raw):return hashlib.sha256(raw).hexdigest()
def blob(raw):return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
def once(text,old,new):
 if text.count(old)!=1:raise r.inv.o.SafeError('budget_patch_anchor_mismatch')
 return text.replace(old,new,1)


def scheduler_patch(raw):
 text=raw.decode()
 if digest(raw)!=SCHEDULER_BASE:
  restored=once(once(text,NEW_TIMER,OLD_TIMER),NEW_MESSAGE,OLD_MESSAGE).encode()
  if digest(restored)!=SCHEDULER_BASE:raise r.inv.o.SafeError('scheduler_source_drift')
  return raw
 return once(once(text,OLD_TIMER,NEW_TIMER),OLD_MESSAGE,NEW_MESSAGE).encode()


def replay_patch(raw):
 text=raw.decode()
 original=text.replace(RETRY_V2,RETRY_V1)
 if blob(original.encode())!=FINISHLINE_BLOB:raise r.inv.o.SafeError('replay_helper_drift')
 return once(original,RETRY_V1,RETRY_V2).encode()


def parse_modules(kind,raw):
 if not kind.lower().startswith('multipart/'):return {'index.js':raw}
 message=BytesParser(policy=policy.default).parsebytes(('Content-Type: '+kind+'\r\n\r\n').encode()+raw)
 result={}
 for part in message.iter_parts():
  name=part.get_filename() or part.get_param('name',header='content-disposition')
  if name=='metadata':continue
  if name not in ('index.js','recovery.mjs','finishline.mjs','subscriber-cache.mjs') or name in result:raise r.inv.o.SafeError('budget_module_refused')
  result[name]=part.get_payload(decode=True) or b''
 return result


def metadata(settings):
 result={k:v for k,v in settings.items() if k in ('compatibility_date','compatibility_flags','usage_model','logpush','observability','placement','tail_consumers','tags','limits') and v is not None}
 result.update(main_module='index.js',bindings=[{'name':b['name'],'type':'inherit'} for b in settings['bindings']],annotations={'workers/message':'KV LIST budget and target deadline repair','workers/tag':REVISION})
 if any(b['type']=='assets' for b in settings['bindings']):result['keep_assets']=True
 return result


def multipart(settings,files):
 boundary='budget-'+uuid.uuid4().hex;chunks=[]
 for name,value in [('metadata',json.dumps(metadata(settings)).encode()),*files.items()]:
  if name not in ('metadata','index.js','recovery.mjs','finishline.mjs','subscriber-cache.mjs'):raise r.inv.o.SafeError('budget_upload_part_refused')
  kind='application/json' if name=='metadata' else 'application/javascript+module'
  chunks.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{name}"\r\nContent-Type: {kind}\r\n\r\n').encode()+value+b'\r\n')
 chunks.append(f'--{boundary}--\r\n'.encode())
 return 'multipart/form-data; boundary='+boundary,b''.join(chunks)


class Client(r.ReleaseClient):
 def source(self,name):return parse_modules(*self.raw(self.root+name+'/content/v2'))
 def upload(self,name,settings,files):
  if name not in (*r.PRODUCTS,SCHEDULER):raise r.inv.o.SafeError('budget_upload_target_refused')
  kind,data=multipart(settings,files)
  request=urllib.request.Request(r.inv.o.API+self.root+name+'?bindings_inherit=strict',data=data,method='PUT',headers={'Authorization':'Bearer '+self.token,'Content-Type':kind})
  try:
   with r.inv.o.OPENER.open(request,timeout=60) as response:result=r.inv.o.decode_response(response)
  except urllib.error.HTTPError as error:raise r.inv.o.SafeError('budget_upload_http_'+str(error.code)) from None
  if result.get('success') is not True:raise r.inv.o.SafeError('budget_upload_failed')
 def cache_sql(self,statement,params=()):
  if statement not in (SCHEMA,SEED,SELECT,ALIGN):raise r.inv.o.SafeError('budget_sql_refused')
  rows=self.request(f'/accounts/{self.aid}/d1/database/{self.db}/query','POST',json.dumps({'sql':statement,'params':list(params)}).encode())
  if len(rows)!=1 or rows[0].get('success') is not True:raise r.inv.o.SafeError('budget_sql_failed')
  return rows[0].get('results',[])
 def subscriber_seed(self,namespace):
  # Exactly one enumeration of the already-owned namespace. Keys never enter logs.
  if not isinstance(namespace,str) or len(namespace)!=32 or any(c not in '0123456789abcdef' for c in namespace):raise r.inv.o.SafeError('namespace_invalid')
  request=urllib.request.Request(r.inv.o.API+f'/accounts/{self.aid}/storage/kv/namespaces/{namespace}/keys?prefix=sub%3A&limit=1000',headers={'Authorization':'Bearer '+self.token})
  with r.inv.o.OPENER.open(request,timeout=20) as response:result=r.inv.o.decode_response(response)
  if result.get('success') is not True or not isinstance(result.get('result'),list):raise r.inv.o.SafeError('subscriber_seed_failed')
  cursor=result.get('result_info',{}).get('cursor') or ''
  if not isinstance(cursor,str):raise r.inv.o.SafeError('subscriber_cursor_invalid')
  return {'keys':result['result'],'cursor':cursor,'list_complete':not cursor}


def run(client):
 folder=Path(__file__).parent;helper=(folder/'recovery.mjs').read_bytes();cache=(folder/'subscriber-cache.mjs').read_bytes()
 records={}
 for name in (*r.PRODUCTS,SCHEDULER):
  settings=client.settings(name);files=client.source(name);planned=dict(files)
  if name in r.PRODUCTS:
   if digest(files['index.js'])!=r.PATCHED_HASHES[name]:raise r.inv.o.SafeError('product_source_drift')
   if digest(files['recovery.mjs'])!=ORIGINAL_HELPER and files['recovery.mjs']!=helper:raise r.inv.o.SafeError('recovery_helper_drift')
   if 'subscriber-cache.mjs' in files and files['subscriber-cache.mjs']!=cache:raise r.inv.o.SafeError('cache_helper_drift')
   planned.update({'recovery.mjs':helper,'subscriber-cache.mjs':cache})
  else:
   planned.update({'index.js':scheduler_patch(files['index.js']),'finishline.mjs':replay_patch(files['finishline.mjs'])})
  records[name]={'settings':settings,'files':files,'planned':planned,'crons':client.crons(name)}
 client.db=next(b['database_id'] for b in records[SCHEDULER]['settings']['bindings'] if b['name']=='SCHED_DB')
 state=json.loads(client.sql(r.STATE,('scheduler:state',))[0]['payload'])
 if not 0<=time.time()*1000-state.get('lastTick',0)<600000:raise r.inv.o.SafeError('scheduler_not_live')
 if records[SCHEDULER]['crons']!=['* * * * *']:raise r.inv.o.SafeError('scheduler_cron_drift')
 if any(records[n]['crons'] for n in r.PRODUCTS):raise r.inv.o.SafeError('product_cron_drift')
 client.cache_sql(SCHEMA)
 if not client.cache_sql(SELECT,('edgarflash',CACHE_KEY)):
  ns=next(b['namespace_id'] for b in records['edgarflash']['settings']['bindings'] if b['name']=='EF_SUBS')
  seed=client.subscriber_seed(ns);now=int(time.time()*1000)
  payload=json.dumps(seed)
  client.cache_sql(SEED,('edgarflash',CACHE_KEY,payload,now,now+300000))
  if client.cache_sql(SELECT,('edgarflash',CACHE_KEY))[0]['payload']!=payload:raise r.inv.o.SafeError('subscriber_seed_readback_failed')
 report={'source_commit':os.environ.get('GITHUB_SHA'),'revision':REVISION,'deployed':{},'new_resources':0,'paid_changes':0}
 for name,item in records.items():
  if client.source(name)!=item['files'] or client.settings(name)!=item['settings']:raise r.inv.o.SafeError('budget_preupload_drift')
  if item['files']!=item['planned']:client.upload(name,item['settings'],item['planned'])
  if client.source(name)!=item['planned'] or client.crons(name)!=item['crons']:raise r.inv.o.SafeError('budget_readback_failed')
  if {b['name']:b for b in client.settings(name)['bindings']}!={b['name']:b for b in item['settings']['bindings']}:raise r.inv.o.SafeError('budget_binding_drift')
  report['deployed'][name]={'source_verified':True,'bindings_preserved':True,'crons_preserved':True}
  print(json.dumps({'phase':'budget_deployed','worker':name}),flush=True)
  if name in r.PRODUCTS:
   for _ in range(4):
    code,body=r.public(name,'/healthz')
    if code==200 and body.get('revision')==REVISION:break
    time.sleep(5)
   else:raise r.inv.o.SafeError('budget_live_revision_unverified')
   period=r.PERIOD[name];now=int(time.time()*1000)
   client.cache_sql(ALIGN,((now//period+1)*period,name))
 # Preserve the original failed scheduled slot. No completed job is replayed.
 before=state['targetStates'].get('ucc-staging',{})
 if before.get('lastStatus')=='success' and 0<=time.time()*1000-before.get('lastCompletedAt',0)<43200000:
  report['ucc_replay']={'ok':True,'source':'already_verified_success'};return report
 rows=client.sql(r.SELECT,('incident',RETRY_V1+'ucc-staging'))
 if len(rows)!=1:raise r.inv.o.SafeError('original_failed_slot_missing')
 payload=json.loads(rows[0]['payload']);due=payload.get('scheduledTime')
 if not isinstance(due,(int,float)) or not 0<=time.time()*1000-due<86400000:raise r.inv.o.SafeError('replay_slot_expired')
 client.sql(r.SEED,('incident',RETRY_V2+'ucc-staging',json.dumps(payload),int(time.time()*1000),1))
 result={'ok':False,'failure_code':'completion_not_observed'}
 for _ in range(22):
  current=json.loads(client.sql(r.STATE,('scheduler:state',))[0]['payload'])['targetStates'].get('ucc-staging',{})
  if current.get('lastInvokedAt',0)>before.get('lastInvokedAt',0):
   result={'ok':current.get('lastStatus')=='success','failure_code':current.get('lastFailureCode')};break
  time.sleep(20)
 report['ucc_replay']=result
 return report


def main():
 try:
  if os.environ.get('KV_BUDGET_APPLY')!='approved-20260923':raise r.inv.o.SafeError('budget_apply_not_authorized')
  report=run(Client(os.environ.get('CLOUDFLARE_API_TOKEN','')))
 except r.inv.o.SafeError as error:report={'error':str(error),'state':'not_complete'}
 except Exception:report={'error':'budget_unexpected_failure','state':'not_complete'}
 print(json.dumps(report,indent=2,sort_keys=True));return int('error' in report or report.get('ucc_replay',{}).get('ok') is not True)
if __name__=='__main__':raise SystemExit(main())
