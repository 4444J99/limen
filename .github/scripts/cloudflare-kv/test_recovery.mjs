import assert from 'node:assert/strict';
import test from 'node:test';
import { DatabaseSync } from 'node:sqlite';
import { recoverWorker, recoveryEnv, REVISION } from './recovery.mjs';
export const SCHEMA='CREATE TABLE cf_kv_recovery(product TEXT NOT NULL,key TEXT NOT NULL,payload TEXT NOT NULL,updated_at INTEGER NOT NULL,next_refresh INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(product,key))';
export function fixture(product='edgarflash') {
  const sql=new DatabaseSync(':memory:'); sql.exec(SCHEMA);
  const counts={read:0,write:0,lists:0,jobs:0,kv:0};
  const db={prepare(query){let params;return {
    bind(...p){params=p;return this;},
    async first(){counts.read++;return sql.prepare(query).get(...params)??null;},
    async run(){counts.write++;sql.prepare(query).run(...params);return {success:true};},
  };}};
  for(const [key,value] of [['status','{"name":"Fixture","subscriber_count":7}'],['last_seen_filings','[]'],['feed:recent','[]']]) {
    sql.prepare('INSERT INTO cf_kv_recovery VALUES(?,?,?,?,?)').run(product,key,value,Date.now(),Date.now()+3600000);
  }
  const env={INCIDENT_DB:db,EF_STATE:{get(){counts.kv++;throw Error('KV quota');},put(){counts.kv++;throw Error('KV quota');}},OTHER:'unchanged'};
  const original={async fetch(req,e){
    if(new URL(req.url).pathname==='/api/status'){counts.lists++;return Response.json({name:'Fixture'});}
    if(new URL(req.url).pathname==='/internal/run-scheduled'){counts.jobs++; await e.EF_STATE.put('feed:recent','[]');return Response.json({ok:true});}
    return new Response(e.OTHER,{status:401});
  },async scheduled(){counts.jobs++;}};
  const context={pending:[],waitUntil(p){this.pending.push(p);}};
  const worker=recoverWorker(original,product);
  return {sql,counts,env,worker,context,original,
    request(path='/api/status',init={}){return worker.fetch(new Request('https://test.workers.dev'+path,init),env,context);},
    async tick(){const r=await worker.fetch(new Request('https://internal/internal/run-scheduled',{method:'POST',body:JSON.stringify({scheduledTime:Date.now()})}),env,context);await Promise.all(context.pending.splice(0));return r;}};
}
test('10,000 liveness requests have no database or KV operations',async()=>{
 const f=fixture();for(let i=0;i<10000;i++)assert.equal((await f.request('/healthz')).status,200);
 assert.deepEqual(f.counts,{read:0,write:0,lists:0,jobs:0,kv:0});
});
test('public polling, cold wrappers and refresh=true never list or write KV',async()=>{
 const f=fixture();for(let i=0;i<1000;i++)assert.equal((await f.request('/api/status?refresh=true')).status,200);
 assert.equal(f.counts.kv,0);assert.equal(f.counts.lists,0);assert.equal(f.counts.write,0);
});
test('public scheduled requests cannot run jobs',async()=>{
 const f=fixture();assert.equal((await f.request('/internal/run-scheduled',{method:'POST',body:'{}'})).status,403);assert.equal(f.counts.jobs,0);
});
test('existing internal job operates while old KV writes throw',async()=>{
 const f=fixture();assert.equal((await f.tick()).status,200);assert.equal(f.counts.jobs,1);assert.equal(f.counts.kv,0);
 assert.equal(JSON.parse(f.sql.prepare("SELECT payload FROM cf_kv_recovery WHERE key='last_job'").get().payload).ok,true);
});
test('atomic status lease permits one sample across concurrent jobs',async()=>{
 const f=fixture();f.sql.prepare("UPDATE cf_kv_recovery SET next_refresh=0 WHERE key='status'").run();
 await Promise.all(Array.from({length:10},()=>f.tick()));assert.equal(f.counts.lists,1);assert.equal(f.counts.jobs,10);
});
test('missing/corrupt/future/stale snapshots fail without scans',async()=>{
 for(const kind of ['missing','corrupt','future','stale']){const f=fixture();
  if(kind==='missing')f.sql.prepare("DELETE FROM cf_kv_recovery WHERE key='status'").run();
  if(kind==='corrupt')f.sql.prepare("UPDATE cf_kv_recovery SET payload='!' WHERE key='status'").run();
  if(kind==='future')f.sql.prepare("UPDATE cf_kv_recovery SET updated_at=? WHERE key='status'").run(Date.now()+100000);
  if(kind==='stale')f.sql.prepare("UPDATE cf_kv_recovery SET updated_at=0 WHERE key='status'").run();
  assert.equal((await f.request()).status,503);assert.equal(f.counts.lists,0);assert.equal(f.counts.kv,0);
 }
});
test('unseeded state and unexpected keys fail closed, do not fall back to KV',async()=>{
 const f=fixture();const state=recoveryEnv(f.env,'edgarflash').EF_STATE;
 await assert.rejects(state.get('unknown'));await assert.rejects(state.put('unknown','[]'));
 f.sql.prepare("DELETE FROM cf_kv_recovery WHERE key='feed:recent'").run();await assert.rejects(state.get('feed:recent'));assert.equal(f.counts.kv,0);
});
test('original authentication response and other bindings remain unchanged',async()=>{
 const f=fixture();const r=await f.request('/api/realtime');assert.equal(r.status,401);assert.equal(await r.text(),'unchanged');
});
test('status freshness and liveness are explicitly distinct',async()=>{
 const f=fixture();assert.equal((await (await f.request('/healthz')).json()).check,'liveness_only');
 const b=await(await f.request()).json();assert.equal(b._status_snapshot.revision,REVISION);assert.equal(b.subscriber_count,7);
});
test('method and payload validation cannot dispatch jobs',async()=>{
 const f=fixture();assert.equal((await f.request('/api/status',{method:'POST'})).status,405);
 const r=await f.worker.fetch(new Request('https://internal/internal/run-scheduled',{method:'POST',body:'{}'}),f.env,f.context);
 assert.equal(r.status,400);assert.equal(f.counts.jobs,0);
});
