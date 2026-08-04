import { test } from "node:test";
import assert from "node:assert";
import {
  parseSearchQuery,
  SearchDocumentEmbeddingRecord,
  SearchEmbeddingAdapter,
  SearchIndexer,
  SearchSourceEnvelopeLike,
} from "../src/index.ts";

const baseEnvelope: SearchSourceEnvelopeLike = {
  envelopeId: "env-01",
  sourceId: "source-email-01",
  partitionId: "partition-01",
  externalId: "external-01",
  revision: 1,
  mediaType: "application/json",
  observedAt: "2026-08-01T00:00:00.000Z",
  classification: "private",
  payload: {
    id: "note-01",
    subject: "Quarterly board meeting",
    body: "Discuss roadmap and budget",
    access_token: "secret-token",
    legal_hold: "hold",
  },
  provenance: {
    source: "ingest",
  },
};

class LabelVectorAdapter implements SearchEmbeddingAdapter {
  public calls = 0;
  constructor(
    public readonly providerId: string,
    public readonly modelId: string,
    public readonly modelVersion: string,
    public readonly maxInputCharacters = 512,
    private readonly behavior: (text: string) => number[],
  ) {}

  public embedText(text: string): readonly number[] {
    this.calls += 1;
    return this.behavior(text);
  }
}

const alphaBetaAdapter = (modelId: string, modelVersion: string) => new LabelVectorAdapter(
  "mock-provider",
  modelId,
  modelVersion,
  512,
  (text: string) => {
    if (text.includes("alpha")) {
      return [10, 0];
    }
    if (text.includes("beta")) {
      return [0, 10];
    }
    if (text.includes("board")) {
      return [1, 0];
    }
    return [2, 2];
  },
);


test("THETA-01 indexes documents with policy-safe redaction", () => {
  const indexer = new SearchIndexer();
  const receipt = indexer.index({
    sourceEnvelope: baseEnvelope,
    indexedBy: "svc-search",
  });

  assert.strictEqual(receipt.status, "indexed");
  assert.strictEqual(receipt.documentId.length > 0, true);
  assert.strictEqual(receipt.receiptHash.length, 64);

  const docs = indexer.replay(baseEnvelope.partitionId);
  assert.strictEqual(docs.length, 1);
  const indexed = docs[0];
  assert.strictEqual(indexed?.documentId, receipt.documentId);
  assert.ok((indexed?.indexedPayload as Record<string, unknown>)?.access_token === undefined);
  assert.ok((indexed?.indexedPayload as Record<string, unknown>)?.legal_hold === undefined);
  assert.strictEqual(indexed?.provenance?.source, "ingest");
});

test("THETA-01 query returns partition-scoped deterministic results", () => {
  const indexer = new SearchIndexer();
  indexer.index({
    sourceEnvelope: { ...baseEnvelope, envelopeId: "env-02", externalId: "external-02", revision: 2 },
    indexedBy: "svc-search",
  });
  indexer.index({
    sourceEnvelope: {
      ...baseEnvelope,
      envelopeId: "env-03",
      sourceId: "source-other",
      partitionId: "partition-02",
      externalId: "external-03",
      revision: 3,
      payload: {
        subject: "Different partition",
        body: "Private note",
      },
    },
    indexedBy: "svc-search",
  });

  const partitionOne = indexer.query("partition-01", "board");
  assert.strictEqual(partitionOne.length, 1);
  assert.strictEqual(partitionOne[0].sourceId, baseEnvelope.sourceId);

  const all = indexer.replay();
  assert.strictEqual(all.length, 2);
});

test("THETA-01 rejects malformed envelope input", () => {
  const indexer = new SearchIndexer();
  assert.throws(() => {
    indexer.index({
      // @ts-expect-error invalid payload to validate contract
      sourceEnvelope: {
        envelopeId: "env-bad",
        sourceId: "",
        partitionId: "p-1",
        externalId: "x",
        revision: 1,
        mediaType: "application/json",
        observedAt: "not-a-date",
        classification: "private",
        payload: null,
      },
      indexedBy: "svc-search",
    });
  }, /source envelope identity incomplete|invalid observedAt/);
});

test("THETA-02 parses filters, limits, sorts, and exclusions", () => {
  const query = parseSearchQuery('"quarterly board" classification:private limit:12 sort:recent -draft page:2 offset:3');

  assert.deepStrictEqual(query.phrases, ["quarterly board"]);
  assert.strictEqual(query.filters.length, 1);
  assert.strictEqual(query.filters[0].field, "classification");
  assert.strictEqual(query.filters[0].value, "private");
  assert.strictEqual(query.limit, 12);
  assert.strictEqual(query.sort, "recent");
  assert.deepStrictEqual(query.excludedTerms, ["draft"]);
  assert.strictEqual(query.page, 2);
  assert.strictEqual(query.offset, 3);
});

test("THETA-02 ranks by relevance and returns matched filters", () => {
  const indexer = new SearchIndexer();

  const first = indexer.index({
    sourceEnvelope: {
      ...baseEnvelope,
      envelopeId: "env-a",
      externalId: "external-a",
      revision: 1,
      payload: {
        subject: "Board board board",
        status: "open",
        body: "Meeting recap",
      },
      classification: "private",
    },
    indexedBy: "svc-search",
  });

  indexer.index({
    sourceEnvelope: {
      ...baseEnvelope,
      envelopeId: "env-b",
      externalId: "external-b",
      revision: 2,
      payload: {
        subject: "Board",
        status: "open",
        body: "Single mention",
      },
      classification: "private",
    },
    indexedBy: "svc-search",
  });

  const parsed = parseSearchQuery("board status:open");
  const result = indexer.queryParsed("partition-01", parsed);

  assert.strictEqual(result.total, 2);
  const firstDocument = indexer.getByDocumentId(first.documentId);
  assert.strictEqual(result.hits[0].document.documentId, firstDocument?.documentId);
  assert.ok(result.hits[0].score > result.hits[1].score);
  assert.deepStrictEqual(result.hits[0].matchedFilters[0], {
    field: "status",
    operator: "eq",
    value: "open",
    raw: "status:open",
  });
  assert.ok(result.hits[0].highlights.some((entry) => entry.includes("[[board]]")));
});

test("THETA-03 keeps semantic retrieval disabled by default and falls back to exact", () => {
  const indexer = new SearchIndexer({
    semantic: {
      enabled: false,
      provider: alphaBetaAdapter("mock-model", "v1"),
    },
  });

  indexer.index({
    sourceEnvelope: {
      ...baseEnvelope,
      envelopeId: "env-semantics-01",
      externalId: "external-semantics-01",
      revision: 4,
      payload: {
        subject: "Alpha note",
        body: "Project planning",
        status: "open",
      },
      classification: "private",
    },
    indexedBy: "svc-search",
  });

  const parsed = parseSearchQuery("classification:private");
  const exact = indexer.queryParsed("partition-01", parsed);
  const requested = indexer.queryParsed("partition-01", parsed, { useSemantic: true });

  assert.strictEqual(exact.total, 1);
  assert.deepStrictEqual(
    requested.hits.map((entry) => entry.document.documentId),
    exact.hits.map((entry) => entry.document.documentId),
  );
});

test("THETA-03 reorders results with semantic vectors when enabled", () => {
  const indexer = new SearchIndexer({
    semantic: {
      enabled: true,
      provider: alphaBetaAdapter("mock-model", "v1"),
    },
  });

  indexer.index({
    sourceEnvelope: {
      ...baseEnvelope,
      envelopeId: "env-alpha",
      externalId: "external-alpha",
      revision: 5,
      payload: {
        subject: "alpha summary",
        body: "General notes",
      },
      classification: "private",
    },
    indexedBy: "svc-search",
  });
  indexer.index({
    sourceEnvelope: {
      ...baseEnvelope,
      envelopeId: "env-beta",
      externalId: "external-beta",
      revision: 6,
      payload: {
        subject: "beta summary",
        body: "General notes",
      },
      classification: "private",
    },
    indexedBy: "svc-search",
  });

  const query = parseSearchQuery("classification:private");
  const semanticResult = indexer.queryParsed("partition-01", query, { useSemantic: true });

  const resultDocumentIds = semanticResult.hits.map((entry) => entry.document.externalId);
  assert.deepStrictEqual(resultDocumentIds, ["external-alpha", "external-beta"]);
  const firstEmbedding = indexer.getDocumentEmbedding(semanticResult.hits[0].document.documentId);
  const secondEmbedding = indexer.getDocumentEmbedding(semanticResult.hits[1].document.documentId);
  assert.notDeepStrictEqual(firstEmbedding, secondEmbedding);
});

test("THETA-03 provider outage falls back to exact-search ranking", () => {
  const indexer = new SearchIndexer({
    semantic: {
      enabled: true,
      provider: {
        providerId: "failing-provider",
        modelId: "mock-model",
        modelVersion: "v1",
        maxInputCharacters: 512,
        embedText: () => {
          throw new Error("provider unavailable");
        },
      },
    },
  });

  indexer.index({
    sourceEnvelope: {
      ...baseEnvelope,
      envelopeId: "env-semantics-02",
      externalId: "external-outage-1",
      revision: 7,
      payload: {
        subject: "alpha summary",
        body: "General notes",
      },
      classification: "private",
    },
    indexedBy: "svc-search",
  });
  indexer.index({
    sourceEnvelope: {
      ...baseEnvelope,
      envelopeId: "env-semantics-03",
      externalId: "external-outage-2",
      revision: 8,
      payload: {
        subject: "beta summary",
        body: "General notes",
      },
      classification: "private",
    },
    indexedBy: "svc-search",
  });

  const query = parseSearchQuery("classification:private");
  const expected = indexer.queryParsed("partition-01", query, { useSemantic: false });
  const actual = indexer.queryParsed("partition-01", query, { useSemantic: true });

  assert.deepStrictEqual(
    actual.hits.map((entry) => entry.document.documentId),
    expected.hits.map((entry) => entry.document.documentId),
  );
});

test("THETA-03 detects stale embeddings when provider changes and recomputes", () => {
  const providerV1 = alphaBetaAdapter("mock-model", "v1");
  const providerV2 = alphaBetaAdapter("mock-model", "v2");
  const indexer = new SearchIndexer({
    semantic: {
      enabled: true,
      provider: providerV1,
      semanticWeight: 0.6,
    },
  });

  const firstDoc = indexer.index({
    sourceEnvelope: {
      ...baseEnvelope,
      envelopeId: "env-stale-01",
      externalId: "external-stale-1",
      revision: 9,
      payload: {
        subject: "alpha summary",
        body: "General notes",
      },
      classification: "private",
    },
    indexedBy: "svc-search",
  });
  const secondDoc = indexer.index({
    sourceEnvelope: {
      ...baseEnvelope,
      envelopeId: "env-stale-02",
      externalId: "external-stale-2",
      revision: 10,
      payload: {
        subject: "beta summary",
        body: "General notes",
      },
      classification: "private",
    },
    indexedBy: "svc-search",
  });

  const query = parseSearchQuery("classification:private");
  const before = indexer.queryParsed("partition-01", query, { useSemantic: true });
  const beforeEmbedding = indexer.getDocumentEmbedding(before.hits[0].document.documentId);

  indexer.setSemanticProvider(providerV2);
  const after = indexer.queryParsed("partition-01", query, { useSemantic: true });
  const afterEmbedding = indexer.getDocumentEmbedding(after.hits[0].document.documentId);

  assert.strictEqual(beforeEmbedding?.documentId, firstDoc.documentId);
  assert.strictEqual(afterEmbedding?.documentId, firstDoc.documentId);
  assert.strictEqual(beforeEmbedding?.stale, false);
  assert.strictEqual(afterEmbedding?.modelVersion, "v2");
  assert.notStrictEqual(beforeEmbedding?.providerId, afterEmbedding?.providerId);

  // Verify both documents keep a valid embedding state with explicit metadata for auditability.
  const staleCheck: SearchDocumentEmbeddingRecord | null = indexer.getDocumentEmbedding(before.hits[1].document.documentId);
  assert.strictEqual(staleCheck?.sourceEnvelopeId, secondDoc.sourceEnvelopeId);
});
