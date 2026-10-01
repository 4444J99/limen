import assert from 'node:assert/strict';
import test from 'node:test';
import {DatabaseSync} from 'node:sqlite';
import {scheduledIngress,appendRecoveryTargets,failureCode,RETRY_KEY,REPLAY_END} from './finishline.mjs';
const NOW=Date.parse('2026-09-23T22:00:00Z');
function fixture(){
 const db=new DatabaseSync(':memory:');
 db.exec('CREATE TABLE cf_kv_recovery(product TEXT,key TEXT,payload TEXT,next_refresh INTEGER,PRIMARY KEY(product,key))');
 let count=0;
 const env={SCHED_DB:{prepare(q){let p;return{bind(...args){p=args;return this;},async first(){count++;return db.prepare(q).get(...p);}}}}};
 const lookup=name=>({name,active:true,schedule:name==='vulnpulse'?'0 12 * * *':'0 0,2,6,12,18 * * *'});
 const seed=(name,time=NOW-3600000)=>db.prepare('INSERT INTO cf_kv_recovery VALUES(?,?,?,1)').run('incident',RETRY_KEY+name,JSON.stringify({scheduledTime:time}));
 return {db,env,lookup,seed,count:()=>count};
}
test('ingress uses only the target Worker credential and preserves body/context',async()=>{
 const env={SCHEDULER_SECRET:'fixture-only-secret'},ctx={};
 const req=new Request('https://internal/internal/run-scheduled',{method:'POST',body:JSON.stringify({scheduledTime:NOW})});
 const original={async fetch(r,e,c){assert.equal(r.headers.get('Authorization'),'Bearer fixture-only-secret');assert.equal(e,env);assert.equal(c,ctx);assert.equal((await r.json()).scheduledTime,NOW);return Response.json({ok:true});}};
 const r=await scheduledIngress(req,env,ctx,original);assert.equal(r.status,200);assert.equal(req.headers.get('Authorization'),null);
});
test('ingress rejects missing credential, wrong method/path and invalid payload',async()=>{
 let calls=0;const original={fetch(){calls++;}};
 for(const [path,method,body,expected] of [['/wrong','POST','{}',404],['/internal/run-scheduled','GET',undefined,405],['/internal/run-scheduled','POST','{',400],['/internal/run-scheduled','POST','{}',400],['/internal/run-scheduled','POST',JSON.stringify({scheduledTime:NOW}),503]]){
  const r=await scheduledIngress(new Request('https://internal'+path,{method,body}),{},null,original);assert.equal(r.status,expected);
 }
 assert.equal(calls,0);
});
test('one-time replay is consumed once without replaying naturally due jobs',async()=>{
 const f=fixture();f.seed('vulnpulse');f.seed('ucc-staging');
 const due=[{target:f.lookup('vulnpulse'),payload:{scheduledTime:NOW}}];
 const first=await appendRecoveryTargets(f.env,due,NOW,f.lookup);assert.equal(first.length,2);assert.equal(first[1].target.name,'ucc-staging');assert.equal(due.length,1);
 assert.deepEqual(await appendRecoveryTargets(f.env,[],NOW,f.lookup),[]);
});
test('expired repair has zero database calls',async()=>{
 const f=fixture();f.seed('vulnpulse');assert.deepEqual(await appendRecoveryTargets(f.env,[],REPLAY_END,f.lookup),[]);assert.equal(f.count(),0);
});
test('unknown/inactive/future payloads fail closed',async()=>{
 for(const mode of ['future','inactive']){const f=fixture();f.seed('vulnpulse',mode==='future'?NOW+1:NOW-1000);const lookup=mode==='inactive'?()=>({active:false}):f.lookup;await assert.rejects(appendRecoveryTargets(f.env,[],NOW,lookup));}
});
test('failure codes never echo arbitrary provider contents',()=>{
 assert.equal(failureCode('KV PUT failed: 429 quota exhausted'),'kv_quota');assert.equal(failureCode('HTTP 401 unauthorized'),'authorization');assert.equal(failureCode('private-secret-goes-here'),'unclassified_failure');
});
