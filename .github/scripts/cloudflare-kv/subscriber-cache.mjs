/** Account-wide LIST conservation without caching subscription entitlements. */
export const CACHE_MS = 5 * 60 * 1000;
export const CACHE_KEY = 'subscriber-index:v1';
const SELECT = 'SELECT payload,updated_at,next_refresh,generation FROM cf_kv_list_cache WHERE product=? AND key=?';
const INSERT = 'INSERT INTO cf_kv_list_cache(product,key,payload,updated_at,next_refresh,generation) VALUES(?,?,?,0,0,0) ON CONFLICT(product,key) DO NOTHING';
export const CLAIM = 'UPDATE cf_kv_list_cache SET next_refresh=? WHERE product=? AND key=? AND next_refresh<=? RETURNING payload,updated_at,generation';
const COMMIT = 'UPDATE cf_kv_list_cache SET payload=?,updated_at=? WHERE product=? AND key=? AND next_refresh=? AND generation=?';
const INVALIDATE = 'UPDATE cf_kv_list_cache SET updated_at=0,next_refresh=0,generation=generation+1 WHERE product=? AND key=?';
const PRODUCT = 'edgarflash';
function decode(raw) {
  try {
    const value=JSON.parse(raw);
    if (!value || !Array.isArray(value.keys) || typeof value.list_complete!=='boolean'
      || value.keys.some(k=>!k || typeof k.name!=='string')) return null;
    return value;
  } catch { return null; }
}
async function checkedRun(statement) {
  const result=await statement.run();
  if (result.success===false) throw new Error('subscriber_index_database_failed');
  return result;
}
export function subscriberCache(db, original, now=Date.now) {
  async function invalidate(key) {
    if (typeof key==='string' && key.startsWith('sub:')) {
      await checkedRun(db.prepare(INVALIDATE).bind(PRODUCT,CACHE_KEY));
    }
  }
  async function list(options) {
    // Cache exactly the existing enumeration. Entitlement get(), other prefixes,
    // custom limits and explicit pagination retain their original semantics.
    if (!options || options.prefix!=='sub:' || Object.keys(options).some(k=>k!=='prefix')) {
      return original.list(options);
    }
    const time=now();
    let row=await db.prepare(SELECT).bind(PRODUCT,CACHE_KEY).first();
    let cached=decode(row?.payload);
    if (cached && row.updated_at>0 && time>=row.updated_at && time-row.updated_at<CACHE_MS) return cached;
    if (!row) await checkedRun(db.prepare(INSERT).bind(PRODUCT,CACHE_KEY,'null'));
    const lease=time+CACHE_MS;
    const claim=await db.prepare(CLAIM).bind(lease,PRODUCT,CACHE_KEY,time).first();
    if (!claim) {
      row=await db.prepare(SELECT).bind(PRODUCT,CACHE_KEY).first();
      cached=decode(row?.payload);
      // A single refresh is in flight. Never turn contention into another KV
      // scan. Explicit mutation invalidation sets updated_at=0 and refuses stale.
      if (cached && row.updated_at>0 && time>=row.updated_at && time-row.updated_at<2*CACHE_MS) return cached;
      throw new Error('subscriber_index_refresh_in_progress');
    }
    const result=await original.list(options);
    const payload=JSON.stringify(result);
    if (!decode(payload) || payload.length>524288) throw new Error('subscriber_index_result_invalid');
    const stored=await checkedRun(db.prepare(COMMIT).bind(payload,now(),PRODUCT,CACHE_KEY,lease,claim.generation));
    if (stored.meta?.changes!==1) throw new Error('subscriber_index_invalidated_during_refresh');
    return result;
  }
  return new Proxy(original, { get(target,property) {
    if (property==='list') return list;
    if (property==='put' || property==='delete') return async (key,...args)=>{
      // Invalidate before and after: do not allow an in-flight pre-mutation scan
      // to become the cached index after a successful subscription change.
      await invalidate(key);
      const result=await target[property](key,...args);
      await invalidate(key);
      return result;
    };
    const value=Reflect.get(target,property,target);
    return typeof value==='function'?value.bind(target):value;
  }});
}
