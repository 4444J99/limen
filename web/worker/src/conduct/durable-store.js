const LEGACY_STATE_KEY = "conduct_state";
const MANIFEST_KEY = "conduct_state.v2.manifest";
const CHUNK_PREFIX = "conduct_state.v2.chunk.";
const LIVENESS_PREFIX = "conduct_liveness.v1.";
const LIVENESS_SCHEMA = "limen.conduct_liveness.v1";
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

function chunkKey(contract, generation, index) {
  return `${contract.chunk_prefix}${generation}.${String(index).padStart(4, "0")}`;
}

async function livenessKey(leaseId) {
  return `${LIVENESS_PREFIX}${await sha256(encoder.encode(leaseId))}`;
}

function bytesFromStoredChunk(value) {
  if (value instanceof Uint8Array) return value;
  if (value instanceof ArrayBuffer) return new Uint8Array(value);
  if (ArrayBuffer.isView(value)) {
    return new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
  }
  throw new Error("stored conduct state chunk has an unsupported value type");
}

function validateManifest(value, contract) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("stored conduct state chunk manifest is invalid");
  }
  if (value.schema_version !== contract.schema_version
      || value.encoding !== "json-utf8"
      || !/^[0-9a-f]{64}$/.test(String(value.generation || ""))
      || !Number.isInteger(value.chunk_count)
      || value.chunk_count < 1
      || !Number.isInteger(value.byte_length)
      || value.byte_length < 1
      || value.byte_length > contract.max_state_bytes
      || value.chunk_bytes !== contract.chunk_bytes
      || value.chunk_count !== Math.ceil(value.byte_length / contract.chunk_bytes)) {
    throw new Error("stored conduct state chunk manifest is invalid");
  }
  return value;
}

function validTimestamp(value) {
  return typeof value === "string" && value.length <= 64 && !Number.isNaN(Date.parse(value));
}

function validateLiveness(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)
      || value.schema_version !== LIVENESS_SCHEMA
      || !/^[0-9a-f]{64}$/.test(String(value.base_generation || ""))
      || typeof value.lease_id !== "string" || !value.lease_id || value.lease_id.length > 256
      || !Number.isSafeInteger(value.lease_generation) || value.lease_generation < 1
      || typeof value.run_id !== "string" || !value.run_id || value.run_id.length > 256
      || typeof value.session_id !== "string" || !value.session_id || value.session_id.length > 256
      || !value.lease || typeof value.lease !== "object" || Array.isArray(value.lease)
      || value.lease.state !== "active"
      || !validTimestamp(value.lease.heartbeat_at)
      || !validTimestamp(value.lease.hard_deadline)
      || !value.run || typeof value.run !== "object" || Array.isArray(value.run)
      || value.run.status !== "running"
      || !validTimestamp(value.run.updated_at)
      || !value.session || typeof value.session !== "object" || Array.isArray(value.session)
      || !validTimestamp(value.session.heartbeat_at)
      || !value.audit || typeof value.audit !== "object" || Array.isArray(value.audit)
      || value.audit.kind !== "lease.heartbeat"
      || !Number.isSafeInteger(value.audit.count) || value.audit.count < 1
      || !validTimestamp(value.audit.first_timestamp)
      || !validTimestamp(value.audit.last_timestamp)
      || !/^[0-9a-f]{64}$/.test(String(value.audit.chain_sha256 || ""))) {
    throw new Error("stored conduct liveness overlay is invalid");
  }
  if (value.lease.heartbeat_at !== value.run.updated_at
      || value.lease.heartbeat_at !== value.session.heartbeat_at
      || value.lease.heartbeat_at !== value.audit.last_timestamp
      || Date.parse(value.audit.first_timestamp) > Date.parse(value.audit.last_timestamp)
      || Date.parse(value.lease.hard_deadline) < Date.parse(value.lease.heartbeat_at)) {
    throw new Error("stored conduct liveness overlay is inconsistent");
  }
  return value;
}

async function readChunks(storage, manifest, contract) {
  const keys = Array.from(
    { length: manifest.chunk_count },
    (_, index) => chunkKey(contract, manifest.generation, index),
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
      if (chunk.byteLength < 1 || chunk.byteLength > contract.chunk_bytes) {
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

async function cleanupUnselected(storage, generation, contract) {
  const listed = await storage.list({ prefix: contract.chunk_prefix });
  if (!(listed instanceof Map)) return;
  const selectedPrefix = `${contract.chunk_prefix}${generation}.`;
  await deleteKeys(
    storage,
    [...listed.keys()].filter((key) => !key.startsWith(selectedPrefix)),
  );
  await storage.delete(contract.legacy_key);
}

async function cleanupLiveness(storage) {
  const listed = await storage.list({ prefix: LIVENESS_PREFIX });
  if (listed instanceof Map) await deleteKeys(storage, [...listed.keys()]);
}

function eventMultiplicity(event) {
  return Number.isSafeInteger(event?.count) && event.count > 0 ? event.count : 1;
}

function mergeHeartbeatAudit(state, overlay) {
  state.events = Array.isArray(state.events) ? state.events : [];
  let count = overlay.audit.count;
  let first = overlay.audit.first_timestamp;
  let last = overlay.audit.last_timestamp;
  let highestSequence = Number.isSafeInteger(state.next_event_sequence)
    && state.next_event_sequence >= 0 ? state.next_event_sequence : 0;
  const retained = [];
  for (let index = 0; index < state.events.length; index += 1) {
    const event = state.events[index];
    const sequence = Number.isSafeInteger(event?.sequence) && event.sequence > 0
      ? event.sequence
      : index + 1;
    highestSequence = Math.max(highestSequence, sequence);
    if (event?.kind === "lease.heartbeat" && event.lease_id === overlay.lease_id) {
      count += eventMultiplicity(event);
      const eventFirst = String(event.first_timestamp || event.timestamp || first);
      const eventLast = String(event.last_timestamp || event.timestamp || last);
      if (eventFirst < first) first = eventFirst;
      if (eventLast > last) last = eventLast;
      continue;
    }
    retained.push(event);
  }
  const sequence = highestSequence + 1;
  retained.push({
    sequence,
    timestamp: overlay.audit.last_timestamp,
    kind: "lease.heartbeat",
    lease_id: overlay.lease_id,
    run_id: overlay.run_id,
    count,
    first_timestamp: first,
    last_timestamp: last,
    audit_chain_sha256: overlay.audit.chain_sha256,
  });
  state.events = retained;
  state.next_event_sequence = Math.max(
    Number.isSafeInteger(state.next_event_sequence) ? state.next_event_sequence : 0,
    sequence,
  );
}

function applyLiveness(state, overlay) {
  const lease = state.leases?.[overlay.lease_id];
  const run = state.runs?.[overlay.run_id];
  const session = state.sessions?.[overlay.session_id];
  if (!lease || lease.generation !== overlay.lease_generation
      || lease.run_id !== overlay.run_id
      || lease.state !== "active"
      || !run || run.run_id !== overlay.run_id
      || run.status !== "running"
      || run.executor_session_id !== overlay.session_id
      || !session || session.session_id !== overlay.session_id
      || Date.parse(overlay.lease.hard_deadline) > Date.parse(run.packet.deadline)) {
    throw new Error("stored conduct liveness overlay does not match its base checkpoint");
  }
  lease.heartbeat_at = overlay.lease.heartbeat_at;
  lease.hard_deadline = overlay.lease.hard_deadline;
  lease.state = overlay.lease.state;
  run.status = overlay.run.status;
  run.updated_at = overlay.run.updated_at;
  session.heartbeat_at = overlay.session.heartbeat_at;
  mergeHeartbeatAudit(state, overlay);
}

/**
 * Manifest-switched cold snapshots plus a one-row steady-heartbeat overlay.
 *
 * Cold lifecycle mutations retain the existing chunked crash-safety contract. A
 * steady heartbeat changes only lease/run/session liveness and its coalesced audit
 * summary, so it is written atomically to one fixed per-lease row. Loading overlays
 * matching the selected cold generation reconstructs the authoritative state. The
 * next cold save folds them into a new generation; stale overlays are ignored before
 * best-effort cleanup, making a failed cleanup safe.
 */
export class ChunkedDurableStateStore {
  constructor(storage, emptyState, options = {}) {
    this.storage = storage;
    this.emptyState = emptyState;
    this.contract = Object.freeze({
      schema_version: options.schema_version || "limen.conduct_state_chunks.v1",
      manifest_key: options.manifest_key || MANIFEST_KEY,
      legacy_key: options.legacy_key || LEGACY_STATE_KEY,
      chunk_prefix: options.chunk_prefix || CHUNK_PREFIX,
      chunk_bytes: options.chunk_bytes || CHUNK_BYTES,
      max_state_bytes: options.max_state_bytes || MAX_STATE_BYTES,
    });
    this.livenessEnabled = options.liveness_enabled !== false;
    this.loadedGeneration = null;
    this.loadedOverlays = new Map();
  }

  async loadBase() {
    const rawManifest = await this.storage.get(this.contract.manifest_key);
    if (rawManifest !== undefined && rawManifest !== null) {
      const manifest = validateManifest(rawManifest, this.contract);
      const bytes = await readChunks(this.storage, manifest, this.contract);
      try {
        return {
          state: JSON.parse(decoder.decode(bytes)),
          generation: manifest.generation,
        };
      } catch (error) {
        throw new Error(`stored conduct state JSON is invalid: ${error.message}`);
      }
    }
    const stored = await this.storage.get(this.contract.legacy_key);
    const state = stored || this.emptyState();
    return {
      state,
      generation: await sha256(encoder.encode(JSON.stringify(state))),
    };
  }

  async load() {
    const base = await this.loadBase();
    const listed = this.livenessEnabled
      ? await this.storage.list({ prefix: LIVENESS_PREFIX })
      : new Map();
    const selected = [];
    if (listed instanceof Map) {
      for (const [key, raw] of listed) {
        const overlay = validateLiveness(raw);
        if (key !== await livenessKey(overlay.lease_id)) {
          throw new Error("stored conduct liveness overlay key is invalid");
        }
        if (overlay.base_generation === base.generation) selected.push(overlay);
      }
    }
    selected.sort((left, right) =>
      left.audit.last_timestamp.localeCompare(right.audit.last_timestamp)
      || left.lease_id.localeCompare(right.lease_id));
    for (const overlay of selected) applyLiveness(base.state, overlay);
    this.loadedGeneration = base.generation;
    this.loadedOverlays = new Map(selected.map((overlay) => [overlay.lease_id, overlay]));
    return base.state;
  }

  hasLivenessOverlays() {
    return this.loadedOverlays.size > 0;
  }

  async saveHeartbeat(state, leaseId) {
    if (!this.livenessEnabled || !this.loadedGeneration) {
      throw new Error("conduct liveness save requires a loaded base checkpoint");
    }
    const lease = state.leases?.[leaseId];
    const run = lease ? state.runs?.[lease.run_id] : null;
    const session = run ? state.sessions?.[run.executor_session_id] : null;
    if (!lease || lease.state !== "active" || !run || run.status !== "running" || !session) {
      throw new Error("conduct liveness save requires one active lease/run/session");
    }
    const prior = this.loadedOverlays.get(leaseId);
    const firstTimestamp = prior?.audit.first_timestamp || lease.heartbeat_at;
    const priorChain = prior?.audit.chain_sha256 || "0".repeat(64);
    const chainInput = [
      priorChain,
      leaseId,
      String(lease.generation),
      lease.heartbeat_at,
      lease.hard_deadline,
      run.run_id,
      session.session_id,
    ].join("\0");
    const overlay = {
      schema_version: LIVENESS_SCHEMA,
      base_generation: this.loadedGeneration,
      lease_id: leaseId,
      lease_generation: lease.generation,
      run_id: run.run_id,
      session_id: session.session_id,
      lease: {
        state: "active",
        heartbeat_at: lease.heartbeat_at,
        hard_deadline: lease.hard_deadline,
      },
      run: {
        status: "running",
        updated_at: run.updated_at,
      },
      session: {
        heartbeat_at: session.heartbeat_at,
      },
      audit: {
        kind: "lease.heartbeat",
        count: (prior?.audit.count || 0) + 1,
        first_timestamp: firstTimestamp,
        last_timestamp: lease.heartbeat_at,
        chain_sha256: await sha256(encoder.encode(chainInput)),
      },
    };
    await this.storage.put(await livenessKey(leaseId), overlay);
    this.loadedOverlays.set(leaseId, overlay);
    return overlay;
  }

  async save(state) {
    const bytes = encoder.encode(JSON.stringify(state));
    if (bytes.byteLength < 1 || bytes.byteLength > this.contract.max_state_bytes) {
      throw new Error(
        `durable state exceeds bounded chunk store (${bytes.byteLength} > ${this.contract.max_state_bytes} bytes)`,
      );
    }
    const generation = await sha256(bytes);
    const priorRaw = await this.storage.get(this.contract.manifest_key);
    const prior = priorRaw == null ? null : validateManifest(priorRaw, this.contract);
    const chunkCount = Math.ceil(bytes.byteLength / this.contract.chunk_bytes);
    if (prior
        && prior.generation === generation
        && prior.byte_length === bytes.byteLength
        && prior.chunk_count === chunkCount) {
      try {
        await cleanupUnselected(this.storage, generation, this.contract);
        if (this.livenessEnabled) await cleanupLiveness(this.storage);
      } catch {
        // The selected generation is already durable. Orphan cleanup remains
        // best-effort and is retried by the next save.
      }
      this.loadedGeneration = generation;
      this.loadedOverlays = new Map();
      return;
    }

    for (let index = 0; index < chunkCount; index += 1) {
      const start = index * this.contract.chunk_bytes;
      const chunk = bytes.slice(start, Math.min(start + this.contract.chunk_bytes, bytes.byteLength));
      await this.storage.put(chunkKey(this.contract, generation, index), chunk);
    }
    const manifest = {
      schema_version: this.contract.schema_version,
      encoding: "json-utf8",
      generation,
      byte_length: bytes.byteLength,
      chunk_bytes: this.contract.chunk_bytes,
      chunk_count: chunkCount,
    };
    await this.storage.put(this.contract.manifest_key, manifest);
    this.loadedGeneration = generation;
    this.loadedOverlays = new Map();

    try {
      await cleanupUnselected(this.storage, generation, this.contract);
      if (this.livenessEnabled) await cleanupLiveness(this.storage);
    } catch {
      // Receipt custody is already committed through the manifest. Cleanup is
      // deliberately best-effort and stale overlays cannot match this generation.
    }
  }
}

export const durableStateStoreContract = Object.freeze({
  schema_version: "limen.conduct_state_store_contract.v2",
  manifest_key: MANIFEST_KEY,
  legacy_key: LEGACY_STATE_KEY,
  chunk_prefix: CHUNK_PREFIX,
  chunk_bytes: CHUNK_BYTES,
  max_state_bytes: MAX_STATE_BYTES,
  liveness_schema: LIVENESS_SCHEMA,
  liveness_prefix: LIVENESS_PREFIX,
  steady_heartbeat_max_rows_written: 1,
  steady_heartbeat_rows_deleted: 0,
});
