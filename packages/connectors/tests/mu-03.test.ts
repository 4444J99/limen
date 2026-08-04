import assert from "node:assert";
import { test } from "node:test";
import {
  ConnectorCursorLedger,
  ConnectorRateLimiter,
  ConnectorRegistry,
  ConnectorRuntime,
  MU02_SYNTHETIC_PARTITION,
  MU03_CONNECTORS_VERSION,
  createMu03ProductionConnectorCatalog,
  ProductionConnectorShellAdapter,
  type ConnectorOperationContext,
} from "../src/index.ts";

const actorId = "operator-mu-03";

function context(overrides: Partial<ConnectorOperationContext> = {}): ConnectorOperationContext {
  return {
    actorId,
    partitionId: MU02_SYNTHETIC_PARTITION,
    ...overrides,
  };
}

function installAdapter(runtime: ConnectorRuntime, registry: ConnectorRegistry, adapter: ProductionConnectorShellAdapter): void {
  registry.register(adapter.manifest);
  runtime.registerAdapter(adapter);
  registry.transition(adapter.manifest.connectorId, "authorized", actorId, "authorize");
  registry.transition(adapter.manifest.connectorId, "enabled", actorId, "enable");
}

function registerAdapter(
  adapter: ProductionConnectorShellAdapter,
): { runtime: ConnectorRuntime; registry: ConnectorRegistry } {
  const registry = new ConnectorRegistry();
  const cursorLedger = new ConnectorCursorLedger();
  const limiter = new ConnectorRateLimiter();
  const runtime = new ConnectorRuntime(registry, cursorLedger, limiter);
  installAdapter(runtime, registry, adapter);
  return { registry, runtime };
}

test("MU-03 builds production adapter shells with credential and write valves", () => {
  const catalog = createMu03ProductionConnectorCatalog();
  const ids = catalog.map((adapter) => adapter.manifest.connectorId).sort();
  assert.deepStrictEqual(ids, [
    "connector-github-mu-03",
    "connector-google-mu-03",
    "connector-notion-mu-03",
    "connector-slack-mu-03",
    "connector-webhook-mu-03",
  ].sort());

  for (const adapter of catalog) {
    assert.strictEqual(adapter.manifest.version, MU03_CONNECTORS_VERSION);
    assert.strictEqual(adapter.manifest.requiresAuth, false);
    const snapshot = adapter.snapshot();
    assert.strictEqual(snapshot.writeEffect, "deny");
    assert.strictEqual(snapshot.credentialEffect, "deny");
  }
});

test("MU-03 provides fallback on temporary provider outage during pull", async () => {
  const catalog = createMu03ProductionConnectorCatalog();
  const adapter = catalog[0];
  const { runtime } = registerAdapter(adapter);

  const first = await runtime.executePull(adapter.manifest.connectorId, context({ requestId: "outage-pull" }));
  assert.strictEqual(first.status, "success");
  const firstDiagnostics = JSON.parse(first.redactedDiagnostics || "{}") as { chosenProvider: string; pullRecordCount: number };
  assert.strictEqual(firstDiagnostics.chosenProvider, "github-fallback");
  assert.strictEqual(first.records, 1);
});

test("MU-03 reorders providers to steer pull behavior", async () => {
  const catalog = createMu03ProductionConnectorCatalog();
  const adapter = catalog[1];
  adapter.reorderProviders(["google-fallback", "google-primary"]);
  const { runtime } = registerAdapter(adapter);

  const beforePush = await runtime.executePull(adapter.manifest.connectorId, context({ requestId: "reordered-pull" }));
  assert.strictEqual(beforePush.status, "success");
  const diagnostics = JSON.parse(beforePush.redactedDiagnostics || "{}") as { chosenProvider: string };
  assert.strictEqual(diagnostics.chosenProvider, "google-fallback");
});

test("MU-03 revokes all providers and rejects subsequent operations", async () => {
  const catalog = createMu03ProductionConnectorCatalog();
  const adapter = catalog[2];
  const { runtime } = registerAdapter(adapter);

  const revoked = await runtime.executeRevoke(adapter.manifest.connectorId, context({ requestId: "revoke" }));
  assert.strictEqual(revoked.status, "success");

  const failed = await runtime.executePull(adapter.manifest.connectorId, context({ requestId: "after-revoke" }));
  assert.strictEqual(failed.status, "failed");
  assert.ok((failed.reason || "").includes("revoked"));
});

test("MU-03 models provider removal and partial scope with controlled write valve", async () => {
  const catalog = createMu03ProductionConnectorCatalog();
  const adapter = catalog[3];
  const { runtime } = registerAdapter(adapter);

  const deniedPush = await runtime.executePush(adapter.manifest.connectorId, context({
    requestId: "push-denied-default",
    payload: { operation: "append" },
  }));
  assert.strictEqual(deniedPush.status, "skipped");
  assert.ok((deniedPush.redactedDiagnostics || "").includes("write effect disabled"));

  adapter.setCredentialEffect("allow");
  adapter.setWriteEffect("allow");
  const allowedPush = await runtime.executePush(adapter.manifest.connectorId, context({
    requestId: "push-allowed",
    payload: { operation: "append" },
  }));
  assert.strictEqual(allowedPush.status, "success");
  assert.strictEqual(allowedPush.records, 1);
  assert.ok((allowedPush.redactedDiagnostics || "").includes("chosenProvider"));

  adapter.removeProvider("notion-primary");
  const removedHealth = await runtime.executeHealth(adapter.manifest.connectorId, context({ requestId: "health-after-remove" }));
  assert.strictEqual(removedHealth.status, "success");
  const removedHealthDiag = JSON.parse(removedHealth.redactedDiagnostics || "{}") as { chosenProvider: string };
  assert.strictEqual(removedHealthDiag.chosenProvider, "notion-fallback");
});
