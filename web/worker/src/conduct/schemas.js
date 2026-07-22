import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { canonicalize } from "json-canonicalize";

import conductorSessionSchema from "../../../../spec/contracts/conduct/conductor-session-v1.schema.json" with { type: "json" };
import executorAttemptSchema from "../../../../spec/contracts/conduct/executor-attempt-v1.schema.json" with { type: "json" };
import leaseSchema from "../../../../spec/contracts/conduct/lease-v1.schema.json" with { type: "json" };
import runReceiptSchema from "../../../../spec/contracts/conduct/run-receipt-v1.schema.json" with { type: "json" };
import workPacketSchema from "../../../../spec/contracts/conduct/work-packet-v1.schema.json" with { type: "json" };

const IDENTIFIER_RE = /^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$/;
const RESOURCE_RE = /^[A-Za-z0-9][A-Za-z0-9._:/@*+-]{0,1023}$/;
const HASH_RE = /^[a-f0-9]{64}$/;
const encoder = new TextEncoder();

const ajv = new Ajv2020({
  allErrors: true,
  strict: false,
  useDefaults: true,
});
addFormats(ajv);

const validators = {
  session: ajv.compile(conductorSessionSchema),
  attempt: ajv.compile(executorAttemptSchema),
  lease: ajv.compile(leaseSchema),
  receipt: ajv.compile(runReceiptSchema),
  packet: ajv.compile(workPacketSchema),
};

export class ConductValidationError extends Error {
  constructor(message) {
    super(message);
    this.name = "ConductValidationError";
    this.status = 422;
  }
}

function clone(value) {
  try {
    return structuredClone(value);
  } catch {
    throw new ConductValidationError("conduct payload must be structured JSON");
  }
}

function fail(message) {
  throw new ConductValidationError(message);
}

function validateSchema(kind, payload) {
  const value = clone(payload);
  if (!validators[kind](value)) {
    const detail = ajv.errorsText(validators[kind].errors, { separator: "; " });
    fail(`${kind} schema rejected: ${detail}`);
  }
  return value;
}

function assertIdentifier(value, field) {
  if (typeof value !== "string" || !IDENTIFIER_RE.test(value)) fail(`${field} must be a bounded protocol identifier`);
}

function assertIdentity(identity, field = "identity") {
  assertIdentifier(identity.agent, `${field}.agent`);
  assertIdentifier(identity.surface, `${field}.surface`);
  assertIdentifier(identity.session_id, `${field}.session_id`);
}

function assertDate(value, field) {
  if (typeof value !== "string" || !Number.isFinite(Date.parse(value))) fail(`${field} must be an RFC 3339 timestamp`);
}

function assertBoundedText(value, field) {
  if (typeof value !== "string" || !value.trim() || value.length > 8192 || value.includes("\0")) {
    fail(`${field} must be a non-empty bounded string`);
  }
}

export function stableStringify(value) {
  return canonicalize(value);
}

export async function canonicalHash(value) {
  const raw = await crypto.subtle.digest("SHA-256", encoder.encode(stableStringify(value)));
  return [...new Uint8Array(raw)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function identityDefaults(identity) {
  return {
    schema_version: "limen.agent_identity.v1",
    native_run_id: null,
    provider_identity: null,
    ...identity,
  };
}

export function validateSession(payload, now = new Date()) {
  const timestamp = now.toISOString();
  const candidate = {
    schema_version: "limen.conductor_session.v1",
    native_session_id: null,
    native_run_id: null,
    worktree: null,
    capabilities: [],
    transport: "native",
    native_fanout: false,
    harvest_method: "receipt",
    concurrency: 1,
    meter: null,
    registered_at: timestamp,
    heartbeat_at: timestamp,
    human_protected: false,
    accepting_work: true,
    ...clone(payload),
  };
  if (candidate.identity) candidate.identity = identityDefaults(candidate.identity);
  const session = validateSchema("session", candidate);
  assertIdentifier(session.session_id, "session_id");
  assertIdentity(session.identity);
  if (session.identity.session_id !== session.session_id) fail("identity.session_id must equal session_id");
  for (const capability of session.capabilities) assertIdentifier(capability, "capability");
  assertIdentifier(session.transport, "transport");
  assertIdentifier(session.harvest_method, "harvest_method");
  assertDate(session.registered_at, "registered_at");
  assertDate(session.heartbeat_at, "heartbeat_at");
  return session;
}

function envelopeDefaults(authority) {
  return {
    schema_version: "limen.authority_envelope.v1",
    actions: [],
    repositories: [],
    path_prefixes: [],
    external_effects: [],
    may_delegate: true,
    ...authority,
  };
}

export async function validateWorkPacket(payload) {
  const candidate = {
    schema_version: "limen.work_packet.v1",
    root_run_id: null,
    parent_run_id: null,
    execution: {},
    intent_hash: "",
    execution_hash: "",
    work_loan: null,
    preferred_agent: null,
    required_capabilities: [],
    resource_claims: [],
    spend: {
      schema_version: "limen.spend_envelope.v1",
      unit: "runs",
      limit: 1,
      reserve: 0,
    },
    retry: {
      schema_version: "limen.retry_policy.v1",
      max_attempts: 1,
      transient_only: true,
    },
    depth: 0,
    fanout: {
      schema_version: "limen.fanout_bounds.v1",
      max_children: 0,
      max_depth: 0,
    },
    effect: "write",
    task_id: null,
    ...clone(payload),
  };
  if (candidate.initiator) candidate.initiator = identityDefaults(candidate.initiator);
  if (candidate.conductor) candidate.conductor = identityDefaults(candidate.conductor);
  if (candidate.authority) candidate.authority = envelopeDefaults(candidate.authority);
  const packet = validateSchema("packet", candidate);
  assertIdentifier(packet.work_id, "work_id");
  assertIdentifier(packet.work_key, "work_key");
  assertIdentity(packet.initiator, "initiator");
  assertIdentity(packet.conductor, "conductor");
  if (packet.preferred_agent) assertIdentifier(packet.preferred_agent, "preferred_agent");
  if (packet.task_id) assertIdentifier(packet.task_id, "task_id");
  for (const capability of packet.required_capabilities) assertIdentifier(capability, "required_capability");
  for (const claim of packet.resource_claims) {
    if (typeof claim.key !== "string" || !RESOURCE_RE.test(claim.key)) fail("resource key contains unsupported characters or is too long");
  }
  for (const field of ["actions", "repositories", "external_effects"]) {
    for (const atom of packet.authority[field]) {
      if (atom !== "*") assertIdentifier(atom, `authority.${field}`);
    }
  }
  if (packet.authority.path_prefixes.some((path) => typeof path !== "string" || path.length > 4096 || path.includes("\0"))) {
    fail("authority.path_prefixes must be bounded strings without NUL");
  }
  assertBoundedText(packet.predicate, "predicate");
  assertBoundedText(packet.receipt_target, "receipt_target");
  assertDate(packet.deadline, "deadline");
  if (packet.spend.reserve > packet.spend.limit) fail("spend reserve cannot exceed limit");
  if (packet.parent_run_id === null && packet.depth !== 0) fail("root work packet depth must be zero");
  if (packet.parent_run_id !== null && packet.depth === 0) fail("child work packet depth must be positive");
  if (packet.effect === "external" && !packet.authority.external_effects.length) {
    fail("external work requires an explicit external-effect authority");
  }
  const expectedIntentHash = await canonicalHash(packet.intent);
  const expectedExecutionHash = await canonicalHash(packet.execution);
  if (packet.intent_hash && !HASH_RE.test(packet.intent_hash)) fail("intent_hash must be a lowercase SHA-256 digest");
  if (packet.execution_hash && !HASH_RE.test(packet.execution_hash)) fail("execution_hash must be a lowercase SHA-256 digest");
  if (packet.intent_hash && packet.intent_hash !== expectedIntentHash) fail("intent_hash does not match canonical intent");
  if (packet.execution_hash && packet.execution_hash !== expectedExecutionHash) fail("execution_hash does not match canonical execution");
  packet.intent_hash ||= expectedIntentHash;
  packet.execution_hash ||= expectedExecutionHash;
  return packet;
}

export function validateReceipt(payload, now = new Date()) {
  const timestamp = now.toISOString();
  const candidate = {
    schema_version: "limen.run_receipt.v1",
    provider_identity: null,
    observed_heads_before: {},
    observed_heads_after: {},
    changed_paths: [],
    provider_run_url: null,
    checks: [],
    reviews: [],
    spend: {},
    child_runs: [],
    completed_at: timestamp,
    ...clone(payload),
  };
  if (candidate.executor) candidate.executor = identityDefaults(candidate.executor);
  if (candidate.predicate) {
    candidate.predicate = {
      summary: "",
      observed_at: timestamp,
      ...candidate.predicate,
    };
  }
  const receipt = validateSchema("receipt", candidate);
  assertIdentifier(receipt.receipt_id, "receipt_id");
  assertIdentifier(receipt.run_id, "run_id");
  assertIdentifier(receipt.lease_id, "lease_id");
  assertIdentity(receipt.executor, "executor");
  assertDate(receipt.completed_at, "completed_at");
  assertDate(receipt.predicate.observed_at, "predicate.observed_at");
  return receipt;
}

export function validateLease(payload) {
  const lease = validateSchema("lease", payload);
  assertIdentifier(lease.lease_id, "lease_id");
  assertIdentifier(lease.run_id, "run_id");
  assertIdentity(lease.executor, "executor");
  assertDate(lease.acquired_at, "acquired_at");
  assertDate(lease.heartbeat_at, "heartbeat_at");
  assertDate(lease.hard_deadline, "hard_deadline");
  return lease;
}

export function validateExecutorAttempt(payload, now = new Date()) {
  const source = clone(payload);
  const timestamp = now.toISOString();
  const candidate = {
    schema_version: "limen.executor_attempt.v1",
    provider_run_id: null,
    provider_run_url: null,
    failure_class: null,
    submitted_at: timestamp,
    updated_at: timestamp,
    detail: "",
    ...source,
  };
  if (candidate.executor) candidate.executor = identityDefaults(candidate.executor);
  const attempt = validateSchema("attempt", candidate);
  for (const field of ["attempt_id", "run_id", "lease_id", "adapter"]) {
    assertIdentifier(attempt[field], field);
  }
  if (!Number.isSafeInteger(attempt.lease_generation) || attempt.lease_generation < 1) {
    fail("lease_generation must be a positive integer");
  }
  attempt.executor = identityDefaults(attempt.executor);
  assertIdentity(attempt.executor, "executor");
  if (attempt.provider_run_id !== null) assertIdentifier(attempt.provider_run_id, "provider_run_id");
  if (!["launching", "submitted", "running", "succeeded", "failed", "blocked"].includes(attempt.status)) {
    fail("executor attempt status is unsupported");
  }
  for (const field of ["provider_run_url", "detail"]) {
    if (attempt[field] !== null
        && (typeof attempt[field] !== "string" || attempt[field].length > 4096 || attempt[field].includes("\0"))) {
      fail(`${field} must be bounded and contain no NUL`);
    }
  }
  assertDate(attempt.submitted_at, "submitted_at");
  assertDate(attempt.updated_at, "updated_at");
  return attempt;
}
