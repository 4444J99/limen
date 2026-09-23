#!/usr/bin/env python3
"""Persist sanitized real invocation diagnoses; replay one failed slot once."""
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
import budget_recovery as b

NAME=b.SCHEDULER
PREFIX="import { failureDiagnosis as __failureDiagnosis } from './diagnosis.mjs';\n"
ANCHOR='targetState.lastFailureCode = result.ok ? null : __failureCode(result.error);'
EXTRA='\n  targetState.lastFailureDetail = result.ok ? null : __failureDiagnosis(result.error);'
KEY='retry-auth-20260923-v3:'

def patch_index(raw):
 text=raw.decode()
 if text.startswith(PREFIX):
  plain=b.once(text[len(PREFIX):],EXTRA,'')
  b.scheduler_patch(plain.encode())
  return raw
 b.scheduler_patch(raw)
 return (PREFIX+b.once(text,ANCHOR,ANCHOR+EXTRA)).encode()

def patch_replay(raw):
 original=raw.decode().replace(KEY,b.RETRY_V2).encode()
 verified=b.replay_patch(original)
 return b.once(verified.decode(),b.RETRY_V2,KEY).encode()

def modules(kind,raw):
 if not kind.lower().startswith('multipart/'):return{'index.js':raw}
 msg=BytesParser(policy=policy.default).parsebytes(('Content-Type: '+kind+'\r\n\r\n').encode()+raw)
 result={}
 for part in msg.iter_parts():
  name=part.get_filename() or part.get_param('name',header='content-disposition')
  if name=='metadata':continue
  if name not in ('index.js','finishline.mjs','diagnosis.mjs') or name in result:raise b.r.inv.o.SafeError('diagnostic_module_refused')
  result[name]=part.get_payload(decode=True) or b''
 return result

class Client(b.Client):
 def source(self,name):
  if name!=NAME:raise b.r.inv.o.SafeError('diagnostic_source_target_refused')
  return modules(*self.raw(self.root+name+'/content/v2'))
 def upload_diagnostic(self,settings,files):
  boundary='diagnostic-'+uuid.uuid4().hex;parts=[]
  for name,value in [('metadata',json.dumps(b.metadata(settings)).encode()),*files.items()]:
   if name not in ('metadata','index.js','finishline.mjs','diagnosis.mjs'):raise b.r.inv.o.SafeError('diagnostic_upload_part_refused')
   kind='application/json' if name=='metadata' else 'application/javascript+module'
   parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{name}"\r\nContent-Type: {kind}\r\n\r\n').encode()+value+b'\r\n')
  parts.append(f'--{boundary}--\r\n'.encode())
  request=urllib.request.Request(b.r.inv.o.API+self.root+NAME+'?bindings_inherit=strict',method='PUT',data=b''.join(parts),headers={'Authorization':'Bearer '+self.token,'Content-Type':'multipart/form-data; boundary='+boundary})
  try:
   with b.r.inv.o.OPENER.open(request,timeout=60) as response:result=b.r.inv.o.decode_response(response)
  except urllib.error.HTTPError as error:raise b.r.inv.o.SafeError('diagnostic_upload_http_'+str(error.code)) from None
  if result.get('success') is not True:raise b.r.inv.o.SafeError('diagnostic_upload_failed')

def run(client):
 original=client.source(NAME);settings=client.settings(NAME);crons=client.crons(NAME)
 helper=Path(__file__).with_name('diagnosis.mjs').read_bytes()
 if 'diagnosis.mjs' in original and original['diagnosis.mjs']!=helper:raise b.r.inv.o.SafeError('diagnostic_helper_drift')
 planned={**original,'index.js':patch_index(original['index.js']),
          'finishline.mjs':patch_replay(original['finishline.mjs']),'diagnosis.mjs':helper}
 if crons!=['* * * * *']:raise b.r.inv.o.SafeError('diagnostic_cron_drift')
 client.db=next(v['database_id'] for v in settings['bindings'] if v['name']=='SCHED_DB' and v['type']=='d1')
 before=json.loads(client.sql(b.r.STATE,('scheduler:state',))[0]['payload'])['targetStates']['ucc-staging']
 if client.source(NAME)!=original or client.settings(NAME)!=settings:raise b.r.inv.o.SafeError('diagnostic_preupload_drift')
 if planned!=original:client.upload_diagnostic(settings,planned)
 if client.source(NAME)!=planned or client.crons(NAME)!=crons:raise b.r.inv.o.SafeError('diagnostic_source_readback_failed')
 if {v['name']:v for v in client.settings(NAME)['bindings']}!={v['name']:v for v in settings['bindings']}:raise b.r.inv.o.SafeError('diagnostic_binding_readback_failed')
 if before.get('lastStatus')=='success':return {'ok':True,'source':'already_successful'}
 original_slot=client.sql(b.r.SELECT,('incident',b.RETRY_V1+'ucc-staging'))
 payload=json.loads(original_slot[0]['payload'])
 if not 0<=time.time()*1000-payload['scheduledTime']<86400000:raise b.r.inv.o.SafeError('diagnostic_slot_expired')
 client.sql(b.r.SEED,('incident',KEY+'ucc-staging',json.dumps(payload),int(time.time()*1000),1))
 for _ in range(22):
  current=json.loads(client.sql(b.r.STATE,('scheduler:state',))[0]['payload'])['targetStates']['ucc-staging']
  if current.get('lastInvokedAt',0)>before.get('lastInvokedAt',0):
   return {'source_verified':True,'bindings_preserved':True,'ok':current.get('lastStatus')=='success',
           'diagnosis':current.get('lastFailureDetail'),'source_commit':os.environ.get('GITHUB_SHA')}
  time.sleep(20)
 raise b.r.inv.o.SafeError('diagnostic_completion_not_observed')

def main():
 try:
  if os.environ.get('KV_DIAGNOSTIC_APPLY')!='approved-20260923':raise b.r.inv.o.SafeError('diagnostic_apply_not_authorized')
  report=run(Client(os.environ.get('CLOUDFLARE_API_TOKEN','')))
 except b.r.inv.o.SafeError as error:report={'error':str(error),'ok':False}
 except Exception:report={'error':'diagnostic_replay_failed','ok':False}
 print(json.dumps(report,indent=2,sort_keys=True));return int(not report.get('ok'))
if __name__=='__main__':raise SystemExit(main())
