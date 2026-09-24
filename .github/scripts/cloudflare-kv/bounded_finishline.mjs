/** Internal scheduler ingress plus bounded, queue-only UCC continuation ticks. */
export const REPLAY_END=Date.parse('2026-09-25T00:00:00Z');
export const RETRY_KEY='retry-budget-20260923-v4:';
export const CLAIM_SQL="UPDATE cf_kv_recovery SET next_refresh=0 WHERE product='incident' AND key=? AND next_refresh=1 RETURNING payload";
export async function scheduledIngress(request,env,ctx,original){
 if(new URL(request.url).pathname!=='/internal/run-scheduled')return new Response(null,{status:404});
 if(request.method!=='POST')return new Response(null,{status:405});
 let body;try{body=await request.clone().json();}catch{return new Response(null,{status:400});}
 if(!Number.isFinite(body?.scheduledTime))return new Response(null,{status:400});
 if(typeof env.SCHEDULER_SECRET!=='string'||!env.SCHEDULER_SECRET)return Response.json({ok:false,error:'scheduler_credential_missing'},{status:503});
 const headers=new Headers(request.headers);headers.set('Authorization','Bearer '+env.SCHEDULER_SECRET);
 return original.fetch(new Request(request,{headers}),env,ctx);
}
export function failureCode(error){
 const text=String(error??'');
 if(/Too many API requests by single Worker invocation|subrequests/i.test(text))return 'invocation_request_limit';
 if(/KV|key.?value/i.test(text)&&/429|limit|quota/i.test(text))return 'kv_quota';
 if(/401|unauthorized/i.test(text))return 'authorization';
 if(/NVD|nvd.nist/i.test(text))return 'nvd_upstream';
 if(/timeout|abort/i.test(text))return 'timeout';
 if(/D1|SQLITE|no such table|no such column/i.test(text))return 'database';
 if(/AI|neurons|model/i.test(text))return 'ai_upstream';
 if(/Service Binding|binding.*not found/i.test(text))return 'binding_missing';
 return 'unclassified_failure';
}
export async function appendRecoveryTargets(env,due,scheduledTime,lookup){
 if(!Number.isFinite(scheduledTime)||!Number.isFinite(new Date(scheduledTime).getTime()))return due;
 const result=[...due],target=lookup('ucc-staging');
 // A natural pipeline slot takes precedence. Other ten-minute slots drain only
 // already-queued work; they never enqueue the scheduled ingestion/enrichment plan.
 if(target?.active&&new Date(scheduledTime).getUTCMinutes()%10===0&&!result.some(x=>x.target.name==='ucc-staging')){
  result.push({target,payload:{scheduledTime,cron:target.schedule,target:target.name,drainOnly:true}});
 }
 if(scheduledTime>=REPLAY_END)return result;
 const row=await env.SCHED_DB.prepare(CLAIM_SQL).bind(RETRY_KEY+'ucc-staging').first();
 if(!row||result.some(x=>x.target.name==='ucc-staging'))return result;
 const body=JSON.parse(row.payload);
 if(!target?.active||!Number.isFinite(body.scheduledTime)||body.scheduledTime>scheduledTime||scheduledTime-body.scheduledTime>86400000||body.drainOnly!==true)throw new Error('bounded_replay_payload_invalid');
 result.push({target,payload:{scheduledTime:body.scheduledTime,cron:target.schedule,target:target.name,drainOnly:true}});
 return result;
}
