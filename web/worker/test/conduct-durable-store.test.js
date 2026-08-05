import assert from "node:assert/strict";
import test from "node:test";

import {
  ChunkedDurableStateStore,
  durableStateStoreContract,
} from "../src/conduct/durable-store.js";

const encoder = new TextEncoder();

function storedBytes(value) {
  if (value instanceof Uint8Array) return value.byteLength;
  if (value instanceof ArrayBuffer) return value.byteLength;
  if (ArrayBuffer.isView(value)) return value.byteLength;
  return encoder.encode(JSON.stringify(value)).byteLength;
}

class LimitedStorage {
  constructor({ limit = 128 * 1024 } = {}) {
    this.limit = limit;
    this.values = new Map();
    this.putCount = 0;
  }

  seed(key, value) {
    this.values.set(key, structuredClone(value));
  }

  async get(key) {
    if (Array.isArray(key)) {
      return new Map(
        key
          .filter((candidate) => this.values.has(candidate))
          .map((candidate) => [candidate, structuredClone(this.values.get(candidate))]),
      );
    }
    return this.values.has(key) ? structuredClone(this.values.get(key)) : undefined;
  }

  async put(key, value) {
    if (storedBytes(value) > this.limit) throw new Error("SQLITE_TOOBIG");
    this.values.set(key, structuredClone(value));
    this.putCount += 1;
  }

  async delete(key) {
    if (Array.isArray(key)) {
      let removed = 0;
      for (const candidate of key) removed += Number(this.values.delete(candidate));
      return removed;
    }
    return this.values.delete(key);
  }

  async list({ prefix } = {}) {
    return new Map(
      [...this.values]
        .filter(([key]) => !prefix || key.startsWith(prefix))
        .map(([key, value]) => [key, structuredClone(value)]),
    );
  }
}

function oversizedState(marker = "first") {
  const state = {
    schema_version: "limen.conduct_state.v1",
    sessions: {},
    session_principals: {},
    runs: {},
    leases: {},
    work_index: {},
    work_key_index: {},
    receipt_index: {},
    resource_generations: {},
    next_generation: 0,
    events: [],
  };
  state.events = Array.from({ length: 2_400 }, (_, index) => ({
    sequence: index + 1,
    timestamp: "2026-07-26T20:00:00.000Z",
    kind: "test.event",
    marker,
    detail: `${index}:${"receipt-custody-".repeat(6)}`,
  }));
  return state;
}

test("chunked durable store migrates a legacy value that cannot be rewritten whole", async () => {
  const storage = new LimitedStorage();
  const state = oversizedState();
  assert.ok(storedBytes(state) > storage.limit);
  storage.seed(durableStateStoreContract.legacy_key, state);
  const store = new ChunkedDurableStateStore(storage, () => oversizedState("empty"));

  assert.deepEqual(await store.load(), state);
  await store.save(state);

  assert.equal(storage.values.has(durableStateStoreContract.legacy_key), false);
  const manifest = storage.values.get(durableStateStoreContract.manifest_key);
  assert.equal(manifest.schema_version, "limen.conduct_state_chunks.v1");
  assert.ok(manifest.chunk_count > 1);
  for (const [key, value] of storage.values) {
    if (key.startsWith(durableStateStoreContract.chunk_prefix)) {
      assert.ok(storedBytes(value) <= durableStateStoreContract.chunk_bytes);
      assert.ok(storedBytes(value) < storage.limit);
    }
  }
  assert.deepEqual(await store.load(), state);
});

test("chunked durable store is content-addressed and ignores unselected chunks", async () => {
  const storage = new LimitedStorage();
  const store = new ChunkedDurableStateStore(storage, () => oversizedState("empty"));
  const state = oversizedState();
  await store.save(state);
  const writes = storage.putCount;

  await store.save(state);
  assert.equal(storage.putCount, writes);

  const orphan = `${durableStateStoreContract.chunk_prefix}${"0".repeat(64)}.0000`;
  storage.seed(orphan, new Uint8Array([1]));
  assert.deepEqual(await store.load(), state);
  await store.save(state);
  assert.equal(storage.values.has(orphan), false);
});

test("chunked durable store fails closed when the selected generation is incomplete", async () => {
  const storage = new LimitedStorage();
  const store = new ChunkedDurableStateStore(storage, () => oversizedState("empty"));
  await store.save(oversizedState());
  const manifest = storage.values.get(durableStateStoreContract.manifest_key);
  const missing = `${durableStateStoreContract.chunk_prefix}${manifest.generation}.0000`;
  storage.values.delete(missing);

  await assert.rejects(store.load(), /missing chunk/);
});

test("chunked durable store removes the prior selected generation after a manifest switch", async () => {
  const storage = new LimitedStorage();
  const store = new ChunkedDurableStateStore(storage, () => oversizedState("empty"));
  await store.save(oversizedState("first"));
  const first = storage.values.get(durableStateStoreContract.manifest_key);
  await store.save(oversizedState("second"));
  const second = storage.values.get(durableStateStoreContract.manifest_key);

  assert.notEqual(first.generation, second.generation);
  assert.equal(
    [...storage.values.keys()].some((key) =>
      key.startsWith(`${durableStateStoreContract.chunk_prefix}${first.generation}.`)),
    false,
  );
  assert.deepEqual(await store.load(), oversizedState("second"));
});
