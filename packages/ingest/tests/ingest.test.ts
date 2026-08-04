import { test } from "node:test";
import assert from "node:assert";
import {
  DEFAULT_MAX_PAYLOAD_BYTES,
  ArtifactCustodyVault,
  IngestionProcessor,
  SourceEnvelopeLedger,
  buildRawSourceEnvelope,
  validateSourceEnvelopeInput,
  replaySourceEnvelopes,
} from "../src/index.ts";

const baseSource = {
  sourceId: "source-email-01",
  sourceType: "email" as const,
  partitionId: "partition-01",
  sourceKey: "inbox/ops",
};

const baseCursor = {
  key: "page-token",
  scope: "global",
  value: { page: "p-001" },
  observedAt: "2026-08-01T00:00:00.000Z",
};

function baseInput(overrides: Record<string, unknown> = {}) {
  return {
    source: baseSource,
    externalId: "ext-msg-01",
    revision: 1,
    cursor: baseCursor,
    payload: {
      subject: "Welcome",
      body: "hello",
    },
    mediaType: "application/json",
    classification: "private",
    provenance: {
      collectedBy: "ingest-bot",
      sourceChannel: "smtp",
    },
    observedAt: "2026-08-01T00:00:00.000Z",
    ...overrides,
  } as any;
}

test("ETA-01 admission captures source/revision/cursor/checksum and enforces invariants", () => {
  const decision = validateSourceEnvelopeInput(baseInput());
  assert.strictEqual(decision.accepted, true);
  assert.ok(decision.envelope);
  assert.strictEqual(decision.envelope?.sourceId, baseSource.sourceId);
  assert.strictEqual(decision.envelope?.externalId, "ext-msg-01");
  assert.strictEqual(decision.envelope?.revision, 1);
  assert.strictEqual(decision.envelope?.cursor.key, "page-token");
  assert.ok(typeof decision.envelope?.checksum === "string");
  assert.ok(decision.envelope?.payloadSizeBytes > 0);

  const envelope = buildRawSourceEnvelope(baseInput());
  assert.strictEqual(envelope.mediaType, "application/json");
  assert.strictEqual(envelope.classification, "private");
});

test("ETA-01 requires explicit partition/classification/media/provenance at admission", () => {
  const invalidPartition = validateSourceEnvelopeInput(baseInput({ source: { ...baseSource, partitionId: "" } }));
  assert.strictEqual(invalidPartition.accepted, false);
  assert.deepStrictEqual(
    invalidPartition.errors.some((error) => error.field === "source.partitionId"), true,
  );

  const invalidClassification = validateSourceEnvelopeInput(baseInput({ classification: "public" }));
  assert.strictEqual(invalidClassification.accepted, false);
  assert.deepStrictEqual(
    invalidClassification.errors.some((error) => error.field === "classification"), true,
  );

  const invalidMedia = validateSourceEnvelopeInput(baseInput({ mediaType: "application/x-unknown" }));
  assert.strictEqual(invalidMedia.accepted, false);
  assert.deepStrictEqual(invalidMedia.errors.some((error) => error.field === "mediaType"), true);

  const missingProvenance = validateSourceEnvelopeInput(baseInput({ provenance: {} }));
  assert.strictEqual(missingProvenance.accepted, false);
  assert.deepStrictEqual(
    missingProvenance.errors.some((error) => error.field === "provenance"), true,
  );
});

test("ETA-01 enforces payload budget and supports replayable append-only behavior", () => {
  const ledger = new SourceEnvelopeLedger({ maxPayloadBytes: 128 });

  const first = ledger.appendEnvelope(baseInput());
  assert.strictEqual(first.duplicated, false);
  assert.strictEqual(first.envelope.sequence, 0);

  const duplicate = ledger.appendEnvelope(baseInput());
  assert.strictEqual(duplicate.duplicated, true);
  assert.strictEqual(duplicate.envelope.envelopeId, first.envelope.envelopeId);
  assert.strictEqual(ledger.snapshot().envelopes.length, 1);

  const oversized = validateSourceEnvelopeInput(
    baseInput({
      payload: { data: "x".repeat(DEFAULT_MAX_PAYLOAD_BYTES + 10) },
      externalId: "ext-too-large",
      revision: 2,
    }),
  );
  assert.strictEqual(oversized.accepted, false);
  assert.deepStrictEqual(oversized.errors.some((error) => error.field === "payload"), true);
});

test("ETA-01 replay preserves sequence and cursor per source", () => {
  const ledger = new SourceEnvelopeLedger();
  ledger.appendEnvelope(baseInput({ externalId: "ext-msg-02", revision: 1 }));
  ledger.appendEnvelope(baseInput({ externalId: "ext-msg-03", revision: 2, cursor: { ...baseCursor, observedAt: "2026-08-01T00:00:01.000Z" } }));

  const bySource = replaySourceEnvelopes(ledger, baseSource.sourceId);
  assert.strictEqual(bySource.length, 2);
  assert.ok(bySource[0].sequence < bySource[1].sequence);

  const cursor = ledger.cursorFor(baseSource.sourceId, "page-token", "global");
  assert.ok(cursor);
  assert.strictEqual(cursor?.value.page, "p-001");
});

test("ETA-02 separates duplicate, probable match, and accepted normalization outcomes", () => {
  const ledger = new SourceEnvelopeLedger();
  const processor = new IngestionProcessor(ledger);

  const first = processor.process(baseInput({
    externalId: "dup-01",
    revision: 1,
    payload: { title: "alpha", body: "meeting notes" },
  }));
  assert.strictEqual(first.status, "accepted");
  assert.strictEqual(first.linkProposals.length, 0);
  assert.ok(first.command);
  assert.strictEqual(first.command?.commandVersion, "eta-02-domain-command-v1");

  const second = processor.process(baseInput({
    externalId: "dup-02",
    revision: 2,
    payload: { title: "alpha", body: "meeting notes" },
  }));
  assert.strictEqual(second.status, "probable_match");
  assert.strictEqual(second.linkProposals.length, 1);
  assert.strictEqual(second.linkProposals[0].reason, "checksum_match");

  const third = processor.process(baseInput({
    externalId: "dup-01",
    revision: 1,
    payload: { title: "alpha", body: "meeting notes" },
  }));
  assert.strictEqual(third.status, "duplicate");
  assert.strictEqual(third.duplicateOf, third.sourceEnvelopeId);
});

test("ETA-02 quarantines malformed and hostile payloads with bounded diagnostics", () => {
  const ledger = new SourceEnvelopeLedger();
  const processor = new IngestionProcessor(ledger);

  const malformed = processor.process(baseInput({
    externalId: "bad-01",
    revision: 1,
    payload: "",
  }));
  assert.strictEqual(malformed.status, "quarantined");
  assert.ok(malformed.diagnostics.length > 0);
  assert.strictEqual(malformed.statusReason.includes("payload"), true);

  const hostile = processor.process(baseInput({
    externalId: "host-01",
    revision: 2,
    payload: { html: "<script>alert('x')</script>" },
  }));
  assert.strictEqual(hostile.status, "quarantined");
  assert.ok(hostile.diagnostics.some((diagnostic) => diagnostic.includes("script")));
});

test("ETA-03 archives normalized payloads as encrypted content-addressed artifacts and supports retrieval", () => {
  const ledger = new SourceEnvelopeLedger();
  const envelope = buildRawSourceEnvelope(baseInput({}));
  const vault = new ArtifactCustodyVault();

  const record = vault.archive({
    sourceEnvelope: envelope,
    payload: envelope.payload,
    masterKey: "artifact-encryption-key-2026",
  });

  assert.ok(record.address);
  assert.strictEqual(record.custodyVersion, "eta-03-v1");
  assert.strictEqual(vault.exists(record.address), true);

  const decrypted = vault.retrieve(record.address, "artifact-encryption-key-2026");
  assert.deepStrictEqual(JSON.parse(decrypted), envelope.payload);
});

test("ETA-03 rejects invalid decryption attempts and preserves source-addressability", () => {
  const ledger = new SourceEnvelopeLedger();
  const envelope = buildRawSourceEnvelope(baseInput({ externalId: "artifact-02", revision: 2 }));
  const vault = new ArtifactCustodyVault();
  const record = vault.archive({
    sourceEnvelope: envelope,
    payload: envelope.payload,
    masterKey: "artifact-encryption-key-2026",
  });
  assert.throws(() => {
    vault.retrieve(record.address, "wrong-key");
  }, /bad decrypt|Unsupported state/);

  const bySource = vault.listBySource(envelope.sourceId);
  assert.strictEqual(bySource.length, 1);
  assert.strictEqual(bySource[0].artifactId, record.artifactId);
});
