const LEGACY_STATE_KEY = "conduct_state";
const MANIFEST_KEY = "conduct_state.v2.manifest";
const CHUNK_PREFIX = "conduct_state.v2.chunk.";
const CHUNK_BYTES = 96 * 1024;
const MAX_STATE_BYTES = 16 * 1024 * 1024;
const MAX_MULTI_KEY_READ = 128;
const encoder = new TextEncoder();
const decoder = new TextDecoder("utf-8", { fatal: true });

function hex(bytes) {
  return [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function sha256(bytes) {
  return hex(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)));
}

function chunkKey(generation, index) {
  return `${CHUNK_PREFIX}${generation}.${String(index).padStart(4, "0")}`;
}

function bytesFromStoredChunk(value) {
  if (value instanceof Uint8Array) return value;
  if (value instanceof ArrayBuffer) return new Uint8Array(value);
  if (ArrayBuffer.isView(value)) {
    return new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
  }
  throw new Error("stored conduct state chunk has an unsupported value type");
}

function validateManifest(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("stored conduct state chunk manifest is invalid");
  }
  if (value.schema_version !== "limen.conduct_state_chunks.v1"
      || value.encoding !== "json-utf8"
      || !/^[0-9a-f]{64}$/.test(String(value.generation || ""))
      || !Number.isInteger(value.chunk_count)
      || value.chunk_count < 1
      || !Number.isInteger(value.byte_length)
      || value.byte_length < 1
      || value.byte_length > MAX_STATE_BYTES
      || value.chunk_bytes !== CHUNK_BYTES
      || value.chunk_count !== Math.ceil(value.byte_length / CHUNK_BYTES)) {
    throw new Error("stored conduct state chunk manifest is invalid");
  }
  return value;
}

async function readChunks(storage, manifest) {
  const keys = Array.from(
    { length: manifest.chunk_count },
    (_, index) => chunkKey(manifest.generation, index),
  );
  const chunks = [];
  let received = 0;
  for (let offset = 0; offset < keys.length; offset += MAX_MULTI_KEY_READ) {
    const selected = keys.slice(offset, offset + MAX_MULTI_KEY_READ);
    const values = await storage.get(selected);
    for (const key of selected) {
      const value = values instanceof Map ? values.get(key) : await storage.get(key);
      if (value === undefined || value === null) {
        throw new Error(`stored conduct state is missing chunk ${key}`);
      }
      const chunk = bytesFromStoredChunk(value);
      if (chunk.byteLength < 1 || chunk.byteLength > CHUNK_BYTES) {
        throw new Error(`stored conduct state chunk ${key} has an invalid size`);
      }
      chunks.push(chunk);
      received += chunk.byteLength;
    }
  }
  if (received !== manifest.byte_length) {
    throw new Error("stored conduct state byte length does not match its manifest");
  }
  const joined = new Uint8Array(received);
  let cursor = 0;
  for (const chunk of chunks) {
    joined.set(chunk, cursor);
    cursor += chunk.byteLength;
  }
  if (await sha256(joined) !== manifest.generation) {
    throw new Error("stored conduct state content digest does not match its manifest");
  }
  return joined;
}

async function deleteKeys(storage, keys) {
  for (let offset = 0; offset < keys.length; offset += MAX_MULTI_KEY_READ) {
    const selected = keys.slice(offset, offset + MAX_MULTI_KEY_READ);
    if (selected.length) await storage.delete(selected);
  }
}

async function cleanupUnselected(storage, generation) {
  const listed = await storage.list({ prefix: CHUNK_PREFIX });
  if (!(listed instanceof Map)) return;
  const selectedPrefix = `${CHUNK_PREFIX}${generation}.`;
  await deleteKeys(
    storage,
    [...listed.keys()].filter((key) => !key.startsWith(selectedPrefix)),
  );
  await storage.delete(LEGACY_STATE_KEY);
}

/**
 * Content-addressed, manifest-switched persistence for the serialized conduct kernel.
 *
 * Durable Object values have a finite per-value ceiling. The former single
 * `conduct_state` value crossed that ceiling while every receipt was still valid.
 * Chunks stay below both legacy-KV and SQLite-backed limits. The manifest is
 * advanced only after every new chunk is durable, so interrupted writes leave the
 * prior generation readable and completed receipts are never discarded.
 */
export class ChunkedDurableStateStore {
  constructor(storage, emptyState) {
    this.storage = storage;
    this.emptyState = emptyState;
  }

  async load() {
    const rawManifest = await this.storage.get(MANIFEST_KEY);
    if (rawManifest !== undefined && rawManifest !== null) {
      const manifest = validateManifest(rawManifest);
      const bytes = await readChunks(this.storage, manifest);
      try {
        return JSON.parse(decoder.decode(bytes));
      } catch (error) {
        throw new Error(`stored conduct state JSON is invalid: ${error.message}`);
      }
    }
    return (await this.storage.get(LEGACY_STATE_KEY)) || this.emptyState();
  }

  async save(state) {
    const bytes = encoder.encode(JSON.stringify(state));
    if (bytes.byteLength < 1 || bytes.byteLength > MAX_STATE_BYTES) {
      throw new Error(
        `conduct state exceeds bounded chunk store (${bytes.byteLength} > ${MAX_STATE_BYTES} bytes)`,
      );
    }
    const generation = await sha256(bytes);
    const priorRaw = await this.storage.get(MANIFEST_KEY);
    const prior = priorRaw == null ? null : validateManifest(priorRaw);
    const chunkCount = Math.ceil(bytes.byteLength / CHUNK_BYTES);
    if (prior
        && prior.generation === generation
        && prior.byte_length === bytes.byteLength
        && prior.chunk_count === chunkCount) {
      try {
        await cleanupUnselected(this.storage, generation);
      } catch {
        // The selected generation is already durable. Orphan cleanup remains
        // best-effort and is retried by the next save.
      }
      return;
    }

    for (let index = 0; index < chunkCount; index += 1) {
      const start = index * CHUNK_BYTES;
      const chunk = bytes.slice(start, Math.min(start + CHUNK_BYTES, bytes.byteLength));
      await this.storage.put(chunkKey(generation, index), chunk);
    }
    const manifest = {
      schema_version: "limen.conduct_state_chunks.v1",
      encoding: "json-utf8",
      generation,
      byte_length: bytes.byteLength,
      chunk_bytes: CHUNK_BYTES,
      chunk_count: chunkCount,
    };
    await this.storage.put(MANIFEST_KEY, manifest);

    // Cleanup follows the atomic manifest switch. A cleanup interruption can
    // leave only unreachable bytes; it cannot make the selected generation
    // unreadable. The next save retries removal of every unselected generation.
    try {
      await cleanupUnselected(this.storage, generation);
    } catch {
      // Receipt custody is already committed through the manifest. Cleanup is
      // deliberately best-effort and never rewrites the selected generation.
    }
  }
}

export const durableStateStoreContract = Object.freeze({
  schema_version: "limen.conduct_state_store_contract.v1",
  manifest_key: MANIFEST_KEY,
  legacy_key: LEGACY_STATE_KEY,
  chunk_prefix: CHUNK_PREFIX,
  chunk_bytes: CHUNK_BYTES,
  max_state_bytes: MAX_STATE_BYTES,
});
