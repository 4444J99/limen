/** Incident repair over the preserved live Worker, not a stale source replacement. */
export const REVISION = 'kv-recovery-d1-20260923-v1';
const PERIOD = { edgarflash: 3600000, trendpulse: 14400000, vulnpulse: 86400000 };
const STATE_KEYS = new Set(['last_seen_filings', 'feed:recent']);
const SELECT = 'SELECT payload, updated_at FROM cf_kv_recovery WHERE product = ? AND key = ?';
const UPSERT = 'INSERT INTO cf_kv_recovery(product,key,payload,updated_at,next_refresh) VALUES(?,?,?,?,0) ON CONFLICT(product,key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at';

async function read(db, product, key) {
  return db.prepare(SELECT).bind(product, key).first();
}
async function write(db, product, key, value) {
  if (typeof value !== 'string' || value.length > 262144) throw new Error('recovery_value_invalid');
  const result = await db.prepare(UPSERT).bind(product, key, value, Date.now()).run();
  if (result.success === false) throw new Error('recovery_write_failed');
}
export function recoveryEnv(env, product) {
  if (product !== 'edgarflash') return env;
  const state = {
    async get(key) {
      if (!STATE_KEYS.has(key)) throw new Error('recovery_state_key_refused');
      const row = await read(env.INCIDENT_DB, product, key);
      if (!row) throw new Error('recovery_state_not_seeded');
      return row.payload;
    },
    async put(key, value) {
      if (!STATE_KEYS.has(key)) throw new Error('recovery_state_key_refused');
      await write(env.INCIDENT_DB, product, key, value);
    },
  };
  return new Proxy(env, { get(target, key) { return key === 'EF_STATE' ? state : Reflect.get(target, key); } });
}

export function recoverWorker(original, product) {
  if (!PERIOD[product]) throw new Error('recovery_product_refused');
  async function sample(env, ctx) {
    const now = Date.now();
    // Atomic claim: concurrent scheduler retries cannot multiply status scans.
    const claim = await env.INCIDENT_DB.prepare(
      "UPDATE cf_kv_recovery SET next_refresh=? WHERE product=? AND key='status' AND next_refresh<=? RETURNING key"
    ).bind(now + PERIOD[product], product, now).first();
    if (!claim) return;
    const response = await original.fetch(new Request('https://internal/api/status'), recoveryEnv(env, product), ctx);
    if (!response.ok) throw new Error('recovery_status_sample_failed');
    const body = await response.text();
    const parsed = JSON.parse(body);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('recovery_status_invalid');
    await write(env.INCIDENT_DB, product, 'status', body);
  }
  return {
    async fetch(request, env, ctx) {
      const url = new URL(request.url);
      const path = url.pathname;
      const headers = { 'cache-control': 'no-store' };
      if (path === '/healthz') {
        if (!['GET', 'HEAD'].includes(request.method)) return new Response(null, {status:405});
        const r = Response.json({ product, revision:REVISION, check:'liveness_only' }, {headers});
        return request.method === 'HEAD' ? new Response(null,r) : r;
      }
      if (path === '/api/status') {
        if (!['GET','HEAD'].includes(request.method)) return new Response(null,{status:405});
        try {
          const row = await read(env.INCIDENT_DB, product, 'status');
          if (!row) throw new Error('missing');
          const age = Date.now() - row.updated_at;
          const stale = !Number.isFinite(age) || age < 0 || age > PERIOD[product] * 2;
          const body = JSON.parse(row.payload);
          if (!body || typeof body !== 'object' || Array.isArray(body)) throw new Error('corrupt');
          const r = Response.json({...body, _status_snapshot:{
            revision:REVISION, observed_at:new Date(row.updated_at).toISOString(),
            age_seconds:Math.max(0,Math.floor(age/1000)), stale,
          }}, {status:stale?503:200,headers});
          return request.method === 'HEAD' ? new Response(null,r) : r;
        } catch {
          return Response.json({error:'status_snapshot_unavailable', revision:REVISION}, {status:503,headers});
        }
      }
      if (path === '/internal/run-scheduled') {
        // The existing scheduler Service Binding uses https://internal. Requests
        // arriving on the public workers.dev/custom hostname cannot trigger jobs.
        if (url.hostname !== 'internal') return Response.json({error:'internal_only'},{status:403});
        if (request.method !== 'POST') return new Response(null,{status:405});
        let payload;
        try { payload = await request.clone().json(); } catch { return new Response(null,{status:400}); }
        if (!Number.isFinite(payload?.scheduledTime)) return new Response(null,{status:400});
        const response = await original.fetch(request, recoveryEnv(env, product), ctx);
        let ok = false;
        try { ok = response.ok && (await response.clone().json()).ok === true; } catch {}
        await write(env.INCIDENT_DB, product, 'last_job', JSON.stringify({
          scheduled_at:payload.scheduledTime, completed_at:Date.now(), ok,
        }));
        // Sample failure is independently visible; it never changes a completed
        // product result into a retry that could duplicate deliveries.
        const refresh = sample(env, ctx).catch(() => console.warn('recovery_status_sample_failed'));
        if (ctx?.waitUntil) ctx.waitUntil(refresh); else await refresh;
        return response;
      }
      return original.fetch(request, recoveryEnv(env, product), ctx);
    },
    async scheduled(event, env, ctx) {
      // No native product cron is added by the release. Preserve this export.
      return original.scheduled(event, recoveryEnv(env, product), ctx);
    },
  };
}
