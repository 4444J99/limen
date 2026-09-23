import assert from 'node:assert/strict';
import test from 'node:test';
import {appendRecoveryTargets,REPLAY_END,RETRY_KEY,failureCode} from './bounded_finishline.mjs';
function fixture(){let reads=0;const claims=new Map();return{claims,reads:()=>reads,
 env:{SCHED_DB:{prepare(){let k;return{bind(key){k=key;return this;},async first(){reads++;const row=claims.get(k);claims.delete(k);return row;}}}}},
 lookup:name=>({name,active:true,schedule:'0 0,2,6,12,18 * * *'})};}
test('one day contains 144 UCC slots, preserving natural slots and using drain-only otherwise',async()=>{
 const f=fixture();let count=0,natural=0;
 for(let minute=0;minute<1440;minute++){
  const t=REPLAY_END+minute*60000, hour=Math.floor(minute/60);
  const due=minute%60===0&&[0,2,6,12,18].includes(hour)?[{target:f.lookup('ucc-staging'),payload:{scheduledTime:t}}]:[];
  const out=await appendRecoveryTargets(f.env,due,t,f.lookup);count+=out.length;
  if(due.length){natural++;assert.equal(out.length,1);assert.equal(out[0],due[0]);}
  else if(out.length)assert.equal(out[0].payload.drainOnly,true);
 }
 assert.equal(count,144);assert.equal(natural,5);assert.equal(f.reads(),0);
});
test('inactive targets cannot be added and unrelated due jobs are preserved',async()=>{
 const f=fixture(),due=[{target:{name:'other'},payload:{}}];
 assert.deepEqual(await appendRecoveryTargets(f.env,due,REPLAY_END,()=>({active:false})),due);
});
test('one-shot drain claim executes once and never duplicates an existing natural invocation',async()=>{
 const f=fixture(),time=Date.parse('2026-09-23T22:41:00Z');
 f.claims.set(RETRY_KEY+'ucc-staging',{payload:JSON.stringify({scheduledTime:time-60000,drainOnly:true})});
 const out=await appendRecoveryTargets(f.env,[],time,f.lookup);assert.equal(out.length,1);assert.equal(out[0].payload.drainOnly,true);
 assert.deepEqual(await appendRecoveryTargets(f.env,[],time,f.lookup),[]);
 f.claims.set(RETRY_KEY+'ucc-staging',{payload:JSON.stringify({scheduledTime:time-60000,drainOnly:true})});
 const due=[{target:f.lookup('ucc-staging'),payload:{}}];assert.deepEqual(await appendRecoveryTargets(f.env,due,time,f.lookup),due);
});
test('invalid timestamps cannot create queue work',async()=>{
 const f=fixture();for(const t of [NaN,Infinity,1e30])assert.deepEqual(await appendRecoveryTargets(f.env,[],t,f.lookup),[]);
 assert.equal(f.reads(),0);
});
test('real platform request-limit message has a non-sensitive category',()=>{
 assert.equal(failureCode('Too many API requests by single Worker invocation.'),'invocation_request_limit');
});
