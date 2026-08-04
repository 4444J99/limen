import {
  createCipheriv,
  createDecipheriv,
  createHash,
  randomBytes,
  randomUUID,
} from "node:crypto";

export const INGEST_VERSION = "eta-01-ingest-v1";
export const DEFAULT_MAX_PAYLOAD_BYTES = 4_194_304;
export const DEFAULT_ALLOWED_MEDIA_TYPES = [
  "application/json",
  "application/xml",
  "application/pdf",
  "text/plain",
  "text/markdown",
  "text/csv",
  "application/octet-stream",
] as const;
export const ETA02_COMMAND_VERSION = "eta-02-domain-command-v1";
export const ETA03_CUSTODY_VERSION = "eta-03-custody-v1";

export type IngestClassification = "private" | "confidential" | "restricted";
export type SourceType = "email" | "chat" | "doc" | "calendar" | "manual" | "api" | "other";

export interface SourceIdentity {
  sourceId: string;
  sourceType: SourceType;
  partitionId: string;
  sourceKey?: string;
}

export interface SourceCursor {
  key: string;
  scope: string;
  value: Record<string, unknown>;
  observedAt: string;
}

export interface SourceEnvelopeInput {
  source: SourceIdentity;
  externalId: string;
  revision: number;
  cursor: SourceCursor;
  payload: unknown;
  mediaType: string;
  classification: IngestClassification;
  provenance: Record<string, unknown>;
  envelopeType?: string;
  observedAt?: string;
  createdAt?: string;
}

export interface SourceEnvelope {
  envelopeId: string;
  sourceId: string;
  sourceType: SourceType;
  partitionId: string;
  sourceKey?: string;
  externalId: string;
  revision: number;
  cursor: SourceCursor;
  checksum: string;
  mediaType: string;
  observedAt: string;
  createdAt: string;
  payloadSizeBytes: number;
  classification: IngestClassification;
  provenance: Record<string, unknown>;
  envelopeType: string;
  payload: unknown;
  sequence: number;
}

export interface SourceEnvelopeAdmissionError {
  field: string;
  reason: string;
}

export interface SourceEnvelopeAdmissionResult {
  accepted: boolean;
  errors: SourceEnvelopeAdmissionError[];
  envelope?: SourceEnvelope;
}

export interface SourceEnvelopeAppendResult {
  envelope: SourceEnvelope;
  duplicated: boolean;
}

export interface IngestLedgerState {
  envelopes: readonly SourceEnvelope[];
  cursors: Record<string, SourceCursor>;
}

export interface IngestLedgerOptions {
  maxPayloadBytes?: number;
  allowedMediaTypes?: readonly string[];
  requireProvenance?: boolean;
}

export interface SourceLinkProposal {
  sourceEnvelopeId: string;
  reason: "checksum_match" | "title_similarity";
  confidence: "low" | "medium" | "high";
  evidence: Record<string, unknown>;
}

export interface DomainIngestionCommand {
  commandId: string;
  commandVersion: string;
  commandType: "ingest.normalized";
  sourceEnvelopeId: string;
  sourceId: string;
  partitionId: string;
  envelopeRevision: number;
  cursorKey: string;
  cursorScope: string;
  classification: IngestClassification;
  mediaType: string;
  normalizedPayload: Record<string, unknown>;
  checksum: string;
  createdAt: string;
}

export interface SourceNormalizationReceipt {
  status: "accepted" | "duplicate" | "probable_match" | "quarantined";
  sourceEnvelopeId: string;
  statusReason: string;
  command?: DomainIngestionCommand;
  duplicateOf?: string;
  linkProposals: SourceLinkProposal[];
  diagnostics: string[];
  receiptHash: string;
  normalizationVersion: "eta-02-v1";
}

export interface IngestionProcessorOptions {
  maxDiagnostics?: number;
}

export interface ArtifactCustodyRecord {
  artifactId: string;
  sourceEnvelopeId: string;
  sourceId: string;
  partitionId: string;
  address: string;
  custodyVersion: "eta-03-v1";
  algorithm: string;
  iv: string;
  tag: string;
  ciphertext: string;
  checksum: string;
  mediaType: string;
  plaintextBytes: number;
  classification: IngestClassification;
  createdAt: string;
  retained: boolean;
}

export interface ArtifactCustodyInput {
  sourceEnvelope: SourceEnvelope;
  payload: unknown;
  masterKey: string;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stableStringify(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(",")}]`;
  }
  const entries = Object.entries(value as Record<string, unknown>).sort(([left], [right]) => left.localeCompare(right));
  return `{${entries.map(([key, nestedValue]) => `${JSON.stringify(key)}:${stableStringify(nestedValue)}`).join(",")}}`;
}

function payloadChecksum(payload: unknown): string {
  return createHash("sha256").update(stableStringify(payload)).digest("hex");
}

function payloadBytes(payload: unknown): number {
  return new TextEncoder().encode(stableStringify(payload)).byteLength;
}

function deepCopy<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function keyForCursor(sourceId: string, scope: string, key: string): string {
  return `${sourceId}::${scope}::${key}`;
}

function normalizeSourceIdentity(source: SourceIdentity): SourceIdentity {
  return {
    sourceId: String(source.sourceId || "").trim(),
    sourceType: source.sourceType,
    partitionId: String(source.partitionId || "").trim(),
    sourceKey: source.sourceKey?.trim(),
  };
}

function normalizeCursor(input: SourceCursor): SourceCursor {
  return {
    key: String(input.key || "global").trim() || "global",
    scope: String(input.scope || "global").trim() || "global",
    value: isObject(input.value) ? input.value : {},
    observedAt: input.observedAt || new Date().toISOString(),
  };
}

function textValue(value: unknown): string {
  if (typeof value === "string") {
    return value.trim().toLowerCase();
  }
  return "";
}

function suspiciousPayloadReasons(payload: unknown): string[] {
  const reasons: string[] = [];
  const visit = (candidate: unknown, path = "$"): void => {
    if (typeof candidate === "string") {
      const lowered = candidate.toLowerCase();
      if (lowered.includes("<script")) {
        reasons.push(`hostile string at ${path}: script tag`);
      }
      if (lowered.includes("javascript:")) {
        reasons.push(`hostile string at ${path}: javascript scheme`);
      }
      if (/<\w+\s*=/.test(lowered)) {
        reasons.push(`hostile markup at ${path}`);
      }
      return;
    }
    if (Array.isArray(candidate)) {
      candidate.forEach((entry, index) => visit(entry, `${path}[${index}]`));
      return;
    }
    if (candidate && typeof candidate === "object") {
      for (const [key, value] of Object.entries(candidate as Record<string, unknown>)) {
        visit(value, `${path}.${key}`);
      }
    }
  };
  visit(payload);
  return reasons;
}

function deterministicCommandId(sourceEnvelopeId: string, revision: number): string {
  return createHash("sha256")
    .update(`${sourceEnvelopeId}:${revision}:${ETA02_COMMAND_VERSION}`)
    .digest("hex")
    .slice(0, 16);
}

function normalizePayloadForCommand(payload: unknown): Record<string, unknown> {
  if (payload === null || payload === undefined) {
    return {};
  }
  if (Array.isArray(payload)) {
    return { items: payload.length };
  }
  if (typeof payload !== "object") {
    return { value: payload };
  }

  const normalized: Record<string, unknown> = {};
  const typed = payload as Record<string, unknown>;
  for (const key of Object.keys(typed).sort()) {
    const value = typed[key];
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean" || value === null) {
      normalized[key] = value;
    } else if (Array.isArray(value)) {
      normalized[key] = value.map((entry) => (typeof entry === "object" ? "object" : String(entry)));
    } else if (value && typeof value === "object") {
      normalized[key] = JSON.parse(stableStringify(value));
    }
  }
  return normalized;
}

function similarText(left: unknown, right: unknown): number {
  const leftText = textValue(left);
  const rightText = textValue(right);
  if (!leftText || !rightText) {
    return 0;
  }
  if (leftText === rightText) {
    return 1;
  }
  if (leftText.includes(rightText) || rightText.includes(leftText)) {
    return 0.72;
  }
  return 0;
}

function proposalEvidence(candidate: SourceEnvelope): Record<string, unknown> {
  return {
    candidateId: candidate.envelopeId,
    checksum: candidate.checksum,
    mediaType: candidate.mediaType,
    observedAt: candidate.observedAt,
    partitionId: candidate.partitionId,
  };
}

function buildLinkProposals(current: SourceEnvelope, others: SourceEnvelope[]): SourceLinkProposal[] {
  const proposals: SourceLinkProposal[] = [];
  for (const other of others) {
    if (other.envelopeId === current.envelopeId) {
      continue;
    }
    if (other.checksum === current.checksum) {
      proposals.push({
        sourceEnvelopeId: other.envelopeId,
        reason: "checksum_match",
        confidence: "high",
        evidence: proposalEvidence(other),
      });
      continue;
    }

    const titleScore = Math.max(
      similarText((current.payload as Record<string, unknown>)?.["title"], (other.payload as Record<string, unknown>)?.["title"]),
      similarText((current.payload as Record<string, unknown>)?.["subject"], (other.payload as Record<string, unknown>)?.["subject"]),
      similarText((current.payload as Record<string, unknown>)?.["body"], (other.payload as Record<string, unknown>)?.["body"]),
    );
    if (titleScore > 0.7) {
      proposals.push({
        sourceEnvelopeId: other.envelopeId,
        reason: "title_similarity",
        confidence: titleScore > 0.95 ? "high" : titleScore > 0.8 ? "medium" : "low",
        evidence: {
          ...proposalEvidence(other),
          similarity: titleScore,
        },
      });
    }
  }
  return proposals.slice(0, 3);
}

function boundedDiagnostics(items: string[], maxItems: number): string[] {
  return items.slice(0, maxItems);
}

function deriveKey(masterKey: string): Buffer {
  return createHash("sha256").update(masterKey).digest();
}

function serializeArtifactPayload(payload: unknown): string {
  return stableStringify(payload);
}

export function validateSourceEnvelopeInput(
  input: SourceEnvelopeInput,
  options: IngestLedgerOptions = {},
): SourceEnvelopeAdmissionResult {
  const errors: SourceEnvelopeAdmissionError[] = [];
  const maxPayloadBytes = options.maxPayloadBytes ?? DEFAULT_MAX_PAYLOAD_BYTES;
  const allowedMediaTypes = new Set(options.allowedMediaTypes ?? DEFAULT_ALLOWED_MEDIA_TYPES);
  const requireProvenance = options.requireProvenance ?? true;

  const source = normalizeSourceIdentity(input.source);

  if (!source.sourceId) {
    errors.push({ field: "source.sourceId", reason: "source identity is required" });
  }
  if (!source.partitionId) {
    errors.push({ field: "source.partitionId", reason: "partition is required" });
  }
  if (!source.sourceType) {
    errors.push({ field: "source.sourceType", reason: "source type is required" });
  }

  const revision = Number(input.revision);
  if (!Number.isInteger(revision) || revision < 1) {
    errors.push({ field: "revision", reason: "revision must be a positive integer" });
  }

  if (!input.externalId || !String(input.externalId).trim()) {
    errors.push({ field: "externalId", reason: "external ID is required" });
  }

  const normalizedObservedAt = input.observedAt || new Date().toISOString();
  if (Number.isNaN(Date.parse(normalizedObservedAt))) {
    errors.push({ field: "observedAt", reason: "observedAt must be ISO-8601" });
  }

  const normalizedCursor = normalizeCursor(input.cursor);
  if (!normalizedCursor.key) {
    errors.push({ field: "cursor.key", reason: "cursor key is required" });
  }
  if (!normalizedCursor.scope) {
    errors.push({ field: "cursor.scope", reason: "cursor scope is required" });
  }

  const mediaType = String(input.mediaType || "").toLowerCase();
  if (!mediaType) {
    errors.push({ field: "mediaType", reason: "media type is required" });
  }
  if (mediaType && !allowedMediaTypes.has(mediaType)) {
    errors.push({ field: "mediaType", reason: `media type ${mediaType} is unsupported` });
  }

  const incomingBytes = payloadBytes(input.payload);
  if (!Number.isFinite(incomingBytes) || incomingBytes < 0) {
    errors.push({ field: "payload", reason: "payload is invalid" });
  }
  if (incomingBytes > maxPayloadBytes) {
    errors.push({ field: "payload", reason: `payload exceeds max size ${maxPayloadBytes}` });
  }

  if (!("private" === input.classification || "confidential" === input.classification || "restricted" === input.classification)) {
    errors.push({ field: "classification", reason: "classification must be private, confidential, or restricted" });
  }

  if (requireProvenance) {
    if (!isObject(input.provenance)) {
      errors.push({ field: "provenance", reason: "provenance must be an object" });
    }
    if (isObject(input.provenance) && Object.keys(input.provenance).length === 0) {
      errors.push({ field: "provenance", reason: "provenance must include at least one key" });
    }
  }

  const accepted = errors.length === 0;
  if (!accepted) {
    return { accepted: false, errors };
  }

  const envelope: SourceEnvelope = {
    envelopeId: randomUUID(),
    sourceId: source.sourceId,
    sourceType: source.sourceType,
    partitionId: source.partitionId,
    sourceKey: source.sourceKey,
    externalId: String(input.externalId).trim(),
    revision,
    cursor: normalizedCursor,
    checksum: payloadChecksum(input.payload),
    mediaType,
    observedAt: normalizedObservedAt,
    createdAt: input.createdAt || new Date().toISOString(),
    payloadSizeBytes: payloadBytes(input.payload),
    classification: input.classification,
    provenance: deepCopy(input.provenance || {}),
    envelopeType: input.envelopeType || "raw",
    payload: deepCopy(input.payload),
    sequence: 0,
  };

  return { accepted: true, errors: [], envelope };
}

export function buildRawSourceEnvelope(input: SourceEnvelopeInput, options?: IngestLedgerOptions): SourceEnvelope {
  const result = validateSourceEnvelopeInput(input, options);
  if (!result.accepted || !result.envelope) {
    const first = result.errors[0];
    throw new Error(`invalid source envelope: ${first ? `${first.field} ${first.reason}` : "unknown reason"}`);
  }
  return result.envelope;
}

export class SourceEnvelopeLedger {
  private nextSequence = 0;
  private readonly envelopes: SourceEnvelope[] = [];
  private readonly cursorIndex = new Map<string, SourceCursor>();

  public constructor(private readonly options: IngestLedgerOptions = {}) {}

  public appendEnvelope(input: SourceEnvelopeInput): SourceEnvelopeAppendResult {
    const envelope = buildRawSourceEnvelope(input, this.options);

    const duplicate = this.findDuplicate(envelope);
    if (duplicate) {
      return {
        envelope: deepCopy(duplicate),
        duplicated: true,
      };
    }

    envelope.sequence = this.nextSequence++;
    this.envelopes.push(deepCopy(envelope));
    this.setCursor(envelope.sourceId, envelope.cursor);

    return {
      envelope: deepCopy(envelope),
      duplicated: false,
    };
  }

  public replayAll(): SourceEnvelope[] {
    return this.envelopes.map((envelope) => deepCopy(envelope));
  }

  public replayBySource(sourceId: string): SourceEnvelope[] {
    return this.envelopes
      .filter((envelope) => envelope.sourceId === sourceId)
      .map((envelope) => deepCopy(envelope));
  }

  public cursorFor(sourceId: string, key = "global", scope = "global"): SourceCursor | null {
    const hit = this.cursorIndex.get(keyForCursor(sourceId, scope, key));
    return hit ? deepCopy(hit) : null;
  }

  public snapshot(): IngestLedgerState {
    return {
      envelopes: this.replayAll(),
      cursors: Object.fromEntries(Array.from(this.cursorIndex.entries()).map(([k, v]) => [k, deepCopy(v)])),
    };
  }

  private setCursor(sourceId: string, cursor: SourceCursor): void {
    const existing = this.cursorIndex.get(keyForCursor(sourceId, cursor.scope, cursor.key));
    if (existing && Date.parse(existing.observedAt) > Date.parse(cursor.observedAt)) {
      return;
    }
    this.cursorIndex.set(keyForCursor(sourceId, cursor.scope, cursor.key), deepCopy(cursor));
  }

  private findDuplicate(candidate: SourceEnvelope): SourceEnvelope | undefined {
    return this.envelopes.find((envelope) =>
      envelope.sourceId === candidate.sourceId &&
      envelope.externalId === candidate.externalId &&
      envelope.revision === candidate.revision,
    );
  }
}

export class IngestionProcessor {
  private readonly receipts: SourceNormalizationReceipt[] = [];
  private readonly options: IngestionProcessorOptions;

  public constructor(
    private readonly ledger: SourceEnvelopeLedger,
    options?: IngestionProcessorOptions,
  ) {
    this.options = {
      maxDiagnostics: 8,
      ...options,
    };
  }

  public process(input: SourceEnvelopeInput): SourceNormalizationReceipt {
    const maxDiagnostics = this.options.maxDiagnostics ?? 8;
    const append = this.ledger.appendEnvelope(input);

    if (append.duplicated) {
      const receipt = this.makeReceipt({
        status: "duplicate",
        sourceEnvelopeId: append.envelope.envelopeId,
        statusReason: "Exact duplicate for source-id, external-id, and revision",
        linkProposals: [],
        diagnostics: [],
        command: undefined,
        duplicateOf: append.envelope.envelopeId,
      });
      this.receipts.push(receipt);
      return receipt;
    }

    const diagnostics = boundedDiagnostics([
      ...suspiciousPayloadReasons(append.envelope.payload),
      ...this.validatePayloadSemantics(append.envelope),
    ], maxDiagnostics);

    if (diagnostics.length > 0) {
      const receipt = this.makeReceipt({
        status: "quarantined",
        sourceEnvelopeId: append.envelope.envelopeId,
        statusReason: diagnostics[0] || "payload quarantined",
        linkProposals: [],
        diagnostics,
        command: undefined,
      });
      this.receipts.push(receipt);
      return receipt;
    }

    const proposals = buildLinkProposals(
      append.envelope,
      this.ledger.replayBySource(append.envelope.sourceId),
    );
    const command = buildDomainCommand(append.envelope);
    const status = proposals.length > 0 ? "probable_match" : "accepted";
    const reason = status === "accepted" ? "Payload normalized and accepted" : "Potential duplicate relationship detected";

    const receipt = this.makeReceipt({
      status,
      sourceEnvelopeId: append.envelope.envelopeId,
      statusReason: reason,
      linkProposals: proposals,
      diagnostics: [],
      command,
    });
    this.receipts.push(receipt);
    return receipt;
  }

  public listReceipts(): SourceNormalizationReceipt[] {
    return this.receipts.map((receipt) => deepCopy(receipt));
  }

  private validatePayloadSemantics(envelope: SourceEnvelope): string[] {
    const payload = envelope.payload;
    const findings: string[] = [];
    if (payload === null || payload === undefined) {
      findings.push("payload missing");
    }
    if (typeof payload === "string" && payload.trim().length === 0) {
      findings.push("payload body is empty string");
    }
    return findings;
  }

  private makeReceipt(input: Omit<SourceNormalizationReceipt, "receiptHash" | "normalizationVersion"> & { diagnostics: string[] }): SourceNormalizationReceipt {
    const payload = {
      normalizationVersion: "eta-02-v1",
      status: input.status,
      sourceEnvelopeId: input.sourceEnvelopeId,
      statusReason: input.statusReason,
      duplicateOf: input.duplicateOf,
      command: input.command ? { ...input.command } : undefined,
      linkProposals: input.linkProposals,
      diagnostics: input.diagnostics,
    };
    const receiptHash = createHash("sha256").update(stableStringify(payload)).digest("hex");
    return {
      ...input,
      normalizationVersion: "eta-02-v1",
      receiptHash,
    };
  }
}

function buildDomainCommand(envelope: SourceEnvelope): DomainIngestionCommand {
  return {
    commandId: deterministicCommandId(envelope.envelopeId, envelope.sequence),
    commandVersion: ETA02_COMMAND_VERSION,
    commandType: "ingest.normalized",
    sourceEnvelopeId: envelope.envelopeId,
    sourceId: envelope.sourceId,
    partitionId: envelope.partitionId,
    envelopeRevision: envelope.revision,
    cursorKey: envelope.cursor.key,
    cursorScope: envelope.cursor.scope,
    classification: envelope.classification,
    mediaType: envelope.mediaType,
    normalizedPayload: normalizePayloadForCommand(envelope.payload),
    checksum: envelope.checksum,
    createdAt: envelope.createdAt,
  };
}

function decryptArtifact(record: ArtifactCustodyRecord, key: string): string {
  const keyBytes = deriveKey(key);
  const decipher = createDecipheriv(record.algorithm, keyBytes, Buffer.from(record.iv, "hex"));
  decipher.setAuthTag(Buffer.from(record.tag, "hex"));
  const ciphertext = Buffer.from(record.ciphertext, "base64");
  const plaintext = Buffer.concat([decipher.update(ciphertext), decipher.final()]);
  return plaintext.toString("utf8");
}

export class ArtifactCustodyVault {
  private readonly records = new Map<string, ArtifactCustodyRecord>();

  public archive(input: ArtifactCustodyInput): ArtifactCustodyRecord {
    const key = deriveKey(input.masterKey);
    if (!input.masterKey) {
      throw new Error("master key required");
    }
    const algorithm = "aes-256-gcm";
    const iv = randomBytes(12);
    const cipher = createCipheriv(algorithm, key, iv);
    const serialized = serializeArtifactPayload(input.payload);
    const encrypted = Buffer.concat([cipher.update(serialized, "utf8"), cipher.final()]);
    const tag = cipher.getAuthTag();
    const checksum = payloadChecksum(serialized);
    const address = createHash("sha256")
      .update(Buffer.concat([
        encrypted,
        Buffer.from(input.sourceEnvelope.sourceId),
        Buffer.from(input.sourceEnvelope.externalId),
      ]))
      .digest("hex");

    const record: ArtifactCustodyRecord = {
      artifactId: randomUUID(),
      sourceEnvelopeId: input.sourceEnvelope.envelopeId,
      sourceId: input.sourceEnvelope.sourceId,
      partitionId: input.sourceEnvelope.partitionId,
      address,
      custodyVersion: "eta-03-v1",
      algorithm,
      iv: iv.toString("hex"),
      tag: tag.toString("hex"),
      ciphertext: encrypted.toString("base64"),
      checksum,
      mediaType: input.sourceEnvelope.mediaType,
      plaintextBytes: Buffer.byteLength(serialized, "utf8"),
      classification: input.sourceEnvelope.classification,
      createdAt: new Date().toISOString(),
      retained: true,
    };
    this.records.set(record.address, record);
    return deepCopy(record);
  }

  public retrieve(address: string, masterKey: string): string {
    const record = this.records.get(address);
    if (!record) {
      throw new Error(`artifact ${address} not found`);
    }
    return decryptArtifact(record, masterKey);
  }

  public exists(address: string): boolean {
    return this.records.has(address);
  }

  public listBySource(sourceId: string): ArtifactCustodyRecord[] {
    return Array.from(this.records.values())
      .filter((record) => record.sourceId === sourceId)
      .map(deepCopy);
  }

  public snapshot(): ArtifactCustodyRecord[] {
    return Array.from(this.records.values()).map(deepCopy);
  }
}

export function replaySourceEnvelopes(ledger: SourceEnvelopeLedger, sourceId?: string): SourceEnvelope[] {
  return sourceId ? ledger.replayBySource(sourceId) : ledger.replayAll();
}
