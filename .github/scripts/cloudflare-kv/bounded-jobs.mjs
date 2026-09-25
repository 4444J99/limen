/** Bound actual D1 work; split claimed jobs without losing their unprocessed tail. */
export const MAX_DB_QUERIES = 44;
export const SPLIT_INSERT = `INSERT INTO jobs (id,type,payload,org_id,status,attempts,created_at,next_attempt_at)
SELECT ?,type,?,org_id,'pending',0,?,? FROM jobs
WHERE id=? AND status='processing' AND lease_owner=? AND lease_expires_at>? AND payload=?`;
export const SPLIT_UPDATE = `UPDATE jobs SET payload=?
WHERE id=? AND status='processing' AND lease_owner=? AND lease_expires_at>? AND payload=?`;

export function meterEnv(env, cap=MAX_DB_QUERIES) {
  if (!Number.isInteger(cap) || cap<1 || cap>MAX_DB_QUERIES) throw new Error('invalid_database_budget');
  let used=0;
  const nativeStatements=new WeakMap();
  function spend(n) {
    if (used+n>cap) throw new Error('invocation_database_budget_exhausted');
    used+=n;
  }
  function statement(native) {
    const proxy=new Proxy(native,{get(target,key){
      if (key==='bind') return (...args)=>statement(target.bind(...args));
      if (['all','first','run','raw'].includes(key)) return (...args)=>{
        spend(1);return target[key](...args);
      };
      const value=Reflect.get(target,key,target);
      return typeof value==='function'?value.bind(target):value;
    }});
    nativeStatements.set(proxy,native);return proxy;
  }
  const db=new Proxy(env.DB,{get(target,key){
    if (key==='prepare') return sql=>statement(target.prepare(sql));
    if (key==='batch') return statements=>{
      spend(statements.length);
      return target.batch(statements.map(s=>nativeStatements.get(s)??s));
    };
    if (key==='exec' || key==='withSession') return ()=>{throw new Error('unmetered_database_operation_refused');};
    const value=Reflect.get(target,key,target);
    return typeof value==='function'?value.bind(target):value;
  }});
  return {
    env:new Proxy(env,{get(target,key){return key==='DB'?db:Reflect.get(target,key);}}),
    stats:()=>({dbQueries:used,dbQueryLimit:cap,maxJobsPerPass:1,maxRecordsPerJob:1}),
  };
}

export async function splitJob(env, job, now=Date.now()) {
  let payload;
  try {payload=JSON.parse(job.payload??'{}');} catch {return job;}
  let head,tail;
  if (job.type==='ucc_enrichment' && Array.isArray(payload.prospectIds) && payload.prospectIds.length>1) {
    head={...payload,prospectIds:payload.prospectIds.slice(0,1)};
    tail={...payload,prospectIds:payload.prospectIds.slice(1)};
  } else if (job.type==='ucc_health' && Number.isInteger(payload.batchSize) && payload.batchSize>1) {
    head={...payload,batchSize:1};tail={...payload,batchSize:payload.batchSize-1};
  } else {return job;}
  const headJson=JSON.stringify(head), tailJson=JSON.stringify(tail);
  // D1 batch is transactional. Both statements are guarded by the same exact
  // live lease and original payload. A retried one-item head cannot split again.
  const results=await env.DB.batch([
    env.DB.prepare(SPLIT_INSERT).bind(crypto.randomUUID(),tailJson,now,now,
      job.id,job.lease_owner,now,job.payload),
    env.DB.prepare(SPLIT_UPDATE).bind(headJson,job.id,job.lease_owner,now,job.payload),
  ]);
  if (results.length!==2 || results.some(r=>r.success===false || r.meta?.changes!==1)) {
    throw new Error('job_split_lease_not_owned');
  }
  return {...job,payload:headJson};
}

export async function budgetIngress(request,env,ctx,original) {
  if (new URL(request.url).pathname!=='/internal/run-scheduled') return new Response(null,{status:404});
  if (request.method!=='POST') return new Response(null,{status:405});
  if (typeof env.SCHEDULER_SECRET!=='string' || !env.SCHEDULER_SECRET) return new Response(null,{status:503});
  const headers=new Headers(request.headers);headers.set('Authorization','Bearer '+env.SCHEDULER_SECRET);
  return original.fetch(new Request(request,{headers}),env,ctx);
}
