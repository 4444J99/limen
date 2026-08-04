import assert from "node:assert";
import { test } from "node:test";
import {
  ConnectorCursorLedger,
  ConnectorError,
  ConnectorRateLimiter,
  ConnectorRegistry,
  ConnectorRuntime,
  createBaselineConnectorContracts,
  validateConnectorManifest,
} from "../src/index.ts";
import type {
  ConnectorAdapter,
  ConnectorContractContext,
  ConnectorOperationContext,
  ConnectorScope,
  ConnectorManifest,
} from "../src/index.ts";

function fixedTime(value: string): string {
  return value;
}

function makeManifest(overrides: Partial<ConnectorManifest> = {}): ConnectorManifest {
  return {
    connectorId: overrides.connectorId ?? "connector-mu-01",
    connectorType: overrides.connectorType ?? "synthetic",
    name: overrides.name ?? "Mu Synthetic Connector",
    version: overrides.version ?? "mu-01-connectors-v1",
    description: overrides.description ?? "Connector for MU-01 proof work",
    sourceDataClasses: overrides.sourceDataClasses ?? ["note", "event"],
    capabilities: overrides.capabilities ?? [
      { action: "discover", scope: "admin" as ConnectorScope, description: "discover" },
      { action: "authorize", scope: "admin" as ConnectorScope, description: "authorize" },
      { action: "pull", scope: "read" as ConnectorScope, description: "pull records" },
      { action: "push", scope: "write" as ConnectorScope, description: "push records" },
      { action: "health", scope: "read" as ConnectorScope, description: "health" },
      { action: "revoke", scope: "admin" as ConnectorScope, description: "revoke" },
      { action: "dryRun", scope: "read" as ConnectorScope, description: "dry-run" },
    ],
    supportsDryRun: overrides.supportsDryRun ?? true,
    requiresAuth: overrides.requiresAuth ?? false,
    rateLimit: {
      windowMs: 60_000,
      maxRequests: 5,
      maxConsecutiveFailures: 2,
      maxRetries: 1,
      ...(overrides.rateLimit ?? {}),
    },
    redactionKeys: overrides.redactionKeys ?? ["token", "secret"],
  };
}

const partition = "partition-01";
const actorId = "operator-mu-01";

test("MU-01 validates manifest fields", () => {
  const invalid = validateConnectorManifest({
    connectorId: "",
    connectorType: "",
    name: "",
    version: "",
    description: "",
    sourceDataClasses: [],
    capabilities: [],
    supportsDryRun: true,
    requiresAuth: false,
    rateLimit: {
      windowMs: 1_000,
      maxRequests: 1,
    },
  });
  assert.strictEqual(invalid.valid, false);
  assert.ok(invalid.errors.length >= 3);
});

test("MU-01 enforces manifest validation and registry transitions", () => {
  const registry = new ConnectorRegistry();
  const manifest = makeManifest({ connectorId: "registry-01" });

  const first = registry.register(manifest);
  assert.strictEqual(first.state, "discovered");

  const duplicate = registry.register(manifest);
  assert.strictEqual(duplicate.state, "discovered");
  assert.strictEqual(duplicate.transitions.length, 1);

  assert.throws(() => {
    registry.register({ ...manifest, version: "other" });
  }, /already registered with a different manifest/);

  const toAuthorized = registry.transition("registry-01", "authorized", actorId, "authorize");
  assert.strictEqual(toAuthorized.state, "authorized");
  const toEnabled = registry.transition("registry-01", "enabled", actorId, "enable");
  assert.strictEqual(toEnabled.state, "enabled");
  assert.strictEqual(registry.canInvoke("registry-01", "pull"), true);

  assert.throws(() => registry.transition("registry-01", "discovered", actorId, "invalid"), /invalid lifecycle transition/);
});

test("MU-01 manages partition-scoped cursor monotonicity and idempotency", () => {
  const ledger = new ConnectorCursorLedger();

  const first = ledger.setCursor({
    connectorId: "cursor-01",
    partitionId: partition,
    key: "default",
    value: "v1",
    observedAt: fixedTime("2026-08-01T00:00:00.000Z"),
  });

  const same = ledger.setCursor({
    connectorId: "cursor-01",
    partitionId: partition,
    key: "default",
    value: "v1",
    observedAt: fixedTime("2026-08-01T00:00:00.000Z"),
  });
  assert.strictEqual(same.sequence, first.sequence);

  const next = ledger.setCursor({
    connectorId: "cursor-01",
    partitionId: partition,
    key: "default",
    value: "v2",
    observedAt: fixedTime("2026-08-01T00:00:01.000Z"),
  });
  assert.strictEqual(next.sequence, first.sequence + 1);

  const missing = ledger.getCursor("cursor-01", partition, "missing");
  assert.strictEqual(missing, null);

  assert.throws(() => {
    ledger.setCursor({
      connectorId: "cursor-01",
      partitionId: partition,
      key: "default",
      value: "v0",
      observedAt: fixedTime("2026-07-31T23:59:59.000Z"),
    });
  }, /stale cursor update/);
});

test("MU-01 bounds connector usage with fixed-rate limits", () => {
  const limiter = new ConnectorRateLimiter();
  const manifest = makeManifest({
    connectorId: "rate-01",
    rateLimit: {
      windowMs: 1_000,
      maxRequests: 1,
      maxConsecutiveFailures: 1,
      maxRetries: 0,
    },
  });

  const first = limiter.allow(manifest, "health");
  assert.strictEqual(first.allowed, true);

  const second = limiter.allow(manifest, "health");
  assert.strictEqual(second.allowed, false);
  assert.ok(typeof second.retryAfterMs === "number");
  assert.strictEqual(second.reason, "rate limit exceeded");
});

function asContext(overrides: Partial<ConnectorOperationContext> = {}): ConnectorOperationContext {
  return {
    actorId,
    partitionId: partition,
    ...overrides,
  };
}

test("MU-01 executes with idempotency, bounded retry, and redacted diagnostics", async () => {
  class RetryAdapter {
    public calls = 0;
    public manifest = makeManifest({
      connectorId: "runtime-01",
      rateLimit: {
        windowMs: 10_000,
        maxRequests: 10,
        maxRetries: 2,
      },
    });

    public async pull(context: ConnectorOperationContext) {
      this.calls += 1;
      if (this.calls < 2 && context.requestId === "request-retry") {
        throw new ConnectorError("temporary provider error", { retryable: true });
      }
      return {
        status: "ok",
        records: this.calls,
        cursor: {
          connectorId: "runtime-01",
          partitionId: partition,
          key: "default",
          value: context.requestId ? `cursor-${context.requestId}` : "cursor",
          observedAt: fixedTime("2026-08-01T00:00:00.000Z"),
        },
        diagnostics: {
          message: "ok",
          token: "do-not-leak",  // allow-secret
          nested: {
            secret: "top-secret",  // allow-secret
            project: "collaboration",
          },
        },
      };
    }
  }

  const registry = new ConnectorRegistry();
  const cursorLedger = new ConnectorCursorLedger();
  const limiter = new ConnectorRateLimiter();
  const runtime = new ConnectorRuntime(registry, cursorLedger, limiter);

  const adapter = new RetryAdapter();
  runtime.registerAdapter(adapter);
  registry.transition(adapter.manifest.connectorId, "authorized", actorId, "authorize");
  registry.transition(adapter.manifest.connectorId, "enabled", actorId, "enable");

  const firstAttempt = await runtime.executePull(adapter.manifest.connectorId, asContext({
    requestId: "request-retry",
  }));
  assert.strictEqual(firstAttempt.status, "success");
  assert.strictEqual(firstAttempt.attempts, 2);
  assert.strictEqual(firstAttempt.dryRun, false);
  assert.ok(firstAttempt.redactedDiagnostics);
  assert.ok(!firstAttempt.redactedDiagnostics.includes("do-not-leak"));
  assert.ok(!firstAttempt.redactedDiagnostics.includes("top-secret"));

  const replay = await runtime.executePull(adapter.manifest.connectorId, asContext({
    requestId: "request-retry",
  }));
  assert.strictEqual(replay.idempotentReplay, true);
  assert.strictEqual(replay.status, firstAttempt.status);
});

test("MU-01 dry-runs are skipped when connector disables dry-run", async () => {
  const registry = new ConnectorRegistry();
  const cursorLedger = new ConnectorCursorLedger();
  const limiter = new ConnectorRateLimiter();
  const runtime = new ConnectorRuntime(registry, cursorLedger, limiter);

  const manifest = makeManifest({
    connectorId: "runtime-dryrun",
    supportsDryRun: false,
    capabilities: [
      { action: "discover", scope: "admin" as ConnectorScope, description: "discover" },
      { action: "dryRun", scope: "read" as ConnectorScope, description: "dry-run not supported" },
    ],
  });

  const adapter: ConnectorAdapter = {
    manifest,
    dryRun() {
      return {
        status: "ok",
      };
    },
  };

  runtime.registerAdapter(adapter);
  registry.transition("runtime-dryrun", "authorized", actorId, "authorize");
  registry.transition("runtime-dryrun", "enabled", actorId, "enable");

  const result = await runtime.executeDryRun("runtime-dryrun", asContext({
    requestId: "dry-request",
    dryRun: true,
  }));
  assert.strictEqual(result.status, "skipped");
  assert.strictEqual(result.reason, "dry-run disabled");
});

test("MU-01 baseline contract kit can verify the connector envelope invariants", () => {
  const registry = new ConnectorRegistry();
  const cursorLedger = new ConnectorCursorLedger();
  const limiter = new ConnectorRateLimiter();
  const runtime = new ConnectorRuntime(registry, cursorLedger, limiter);

  const manifest = makeManifest({ connectorId: "contract-manifest" });
  registry.register(manifest);

  const adapter: ConnectorAdapter = {
    manifest,
    health: () => ({ status: "ok" }),
  };
  runtime.registerAdapter(adapter);

  const kit = createBaselineConnectorContracts();
  const context: ConnectorContractContext = {
    registry,
    cursorLedger,
    rateLimiter: limiter,
    runtime,
  };
  const result = kit.run(context);

  assert.strictEqual(result.passed, true);
  assert.strictEqual(result.runs.length, 3);
  for (const run of result.runs) {
    assert.strictEqual(run.passed, true);
  }
});
