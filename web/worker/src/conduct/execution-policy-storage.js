// Transport only: admission always receives the complete decoded policy object.
const STORAGE_SCHEMA = "limen.execution_policy_storage.v1";
const MAX_BINDING_BYTES = 5120;
const MAX_POLICY_BYTES = 65536;
const encoder = new TextEncoder();

function object(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export async function readExecutionPolicy(binding) {
  try {
    const raw = binding === "" ? "{}" : binding ?? "{}";
    if (typeof raw !== "string" || encoder.encode(raw).length > MAX_POLICY_BYTES) throw new Error();
    const value = JSON.parse(raw);
    if (!object(value)) throw new Error();
    if (!String(value.schema_version || "").startsWith("limen.execution_policy_storage.")) return value;
    if (encoder.encode(raw).length > MAX_BINDING_BYTES
        || value.schema_version !== STORAGE_SCHEMA || value.encoding !== "gzip+base64"
        || Object.keys(value).sort().join(",") !== "data,encoding,schema_version,sha256,uncompressed_bytes"
        || !/^[0-9a-f]{64}$/.test(value.sha256)
        || !Number.isSafeInteger(value.uncompressed_bytes)
        || value.uncompressed_bytes < 2 || value.uncompressed_bytes > MAX_POLICY_BYTES
        || typeof value.data !== "string" || !value.data || value.data.length % 4 !== 0) throw new Error();
    const packed = atob(value.data);
    if (btoa(packed) !== value.data) throw new Error();
    const bytes = Uint8Array.from(packed, char => char.charCodeAt(0));
    const reader = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip")).getReader();
    const decoded = new Uint8Array(value.uncompressed_bytes);
    let offset = 0;
    try {
      for (;;) {
        const {value: chunk, done} = await reader.read();
        if (done) break;
        if (offset + chunk.length > decoded.length) throw new Error();
        decoded.set(chunk, offset);
        offset += chunk.length;
      }
    } finally {
      await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
    if (offset !== decoded.length) throw new Error();
    const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", decoded));
    if (Array.from(digest, byte => byte.toString(16).padStart(2, "0")).join("") !== value.sha256) throw new Error();
    const policy = JSON.parse(new TextDecoder("utf-8", {fatal: true}).decode(decoded));
    if (!object(policy) || String(policy.schema_version || "").startsWith("limen.execution_policy_storage.")) throw new Error();
    return policy;
  } catch {
    // Never expose payload, JSON, base64 or provider exception details.
    throw new Error("execution_policy_invalid");
  }
}
