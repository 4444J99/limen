import assert from 'node:assert/strict';
import test from 'node:test';
import {DatabaseSync} from 'node:sqlite';
import {meterEnv,splitJob,MAX_DB_QUERIES,budgetIngress} from './bounded-jobs.mjs';
function fixture(){
 const db=new DatabaseSync(':memory:');
 db.exec('CREATE TABLE jobs(id TEXT PRIMARY KEY,type TEXT,payload TEXT,org_id TEXT,status TEXT,attempts INTEGER,created_at INTEGER,next_attempt_at INTEGER,lease_owner TEXT,lease_expires_at INTEGER)');
 let calls=0;
 const native={prepare(sql){let params=[];return{bind(...p){params=p;return this;},async first(){calls++;return db.prepare(sql).get(...params)??null;},async all(){calls++;return{results:db.prepare(sql).all(...params)};},async run(){calls++;const r=db.prepare(sql).run(...params);return{success:true,meta:{changes:Number(r.changes)}};},_run(){const r=db.prepare(sql).run(...params);return{success:true,meta:{changes:Number(r.changes)}};}};},async batch(statements){calls++;db.exec('BEGIN');try{const out=statements.map(s=>s._run());db.exec('COMMIT');return out;}catch(e){db.exec('ROLLBACK');throw e;}}};
 const env={DB:native,OTHER:'preserved'};
 const insert=(type,payload,lease='owned')=>{const job={id:'original',type,payload:JSON.stringify(payload),org_id:'tenant-one',lease_owner:lease,lease_expires_at:10000};db.prepare("INSERT INTO jobs VALUES(?,?,?,?,'processing',1,0,0,?,?)").run(job.id,type,job.payload,job.org_id,lease,job.lease_expires_at);return job;};
 return{db,env,insert,calls:()=>calls};
}
test('D1 metering counts prepared queries and rejects before the 45th provider call',async()=>{
 const f=fixture(),m=meterEnv(f.env);
 for(let i=0;i<MAX_DB_QUERIES;i++)await m.env.DB.prepare('SELECT 1').first();
 assert.throws(()=>m.env.DB.prepare('SELECT 1').first(),/budget_exhausted/);
 assert.equal(f.calls(),44);assert.equal(m.stats().dbQueries,44);assert.equal(m.env.OTHER,'preserved');
});
test('transactional split preserves every prospect, tenant, and original claim',async()=>{
 const f=fixture();const job=f.insert('ucc_enrichment',{prospectIds:['one','two','three'],force:true});
 const m=meterEnv(f.env),head=await splitJob(m.env,job,1000);
 assert.deepEqual(JSON.parse(head.payload).prospectIds,['one']);
 const rows=f.db.prepare('SELECT * FROM jobs ORDER BY status').all();
 const pending=rows.find(r=>r.status==='pending');assert.deepEqual(JSON.parse(pending.payload),{prospectIds:['two','three'],force:true});
 assert.equal(pending.org_id,'tenant-one');assert.equal(m.stats().dbQueries,2);
 assert.equal(f.db.prepare('SELECT lease_owner FROM jobs WHERE id=?').get(job.id).lease_owner,'owned');
 await splitJob(m.env,head,1001);assert.equal(f.db.prepare('SELECT count(*) n FROM jobs').get().n,2);
});
test('lost or expired lease creates no continuation and changes no original payload',async()=>{
 for(const kind of ['lost','expired']){const f=fixture(),job=f.insert('ucc_enrichment',{prospectIds:['one','two']});
 const stale={...job,lease_owner:kind==='lost'?'other':'owned'};
 await assert.rejects(splitJob(f.env,stale,kind==='expired'?10001:1000),/lease_not_owned/);
 assert.equal(f.db.prepare('SELECT count(*) n FROM jobs').get().n,1);assert.equal(f.db.prepare('SELECT payload FROM jobs').get().payload,job.payload);
 }
});
test('health continuation preserves the requested remainder',async()=>{
 const f=fixture(),job=f.insert('ucc_health',{batchSize:50});const head=await splitJob(f.env,job,1000);
 assert.equal(JSON.parse(head.payload).batchSize,1);
 assert.equal(JSON.parse(f.db.prepare("SELECT payload FROM jobs WHERE status='pending'").get().payload).batchSize,49);
});
test('other job types and single-record jobs stay unchanged',async()=>{
 for(const type of ['ucc_ingestion','webhook_delivery','ucc_enrichment']){const f=fixture(),j=f.insert(type,{prospectIds:['one']});assert.equal(await splitJob(f.env,j,1000),j);assert.equal(f.calls(),0);}
});
test('named ingress uses existing target credential and does not modify caller headers',async()=>{
 const req=new Request('https://internal/internal/run-scheduled',{method:'POST',body:'{}'});
 const original={async fetch(r){assert.equal(r.headers.get('Authorization'),'Bearer fixture');return new Response('ok');}};
 assert.equal((await budgetIngress(req,{SCHEDULER_SECRET:'fixture'},{},original)).status,200);
 assert.equal(req.headers.get('Authorization'),null);
 assert.equal((await budgetIngress(req,{},null,original)).status,503);
});
