import assert from "node:assert/strict";
import test from "node:test";
import { ChunkedDurableStateStore, durableStateStoreContract } from "../src/conduct/durable-store.js";
import { RecordDurableStateStore, recordStateStoreContract } from "../src/conduct/record-store.js";

class Storage {
  constructor() { this.values = new Map(); this.reset(); }
  reset(failAt = Infinity) { this.puts = 0; this.deletes = 0; this.failAt = failAt; }
  async get(key) {
    if (Array.isArray(key)) return new Map(key.filter(k => this.values.has(k)).map(k => [k, structuredClone(this.values.get(k))]));
    return structuredClone(this.values.get(key));
  }
  async list({prefix = ""} = {}) {
    return new Map([...this.values].filter(([k]) => k.startsWith(prefix)).map(([k,v]) => [k,structuredClone(v)]));
  }
  async put(key, value) {
    if (++this.puts === this.failAt) throw new Error("injected commit failure");
    this.values.set(key, structuredClone(value));
  }
  async delete(keys) {
    for (const key of Array.isArray(keys) ? keys : [keys]) { this.deletes++; this.values.delete(key); }
  }
  async transaction(callback) {
    const before = structuredClone(this.values);
    try { return await callback(this); } catch (error) { this.values = before; throw error; }
  }
}

function state(history = 0) {
  return {schema_version:"limen.conduct_state.v1", sessions:{}, session_principals:{},
    session_principal_roles:{}, runs:{}, leases:{}, next_generation:0, next_event_sequence:history,
    events:Array.from({length:history}, (_,i) => ({sequence:i+1,kind:"test.history",detail:"custody".repeat(12)}))};
}
function registered(before) {
  const next = structuredClone(before);
  next.sessions.new = {session_id:"new",heartbeat_at:"2026-10-18T23:00:00Z"};
  next.session_principals.new = {principal_id:"codex"};
  next.session_principal_roles.new = ["observer"];
  next.next_event_sequence++;
  next.events.push({sequence:next.next_event_sequence,kind:"session.registered",session_id:"new"});
  return next;
}
const empty = () => state();

for (const size of [0, 2400, 12000]) {
  test("registration writes six rows with "+size+" historical events", async () => {
    const storage = new Storage();
    const store = new RecordDurableStateStore(storage, empty);
    const before = state(size);
    await store.save(before);
    storage.reset();
    const after = registered(before);
    await store.save(after);
    assert.equal(storage.puts, 6); // session, principal, roles, event, sequence counter, commit manifest
    assert.equal(storage.deletes, 0);
    assert.deepEqual(await new RecordDurableStateStore(storage, empty).load(), after);
    storage.reset();
    await store.save(after);
    assert.equal(storage.puts, 0);
    assert.equal(storage.deletes, 0);
  });
}

test("migration retains the deployed checkpoint and preserves oversized records", async () => {
  const storage = new Storage();
  const before = state(2400);
  before.runs.large = {receipt:"custody".repeat(40000)};
  const legacy = new ChunkedDurableStateStore(storage, empty);
  await legacy.save(before);
  const oldManifest = await storage.get(durableStateStoreContract.manifest_key);
  const store = new RecordDurableStateStore(storage, empty);
  assert.deepEqual(await store.load(), before);
  const after = registered(before);
  await store.save(after);
  assert.deepEqual((await storage.get(recordStateStoreContract.legacy_checkpoint_key)).manifest, oldManifest);
  assert.deepEqual(await new RecordDurableStateStore(storage, empty).load(), after);
  await assert.rejects(legacy.load(), /manifest is invalid/);
});

test("every differential commit failure preserves the complete previous generation", async () => {
  const storage = new Storage();
  const before = state(25);
  await new RecordDurableStateStore(storage, empty).save(before);
  const baseline = structuredClone(storage.values);
  for (let failAt = 1; failAt <= 6; failAt++) {
    storage.values = structuredClone(baseline);
    const store = new RecordDurableStateStore(storage, empty);
    await store.load();
    storage.reset(failAt);
    await assert.rejects(store.save(registered(before)), /injected commit failure/);
    assert.deepEqual(await new RecordDurableStateStore(storage, empty).load(), before);
    storage.reset();
    await store.save(registered(before));
    assert.deepEqual(await new RecordDurableStateStore(storage, empty).load(), registered(before));
  }
});

test("selected missing or corrupted rows never fall back to the old checkpoint", async () => {
  for (const corrupt of [false,true]) {
    const storage = new Storage();
    await new ChunkedDurableStateStore(storage, empty).save(state());
    await new RecordDurableStateStore(storage, empty).save(registered(state()));
    const key = [...storage.values.keys()].find(k => k.startsWith(recordStateStoreContract.row_prefix));
    if (corrupt) storage.values.get(key).data[0] ^= 1;
    else storage.values.delete(key);
    await assert.rejects(new RecordDurableStateStore(storage, empty).load(), /record|digest|count/);
  }
});

test("rollback materializes exact state in the deployed format atomically", async () => {
  const storage = new Storage();
  const after = registered(state(25));
  await new RecordDurableStateStore(storage, empty).save(after);
  const store = new RecordDurableStateStore(storage, empty, {recordPersistence:false});
  assert.deepEqual(await store.load(), after);
  await store.save(after);
  assert.equal(await storage.get(recordStateStoreContract.manifest_key), undefined);
  assert.deepEqual(await new ChunkedDurableStateStore(storage, empty).load(), after);
  // Re-enabling must reconcile retained old record rows against the current snapshot.
  const resumed = registered({...after, sessions:{}, session_principals:{}, session_principal_roles:{}});
  await new RecordDurableStateStore(storage, empty).save(resumed);
  assert.deepEqual(await new RecordDurableStateStore(storage, empty).load(), resumed);
});

test("cold persistence requires an atomic storage transaction", async () => {
  const storage = new Storage();
  storage.transaction = undefined;
  await assert.rejects(new RecordDurableStateStore(storage, empty).save(state()), /transaction/);
  assert.equal(storage.puts,0);
});

test("legacy saves issue no delete attempts when nothing needs cleanup", async () => {
  const storage = new Storage();
  const store = new ChunkedDurableStateStore(storage,empty);
  await store.save(state());
  storage.reset();
  await store.save(state());
  assert.equal(storage.puts,0);
  assert.equal(storage.deletes,0);
});

test("re-migration rewrites corrupted retained rows rather than trusting their envelope", async () => {
  const storage = new Storage();
  const before = registered(state(25));
  await new RecordDurableStateStore(storage,empty).save(before);
  await new RecordDurableStateStore(storage,empty,{recordPersistence:false}).save(before);
  const row = [...storage.values].find(([key]) => key.startsWith(recordStateStoreContract.row_prefix))[1];
  row.data[0] ^= 1;
  await new RecordDurableStateStore(storage,empty).save(before);
  assert.deepEqual(await new RecordDurableStateStore(storage,empty).load(),before);
});

test("retried transactions do not advance the committed cache or duplicate events", async () => {
  class RetryingStorage extends Storage {
    async transaction(callback) {
      const before = structuredClone(this.values);
      await callback(this);
      this.values = before;
      return super.transaction(callback);
    }
  }
  const storage = new RetryingStorage();
  const store = new RecordDurableStateStore(storage,empty);
  await store.save(state(25));
  const after = registered(state(25));
  await store.save(after);
  assert.deepEqual(await new RecordDurableStateStore(storage,empty).load(),after);
  assert.deepEqual(await store.load(),after);
});

test("encoded record bounds fail before any storage mutation", async () => {
  const storage = new Storage();
  const store = new RecordDurableStateStore(storage,() => ({}),{max_state_bytes:1024});
  const input = {data:Object.fromEntries(Array.from({length:120},(_,i) => [String(i),0]))};
  assert.ok(new TextEncoder().encode(JSON.stringify(input)).byteLength < 1024);
  await assert.rejects(store.save(input), /encoded record bytes/);
  assert.equal(storage.puts,0);
  assert.equal(storage.deletes,0);
});

test("migration failures preserve the exact legacy checkpoint", async () => {
  const storage = new Storage(), before = state(25);
  await new ChunkedDurableStateStore(storage,empty).save(before);
  const baseline = structuredClone(storage.values);
  storage.reset();
  await new RecordDurableStateStore(storage,empty).save(registered(before));
  const attempts = storage.puts;
  for (let failAt=1; failAt<=attempts; failAt++) {
    storage.values=structuredClone(baseline); storage.reset(failAt);
    await assert.rejects(new RecordDurableStateStore(storage,empty).save(registered(before)),/injected commit failure/);
    assert.deepEqual(await new ChunkedDurableStateStore(storage,empty).load(),before);
    assert.deepEqual(await new RecordDurableStateStore(storage,empty).load(),before);
  }
});
test("rollback failures preserve authoritative records and the old-reader fence", async () => {
  const storage = new Storage(), before = registered(state(25));
  await new RecordDurableStateStore(storage,empty).save(before);
  const baseline = structuredClone(storage.values);
  storage.reset();
  await new RecordDurableStateStore(storage,empty,{recordPersistence:false}).save(before);
  const attempts = storage.puts;
  for (let failAt=1; failAt<=attempts; failAt++) {
    storage.values=structuredClone(baseline); storage.reset(failAt);
    await assert.rejects(new RecordDurableStateStore(storage,empty,{recordPersistence:false}).save(before),/injected commit failure/);
    assert.deepEqual(await new RecordDurableStateStore(storage,empty).load(),before);
    await assert.rejects(new ChunkedDurableStateStore(storage,empty).load(),/manifest is invalid/);
  }
});
test("initial migration of 12000 events writes 194 rows with no deletes", async () => {
  const storage = new Storage();
  await new RecordDurableStateStore(storage,empty).save(state(12000));
  assert.equal(storage.puts,194);
  assert.equal(storage.deletes,0);
  assert.equal((await new RecordDurableStateStore(storage,empty).load()).events.length,12000);
});
