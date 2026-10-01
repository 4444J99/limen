#!/usr/bin/env python3
"""Read existing Worker failure logs; project only fixed diagnoses and stack sites."""
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
import schema_probe as s

TARGETS=('ucc-mca-edge-staging','ops-scheduler-production')

def payload(name,now):
 if name not in TARGETS:raise s.r.inv.o.SafeError('telemetry_target_refused')
 return {'queryId':'kv-incident-errors-20260923','timeframe':{'from':now-3600000,'to':now},
  'view':'events','limit':100,'parameters':{'datasets':[], 'filters':[
   {'key':'$metadata.service','operation':'eq','type':'string','value':name}],
   'filterCombination':'and','needle':{'value':'error|failed|D1|SQLITE','isRegex':True}}}

def project(value):
 texts=[]
 def walk(v,depth=0):
  if depth>10:return
  if isinstance(v,str):texts.append(v[:16000])
  elif isinstance(v,dict):
   for key,item in v.items():
    if key not in ('headers','request','url','body','payload','account','accountId','bindings'):walk(item,depth+1)
  elif isinstance(v,list):
   for item in v[:100]:walk(item,depth+1)
 walk(value)
 diagnoses=[];sites=set();signals=set()
 patterns=(('subrequest_limit',r'too many subrequests'),('d1_request_limit',r'too many (?:D1 |database )?requests'),
  ('cpu_limit',r'exceeded (?:the )?(?:CPU|cpu) (?:time|limit)'),('memory_limit',r'memory limit'),
  ('body_consumed',r'body.*(?:used|consumed|disturbed)'),('network',r'fetch failed|network connection lost'),
  ('database_reset',r'D1.*reset'),('database_overloaded',r'D1.*overloaded'),('database_size',r'database.*(?:size|full)'),
  ('http_500',r'HTTP 500'),('http_401',r'HTTP 401'),('http_429',r'HTTP 429'))
 for text in texts:
  diagnosis=s.diagnose(text)
  if diagnosis['category']!='unclassified':diagnoses.append(diagnosis)
  for name,pattern in patterns:
   if re.search(pattern,text,re.I):signals.add(name)
  for fn,line in re.findall(r'\bat ([A-Za-z_$][\w.$]{0,63})\s*\([^()\s]*?index\.js:(\d+):\d+\)',text):
   sites.add((fn,int(line)))
 return {'diagnoses':list({json.dumps(d,sort_keys=True):d for d in diagnoses}.values()),
         'signals':sorted(signals),'stack_sites':[{'function':f,'line':line} for f,line in sorted(sites)],
         'opaque_message_hashes':sorted({hashlib.sha256(t.encode()).hexdigest() for t in texts})[:20]}

def run(client):
 now=int(time.time()*1000);report={'mode':'existing_log_observation','mutations':0,'workers':{}}
 for name in TARGETS:
  request=urllib.request.Request(s.r.inv.o.API+f'/accounts/{client.aid}/workers/observability/telemetry/query',
   data=json.dumps(payload(name,now)).encode(),headers={'Authorization':'Bearer '+client.token,'Content-Type':'application/json'})
  try:
   with s.r.inv.o.OPENER.open(request,timeout=40) as response:body=s.r.inv.o.decode_response(response)
  except urllib.error.HTTPError as error:raise s.r.inv.o.SafeError('telemetry_http_'+str(error.code)) from None
  if body.get('success') is False or body.get('errors'):raise s.r.inv.o.SafeError('telemetry_query_rejected')
  result=body.get('result',{});events=result.get('events',{}).get('events')
  if not isinstance(events,list) or len(events)>100:raise s.r.inv.o.SafeError('telemetry_shape_invalid')
  report['workers'][name]={'events_returned':len(events),'limited':len(events)==100,'projection':project(events)}
 return report

def main():
 try:report=run(s.r.ReleaseClient(os.environ.get('CLOUDFLARE_API_TOKEN','')))
 except s.r.inv.o.SafeError as error:report={'error':str(error)}
 except Exception:report={'error':'telemetry_unobserved'}
 print(json.dumps(report,indent=2,sort_keys=True));return int('error' in report)
if __name__=='__main__':raise SystemExit(main())
