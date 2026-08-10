import assert from "node:assert/strict";
import test from "node:test";

import {
  ChunkedDurableStateStore,
  durableStateStoreContract,
} from "../src/conduct/durable-store.js";

const encoder = new TextEncoder();
const DEPLOYED_V1_MANIFEST_KEY = "conduct_state.v2.manifest";
const DEPLOYED_V1_CHUNK_PREFIX = "conduct_state.v2.chunk.";
const DEPLOYED_V1_CHUNK_BYTES = 96 * 1024;

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
    this.readKeys = [];
  }

  seed(key, value) {
    this.values.set(key, structuredClone(value));
  }

  async get(key) {
    if (Array.isArray(key)) {
      this.readKeys.push(...key);
      return new Map(
        key
          .filter((candidate) => this.values.has(candidate))
          .map((candidate) => [candidate, structuredClone(this.values.get(candidate))]),
      );
    }
    this.readKeys.push(key);
    return this.values.has(key) ? structuredClone(this.values.get(key)) : undefined;
  }

  async put(key, value) {
    const entries = typeof key === "string"
      ? [[key, value]]
      : key instanceof Map
        ? [...key]
        : Object.entries(key);
    for (const [candidate, stored] of entries) {
      if (storedBytes(stored) > this.limit) throw new Error("SQLITE_TOOBIG");
      this.values.set(candidate, structuredClone(stored));
    }
    this.putCount += entries.length;
  }

  async delete(key) {
    const candidates = Array.isArray(key) ? key : [key];
    let removed = 0;
    for (const candidate of candidates) removed += Number(this.values.delete(candidate));
    return Array.isArray(key) ? removed : Boolean(removed);
  }

  async list({ prefix } = {}) {
    return new Map(
      [...this.values]
        .filter(([key]) => !prefix || key.startsWith(prefix))
        .map(([key, value]) => [key, structuredClone(value)]),
    );
  }

  resetReadTrace() {
    this.readKeys = [];
  }

}

function hex(bytes) {
  return [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function digest(bytes) {
  return hex(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)));
}

function deployedV1ChunkKey(generation, index) {
  return `${DEPLOYED_V1_CHUNK_PREFIX}${generation}.${String(index).padStart(4, "0")}`;
}

async function seedDeployedV1State(storage, state) {
  const bytes = encoder.encode(JSON.stringify(state));
  const generation = await digest(bytes);
  const chunkCount = Math.ceil(bytes.byteLength / DEPLOYED_V1_CHUNK_BYTES);
  for (let index = 0; index < chunkCount; index += 1) {
    const start = index * DEPLOYED_V1_CHUNK_BYTES;
    storage.seed(
      deployedV1ChunkKey(generation, index),
      bytes.slice(start, Math.min(start + DEPLOYED_V1_CHUNK_BYTES, bytes.byteLength)),
    );
  }
  const manifest = {
    schema_version: "limen.conduct_state_chunks.v1",
    encoding: "json-utf8",
    generation,
    byte_length: bytes.byteLength,
    chunk_bytes: DEPLOYED_V1_CHUNK_BYTES,
    chunk_count: chunkCount,
  };
  storage.seed(DEPLOYED_V1_MANIFEST_KEY, manifest);
  return manifest;
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

async function selectedReadKeys(store, storage) {
  storage.resetReadTrace();
  await store.load();
  return new Set(storage.readKeys.filter((key) => storage.values.has(key)));
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
  assert.ok(storage.values.size > 2);
  for (const value of storage.values.values()) {
    assert.ok(storedBytes(value) <= storage.limit);
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
  const selected = await selectedReadKeys(store, storage);
  const missing = [...selected].find((key) =>
    key !== durableStateStoreContract.manifest_key
    && key !== durableStateStoreContract.legacy_key);
  assert.ok(missing, "the selected state must reference at least one durable data row");
  storage.values.delete(missing);
  storage.seed(durableStateStoreContract.legacy_key, oversizedState("stale-fallback"));

  await assert.rejects(store.load());
});

test("chunked durable store removes the prior selected generation after a manifest switch", async () => {
  const storage = new LimitedStorage();
  const store = new ChunkedDurableStateStore(storage, () => oversizedState("empty"));
  await store.save(oversizedState("first"));
  const firstSelected = await selectedReadKeys(store, storage);
  await store.save(oversizedState("second"));
  const secondState = await store.load();
  const secondSelected = await selectedReadKeys(store, storage);

  for (const key of firstSelected) {
    if (!secondSelected.has(key)) assert.equal(storage.values.has(key), false);
  }
  assert.deepEqual(secondState, oversizedState("second"));
});

test("deployed v1 chunk manifests load and remain writable through the current cold path", async () => {
  const storage = new LimitedStorage();
  const before = oversizedState("deployed-v1");
  const deployedManifest = await seedDeployedV1State(storage, before);
  const store = new ChunkedDurableStateStore(storage, () => oversizedState("empty"));

  assert.equal(deployedManifest.schema_version, "limen.conduct_state_chunks.v1");
  assert.deepEqual(await store.load(), before);
  const after = oversizedState("migrated-v2");
  await store.save(after);

  const selectedManifest = storage.values.get(durableStateStoreContract.manifest_key);
  assert.equal(
    selectedManifest.schema_version,
    deployedManifest.schema_version,
    "a changed deployed generation must remain readable by the current cold store",
  );
  assert.deepEqual(await store.load(), after);
});
