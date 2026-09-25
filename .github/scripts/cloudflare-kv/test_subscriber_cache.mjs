import assert from 'node:assert/strict';
import test from 'node:test';
import {DatabaseSync} from 'node:sqlite';
import {subscriberCache,CACHE_KEY,CACHE_MS} from './subscriber-cache.mjs';
function fixture(){
 const sql=new DatabaseSync(':memory:');
 sql.exec('CREATE TABLE cf_kv_list_cache(product TEXT,key TEXT,payload TEXT,updated_at INTEGER,next_refresh INTEGER,generation INTEGER,PRIMARY KEY(product,key))');
 let time=Date.UTC(2026,8,24), scans=0;
 const values=new Map([['sub:one','entitlement']]);
 const db={prepare(q){let args;return{bind(...a){args=a;return this;},async first(){return sql.prepare(q).get(...args)??null;},async run(){const r=sql.prepare(q).run(...args);return{success:true,meta:{changes:Number(r.changes)}};}}}};
 const original={async list(options){scans++;return{keys:[...values.keys()].filter(k=>k.startsWith(options?.prefix??'')).map(name=>({name})),list_complete:true,cursor:''};},async get(key){return values.get(key)??null;},async put(key,value){values.set(key,value);},async delete(key){values.delete(key);}};
 const cache=subscriberCache(db,original,()=>time);
 return{sql,db,original,cache,values,scans:()=>scans,advance:ms=>time+=ms};
}
test('1440 scheduled enumerations and status polls require 288 lists over a day',async()=>{
 const f=fixture();
 for(let minute=0;minute<1440;minute++){
  for(let poll=0;poll<5;poll++)assert.equal((await f.cache.list({prefix:'sub:'})).keys.length,1);
  f.advance(60000);
 }
 assert.equal(f.scans(),288);
});
test('new subscriber invalidates immediately; entitlement get is never cached',async()=>{
 const f=fixture();await f.cache.list({prefix:'sub:'});
 await f.cache.put('sub:two','paid');
 assert.equal((await f.cache.list({prefix:'sub:'})).keys.length,2);
 f.values.set('sub:two','revoked');assert.equal(await f.cache.get('sub:two'),'revoked');
 await f.cache.delete('sub:two');assert.equal((await f.cache.list({prefix:'sub:'})).keys.length,1);
 assert.equal(f.scans(),3);
});
test('concurrent cold callers do not multiply the namespace scan',async()=>{
 const f=fixture();const results=await Promise.allSettled(Array.from({length:20},()=>f.cache.list({prefix:'sub:'})));
 assert.equal(f.scans(),1);assert(results.some(r=>r.status==='fulfilled'));
});
test('mutation during an in-flight scan cannot commit a stale index',async()=>{
 const f=fixture();let release;
 const originalList=f.original.list;
 f.original.list=async opts=>{const old=await originalList(opts);await new Promise(r=>release=r);return old;};
 const read=f.cache.list({prefix:'sub:'});
 while(!release)await new Promise(r=>setImmediate(r));
 await f.cache.put('sub:two','paid');release();
 await assert.rejects(read,/invalidated_during_refresh/);
 assert.equal(f.sql.prepare('SELECT updated_at FROM cf_kv_list_cache WHERE key=?').get(CACHE_KEY).updated_at,0);
});
test('custom cursor/limit and non-subscription keys retain original behavior',async()=>{
 const f=fixture();await f.cache.list({prefix:'sub:'});
 await f.cache.put('apikey:one','token');await f.cache.list({prefix:'sub:'});assert.equal(f.scans(),1);
 await f.cache.list({prefix:'sub:',cursor:'cursor'});await f.cache.list({prefix:'other:'});assert.equal(f.scans(),3);
});
test('expired scan failure is not converted into success or repeated every request',async()=>{
 const f=fixture();await f.cache.list({prefix:'sub:'});f.advance(CACHE_MS);
 f.original.list=async()=>{throw new Error('quota');};
 await assert.rejects(f.cache.list({prefix:'sub:'}),/quota/);
 assert.equal((await f.cache.list({prefix:'sub:'})).keys.length,1);
 f.advance(CACHE_MS);await assert.rejects(f.cache.list({prefix:'sub:'}),/quota/);
});

test('same-clock re-claim after invalidation cannot accept the old generation',async()=>{
 const f=fixture();let release;
 const originalList=f.original.list;
 let first=true;
 f.original.list=async opts=>{const result=await originalList(opts);if(first){first=false;await new Promise(r=>release=r);}return result;};
 const old=f.cache.list({prefix:'sub:'});while(!release)await new Promise(r=>setImmediate(r));
 await f.cache.put('sub:two','paid');
 assert.equal((await f.cache.list({prefix:'sub:'})).keys.length,2);
 release();await assert.rejects(old,/invalidated_during_refresh/);
 assert.equal((await f.cache.list({prefix:'sub:'})).keys.length,2);
});
