import assert from "node:assert/strict";
import test from "node:test";

import rfc8785Vectors from "../../../spec/contracts/conduct/rfc8785-vectors.json" with { type: "json" };
import { authorizeConductRequest } from "../src/conduct/auth.js";
import {
  ConductKeeperDurableObject,
} from "../src/conduct/durable-object.js";
import {
  MemoryConductStore,
  SerializedConductService,
} from "../src/conduct/keeper.js";
import {
  applyTaskCompatibilityEvent,
  applyTaskPacketProjectionEvent,
  commitTaskCompatibilityEvent,
  readInlineProjectionForTest,
} from "../src/conduct/projection.js";
import {
  canonicalHash,
  stableStringify,
  validateExecutorAttempt,
  validateReceipt,
  validateSession,
  validateWorkPacket,
} from "../src/conduct/schemas.js";

const NOW = new Date("2026-07-18T15:00:00.000Z");

function identity(agent, sessionId = `${agent}-session`) {
  return {
    schema_version: "limen.agent_identity.v1",
    agent,
    surface: "cli",
    session_id: sessionId,
    native_run_id: null,
    provider_identity: null,
  };
}

function session(agent, {
  sessionId = `${agent}-session`,
  capabilities = ["code", "review", "conduct"],
  concurrency = 8,
  heartbeatAt = NOW,
  protectedSession = false,
  worktree = null,
} = {}) {
  const ident = identity(agent, sessionId);
  return validateSession({
    session_id: sessionId,
    identity: ident,
    origin: protectedSession ? "direct" : "dispatched",
    capabilities,
    concurrency,
    worktree,
    registered_at: heartbeatAt.toISOString(),
    heartbeat_at: heartbeatAt.toISOString(),
    human_protected: protectedSession,
  }, heartbeatAt);
}

async function packet({
  workId,
  conductor,
  resource = "task/T-1",
  workKey = workId,
  initiator = conductor,
  parentRunId = null,
  rootRunId = null,
  depth = 0,
  maxChildren = 3,
  maxDepth = 3,
  preferredAgent = null,
  claims = null,
  authority = null,
  taskId = null,
  effect = "write",
  spendUnit = "runs",
  spendLimit = 4,
  spendReserve = 0,
  maxAttempts = 2,
  transientOnly = true,
  deadline = new Date(NOW.getTime() + 60 * 60 * 1000),
} = {}) {
  return validateWorkPacket({
    root_run_id: rootRunId,
    parent_run_id: parentRunId,
    work_id: workId,
    work_key: workKey,
    intent: { objective: workId },
    execution: { command: "pytest -q", observed_heads: { pr: "abc123" } },
    initiator,
    conductor,
    preferred_agent: preferredAgent,
    required_capabilities: ["code"],
    resource_claims: claims || [{ key: resource, mode: "exclusive" }],
    predicate: "pytest -q",
    receipt_target: `github:organvm/limen:pull-request:${workId}`,
    authority: authority || {
      actions: ["code", "review"],
      repositories: ["organvm/limen"],
      path_prefixes: ["cli"],
      external_effects: [],
      may_delegate: true,
    },
    deadline: deadline.toISOString(),
    spend: { unit: spendUnit, limit: spendLimit, reserve: spendReserve },
    retry: { max_attempts: maxAttempts, transient_only: transientOnly },
    depth,
    fanout: { max_children: maxChildren, max_depth: maxDepth },
    effect,
    task_id: taskId,
  });
}

async function taskPacket({
  workId,
  conductor,
  intent,
  taskId = intent.task_id,
  deadline = new Date(NOW.getTime() + 60 * 60 * 1000),
} = {}) {
  return validateWorkPacket({
    work_id: workId,
    work_key: workId,
    intent,
    execution: {
      adapter: "tabularius",
      projection: "tasks.yaml",
      observed_heads: {},
    },
    initiator: conductor,
    conductor,
    preferred_agent: "tabularius",
    required_capabilities: ["board-write"],
    resource_claims: [{ key: `task/${taskId}`, mode: "exclusive" }],
    predicate: `test -n "${taskId}"`,
    receipt_target: `git:organvm/limen:tasks.yaml#${taskId}`,
    authority: {
      actions: [intent.kind],
      repositories: ["organvm/limen"],
      path_prefixes: ["tasks.yaml"],
      external_effects: [],
      may_delegate: false,
    },
    deadline: deadline.toISOString(),
    spend: { unit: "runs", limit: 0, reserve: 0 },
    retry: { max_attempts: 1, transient_only: true },
    fanout: { max_children: 0, max_depth: 0 },
    effect: "write",
    task_id: taskId,
  });
}

function serviceWith(sessions, options = {}) {
  const store = options.store || new MemoryConductStore();
  const service = new SerializedConductService(store, {
    clock: options.clock || (() => NOW),
    projectTaskEvent: options.projectTaskEvent,
    capabilitySecret: options.capabilitySecret,
  });
  return Promise.all(sessions.map((item) => service.call("register", { session: item })))
    .then(() => ({ service, store }));
}

async function leaseCapability(service, reserved, principal = null) {
  const claim = await service.call("claim", {
    lease_id: reserved.lease.lease_id,
    generation: reserved.lease.generation,
    ...(principal ? { principal } : {}),
  });
  return claim.capability_token;
}

function principalRegistry(...principals) {
  return JSON.stringify({
    schema_version: "limen.conduct_principal_registry.v1",
    principals,
  });
}

function principalMeta(principalId, agent, roles) {
  return {
    schema_version: "limen.conduct_principal.v1",
    principal_id: principalId,
    agent,
    surface: "cloud",
    roles,
  };
}

test("conduct auth fails closed without a principal registry and derives identity from its secret", async () => {
  const request = (token) => new Request("https://limen.example/api/conduct/capabilities", {
    headers: token ? { authorization: `Bearer ${token}` } : {},
  });
  assert.deepEqual(await authorizeConductRequest(request("secret"), {}), {
    ok: false,
    status: 503,
    detail: "conduct principal registry is not configured",
  });
  assert.equal((await authorizeConductRequest(request("owner"), {
    LIMEN_API_TOKEN: "owner",
  })).ok, false);
  const registry = principalRegistry({
    principal_id: "codex-cloud",
    agent: "codex",
    surface: "cloud",
    roles: ["observer", "conductor", "executor"],
    bearer: "conduct-secret-at-least-24-characters",
  });
  const auth = await authorizeConductRequest(request("conduct-secret-at-least-24-characters"), {
    LIMEN_CONDUCT_PRINCIPAL_REGISTRY: registry,
  });
  assert.equal(auth.ok, true);
  assert.equal(auth.principal.principal_id, "codex-cloud");
  assert.equal("bearer" in auth.principal, false);
});

test("principal-bound executor claims are recoverable and secret from conductors", async () => {
  const store = new MemoryConductStore();
  const service = new SerializedConductService(store, {
    clock: () => NOW,
    capabilitySecret: "worker-principal-capability-secret",
  });
  const conductorPrincipal = principalMeta(
    "principal-conductor",
    "codex",
    ["observer", "conductor"],
  );
  const executorPrincipal = principalMeta(
    "principal-executor",
    "claude",
    ["observer", "executor"],
  );
  const attackerPrincipal = principalMeta(
    "principal-attacker",
    "opencode",
    ["observer", "executor"],
  );
  const conductor = await service.call("register", {
    session: session("spoofed", { sessionId: "principal-conductor-session" }),
    principal: conductorPrincipal,
  });
  await service.call("register", {
    session: session("spoofed", {
      sessionId: "principal-executor-session",
      capabilities: ["code"],
    }),
    principal: executorPrincipal,
  });
  assert.equal(conductor.identity.agent, "codex");
  const reserved = await service.call("submit", {
    packet: await packet({
      workId: "principal-bound-worker",
      conductor: conductor.identity,
      preferredAgent: "claude",
    }),
    principal: conductorPrincipal,
  });
  assert.equal("capability_token" in reserved, false);
  assert.equal("capability_token_hash" in reserved.lease, false);
  await assert.rejects(service.call("claim", {
    lease_id: reserved.lease.lease_id,
    generation: reserved.lease.generation,
    principal: attackerPrincipal,
  }), /another executor principal/);
  const first = await service.call("claim", {
    lease_id: reserved.lease.lease_id,
    generation: reserved.lease.generation,
    principal: executorPrincipal,
  });
  const second = await service.call("claim", {
    lease_id: reserved.lease.lease_id,
    generation: reserved.lease.generation,
    principal: executorPrincipal,
  });
  assert.equal(first.capability_token, second.capability_token);
});

test("executor attempts are capability-bound, durable, idempotent, and token-free", async () => {
  const codex = session("codex");
  const { service } = await serviceWith([codex], {
    capabilitySecret: "worker-attempt-capability-secret",
  });
  const reserved = await service.call("submit", {
    packet: await packet({
      workId: "attempt-bound-worker",
      conductor: codex.identity,
    }),
  });
  const capabilityToken = await leaseCapability(service, reserved);
  const launching = validateExecutorAttempt({
    attempt_id: "attempt-bound-worker-1",
    run_id: reserved.run_id,
    lease_id: reserved.lease.lease_id,
    lease_generation: reserved.lease.generation,
    executor: codex.identity,
    adapter: "fixture-remote",
    status: "launching",
    submitted_at: NOW.toISOString(),
    updated_at: NOW.toISOString(),
  }, NOW);
  const created = await service.call("heartbeat", {
    lease_id: reserved.lease.lease_id,
    capability_token: capabilityToken,
    generation: reserved.lease.generation,
    observed_heads: { pr: "abc123" },
    attempt: launching,
  });
  assert.equal(created.attempt_created, true);
  const submitted = validateExecutorAttempt({
    ...launching,
    provider_run_id: "provider-run-1",
    provider_run_url: "https://executor.example/runs/1",
    status: "submitted",
  }, NOW);
  const updated = await service.call("heartbeat", {
    lease_id: reserved.lease.lease_id,
    capability_token: capabilityToken,
    generation: reserved.lease.generation,
    observed_heads: { pr: "abc123" },
    attempt: submitted,
  });
  assert.equal(updated.attempt_created, false);
  const graph = await service.call("graph", { run_id: reserved.run_id });
  assert.deepEqual(graph.nodes[0].attempts, [submitted]);
  assert.equal("capability_token" in graph.nodes[0], false);
  assert.equal("capability_token_hash" in graph.nodes[0].lease, false);
  await assert.rejects(service.call("heartbeat", {
    lease_id: reserved.lease.lease_id,
    capability_token: capabilityToken,
    generation: reserved.lease.generation,
    observed_heads: { pr: "abc123" },
    attempt: { ...submitted, provider_run_id: "provider-run-2" },
  }), /provider receipt identity changed/);
});

test("executor attempt limits are keeper-enforced", async () => {
  const codex = session("codex");
  const { service } = await serviceWith([codex]);
  const reserved = await service.call("submit", {
    packet: await packet({ workId: "attempt-limit", conductor: codex.identity }),
  });
  const capabilityToken = await leaseCapability(service, reserved);
  for (const number of [1, 2]) {
    await service.call("heartbeat", {
      lease_id: reserved.lease.lease_id,
      capability_token: capabilityToken,
      generation: reserved.lease.generation,
      observed_heads: { pr: "abc123" },
      attempt: validateExecutorAttempt({
        attempt_id: `attempt-limit-${number}`,
        run_id: reserved.run_id,
        lease_id: reserved.lease.lease_id,
        lease_generation: reserved.lease.generation,
        executor: codex.identity,
        adapter: `fixture-${number}`,
        status: "failed",
        submitted_at: NOW.toISOString(),
        updated_at: NOW.toISOString(),
      }, NOW),
    });
  }
  await assert.rejects(service.call("heartbeat", {
    lease_id: reserved.lease.lease_id,
    capability_token: capabilityToken,
    generation: reserved.lease.generation,
    observed_heads: { pr: "abc123" },
    attempt: validateExecutorAttempt({
      attempt_id: "attempt-limit-3",
      run_id: reserved.run_id,
      lease_id: reserved.lease.lease_id,
      lease_generation: reserved.lease.generation,
      executor: codex.identity,
      adapter: "fixture-3",
      status: "failed",
      submitted_at: NOW.toISOString(),
      updated_at: NOW.toISOString(),
    }, NOW),
  }), /attempt limit exhausted/);
});

test("transient attempts reroute to a separately authenticated executor", async () => {
  const service = new SerializedConductService(new MemoryConductStore(), {
    clock: () => NOW,
    capabilitySecret: "worker-reroute-capability-secret",
  });
  const conductorPrincipal = principalMeta(
    "reroute-conductor",
    "codex",
    ["observer", "conductor"],
  );
  const firstPrincipal = principalMeta(
    "reroute-first",
    "claude",
    ["observer", "executor"],
  );
  const secondPrincipal = principalMeta(
    "reroute-second",
    "jules",
    ["observer", "executor"],
  );
  const conductor = await service.call("register", {
    session: session("spoofed", {
      sessionId: "reroute-conductor-session",
      capabilities: ["conduct"],
    }),
    principal: conductorPrincipal,
  });
  await service.call("register", {
    session: session("spoofed", {
      sessionId: "reroute-first-session",
      capabilities: ["code"],
    }),
    principal: firstPrincipal,
  });
  await service.call("register", {
    session: session("spoofed", {
      sessionId: "reroute-second-session",
      capabilities: ["code"],
    }),
    principal: secondPrincipal,
  });
  const reserved = await service.call("submit", {
    packet: await packet({
      workId: "attempt-reroute-worker",
      conductor: conductor.identity,
      preferredAgent: "claude",
    }),
    principal: conductorPrincipal,
  });
  const oldClaim = await service.call("claim", {
    lease_id: reserved.lease.lease_id,
    generation: reserved.lease.generation,
    principal: firstPrincipal,
  });
  const failed = validateExecutorAttempt({
    attempt_id: "attempt-reroute-worker-1",
    run_id: reserved.run_id,
    lease_id: reserved.lease.lease_id,
    lease_generation: reserved.lease.generation,
    executor: reserved.lease.executor,
    adapter: "fixture-first",
    status: "failed",
    failure_class: "transient",
    submitted_at: NOW.toISOString(),
    updated_at: NOW.toISOString(),
  }, NOW);
  const rerouted = await service.call("heartbeat", {
    lease_id: reserved.lease.lease_id,
    capability_token: oldClaim.capability_token,
    generation: reserved.lease.generation,
    principal: firstPrincipal,
    observed_heads: { pr: "abc123" },
    attempt: failed,
  });
  assert.equal(rerouted.status, "rerouted");
  assert.equal(rerouted.lease.executor.agent, "jules");
  assert.ok(rerouted.lease.generation > reserved.lease.generation);
  await assert.rejects(service.call("claim", {
    lease_id: rerouted.lease.lease_id,
    generation: rerouted.lease.generation,
    principal: firstPrincipal,
  }), /another executor principal/);
  await service.call("claim", {
    lease_id: rerouted.lease.lease_id,
    generation: rerouted.lease.generation,
    principal: secondPrincipal,
  });
  const graph = await service.call("graph", { run_id: reserved.run_id });
  assert.deepEqual(graph.nodes[0].attempts, [failed]);
  assert.equal("capability_token_hash" in graph.nodes[0].lease, false);
});

test("spend limits and permanent failure classifications stop retries", async () => {
  const codex = session("codex");
  const { service } = await serviceWith([codex]);
  const reserved = await service.call("submit", {
    packet: await packet({
      workId: "attempt-spend-worker",
      conductor: codex.identity,
      spendLimit: 1,
      maxAttempts: 2,
      transientOnly: true,
    }),
  });
  const capabilityToken = await leaseCapability(service, reserved);
  const failed = validateExecutorAttempt({
    attempt_id: "attempt-spend-worker-1",
    run_id: reserved.run_id,
    lease_id: reserved.lease.lease_id,
    lease_generation: reserved.lease.generation,
    executor: reserved.lease.executor,
    adapter: "fixture",
    status: "failed",
    failure_class: "permanent",
    submitted_at: NOW.toISOString(),
    updated_at: NOW.toISOString(),
  }, NOW);
  const heartbeat = await service.call("heartbeat", {
    lease_id: reserved.lease.lease_id,
    capability_token: capabilityToken,
    generation: reserved.lease.generation,
    observed_heads: { pr: "abc123" },
    attempt: failed,
  });
  assert.equal(heartbeat.status, "active");
  await assert.rejects(service.call("heartbeat", {
    lease_id: reserved.lease.lease_id,
    capability_token: capabilityToken,
    generation: reserved.lease.generation,
    observed_heads: { pr: "abc123" },
    attempt: validateExecutorAttempt({
      ...failed,
      attempt_id: "attempt-spend-worker-2",
    }, NOW),
  }), /spend limit exhausted/);
});

test("atomic graph submission rolls back partial reservations and is idempotent", async () => {
  const codex = session("codex", { concurrency: 8 });
  const { service, store } = await serviceWith([codex]);
  const root = await packet({
    workId: "atomic-root",
    conductor: codex.identity,
    resource: "task/atomic-root",
    effect: "read",
    spendLimit: 4,
  });
  const rootRunId = `run-${(await canonicalHash({
    work_id: root.work_id,
    intent_hash: root.intent_hash,
    execution_hash: root.execution_hash,
  })).slice(0, 32)}`;
  const childOne = await packet({
    workId: "atomic-child-one",
    conductor: codex.identity,
    resource: "task/atomic-child-one",
    effect: "read",
    parentRunId: rootRunId,
    rootRunId,
    depth: 1,
    spendLimit: 1,
  });
  const childTwo = await packet({
    workId: "atomic-child-two",
    conductor: codex.identity,
    resource: "task/atomic-child-two",
    effect: "read",
    parentRunId: rootRunId,
    rootRunId,
    depth: 1,
    spendLimit: 1,
  });
  const submitted = await service.call("submit_graph", {
    packets: [root, childOne, childTwo],
  });
  assert.equal(submitted.status, "reserved");
  assert.equal((await service.call("graph", { run_id: rootRunId })).nodes.length, 3);
  const duplicate = await service.call("submit_graph", {
    packets: [root, childOne, childTwo],
  });
  assert.deepEqual(duplicate.runs.map((run) => run.status), ["duplicate", "duplicate", "duplicate"]);

  const rollbackRoot = await packet({
    workId: "rollback-root",
    conductor: codex.identity,
    resource: "task/rollback-root",
    effect: "read",
  });
  const rollbackRootId = `run-${(await canonicalHash({
    work_id: rollbackRoot.work_id,
    intent_hash: rollbackRoot.intent_hash,
    execution_hash: rollbackRoot.execution_hash,
  })).slice(0, 32)}`;
  const rollbackChild = await packet({
    workId: "rollback-child",
    conductor: codex.identity,
    resource: "task/atomic-child-one",
    effect: "read",
    parentRunId: rollbackRootId,
    rootRunId: rollbackRootId,
    depth: 1,
    spendLimit: 1,
  });
  const before = store.snapshot();
  const busy = await service.call("submit_graph", {
    packets: [rollbackRoot, rollbackChild],
  });
  assert.equal(busy.status, "busy");
  assert.deepEqual(store.snapshot(), before);
});

test("fanout graph serializes dependency claims and settles its keeper root", async () => {
  const codex = session("codex", { concurrency: 3 });
  const { service, store } = await serviceWith([codex]);
  const rootTemplate = await packet({
    workId: "fanout-root",
    conductor: codex.identity,
    resource: "task/fanout-root",
    effect: "read",
    spendLimit: 2,
  });
  const root = await validateWorkPacket({
    ...rootTemplate,
    intent: { kind: "fanout-root" },
    execution: { adapter: "fanout-keeper" },
    intent_hash: "",
    execution_hash: "",
  });
  const rootRunId = `run-${(await canonicalHash({
    work_id: root.work_id,
    intent_hash: root.intent_hash,
    execution_hash: root.execution_hash,
  })).slice(0, 32)}`;
  const first = await packet({
    workId: "fanout-first",
    conductor: codex.identity,
    resource: "task/fanout-shared",
    parentRunId: rootRunId,
    rootRunId,
    depth: 1,
    spendLimit: 1,
  });
  const secondTemplate = await packet({
    workId: "fanout-second",
    conductor: codex.identity,
    resource: "task/fanout-shared",
    parentRunId: rootRunId,
    rootRunId,
    depth: 1,
    spendLimit: 1,
  });
  const second = await validateWorkPacket({
    ...secondTemplate,
    execution: {
      ...secondTemplate.execution,
      dependencies: ["fanout-first"],
    },
    execution_hash: "",
  });
  const submitted = await service.call("submit_graph", { packets: [root, first, second] });
  assert.deepEqual(submitted.runs.map((run) => run.status), ["reserved", "reserved", "waiting"]);
  const repeat = await service.call("submit_graph", { packets: [root, first, second] });
  assert.deepEqual(repeat.runs.map((run) => run.status), ["duplicate", "duplicate", "duplicate"]);

  const reportLeaf = async (workId) => {
    const graph = await service.call("graph", { run_id: rootRunId });
    const node = graph.nodes.find((candidate) => candidate.packet.work_id === workId);
    const lease = store.snapshot().leases[node.lease_id];
    const token = await leaseCapability(service, { lease });
    return service.call("report", {
      lease_id: lease.lease_id,
      capability_token: token,
      generation: lease.generation,
      receipt: validateReceipt({
        receipt_id: `receipt-${workId}`,
        run_id: node.run_id,
        lease_id: lease.lease_id,
        lease_generation: lease.generation,
        executor: codex.identity,
        observed_heads_before: { pr: "abc123" },
        predicate: { command: "pytest -q", exit_code: 0 },
        spend: { runs: 1 },
        child_runs: [],
        outcome: "succeeded",
      }, NOW),
    });
  };
  await reportLeaf("fanout-first");
  assert.equal(
    (await service.call("graph", { run_id: rootRunId }))
      .nodes.find((node) => node.packet.work_id === "fanout-second").status,
    "reserved",
  );
  await reportLeaf("fanout-second");
  const terminal = await service.call("harvest", { run_id: rootRunId });
  assert.deepEqual(terminal.by_status, { succeeded: 3 });
  assert.deepEqual(terminal.unharvested, []);
  assert.equal(terminal.receipt_count, 3);
});

test("registration timestamps are server-owned while protection and healthy worktree ownership are sticky", async () => {
  const store = new MemoryConductStore();
  const service = new SerializedConductService(store, { clock: () => NOW });
  const staleHeartbeat = new Date(NOW.getTime() - 60 * 60 * 1000);
  const protectedLane = session("codex", {
    sessionId: "sticky-session",
    heartbeatAt: staleHeartbeat,
    protectedSession: true,
    worktree: "/tmp/mesh/../mesh",
  });
  const registered = await service.call("register", { session: protectedLane });
  assert.equal(registered.registered_at, NOW.toISOString());
  assert.equal(registered.heartbeat_at, NOW.toISOString());
  assert.equal(registered.human_protected, true);

  const downgrade = session("codex", {
    sessionId: "sticky-session",
    heartbeatAt: new Date(NOW.getTime() + 60 * 60 * 1000),
    worktree: "/tmp/mesh",
  });
  const refreshed = await service.call("register", { session: downgrade });
  assert.equal(refreshed.registered_at, NOW.toISOString());
  assert.equal(refreshed.heartbeat_at, NOW.toISOString());
  assert.equal(refreshed.human_protected, true);

  await assert.rejects(
    service.call("register", {
      session: session("claude", {
        sessionId: "worktree-thief",
        worktree: "/tmp/mesh/.",
      }),
    }),
    /worktree is already owned by healthy session sticky-session/,
  );
});

test("only healthy registered conductors with the adapter-specific capability may submit", async () => {
  const ordinary = session("codex", {
    sessionId: "ordinary-no-conduct",
    capabilities: ["code"],
  });
  const taskOnly = session("claude", {
    sessionId: "task-submit-only",
    capabilities: ["task-submit"],
  });
  const store = new MemoryConductStore();
  const { service } = await serviceWith([ordinary, taskOnly], { store });

  await assert.rejects(
    service.call("submit", {
      packet: await packet({
        workId: "unregistered-conductor",
        conductor: identity("agy", "missing-session"),
      }),
    }),
    /registered session/,
  );
  await assert.rejects(
    service.call("submit", {
      packet: await packet({
        workId: "ordinary-capability",
        conductor: ordinary.identity,
      }),
    }),
    /lacks required conduct capability/,
  );
  await assert.rejects(
    service.call("submit", {
      packet: await packet({
        workId: "task-capability-on-code",
        conductor: taskOnly.identity,
      }),
    }),
    /lacks required conduct capability/,
  );

  const taskIntent = {
    kind: "task.upsert",
    task_id: "TASK-CAPABILITY",
    expected_absent: true,
    task: {
      id: "TASK-CAPABILITY",
      title: "Capability",
      target_agent: "codex",
      priority: "high",
      budget_cost: 0,
      status: "open",
      created: "2026-07-18",
      dispatch_log: [],
    },
  };
  await assert.rejects(
    service.call("submit", {
      packet: await taskPacket({
        workId: "task-packet-no-capability",
        conductor: ordinary.identity,
        intent: taskIntent,
      }),
    }),
    /lacks required task-submit capability/,
  );

  const stale = store.snapshot();
  stale.sessions[taskOnly.session_id].heartbeat_at =
    new Date(NOW.getTime() - 60 * 60 * 1000).toISOString();
  await store.save(stale);
  await assert.rejects(
    service.call("submit", {
      packet: await taskPacket({
        workId: "task-packet-stale-conductor",
        conductor: taskOnly.identity,
        intent: taskIntent,
      }),
    }),
    /session is not healthy/,
  );
});

test("work ids and deterministic work keys share one idempotency index", async () => {
  const codex = session("codex");
  const { service, store } = await serviceWith([codex]);
  const original = await packet({
    workId: "work-index-original",
    workKey: "stable-work-key",
    conductor: codex.identity,
  });
  const first = await service.call("submit", { packet: original });
  const alias = await validateWorkPacket({
    ...original,
    work_id: "work-index-alias",
  });
  const duplicate = await service.call("submit", { packet: alias });
  assert.equal(duplicate.status, "duplicate");
  assert.equal(duplicate.run_id, first.run_id);
  assert.equal(store.snapshot().work_index["work-index-alias"], first.run_id);
  assert.equal(store.snapshot().work_key_index["stable-work-key"], first.run_id);
  assert.equal(Object.keys(store.snapshot().leases).length, 1);

  await assert.rejects(
    service.call("submit", {
      packet: await packet({
        workId: "work-index-conflict",
        workKey: "stable-work-key",
        conductor: codex.identity,
      }),
    }),
    /reused with different immutable hashes or contract/,
  );
  await assert.rejects(
    service.call("submit", {
      packet: await validateWorkPacket({
        ...original,
        work_key: "different-work-key",
      }),
    }),
    /reused with different immutable hashes or contract/,
  );
});

test("fifty conductor submissions serialize to one task lease and deterministic busy receipts", async () => {
  const sessions = Array.from({ length: 50 }, (_, index) =>
    session(`lane${index}`, { sessionId: `session${index}`, concurrency: 100 }));
  const { service, store } = await serviceWith(sessions);
  const packets = await Promise.all(sessions.map((item, index) => packet({
    workId: `race-${index}`,
    conductor: item.identity,
    resource: "task/SAME",
    preferredAgent: item.identity.agent,
  })));
  const results = await Promise.all(packets.map((item) => service.call("submit", { packet: item })));
  assert.equal(results.filter((result) => result.status === "reserved").length, 1);
  assert.equal(results.filter((result) => result.status === "busy").length, 49);
  assert.equal(new Set(results.filter((result) => result.status === "busy").map((result) => result.busy_receipt_id)).size, 49);
  const snapshot = store.snapshot();
  assert.equal(Object.keys(snapshot.leases).length, 1);
  assert.equal(snapshot.events.filter((event) => event.kind === "run.reserved").length, 1);
});

test("PR writers contend across task ids while independent review leases coexist", async () => {
  const codex = session("codex");
  const claude = session("claude");
  const copilot = session("copilot");
  const { service } = await serviceWith([codex, claude, copilot]);
  const writer = await service.call("submit", { packet: await packet({
    workId: "writer-one",
    conductor: codex.identity,
    resource: "pr/organvm/limen/77/write@abc",
    preferredAgent: "codex",
  }) });
  assert.equal(writer.status, "reserved");
  const second = await service.call("submit", { packet: await packet({
    workId: "writer-two",
    conductor: claude.identity,
    resource: "pr/organvm/limen/77/write@abc",
    preferredAgent: "claude",
  }) });
  assert.equal(second.status, "busy");
  const review = await service.call("submit", { packet: await packet({
    workId: "review-one",
    conductor: copilot.identity,
    resource: "pr/organvm/limen/77/review/copilot@abc",
    preferredAgent: "copilot",
    effect: "read",
  }) });
  assert.equal(review.status, "reserved");
});

test("same-provider exact-head reviews serialize even when mislabeled shared", async () => {
  const codex = session("codex");
  const claude = session("claude");
  const { service } = await serviceWith([codex, claude]);
  const reviewClaim = [{
    key: "pr/organvm/limen/77/review/copilot@abc",
    mode: "shared",
  }];
  assert.equal((await service.call("submit", { packet: await packet({
    workId: "shared-review-one",
    conductor: codex.identity,
    claims: reviewClaim,
    effect: "read",
  }) })).status, "reserved");
  assert.equal((await service.call("submit", { packet: await packet({
    workId: "shared-review-two",
    conductor: claude.identity,
    claims: reviewClaim,
    effect: "read",
  }) })).status, "busy");
});

test("disjoint paths run together, overlapping prefixes serialize, and five native identities survive", async () => {
  const names = ["codex", "claude", "copilot", "agy", "opencode"];
  const sessions = names.map((name) => session(name, { concurrency: 1 }));
  const { service } = await serviceWith(sessions);
  const results = [];
  for (const item of sessions) {
    results.push(await service.call("submit", { packet: await packet({
      workId: `matrix-${item.identity.agent}`,
      conductor: item.identity,
      resource: `path/organvm/repo-${item.identity.agent}/main/src`,
      preferredAgent: item.identity.agent,
      authority: {
        actions: ["code"],
        repositories: [`organvm/repo-${item.identity.agent}`],
        path_prefixes: ["src"],
        external_effects: [],
      },
    }) }));
  }
  assert.deepEqual(results.map((result) => result.status), Array(5).fill("reserved"));
  assert.deepEqual(new Set(results.map((result) => result.lease.executor.agent)), new Set(names));

  const overlapSessions = [session("red", { sessionId: "red" }), session("blue", { sessionId: "blue" })];
  const overlap = await serviceWith(overlapSessions);
  assert.equal((await overlap.service.call("submit", { packet: await packet({
    workId: "path-root",
    conductor: overlapSessions[0].identity,
    resource: "path/organvm/limen/main/cli",
  }) })).status, "reserved");
  assert.equal((await overlap.service.call("submit", { packet: await packet({
    workId: "path-child",
    conductor: overlapSessions[1].identity,
    resource: "path/organvm/limen/main/cli/src",
  }) })).status, "busy");
  assert.equal((await overlap.service.call("submit", { packet: await packet({
    workId: "path-peer",
    conductor: overlapSessions[1].identity,
    resource: "path/organvm/limen/main/web",
    authority: {
      actions: ["code"],
      repositories: ["organvm/limen"],
      path_prefixes: ["web"],
      external_effects: [],
    },
  }) })).status, "reserved");
});

test("authority attenuation and ancestry cycle checks gate child work", async () => {
  const codex = session("codex", { concurrency: 4 });
  const { service } = await serviceWith([codex]);
  const root = await service.call("submit", { packet: await packet({
    workId: "root",
    workKey: "root-key",
    conductor: codex.identity,
    resource: "path/organvm/limen/main/cli/root",
    maxChildren: 2,
    maxDepth: 2,
  }) });
  const child = await packet({
    workId: "child",
    workKey: "child-key",
    conductor: codex.identity,
    resource: "path/organvm/limen/main/cli/src",
    parentRunId: root.run_id,
    rootRunId: root.run_id,
    depth: 1,
    maxChildren: 2,
    maxDepth: 2,
    authority: {
      actions: ["code"],
      repositories: ["organvm/limen"],
      path_prefixes: ["cli/src"],
      external_effects: [],
      may_delegate: false,
    },
  });
  assert.equal((await service.call("split", { parent_run_id: root.run_id, packet: child })).status, "reserved");
  await assert.rejects(
    service.call("split", {
      parent_run_id: root.run_id,
      packet: await packet({
        workId: "cycle",
        workKey: "root-key",
        conductor: codex.identity,
        resource: "path/organvm/limen/main/cli/cycle",
        parentRunId: root.run_id,
        rootRunId: root.run_id,
        depth: 1,
        maxChildren: 2,
        maxDepth: 2,
        spendLimit: 0,
      }),
    }),
    /cycle/,
  );
});

test("lineage preserves owners and initiators while attenuating every bounded envelope", async () => {
  const codex = session("codex");
  const claude = session("claude");
  const agy = session("agy");
  const { service } = await serviceWith([codex, claude, agy]);
  const parentDeadline = new Date(NOW.getTime() + 60 * 60 * 1000);
  const parent = await service.call("submit", {
    packet: await packet({
      workId: "lineage-parent",
      conductor: codex.identity,
      preferredAgent: "codex",
      resource: "path/organvm/limen/main/cli/lineage-parent",
      maxChildren: 2,
      maxDepth: 2,
      spendLimit: 6,
      spendReserve: 2,
      maxAttempts: 3,
      transientOnly: true,
      deadline: parentDeadline,
    }),
  });
  const child = (workId, overrides = {}) => packet({
    workId,
    conductor: codex.identity,
    initiator: codex.identity,
    resource: `path/organvm/limen/main/cli/${workId}`,
    parentRunId: parent.run_id,
    rootRunId: parent.run_id,
    depth: 1,
    maxChildren: 2,
    maxDepth: 2,
    spendLimit: 1,
    spendReserve: 0,
    maxAttempts: 2,
    transientOnly: true,
    deadline: parentDeadline,
    ...overrides,
  });

  await assert.rejects(
    service.call("split", {
      parent_run_id: parent.run_id,
      packet: await child("wrong-lineage-owner", {
        conductor: agy.identity,
        initiator: codex.identity,
      }),
    }),
    /only the parent conductor or executor/,
  );
  await assert.rejects(
    service.call("split", {
      parent_run_id: parent.run_id,
      packet: await child("wrong-root-initiator", {
        initiator: claude.identity,
      }),
    }),
    /preserve the root initiator/,
  );
  await assert.rejects(
    service.call("split", {
      parent_run_id: parent.run_id,
      packet: await child("late-child", {
        deadline: new Date(parentDeadline.getTime() + 1),
      }),
    }),
    /deadline does not attenuate/,
  );
  await assert.rejects(
    service.call("split", {
      parent_run_id: parent.run_id,
      packet: await child("wrong-spend-unit", {
        spendUnit: "tokens",
      }),
    }),
    /spend unit does not match/,
  );
  await assert.rejects(
    service.call("split", {
      parent_run_id: parent.run_id,
      packet: await child("non-transient-retries", {
        transientOnly: false,
      }),
    }),
    /retry policy does not attenuate/,
  );
  await assert.rejects(
    service.call("split", {
      parent_run_id: parent.run_id,
      packet: await child("wider-fanout", {
        maxChildren: 3,
      }),
    }),
    /fanout does not attenuate/,
  );

  assert.equal((await service.call("split", {
    parent_run_id: parent.run_id,
    packet: await child("aggregate-child-one", { spendLimit: 2 }),
  })).status, "reserved");
  await assert.rejects(
    service.call("split", {
      parent_run_id: parent.run_id,
      packet: await child("aggregate-child-two", { spendLimit: 3 }),
    }),
    /aggregate child spend exceeds/,
  );

  const terminalParent = await service.call("submit", {
    packet: await packet({
      workId: "terminal-parent",
      conductor: codex.identity,
      preferredAgent: "codex",
      resource: "path/organvm/limen/main/cli/terminal-parent",
      maxChildren: 1,
      maxDepth: 1,
    }),
  });
  await service.call("request_stop", {
    run_id: terminalParent.run_id,
    session_id: codex.session_id,
  });
  await assert.rejects(
    service.call("split", {
      parent_run_id: terminalParent.run_id,
      packet: await packet({
        workId: "terminal-child",
        conductor: codex.identity,
        resource: "path/organvm/limen/main/cli/terminal-child",
        parentRunId: terminalParent.run_id,
        rootRunId: terminalParent.run_id,
        depth: 1,
        maxChildren: 1,
        maxDepth: 1,
      }),
    }),
    /terminal or stopping work cannot create children/,
  );
});

test("canonical hashes, packet deadlines, and conservative unknown write scope fail closed", async () => {
  const codex = session("codex");
  const { service } = await serviceWith([codex]);
  const original = await packet({ workId: "hash-check", conductor: codex.identity });
  await assert.rejects(
    validateWorkPacket({ ...original, intent: { objective: "changed" } }),
    /intent_hash does not match/,
  );
  await assert.rejects(
    service.call("submit", { packet: await packet({
      workId: "already-late",
      conductor: codex.identity,
      deadline: new Date(NOW.getTime() - 1),
    }) }),
    /deadline has already passed/,
  );
  const first = await service.call("submit", { packet: await packet({
    workId: "unknown-scope-one",
    conductor: codex.identity,
    resource: "task/ONE",
  }) });
  assert.equal(first.status, "reserved");
  const second = await service.call("submit", { packet: await packet({
    workId: "unknown-scope-two",
    conductor: codex.identity,
    resource: "task/TWO",
  }) });
  assert.equal(second.status, "busy");
  assert.ok(second.conflicts[0].keys.some(([left, right]) =>
    left === "repo/organvm/limen/write" && right === "repo/organvm/limen/write"));
});

test("resource claims enforce legal modes and repository, path, and external authority", async () => {
  const codex = session("codex");
  const { service } = await serviceWith([codex]);
  const invalidMode = await packet({
    workId: "invalid-claim-mode",
    conductor: codex.identity,
    effect: "read",
  });
  invalidMode.resource_claims[0].mode = "optimistic";
  await assert.rejects(
    service.call("submit", { packet: invalidMode }),
    /unsupported resource claim mode/,
  );

  await assert.rejects(
    service.call("submit", {
      packet: await packet({
        workId: "repository-authority-escape",
        conductor: codex.identity,
        resource: "branch/other/repository/main",
      }),
    }),
    /resource repository other\/repository exceeds packet authority/,
  );
  await assert.rejects(
    service.call("submit", {
      packet: await packet({
        workId: "path-authority-escape",
        conductor: codex.identity,
        resource: "path/organvm/limen/main/web/private",
      }),
    }),
    /path resource exceeds packet path authority/,
  );
  await assert.rejects(
    service.call("submit", {
      packet: await packet({
        workId: "external-without-effect",
        conductor: codex.identity,
        resource: "external/deploy",
      }),
    }),
    /external resource requires matching external effect authority/,
  );
  await assert.rejects(
    service.call("submit", {
      packet: await packet({
        workId: "external-authority-escape",
        conductor: codex.identity,
        resource: "external/deploy",
        effect: "external",
        authority: {
          actions: ["code"],
          repositories: ["organvm/limen"],
          path_prefixes: ["cli"],
          external_effects: ["publish"],
        },
      }),
    }),
    /external resource requires matching external effect authority/,
  );

  const ancillary = await service.call("submit", {
    packet: await packet({
      workId: "ancillary-locks-need-repository-scope",
      conductor: codex.identity,
      claims: [
        { key: "worktree//tmp/limen-mesh", mode: "shared" },
        { key: "repo-common-dir/ORGANVM/LIMEN/plumbing", mode: "shared" },
      ],
    }),
  });
  const ancillaryClaims = Object.fromEntries(
    ancillary.lease.resources.map((claim) => [claim.key, claim.mode]),
  );
  assert.equal(ancillaryClaims["repo/organvm/limen/write"], "exclusive");
  assert.equal(ancillaryClaims["repo-common-dir/organvm/limen/plumbing"], "exclusive");
  assert.equal(ancillaryClaims["worktree//tmp/limen-mesh"], "exclusive");

  const sharedTask = await service.call("submit", {
    packet: await packet({
      workId: "shared-task-is-still-exclusive",
      conductor: codex.identity,
      claims: [{ key: "task/EXCLUSIVE", mode: "shared" }],
      effect: "read",
    }),
  });
  assert.equal(
    sharedTask.lease.resources.find((claim) => claim.key === "task/EXCLUSIVE").mode,
    "exclusive",
  );
});

test("RFC 8785 canonical hashes match the cross-runtime Unicode and integral-float fixture", async () => {
  assert.ok(rfc8785Vectors.vectors.length >= 2);
  for (const vector of rfc8785Vectors.vectors) {
    assert.equal(stableStringify(vector.value), vector.canonical);
    assert.equal(await canonicalHash(vector.value), vector.sha256);
  }
});

test("moved heads fence leases and late receipts remain evidence only", async () => {
  const codex = session("codex");
  const { service } = await serviceWith([codex]);
  const reserved = await service.call("submit", { packet: await packet({
    workId: "head-fence",
    conductor: codex.identity,
  }) });
  const token = await leaseCapability(service, reserved);
  const fenced = await service.call("heartbeat", {
    lease_id: reserved.lease.lease_id,
    capability_token: token,
    generation: reserved.lease.generation,
    observed_heads: { pr: "moved" },
  });
  assert.equal(fenced.status, "fenced");
  const receipt = validateReceipt({
    receipt_id: "receipt-head-fence",
    run_id: reserved.run_id,
    lease_id: reserved.lease.lease_id,
    lease_generation: reserved.lease.generation,
    executor: codex.identity,
    observed_heads_before: { pr: "abc123" },
    predicate: { command: "pytest -q", exit_code: 0 },
    outcome: "succeeded",
  }, NOW);
  const report = await service.call("report", {
    lease_id: reserved.lease.lease_id,
    capability_token: token,
    generation: reserved.lease.generation,
    receipt,
  });
  assert.equal(report.mutation_authorized, false);
  assert.equal(report.run_status, "fenced");
});

test("heartbeat fences an executor that omits any leased observed head", async () => {
  const codex = session("codex");
  const { service } = await serviceWith([codex]);
  const reserved = await service.call("submit", {
    packet: await packet({
      workId: "omitted-head-fence",
      conductor: codex.identity,
    }),
  });
  const token = await leaseCapability(service, reserved);
  const fenced = await service.call("heartbeat", {
    lease_id: reserved.lease.lease_id,
    capability_token: token,
    generation: reserved.lease.generation,
    observed_heads: {},
  });
  assert.equal(fenced.status, "fenced");
  assert.equal(fenced.reason, "required observed head omitted for pr");
});

test("receipts authorize mutation only with exact predicates, scoped paths, bounded spend, and exact children", async () => {
  const codex = session("codex");
  const { service } = await serviceWith([codex]);
  const reserved = await service.call("submit", {
    packet: await packet({
      workId: "receipt-contract",
      conductor: codex.identity,
      resource: "path/organvm/limen/main/cli/receipt-contract",
      spendLimit: 4,
    }),
  });
  const token = await leaseCapability(service, reserved);
  await service.call("heartbeat", {
    lease_id: reserved.lease.lease_id,
    capability_token: token,
    generation: reserved.lease.generation,
    observed_heads: { pr: "abc123" },
  });
  const report = async (receiptId, overrides = {}) => service.call("report", {
    lease_id: reserved.lease.lease_id,
    capability_token: token,
    generation: reserved.lease.generation,
    receipt: validateReceipt({
      receipt_id: receiptId,
      run_id: reserved.run_id,
      lease_id: reserved.lease.lease_id,
      lease_generation: reserved.lease.generation,
      executor: codex.identity,
      observed_heads_before: { pr: "abc123" },
      changed_paths: ["cli/receipt.js"],
      predicate: { command: "pytest -q", exit_code: 0 },
      spend: { runs: 1 },
      child_runs: [],
      outcome: "succeeded",
      ...overrides,
    }, NOW),
  });

  assert.equal((await report("receipt-wrong-command", {
    predicate: { command: "npm test", exit_code: 0 },
  })).mutation_authorized, false);
  assert.equal((await report("receipt-nonzero-success", {
    predicate: { command: "pytest -q", exit_code: 1 },
  })).mutation_authorized, false);
  assert.equal((await report("receipt-path-escape", {
    changed_paths: ["web/worker.js"],
  })).mutation_authorized, false);
  assert.equal((await report("receipt-spend-string", {
    spend: { runs: "1" },
  })).mutation_authorized, false);
  assert.equal((await report("receipt-spend-overrun", {
    spend: { runs: 5 },
  })).mutation_authorized, false);
  assert.equal((await report("receipt-forged-child", {
    child_runs: ["run-forged-child"],
  })).mutation_authorized, false);
  assert.equal((await report("receipt-contract-valid")).mutation_authorized, true);
});

test("read receipts cannot change paths or observed heads", async () => {
  const codex = session("codex");
  const { service } = await serviceWith([codex]);
  const reserved = await service.call("submit", {
    packet: await packet({
      workId: "read-no-mutation",
      conductor: codex.identity,
      effect: "read",
    }),
  });
  const token = await leaseCapability(service, reserved);
  const result = await service.call("report", {
    lease_id: reserved.lease.lease_id,
    capability_token: token,
    generation: reserved.lease.generation,
    receipt: validateReceipt({
      receipt_id: "receipt-read-mutated",
      run_id: reserved.run_id,
      lease_id: reserved.lease.lease_id,
      lease_generation: reserved.lease.generation,
      executor: codex.identity,
      observed_heads_before: { pr: "abc123" },
      observed_heads_after: { pr: "different" },
      changed_paths: ["cli/changed.js"],
      predicate: { command: "pytest -q", exit_code: 0 },
      spend: { runs: 1 },
      outcome: "succeeded",
    }, NOW),
  });
  assert.equal(result.mutation_authorized, false);
});

test("heartbeat, cooperative stop, report idempotency, cancel, and hard deadlines are serialized", async () => {
  const codex = session("codex", { concurrency: 4 });
  let clock = new Date(NOW);
  const store = new MemoryConductStore();
  const service = new SerializedConductService(store, {
    clock: () => clock,
    leaseTtlMs: 1000,
  });
  await service.call("register", { session: codex });
  const running = await service.call("submit", { packet: await packet({
    workId: "lifecycle-run",
    conductor: codex.identity,
    resource: "path/organvm/limen/main/cli/lifecycle",
  }) });
  const runningToken = await leaseCapability(service, running);
  assert.equal((await service.call("heartbeat", {
    lease_id: running.lease.lease_id,
    capability_token: runningToken,
    generation: running.lease.generation,
    observed_heads: { pr: "abc123" },
  })).status, "active");
  assert.equal((await service.call("request_stop", {
    run_id: running.run_id,
    session_id: codex.session_id,
  })).cooperative, true);
  const receipt = validateReceipt({
    receipt_id: "receipt-lifecycle",
    run_id: running.run_id,
    lease_id: running.lease.lease_id,
    lease_generation: running.lease.generation,
    executor: codex.identity,
    observed_heads_before: { pr: "abc123" },
    predicate: { command: "pytest -q", exit_code: 0 },
    outcome: "succeeded",
  }, NOW);
  const reportPayload = {
    lease_id: running.lease.lease_id,
    capability_token: runningToken,
    generation: running.lease.generation,
    receipt,
  };
  assert.equal((await service.call("report", reportPayload)).mutation_authorized, true);
  assert.equal((await service.call("report", reportPayload)).mutation_authorized, true);
  assert.equal(store.snapshot().runs[running.run_id].receipts.length, 1);

  const cancellable = await service.call("submit", { packet: await packet({
    workId: "cancel-lifecycle",
    conductor: codex.identity,
    resource: "path/organvm/limen/main/cli/cancel",
  }) });
  assert.equal((await service.call("cancel", {
    run_id: cancellable.run_id,
    session_id: codex.session_id,
  })).status, "cancelled");

  const expiring = await service.call("submit", { packet: await packet({
    workId: "expire-lifecycle",
    conductor: codex.identity,
    resource: "path/organvm/limen/main/cli/expire",
  }) });
  const expiringToken = await leaseCapability(service, expiring);
  clock = new Date(NOW.getTime() + 2000);
  await assert.rejects(service.call("heartbeat", {
    lease_id: expiring.lease.lease_id,
    capability_token: expiringToken,
    generation: expiring.lease.generation,
    observed_heads: {},
  }), /lease is not active: expired/);
  assert.equal(store.snapshot().leases[expiring.lease.lease_id].state, "expired");
});

test("dead conductors are adoptable without cancelling children; protected humans are not signal targets", async () => {
  const codex = session("codex", { concurrency: 4 });
  const claude = session("claude", { concurrency: 4 });
  const { service, store } = await serviceWith([codex, claude]);
  const parent = await service.call("submit", { packet: await packet({
    workId: "adopt-parent",
    conductor: codex.identity,
    resource: "path/organvm/limen/main/cli/adopt-parent",
  }) });
  const child = await service.call("submit", { packet: await packet({
    workId: "adopt-child",
    conductor: codex.identity,
    resource: "path/organvm/limen/main/cli/adopt-child",
    parentRunId: parent.run_id,
    rootRunId: parent.run_id,
    depth: 1,
  }) });
  const stale = store.snapshot();
  stale.sessions[codex.session_id].heartbeat_at = new Date(NOW.getTime() - 60 * 60 * 1000).toISOString();
  await store.save(stale);
  assert.equal((await service.call("adopt", {
    run_id: parent.run_id,
    session_id: claude.session_id,
  })).status, "adopted");
  const graph = await service.call("graph", { run_id: parent.run_id });
  assert.equal(graph.nodes.find((node) => node.run_id === child.run_id).status, "reserved");

  const human = session("codex", {
    sessionId: "human-session",
    concurrency: 2,
    protectedSession: true,
  });
  const protectedLane = await serviceWith([human, claude]);
  const protectedRun = await protectedLane.service.call("submit", { packet: await packet({
    workId: "protected-run",
    conductor: human.identity,
    resource: "path/organvm/limen/main/protected",
    preferredAgent: "codex",
    authority: {
      actions: ["code"],
      repositories: ["organvm/limen"],
      path_prefixes: ["protected"],
      external_effects: [],
    },
  }) });
  await assert.rejects(protectedLane.service.call("request_stop", {
    run_id: protectedRun.run_id,
    session_id: human.session_id,
  }), /protected human session/);
  const protectedState = protectedLane.store.snapshot();
  protectedState.sessions[human.session_id].heartbeat_at = new Date(NOW.getTime() - 60 * 60 * 1000).toISOString();
  await protectedLane.store.save(protectedState);
  await assert.rejects(protectedLane.service.call("adopt", {
    run_id: protectedRun.run_id,
    session_id: claude.session_id,
  }), /protected human session/);
});

test("a restarted service reconstructs graph and lease state from durable storage", async () => {
  const opencode = session("opencode");
  const store = new MemoryConductStore();
  const first = await serviceWith([opencode], { store });
  const work = await packet({ workId: "restart-work", conductor: opencode.identity });
  const reserved = await first.service.call("submit", { packet: work });
  const restarted = new SerializedConductService(store, { clock: () => NOW });
  const duplicate = await restarted.call("submit", { packet: work });
  assert.equal(duplicate.status, "duplicate");
  assert.equal(duplicate.run_id, reserved.run_id);
  const graph = await restarted.call("graph", { run_id: reserved.run_id });
  assert.equal(graph.nodes[0].lease_id, reserved.lease.lease_id);
});

test("projection failure prevents lease state from being acknowledged or committed", async () => {
  const codex = session("codex");
  const failure = new Error("projection unavailable");
  const { service, store } = await serviceWith([codex], {
    projectTaskEvent: async () => { throw failure; },
  });
  await assert.rejects(
    service.call("submit", { packet: await packet({
      workId: "project-me",
      conductor: codex.identity,
      taskId: "TASK-1",
    }) }),
    /projection unavailable/,
  );
  assert.equal(Object.keys(store.snapshot().leases).length, 0);
});

test("task compatibility events are idempotent and update budget exactly once", () => {
  const board = {
    portal: {
      budget: {
        daily: 10,
        per_agent: { codex: 10 },
        track: { spent: 0, per_agent: { codex: 0 } },
      },
    },
    tasks: [{
      id: "TASK-1",
      status: "open",
      budget_cost: 2,
      dispatch_log: [],
    }],
  };
  const event = {
    event_id: "conduct:run-1:1:reserved",
    kind: "task.dispatched",
    timestamp: NOW.toISOString(),
    task_id: "TASK-1",
    run_id: "run-1",
    lease_id: "lease-1",
    generation: 1,
    agent: "codex",
    session_id: "run-1",
    status: "dispatched",
    from_statuses: ["open"],
    budget_action: "debit",
    output: "reserved",
  };
  const first = applyTaskCompatibilityEvent(board, event);
  const second = applyTaskCompatibilityEvent(first.board, event);
  assert.equal(first.board.portal.budget.track.spent, 2);
  assert.equal(second.board.portal.budget.track.spent, 2);
  assert.equal(second.board.tasks[0].dispatch_log.length, 1);
  assert.equal(second.duplicate, true);
});

test("task-packet projection preserves history and rejects forged server-owned fields", () => {
  const board = {
    portal: { budget: { daily: 10, track: { spent: 0, per_agent: {} } } },
    tasks: [{
      id: "TASK-HISTORY",
      title: "History",
      target_agent: "codex",
      priority: "high",
      budget_cost: 2,
      status: "open",
      created: "2026-07-01",
      dispatch_log: [{
        timestamp: "2026-07-01T00:00:00.000Z",
        agent: "human",
        session_id: "human",
        status: "open",
        output: "original",
      }],
    }],
  };
  const upsert = {
    schema_version: "limen.task_packet_projection_event.v1",
    event_id: "conduct:history:1:compatibility",
    kind: "task.upsert",
    timestamp: NOW.toISOString(),
    task_id: "TASK-HISTORY",
    run_id: "run-history",
    lease_id: "lease-history",
    generation: 1,
    agent: "codex",
    session_id: "codex-session",
    intent: {
      kind: "task.upsert",
      task_id: "TASK-HISTORY",
      task: {
        id: "TASK-HISTORY",
        title: "Updated title",
        target_agent: "codex",
        priority: "high",
        budget_cost: 2,
        status: "open",
        created: "2026-07-18",
        dispatch_log: [{
          timestamp: NOW.toISOString(),
          agent: "attacker",
          session_id: "attacker",
          status: "done",
        }],
      },
    },
  };
  const applied = applyTaskPacketProjectionEvent(board, upsert);
  assert.equal(applied.task.title, "Updated title");
  assert.equal(applied.task.created, "2026-07-01");
  assert.equal(applied.task.dispatch_log.length, 2);
  assert.equal(applied.task.dispatch_log[0].agent, "human");
  assert.equal(applied.task.dispatch_log[1].agent, "codex");
  assert.equal(applied.task.dispatch_log[1].status, "open");

  const forged = structuredClone(upsert);
  forged.event_id = "conduct:history:2:compatibility";
  forged.intent.kind = "task.mutate";
  forged.intent.expected_status = "open";
  forged.intent.patch = {
    updated: "2099-01-01T00:00:00.000Z",
    dispatch_log: [],
  };
  delete forged.intent.task;
  assert.throws(
    () => applyTaskPacketProjectionEvent(applied.board, forged),
    /server-owned or unsupported fields: dispatch_log, updated/,
  );

  const lifecycleBypass = structuredClone(upsert);
  lifecycleBypass.event_id = "conduct:history:3:compatibility";
  lifecycleBypass.intent.task.status = "done";
  assert.throws(
    () => applyTaskPacketProjectionEvent(board, lifecycleBypass),
    /upsert cannot change lifecycle status/,
  );
});

test("task claims derive canonical debit and identity while canonical transitions fence bypasses", () => {
  const board = {
    portal: {
      budget: {
        daily: 10,
        per_agent: { codex: 10, attacker: 10 },
        track: {
          date: "2026-07-17",
          spent: 9,
          per_agent: { codex: 9, attacker: 0 },
        },
      },
    },
    tasks: [{
      id: "TASK-CLAIM",
      title: "Claim",
      target_agent: "codex",
      priority: "high",
      budget_cost: 2,
      status: "open",
      created: "2026-07-01",
      dispatch_log: [],
    }],
  };
  const claim = {
    schema_version: "limen.task_packet_projection_event.v1",
    event_id: "conduct:claim:1:compatibility",
    kind: "task.claim",
    timestamp: NOW.toISOString(),
    task_id: "TASK-CLAIM",
    run_id: "run-claim",
    lease_id: "lease-claim",
    generation: 1,
    agent: "codex",
    session_id: "codex-session",
    intent: {
      kind: "task.claim",
      task_id: "TASK-CLAIM",
      expected_status: "open",
      budget_debit: 99,
      budget_agent: "attacker",
      patch: { status: "dispatched", target_agent: "codex" },
      log: {
        agent: "attacker",
        session_id: "attacker",
        status: "done",
        output: "claimed",
        route_to: "jules",
        provider_run_id: "provider-42",
        remote_state: "queued",
      },
    },
  };
  const first = applyTaskPacketProjectionEvent(board, claim);
  const duplicate = applyTaskPacketProjectionEvent(first.board, claim);
  assert.equal(first.board.portal.budget.track.spent, 2);
  assert.equal(first.board.portal.budget.track.date, "2026-07-18");
  assert.equal(first.board.portal.budget.track.per_agent.codex, 2);
  assert.equal(first.board.portal.budget.track.per_agent.attacker, 0);
  assert.equal(first.task.dispatch_log.at(-1).agent, "codex");
  assert.equal(first.task.dispatch_log.at(-1).session_id, "codex-session");
  assert.equal(first.task.dispatch_log.at(-1).logical_agent, "attacker");
  assert.equal(first.task.dispatch_log.at(-1).logical_session_id, "attacker");
  assert.equal(first.task.dispatch_log.at(-1).status, "dispatched");
  assert.equal(first.task.dispatch_log.at(-1).route_to, "jules");
  assert.equal(first.task.dispatch_log.at(-1).provider_run_id, "provider-42");
  assert.equal(first.task.dispatch_log.at(-1).remote_state, "queued");
  assert.equal(duplicate.board.portal.budget.track.spent, 2);
  assert.equal(duplicate.task.dispatch_log.length, 1);

  const bypass = structuredClone(claim);
  bypass.event_id = "conduct:claim:2:compatibility";
  bypass.intent.kind = "task.status";
  bypass.intent.expected_status = "open";
  bypass.intent.patch = { status: "done" };
  assert.throws(
    () => applyTaskPacketProjectionEvent(board, bypass),
    /cannot transition from open to done/,
  );

  const historicalDone = structuredClone(board);
  historicalDone.tasks[0].dispatch_log.push({
    timestamp: "2026-07-17T00:00:00.000Z",
    agent: "codex",
    session_id: "prior-run",
    status: "done",
    output: "durable terminal receipt",
  });
  const repair = structuredClone(bypass);
  repair.event_id = "conduct:claim:3:compatibility";
  repair.intent.log.lifecycle_repair = "prior-done";
  repair.intent.log.output = "lifecycle guard restored the prior terminal receipt";
  const repaired = applyTaskPacketProjectionEvent(historicalDone, repair);
  assert.equal(repaired.task.status, "done");
  assert.equal(repaired.task.dispatch_log.at(-1).lifecycle_repair, "prior-done");

  const forgedRepairKind = structuredClone(repair);
  forgedRepairKind.event_id = "conduct:claim:4:compatibility";
  forgedRepairKind.intent.kind = "task.mutate";
  assert.throws(
    () => applyTaskPacketProjectionEvent(historicalDone, forgedRepairKind),
    /cannot transition from open to done/,
  );
});

test("exceptional task transitions require exact structured evidence", () => {
  const task = (overrides = {}) => ({
    id: "TASK-REPAIR",
    title: "Repair",
    repo: "organvm/limen",
    target_agent: "codex",
    priority: "high",
    budget_cost: 1,
    status: "open",
    labels: [],
    created: "2026-07-01",
    dispatch_log: [],
    ...overrides,
  });
  const event = (fromStatus, toStatus, log, patch = {}) => ({
    schema_version: "limen.task_packet_projection_event.v1",
    event_id: `conduct:repair:${fromStatus}:${toStatus}:${log.lifecycle_repair}`,
    kind: "task.status",
    timestamp: NOW.toISOString(),
    task_id: "TASK-REPAIR",
    run_id: "run-repair",
    lease_id: "lease-repair",
    generation: 1,
    agent: "tabularius",
    session_id: "keeper-session",
    intent: {
      kind: "task.status",
      task_id: "TASK-REPAIR",
      expected_status: fromStatus,
      patch: { status: toStatus, ...patch },
      log: { status: toStatus, output: "evidence-bound repair", ...log },
    },
  });
  const apply = (baseTask, repairEvent) =>
    applyTaskPacketProjectionEvent({ tasks: [baseTask] }, repairEvent).task;

  const human = event(
    "open",
    "needs_human",
    { lifecycle_repair: "human-gate-reconcile" },
    { labels: ["needs-human"] },
  );
  assert.equal(apply(task(), human).status, "needs_human");
  const forgedHuman = structuredClone(human);
  forgedHuman.event_id += ":forged";
  forgedHuman.intent.patch.labels = [];
  assert.throws(() => apply(task(), forgedHuman), /cannot transition/);

  const fleet = event(
    "open",
    "failed_blocked",
    {
      lifecycle_repair: "fleet-debt-park",
      fleet_debt_source: "dispatch-verify",
      fleet_debt_count: 3,
    },
    { labels: ["chronic-fleet-debt"] },
  );
  assert.equal(apply(task(), fleet).status, "failed_blocked");
  const forgedFleet = structuredClone(fleet);
  forgedFleet.event_id += ":forged";
  forgedFleet.intent.log.fleet_debt_count = 2;
  assert.throws(() => apply(task(), forgedFleet), /cannot transition/);

  const pr = event("dispatched", "done", {
    lifecycle_repair: "pr-observed-terminal",
    pr_observed_state: "merged",
    pr_observed_ref: "organvm/limen#1265",
  });
  assert.equal(apply(task({ status: "dispatched" }), pr).status, "done");

  const routine = event("needs_human", "done", {
    lifecycle_repair: "routine-recovered",
    routine_name: "mesh",
    routine_observed_state: "recovered",
  }, { labels: ["routine-freshness"] });
  assert.equal(
    apply(task({ id: "ASK-routine-mesh", status: "needs_human" }), {
      ...routine,
      task_id: "ASK-routine-mesh",
      intent: { ...routine.intent, task_id: "ASK-routine-mesh" },
    }).status,
    "done",
  );

  const reservation = {
    timestamp: "2026-07-18T00:00:00.000Z",
    agent: "dispatch-async",
    session_id: "keeper-reserve",
    logical_session_id: "async-reserve:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    status: "dispatched",
    execution_contract_hash: "a".repeat(64),
  };
  const provider = event("dispatched", "failed_blocked", {
    lifecycle_repair: "provider-terminal",
    execution_started: true,
    execution_contract_hash: "a".repeat(64),
    execution_reservation_id: reservation.logical_session_id,
    execution_result_kind: "failed_blocked",
  });
  assert.equal(
    apply(task({ status: "dispatched", dispatch_log: [reservation] }), provider).status,
    "failed_blocked",
  );

  const stale = event("dispatched", "failed", {
    lifecycle_repair: "stale-successor-hold",
    liveness_evidence: "dead-process",
    liveness_reservation_id: reservation.logical_session_id,
    liveness_pid: 424242,
    liveness_age_seconds: 10,
  }, { labels: ["workstream:successor-required"] });
  assert.equal(
    apply(task({
      status: "dispatched",
      labels: ["workstream:successor-required"],
      dispatch_log: [reservation],
    }), stale).status,
    "failed",
  );

  const recurrence = event("done", "open", {
    lifecycle_repair: "recurrence-reopen",
    recurrence_source: "main-green",
    recurrence_head_sha: "b".repeat(40),
  }, {
    title: "Restore main at bbbbbbbb",
    labels: ["lifecycle", "ci", "mainred"],
    predicate: `test "${"b".repeat(40)}" = "${"b".repeat(40)}"`,
  });
  assert.equal(
    apply(task({
      id: "HEAL-mainred-organvm-limen",
      status: "done",
      labels: ["lifecycle", "ci", "mainred"],
    }), {
      ...recurrence,
      task_id: "HEAL-mainred-organvm-limen",
      intent: { ...recurrence.intent, task_id: "HEAL-mainred-organvm-limen" },
    }).status,
    "open",
  );

  for (const [field, value] of [
    ["execution_profile", "bad"],
    ["workflow_id", "x"],
    ["landing_terminal", "yes"],
    ["execution_contract_hash", "not-a-sha"],
  ]) {
    const malformed = event("open", "open", { [field]: value });
    malformed.event_id += `:${field}`;
    assert.throws(
      () => apply(task(), malformed),
      new RegExp(field),
    );
  }
});

test("MCP-compatible task packets execute in the keeper without a board-write lane", async () => {
  const env = {
    LIMEN_INLINE_TASKS_YAML: `
portal:
  budget:
    daily: 10
    per_agent:
      codex: 10
    track:
      spent: 0
      per_agent:
        codex: 0
tasks: []
`,
  };
  const submitter = session("codex", {
    sessionId: "mcp-submit",
    capabilities: ["task-submit"],
  });
  const store = new MemoryConductStore();
  const service = new SerializedConductService(store, {
    clock: () => NOW,
    projectTaskEvent: (event) => commitTaskCompatibilityEvent(env, event),
  });
  await service.call("register", { session: submitter });
  const intent = {
    kind: "task.upsert",
    task_id: "TASK-MCP",
    expected_absent: true,
    task: {
      id: "TASK-MCP",
      title: "MCP task",
      target_agent: "codex",
      priority: "high",
      budget_cost: 2,
      status: "open",
      created: "2026-07-18",
      dispatch_log: [],
    },
  };
  const work = await taskPacket({
    workId: "mcp-upsert",
    conductor: submitter.identity,
    intent,
  });
  const applied = await service.call("submit", { packet: work });
  assert.equal(applied.status, "applied");
  assert.equal(applied.lease.executor.agent, "tabularius");
  assert.equal(applied.lease.state, "released");
  assert.equal(applied.projection_receipts[0].task.id, "TASK-MCP");
  assert.equal(store.snapshot().runs[applied.run_id].status, "succeeded");
  assert.equal(readInlineProjectionForTest(env).tasks[0].id, "TASK-MCP");

  const duplicate = await service.call("submit", { packet: work });
  assert.equal(duplicate.status, "duplicate");
  assert.equal(duplicate.projection_receipts[0].task.dispatch_log.length, 1);
  assert.equal(readInlineProjectionForTest(env).tasks[0].dispatch_log.length, 1);
});

test("GitHub projection retries SHA conflicts and always writes the observed SHA", async () => {
  let board = {
    portal: { budget: { daily: 10, per_agent: { codex: 10 }, track: { spent: 0, per_agent: {} } } },
    tasks: [{ id: "TASK-2", status: "open", budget_cost: 1, dispatch_log: [] }],
  };
  let sha = "sha-1";
  let puts = 0;
  const fetchImpl = async (_url, init) => {
    if (init.method === "GET") {
      return new Response(JSON.stringify({
        sha,
        content: btoa(unescape(encodeURIComponent((await import("yaml")).default.stringify(board)))),
      }), { status: 200 });
    }
    puts += 1;
    const payload = JSON.parse(init.body);
    assert.equal(payload.sha, sha);
    if (puts === 1) {
      sha = "sha-2";
      return new Response(JSON.stringify({ message: "sha does not match" }), { status: 409 });
    }
    board = (await import("yaml")).default.parse(decodeURIComponent(escape(atob(payload.content))));
    return new Response(JSON.stringify({ content: { sha: "sha-3" } }), { status: 200 });
  };
  const event = {
    event_id: "conduct:run-2:1:reserved",
    kind: "task.dispatched",
    timestamp: NOW.toISOString(),
    task_id: "TASK-2",
    run_id: "run-2",
    lease_id: "lease-2",
    generation: 1,
    agent: "codex",
    session_id: "run-2",
    status: "dispatched",
    from_statuses: ["open"],
    budget_action: "debit",
    output: "reserved",
  };
  const result = await commitTaskCompatibilityEvent({
    LIMEN_GITHUB_REPO: "organvm/limen",
    LIMEN_GITHUB_TOKEN: "secret",
    LIMEN_GITHUB_BRANCH: "main",
  }, event, { fetchImpl });
  assert.equal(result.status, "committed");
  assert.equal(puts, 2);
  assert.equal(board.tasks[0].status, "dispatched");
});

test("Durable Object HTTP routes match the authenticated client surface and survive recreation", async () => {
  class FakeStorage {
    constructor() { this.values = new Map(); }
    async get(key) { return structuredClone(this.values.get(key)); }
    async put(key, value) { this.values.set(key, structuredClone(value)); }
  }
  const storage = new FakeStorage();
  const bearer = "http-conduct-secret-at-least-24-characters";
  const env = {
    LIMEN_CONDUCT_PRINCIPAL_REGISTRY: principalRegistry({
      principal_id: "codex-http",
      agent: "codex",
      surface: "cli",
      roles: ["observer", "conductor", "executor"],
      bearer,
    }),
    LIMEN_CONDUCT_CAPABILITY_SECRET: "http-capability-secret-at-least-24-characters",
  };
  const request = (path, method = "GET", body = null) => new Request(`https://limen.example${path}`, {
    method,
    headers: {
      authorization: `Bearer ${bearer}`,
      ...(body ? { "content-type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const first = new ConductKeeperDurableObject({ storage }, env);
  const liveNow = new Date();
  const codex = session("codex", { heartbeatAt: liveNow });
  assert.equal((await first.fetch(request("/api/conduct/sessions", "POST", codex))).status, 200);
  const work = await packet({
    workId: "http-work",
    conductor: codex.identity,
    deadline: new Date(liveNow.getTime() + 60 * 60 * 1000),
  });
  const reservedResponse = await first.fetch(request("/api/conduct/runs", "POST", work));
  assert.equal(reservedResponse.status, 200);
  const reserved = await reservedResponse.json();
  const restarted = new ConductKeeperDurableObject({ storage }, env);
  const graphResponse = await restarted.fetch(request(`/api/conduct/runs/${reserved.run_id}/graph`));
  assert.equal(graphResponse.status, 200);
  const graph = await graphResponse.json();
  assert.equal(graph.nodes[0].lease_id, reserved.lease.lease_id);
});
