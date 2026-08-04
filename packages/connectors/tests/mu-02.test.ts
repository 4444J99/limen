import assert from "node:assert";
import { test } from "node:test";
import {
  ConnectorCursorLedger,
  ConnectorRateLimiter,
  ConnectorRegistry,
  ConnectorRuntime,
  MU02_CONNECTORS_VERSION,
  MU02_SYNTHETIC_PARTITION,
  buildSyntheticConnectorReplayCorpus,
  createMu02SyntheticConnectorCatalog,
  synthesizeConnectorReplayChecksums,
  type ConnectorOperationContext,
} from "../src/index.ts";

const actorId = "operator-mu-02";

const EXPECTED_CONNECTORS = [
  "connector-mail-mu-02",
  "connector-calendar-mu-02",
  "connector-drive-mu-02",
  "connector-chat-mu-02",
  "connector-github-mu-02",
];

function createRuntimeContext(overrides: Partial<ConnectorOperationContext> = {}): ConnectorOperationContext {
  return {
    actorId,
    partitionId: MU02_SYNTHETIC_PARTITION,
    ...overrides,
  };
}

function installCatalog(runtime: ConnectorRuntime, registry: ConnectorRegistry): void {
  const catalog = createMu02SyntheticConnectorCatalog({ pageSize: 2 });
  for (const adapter of catalog) {
    registry.register(adapter.manifest);
    runtime.registerAdapter(adapter);
    registry.transition(adapter.manifest.connectorId, "authorized", actorId, "authorize");
    registry.transition(adapter.manifest.connectorId, "enabled", actorId, "enable");
  }
}

test("MU-02 builds the synthetic connector catalog and fixture classes", () => {
  const catalog = createMu02SyntheticConnectorCatalog({ pageSize: 2 });
  const connectorIds = catalog.map((connector) => connector.manifest.connectorId).sort();
  const sourceClasses = catalog.map((connector) => connector.manifest.sourceDataClasses[0]).sort();

  assert.deepStrictEqual(connectorIds, EXPECTED_CONNECTORS.sort());
  assert.deepStrictEqual(sourceClasses, ["calendar", "chat", "drive", "github", "mail"].sort());
  for (const adapter of catalog) {
    assert.strictEqual(adapter.manifest.version, MU02_CONNECTORS_VERSION);
    assert.strictEqual(adapter.manifest.requiresAuth, false);
    assert.ok(typeof adapter.manifest.name === "string");
  }
});

test("MU-02 paginates deterministic synthetic records across reads", () => {
  const catalog = createMu02SyntheticConnectorCatalog({ pageSize: 2 });
  const mail = catalog.find((entry) => entry.manifest.connectorId === "connector-mail-mu-02");
  assert.ok(mail);

  const first = mail!.readPage("0");
  const second = mail!.readPage(first.cursorOut ?? "0");
  const third = second.cursorOut === null ? first : mail!.readPage(second.cursorOut);

  assert.strictEqual(first.pageIndex, 0);
  assert.strictEqual(first.records.length, 2);
  assert.strictEqual(first.cursorOut, "2");

  assert.strictEqual(second.pageIndex, 1);
  assert.strictEqual(second.records.length, 2);
  assert.strictEqual(second.cursorOut, "4");

  assert.strictEqual(third.pageIndex, 2);
  assert.strictEqual(third.records.length, 2);
  assert.strictEqual(third.cursorOut, null);
});

test("MU-02 exercises read-only and proposed-write modes without network", async () => {
  const registry = new ConnectorRegistry();
  const cursorLedger = new ConnectorCursorLedger();
  const limiter = new ConnectorRateLimiter();
  const runtime = new ConnectorRuntime(registry, cursorLedger, limiter);
  const catalog = createMu02SyntheticConnectorCatalog({ pageSize: 2 });
  installCatalog(runtime, registry);

  const readOnly = catalog.find((connector) => connector.manifest.connectorId === "connector-mail-mu-02");
  const proposedWrite = catalog.find((connector) => connector.manifest.connectorId === "connector-calendar-mu-02");
  assert.ok(readOnly);
  assert.ok(proposedWrite);

  const readonlyResult = await runtime.executePush(readOnly.manifest.connectorId, createRuntimeContext({
    requestId: "read-only-push",
    payload: { mode: "noop" },
  }));
  assert.strictEqual(readonlyResult.status, "skipped");
  assert.strictEqual(readonlyResult.records, undefined);

  const writeResult = await runtime.executePush(proposedWrite.manifest.connectorId, createRuntimeContext({
    requestId: "proposed-write",
    payload: { operation: "create-note", title: "Draft note" },
  }));
  assert.strictEqual(writeResult.status, "success");
  assert.strictEqual(writeResult.records, 1);
});

test("MU-02 simulates transient outages with bounded retries", async () => {
  const registry = new ConnectorRegistry();
  const cursorLedger = new ConnectorCursorLedger();
  const limiter = new ConnectorRateLimiter();
  const runtime = new ConnectorRuntime(registry, cursorLedger, limiter);

  const catalog = createMu02SyntheticConnectorCatalog({ pageSize: 2 });
  installCatalog(runtime, registry);

  const github = catalog.find((entry) => entry.manifest.connectorId === "connector-github-mu-02");
  assert.ok(github);

  const result = await runtime.executePull(github.manifest.connectorId, createRuntimeContext({
    requestId: "retry-github",
  }));
  assert.strictEqual(result.status, "success");
  assert.strictEqual(result.attempts, 2);
  assert.strictEqual(result.records, 2);
});

test("MU-02 enforces synthetic rate limits and deterministic replay receipts", async () => {
  const registry = new ConnectorRegistry();
  const cursorLedger = new ConnectorCursorLedger();
  const limiter = new ConnectorRateLimiter();
  const runtime = new ConnectorRuntime(registry, cursorLedger, limiter);
  installCatalog(runtime, registry);

  const drive = "connector-drive-mu-02";
  const firstHealth = await runtime.executeHealth(drive, createRuntimeContext({ requestId: "health-01" }));
  assert.strictEqual(firstHealth.status, "success");

  const secondHealth = await runtime.executeHealth(drive, createRuntimeContext({ requestId: "health-02" }));
  assert.strictEqual(secondHealth.status, "rejected");
  assert.strictEqual(secondHealth.reason, "rate limit exceeded");

  const corpusOne = buildSyntheticConnectorReplayCorpus(createMu02SyntheticConnectorCatalog({ pageSize: 2 }), {
    partitionId: MU02_SYNTHETIC_PARTITION,
  });
  const corpusTwo = buildSyntheticConnectorReplayCorpus(createMu02SyntheticConnectorCatalog({ pageSize: 2 }), {
    partitionId: MU02_SYNTHETIC_PARTITION,
  });
  const checksOne = synthesizeConnectorReplayChecksums(corpusOne);
  const checksTwo = synthesizeConnectorReplayChecksums(corpusTwo);

  assert.deepStrictEqual(checksOne, checksTwo);
  assert.ok(checksOne.overall);
  assert.strictEqual(corpusOne.version, MU02_CONNECTORS_VERSION);
  assert.strictEqual(corpusOne.generatedForPartition, MU02_SYNTHETIC_PARTITION);
  assert.strictEqual(corpusOne.totals.connectors, 5);
  assert.strictEqual(corpusOne.totals.records, 21);
  assert.strictEqual(corpusOne.totals.duplicates, 2);
  assert.strictEqual(corpusOne.totals.deleted, 2);
  assert.strictEqual(corpusOne.totals.attachments, 2);

  const mail = corpusOne.connectors.find((entry) => entry.connectorId === "connector-mail-mu-02");
  assert.ok(mail);
  assert.strictEqual(mail.totals.records, 6);
  assert.strictEqual(mail.totals.duplicates, 1);
  assert.strictEqual(mail.totals.deleted, 1);
  assert.strictEqual(mail.totals.attachments, 1);
});
