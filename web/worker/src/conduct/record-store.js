import { ChunkedDurableStateStore } from "./durable-store.js";

const MANIFEST_KEY = "conduct_state.v3.manifest";
const ROW_PREFIX = "conduct_state.v3.row.";
const LEGACY_CHECKPOINT_KEY = "conduct_state.v3.legacy_checkpoint";
const LEGACY_FENCE_SCHEMA = "limen.conduct_state_requires_record_store.v1";
const SCHEMA = "limen.conduct_records.v1";
const encoder = new TextEncoder();
const decoder = new TextDecoder("utf-8", { fatal: true });

function canonical(value) {
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  if (value !== null && typeof value === "object") {
    return "{" + Object.keys(value).sort().map(key =>
      JSON.stringify(key) + ":" + canonical(value[key])).join(",") + "}";
  }
  return JSON.stringify(value);
}

async function digest(bytes) {
  return [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))]
    .map(byte => byte.toString(16).padStart(2, "0")).join("");
}

function assign(object, key, value) {
  Object.defineProperty(object, key, { value, enumerable: true, writable: true, configurable: true });
}

function records(state) {
  const fields = [];
  const entries = [];
  for (const name of Object.keys(state).sort()) {
    const value = state[name];
    if (name === "events") {
      if (!Array.isArray(value)) throw new Error("conduct record events must be an array");
      fields.push({ name, kind: "events" });
      let last = 0;
      const pages = new Map();
      for (const event of value) {
        if (!Number.isSafeInteger(event?.sequence) || event.sequence <= last) {
          throw new Error("conduct record events require unique increasing sequences");
        }
        last = event.sequence;
        const page = String(Math.floor((event.sequence - 1) / 64));
        const selected = pages.get(page) || [];
        selected.push(event);
        pages.set(page,selected);
      }
      for (const [page,events] of pages) entries.push({ path: ["events",page], value:events });
    } else if (value !== null && typeof value === "object" && !Array.isArray(value)) {
      fields.push({ name, kind: "map" });
      for (const key of Object.keys(value).sort()) entries.push({ path: ["entry", name, key], value: value[key] });
    } else {
      fields.push({ name, kind: "value" });
      entries.push({ path: ["value", name], value });
    }
  }
  return { fields, entries };
}

async function encodeRows(entries, chunkBytes, previous) {
  const rows = new Map();
  const cache = new Map();
  for (const entry of entries) {
    const pathKey = JSON.stringify(entry.path);
    const prior = previous.get(pathKey);
    if (prior && canonical(prior.value) === canonical(entry.value)) {
      for (const [key,row] of prior.rows) rows.set(key,row);
      cache.set(pathKey, {value:entry.value,rows:prior.rows});
      continue;
    }
    const selected = new Map();
    const bytes = encoder.encode(canonical(entry));
    const id = await digest(encoder.encode(JSON.stringify(entry.path)));
    const hash = await digest(bytes);
    const count = Math.ceil(bytes.byteLength / chunkBytes);
    for (let index = 0; index < count; index++) {
      selected.set(ROW_PREFIX + id + "." + String(index).padStart(4, "0"), {
        digest: hash, index, count,
        data: bytes.slice(index * chunkBytes, Math.min((index + 1) * chunkBytes, bytes.byteLength)),
      });
    }
    for (const [key,row] of selected) rows.set(key,row);
    cache.set(pathKey, {value:entry.value,rows:selected});
  }
  return {rows,cache};
}

/**
 * Conduct-only differential persistence. The Durable Object is the exclusive
 * serialized writer. One manifest and its changed record rows commit in one
 * storage transaction; unchanged lifecycle history is never rewritten or pruned.
 *
 * A cached committed base avoids scanning every historical row on every call.
 * Heartbeat overlays are still read and validated by the parent store. Failed
 * transactions never advance this cache. A recreated object verifies every row
 * and the whole-state digest before accepting the selected generation.
 */
export class RecordDurableStateStore extends ChunkedDurableStateStore {
  constructor(storage, emptyState, { recordPersistence = true, ...options } = {}) {
    super(storage, emptyState, options);
    this.recordPersistence = recordPersistence;
    this.recordRows = null;
    this.recordCache = new Map();
    this.cachedBase = null;
  }

  async loadBase() {
    if (this.cachedBase) return structuredClone(this.cachedBase);
    const manifest = await this.storage.get(MANIFEST_KEY);
    const rows = await this.storage.list({ prefix: ROW_PREFIX });
    if (!(rows instanceof Map)) throw new Error("conduct record listing is invalid");
    if (manifest == null) {
      const base = await super.loadBase();
      // Retained rows after rollback are unselected, but must be reconciled
      // during the next migration so they cannot reappear as selected state.
      this.recordRows = rows;
      this.cachedBase = structuredClone(base);
      return base;
    }
    if (manifest.schema_version !== SCHEMA
        || !/^[0-9a-f]{64}$/.test(manifest.generation)
        || !Number.isSafeInteger(manifest.row_count) || manifest.row_count < 1
        || manifest.row_count !== rows.size
        || !Number.isSafeInteger(manifest.byte_length) || manifest.byte_length < 1
        || manifest.byte_length > this.contract.max_state_bytes
        || !Array.isArray(manifest.fields)) {
      throw new Error("conduct record manifest or row count is invalid");
    }
    const state = {};
    const layout = new Map();
    for (const field of manifest.fields) {
      if (typeof field?.name !== "string" || layout.has(field.name)
          || !["map", "events", "value"].includes(field.kind)
          || (field.kind === "events" && field.name !== "events")) {
        throw new Error("conduct record field layout is invalid");
      }
      layout.set(field.name, field.kind);
      if (field.kind !== "value") assign(state, field.name, field.kind === "map" ? {} : []);
    }
    const groups = new Map();
    let total = 0;
    for (const [key, row] of rows) {
      const match = key.slice(ROW_PREFIX.length).match(/^([0-9a-f]{64})\.([0-9]{4})$/);
      if (!match || !row || !/^[0-9a-f]{64}$/.test(row.digest)
          || !Number.isSafeInteger(row.count) || row.count < 1
          || !Number.isSafeInteger(row.index) || row.index < 0 || row.index >= row.count
          || String(row.index).padStart(4, "0") !== match[2]
          || !(row.data instanceof Uint8Array)
          || row.data.byteLength < 1 || row.data.byteLength > this.contract.chunk_bytes) {
        throw new Error("conduct record chunk is invalid");
      }
      total += row.data.byteLength;
      if (total > this.contract.max_state_bytes * 4) throw new Error("conduct record bytes exceed bound");
      const group = groups.get(match[1]) || [];
      group.push(row);
      groups.set(match[1], group);
    }
    const seenPaths = new Set();
    const cache = new Map();
    for (const [id, group] of groups) {
      group.sort((a,b) => a.index - b.index);
      const first = group[0];
      if (group.length !== first.count || group.some((row,index) =>
        row.index !== index || row.count !== first.count || row.digest !== first.digest)) {
        throw new Error("conduct record chunks are incomplete");
      }
      const bytes = new Uint8Array(group.reduce((size,row) => size + row.data.byteLength, 0));
      let cursor = 0;
      for (const row of group) { bytes.set(row.data, cursor); cursor += row.data.byteLength; }
      if (await digest(bytes) !== first.digest) throw new Error("conduct record digest mismatch");
      const entry = JSON.parse(decoder.decode(bytes));
      const path = entry.path;
      const pathKey = JSON.stringify(path);
      if (!Array.isArray(path) || path.some(part => typeof part !== "string")
          || await digest(encoder.encode(pathKey)) !== id || seenPaths.has(pathKey)) {
        throw new Error("conduct record path is invalid");
      }
      seenPaths.add(pathKey);
      cache.set(pathKey,{value:entry.value,rows:new Map(group.map(row =>
        [ROW_PREFIX + id + "." + String(row.index).padStart(4,"0"),row]))});
      if (path[0] === "entry" && path.length === 3 && layout.get(path[1]) === "map") {
        assign(state[path[1]], path[2], entry.value);
      } else if (path[0] === "value" && path.length === 2 && layout.get(path[1]) === "value") {
        assign(state, path[1], entry.value);
      } else if (path[0] === "events" && path.length === 2 && layout.get("events") === "events"
          && Array.isArray(entry.value) && entry.value.length > 0 && entry.value.length <= 64
          && entry.value.every((event,index) => Number.isSafeInteger(event?.sequence)
            && event.sequence > (index ? entry.value[index-1].sequence : 0)
            && String(Math.floor((event.sequence - 1) / 64)) === path[1])) {
        state.events.push(...entry.value);
      } else {
        throw new Error("conduct record path does not match field layout");
      }
    }
    if (state.events) state.events.sort((a,b) => a.sequence - b.sequence);
    const bytes = encoder.encode(canonical(state));
    if (bytes.byteLength !== manifest.byte_length || await digest(bytes) !== manifest.generation) {
      throw new Error("conduct record state digest mismatch");
    }
    this.recordRows = rows;
    this.recordCache = cache;
    this.cachedBase = { state, generation: manifest.generation };
    return structuredClone(this.cachedBase);
  }

  async save(input) {
    if (typeof this.storage.transaction !== "function") {
      throw new Error("conduct record persistence requires an atomic storage transaction");
    }
    const state = JSON.parse(JSON.stringify(input));
    const bytes = encoder.encode(canonical(state));
    if (!bytes.byteLength || bytes.byteLength > this.contract.max_state_bytes) {
      throw new Error("conduct record state exceeds bounded store");
    }
    if (!this.recordPersistence) {
      // Explicit rollback mode: reads remain pure. A successful mutating request
      // materializes current authoritative state before restoring an older binary.
      await this.storage.transaction(async transaction => {
        const selector = await transaction.get(this.contract.manifest_key);
        if (selector?.schema_version === LEGACY_FENCE_SCHEMA) await transaction.delete(this.contract.manifest_key);
        await new ChunkedDurableStateStore(transaction, this.emptyState).save(state);
        if (await transaction.get(MANIFEST_KEY) != null) await transaction.delete(MANIFEST_KEY);
      });
      this.cachedBase = null;
      this.recordRows = null;
      this.recordCache = new Map();
      this.loadedGeneration = null;
      this.loadedOverlays = new Map();
      return;
    }
    if (this.recordRows === null) await this.loadBase();
    const generation = await digest(bytes);
    const migrating = await this.storage.get(MANIFEST_KEY) == null;
    if (!migrating && !this.loadedOverlays.size && this.cachedBase?.generation === generation) return;
    const { fields, entries } = records(state);
    const {rows:nextRows,cache} = await encodeRows(entries, this.contract.chunk_bytes, this.recordCache);
    const encodedBytes = [...nextRows.values()].reduce((sum,row) => sum + row.data.byteLength,0);
    if (!nextRows.size || encodedBytes > this.contract.max_state_bytes * 4) {
      throw new Error("conduct encoded record bytes exceed bound");
    }
    const changed = [...nextRows].filter(([key,row]) => {
      const prior = this.recordRows.get(key);
      return migrating || prior?.digest !== row.digest || prior?.count !== row.count || prior?.index !== row.index;
    });
    const removed = [...this.recordRows.keys()].filter(key => !nextRows.has(key));
    const selectedOverlays = [...this.loadedOverlays.keys()];
    if (!changed.length && !removed.length && !selectedOverlays.length
        && !migrating && this.cachedBase?.generation === generation) return;
    const manifest = { schema_version: SCHEMA, generation, byte_length: bytes.byteLength,
      row_count: nextRows.size, fields };
    await this.storage.transaction(async transaction => {
      if (migrating) {
        const oldManifest = await transaction.get(this.contract.manifest_key);
        await transaction.put(LEGACY_CHECKPOINT_KEY, {manifest:oldManifest ?? null});
        await transaction.put(this.contract.manifest_key, {schema_version:LEGACY_FENCE_SCHEMA});
      }
      for (const [key,row] of changed) await transaction.put(key,row);
      for (const key of removed) await transaction.delete(key);
      for (const leaseId of selectedOverlays) {
        const key = "conduct_liveness.v1." + await digest(encoder.encode(leaseId));
        await transaction.delete(key);
      }
      await transaction.put(MANIFEST_KEY,manifest);
    });
    this.recordRows = nextRows;
    this.recordCache = cache;
    this.cachedBase = { state, generation };
    this.loadedGeneration = generation;
    this.loadedOverlays = new Map();
  }
}

export const recordStateStoreContract = Object.freeze({
  schema_version: "limen.conduct_record_store_contract.v1",
  manifest_key: MANIFEST_KEY,
  row_prefix: ROW_PREFIX,
  legacy_checkpoint_key: LEGACY_CHECKPOINT_KEY,
  simple_registration_rows_written: 6,
  events_per_record: 64,
  registration_conditions: "after migration, without supersession, expiry or pending liveness overlays",
  registration_rows_deleted: 0,
  mutation_cost: "changed record chunks plus one manifest",
  rollback_flag: "LIMEN_CONDUCT_STEADY_HEARTBEAT_OVERLAY",
});
