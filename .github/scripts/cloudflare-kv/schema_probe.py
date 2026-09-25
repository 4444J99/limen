#!/usr/bin/env python3
"""Inspect the failed job's error and schema, never business rows or credentials."""
import json
import os
import re
import release as r

TABLES=('jobs','webhook_deliveries','webhook_events','ingestion_checkpoints','prospects','ucc_filings')
IDENTIFIER=re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,63}')

def diagnose(value):
 text=str(value)
 for label,pattern in (
  ('missing_table',r'no such table:\s*([A-Za-z_][A-Za-z0-9_]{0,63})(?:\s|:|$)'),
  ('missing_column',r'no such column:\s*([A-Za-z_][A-Za-z0-9_.]{0,63})(?:\s|:|$)'),
  ('missing_function',r'no such function:\s*([A-Za-z_][A-Za-z0-9_]{0,63})(?:\s|:|$)'),
  ('unknown_insert_column',r'has no column named\s+([A-Za-z_][A-Za-z0-9_]{0,63})(?:\s|:|$)'),
 ):
  match=re.search(pattern,text,re.I)
  if match:return {'category':label,'schema_identifier':match.group(1)}
 for phrase,label in [('too many sql variables','parameter_limit'),('syntax error','syntax_error'),
                      ('datatype mismatch','datatype'),('d1_type_error','bind_type'),
                      ('wrong number of arguments','function_arity'),('foreign key constraint','foreign_key'),
                      ('not null constraint','not_null'),('unique constraint','unique'),('database is locked','locked'),
                      ('exceeded','resource_limit'),('timeout','timeout')]:
  if phrase in text.lower():return {'category':label}
 return {'category':'unclassified'}

class Client(r.ReleaseClient):
 def schema(self,table):
  if table not in TABLES:raise r.inv.o.SafeError('schema_table_refused')
  sql='PRAGMA table_info('+table+')'
  result=self.request(f'/accounts/{self.aid}/d1/database/{self.db}/query','POST',
   json.dumps({'sql':sql,'params':[]}).encode())
  if len(result)!=1 or result[0].get('success') is not True:raise r.inv.o.SafeError('schema_read_failed')
  rows=result[0].get('results')
  if not isinstance(rows,list) or len(rows)>100:raise r.inv.o.SafeError('schema_shape_invalid')
  names=[]
  for row in rows:
   name=row.get('name')
   if not isinstance(name,str) or not IDENTIFIER.fullmatch(name):raise r.inv.o.SafeError('schema_identifier_invalid')
   names.append(name)
  return names

def error_categories(value, depth=0):
 if depth>8:return []
 if isinstance(value,dict):
  result=[]
  for key,item in value.items():
   if isinstance(key,str) and 'error' in key.lower() and isinstance(item,str):
    result.append(diagnose(item))
   elif isinstance(item,(dict,list)):
    result.extend(error_categories(item,depth+1))
  return result
 if isinstance(value,list):
  return [item for row in value[:100] for item in error_categories(row,depth+1)]
 return []

def recent_failures(client):
 def query(sql):
  rows=client.request(f'/accounts/{client.aid}/d1/database/{client.db}/query','POST',
   json.dumps({'sql':sql,'params':[]}).encode())
  if len(rows)!=1 or rows[0].get('success') is not True:raise r.inv.o.SafeError('log_metadata_read_failed')
  return rows[0].get('results',[])
 tables=query("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'scheduler_%' ORDER BY name LIMIT 8")
 if not isinstance(tables,list) or len(tables)>=8:raise r.inv.o.SafeError('log_table_bound')
 categories=[];examined=0;stores=[]
 for entry in tables:
  table=entry.get('name')
  if not isinstance(table,str) or not IDENTIFIER.fullmatch(table) or not table.startswith('scheduler_'):
   raise r.inv.o.SafeError('log_table_identifier_invalid')
  columns=query('PRAGMA table_info('+table+')')
  names={c.get('name') for c in columns}
  if 'payload' not in names:continue
  exclude="id <> 'scheduler:state' AND " if table=='scheduler_state' and 'id' in names else ''
  order='created_at' if 'created_at' in names else 'rowid'
  records=query("SELECT payload FROM "+table+" WHERE "+exclude+"instr(payload, 'ucc-staging') > 0 ORDER BY "+order+" DESC LIMIT 12")
  if not isinstance(records,list) or len(records)>12:raise r.inv.o.SafeError('log_metadata_shape_invalid')
  for row in records:categories.extend(error_categories(json.loads(row['payload'])))
  stores.append(table);examined+=len(records)
 return {'stores':stores,'records_examined':examined,'error_categories':categories}

def run(client):
 scheduler=client.settings('ops-scheduler-production')
 client.db=next(b['database_id'] for b in scheduler['bindings'] if b['name']=='SCHED_DB' and b['type']=='d1')
 state=json.loads(client.sql(r.STATE,('scheduler:state',))[0]['payload'])
 target=state.get('targetStates',{}).get('ucc-staging',{})
 errors={key:diagnose(value) for key,value in target.items()
         if isinstance(key,str) and re.fullmatch(r'[A-Za-z]{1,40}',key)
         and ('error' in key.lower() or 'failure' in key.lower()) and value is not None}
 recent=recent_failures(client)
 staging=client.settings('ucc-mca-edge-staging')
 databases=[b for b in staging['bindings'] if b['type']=='d1' and b['name']=='DB']
 if len(databases)!=1:raise r.inv.o.SafeError('staging_database_unresolved')
 client.db=databases[0]['database_id']
 return {'mode':'schema_and_error_only','mutations':0,'failed_target':'ucc-staging',
         'errors':errors,'recent_failures':recent,'columns':{table:client.schema(table) for table in TABLES}}

def main():
 try:report=run(Client(os.environ.get('CLOUDFLARE_API_TOKEN','')))
 except r.inv.o.SafeError as error:report={'error':str(error)}
 except Exception:report={'error':'schema_probe_failed'}
 print(json.dumps(report,indent=2,sort_keys=True));return int('error' in report)
if __name__=='__main__':raise SystemExit(main())
