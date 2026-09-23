#!/usr/bin/env python3
"""Exact-live-source recovery. Existing resources only; sanitized receipts."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from email import policy
from email.parser import BytesParser
import inventory as inv

REVISION = 'kv-recovery-d1-20260923-v1'
HASHES = {
 'edgarflash':'30d7dddfb9f0e3c4bd7f7e019d783204b8d15b51388bbf0bea821b7573b5f312',
 'trendpulse':'307f12639d325aa9617617a4ab4316d9a59275be848fc49eaffaf14f9a5b046b',
 'vulnpulse':'30fc3ac86444ced9e029159c8d5c0202b21f12c0d97d2789c22b7feb2ccf2534',
 'ops-scheduler':'1af405f33c08cd93e95f542111633744ea8ebbf3592e8f8d9915bad12c02af5a',
 'ops-scheduler-production':'8fa029e703baa5af8c5a4f30337a7f700d1964fcf9d347d785253ff4186028e1',
 'ops-scheduler-staging':'07e0614e9b9b35841063dd260a64657c08362f6be76893c52879bd5705b1be83',
}
PATCHED_HASHES = {'edgarflash': 'cea0874ec649d8b17f56dc18f81d4a3f1c752425a4942289db98bf6084213563', 'trendpulse': '78564e302ded6abfa853535bcc948467c0d911d314721e09cef41eafe6acb8bb', 'vulnpulse': '2dc56dd4f219c6ebde60b812b64d5a35229b26175f7321c3bffe83c809a417ae'}
PRODUCTS = ('edgarflash','trendpulse','vulnpulse')
DUPLICATES = ('ops-scheduler','ops-scheduler-staging')
PERIOD = {'edgarflash':3600000,'trendpulse':14400000,'vulnpulse':86400000}
SCHEMA = 'CREATE TABLE IF NOT EXISTS cf_kv_recovery(product TEXT NOT NULL,key TEXT NOT NULL,payload TEXT NOT NULL,updated_at INTEGER NOT NULL,next_refresh INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(product,key))'
SEED = 'INSERT INTO cf_kv_recovery(product,key,payload,updated_at,next_refresh) VALUES(?,?,?,?,?) ON CONFLICT(product,key) DO NOTHING'
SELECT = 'SELECT payload,updated_at FROM cf_kv_recovery WHERE product=? AND key=?'
STATE = 'SELECT payload FROM scheduler_state WHERE id=?'
PREFIX = "import { recoverWorker as __recoverWorker } from './recovery.mjs';\n"


def modules(kind, raw):
 if not kind.lower().startswith('multipart/'):
  return {'index.js':raw}
 msg=BytesParser(policy=policy.default).parsebytes(('Content-Type: '+kind+'\r\n\r\n').encode()+raw)
 result={}
 for part in msg.iter_parts():
  name=part.get_filename() or part.get_param('name',header='content-disposition')
  if name == 'metadata': continue
  if name not in ('index.js','recovery.mjs') or name in result:
   raise inv.o.SafeError('unexpected_live_module')
  result[name]=part.get_payload(decode=True) or b''
 if 'index.js' not in result: raise inv.o.SafeError('main_module_missing')
 return result


def transform(name, content):
 if name not in PRODUCTS or hashlib.sha256(content).hexdigest()!=HASHES[name]:
  raise inv.o.SafeError('live_source_identity_drift')
 text=content.decode()
 alias='index_default' if name=='trendpulse' else 'src_default'
 marker=f'  {alias} as default,'
 if text.count(marker)!=1:
  # The default export can be last (no trailing comma).
  marker=f'  {alias} as default\n'
 if text.count(marker)!=1: raise inv.o.SafeError('default_export_shape_changed')
 text=text.replace(marker,marker.replace(alias,'__recovered'))
 tail=f'\nconst __recovered = __recoverWorker({alias}, {json.dumps(name)});\n'
 return (PREFIX+text+tail).encode()


def preserved_metadata(settings, db, revision):
 meta={k:v for k,v in settings.items() if k in (
  'compatibility_date','compatibility_flags','usage_model','logpush','observability',
  'placement','tail_consumers','tags','limits') and v is not None}
 bindings=inv.o.object_rows(settings.get('bindings'))
 meta.update(main_module='index.js',keep_assets=True,
  annotations={'workers/message':'KV incident exact-live repair '+revision,'workers/tag':REVISION},
  bindings=[{'name':b['name'],'type':'inherit'} for b in bindings if b['name']!='INCIDENT_DB'])
 meta['bindings'].append({'name':'INCIDENT_DB','type':'d1','database_id':db})
 return meta


def multipart(meta, files):
 boundary='kv-recovery-'+uuid.uuid4().hex
 chunks=[]
 for name,kind,value in [('metadata','application/json',json.dumps(meta).encode())]+[
   (name,'application/javascript+module',content) for name,content in files.items()]:
  if name not in ('metadata','index.js','recovery.mjs'): raise inv.o.SafeError('upload_part_refused')
  chunks.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{name}"\r\nContent-Type: {kind}\r\n\r\n').encode()+value+b'\r\n')
 chunks.append(f'--{boundary}--\r\n'.encode())
 return 'multipart/form-data; boundary='+boundary,b''.join(chunks)


class ReleaseClient(inv.InventoryClient):
 def __init__(self,token):
  super().__init__(token)
  self.aid=self.account()
  self.root=f'/accounts/{self.aid}/workers/scripts/'
  self.db=None
  self.seed_namespace=None

 def request(self,path,method='GET',data=None,kind='application/json',raw=False):
  script=path.removeprefix(self.root)
  allowed=(path.startswith(self.root) and (
   (method=='PUT' and script in [n+'?bindings_inherit=strict' for n in PRODUCTS]) or
   (method=='PUT' and script in [n+'/schedules' for n in DUPLICATES]) or
   (method=='GET' and script in [n+'/deployments' for n in PRODUCTS])))
  allowed=allowed or (method=='POST' and self.db and path==f'/accounts/{self.aid}/d1/database/{self.db}/query')
  allowed=allowed or (method=='GET' and self.seed_namespace and path in [
   f'/accounts/{self.aid}/storage/kv/namespaces/{self.seed_namespace}/values/{key}' for key in ('last_seen_filings','feed:recent')])
  if not allowed: raise inv.o.SafeError('release_endpoint_refused')
  req=urllib.request.Request(inv.o.API+path,data=data,method=method,headers={
   'Authorization':'Bearer '+self.token,'Content-Type':kind,'User-Agent':'organvm-kv-recovery/1'})
  try:
   with inv.o.OPENER.open(req,timeout=60) as response:
    content=response.read(2_000_001)
  except urllib.error.HTTPError as err:
   # Only error codes, never vendor messages or resource identifiers.
   raise inv.o.SafeError('release_http_'+str(err.code)) from None
  except (urllib.error.URLError,TimeoutError):
   raise inv.o.SafeError('release_network_error') from None
  if len(content)>2_000_000: raise inv.o.SafeError('release_response_too_large')
  if raw:return content
  body=inv.o.object_value(json.loads(content))
  if body.get('success') is False or body.get('errors'): raise inv.o.SafeError('release_provider_rejected')
  return body.get('result')

 def sql(self,statement,params=()):
  if statement not in (SCHEMA,SEED,SELECT,STATE): raise inv.o.SafeError('release_sql_refused')
  result=inv.o.object_rows(self.request(f'/accounts/{self.aid}/d1/database/{self.db}/query','POST',
    json.dumps({'sql':statement,'params':[str(p) for p in params]}).encode()))
  if len(result)!=1 or result[0].get('success') is not True: raise inv.o.SafeError('release_sql_failed')
  return result[0].get('results',[])

 def settings(self,name):return inv.o.object_value(self.inventory_result(self.root+name+'/settings'))
 def crons(self,name):
  return [s['cron'] for s in self.inventory_result(self.root+name+'/schedules')['schedules']]
 def source(self,name):return modules(*self.raw(self.root+name+'/content/v2'))
 def upload(self,name,settings,files,revision):
  kind,data=multipart(preserved_metadata(settings,self.db,revision),files)
  return self.request(self.root+name+'?bindings_inherit=strict','PUT',data,kind)
 def pause(self,name):
  if name not in DUPLICATES:raise inv.o.SafeError('canonical_scheduler_pause_refused')
  self.request(self.root+name+'/schedules','PUT',b'[]')
  if self.crons(name): raise inv.o.SafeError('duplicate_schedule_readback_failed')


def public(name,path):
 if name not in PRODUCTS or path not in ('/healthz','/api/status'): raise inv.o.SafeError('probe_refused')
 req=urllib.request.Request(f'https://{name}.ivixivi.workers.dev{path}',headers={'User-Agent':'organvm-kv-recovery/1'})
 try:
  with inv.o.OPENER.open(req,timeout=20) as response:return response.status,inv.o.decode_response(response,262144)
 except urllib.error.HTTPError as err:
  try:body=inv.o.decode_response(err,262144)
  except inv.o.SafeError:body={}
  return err.code,body


def recover(client,revision):
 helper=Path(__file__).with_name('recovery.mjs').read_bytes()
 originals={}
 for name in HASHES:
  parts=client.source(name)
  original=parts['index.js']
  if name in PRODUCTS and 'recovery.mjs' in parts:
   if parts['recovery.mjs']!=helper or hashlib.sha256(original).hexdigest()!=PATCHED_HASHES[name]:raise inv.o.SafeError('existing_repair_differs')
   originals[name]={'already_deployed':True,'settings':client.settings(name),'files':parts}
  else:
   if hashlib.sha256(original).hexdigest()!=HASHES[name]:raise inv.o.SafeError('live_source_identity_drift')
   originals[name]={'already_deployed':False,'settings':client.settings(name),'files':parts}
  if name in PRODUCTS and client.crons(name): raise inv.o.SafeError('product_cron_drift')
 if client.crons('ops-scheduler-production')!=['* * * * *']:raise inv.o.SafeError('canonical_schedule_drift')
 for name in DUPLICATES:
  if client.crons(name) not in ([],['* * * * *']):raise inv.o.SafeError('duplicate_schedule_drift')
 bindings=originals['ops-scheduler-production']['settings']['bindings']
 databases=[b for b in bindings if b['name']=='SCHED_DB' and b['type']=='d1']
 if len(databases)!=1:raise inv.o.SafeError('existing_database_missing')
 client.db=databases[0]['database_id']
 if not re.fullmatch(r'[a-f0-9-]{36}',client.db):raise inv.o.SafeError('database_identity_invalid')
 state=client.sql(STATE,('scheduler:state',))
 if len(state)!=1:raise inv.o.SafeError('canonical_scheduler_state_missing')
 state=json.loads(state[0]['payload'])
 if not isinstance(state.get('lastTick'),(int,float)) or not 0<=time.time()*1000-state['lastTick']<600000:
  raise inv.o.SafeError('canonical_scheduler_not_ticking')
 client.sql(SCHEMA)
 report={'revision':REVISION,'source_commit':revision,'products':{},'cron_cutover':{},'new_resources':0,'paid_changes':0}
 print(json.dumps({'phase':'validated_live_sources_and_canonical_scheduler'}),flush=True)
 # Existing published status observations seed the first snapshot, never a
 # fabricated healthy value. Existing rows are preserved on re-execution.
 for name in PRODUCTS:
  if not client.sql(SELECT,(name,'status')):
   code,body=public(name,'/api/status')
   if code!=200 or not isinstance(body,dict):raise inv.o.SafeError('initial_status_not_observable')
   now=int(time.time()*1000)
   client.sql(SEED,(name,'status',json.dumps(body),now,now+PERIOD[name]))
 # Two known public feed keys only: customer/payment/auth records stay untouched.
 ef_bindings=originals['edgarflash']['settings']['bindings']
 client.seed_namespace=next(b['namespace_id'] for b in ef_bindings if b['name']=='EF_STATE')
 for key in ('last_seen_filings','feed:recent'):
  if not client.sql(SELECT,('edgarflash',key)):
   value=client.request(f'/accounts/{client.aid}/storage/kv/namespaces/{client.seed_namespace}/values/{key}',raw=True).decode()
   if len(value)>262144 or not isinstance(json.loads(value),list):raise inv.o.SafeError('feed_seed_invalid')
   client.sql(SEED,('edgarflash',key,value,int(time.time()*1000),0))
   if client.sql(SELECT,('edgarflash',key))[0]['payload']!=value:raise inv.o.SafeError('feed_seed_readback_failed')
 for name in PRODUCTS:
  item=originals[name]
  if not item['already_deployed']:
   # A second identity/config read immediately before the write detects another
   # operator's deployment. Cloudflare upload itself has no compare-and-swap.
   if client.source(name)!=item['files'] or client.settings(name)!=item['settings']:
    raise inv.o.SafeError('preupload_source_or_settings_drift')
   files={'index.js':transform(name,item['files']['index.js']),'recovery.mjs':helper}
   client.upload(name,item['settings'],files,revision)
   if client.source(name)!=files:raise inv.o.SafeError('deployed_source_readback_failed')
  after=client.settings(name)
  old={b['name']:b for b in item['settings']['bindings'] if b['name']!='INCIDENT_DB'}
  new={b['name']:b for b in after['bindings'] if b['name']!='INCIDENT_DB'}
  if old!=new or client.crons(name):raise inv.o.SafeError('deployment_configuration_readback_failed')
  for _ in range(4):
   code,body=public(name,'/healthz')
   if code==200 and body.get('revision')==REVISION:break
   time.sleep(5)
  else:raise inv.o.SafeError('live_revision_unverified')
  code,status=public(name,'/api/status')
  if code!=200 or status.get('_status_snapshot',{}).get('revision')!=REVISION:
   raise inv.o.SafeError('live_snapshot_unverified')
  deployment=client.request(client.root+name+'/deployments')
  rows=deployment.get('deployments',[]) if isinstance(deployment,dict) else deployment
  versions=rows[0].get('versions',[]) if rows else []
  report['products'][name]={'source_verified':True,'bindings_preserved':True,'health_http':code,
   'version_ids':[v['version_id'] for v in versions if re.fullmatch(r'[a-f0-9-]{36}',v.get('version_id',''))]}
  print(json.dumps({'phase':'product_deployed','product':name,'receipt':report['products'][name]}),flush=True)
 # Keep the existing canonical scheduler continuously active. Its new job
 # acknowledgement must be observed before pausing either duplicate copy.
 earliest_ack=int(time.time()*1000)
 for _ in range(6):
  rows=client.sql(SELECT,('edgarflash','last_job'))
  if rows:
   job=json.loads(rows[0]['payload'])
   canonical=json.loads(client.sql(STATE,('scheduler:state',))[0]['payload'])
   target=canonical.get('targetStates',{}).get('edgarflash',{})
   if (job.get('ok') is True and job.get('completed_at',0)>=earliest_ack
       and target.get('lastStatus')=='success' and target.get('lastCompletedAt',0)>=earliest_ack):break
  time.sleep(20)
 else:raise inv.o.SafeError('repaired_job_acknowledgement_missing')
 for name in DUPLICATES:
  client.pause(name)
  report['cron_cutover'][name]='paused_duplicate_trigger_worker_preserved'
 report['cron_cutover']['ops-scheduler-production']='unchanged_minute_cron_all_six_jobs_preserved'
 report['observed_at']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
 report['qualification']='rollout and job acknowledgement; complete post-rollout UTC quota window remains outstanding'
 return report


def main():
 try:
  if os.environ.get('KV_RECOVERY_APPLY')!='approved-20260923':raise inv.o.SafeError('apply_not_authorized')
  sha=os.environ.get('GITHUB_SHA','')
  if not re.fullmatch(r'[a-f0-9]{40}',sha):raise inv.o.SafeError('source_commit_invalid')
  report=recover(ReleaseClient(os.environ.get('CLOUDFLARE_API_TOKEN','')),sha)
 except inv.o.SafeError as error:report={'error':str(error),'state':'not_verified_complete'}
 except Exception:report={'error':'release_unexpected_failure','state':'not_verified_complete'}
 text=json.dumps(report,sort_keys=True,indent=2)
 print(text,flush=True)
 if os.environ.get('GITHUB_STEP_SUMMARY'):
  with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:f.write('## KV recovery release\n```json\n'+text+'\n```\n')
 return int('error' in report)

if __name__=='__main__':sys.exit(main())
