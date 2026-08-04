import { createHash, randomUUID } from "node:crypto";

export const THETA01_INDEX_VERSION = "theta-01-index-v1";
export const THETA02_QUERY_VERSION = "theta-02-search-v1";
export const THETA03_EMBEDDING_VERSION = "theta-03-embedding-v1";

export type SearchPartitionClassification = "private" | "confidential" | "restricted";

export interface SearchSourceEnvelopeLike {
  envelopeId: string;
  sourceId: string;
  partitionId: string;
  externalId: string;
  revision: number;
  mediaType: string;
  observedAt: string;
  classification: SearchPartitionClassification;
  payload: unknown;
  provenance?: Record<string, unknown>;
}

export interface SearchIndexInput {
  sourceEnvelope: SearchSourceEnvelopeLike;
  indexedBy: string;
  indexVersion?: string;
  allowlist?: readonly string[];
  denylist?: readonly string[];
  now?: string;
}

export interface SearchDocument {
  documentId: string;
  indexVersion: string;
  sourceEnvelopeId: string;
  sourceId: string;
  partitionId: string;
  externalId: string;
  revision: number;
  mediaType: string;
  classification: SearchPartitionClassification;
  observedAt: string;
  indexedAt: string;
  indexedBy: string;
  textBlob: string;
  indexedPayload: Record<string, unknown>;
  payloadChecksum: string;
  provenance: Record<string, unknown>;
}

export interface SearchIndexReceipt {
  status: "indexed" | "rejected";
  action: "upsert" | "skip";
  documentId: string;
  sourceEnvelopeId: string;
  reason: string;
  redactionCount: number;
  receiptHash: string;
}

export interface SearchEmbeddingAdapter {
  providerId: string;
  modelId: string;
  modelVersion: string;
  maxInputCharacters: number;
  embedText(text: string): readonly number[];
}

export interface SearchIndexerOptions {
  semantic?: {
    enabled?: boolean;
    provider?: SearchEmbeddingAdapter | null;
    semanticWeight?: number;
    maxEmbeddingInputCharacters?: number;
  };
}

export interface SearchDocumentEmbeddingRecord {
  documentId: string;
  sourceEnvelopeId: string;
  providerId: string;
  modelId: string;
  modelVersion: string;
  requestHash: string;
  requestLength: number;
  truncated: boolean;
  embeddingDimension: number;
  createdAt: string;
  vector: number[];
  stale: boolean;
}

export type SearchQuerySort = "relevance" | "recent";

export interface ParsedSearchQuery {
  raw: string;
  normalized: string;
  terms: string[];
  phrases: string[];
  excludedTerms: string[];
  filters: SearchFilter[];
  limit: number;
  page: number;
  offset: number;
  sort: SearchQuerySort;
}

export interface SearchFilter {
  field: string;
  operator: "eq" | "neq";
  value: string;
  raw: string;
}

export interface SearchResultHit {
  document: SearchDocument;
  score: number;
  matchedTerms: string[];
  matchedFilters: SearchFilter[];
  highlights: string[];
}

export interface SearchQueryResult {
  partitionIds: string[];
  query: ParsedSearchQuery;
  total: number;
  returned: number;
  offset: number;
  limit: number;
  sort: SearchQuerySort;
  hits: SearchResultHit[];
}

export interface SavedSearch {
  searchId: string;
  ownerId: string;
  name: string;
  query: string;
  parsedQuery: ParsedSearchQuery;
  createdAt: string;
  createdBy: string;
  partitionIds: readonly string[];
  defaultLimit: number;
}

export interface SearchQueryExecution {
  limit?: number;
  page?: number;
  offset?: number;
  sort?: SearchQuerySort;
  maxHighlights?: number;
  useSemantic?: boolean;
  semanticWeight?: number;
}

export interface RunSavedSearchOptions {
  limit?: number;
  page?: number;
  offset?: number;
  sort?: SearchQuerySort;
  maxHighlights?: number;
  partitionIds?: string[];
  useSemantic?: boolean;
  semanticWeight?: number;
}

export interface SaveSearchOptions {
  createdBy?: string;
  partitionIds?: string[];
  defaultLimit?: number;
}

interface SearchIndexState {
  documents: Map<string, SearchDocument>;
  byPartition: Map<string, Set<string>>;
  receipts: SearchIndexReceipt[];
  savedSearches: Map<string, SavedSearch>;
  embeddings: Map<string, SearchDocumentEmbeddingRecord>;
  semanticEnabled: boolean;
  semanticProvider: SearchEmbeddingAdapter | null;
  semanticWeight: number;
  maxEmbeddingInputCharacters: number;
}

const DEFAULT_DENYLIST = [
  "access_token",
  "refresh_token",
  "api_key",
  "client_secret",
  "private_key",
  "encryption_nonce",
  "raw_headers",
  "identity_map",
  "confidential_comment",
  "legal_hold",
  "risk_notes",
  "sensitive_reason",
];

function stableStringify(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(",")]`;
  }
  const entries = Object.entries(value as Record<string, unknown>).sort(([left], [right]) => left.localeCompare(right));
  return `{${entries.map(([key, nestedValue]) => `${JSON.stringify(key)}:${stableStringify(nestedValue)}`).join(",")}}`;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function textFromPayload(payload: unknown): string {
  if (payload === null || payload === undefined) {
    return "";
  }
  if (typeof payload === "string") {
    return payload;
  }
  if (typeof payload === "number" || typeof payload === "boolean") {
    return String(payload);
  }
  if (Array.isArray(payload)) {
    return payload.map((entry) => textFromPayload(entry)).join(" ");
  }
  return Object.entries(payload as Record<string, unknown>)
    .map(([key, value]) => `${key}:${textFromPayload(value)}`)
    .join(" ");
}

function normalizePayload(payload: unknown, denylist: Set<string>, allowlist?: Set<string>): Record<string, unknown> {
  if (!isObject(payload)) {
    return {};
  }

  const normalized: Record<string, unknown> = {};
  const denied = new Set<string>();

  const walk = (source: Record<string, unknown>, target: Record<string, unknown>): void => {
    for (const [key, value] of Object.entries(source)) {
      const lowered = key.toLowerCase();
      if (denylist.has(lowered)) {
        denied.add(key);
        continue;
      }
      if (allowlist && allowlist.size > 0 && !allowlist.has(lowered)) {
        continue;
      }
      if (value === null || typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
        target[key] = value;
        continue;
      }
      if (Array.isArray(value)) {
        target[key] = value.map((entry) => (isObject(entry) ? JSON.parse(stableStringify(entry)) : entry));
        continue;
      }
      if (isObject(value)) {
        const nested: Record<string, unknown> = {};
        walk(value, nested);
        target[key] = nested;
      }
    }
  };

  walk(payload, normalized);
  if (denied.size > 0) {
    targetMetadata(normalized, denied.size);
  }
  return normalized;
}

function targetMetadata(target: Record<string, unknown>, redacted: number): void {
  target.__redactedFields = redacted;
}

function indexText(document: SearchDocument): string {
  return `${document.sourceId} ${document.externalId} ${document.revision} ${document.classification} ${document.mediaType} ${textFromPayload(document.indexedPayload)}`
    .toLowerCase();
}

function computeReceiptHash(payload: unknown): string {
  return createHash("sha256").update(stableStringify(payload)).digest("hex");
}

function validateSourceEnvelopeLike(input: SearchSourceEnvelopeLike): void {
  if (!input.sourceId || !input.partitionId || !input.externalId) {
    throw new Error("source envelope identity incomplete");
  }
  if (
    input.payload === null
    || input.payload === undefined
    || (typeof input.payload === "number" && Number.isNaN(input.payload))
  ) {
    throw new Error("invalid payload");
  }
  if (typeof input.revision !== "number" || !Number.isInteger(input.revision) || input.revision < 1) {
    throw new Error("invalid revision");
  }
  if (!Number.isFinite(Date.parse(input.observedAt))) {
    throw new Error("invalid observedAt");
  }
}

function normalizeField(value: string): string {
  return value.trim().toLowerCase();
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function splitQuery(input: string): string[] {
  const normalized = input.trim();
  if (!normalized) {
    return [];
  }
  const tokenPattern = /"([^"\\]*(?:\\.[^"\\]*)*)"|'([^'\\]*(?:\\.[^'\\]*)*)'|(\S+)/g;
  const tokens: string[] = [];
  let match: RegExpExecArray | null;
  while ((match = tokenPattern.exec(normalized)) !== null) {
    const quoted = match[1] || match[2];
    const plain = match[3];
    tokens.push(quoted ?? plain);
  }
  return tokens;
}

function parseSort(value: string): SearchQuerySort | null {
  const normalized = normalizeField(value);
  if (normalized === "recent" || normalized === "relevance") {
    return normalized;
  }
  return null;
}

function parsePositiveInt(value: string): number | null {
  const parsed = Number.parseInt(normalizeField(value), 10);
  if (Number.isNaN(parsed) || parsed <= 0) {
    return null;
  }
  return parsed;
}

function parseNonNegativeInt(value: string): number | null {
  const parsed = Number.parseInt(normalizeField(value), 10);
  if (Number.isNaN(parsed) || parsed < 0) {
    return null;
  }
  return parsed;
}

function parsePage(value: string): number | null {
  const parsed = Number.parseInt(normalizeField(value), 10);
  if (Number.isNaN(parsed) || parsed < 1) {
    return null;
  }
  return parsed;
}

export function parseSearchQuery(input: string): ParsedSearchQuery {
  const normalized = input.trim();
  const parsed: ParsedSearchQuery = {
    raw: input,
    normalized,
    terms: [],
    phrases: [],
    excludedTerms: [],
    filters: [],
    limit: 25,
    page: 1,
    offset: 0,
    sort: "relevance",
  };

  if (!normalized) {
    return parsed;
  }

  const tokens = splitQuery(normalized);
  for (const token of tokens) {
    if (token.includes(":")) {
      const splitIndex = token.indexOf(":");
      const field = normalizeField(token.slice(0, splitIndex));
      const value = token.slice(splitIndex + 1);
      if (!field || !value) {
        continue;
      }
      if (field === "limit") {
        const parsedLimit = parsePositiveInt(value);
        if (parsedLimit !== null) {
          parsed.limit = parsedLimit;
          continue;
        }
      } else if (field === "page") {
        const parsedPage = parsePage(value);
        if (parsedPage !== null) {
          parsed.page = parsedPage;
          continue;
        }
      } else if (field === "offset") {
        const parsedOffset = parseNonNegativeInt(value);
        if (parsedOffset !== null) {
          parsed.offset = parsedOffset;
          continue;
        }
      } else if (field === "sort") {
        const parsedSort = parseSort(value);
        if (parsedSort !== null) {
          parsed.sort = parsedSort;
          continue;
        }
      }

      const normalizedValue = value.toLowerCase().trim();
      if (!normalizedValue) {
        continue;
      }
      parsed.filters.push({
        field,
        operator: "eq",
        value: normalizeField(normalizedValue),
        raw: token,
      });
      continue;
    }

    if (token.startsWith("-")) {
      const term = token.slice(1).trim();
      if (term.length > 0) {
        parsed.excludedTerms.push(normalizeField(term));
      }
      continue;
    }

    if (token.includes(" ")) {
      parsed.phrases.push(normalizeField(token));
      continue;
    }

    const normalizedTerm = normalizeField(token);
    if (normalizedTerm.length > 0) {
      parsed.terms.push(normalizedTerm);
    }
  }

  parsed.normalized = [
    ...parsed.phrases,
    ...parsed.terms,
    ...parsed.excludedTerms,
    ...parsed.filters.map((entry) => `${entry.field}:${entry.value}`),
  ].join(" ").trim();
  return parsed;
}

function payloadFieldMatches(document: SearchDocument, field: string, expected: string): boolean {
  const normalizedField = normalizeField(field);
  const payload = document.indexedPayload;
  let matched = false;
  if (isObject(payload)) {
    for (const [key, value] of Object.entries(payload)) {
      if (normalizeField(key) !== normalizedField) {
        continue;
      }
      if (String(value).toLowerCase() === expected) {
        matched = true;
      }
    }
  }
  if (!matched) {
    const haystack = textFromPayload(payload).toLowerCase();
    matched = haystack.includes(normalizedField) && haystack.includes(expected);
  }
  return matched;
}

function valueMatchesFilter(document: SearchDocument, filter: SearchFilter): boolean {
  const normalizedExpected = normalizeField(filter.value);
  if (!normalizedExpected) {
    return filter.operator === "neq";
  }
  let matches = false;

  if (filter.field === "sourceid") {
    matches = normalizeField(document.sourceId) === normalizedExpected;
  } else if (filter.field === "externalid") {
    matches = normalizeField(document.externalId) === normalizedExpected;
  } else if (filter.field === "media" || filter.field === "mediatype") {
    matches = normalizeField(document.mediaType) === normalizedExpected;
  } else if (filter.field === "classification") {
    matches = normalizeField(document.classification) === normalizedExpected;
  } else if (filter.field === "revision") {
    matches = String(document.revision) === normalizedExpected;
  } else if (filter.field === "partition" || filter.field === "partitionid") {
    matches = normalizeField(document.partitionId) === normalizedExpected;
  } else {
    matches = payloadFieldMatches(document, filter.field, normalizedExpected);
  }

  return filter.operator === "eq" ? matches : !matches;
}

function countOccurrences(text: string, term: string): number {
  const normalizedText = normalizeField(text);
  const normalizedTerm = normalizeField(term);
  if (!normalizedTerm) {
    return 0;
  }
  let count = 0;
  let cursor = 0;
  while (true) {
    const next = normalizedText.indexOf(normalizedTerm, cursor);
    if (next < 0) {
      break;
    }
    count += 1;
    cursor = next + normalizedTerm.length;
  }
  return count;
}

function scoreDocument(document: SearchDocument, parsedQuery: ParsedSearchQuery): number {
  const haystack = document.textBlob;
  let score = 0;

  for (const phrase of parsedQuery.phrases) {
    const occurrences = countOccurrences(haystack, phrase);
    if (occurrences > 0) {
      score += 7 + occurrences * 4;
    }
  }

  for (const term of parsedQuery.terms) {
    const occurrences = countOccurrences(haystack, term);
    score += occurrences * 2;
  }

  if (!parsedQuery.phrases.length && !parsedQuery.terms.length) {
    score = Math.max(score, 1);
  }

  return score;
}

function createHighlights(text: string, terms: string[], phrases: string[], maxHighlights: number): string[] {
  const lowered = normalizeField(text);
  const needles = [...phrases, ...terms].filter(Boolean);
  const highlights: string[] = [];

  for (const needle of needles) {
    const normalizedNeedle = normalizeField(needle);
    if (!normalizedNeedle) {
      continue;
    }
    const found = lowered.indexOf(normalizedNeedle);
    if (found < 0) {
      continue;
    }
    const start = Math.max(0, found - 24);
    const end = Math.min(text.length, found + normalizedNeedle.length + 24);
    const raw = text.slice(start, end);
    const highlighted = raw.replace(new RegExp(escapeRegExp(needle), "gi"), "[[$&]]");
    highlights.push(highlighted);
    if (highlights.length >= maxHighlights) {
      break;
    }
  }

  if (highlights.length === 0) {
    return [text.slice(0, 160)];
  }
  return highlights;
}

interface SemanticRequest {
  text: string;
  truncated: boolean;
}

function textForSemanticRequest(document: SearchDocument, maxCharacters: number): SemanticRequest {
  const preferredKeys = [
    "subject",
    "title",
    "summary",
    "body",
    "content",
    "description",
    "decision",
    "notes",
    "text",
  ];
  const compact: string[] = [];

  for (const key of preferredKeys) {
    const value = (document.indexedPayload as Record<string, unknown>)[key];
    if (typeof value === "string") {
      compact.push(value);
    }
  }

  if (compact.length === 0) {
    compact.push(document.sourceId);
    compact.push(document.externalId);
    compact.push(document.mediaType);
    compact.push(document.classification);
  }

  const normalized = compact.join(" ").replace(/\s+/g, " ").trim().toLowerCase();
  const truncated = normalized.length > maxCharacters;
  const bounded = truncated ? normalized.slice(0, maxCharacters) : normalized;
  return { text: bounded, truncated };
}

function textForQueryEmbedding(parsedQuery: ParsedSearchQuery, maxCharacters: number): SemanticRequest {
  const base = [
    ...parsedQuery.phrases,
    ...parsedQuery.terms,
    ...parsedQuery.filters.map((entry) => `${entry.field}:${entry.value}`),
    ...(parsedQuery.excludedTerms.length > 0 ? [parsedQuery.excludedTerms.map((entry) => `-${entry}`).join(",") ] : []),
  ].join(" ");
  const normalized = base.trim().toLowerCase();
  const truncated = normalized.length > maxCharacters;
  const bounded = normalized.length > maxCharacters ? normalized.slice(0, maxCharacters) : normalized;
  return {
    text: bounded,
    truncated,
  };
}

function vectorFromProvider(adapter: SearchEmbeddingAdapter, text: string): number[] {
  const raw = adapter.embedText(text);
  if (raw.length === 0) {
    throw new Error("empty embedding vector");
  }
  const vector = raw.map((entry) => {
    const normalized = Number(entry);
    if (!Number.isFinite(normalized)) {
      throw new Error("non-finite embedding value");
    }
    return normalized;
  });
  return vector;
}

function vectorMagnitude(vector: readonly number[]): number {
  return Math.sqrt(vector.reduce((sum, value) => sum + value * value, 0));
}

function cosineSimilarity(left: readonly number[], right: readonly number[]): number {
  if (left.length !== right.length) {
    const length = Math.min(left.length, right.length);
    let matchedLeft = 0;
    let matchedRight = 0;
    let dotProduct = 0;
    for (let index = 0; index < length; index += 1) {
      const lhs = left[index] ?? 0;
      const rhs = right[index] ?? 0;
      matchedLeft += lhs * lhs;
      matchedRight += rhs * rhs;
      dotProduct += lhs * rhs;
    }
    const denom = Math.sqrt(matchedLeft) * Math.sqrt(matchedRight);
    return denom === 0 ? 0 : dotProduct / denom;
  }

  const dotProduct = left.reduce((sum, value, index) => sum + value * right[index]!, 0);
  const denominator = vectorMagnitude(left) * vectorMagnitude(right);
  if (denominator === 0) {
    return 0;
  }
  return dotProduct / denominator;
}

export class SearchIndexer {
  private state: SearchIndexState;

  public constructor(options?: SearchIndexerOptions) {
    const semantic = options?.semantic || {};
    this.state = {
      documents: new Map(),
      byPartition: new Map(),
      receipts: [],
      savedSearches: new Map(),
      embeddings: new Map(),
      semanticEnabled: semantic.enabled ?? false,
      semanticProvider: semantic.provider ?? null,
      semanticWeight: semantic.semanticWeight ?? 0.35,
      maxEmbeddingInputCharacters: semantic.maxEmbeddingInputCharacters ?? 512,
    };
  }

  public configureSemanticRuntime(options?: SearchIndexerOptions["semantic"]): void {
    const fallback = options || {};
    this.state.semanticEnabled = fallback.enabled ?? this.state.semanticEnabled;
    this.state.semanticProvider = fallback.provider === undefined ? this.state.semanticProvider : fallback.provider;
    this.state.semanticWeight = fallback.semanticWeight ?? this.state.semanticWeight;
    this.state.maxEmbeddingInputCharacters = fallback.maxEmbeddingInputCharacters ?? this.state.maxEmbeddingInputCharacters;
  }

  public enableSemanticMode(): void {
    this.state.semanticEnabled = true;
  }

  public disableSemanticMode(): void {
    this.state.semanticEnabled = false;
  }

  public setSemanticProvider(adapter: SearchEmbeddingAdapter | null): void {
    this.state.semanticProvider = adapter;
  }

  public getSemanticEmbedding(documentId: string): SearchDocumentEmbeddingRecord | null {
    const record = this.state.embeddings.get(documentId);
    if (!record) {
      return null;
    }

    const provider = this.state.semanticProvider;
    const stale = this.isDocumentEmbeddingStale(record, provider);
    return { ...record, stale };
  }

  public isSemanticEnabled(): boolean {
    return this.state.semanticEnabled;
  }

  public getDocumentEmbeddingProviderId(): string | null {
    return this.state.semanticProvider?.providerId ?? null;
  }

  public index(input: SearchIndexInput): SearchIndexReceipt {
    const now = input.now || new Date().toISOString();
    validateSourceEnvelopeLike(input.sourceEnvelope);

    const denylist = new Set((input.denylist || DEFAULT_DENYLIST).map((entry) => String(entry).toLowerCase()));
    const allowlist = input.allowlist ? new Set(input.allowlist.map((entry) => String(entry).toLowerCase())) : undefined;

    const sanitized = normalizePayload(input.sourceEnvelope.payload as Record<string, unknown>, denylist, allowlist);
    const redactedFields = Number((sanitized as Record<string, unknown>).__redactedFields ?? 0);
    const document: SearchDocument = {
      documentId: randomUUID(),
      indexVersion: input.indexVersion || THETA01_INDEX_VERSION,
      sourceEnvelopeId: input.sourceEnvelope.envelopeId,
      sourceId: input.sourceEnvelope.sourceId,
      partitionId: input.sourceEnvelope.partitionId,
      externalId: input.sourceEnvelope.externalId,
      revision: input.sourceEnvelope.revision,
      mediaType: input.sourceEnvelope.mediaType,
      classification: input.sourceEnvelope.classification,
      observedAt: input.sourceEnvelope.observedAt,
      indexedAt: now,
      indexedBy: input.indexedBy,
      textBlob: "",
      indexedPayload: sanitized,
      payloadChecksum: createHash("sha256").update(stableStringify(sanitized)).digest("hex"),
      provenance: input.sourceEnvelope.provenance || {},
    };
    document.textBlob = indexText(document);

    this.state.documents.set(document.documentId, document);
    if (!this.state.byPartition.has(document.partitionId)) {
      this.state.byPartition.set(document.partitionId, new Set());
    }
    this.state.byPartition.get(document.partitionId)?.add(document.documentId);

    const receiptPayload = {
      version: THETA01_INDEX_VERSION,
      status: "indexed",
      sourceEnvelopeId: input.sourceEnvelope.envelopeId,
      action: "upsert",
      redactionCount: redactedFields,
      indexedAt: now,
      indexedBy: input.indexedBy,
    };

    const receipt: SearchIndexReceipt = {
      status: "indexed",
      action: "upsert",
      documentId: document.documentId,
      sourceEnvelopeId: input.sourceEnvelope.envelopeId,
      reason: "indexed",
      redactionCount: redactedFields,
      receiptHash: computeReceiptHash(receiptPayload),
    };
    this.state.receipts.push(receipt);
    this.state.embeddings.delete(document.documentId);
    return receipt;
  }

  public query(
    partitionId: string,
    query: string,
    opts?: SearchQueryExecution,
  ): SearchDocument[] {
    return this.queryParsed(partitionId, parseSearchQuery(query), opts).hits.map((hit) => hit.document);
  }

  public queryParsed(
    partitionId: string,
    parsedQuery: ParsedSearchQuery,
    opts?: SearchQueryExecution,
  ): SearchQueryResult {
    const docs = Array.from(this.state.byPartition.get(partitionId) || new Set())
      .map((documentId) => this.state.documents.get(documentId))
      .filter((document): document is SearchDocument => Boolean(document));

    return this.searchDocuments(docs, parsedQuery, opts);
  }

  public saveSearch(
    ownerId: string,
    name: string,
    query: string,
    opts?: SaveSearchOptions,
  ): SavedSearch {
    if (!ownerId.trim() || !name.trim()) {
      throw new Error("invalid search metadata");
    }

    const parsedQuery = parseSearchQuery(query);
    const now = new Date().toISOString();
    const search: SavedSearch = {
      searchId: randomUUID(),
      ownerId,
      name,
      query,
      parsedQuery,
      createdAt: now,
      createdBy: opts?.createdBy || ownerId,
      partitionIds: Object.freeze([...(opts?.partitionIds || [])]),
      defaultLimit: opts?.defaultLimit ?? parsedQuery.limit,
    };
    this.state.savedSearches.set(search.searchId, search);
    return { ...search };
  }

  public runSavedSearch(
    searchId: string,
    opts?: RunSavedSearchOptions,
  ): SearchQueryResult {
    const search = this.state.savedSearches.get(searchId);
    if (!search) {
      throw new Error(`missing saved search: ${searchId}`);
    }

    const partitionIds = (opts?.partitionIds && opts.partitionIds.length > 0)
      ? opts.partitionIds
      : Array.from(search.partitionIds);

    const uniqueDocuments = new Map<string, SearchDocument>();
    if (partitionIds.length > 0) {
      for (const partitionId of partitionIds) {
        for (const documentId of this.state.byPartition.get(partitionId) || []) {
          const document = this.state.documents.get(documentId);
          if (document) {
            uniqueDocuments.set(document.documentId, document);
          }
        }
      }
    } else {
      for (const document of this.state.documents.values()) {
        uniqueDocuments.set(document.documentId, document);
      }
    }

    const options: SearchQueryExecution = {
      limit: opts?.limit ?? search.defaultLimit,
      page: opts?.page,
      offset: opts?.offset,
      sort: opts?.sort,
      maxHighlights: opts?.maxHighlights,
      useSemantic: opts?.useSemantic,
      semanticWeight: opts?.semanticWeight,
    };

    return this.searchDocuments(Array.from(uniqueDocuments.values()), search.parsedQuery, options);
  }

  public listSavedSearches(ownerId?: string): SavedSearch[] {
    const searches = Array.from(this.state.savedSearches.values());
    const filtered = ownerId ? searches.filter((entry) => entry.ownerId === ownerId) : searches;
    return filtered.map((entry) => ({ ...entry }));
  }

  public deleteSavedSearch(searchId: string): SavedSearch | null {
    const search = this.state.savedSearches.get(searchId);
    if (!search) {
      return null;
    }
    this.state.savedSearches.delete(searchId);
    return { ...search };
  }

  public getSavedSearch(searchId: string): SavedSearch | null {
    const search = this.state.savedSearches.get(searchId);
    return search ? { ...search } : null;
  }

  public getByDocumentId(documentId: string): SearchDocument | null {
    return this.state.documents.get(documentId) ?? null;
  }

  public replay(partitionId?: string): SearchDocument[] {
    if (!partitionId) {
      return Array.from(this.state.documents.values());
    }
    const ids = this.state.byPartition.get(partitionId) || new Set();
    return Array.from(ids).map((id) => this.state.documents.get(id)!).filter(Boolean);
  }

  public listReceipts(): SearchIndexReceipt[] {
    return this.state.receipts.map((receipt) => ({ ...receipt }));
  }

  private isDocumentEmbeddingStale(record: SearchDocumentEmbeddingRecord, provider?: SearchEmbeddingAdapter | null): boolean {
    if (!provider) {
      return true;
    }
    if (record.providerId !== provider.providerId || record.modelId !== provider.modelId || record.modelVersion !== provider.modelVersion) {
      return true;
    }
    if (record.stale === false && record.embeddingDimension <= 0) {
      return true;
    }
    if (!record.requestLength || record.requestLength < 0) {
      return true;
    }
    return record.stale;
  }

  private materializeEmbedding(document: SearchDocument, provider: SearchEmbeddingAdapter): SearchDocumentEmbeddingRecord {
    const request = textForSemanticRequest(document, Math.min(
      this.state.maxEmbeddingInputCharacters,
      provider.maxInputCharacters,
    ));
    const vector = vectorFromProvider(provider, request.text);
    const requestHash = createHash("sha256").update(stableStringify(request)).digest("hex");

    const embedding: SearchDocumentEmbeddingRecord = {
      documentId: document.documentId,
      sourceEnvelopeId: document.sourceEnvelopeId,
      providerId: provider.providerId,
      modelId: provider.modelId,
      modelVersion: provider.modelVersion,
      requestHash,
      requestLength: request.text.length,
      truncated: request.truncated,
      embeddingDimension: vector.length,
      createdAt: new Date().toISOString(),
      vector,
      stale: false,
    };

    this.state.embeddings.set(document.documentId, embedding);
    return embedding;
  }

  private getEmbedding(document: SearchDocument, provider: SearchEmbeddingAdapter): SearchDocumentEmbeddingRecord {
    const existing = this.state.embeddings.get(document.documentId);
    if (existing) {
      const expectedRequest = textForSemanticRequest(document, Math.min(this.state.maxEmbeddingInputCharacters, provider.maxInputCharacters));
      const expectedHash = createHash("sha256").update(stableStringify(expectedRequest)).digest("hex");
      const matching = !this.isDocumentEmbeddingStale(existing, provider)
        && existing.requestHash === expectedHash
        && existing.requestLength === expectedRequest.text.length;
      if (matching) {
        return existing;
      }
    }

    return this.materializeEmbedding(document, provider);
  }

  private searchDocuments(
    documents: SearchDocument[],
    parsedQuery: ParsedSearchQuery,
    opts?: SearchQueryExecution,
  ): SearchQueryResult {
    const limit = opts?.limit ?? parsedQuery.limit;
    const sort = opts?.sort ?? parsedQuery.sort;
    const page = opts?.page;
    const resolvedOffset = opts?.offset !== undefined
      ? opts.offset
      : (page !== undefined ? Math.max(0, (Math.max(1, page) - 1) * limit) : parsedQuery.offset);
    const offset = Math.max(0, resolvedOffset);
    const maxHighlights = opts?.maxHighlights ?? 3;
    const useSemantic = opts?.useSemantic === true && this.state.semanticEnabled;
    const semanticWeight = Math.max(0, Math.min(1, opts?.semanticWeight ?? this.state.semanticWeight));

    const partitionIds = Array.from(new Set(documents.map((document) => document.partitionId)));

    const preFiltered = documents.filter((document) => {
      for (const filter of parsedQuery.filters) {
        if (!valueMatchesFilter(document, filter)) {
          return false;
        }
      }

      for (const phrase of parsedQuery.phrases) {
        if (!document.textBlob.includes(phrase)) {
          return false;
        }
      }

      for (const term of parsedQuery.terms) {
        if (!document.textBlob.includes(term)) {
          return false;
        }
      }

      for (const excluded of parsedQuery.excludedTerms) {
        if (excluded && document.textBlob.includes(excluded)) {
          return false;
        }
      }

      return true;
    });

    let queryVector: readonly number[] | null = null;
    if (useSemantic && this.state.semanticProvider) {
      try {
        const request = textForQueryEmbedding(parsedQuery, Math.min(this.state.maxEmbeddingInputCharacters, this.state.semanticProvider.maxInputCharacters));
        queryVector = vectorFromProvider(this.state.semanticProvider, request.text);
      } catch {
        queryVector = null;
      }
    }

    const semanticEnabled = Boolean(useSemantic && this.state.semanticProvider && queryVector);

    const ranked = preFiltered.map((document) => {
      const lexicalScore = scoreDocument(document, parsedQuery);
      let semanticScore = 0;
      if (semanticEnabled && this.state.semanticProvider) {
        try {
          const embedding = this.getEmbedding(document, this.state.semanticProvider);
          semanticScore = cosineSimilarity(queryVector!, embedding.vector);
        } catch {
          semanticScore = 0;
        }
      }
      const combined = semanticEnabled
        ? (lexicalScore + (semanticScore * 10)) * (1 + semanticWeight)
        : lexicalScore;
      return {
        document,
        score: combined,
        matchedTerms: [...parsedQuery.terms, ...parsedQuery.phrases],
        matchedFilters: parsedQuery.filters,
        highlights: createHighlights(document.textBlob, parsedQuery.terms, parsedQuery.phrases, maxHighlights),
      } satisfies SearchResultHit;
    });

    const sorted = ranked.sort((left, right) => {
      if (sort === "recent") {
        return Date.parse(right.document.indexedAt) - Date.parse(left.document.indexedAt);
      }
      if (right.score !== left.score) {
        return right.score - left.score;
      }
      return Date.parse(right.document.indexedAt) - Date.parse(left.document.indexedAt);
    });

    const end = Math.min(offset + limit, sorted.length);
    return {
      partitionIds,
      query: parsedQuery,
      sort,
      total: sorted.length,
      returned: Math.max(0, end - offset),
      offset,
      limit,
      hits: sorted.slice(offset, end),
    };
  }
}
