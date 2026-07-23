import { conflictingKeys, parseResource, sortedClaims } from "./resources.js";
import {
  canonicalHash,
  stableStringify,
  validateLease,
} from "./schemas.js";
import {
  packetIsNonCapacityProjection,
  packetWorkLoanMissingFields,
  workLoanDenial,
} from "./work-loan.js";

const ACTIVE_LEASE_STATES = new Set(["reserved", "active"]);
const ACTIVE_RUN_STATES = new Set(["reserved", "running", "stop_requested"]);
const encoder = new TextEncoder();

export class ConductError extends Error {
  constructor(message, status = 409) {
    super(message);
    this.name = "ConductError";
    this.status = status;
  }
}

export function emptyConductState() {
  return {
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
}

function clone(value) {
  return structuredClone(value);
}

function asDate(value) {
  return new Date(value);
}

function identitiesEqual(left, right) {
  return stableStringify(left) === stableStringify(right);
}

function isTaskCompatibilityPacket(packet) {
  return packetIsNonCapacityProjection(packet);
}

function requireWorkLoan(packet) {
  const missing = packetWorkLoanMissingFields(packet);
  if (missing.length) throw new ConductError(workLoanDenial(missing));
}

function coveredAtoms(child, parent) {
  return parent.includes("*") || child.every((atom) => parent.includes(atom));
}

function coveredPaths(child, parent) {
  if (parent.includes("*") || parent.includes(".")) return true;
  return child.every((path) => parent.some((base) =>
    path === base || path.startsWith(`${base.replace(/\/+$/, "")}/`)));
}

export function authorityAttenuates(child, parent) {
  return coveredAtoms(child.actions, parent.actions)
    && coveredAtoms(child.repositories, parent.repositories)
    && coveredPaths(child.path_prefixes, parent.path_prefixes)
    && coveredAtoms(child.external_effects, parent.external_effects)
    && (parent.may_delegate || !child.may_delegate);
}

async function sha256Text(value) {
  const raw = await crypto.subtle.digest("SHA-256", encoder.encode(value));
  return [...new Uint8Array(raw)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function capabilityToken(secret, leaseId, generation, principalId) {
  if (typeof secret !== "string" || secret.length < 24) {
    throw new ConductError("conduct capability secret is not configured", 503);
  }
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const binding = `limen.lease-capability.v1\0${leaseId}\0${generation}\0${principalId}`;
  const raw = new Uint8Array(await crypto.subtle.sign("HMAC", key, encoder.encode(binding)));
  let binary = "";
  for (const byte of raw) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

function constantTimeTextEqual(left, right) {
  if (left.length !== right.length) return false;
  let mismatch = 0;
  for (let index = 0; index < left.length; index += 1) mismatch |= left.charCodeAt(index) ^ right.charCodeAt(index);
  return mismatch === 0;
}

function validateLoadedState(input) {
  const state = clone(input || emptyConductState());
  if (state.schema_version !== "limen.conduct_state.v1") {
    throw new ConductError("stored conduct state has an unsupported schema version", 500);
  }
  for (const field of [
    "sessions",
    "session_principals",
    "runs",
    "leases",
    "work_index",
    "work_key_index",
    "receipt_index",
    "resource_generations",
  ]) {
    state[field] ||= {};
  }
  state.events ||= [];
  state.next_generation ||= 0;
  for (const lease of Object.values(state.leases)) validateLease(lease);
  return state;
}

export class ConductKernel {
  constructor(
    input,
    {
      now = new Date(),
      sessionTtlMs = 5 * 60 * 1000,
      adoptionAfterMs = 10 * 60 * 1000,
      leaseTtlMs = 15 * 60 * 1000,
      capabilitySecret = null,
    } = {},
  ) {
    this.state = validateLoadedState(input);
    this.now = now;
    this.timestamp = now.toISOString();
    this.sessionTtlMs = sessionTtlMs;
    this.adoptionAfterMs = adoptionAfterMs;
    this.leaseTtlMs = leaseTtlMs;
    this.capabilitySecret = capabilitySecret;
    this.projectionEvents = [];
    this.mutated = false;
  }

  async execute(operation, payload = {}) {
    switch (operation) {
      case "register": return this.register(payload.session, payload.principal);
      case "capabilities": return this.capabilities();
      case "submit": return this.submit(payload.packet, payload.principal);
      case "submit_graph": return this.submitGraph(payload.packets, payload.principal);
      case "split": return this.split(payload.parent_run_id, payload.packet, payload.principal);
      case "graph": return this.graph(payload.run_id);
      case "claim": return this.claim(payload.lease_id, payload.generation, payload.principal);
      case "heartbeat": return this.heartbeat(
        payload.lease_id,
        payload.capability_token,
        payload.generation,
        payload.principal,
        payload.observed_heads,
        payload.attempt,
      );
      case "report": return this.report(
        payload.lease_id,
        payload.capability_token,
        payload.generation,
        payload.principal,
        payload.receipt,
      );
      case "harvest": return this.harvest(payload.run_id);
      case "adopt": return this.adopt(payload.run_id, payload.session_id, payload.principal);
      case "cancel": return this.cancel(payload.run_id, payload.session_id, payload.principal);
      case "request_stop": return this.requestStop(payload.run_id, payload.session_id, payload.principal);
      default: throw new ConductError(`unsupported conduct operation: ${operation}`, 404);
    }
  }

  recordEvent(kind, payload = {}) {
    this.state.events.push({
      sequence: this.state.events.length + 1,
      timestamp: this.timestamp,
      kind,
      ...payload,
    });
    this.mutated = true;
  }

  principalForIdentity(identity, principal) {
    if (principal) return { principal, enforced: true };
    return {
      enforced: false,
      principal: {
        schema_version: "limen.conduct_principal.v1",
        principal_id: `local:${identity.agent}:${identity.surface}`,
        agent: identity.agent,
        surface: identity.surface,
        roles: ["observer", "conductor", "executor", "compatibility"],
      },
    };
  }

  requireRole(principal, ...roles) {
    if (!roles.some((role) => principal.roles.includes(role))) {
      throw new ConductError(`authenticated principal lacks required ${roles.join("/")} role`, 403);
    }
  }

  bindSessionIdentity(session, principal) {
    return {
      ...clone(session),
      identity: {
        ...clone(session.identity),
        agent: principal.agent,
        surface: principal.surface,
        session_id: session.session_id,
      },
    };
  }

  bindConductorIdentity(identity, principal) {
    // register() stores token-bound agent/surface; comparisons against the
    // stored session must apply the same binding or a client that declares
    // its own surface can never match (the #1408 relay freeze).
    return {
      ...clone(identity),
      agent: principal.agent,
      surface: principal.surface,
    };
  }

  taskEvent(run, lease, {
    kind,
    status,
    fromStatuses,
    budgetAction = "none",
    suffix = kind,
    output,
  }) {
    const taskId = run.packet.task_id;
    if (!taskId) return;
    this.projectionEvents.push({
      schema_version: "limen.task_compatibility_event.v1",
      event_id: `conduct:${run.run_id}:${lease.generation}:${suffix}`,
      kind,
      timestamp: this.timestamp,
      task_id: taskId,
      run_id: run.run_id,
      lease_id: lease.lease_id,
      generation: lease.generation,
      agent: lease.executor.agent,
      session_id: run.run_id,
      status,
      from_statuses: fromStatuses,
      budget_action: budgetAction,
      budget_cost: run.packet.spend.limit,
      output,
    });
  }

  taskPacketEvent(run, lease) {
    const intent = run.packet.intent;
    this.projectionEvents.push({
      schema_version: "limen.task_packet_projection_event.v1",
      event_id: `conduct:${run.run_id}:${lease.generation}:compatibility`,
      kind: intent.kind,
      timestamp: this.timestamp,
      task_id: run.packet.task_id,
      run_id: run.run_id,
      lease_id: lease.lease_id,
      generation: lease.generation,
      agent: run.packet.conductor.agent,
      session_id: run.packet.conductor.session_id,
      lease_executor: clone(lease.executor),
      intent: clone(intent),
    });
  }

  register(session, requestedPrincipal = null) {
    const { principal, enforced } = this.principalForIdentity(session.identity, requestedPrincipal);
    this.requireRole(principal, "conductor", "executor");
    session = this.bindSessionIdentity(session, principal);
    const current = this.state.sessions[session.session_id];
    if (current && !identitiesEqual(current.identity, session.identity)) {
      throw new ConductError("session_id is already registered to another identity");
    }
    if (session.worktree) {
      const claimed = parseResource(`worktree/${session.worktree}`).identity[0];
      for (const owner of Object.values(this.state.sessions)) {
        if (owner.session_id === session.session_id || !owner.worktree) continue;
        const owned = parseResource(`worktree/${owner.worktree}`).identity[0];
        if (owned === claimed && this.now - asDate(owner.heartbeat_at) <= this.sessionTtlMs) {
          throw new ConductError(`worktree is already owned by healthy session ${owner.session_id}`);
        }
      }
    }
    const stored = {
      ...clone(session),
      registered_at: current?.registered_at || this.timestamp,
      heartbeat_at: this.timestamp,
      human_protected: Boolean(current?.human_protected || session.human_protected),
    };
    const priorPrincipal = this.state.session_principals[session.session_id];
    if (priorPrincipal && priorPrincipal !== principal.principal_id) {
      throw new ConductError("session_id is already bound to another principal", 403);
    }
    this.state.sessions[session.session_id] = stored;
    this.state.session_principals[session.session_id] = principal.principal_id;
    this.recordEvent("session.registered", {
      session_id: session.session_id,
      agent: session.identity.agent,
      principal_id: enforced ? principal.principal_id : "local-development",
    });
    return clone(stored);
  }

  capabilities() {
    const load = this.activeLoad();
    const sessions = Object.values(this.state.sessions).map((session) => ({
      ...clone(session),
      healthy: this.now - asDate(session.heartbeat_at) <= this.sessionTtlMs,
      active_leases: load[session.session_id] || 0,
    }));
    sessions.sort((left, right) =>
      left.identity.agent.localeCompare(right.identity.agent) || left.session_id.localeCompare(right.session_id));
    return {
      schema_version: "limen.conduct_capabilities.v1",
      generated_at: this.timestamp,
      sessions,
    };
  }

  async submit(packet, requestedPrincipal = null) {
    const { principal, enforced } = this.principalForIdentity(packet.conductor, requestedPrincipal);
    this.requireRole(principal, "conductor", "compatibility");
    requireWorkLoan(packet);
    if (asDate(packet.deadline) <= this.now) {
      throw new ConductError("work packet deadline has already passed", 422);
    }
    await this.expireLeases();
    const conductor = this.state.sessions[packet.conductor.session_id];
    if (!conductor) {
      throw new ConductError("packet conductor must be a registered session");
    }
    if (!identitiesEqual(conductor.identity, this.bindConductorIdentity(packet.conductor, principal))) {
      throw new ConductError("packet conductor identity does not match its registered session");
    }
    if (this.now - asDate(conductor.heartbeat_at) > this.sessionTtlMs) {
      throw new ConductError("packet conductor session is not healthy");
    }
    if (this.state.session_principals[conductor.session_id] !== principal.principal_id) {
      throw new ConductError("packet conductor is not bound to the authenticated principal", 403);
    }
    const neededCapability = packet.execution?.adapter === "tabularius" ? "task-submit" : "conduct";
    if (!conductor.capabilities.includes(neededCapability)) {
      throw new ConductError(`packet conductor lacks required ${neededCapability} capability`);
    }
    const byId = this.state.work_index[packet.work_id];
    const byKey = this.state.work_key_index[packet.work_key];
    if (byId && byKey && byId !== byKey) {
      throw new ConductError("work id/key indexes disagree");
    }
    if (packet.parent_run_id && byKey) {
      let cursor = this.state.runs[packet.parent_run_id];
      while (cursor) {
        if (packet.work_key === cursor.packet.work_key) {
          throw new ConductError("repeated ancestry work_key/cycle rejected");
        }
        cursor = cursor.parent_run_id ? this.state.runs[cursor.parent_run_id] : null;
      }
    }
    const duplicateRunId = byId || byKey;
    if (duplicateRunId) {
      const run = this.state.runs[duplicateRunId];
      const stored = run.packet;
      const samePayload = stored.intent_hash === packet.intent_hash
        && stored.execution_hash === packet.execution_hash
        && stored.work_key === packet.work_key
        && identitiesEqual(stored.initiator, packet.initiator)
        && identitiesEqual(stored.conductor, packet.conductor)
        && stableStringify(stored.authority) === stableStringify(packet.authority)
        && stableStringify(stored.resource_claims) === stableStringify(packet.resource_claims)
        && stored.predicate === packet.predicate
        && stored.receipt_target === packet.receipt_target
        && stableStringify(stored.work_loan) === stableStringify(packet.work_loan);
      if (!samePayload) {
        throw new ConductError("work id/key was reused with different immutable hashes or contract");
      }
      if (this.state.work_index[packet.work_id] !== duplicateRunId) {
        this.state.work_index[packet.work_id] = duplicateRunId;
        this.mutated = true;
      }
      if (this.state.work_key_index[packet.work_key] !== duplicateRunId) {
        this.state.work_key_index[packet.work_key] = duplicateRunId;
        this.mutated = true;
      }
      return this.submitResult(run, true);
    }
    const parent = this.validateLineage(packet, enforced ? principal.principal_id : null);
    const executor = this.selectExecutor(packet);
    const claims = this.effectiveClaims(packet);
    const conflicts = [];
    for (const lease of Object.values(this.state.leases)) {
      if (!ACTIVE_LEASE_STATES.has(lease.state)) continue;
      const keys = conflictingKeys(claims, lease.resources);
      if (keys.length) conflicts.push({ lease_id: lease.lease_id, run_id: lease.run_id, keys });
    }
    if (conflicts.length) {
      conflicts.sort((left, right) => left.lease_id.localeCompare(right.lease_id));
      const digest = await canonicalHash({
        work_id: packet.work_id,
        intent_hash: packet.intent_hash,
        execution_hash: packet.execution_hash,
        conflicts,
      });
      return {
        schema_version: "limen.conduct_submit_result.v1",
        status: "busy",
        busy_receipt_id: `busy-${digest.slice(0, 24)}`,
        work_id: packet.work_id,
        conflicts,
      };
    }
    const runDigest = await canonicalHash({
      work_id: packet.work_id,
      intent_hash: packet.intent_hash,
      execution_hash: packet.execution_hash,
    });
    const runId = `run-${runDigest.slice(0, 32)}`;
    const rootRunId = parent ? parent.root_run_id : runId;
    if (packet.root_run_id && packet.root_run_id !== rootRunId) {
      throw new ConductError("root_run_id does not match the broker-owned lineage root");
    }
    const generation = Number(this.state.next_generation || 0) + 1;
    this.state.next_generation = generation;
    const resourceGenerations = {};
    for (const claim of claims) {
      const next = Number(this.state.resource_generations[claim.key] || 0) + 1;
      this.state.resource_generations[claim.key] = next;
      resourceGenerations[claim.key] = next;
    }
    const leaseId = `lease-${generation}-${runId.slice(4, 20)}`;
    let executorPrincipalId = this.state.session_principals[executor.session_id];
    if (isTaskCompatibilityPacket(packet)) executorPrincipalId = principal.principal_id;
    if (!executorPrincipalId) {
      throw new ConductError("selected executor session has no authenticated principal binding");
    }
    const token = await capabilityToken(
      this.capabilitySecret,
      leaseId,
      generation,
      executorPrincipalId,
    );
    const observedHeads = {};
    for (const [key, value] of Object.entries(packet.execution.observed_heads || {})) {
      if (key && value) observedHeads[String(key)] = String(value);
    }
    const hardDeadline = new Date(Math.min(
      asDate(packet.deadline).getTime(),
      this.now.getTime() + this.leaseTtlMs,
    ));
    const lease = {
      schema_version: "limen.lease.v1",
      lease_id: leaseId,
      run_id: runId,
      executor: clone(executor.identity),
      executor_principal_id: executorPrincipalId,
      resources: claims,
      observed_heads: observedHeads,
      generation,
      resource_generations: resourceGenerations,
      capability_token_hash: await sha256Text(token),
      acquired_at: this.timestamp,
      heartbeat_at: this.timestamp,
      hard_deadline: hardDeadline.toISOString(),
      state: "reserved",
    };
    const run = {
      run_id: runId,
      root_run_id: rootRunId,
      parent_run_id: packet.parent_run_id,
      packet: clone(packet),
      conductor_session_id: packet.conductor.session_id,
      conductor_principal_id: principal.principal_id,
      executor_session_id: executor.session_id,
      lease_id: leaseId,
      status: "reserved",
      children: [],
      receipts: [],
      attempts: [],
      projection_receipts: [],
      compatibility_projection: isTaskCompatibilityPacket(packet),
      created_at: this.timestamp,
      updated_at: this.timestamp,
    };
    this.state.runs[runId] = run;
    this.state.leases[leaseId] = lease;
    this.state.work_index[packet.work_id] = runId;
    this.state.work_key_index[packet.work_key] = runId;
    if (parent) {
      parent.children.push(runId);
      parent.updated_at = this.timestamp;
    }
    this.recordEvent("run.reserved", {
      run_id: runId,
      root_run_id: rootRunId,
      executor_session_id: executor.session_id,
      lease_id: leaseId,
      generation,
    });
    if (run.compatibility_projection) {
      this.taskPacketEvent(run, lease);
      run.status = "succeeded";
      run.updated_at = this.timestamp;
      lease.state = "released";
      lease.heartbeat_at = this.timestamp;
      this.recordEvent("task.compatibility_applied", {
        run_id: runId,
        task_id: packet.task_id,
        kind: packet.intent.kind,
        lease_id: leaseId,
        generation,
      });
    } else {
      this.taskEvent(run, lease, {
        kind: "task.dispatched",
        status: "dispatched",
        fromStatuses: ["open"],
        budgetAction: "debit",
        suffix: "reserved",
        output: `Conduct broker reserved ${runId} for ${executor.identity.agent}`,
      });
    }
    return this.submitResult(run, false);
  }

  async submitGraph(packets, requestedPrincipal = null) {
    if (!Array.isArray(packets) || !packets.length) {
      throw new ConductError("conduct graph submission requires at least one packet", 422);
    }
    if (packets.some((packet) => isTaskCompatibilityPacket(packet) || packet.task_id)) {
      throw new ConductError("task-board packets are not accepted in graph submissions");
    }
    for (const packet of packets) requireWorkLoan(packet);
    const { principal } = this.principalForIdentity(packets[0].conductor, requestedPrincipal);
    this.requireRole(principal, "conductor");
    if (packets.some((packet) => packet.conductor.session_id !== packets[0].conductor.session_id)) {
      throw new ConductError("atomic graph packets must share one owning conductor session");
    }
    const originalState = clone(this.state);
    const originalEvents = clone(this.projectionEvents);
    const originalMutated = this.mutated;
    const results = [];
    try {
      for (const [index, packet] of packets.entries()) {
        const dependencies = packet.execution?.dependencies || [];
        const result = dependencies.length
          ? await this.deferDependencyPacket(packet, principal)
          : await this.submit(packet, principal);
        if (result.status === "busy") {
          this.state = originalState;
          this.projectionEvents = originalEvents;
          this.mutated = originalMutated;
          return {
            schema_version: "limen.conduct_graph_submit_result.v1",
            status: "busy",
            work_id: result.work_id,
            conflicts: result.conflicts,
          };
        }
        results.push(result);
        if (index === 0 && packet.intent?.kind === "fanout-root" && result.status !== "duplicate") {
          const run = this.state.runs[result.run_id];
          const lease = this.state.leases[run.lease_id];
          lease.state = "released";
          lease.heartbeat_at = this.timestamp;
          run.status = "running";
          run.executor_session_id = null;
          run.updated_at = this.timestamp;
          this.recordEvent("fanout.campaign_started", { run_id: run.run_id });
        }
      }
    } catch (error) {
      this.state = originalState;
      this.projectionEvents = originalEvents;
      this.mutated = originalMutated;
      throw error;
    }
    return {
      schema_version: "limen.conduct_graph_submit_result.v1",
      status: "reserved",
      root_run_id: results[0].root_run_id,
      runs: results,
    };
  }

  async deferDependencyPacket(packet, principal) {
    requireWorkLoan(packet);
    if (asDate(packet.deadline) <= this.now) {
      throw new ConductError("work packet deadline has already passed", 422);
    }
    const dependencies = packet.execution?.dependencies || [];
    if (!dependencies.length) throw new ConductError("dependency deferral requires dependencies", 422);
    const conductor = this.state.sessions[packet.conductor.session_id];
    if (!conductor || !identitiesEqual(conductor.identity, this.bindConductorIdentity(packet.conductor, principal))) {
      throw new ConductError("packet conductor must be its registered session");
    }
    if (this.state.session_principals[conductor.session_id] !== principal.principal_id) {
      throw new ConductError("packet conductor is not bound to the authenticated principal", 403);
    }
    const duplicateRunId = this.state.work_index[packet.work_id]
      || this.state.work_key_index[packet.work_key];
    if (duplicateRunId) {
      const duplicate = this.state.runs[duplicateRunId];
      if (duplicate.packet.intent_hash !== packet.intent_hash
          || duplicate.packet.execution_hash !== packet.execution_hash
          || duplicate.packet.work_key !== packet.work_key) {
        throw new ConductError("work id/key was reused with different immutable hashes");
      }
      return {
        schema_version: "limen.conduct_submit_result.v1",
        status: "duplicate",
        duplicate: true,
        work_id: packet.work_id,
        run_id: duplicate.run_id,
        root_run_id: duplicate.root_run_id,
        executor_session_id: duplicate.executor_session_id,
        lease: null,
      };
    }
    const parent = this.validateLineage(packet, principal.principal_id);
    const dependencyRunIds = dependencies.map((workId) => {
      const runId = this.state.work_index[workId];
      if (!runId) throw new ConductError(`fanout dependency is not registered: ${workId}`);
      if (this.state.runs[runId].root_run_id !== parent.root_run_id) {
        throw new ConductError("fanout dependency belongs to another graph");
      }
      return runId;
    });
    const digest = await canonicalHash({
      work_id: packet.work_id,
      intent_hash: packet.intent_hash,
      execution_hash: packet.execution_hash,
    });
    const runId = `run-${digest.slice(0, 32)}`;
    const run = {
      run_id: runId,
      root_run_id: parent.root_run_id,
      parent_run_id: packet.parent_run_id,
      packet: clone(packet),
      conductor_session_id: packet.conductor.session_id,
      conductor_principal_id: principal.principal_id,
      executor_session_id: null,
      lease_id: null,
      status: "waiting",
      children: [],
      receipts: [],
      attempts: [],
      projection_receipts: [],
      compatibility_projection: false,
      dependency_run_ids: dependencyRunIds,
      created_at: this.timestamp,
      updated_at: this.timestamp,
    };
    this.state.runs[runId] = run;
    this.state.work_index[packet.work_id] = runId;
    this.state.work_key_index[packet.work_key] = runId;
    parent.children.push(runId);
    parent.updated_at = this.timestamp;
    this.recordEvent("fanout.run_waiting", {
      run_id: runId,
      root_run_id: parent.root_run_id,
      dependencies: dependencyRunIds,
    });
    return {
      schema_version: "limen.conduct_submit_result.v1",
      status: "waiting",
      duplicate: false,
      work_id: packet.work_id,
      run_id: runId,
      root_run_id: parent.root_run_id,
      executor_session_id: null,
      lease: null,
    };
  }

  async split(parentRunId, packet, principal = null) {
    if (packet.parent_run_id !== parentRunId) {
      throw new ConductError("split packet parent_run_id must match the requested parent");
    }
    return this.submit(packet, principal);
  }

  graph(runId) {
    const selected = this.state.runs[runId];
    if (!selected) throw new ConductError(`unknown run: ${runId}`, 404);
    const rootRunId = selected.root_run_id;
    const nodes = Object.values(this.state.runs)
      .filter((run) => run.root_run_id === rootRunId)
      .map((run) => {
        const node = clone(run);
        if (run.lease_id && this.state.leases[run.lease_id]) {
          node.lease = this.publicLease(this.state.leases[run.lease_id]);
        }
        return node;
      })
      .sort((left, right) => left.created_at.localeCompare(right.created_at) || left.run_id.localeCompare(right.run_id));
    return {
      schema_version: "limen.conduct_graph.v1",
      root_run_id: rootRunId,
      nodes,
    };
  }

  async claim(leaseId, generation, requestedPrincipal = null) {
    await this.expireLeases();
    const lease = this.state.leases[leaseId];
    if (!lease) throw new ConductError(`unknown lease: ${leaseId}`, 404);
    const { principal, enforced } = this.principalForIdentity(lease.executor, requestedPrincipal);
    this.requireRole(principal, "executor", "compatibility");
    if (Number(generation) !== lease.generation) {
      throw new ConductError("lease generation does not match the claim");
    }
    if (enforced && lease.executor_principal_id !== principal.principal_id) {
      throw new ConductError("lease belongs to another executor principal", 403);
    }
    if (!ACTIVE_LEASE_STATES.has(lease.state)) {
      throw new ConductError(`lease is not active: ${lease.state}`);
    }
    const run = this.state.runs[lease.run_id];
    if (!run) throw new ConductError(`lease points to missing run: ${lease.run_id}`, 500);
    requireWorkLoan(run.packet);
    const principalId = lease.executor_principal_id || principal.principal_id;
    const token = await capabilityToken(
      this.capabilitySecret,
      lease.lease_id,
      lease.generation,
      principalId,
    );
    if (!constantTimeTextEqual(lease.capability_token_hash, await sha256Text(token))) {
      throw new ConductError("lease capability binding is invalid");
    }
    this.recordEvent("lease.claimed", {
      lease_id: leaseId,
      run_id: lease.run_id,
      generation: lease.generation,
      executor_principal_id: principalId,
    });
    return {
      schema_version: "limen.conduct_lease_claim.v1",
      lease_id: leaseId,
      run_id: lease.run_id,
      generation: lease.generation,
      capability_token: token,
    };
  }

  async heartbeat(
    leaseId,
    capabilityToken,
    generation = null,
    principal = null,
    observedHeads = {},
    attempt = null,
  ) {
    await this.expireLeases();
    const lease = await this.authorizedLease(
      leaseId,
      capabilityToken,
      generation,
      principal,
    );
    if (!ACTIVE_LEASE_STATES.has(lease.state)) throw new ConductError(`lease is not active: ${lease.state}`);
    for (const [resource, expected] of Object.entries(lease.observed_heads || {})) {
      const actual = observedHeads[resource];
      if (actual === undefined || actual !== expected) {
        lease.state = "fenced";
        lease.heartbeat_at = this.timestamp;
        const run = this.state.runs[lease.run_id];
        run.status = "fenced";
        run.updated_at = this.timestamp;
        const reason = actual === undefined
          ? `required observed head omitted for ${resource}`
          : `observed head moved for ${resource}`;
        if (run.packet?.intent?.kind === "fanout-leaf") {
          run.receipts = [{
            schema_version: "limen.fanout_fence_receipt.v1",
            receipt_id: `fence-${run.run_id}`,
            run_id: run.run_id,
            outcome: "blocked",
            expected_heads: clone(lease.observed_heads || {}),
            observed_heads: clone(observedHeads),
            reason,
            mutation_authorized: true,
            accepted_at: this.timestamp,
          }];
        }
        this.recordEvent("lease.fenced", {
          lease_id: leaseId,
          run_id: lease.run_id,
          reason,
        });
        await this.advanceFanoutGraph(run.root_run_id);
        this.taskEvent(run, lease, {
          kind: "task.fenced",
          status: "failed",
          fromStatuses: ["dispatched", "in_progress"],
          suffix: "fenced",
          output: `Conduct lease fenced: ${reason}`,
        });
        return { status: "fenced", lease_id: leaseId, run_id: lease.run_id, reason };
      }
    }
    const wasReserved = lease.state === "reserved";
    const run = this.state.runs[lease.run_id];
    lease.heartbeat_at = this.timestamp;
    lease.hard_deadline = new Date(Math.min(
      asDate(run.packet.deadline).getTime(),
      this.now.getTime() + this.leaseTtlMs,
    )).toISOString();
    lease.state = "active";
    const attemptCreated = attempt ? this.recordAttempt(run, lease, attempt) : false;
    if (attempt) {
      const rerouted = await this.rerouteAfterAttempt(run, lease, attempt);
      if (rerouted) {
        return {
          status: "rerouted",
          lease: this.publicLease(rerouted),
          attempt_created: attemptCreated,
        };
      }
    }
    run.status = "running";
    run.updated_at = this.timestamp;
    const session = this.state.sessions[run.executor_session_id];
    if (session) session.heartbeat_at = this.timestamp;
    this.recordEvent("lease.heartbeat", { lease_id: leaseId, run_id: lease.run_id });
    if (wasReserved) {
      this.taskEvent(run, lease, {
        kind: "task.in_progress",
        status: "in_progress",
        fromStatuses: ["dispatched"],
        suffix: "active",
        output: `Conduct executor started ${run.run_id}`,
      });
    }
    return {
      status: "active",
      lease: this.publicLease(lease),
      attempt_created: attemptCreated,
    };
  }

  recordAttempt(run, lease, attempt) {
    if (attempt.run_id !== run.run_id
        || attempt.lease_id !== lease.lease_id
        || attempt.lease_generation !== lease.generation
        || !identitiesEqual(attempt.executor, lease.executor)) {
      throw new ConductError("executor attempt does not belong to the lease/run");
    }
    run.attempts ||= [];
    const prior = run.attempts.find((row) => row.attempt_id === attempt.attempt_id);
    if (!prior) {
      if (run.attempts.length >= run.packet.retry.max_attempts) {
        throw new ConductError("executor attempt limit exhausted");
      }
      if (run.attempts.length >= run.packet.spend.limit) {
        throw new ConductError("executor spend limit exhausted");
      }
      if (run.attempts.some((row) => !["failed", "blocked"].includes(row.status))) {
        throw new ConductError("a prior executor attempt is still live");
      }
      run.attempts.push(clone(attempt));
      return true;
    }
    for (const field of [
      "run_id",
      "lease_id",
      "lease_generation",
      "executor",
      "adapter",
      "submitted_at",
    ]) {
      if (stableStringify(prior[field]) !== stableStringify(attempt[field])) {
        throw new ConductError("executor attempt identity changed");
      }
    }
    for (const field of ["provider_run_id", "provider_run_url"]) {
      if (prior[field] && attempt[field] !== prior[field]) {
        throw new ConductError("executor provider receipt identity changed");
      }
    }
    const transitions = {
      launching: new Set(["launching", "submitted", "running", "succeeded", "failed", "blocked"]),
      submitted: new Set(["submitted", "running", "succeeded", "failed", "blocked"]),
      running: new Set(["running", "succeeded", "failed", "blocked"]),
      // Provider success precedes exact landing validation.
      succeeded: new Set(["succeeded", "failed", "blocked"]),
      failed: new Set(["failed"]),
      blocked: new Set(["blocked"]),
    };
    if (!transitions[prior.status]?.has(attempt.status)) {
      throw new ConductError("executor attempt status regressed");
    }
    Object.assign(prior, clone(attempt));
    return false;
  }

  async rerouteAfterAttempt(run, lease, attempt) {
    if (!["failed", "blocked"].includes(attempt.status)) return null;
    const attempts = run.attempts || [];
    if (
      attempts.length >= run.packet.retry.max_attempts
      || attempts.length >= run.packet.spend.limit
      || (run.packet.retry.transient_only && attempt.failure_class !== "transient")
    ) {
      return null;
    }
    let executor;
    try {
      executor = this.selectExecutor(run.packet, {
        excludeSessions: new Set([run.executor_session_id]),
        ignoreRequiredSession: true,
      });
    } catch (error) {
      if (error instanceof ConductError) return null;
      throw error;
    }
    const generation = Number(this.state.next_generation || 0) + 1;
    this.state.next_generation = generation;
    const resourceGenerations = {};
    for (const claim of lease.resources) {
      const next = Number(this.state.resource_generations[claim.key] || 0) + 1;
      this.state.resource_generations[claim.key] = next;
      resourceGenerations[claim.key] = next;
    }
    const leaseId = `lease-${generation}-${run.run_id.slice(4, 20)}`;
    const executorPrincipalId = this.state.session_principals[executor.session_id];
    if (!executorPrincipalId) {
      throw new ConductError("reroute executor has no authenticated principal binding");
    }
    const token = await capabilityToken(
      this.capabilitySecret,
      leaseId,
      generation,
      executorPrincipalId,
    );
    const replacement = {
      schema_version: "limen.lease.v1",
      lease_id: leaseId,
      run_id: run.run_id,
      executor: clone(executor.identity),
      executor_principal_id: executorPrincipalId,
      resources: clone(lease.resources),
      observed_heads: clone(lease.observed_heads),
      generation,
      resource_generations: resourceGenerations,
      capability_token_hash: await sha256Text(token),
      acquired_at: this.timestamp,
      heartbeat_at: this.timestamp,
      hard_deadline: new Date(Math.min(
        asDate(run.packet.deadline).getTime(),
        this.now.getTime() + this.leaseTtlMs,
      )).toISOString(),
      state: "reserved",
    };
    lease.state = "released";
    lease.heartbeat_at = this.timestamp;
    this.state.leases[leaseId] = replacement;
    const priorExecutorSessionId = run.executor_session_id;
    run.executor_session_id = executor.session_id;
    run.lease_id = leaseId;
    run.status = "reserved";
    run.updated_at = this.timestamp;
    this.recordEvent("run.rerouted", {
      run_id: run.run_id,
      prior_executor_session_id: priorExecutorSessionId,
      executor_session_id: executor.session_id,
      lease_id: leaseId,
      generation,
    });
    return replacement;
  }

  async report(leaseId, capabilityToken, generation, principal, receipt) {
    await this.expireLeases();
    const lease = await this.authorizedLease(
      leaseId,
      capabilityToken,
      generation,
      principal,
      true,
    );
    const indexed = this.state.receipt_index[receipt.receipt_id];
    if (indexed) {
      if (indexed.lease_id !== leaseId || indexed.run_id !== receipt.run_id) {
        throw new ConductError("receipt_id was reused for another lease/run");
      }
      return clone(indexed.result);
    }
    if (receipt.lease_id !== leaseId || receipt.run_id !== lease.run_id) {
      throw new ConductError("receipt does not belong to the lease/run");
    }
    const run = this.state.runs[lease.run_id];
    const packet = run.packet;
    const headsMatch = Object.entries(lease.observed_heads || {})
      .every(([key, value]) => receipt.observed_heads_before[key] === value);
    const changedPathsAuthorized = coveredPaths(
      receipt.changed_paths,
      packet.authority.path_prefixes,
    );
    const readOnlyAuthorized = packet.effect !== "read"
      || (receipt.changed_paths.length === 0
        && stableStringify(receipt.observed_heads_after)
          === stableStringify(receipt.observed_heads_before));
    const spendValue = receipt.spend[packet.spend.unit] ?? 0;
    const spendAuthorized = typeof spendValue === "number"
      && Number.isFinite(spendValue)
      && spendValue >= 0
      && spendValue <= packet.spend.limit;
    const childIds = new Set(receipt.child_runs);
    const childRunsAuthorized = childIds.size === receipt.child_runs.length
      && childIds.size === run.children.length
      && run.children.every((childId) => childIds.has(childId));
    const predicateAuthorized = receipt.predicate.command === packet.predicate
      && (receipt.outcome !== "succeeded" || receipt.predicate.exit_code === 0);
    const mutationAuthorized = ACTIVE_LEASE_STATES.has(lease.state)
      && receipt.lease_generation === lease.generation
      && identitiesEqual(receipt.executor, lease.executor)
      && headsMatch
      && changedPathsAuthorized
      && readOnlyAuthorized
      && spendAuthorized
      && childRunsAuthorized
      && predicateAuthorized;
    run.receipts.push({
      ...clone(receipt),
      mutation_authorized: mutationAuthorized,
      accepted_at: this.timestamp,
    });
    run.updated_at = this.timestamp;
    if (mutationAuthorized) {
      const terminal = {
        succeeded: "succeeded",
        failed: "failed",
        blocked: "blocked",
        cancelled: "cancelled",
        partial: "failed",
      }[receipt.outcome];
      run.status = terminal;
      lease.state = "released";
      lease.heartbeat_at = this.timestamp;
      this.recordEvent("run.reported", {
        run_id: run.run_id,
        outcome: receipt.outcome,
        receipt_id: receipt.receipt_id,
      });
      await this.advanceFanoutGraph(run.root_run_id);
      const taskStatus = {
        succeeded: "done",
        failed: "failed",
        blocked: "failed_blocked",
        cancelled: "failed",
        partial: "failed",
      }[receipt.outcome];
      this.taskEvent(run, lease, {
        kind: "task.reported",
        status: taskStatus,
        fromStatuses: ["dispatched", "in_progress"],
        suffix: `receipt:${receipt.receipt_id}`,
        output: `Conduct run ${run.run_id} reported ${receipt.outcome}; predicate exit ${receipt.predicate.exit_code}`,
      });
    } else {
      this.recordEvent("run.late_evidence", {
        run_id: run.run_id,
        receipt_id: receipt.receipt_id,
        lease_state: lease.state,
      });
    }
    const result = {
      schema_version: "limen.conduct_report_result.v1",
      run_id: run.run_id,
      receipt_id: receipt.receipt_id,
      mutation_authorized: mutationAuthorized,
      run_status: run.status,
    };
    this.state.receipt_index[receipt.receipt_id] = {
      lease_id: leaseId,
      run_id: receipt.run_id,
      result: clone(result),
    };
    return result;
  }

  async advanceFanoutGraph(rootRunId) {
    let progress = true;
    while (progress) {
      progress = false;
      const waiting = Object.values(this.state.runs)
        .filter((run) => run.root_run_id === rootRunId && run.status === "waiting")
        .map((run) => clone(run));
      for (const waitingRun of waiting) {
        const dependencyStates = (waitingRun.dependency_run_ids || [])
          .map((runId) => this.state.runs[runId].status);
        if (dependencyStates.some((status) =>
          ["failed", "blocked", "cancelled", "fenced", "expired"].includes(status))) {
          const current = this.state.runs[waitingRun.run_id];
          current.status = "blocked";
          current.updated_at = this.timestamp;
          current.receipts.push({
            schema_version: "limen.fanout_dependency_receipt.v1",
            receipt_id: `dependency-${current.run_id}`,
            run_id: current.run_id,
            outcome: "blocked",
            mutation_authorized: true,
            accepted_at: this.timestamp,
          });
          this.recordEvent("fanout.run_dependency_blocked", { run_id: current.run_id });
          progress = true;
          continue;
        }
        if (!dependencyStates.length || dependencyStates.some((status) => status !== "succeeded")) continue;
        const original = clone(this.state);
        const packet = waitingRun.packet;
        delete this.state.runs[waitingRun.run_id];
        delete this.state.work_index[packet.work_id];
        delete this.state.work_key_index[packet.work_key];
        const parent = this.state.runs[packet.parent_run_id];
        parent.children = parent.children.filter((child) => child !== waitingRun.run_id);
        const session = this.state.sessions[packet.conductor.session_id];
        const principal = {
          schema_version: "limen.conduct_principal.v1",
          principal_id: waitingRun.conductor_principal_id,
          agent: session.identity.agent,
          surface: session.identity.surface,
          roles: ["conductor"],
        };
        try {
          const promoted = await this.submit(packet, principal);
          if (promoted.status === "busy") {
            this.state = original;
            continue;
          }
        } catch {
          this.state = original;
          continue;
        }
        this.recordEvent("fanout.run_promoted", { run_id: waitingRun.run_id });
        progress = true;
      }
    }
    const root = this.state.runs[rootRunId];
    if (!root || root.packet?.intent?.kind !== "fanout-root") return;
    const children = root.children.map((runId) => this.state.runs[runId]);
    if (!children.length || children.some((child) =>
      ["waiting", "reserved", "running", "stop_requested"].includes(child.status))) return;
    const outcome = children.every((child) => child.status === "succeeded") ? "succeeded" : "blocked";
    root.status = outcome;
    root.updated_at = this.timestamp;
    root.receipts = [{
      schema_version: "limen.fanout_campaign_receipt.v1",
      receipt_id: `campaign-${rootRunId}`,
      run_id: rootRunId,
      outcome,
      child_runs: [...root.children],
      mutation_authorized: true,
      accepted_at: this.timestamp,
    }];
    this.recordEvent("fanout.campaign_settled", { run_id: rootRunId, outcome });
  }

  harvest(runId) {
    const graph = this.graph(runId);
    const byStatus = {};
    let receiptCount = 0;
    for (const node of graph.nodes) {
      byStatus[node.status] = (byStatus[node.status] || 0) + 1;
      receiptCount += node.receipts.length;
    }
    return {
      schema_version: "limen.conduct_harvest.v1",
      root_run_id: graph.root_run_id,
      run_count: graph.nodes.length,
      receipt_count: receiptCount,
      by_status: Object.fromEntries(Object.entries(byStatus).sort(([left], [right]) => left.localeCompare(right))),
      unharvested: graph.nodes
        .filter((node) => node.status === "waiting" || ACTIVE_RUN_STATES.has(node.status))
        .map((node) => node.run_id),
      nodes: graph.nodes,
    };
  }

  adopt(runId, adopterSessionId, requestedPrincipal = null) {
    const run = this.state.runs[runId];
    const adopter = this.state.sessions[adopterSessionId];
    if (!run || !adopter) throw new ConductError("run or adopter session not found", 404);
    const { principal, enforced } = this.principalForIdentity(adopter.identity, requestedPrincipal);
    this.requireRole(principal, "conductor");
    if (this.state.session_principals[adopterSessionId] !== principal.principal_id) {
      throw new ConductError("adopter session is not bound to the authenticated principal", 403);
    }
    if (enforced && run.conductor_principal_id !== principal.principal_id) {
      throw new ConductError("only the owning conductor principal may recover a run", 403);
    }
    const priorSession = this.state.sessions[run.conductor_session_id];
    if (priorSession) {
      if (priorSession.human_protected) throw new ConductError("protected human session cannot be adopted");
      if (this.now - asDate(priorSession.heartbeat_at) <= this.adoptionAfterMs) {
        throw new ConductError("conductor absence has not been proven");
      }
    }
    if (this.now - asDate(adopter.heartbeat_at) > this.sessionTtlMs || !adopter.accepting_work) {
      throw new ConductError("adopter is not a healthy accepting session");
    }
    const prior = run.conductor_session_id;
    run.conductor_session_id = adopterSessionId;
    run.conductor_principal_id = principal.principal_id;
    run.updated_at = this.timestamp;
    this.recordEvent("run.adopted", {
      run_id: runId,
      prior_session_id: prior,
      adopter_session_id: adopterSessionId,
    });
    return { status: "adopted", run_id: runId, conductor_session_id: adopterSessionId };
  }

  cancel(runId, requesterSessionId, requestedPrincipal = null) {
    const run = this.state.runs[runId];
    if (!run) throw new ConductError(`unknown run: ${runId}`, 404);
    const requester = this.state.sessions[requesterSessionId];
    if (!requester) throw new ConductError("requester session is not registered");
    const { principal, enforced } = this.principalForIdentity(requester.identity, requestedPrincipal);
    this.requireRole(principal, "conductor");
    if (run.conductor_session_id !== requesterSessionId) {
      throw new ConductError("only the current conductor may cancel a reservation");
    }
    if (this.state.session_principals[requesterSessionId] !== principal.principal_id) {
      throw new ConductError("requester session is not bound to the authenticated principal", 403);
    }
    if (enforced && run.conductor_principal_id !== principal.principal_id) {
      throw new ConductError("only the owning conductor principal may cancel a reservation", 403);
    }
    if (this.state.sessions[requesterSessionId]?.human_protected) {
      throw new ConductError("protected human session cannot be cancelled or signalled through autonomous conduct");
    }
    if (run.status !== "reserved") throw new ConductError("only reserved, not-started work may be cancelled");
    const lease = this.state.leases[run.lease_id];
    lease.state = "released";
    lease.heartbeat_at = this.timestamp;
    run.status = "cancelled";
    run.updated_at = this.timestamp;
    this.recordEvent("run.cancelled", { run_id: runId, requester_session_id: requesterSessionId });
    this.taskEvent(run, lease, {
      kind: "task.cancelled",
      status: "open",
      fromStatuses: ["dispatched"],
      budgetAction: "refund",
      suffix: "cancelled",
      output: `Conduct reservation ${runId} cancelled before execution`,
    });
    return { status: "cancelled", run_id: runId };
  }

  requestStop(runId, requesterSessionId, requestedPrincipal = null) {
    const run = this.state.runs[runId];
    if (!run) throw new ConductError(`unknown run: ${runId}`, 404);
    const requester = this.state.sessions[requesterSessionId];
    if (!requester) throw new ConductError("requester session is not registered");
    const { principal, enforced } = this.principalForIdentity(requester.identity, requestedPrincipal);
    this.requireRole(principal, "conductor");
    if (run.conductor_session_id !== requesterSessionId) {
      throw new ConductError("only the current conductor may request stop");
    }
    if (this.state.session_principals[requesterSessionId] !== principal.principal_id) {
      throw new ConductError("requester session is not bound to the authenticated principal", 403);
    }
    if (enforced && run.conductor_principal_id !== principal.principal_id) {
      throw new ConductError("only the owning conductor principal may request stop", 403);
    }
    if (this.state.sessions[requesterSessionId]?.human_protected) {
      throw new ConductError("protected human session cannot be cancelled or signalled through autonomous conduct");
    }
    if (!["running", "reserved"].includes(run.status)) {
      throw new ConductError("terminal work cannot receive a stop request");
    }
    run.status = "stop_requested";
    run.updated_at = this.timestamp;
    this.recordEvent("run.stop_requested", { run_id: runId, requester_session_id: requesterSessionId });
    return { status: "stop_requested", run_id: runId, cooperative: true };
  }

  validateLineage(packet, principalId = null) {
    if (packet.parent_run_id === null) return null;
    const parent = this.state.runs[packet.parent_run_id];
    if (!parent) throw new ConductError(`parent run not found: ${packet.parent_run_id}`, 404);
    const parentPacket = parent.packet;
    if (!["reserved", "running"].includes(parent.status)) {
      throw new ConductError("terminal or stopping work cannot create children");
    }
    if (![parent.conductor_session_id, parent.executor_session_id].includes(packet.conductor.session_id)) {
      throw new ConductError("only the parent conductor or executor may submit a child");
    }
    if (
      principalId !== null
      && (
        parent.conductor_session_id !== packet.conductor.session_id
        || parent.conductor_principal_id !== principalId
      )
    ) {
      throw new ConductError("only the owning conductor principal may submit a child", 403);
    }
    if (!identitiesEqual(packet.initiator, parentPacket.initiator)) {
      throw new ConductError("child initiator must preserve the root initiator identity");
    }
    if (!parentPacket.authority.may_delegate) throw new ConductError("parent authority does not permit delegation");
    if (packet.depth !== parentPacket.depth + 1 || packet.depth > parentPacket.fanout.max_depth) {
      throw new ConductError("child depth exceeds the parent fanout envelope");
    }
    if (parent.children.length >= parentPacket.fanout.max_children) {
      throw new ConductError("parent fanout limit is exhausted");
    }
    if (!authorityAttenuates(packet.authority, parentPacket.authority)) {
      throw new ConductError("child authority does not attenuate the parent");
    }
    if (packet.spend.limit > parentPacket.spend.limit || packet.spend.reserve > parentPacket.spend.reserve) {
      throw new ConductError("child spend does not attenuate the parent");
    }
    const childReservedSpend = parent.children.reduce(
      (total, childId) => total + this.state.runs[childId].packet.spend.limit,
      0,
    );
    if (childReservedSpend + packet.spend.limit > parentPacket.spend.limit - parentPacket.spend.reserve) {
      throw new ConductError("aggregate child spend exceeds the parent envelope");
    }
    if (packet.spend.unit !== parentPacket.spend.unit) {
      throw new ConductError("child spend unit does not match the parent");
    }
    if (
      packet.retry.max_attempts > parentPacket.retry.max_attempts
      || (parentPacket.retry.transient_only && !packet.retry.transient_only)
    ) {
      throw new ConductError("child retry policy does not attenuate the parent");
    }
    if (asDate(packet.deadline) > asDate(parentPacket.deadline)) {
      throw new ConductError("child deadline does not attenuate the parent");
    }
    if (
      packet.fanout.max_children > parentPacket.fanout.max_children
      || packet.fanout.max_depth > parentPacket.fanout.max_depth
    ) {
      throw new ConductError("child fanout does not attenuate the parent");
    }
    const ancestry = new Set();
    let cursor = parent;
    while (cursor) {
      ancestry.add(cursor.packet.work_key);
      cursor = cursor.parent_run_id ? this.state.runs[cursor.parent_run_id] : null;
    }
    if (ancestry.has(packet.work_key)) throw new ConductError("repeated ancestry work_key/cycle rejected");
    return parent;
  }

  selectExecutor(packet, {
    excludeSessions = new Set(),
    ignoreRequiredSession = false,
  } = {}) {
    if (isTaskCompatibilityPacket(packet)) {
      return {
        session_id: "tabularius-conduct-keeper",
        identity: {
          schema_version: "limen.agent_identity.v1",
          agent: "tabularius",
          surface: "durable-object",
          session_id: "tabularius-conduct-keeper",
          native_run_id: null,
          provider_identity: "tabularius",
        },
      };
    }
    const load = this.activeLoad();
    const requiredSessionId = ignoreRequiredSession
      ? ""
      : String(packet.execution?.executor_session_id || "");
    const candidates = Object.values(this.state.sessions).filter((session) => {
      if (excludeSessions.has(session.session_id)) return false;
      if (requiredSessionId && session.session_id !== requiredSessionId) return false;
      if (!session.accepting_work || this.now - asDate(session.heartbeat_at) > this.sessionTtlMs) return false;
      if (session.quota_remaining === 0) return false;
      if (packet.required_capabilities.some((capability) => !session.capabilities.includes(capability))) return false;
      if (packet.execution?.local_heavy_allowed === false
          && (session.capabilities.includes("local-heavy")
            || session.capabilities.includes("local-worktree"))) return false;
      if (session.human_protected && session.session_id !== packet.conductor.session_id) return false;
      return (load[session.session_id] || 0) < session.concurrency;
    });
    if (!candidates.length) {
      const suffix = requiredSessionId ? ` for executor session ${requiredSessionId}` : "";
      throw new ConductError(`no healthy native lane satisfies the packet capabilities and bounds${suffix}`);
    }
    candidates.sort((left, right) => {
      const leftPreferred = packet.preferred_agent && left.identity.agent === packet.preferred_agent ? 0 : 1;
      const rightPreferred = packet.preferred_agent && right.identity.agent === packet.preferred_agent ? 0 : 1;
      return leftPreferred - rightPreferred
        || Number(right.receipt_quality || 0) - Number(left.receipt_quality || 0)
        || Number(left.cost_per_run ?? Number.POSITIVE_INFINITY)
          - Number(right.cost_per_run ?? Number.POSITIVE_INFINITY)
        || (load[left.session_id] || 0) / left.concurrency - (load[right.session_id] || 0) / right.concurrency
        || left.identity.agent.localeCompare(right.identity.agent)
        || left.session_id.localeCompare(right.session_id);
    });
    return candidates[0];
  }

  effectiveClaims(packet) {
    const claims = [];
    const alwaysExclusive = new Set([
      "task",
      "pr-write",
      "branch",
      "worktree",
      "repo-plumbing",
      "base-integrate",
      "agy-scratch",
      "external",
      "repo-write",
    ]);
    for (const rawClaim of packet.resource_claims) {
      if (!["shared", "exclusive"].includes(rawClaim.mode)) {
        throw new ConductError(`unsupported resource claim mode: ${rawClaim.mode}`);
      }
      const resource = parseResource(rawClaim.key);
      const mode = alwaysExclusive.has(resource.kind)
        || (["write", "external"].includes(packet.effect) && resource.kind !== "pr-review")
        ? "exclusive"
        : rawClaim.mode;
      claims.push({
        schema_version: "limen.resource_claim.v1",
        key: rawClaim.key,
        mode,
      });
      if (resource.repo && !coveredAtoms([resource.repo], packet.authority.repositories)) {
        throw new ConductError(`resource repository ${resource.repo} exceeds packet authority`);
      }
      if (
        resource.kind === "path"
        && resource.prefix
        && !coveredPaths([resource.prefix.replace(/^\/+/, "")], packet.authority.path_prefixes)
      ) {
        throw new ConductError("path resource exceeds packet path authority");
      }
      if (
        resource.kind === "external"
        && (
          packet.effect !== "external"
          || !coveredAtoms([resource.identity[0]], packet.authority.external_effects)
        )
      ) {
        throw new ConductError("external resource requires matching external effect authority");
      }
    }
    const codeWriteScopeKinds = new Set(["branch", "path", "base-integrate", "repo-write"]);
    const hasCodeWriteScope = claims.some((claim) =>
      codeWriteScopeKinds.has(parseResource(claim.key).kind));
    if (packet.effect === "write" && !hasCodeWriteScope) {
      const repositories = [...packet.authority.repositories].sort();
      if (!repositories.length || repositories.includes("*")) {
        claims.push({ schema_version: "limen.resource_claim.v1", key: "repo/*/*/write", mode: "exclusive" });
      } else {
        for (const repo of repositories) {
          claims.push({ schema_version: "limen.resource_claim.v1", key: `repo/${repo}/write`, mode: "exclusive" });
        }
      }
    }
    if (packet.task_id) {
      claims.push({ schema_version: "limen.resource_claim.v1", key: `task/${packet.task_id}`, mode: "exclusive" });
    }
    if (packet.effect === "external") {
      for (const effect of [...packet.authority.external_effects].sort()) {
        claims.push({ schema_version: "limen.resource_claim.v1", key: `external/${effect}`, mode: "exclusive" });
      }
    }
    return sortedClaims(claims);
  }

  activeLoad() {
    const load = {};
    for (const lease of Object.values(this.state.leases)) {
      if (!ACTIVE_LEASE_STATES.has(lease.state) || asDate(lease.hard_deadline) <= this.now) continue;
      const run = this.state.runs[lease.run_id];
      if (run) load[run.executor_session_id] = (load[run.executor_session_id] || 0) + 1;
    }
    return load;
  }

  async expireLeases() {
    const rootsToAdvance = new Set();
    for (const lease of Object.values(this.state.leases)) {
      if (!ACTIVE_LEASE_STATES.has(lease.state) || asDate(lease.hard_deadline) > this.now) continue;
      lease.state = "expired";
      lease.heartbeat_at = this.timestamp;
      const run = this.state.runs[lease.run_id];
      if (run && ACTIVE_RUN_STATES.has(run.status)) {
        run.status = "expired";
        run.updated_at = this.timestamp;
        if (run.packet?.intent?.kind === "fanout-leaf") {
          run.receipts = [{
            schema_version: "limen.fanout_expiry_receipt.v1",
            receipt_id: `expiry-${run.run_id}`,
            run_id: run.run_id,
            outcome: "blocked",
            expected_heads: clone(lease.observed_heads || {}),
            observed_heads: {},
            reason: "executor lease expired without a timely authenticated heartbeat",
            mutation_authorized: true,
            accepted_at: this.timestamp,
          }];
          rootsToAdvance.add(run.root_run_id);
        }
      }
      this.recordEvent("lease.expired", { lease_id: lease.lease_id, run_id: lease.run_id });
      if (run) {
        this.taskEvent(run, lease, {
          kind: "task.expired",
          status: "failed",
          fromStatuses: ["dispatched", "in_progress"],
          suffix: "expired",
          output: `Conduct lease ${lease.lease_id} reached its hard deadline`,
        });
      }
    }
    for (const rootRunId of rootsToAdvance) await this.advanceFanoutGraph(rootRunId);
  }

  async authorizedLease(
    leaseId,
    capabilityToken,
    generation = null,
    requestedPrincipal = null,
    allowTerminal = false,
  ) {
    const lease = this.state.leases[leaseId];
    if (!lease) throw new ConductError(`unknown lease: ${leaseId}`, 404);
    const { principal, enforced } = this.principalForIdentity(lease.executor, requestedPrincipal);
    this.requireRole(principal, "executor", "compatibility");
    if (generation !== null && Number(generation) !== lease.generation) {
      throw new ConductError("lease generation does not match the request");
    }
    if (enforced && lease.executor_principal_id !== principal.principal_id) {
      throw new ConductError("lease belongs to another executor principal", 403);
    }
    const actual = await sha256Text(String(capabilityToken || ""));
    if (!constantTimeTextEqual(lease.capability_token_hash, actual)) {
      throw new ConductError("invalid lease capability token");
    }
    if (!allowTerminal && !ACTIVE_LEASE_STATES.has(lease.state)) {
      throw new ConductError(`lease is not active: ${lease.state}`);
    }
    return lease;
  }

  submitResult(run, duplicate) {
    return {
      schema_version: "limen.conduct_submit_result.v1",
      status: duplicate ? "duplicate" : (run.compatibility_projection ? "applied" : "reserved"),
      run_id: run.run_id,
      root_run_id: run.root_run_id,
      executor_session_id: run.executor_session_id,
      lease: this.publicLease(this.state.leases[run.lease_id]),
    };
  }

  publicLease(lease) {
    const visible = clone(lease);
    delete visible.capability_token_hash;
    delete visible.executor_principal_id;
    return visible;
  }
}

export class MemoryConductStore {
  constructor(state = emptyConductState()) {
    this.state = clone(state);
    this.saveCount = 0;
  }

  async load() {
    return clone(this.state);
  }

  async save(state) {
    this.state = clone(state);
    this.saveCount += 1;
  }

  snapshot() {
    return clone(this.state);
  }
}

export class DurableConductStore {
  constructor(storage) {
    this.storage = storage;
  }

  async load() {
    return (await this.storage.get("conduct_state")) || emptyConductState();
  }

  async save(state) {
    await this.storage.put("conduct_state", state);
  }
}

export class SerializedConductService {
  constructor(
    store,
    {
      projectTaskEvent = async () => {},
      clock = () => new Date(),
      sessionTtlMs,
      adoptionAfterMs,
      leaseTtlMs,
      capabilitySecret = "development-only-capability-secret",
    } = {},
  ) {
    this.store = store;
    this.projectTaskEvent = projectTaskEvent;
    this.clock = clock;
    this.options = {
      sessionTtlMs,
      adoptionAfterMs,
      leaseTtlMs,
      capabilitySecret,
    };
    this.tail = Promise.resolve();
  }

  call(operation, payload = {}) {
    const execute = async () => {
      let state = await this.store.load();
      const options = Object.fromEntries(Object.entries(this.options).filter(([, value]) => value !== undefined));
      const now = this.clock();
      if ([
        "submit",
        "submit_graph",
        "split",
        "claim",
        "heartbeat",
        "report",
        "adopt",
        "cancel",
        "request_stop",
      ].includes(operation)) {
        const preflight = new ConductKernel(state, { ...options, now });
        await preflight.expireLeases();
        if (preflight.mutated) {
          for (const event of preflight.projectionEvents) await this.projectTaskEvent(event);
          await this.store.save(preflight.state);
          state = preflight.state;
        }
      }
      const kernel = new ConductKernel(state, { ...options, now });
      const result = await kernel.execute(operation, payload);
      const projectionReceipts = [];
      for (const event of kernel.projectionEvents) {
        projectionReceipts.push(await this.projectTaskEvent(event));
      }
      if (projectionReceipts.length && result && typeof result === "object") {
        result.projection_receipts = projectionReceipts;
        const run = kernel.state.runs[result.run_id];
        if (run) run.projection_receipts = clone(projectionReceipts);
      } else if (result?.run_id) {
        const stored = kernel.state.runs[result.run_id]?.projection_receipts || [];
        if (stored.length) result.projection_receipts = clone(stored);
      }
      if (kernel.mutated) await this.store.save(kernel.state);
      return result;
    };
    const current = this.tail.then(execute, execute);
    this.tail = current.then(() => undefined, () => undefined);
    return current;
  }
}
