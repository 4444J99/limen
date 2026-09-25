/** Scoped reconciliation through a non-public named Service Binding. */
export const REPLAY_END = Date.parse('2026-09-25T00:00:00Z');
export const RETRY_KEY = 'retry-auth-20260923-v1:';
export const CLAIM_SQL = "UPDATE cf_kv_recovery SET next_refresh=0 WHERE product='incident' AND key=? AND next_refresh=1 RETURNING payload";
export async function scheduledIngress(request, env, ctx, original) {
  if (new URL(request.url).pathname !== '/internal/run-scheduled') return new Response(null,{status:404});
  if (request.method !== 'POST') return new Response(null,{status:405});
  let body;
  try { body=await request.clone().json(); } catch { return new Response(null,{status:400}); }
  if (!Number.isFinite(body?.scheduledTime)) return new Response(null,{status:400});
  if (typeof env.SCHEDULER_SECRET !== 'string' || !env.SCHEDULER_SECRET) {
    return Response.json({ok:false,error:'scheduler_credential_missing'},{status:503});
  }
  // This helper is used ONLY by the named WorkerEntrypoint. The public default
  // export is unchanged. The existing credential never leaves the target Worker.
  const headers=new Headers(request.headers);
  headers.set('Authorization','Bearer '+env.SCHEDULER_SECRET);
  return original.fetch(new Request(request,{headers}),env,ctx);
}
export function failureCode(error) {
  const text=String(error??'');
  if (/KV|key.?value/i.test(text) && /429|limit|quota/i.test(text)) return 'kv_quota';
  if (/401|unauthorized/i.test(text)) return 'authorization';
  if (/NVD|nvd.nist/i.test(text)) return 'nvd_upstream';
  if (/timeout|abort/i.test(text)) return 'timeout';
  if (/subrequests/i.test(text)) return 'subrequest_limit';
  if (/D1|SQLITE|no such table|no such column/i.test(text)) return 'database';
  if (/AI|neurons|model/i.test(text)) return 'ai_upstream';
  if (/Service Binding|binding.*not found/i.test(text)) return 'binding_missing';
  return 'unclassified_failure';
}
export async function appendRecoveryTargets(env, due, scheduledTime, lookup) {
  if (!Number.isFinite(scheduledTime) || scheduledTime>=REPLAY_END) return due;
  const result=[...due];
  for (const name of ['ucc-staging','vulnpulse']) {
    // A naturally due invocation owns that slot: do not add another one.
    const existing=due.some(item=>item.target.name===name);
    const row=await env.SCHED_DB.prepare(CLAIM_SQL).bind(RETRY_KEY+name).first();
    if (!row || existing) continue;
    const payload=JSON.parse(row.payload);
    const target=lookup(name);
    if (!target?.active || !Number.isFinite(payload?.scheduledTime)
        || payload.scheduledTime>scheduledTime || scheduledTime-payload.scheduledTime>86400000) {
      throw new Error('recovery_payload_or_target_invalid');
    }
    result.push({target,payload:{scheduledTime:payload.scheduledTime,cron:target.schedule,target:name}});
  }
  return result;
}
