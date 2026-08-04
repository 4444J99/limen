import { createHash, randomUUID } from "node:crypto";

export const MU01_CONNECTORS_VERSION = "mu-01-connectors-v1";

export type ConnectorAction = "discover" | "authorize" | "pull" | "push" | "revoke" | "health" | "dryRun";
export type ConnectorScope = "read" | "write" | "admin" | "none";
export type ConnectorLifecycleState = "discovered" | "authorized" | "enabled" | "disabled" | "revoked";

export interface ConnectorCapability {
  action: ConnectorAction;
  scope: ConnectorScope;
  description: string;
}

export interface ConnectorRateLimit {
  windowMs?: number;
  maxRequests?: number;
  maxConsecutiveFailures?: number;
  maxRetries?: number;
}

export interface ConnectorManifest {
  connectorId: string;
  connectorType: string;
  name: string;
  version: string;
  description: string;
  sourceDataClasses: readonly string[];
  capabilities: readonly ConnectorCapability[];
  supportsDryRun: boolean;
  requiresAuth: boolean;
  rateLimit: ConnectorRateLimit;
  redactionKeys?: readonly string[];
}

export interface ConnectorManifestValidation {
  valid: boolean;
  errors: string[];
}

export interface ConnectorCursorInput {
  connectorId: string;
  partitionId: string;
  key: string;
  value: string;
  observedAt?: string;
}

export interface ConnectorCursor {
  connectorId: string;
  partitionId: string;
  key: string;
  value: string;
  sequence: number;
  observedAt: string;
}

export interface ConnectorOperationContext {
  actorId: string;
  partitionId?: string;
  requestId?: string;
  cursor?: ConnectorCursor;
  payload?: Record<string, unknown>;
  dryRun?: boolean;
}

export interface ConnectorOperationResult {
  status: "ok" | "skipped";
  records?: number;
  cursor?: ConnectorCursorInput;
  diagnostics?: Record<string, unknown>;
}

export interface ConnectorAdapter {
  manifest: ConnectorManifest;
  discover?(context: ConnectorOperationContext): ConnectorOperationResult | Promise<ConnectorOperationResult>;
  authorize?(context: ConnectorOperationContext): ConnectorOperationResult | Promise<ConnectorOperationResult>;
  pull?(context: ConnectorOperationContext): ConnectorOperationResult | Promise<ConnectorOperationResult>;
  push?(context: ConnectorOperationContext): ConnectorOperationResult | Promise<ConnectorOperationResult>;
  revoke?(context: ConnectorOperationContext): ConnectorOperationResult | Promise<ConnectorOperationResult>;
  health?(context: ConnectorOperationContext): ConnectorOperationResult | Promise<ConnectorOperationResult>;
  dryRun?(context: ConnectorOperationContext): ConnectorOperationResult | Promise<ConnectorOperationResult>;
}

export interface ConnectorErrorOptions {
  retryable?: boolean;
  code?: string;
}

export class ConnectorError extends Error {
  public readonly retryable: boolean;
  public readonly code?: string;

  public constructor(message: string, options: ConnectorErrorOptions = {}) {
    super(message);
    this.retryable = options.retryable ?? false;
    this.code = options.code;
  }
}

export interface ConnectorLifecycleTransition {
  from: ConnectorLifecycleState;
  to: ConnectorLifecycleState;
  by: string;
  reason: string;
  at: string;
}

export interface ConnectorRecord {
  manifest: ConnectorManifest;
  state: ConnectorLifecycleState;
  registeredAt: string;
  updatedAt: string;
  transitions: ConnectorLifecycleTransition[];
}

export interface RateDecision {
  allowed: boolean;
  reason?: string;
  retryAfterMs?: number;
}

interface RateState {
  windowStart: number;
  requests: number;
  consecutiveFailures: number;
}

export interface ConnectorExecutionReceipt {
  connectorId: string;
  action: ConnectorAction;
  requestId: string;
  status: "success" | "skipped" | "failed" | "rejected";
  attempts: number;
  redactedDiagnostics?: string;
  dryRun: boolean;
  startedAt: string;
  finishedAt: string;
  records?: number;
  reason?: string;
  idempotentReplay: boolean;
  receiptHash: string;
}

interface ExecutionCacheKey {
  connectorId: string;
  action: ConnectorAction;
  key: string;
}

export interface ConnectorContractContext {
  registry: ConnectorRegistry;
  cursorLedger: ConnectorCursorLedger;
  rateLimiter: ConnectorRateLimiter;
  runtime: ConnectorRuntime;
}

export interface ConnectorContract {
  contractId: string;
  description: string;
  run(context: ConnectorContractContext): void;
}

export interface ContractRunResult {
  contractId: string;
  passed: boolean;
  description: string;
  message?: string;
}

export interface ContractSuiteResult {
  passed: boolean;
  runs: ContractRunResult[];
}

const DEFAULT_RATE_LIMIT: ConnectorRateLimit = {
  windowMs: 60_000,
  maxRequests: 120,
  maxConsecutiveFailures: 5,
  maxRetries: 3,
};

const REDACTION_KEYS = new Set([
  "token",
  "secret",
  "password",
  "apiKey",
  "credential",
  "authorization",
  "x-api-key",
  "client_secret",
  "access_token",
]);

const TRANSITIONS: Record<ConnectorLifecycleState, ConnectorLifecycleState[]> = {
  discovered: ["authorized", "enabled", "disabled", "revoked"],
  authorized: ["enabled", "disabled", "revoked"],
  enabled: ["disabled", "revoked"],
  disabled: ["authorized", "enabled", "revoked"],
  revoked: [],
};

const REQUIRED_CAPABILITIES_BY_ACTION: Record<ConnectorAction, ConnectorLifecycleState[]> = {
  discover: ["discovered", "authorized", "enabled", "disabled"],
  authorize: ["discovered", "disabled", "enabled", "authorized"],
  pull: ["authorized", "enabled"],
  push: ["authorized", "enabled"],
  revoke: ["discovered", "authorized", "enabled", "disabled"],
  health: ["discovered", "authorized", "enabled", "disabled"],
  dryRun: ["authorized", "enabled", "disabled"],
};

function stableStringify(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(",")}]`;
  }
  const entries = Object.entries(value as Record<string, unknown>).sort(([left], [right]) => left.localeCompare(right));
  return `{${entries
    .map(([key, entry]) => `${JSON.stringify(key)}:${stableStringify(entry)}`)
    .join(",")}}`;
}

function nowIso(): string {
  return new Date().toISOString();
}

function parseObservedAt(input?: string): string {
  if (!input) {
    return nowIso();
  }
  const parsed = Date.parse(input);
  if (Number.isNaN(parsed)) {
    throw new Error("invalid observedAt");
  }
  return new Date(parsed).toISOString();
}

function makeFingerprint(value: unknown): string {
  return createHash("sha256").update(stableStringify(value)).digest("hex");
}

function isRetryableActionError(error: unknown): boolean {
  if (error instanceof ConnectorError) {
    return error.retryable;
  }
  const candidate = error instanceof Error ? error.message : String(error);
  return candidate.includes("retry") || candidate.includes("temporary") || candidate.includes("429");
}

function redactFieldName(field: string): boolean {
  return REDACTION_KEYS.has(field.toLowerCase());
}

function redactValue(value: unknown): unknown {
  if (value === null || typeof value !== "object") {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map(redactValue);
  }
  const redacted: Record<string, unknown> = {};
  for (const [key, val] of Object.entries(value as Record<string, unknown>)) {
    if (redactFieldName(key)) {
      redacted[key] = "***redacted***";
      continue;
    }
    redacted[key] = redactValue(val);
  }
  return redacted;
}

export function validateConnectorManifest(manifest: ConnectorManifest): ConnectorManifestValidation {
  const errors: string[] = [];
  if (!manifest.connectorId?.trim()) {
    errors.push("connectorId is required");
  }
  if (!manifest.name?.trim()) {
    errors.push("name is required");
  }
  if (!manifest.connectorType?.trim()) {
    errors.push("connectorType is required");
  }
  if (!manifest.version?.trim()) {
    errors.push("version is required");
  }
  if (!Array.isArray(manifest.capabilities) || manifest.capabilities.length === 0) {
    errors.push("capabilities must not be empty");
  }
  if (!Array.isArray(manifest.sourceDataClasses)) {
    errors.push("sourceDataClasses must be an array");
  }
  if (!manifest.rateLimit) {
    errors.push("rateLimit is required");
  }
  return { valid: errors.length === 0, errors };
}

export class ConnectorRegistry {
  private connectors = new Map<string, ConnectorRecord>();

  public register(manifest: ConnectorManifest): ConnectorRecord {
    const validation = validateConnectorManifest(manifest);
    if (!validation.valid) {
      throw new Error(`invalid manifest: ${validation.errors.join("; ")}`);
    }

    const now = nowIso();
    const existing = this.connectors.get(manifest.connectorId);
    if (existing) {
      const existingSignature = makeFingerprint(existing.manifest);
      const nextSignature = makeFingerprint(manifest);
      if (existingSignature !== nextSignature) {
        throw new Error(`connector ${manifest.connectorId} already registered with a different manifest`);
      }
      return { ...existing, transitions: existing.transitions.map((entry) => ({ ...entry })) };
    }

    const record: ConnectorRecord = {
      manifest,
      state: "discovered",
      registeredAt: now,
      updatedAt: now,
      transitions: [{
        from: "discovered",
        to: "discovered",
        by: "system",
        reason: "registered",
        at: now,
      }],
    };
    this.connectors.set(manifest.connectorId, record);
    return { ...record, transitions: record.transitions.map((entry) => ({ ...entry })) };
  }

  public get(connectorId: string): ConnectorRecord {
    const record = this.connectors.get(connectorId);
    if (!record) {
      throw new Error(`connector not found: ${connectorId}`);
    }
    return { ...record, transitions: record.transitions.map((entry) => ({ ...entry })) };
  }

  public list(): ConnectorRecord[] {
    return Array.from(this.connectors.values()).map((record) => ({
      ...record,
      transitions: record.transitions.map((entry) => ({ ...entry })),
    }));
  }

  public transition(
    connectorId: string,
    nextState: ConnectorLifecycleState,
    by: string,
    reason: string,
  ): ConnectorRecord {
    const record = this.connectors.get(connectorId);
    if (!record) {
      throw new Error(`connector not found: ${connectorId}`);
    }

    const allowed = TRANSITIONS[record.state] || [];
    if (!allowed.includes(nextState)) {
      throw new Error(`invalid lifecycle transition ${record.state} -> ${nextState}`);
    }

    const now = nowIso();
    const next: ConnectorRecord = {
      ...record,
      state: nextState,
      updatedAt: now,
      transitions: [...record.transitions, {
        from: record.state,
        to: nextState,
        by,
        reason,
        at: now,
      }],
    };
    this.connectors.set(connectorId, next);
    return { ...next, transitions: next.transitions.map((entry) => ({ ...entry })) };
  }

  public canInvoke(connectorId: string, action: ConnectorAction): boolean {
    const record = this.connectors.get(connectorId);
    if (!record) {
      return false;
    }
    return REQUIRED_CAPABILITIES_BY_ACTION[action].includes(record.state);
  }

  public requireActionAllowed(connectorId: string, action: ConnectorAction): void {
    const record = this.connectors.get(connectorId);
    if (!record) {
      throw new Error(`connector not found: ${connectorId}`);
    }

    if (!record.manifest.capabilities.some((cap) => cap.action === action)) {
      throw new Error(`connector ${connectorId} does not declare capability ${action}`);
    }

    if (!REQUIRED_CAPABILITIES_BY_ACTION[action].includes(record.state)) {
      throw new Error(`connector ${connectorId} is not in a valid state for ${action}`);
    }
  }
}

export class ConnectorCursorLedger {
  private cursors = new Map<string, ConnectorCursor>();

  public setCursor(input: ConnectorCursorInput): ConnectorCursor {
    const connectorId = input.connectorId;
    if (!connectorId || !input.partitionId || !input.key) {
      throw new Error("connectorId, partitionId, and key are required");
    }

    const observedAt = parseObservedAt(input.observedAt);
    const observedAtMs = Date.parse(observedAt);
    const current = this.getCursor(connectorId, input.partitionId, input.key);

    if (current && Date.parse(current.observedAt) > observedAtMs) {
      throw new Error("stale cursor update");
    }
    if (current && current.value === input.value) {
      return current;
    }

    const cursor: ConnectorCursor = {
      connectorId,
      partitionId: input.partitionId,
      key: input.key,
      value: input.value,
      sequence: (current?.sequence ?? -1) + 1,
      observedAt,
    };

    this.cursors.set(this.keyFor(cursor.connectorId, cursor.partitionId, cursor.key), cursor);
    return cursor;
  }

  public getCursor(
    connectorId: string,
    partitionId: string,
    key = "default",
  ): ConnectorCursor | null {
    const hit = this.cursors.get(this.keyFor(connectorId, partitionId, key));
    return hit ? { ...hit } : null;
  }

  public list(connectorId?: string): ConnectorCursor[] {
    return Array.from(this.cursors.values())
      .filter((entry) => !connectorId || entry.connectorId === connectorId)
      .map((entry) => ({ ...entry }));
  }

  private keyFor(connectorId: string, partitionId: string, key: string): string {
    return `${connectorId}::${partitionId}::${key}`;
  }
}

export class ConnectorRateLimiter {
  private stateByConnector = new Map<string, Map<string, RateState>>();

  public allow(
    manifest: ConnectorManifest,
    action: ConnectorAction,
  ): RateDecision {
    const now = Date.now();
    const policy = {
      ...DEFAULT_RATE_LIMIT,
      ...manifest.rateLimit,
    };
    const actionBuckets = this.stateByConnector.get(manifest.connectorId)
      || new Map<string, RateState>();
    const state = actionBuckets.get(action) || {
      windowStart: now,
      requests: 0,
      consecutiveFailures: 0,
    };

    if (now - state.windowStart >= (policy.windowMs ?? DEFAULT_RATE_LIMIT.windowMs!)) {
      state.windowStart = now;
      state.requests = 0;
      state.consecutiveFailures = 0;
    }

    const allowed = state.requests < (policy.maxRequests ?? DEFAULT_RATE_LIMIT.maxRequests!);
    if (!allowed) {
      const retryAfterMs = Math.max(0, state.windowStart + (policy.windowMs ?? DEFAULT_RATE_LIMIT.windowMs!) - now);
      actionBuckets.set(action, state);
      this.stateByConnector.set(manifest.connectorId, actionBuckets);
      return {
        allowed: false,
        reason: "rate limit exceeded",
        retryAfterMs,
      };
    }

    state.requests += 1;
    actionBuckets.set(action, state);
    this.stateByConnector.set(manifest.connectorId, actionBuckets);
    return { allowed: true };
  }

  public recordSuccess(manifest: ConnectorManifest): void {
    const actionBuckets = this.stateByConnector.get(manifest.connectorId);
    if (!actionBuckets) {
      return;
    }
    for (const state of actionBuckets.values()) {
      state.consecutiveFailures = 0;
    }
  }

  public recordFailure(manifest: ConnectorManifest): void {
    const actionBuckets = this.stateByConnector.get(manifest.connectorId);
    if (!actionBuckets) {
      return;
    }
    const policy = { ...DEFAULT_RATE_LIMIT, ...manifest.rateLimit };
    for (const state of actionBuckets.values()) {
      state.consecutiveFailures += 1;
      if (state.consecutiveFailures > (policy.maxConsecutiveFailures ?? DEFAULT_RATE_LIMIT.maxConsecutiveFailures!)) {
        state.requests += (policy.maxRequests ?? DEFAULT_RATE_LIMIT.maxRequests!);
      }
    }
  }

  public status(manifest: ConnectorManifest, action: ConnectorAction): RateState {
    const actionBuckets = this.stateByConnector.get(manifest.connectorId);
    const state = actionBuckets?.get(action);
    if (!state) {
      return {
        windowStart: 0,
        requests: 0,
        consecutiveFailures: 0,
      };
    }
    return { ...state };
  }

  public maxRetriesForManifest(manifest: ConnectorManifest): number {
    return manifest.rateLimit.maxRetries ?? DEFAULT_RATE_LIMIT.maxRetries!;
  }
}

export function sanitizeDiagnostics(diagnostics: Record<string, unknown> | undefined): Record<string, unknown> {
  if (!diagnostics) {
    return {};
  }
  return redactValue(diagnostics) as Record<string, unknown>;
}

export class ConnectorRuntime {
  private adapters = new Map<string, ConnectorAdapter>();
  private executionCache = new Map<string, ConnectorExecutionReceipt>();
  private readonly registry: ConnectorRegistry;
  private readonly cursorLedger: ConnectorCursorLedger;
  private readonly rateLimiter: ConnectorRateLimiter;

  public constructor(
    registry: ConnectorRegistry,
    cursorLedger: ConnectorCursorLedger,
    rateLimiter: ConnectorRateLimiter,
  ) {
    this.registry = registry;
    this.cursorLedger = cursorLedger;
    this.rateLimiter = rateLimiter;
  }

  public registerAdapter(adapter: ConnectorAdapter): ConnectorRecord {
    const record = this.registry.register(adapter.manifest);
    this.adapters.set(adapter.manifest.connectorId, adapter);
    return record;
  }

  public async execute(
    connectorId: string,
    action: ConnectorAction,
    context: ConnectorOperationContext,
  ): Promise<ConnectorExecutionReceipt> {
    const startedAt = nowIso();
    const requestId = context.requestId || randomUUID();
    const idempotentKey = this.makeIdempotencyKey(connectorId, action, context.requestId || requestId);
    const cached = this.executionCache.get(idempotentKey);
    if (cached) {
      return {
        ...cached,
        idempotentReplay: true,
      };
    }

    const record = this.registry.get(connectorId);
    this.registry.requireActionAllowed(connectorId, action);

    const decision = this.rateLimiter.allow(record.manifest, action);
    if (!decision.allowed) {
      const receipt: ConnectorExecutionReceipt = {
        connectorId,
        action,
        requestId,
        status: "rejected",
        attempts: 0,
        dryRun: Boolean(context.dryRun),
        startedAt,
        finishedAt: nowIso(),
        reason: decision.reason,
        idempotentReplay: false,
        receiptHash: makeFingerprint({ connectorId, action, requestId, status: "rejected", reason: decision.reason }),
      };
      this.executionCache.set(idempotentKey, receipt);
      return receipt;
    }

    const adapter = this.adapters.get(connectorId);
    if (!adapter) {
      throw new Error(`adapter missing for connector ${connectorId}`);
    }

    const dryRun = Boolean(context.dryRun);
    if (dryRun && !record.manifest.supportsDryRun) {
      const result: ConnectorExecutionReceipt = {
        connectorId,
        action,
        requestId,
        status: "skipped",
        attempts: 1,
        dryRun: true,
        startedAt,
        finishedAt: nowIso(),
        reason: "dry-run disabled",
        idempotentReplay: false,
        receiptHash: makeFingerprint({ connectorId, action, requestId, status: "skipped" }),
      };
      this.executionCache.set(idempotentKey, result);
      return result;
    }

    const fn = this.resolveAction(adapter, action);
    if (!fn) {
      throw new Error(`adapter for ${action} not implemented`);
    }

    const maxAttempts = this.rateLimiter.maxRetriesForManifest(record.manifest) + 1;
    let attempts = 0;
    let lastError: Error | null = null;

    while (attempts < maxAttempts) {
      attempts += 1;
      try {
        const rawResult = await fn(context);
        const output = sanitizeDiagnostics(rawResult.diagnostics);
        const redacted = JSON.stringify(output);

        if (typeof rawResult.cursor !== "undefined") {
          this.cursorLedger.setCursor({
            connectorId,
            partitionId: context.partitionId || "default",
            key: "default",
            value: rawResult.cursor.value,
            observedAt: rawResult.cursor.observedAt,
          });
        }

        const status = rawResult.status === "skipped" ? "skipped" : "success";
        const finishedAt = nowIso();
        const receipt: ConnectorExecutionReceipt = {
          connectorId,
          action,
          requestId,
          status,
          attempts,
          redactedDiagnostics: redacted,
          dryRun,
          startedAt,
          finishedAt,
          records: rawResult.records,
          idempotentReplay: false,
          receiptHash: makeFingerprint({
            connectorId,
            action,
            requestId,
            status,
            startedAt,
            finishedAt,
            records: rawResult.records,
            redacted,
          }),
        };

        this.rateLimiter.recordSuccess(record.manifest);
        this.executionCache.set(idempotentKey, receipt);
        return receipt;
      } catch (error) {
        const safe = error instanceof Error ? error : new Error(String(error));
        lastError = safe;
        if (attempts < maxAttempts && isRetryableActionError(safe)) {
          continue;
        }
        break;
      }
    }

    this.rateLimiter.recordFailure(record.manifest);
    const finishedAt = nowIso();
    const payload = sanitizeDiagnostics({ error: lastError?.message || "unknown failure" });
    const finalStatus: ConnectorExecutionReceipt = {
      connectorId,
      action,
      requestId,
      status: "failed",
      attempts,
      redactedDiagnostics: JSON.stringify(payload),
      dryRun,
      startedAt,
      finishedAt,
      reason: lastError?.message || "execution failed",
      idempotentReplay: false,
      receiptHash: makeFingerprint({
        connectorId,
        action,
        requestId,
        status: "failed",
        reason: lastError?.message,
        attempts,
      }),
    };
    this.executionCache.set(idempotentKey, finalStatus);
    return finalStatus;
  }

  public executeDiscover(connectorId: string, context: ConnectorOperationContext): Promise<ConnectorExecutionReceipt> {
    return this.execute(connectorId, "discover", context);
  }

  public executeAuthorize(connectorId: string, context: ConnectorOperationContext): Promise<ConnectorExecutionReceipt> {
    return this.execute(connectorId, "authorize", context);
  }

  public executePull(connectorId: string, context: ConnectorOperationContext): Promise<ConnectorExecutionReceipt> {
    return this.execute(connectorId, "pull", context);
  }

  public executePush(connectorId: string, context: ConnectorOperationContext): Promise<ConnectorExecutionReceipt> {
    return this.execute(connectorId, "push", context);
  }

  public executeRevoke(connectorId: string, context: ConnectorOperationContext): Promise<ConnectorExecutionReceipt> {
    return this.execute(connectorId, "revoke", context);
  }

  public executeHealth(connectorId: string, context: ConnectorOperationContext): Promise<ConnectorExecutionReceipt> {
    return this.execute(connectorId, "health", context);
  }

  public executeDryRun(connectorId: string, context: ConnectorOperationContext): Promise<ConnectorExecutionReceipt> {
    return this.execute(connectorId, "dryRun", context);
  }

  private resolveAction(adapter: ConnectorAdapter, action: ConnectorAction):
    ((context: ConnectorOperationContext) => ConnectorOperationResult | Promise<ConnectorOperationResult>) | null {
    if (action === "discover") {
      return adapter.discover ? adapter.discover.bind(adapter) : null;
    }
    if (action === "authorize") {
      return adapter.authorize ? adapter.authorize.bind(adapter) : null;
    }
    if (action === "pull") {
      return adapter.pull ? adapter.pull.bind(adapter) : null;
    }
    if (action === "push") {
      return adapter.push ? adapter.push.bind(adapter) : null;
    }
    if (action === "revoke") {
      return adapter.revoke ? adapter.revoke.bind(adapter) : null;
    }
    if (action === "health") {
      return adapter.health ? adapter.health.bind(adapter) : null;
    }
    return adapter.dryRun ? adapter.dryRun.bind(adapter) : null;
  }

  private makeIdempotencyKey(connectorId: string, action: ConnectorAction, requestId: string): string {
    return `${connectorId}::${action}::${requestId}`;
  }
}

export class ConnectorContractTestKit {
  private contracts: ConnectorContract[] = [];

  public register(contract: ConnectorContract): void {
    if (this.contracts.some((entry) => entry.contractId === contract.contractId)) {
      throw new Error(`duplicate contract id ${contract.contractId}`);
    }
    this.contracts.push(contract);
  }

  public run(context: ConnectorContractContext): ContractSuiteResult {
    const runs: ContractRunResult[] = [];

    for (const contract of this.contracts) {
      try {
        contract.run(context);
        runs.push({
          contractId: contract.contractId,
          description: contract.description,
          passed: true,
        });
      } catch (error) {
        runs.push({
          contractId: contract.contractId,
          description: contract.description,
          passed: false,
          message: error instanceof Error ? error.message : String(error),
        });
      }
    }

    return {
      passed: runs.every((entry) => entry.passed),
      runs,
    };
  }
}

export function createBaselineConnectorContracts(): ConnectorContractTestKit {
  const kit = new ConnectorContractTestKit();

  kit.register({
    contractId: "mu-01-manifest",
    description: "manifests require a stable identifier and declared lifecycle actions",
    run(context: ConnectorContractContext): void {
      if (!Array.isArray(context.registry.list())) {
        throw new Error("missing connector registry in context");
      }
      for (const entry of context.registry.list()) {
        if (!entry.manifest.connectorId || !entry.manifest.version) {
          throw new Error("connector manifest missing identifier/version");
        }
      }
    },
  });

  kit.register({
    contractId: "mu-01-cursor",
    description: "cursors must be partition-scoped and monotonic",
    run(context: ConnectorContractContext): void {
      const cursor = context.cursorLedger.setCursor({
        connectorId: "connector-contract",
        partitionId: "partition-01",
        key: "default",
        value: "v1",
      });
      const next = context.cursorLedger.setCursor({
        connectorId: "connector-contract",
        partitionId: "partition-01",
        key: "default",
        value: "v2",
      });
      if (next.sequence !== cursor.sequence + 1) {
        throw new Error("cursor sequence must increase");
      }
      const replay = context.cursorLedger.setCursor({
        connectorId: "connector-contract",
        partitionId: "partition-01",
        key: "default",
        value: "v2",
      });
      if (replay.sequence !== next.sequence) {
        throw new Error("unchanged cursor should remain idempotent by sequence");
      }
    },
  });

  kit.register({
    contractId: "mu-01-limits",
    description: "limit windows reject requests above policy",
    run(context: ConnectorContractContext): void {
      const manifest: ConnectorManifest = {
        connectorId: "connector-contract",
        connectorType: "synthetic",
        name: "Contract Connector",
        version: MU01_CONNECTORS_VERSION,
        description: "contract-only",
        sourceDataClasses: ["note"],
        capabilities: [{ action: "health", scope: "read", description: "health" }],
        supportsDryRun: true,
        requiresAuth: false,
        rateLimit: {
          windowMs: 1_000,
          maxRequests: 1,
          maxConsecutiveFailures: 1,
          maxRetries: 0,
        },
      };
      const first = context.rateLimiter.allow(manifest, "health");
      const second = context.rateLimiter.allow(manifest, "health");
      if (!first.allowed || second.allowed) {
        throw new Error("expected one request allow then reject");
      }
    },
  });

  return kit;
}

export const MU02_CONNECTORS_VERSION = "mu-02-connectors-v1";
export const MU02_SYNTHETIC_PARTITION = "partition-mu-02";

export const MU03_CONNECTORS_VERSION = "mu-03-connectors-v1";

export type SyntheticConnectorMode = "read-only" | "proposed-write";
export type SyntheticConnectorAction = "create" | "edit" | "delete";

export interface SyntheticConnectorRecord {
  externalId: string;
  revision: number;
  action: SyntheticConnectorAction;
  observedAt: string;
  payload: Record<string, unknown>;
  attachmentIds?: readonly string[];
}

export interface SyntheticConnectorPage {
  pageIndex: number;
  cursorIn: string;
  cursorOut: string | null;
  records: SyntheticConnectorRecord[];
}

export interface SyntheticConnectorReplayNormalization {
  connectorId: string;
  partitionId: string;
  sourceDataClass: string;
  externalId: string;
  revision: number;
  action: SyntheticConnectorAction;
  isDeleted: boolean;
  hasAttachments: boolean;
  isDuplicate: boolean;
  checksum: string;
}

export interface SyntheticConnectorReplayPageReceipt {
  pageIndex: number;
  cursorIn: string;
  cursorOut: string | null;
  duplicates: number;
  deleted: number;
  attachments: number;
  recordCount: number;
  recordChecksums: string[];
  receiptHash: string;
}

export interface SyntheticConnectorReplayConnectorReceipt {
  connectorId: string;
  sourceDataClass: string;
  pages: SyntheticConnectorReplayPageReceipt[];
  totals: {
    records: number;
    duplicates: number;
    deleted: number;
    attachments: number;
  };
}

export interface SyntheticConnectorReplayCorpus {
  version: string;
  generatedForPartition: string;
  generatedAt: string;
  connectors: SyntheticConnectorReplayConnectorReceipt[];
  totals: {
    connectors: number;
    pages: number;
    records: number;
    duplicates: number;
    deleted: number;
    attachments: number;
  };
}

interface SyntheticConnectorCatalogConnectorOptions {
  connectorId: string;
  connectorType: string;
  name: string;
  description: string;
  sourceDataClass: string;
  records: readonly SyntheticConnectorRecord[];
  rateLimit?: ConnectorRateLimit;
  mode?: SyntheticConnectorMode;
  pageSize?: number;
  outage?: {
    pullFailures: number;
  };
}

export class SyntheticConnectorAdapter implements ConnectorAdapter {
  public readonly manifest: ConnectorManifest;

  private readonly records: SyntheticConnectorRecord[];
  private readonly sourceDataClass: string;
  private readonly mode: SyntheticConnectorMode;
  private readonly pageSize: number;
  private readonly outagePlan?: { pullFailures: number };
  private pullAttempts = 0;

  public constructor(options: SyntheticConnectorCatalogConnectorOptions) {
    this.sourceDataClass = options.sourceDataClass;
    this.mode = options.mode ?? "read-only";
    this.pageSize = Math.max(1, options.pageSize ?? 2);
    this.outagePlan = options.outage;
    this.records = Array.from(options.records);
    this.manifest = {
      connectorId: options.connectorId,
      connectorType: options.connectorType,
      name: options.name,
      version: MU02_CONNECTORS_VERSION,
      description: options.description,
      sourceDataClasses: [options.sourceDataClass],
      capabilities: [
        { action: "discover", scope: "admin", description: "discover source metadata" },
        { action: "authorize", scope: "admin", description: "authorize source" },
        { action: "pull", scope: "read", description: "pull synthetic events" },
        { action: "push", scope: "write", description: "proposed write mode" },
        { action: "revoke", scope: "admin", description: "revoke auth" },
        { action: "health", scope: "read", description: "health check" },
        { action: "dryRun", scope: "read", description: "simulate write execution" },
      ],
      supportsDryRun: true,
      requiresAuth: false,
      rateLimit: {
        windowMs: 10_000,
        maxRequests: 120,
        maxConsecutiveFailures: 5,
        maxRetries: 3,
        ...(options.rateLimit ?? {}),
      },
      redactionKeys: ["token", "secret", "refresh_token"],
    };
  }

  public discover(_context: ConnectorOperationContext): ConnectorOperationResult {
    return {
      status: "ok",
      records: this.records.length,
      diagnostics: {
        connectorId: this.manifest.connectorId,
        sourceDataClass: this.sourceDataClass,
        pageSize: this.pageSize,
        mode: this.mode,
        firstObservedAt: this.records[0]?.observedAt,
        lastObservedAt: this.records[this.records.length - 1]?.observedAt,
      },
    };
  }

  public authorize(_context: ConnectorOperationContext): ConnectorOperationResult {
    return {
      status: "ok",
      diagnostics: {
        connectorId: this.manifest.connectorId,
        sourceDataClass: this.sourceDataClass,
      },
    };
  }

  public pull(context: ConnectorOperationContext): ConnectorOperationResult {
    const cursorValue = parseConnectorCursorValue(context);
    const page = this.readPage(cursorValue);
    this.pullAttempts += 1;

    if (this.outagePlan && this.pullAttempts <= this.outagePlan.pullFailures) {
      throw new ConnectorError("temporary provider outage", { retryable: true });
    }

    const diagnostics = {
      connectorId: this.manifest.connectorId,
      sourceDataClass: this.sourceDataClass,
      pageIndex: page.pageIndex,
      cursorIn: page.cursorIn,
      cursorOut: page.cursorOut,
      duplicatesInPage: page.records.filter((entry) => entry.action === "edit").length,
    };

    return {
      status: "ok",
      records: page.records.length,
      cursor: page.records.length > 0 && page.cursorOut !== null
        ? {
            connectorId: this.manifest.connectorId,
            partitionId: context.partitionId || MU02_SYNTHETIC_PARTITION,
            key: "default",
            value: page.cursorOut,
            observedAt: page.records.at(-1)?.observedAt,
          }
        : undefined,
      diagnostics,
    };
  }

  public push(context: ConnectorOperationContext): ConnectorOperationResult {
    if (this.mode === "read-only") {
      return {
        status: "skipped",
        diagnostics: {
          connectorId: this.manifest.connectorId,
          sourceDataClass: this.sourceDataClass,
          mode: this.mode,
          message: "proposed-write disabled",
        },
      };
    }

    const request = context.payload ?? {};
    if (!request || typeof request !== "object") {
      throw new ConnectorError("proposed-write requires payload");
    }

    return {
      status: "ok",
      records: 1,
      diagnostics: {
        connectorId: this.manifest.connectorId,
        sourceDataClass: this.sourceDataClass,
        mode: this.mode,
        operation: request.operation ?? "noop",
      },
    };
  }

  public revoke(_context: ConnectorOperationContext): ConnectorOperationResult {
    return { status: "ok", diagnostics: { connectorId: this.manifest.connectorId, message: "revoked" } };
  }

  public health(_context: ConnectorOperationContext): ConnectorOperationResult {
    return {
      status: "ok",
      diagnostics: {
        connectorId: this.manifest.connectorId,
        sourceDataClass: this.sourceDataClass,
        mode: this.mode,
      },
    };
  }

  public dryRun(context: ConnectorOperationContext): ConnectorOperationResult {
    return {
      status: "ok",
      records: 0,
      diagnostics: {
        connectorId: this.manifest.connectorId,
        sourceDataClass: this.sourceDataClass,
        scope: context.dryRun ? "dry-run" : "runtime",
      },
    };
  }

  public readPage(cursorValue: string): SyntheticConnectorPage {
    const offset = Math.max(0, Number.parseInt(cursorValue, 10) || 0);
    const start = Math.min(offset, this.records.length);
    const pageRecords = this.records.slice(start, start + this.pageSize);
    const nextCursor = start + pageRecords.length;
    const hasMore = nextCursor < this.records.length;
    return {
      pageIndex: Math.floor(start / this.pageSize),
      cursorIn: cursorValue,
      cursorOut: hasMore ? String(nextCursor) : null,
      records: pageRecords.map((entry) => ({ ...entry, attachmentIds: entry.attachmentIds ? [...entry.attachmentIds] : undefined })),
    };
  }
}

function parseConnectorCursorValue(context: ConnectorOperationContext): string {
  if (!context.cursor) {
    return "0";
  }
  if (!context.cursor.value || Number.isNaN(Number(context.cursor.value))) {
    throw new Error(`invalid connector cursor ${context.cursor.value}`);
  }
  return context.cursor.value;
}

function normalizeSyntheticConnectorRecord(
  connectorId: string,
  partitionId: string,
  sourceDataClass: string,
  seen: Set<string>,
  record: SyntheticConnectorRecord,
): SyntheticConnectorNormalizationReceipt {
  const key = `${sourceDataClass}::${record.externalId}::${record.revision}`;
  const isDuplicate = seen.has(key);
  seen.add(key);
  return {
    connectorId,
    partitionId,
    sourceDataClass,
    externalId: record.externalId,
    revision: record.revision,
    action: record.action,
    isDeleted: record.action === "delete",
    hasAttachments: (record.attachmentIds?.length ?? 0) > 0,
    isDuplicate,
    checksum: makeFingerprint({
      connectorId,
      partitionId,
      sourceDataClass,
      externalId: record.externalId,
      revision: record.revision,
      action: record.action,
      payload: record.payload,
      attachments: record.attachmentIds ?? [],
    }),
  };
}

function buildReplayForConnector(
  adapter: SyntheticConnectorAdapter,
  partitionId: string,
): SyntheticConnectorReplayConnectorReceipt {
  const seen = new Set<string>();
  const seenKeys = new Set<string>();
  const pages: SyntheticConnectorReplayPageReceipt[] = [];
  let cursorIn = "0";
  let totalRecords = 0;
  let totalDuplicates = 0;
  let totalDeleted = 0;
  let totalAttachments = 0;

  while (true) {
    const page = adapter.readPage(cursorIn);
    const normalized = page.records.map((entry) => normalizeSyntheticConnectorRecord(
      adapter.manifest.connectorId,
      partitionId,
      adapter.manifest.sourceDataClasses[0] ?? "unknown",
      seen,
      entry,
    ));
    const duplicates = normalized.filter((record) => record.isDuplicate).length;
    const deleted = normalized.filter((record) => record.isDeleted).length;
    const attachments = normalized.filter((record) => record.hasAttachments).length;

    for (const item of normalized) {
      seenKeys.add(`${item.sourceDataClass}::${item.externalId}::${item.revision}`);
      totalRecords += 1;
      totalDuplicates += item.isDuplicate ? 1 : 0;
      totalDeleted += item.isDeleted ? 1 : 0;
      totalAttachments += item.hasAttachments ? 1 : 0;
    }

    pages.push({
      pageIndex: page.pageIndex,
      cursorIn: page.cursorIn,
      cursorOut: page.cursorOut,
      duplicates,
      deleted,
      attachments,
      recordCount: normalized.length,
      recordChecksums: normalized.map((entry) => entry.checksum),
      receiptHash: makeFingerprint(normalized.map((entry) => entry.checksum)),
    });

    if (page.cursorOut === null) {
      break;
    }
    cursorIn = page.cursorOut;
  }

  return {
    connectorId: adapter.manifest.connectorId,
    sourceDataClass: adapter.manifest.sourceDataClasses[0] || "unknown",
    pages,
    totals: {
      records: totalRecords,
      duplicates: totalDuplicates,
      deleted: totalDeleted,
      attachments: totalAttachments,
    },
  };
}

export function buildSyntheticConnectorReplayCorpus(
  adapters: readonly SyntheticConnectorAdapter[],
  options: { partitionId?: string } = {},
): SyntheticConnectorReplayCorpus {
  const partitionId = options.partitionId || MU02_SYNTHETIC_PARTITION;
  const connectors = adapters.map((adapter) => buildReplayForConnector(adapter, partitionId));
  const totals = {
    connectors: connectors.length,
    pages: 0,
    records: 0,
    duplicates: 0,
    deleted: 0,
    attachments: 0,
  };
  for (const connector of connectors) {
    totals.pages += connector.pages.length;
    totals.records += connector.totals.records;
    totals.duplicates += connector.totals.duplicates;
    totals.deleted += connector.totals.deleted;
    totals.attachments += connector.totals.attachments;
  }

  return {
    version: MU02_CONNECTORS_VERSION,
    generatedForPartition: partitionId,
    generatedAt: MU02_SYNTHETIC_PARTITION,
    connectors,
    totals,
  };
}

export function createMu02SyntheticConnectorCatalog(options: { pageSize?: number } = {}): SyntheticConnectorAdapter[] {
  const pageSize = options.pageSize ?? 2;
  const catalog: SyntheticConnectorAdapter[] = [];

  catalog.push(new SyntheticConnectorAdapter({
    connectorId: "connector-mail-mu-02",
    connectorType: "synthetic-mail",
    name: "Synthetic Mail Source",
    description: "Deterministic mail events with pagination, edits, duplicates, and deletes",
    sourceDataClass: "mail",
    pageSize,
    mode: "read-only",
    records: [
      {
        externalId: "mail-01",
        revision: 1,
        action: "create",
        observedAt: "2026-08-01T00:00:00.000Z",
        payload: { subject: "Kickoff", from: "ops@tenant.internal" },
        attachmentIds: ["mail-attach-01"],
      },
      {
        externalId: "mail-02",
        revision: 1,
        action: "create",
        observedAt: "2026-08-01T00:00:01.000Z",
        payload: { subject: "Budget Review", from: "finance@tenant.internal" },
      },
      {
        externalId: "mail-01",
        revision: 2,
        action: "edit",
        observedAt: "2026-08-01T00:00:02.000Z",
        payload: { subject: "Kickoff (updated)", from: "ops@tenant.internal" },
      },
      {
        externalId: "mail-03",
        revision: 1,
        action: "create",
        observedAt: "2026-08-01T00:00:03.000Z",
        payload: { subject: "Duplicate target", from: "ops@tenant.internal" },
      },
      {
        externalId: "mail-03",
        revision: 1,
        action: "create",
        observedAt: "2026-08-01T00:00:04.000Z",
        payload: { subject: "Duplicate target", from: "ops@tenant.internal" },
      },
      {
        externalId: "mail-02",
        revision: 2,
        action: "delete",
        observedAt: "2026-08-01T00:00:05.000Z",
        payload: { reason: "purged" },
      },
    ],
  }));

  catalog.push(new SyntheticConnectorAdapter({
    connectorId: "connector-calendar-mu-02",
    connectorType: "synthetic-calendar",
    name: "Synthetic Calendar Source",
    description: "Deterministic event stream with paging and updates",
    sourceDataClass: "calendar",
    pageSize,
    mode: "proposed-write",
    records: [
      {
        externalId: "evt-01",
        revision: 1,
        action: "create",
        observedAt: "2026-08-01T01:00:00.000Z",
        payload: { title: "Planning", location: "HQ" },
      },
      {
        externalId: "evt-02",
        revision: 1,
        action: "create",
        observedAt: "2026-08-01T01:00:01.000Z",
        payload: { title: "Review" },
      },
      {
        externalId: "evt-01",
        revision: 2,
        action: "edit",
        observedAt: "2026-08-01T01:00:02.000Z",
        payload: { title: "Planning (updated)", location: "Zoom" },
      },
      {
        externalId: "evt-03",
        revision: 1,
        action: "create",
        observedAt: "2026-08-01T01:00:03.000Z",
        payload: { title: "Board Sync", location: "Remote" },
      },
    ],
  }));

  catalog.push(new SyntheticConnectorAdapter({
    connectorId: "connector-drive-mu-02",
    connectorType: "synthetic-drive",
    name: "Synthetic Drive Source",
    description: "Deterministic file revisions and attachment references",
    sourceDataClass: "drive",
    pageSize,
    mode: "proposed-write",
    rateLimit: { maxRequests: 1, maxRetries: 1, maxConsecutiveFailures: 2, windowMs: 60_000 },
    records: [
      {
        externalId: "file-01",
        revision: 1,
        action: "create",
        observedAt: "2026-08-01T02:00:00.000Z",
        payload: { name: "spec-v1.docx", bytes: 2048 },
        attachmentIds: ["drive-chunk-01", "drive-chunk-02"],
      },
      {
        externalId: "file-02",
        revision: 1,
        action: "create",
        observedAt: "2026-08-01T02:00:01.000Z",
        payload: { name: "plan.pdf", bytes: 4096 },
      },
      {
        externalId: "file-01",
        revision: 2,
        action: "edit",
        observedAt: "2026-08-01T02:00:02.000Z",
        payload: { name: "spec-v2.docx", bytes: 3072 },
      },
      {
        externalId: "file-03",
        revision: 1,
        action: "delete",
        observedAt: "2026-08-01T02:00:03.000Z",
        payload: { name: "legacy.pdf" },
      },
    ],
  }));

  catalog.push(new SyntheticConnectorAdapter({
    connectorId: "connector-chat-mu-02",
    connectorType: "synthetic-chat",
    name: "Synthetic Chat Source",
    description: "Deterministic message stream with duplicate rows",
    sourceDataClass: "chat",
    pageSize,
    mode: "read-only",
    records: [
      {
        externalId: "msg-01",
        revision: 1,
        action: "create",
        observedAt: "2026-08-01T03:00:00.000Z",
        payload: { room: "alpha", body: "first message" },
      },
      {
        externalId: "msg-02",
        revision: 1,
        action: "create",
        observedAt: "2026-08-01T03:00:01.000Z",
        payload: { room: "alpha", body: "second message" },
      },
      {
        externalId: "msg-01",
        revision: 1,
        action: "create",
        observedAt: "2026-08-01T03:00:02.000Z",
        payload: { room: "alpha", body: "first message (duplicate)" },
      },
    ],
  }));

  catalog.push(new SyntheticConnectorAdapter({
    connectorId: "connector-github-mu-02",
    connectorType: "synthetic-github",
    name: "Synthetic GitHub Source",
    description: "Deterministic issue and PR activity with retries",
    sourceDataClass: "github",
    pageSize,
    mode: "read-only",
    outage: { pullFailures: 1 },
    records: [
      {
        externalId: "issue-101",
        revision: 1,
        action: "create",
        observedAt: "2026-08-01T04:00:00.000Z",
        payload: { title: "Add synthetic runner" },
      },
      {
        externalId: "issue-102",
        revision: 1,
        action: "create",
        observedAt: "2026-08-01T04:00:01.000Z",
        payload: { title: "Fix connector fixture" },
      },
      {
        externalId: "pr-11",
        revision: 1,
        action: "create",
        observedAt: "2026-08-01T04:00:02.000Z",
        payload: { title: "Add read/write adapters", state: "open" },
      },
      {
        externalId: "issue-102",
        revision: 2,
        action: "edit",
        observedAt: "2026-08-01T04:00:03.000Z",
        payload: { title: "Fix connector fixture", state: "closed" },
      },
    ],
  }));

  return catalog;
}

export function synthesizeConnectorReplayChecksums(corpus: SyntheticConnectorReplayCorpus): Record<string, string> {
  const checks: Record<string, string> = {};
  for (const connector of corpus.connectors) {
    checks[connector.connectorId] = makeFingerprint(connector.pages.map((page) => page.receiptHash).join("|"));
  }
  checks.overall = makeFingerprint(
    corpus.connectors.map((connector) => checks[connector.connectorId]).join("|"),
  );
  return checks;
}

export type ProductionConnectorEffect = "allow" | "deny";

export interface ProductionConnectorProviderSpec {
  providerId: string;
  connectorType: string;
  providerName: string;
  sourceDataClass: string;
  pullRecordCount: number;
  supportsPull?: boolean;
  supportsPush?: boolean;
  pullOutagesBeforeHealthy?: number;
  healthEnabled?: boolean;
}

export interface ProductionConnectorShellOptions {
  connectorId: string;
  connectorType: string;
  name: string;
  description: string;
  providers: readonly ProductionConnectorProviderSpec[];
  supportsDryRun?: boolean;
  rateLimit?: ConnectorRateLimit;
}

export interface ProductionConnectorProviderState {
  providerId: string;
  connectorType: string;
  providerName: string;
  sourceDataClass: string;
  pullRecordCount: number;
  supportsPull: boolean;
  supportsPush: boolean;
  active: boolean;
  pullOutagesRemaining: number;
  healthEnabled: boolean;
  lastResult?: string;
}

export interface ProductionConnectorShellSnapshot {
  connectorId: string;
  providers: ProductionConnectorProviderState[];
  writeEffect: ProductionConnectorEffect;
  credentialEffect: ProductionConnectorEffect;
}

export class ProductionConnectorShellAdapter implements ConnectorAdapter {
  public readonly manifest: ConnectorManifest;

  private writeValve: ProductionConnectorEffect = "deny";
  private credentialValve: ProductionConnectorEffect = "deny";
  private revoked = false;

  private readonly providers: ProductionConnectorProviderState[];

  public constructor(options: ProductionConnectorShellOptions) {
    if (!options.providers.length) {
      throw new Error("production connector shell requires at least one provider");
    }
    this.providers = options.providers.map((provider) => ({
      providerId: provider.providerId,
      connectorType: provider.connectorType,
      providerName: provider.providerName,
      sourceDataClass: provider.sourceDataClass,
      pullRecordCount: provider.pullRecordCount,
      supportsPull: provider.supportsPull ?? true,
      supportsPush: provider.supportsPush ?? true,
      active: true,
      pullOutagesRemaining: provider.pullOutagesBeforeHealthy ?? 0,
      healthEnabled: provider.healthEnabled ?? true,
      lastResult: undefined,
    }));

    this.manifest = {
      connectorId: options.connectorId,
      connectorType: options.connectorType,
      name: options.name,
      version: MU03_CONNECTORS_VERSION,
      description: options.description,
      sourceDataClasses: Array.from(new Set(options.providers.map((provider) => provider.sourceDataClass))),
      capabilities: [
        { action: "discover", scope: "admin", description: "discover providers" },
        { action: "authorize", scope: "admin", description: "authorize shell" },
        { action: "pull", scope: "read", description: "pull through provider chain" },
        { action: "push", scope: "write", description: "write through provider chain" },
        { action: "revoke", scope: "admin", description: "revoke provider credentials and outputs" },
        { action: "health", scope: "read", description: "probe provider chain" },
        { action: "dryRun", scope: "read", description: "dry-run with current effects" },
      ],
      supportsDryRun: options.supportsDryRun ?? true,
      requiresAuth: false,
      rateLimit: {
        windowMs: 10_000,
        maxRequests: 30,
        maxConsecutiveFailures: 5,
        maxRetries: 1,
        ...(options.rateLimit ?? {}),
      },
      redactionKeys: ["token", "secret", "credential", "authorization", "apiKey", "client_secret", "access_token"],
    };
  }

  public snapshot(): ProductionConnectorShellSnapshot {
    return {
      connectorId: this.manifest.connectorId,
      providers: this.providers.map((provider) => ({ ...provider })),
      writeEffect: this.writeValve,
      credentialEffect: this.credentialValve,
    };
  }

  public setWriteEffect(effect: ProductionConnectorEffect): void {
    this.writeValve = effect;
  }

  public setCredentialEffect(effect: ProductionConnectorEffect): void {
    this.credentialValve = effect;
  }

  public reorderProviders(providerIds: string[]): void {
    const keep = new Map(this.providers.map((provider) => [provider.providerId, provider]));
    const next: ProductionConnectorProviderState[] = [];

    for (const candidate of providerIds) {
      const provider = keep.get(candidate);
      if (provider) {
        next.push(provider);
        keep.delete(candidate);
      }
    }
    for (const provider of this.providers) {
      if (keep.has(provider.providerId)) {
        next.push(provider);
        keep.delete(provider.providerId);
      }
    }
    for (let i = 0; i < this.providers.length; i += 1) {
      this.providers[i] = next[i];
    }
  }

  public removeProvider(providerId: string): void {
    const provider = this.providers.find((entry) => entry.providerId === providerId);
    if (!provider) {
      throw new Error(`provider ${providerId} not found`);
    }
    provider.active = false;
    provider.lastResult = "removed";
  }

  public setProviderPushEnabled(providerId: string, enabled: boolean): void {
    const provider = this.providers.find((entry) => entry.providerId === providerId);
    if (!provider) {
      throw new Error(`provider ${providerId} not found`);
    }
    provider.supportsPush = enabled;
  }

  public discover(_context: ConnectorOperationContext): ConnectorOperationResult {
    return {
      status: "ok",
      records: this.providers.length,
      diagnostics: this.makeDiagnostics("discover", {
        providers: this.providers.map((provider) => ({
          providerId: provider.providerId,
          active: provider.active,
          supportsPush: provider.supportsPush,
          supportsPull: provider.supportsPull,
        })),
      }),
    };
  }

  public authorize(context: ConnectorOperationContext): ConnectorOperationResult {
    this.requireNotRevoked(context.requestId);
    return {
      status: "ok",
      diagnostics: this.makeDiagnostics("authorize", {
        credentialEffect: this.credentialValve,
        writeEffect: this.writeValve,
      }),
    };
  }

  public pull(context: ConnectorOperationContext): ConnectorOperationResult {
    this.requireNotRevoked(context.requestId);
    return this.executeThroughProviderChain("pull", context);
  }

  public push(context: ConnectorOperationContext): ConnectorOperationResult {
    this.requireNotRevoked(context.requestId);

    if (this.writeValve === "deny" || this.credentialValve === "deny") {
      return {
        status: "skipped",
        diagnostics: this.makeDiagnostics("push", {
          reason: "write effect disabled",
          writeEffect: this.writeValve,
          credentialEffect: this.credentialValve,
        }),
      };
    }
    return this.executeThroughProviderChain("push", context);
  }

  public revoke(_context: ConnectorOperationContext): ConnectorOperationResult {
    this.revoked = true;
    for (const provider of this.providers) {
      provider.active = false;
      provider.lastResult = "revoked";
    }
    return {
      status: "ok",
      diagnostics: this.makeDiagnostics("revoke", {
        revoked: true,
      }),
    };
  }

  public health(context: ConnectorOperationContext): ConnectorOperationResult {
    this.requireNotRevoked(context.requestId);
    return this.executeThroughProviderChain("health", context);
  }

  public dryRun(context: ConnectorOperationContext): ConnectorOperationResult {
    this.requireNotRevoked(context.requestId);
    if (this.writeValve === "deny" || this.credentialValve === "deny") {
      return {
        status: "skipped",
        records: 0,
        diagnostics: this.makeDiagnostics("dryRun", {
          reason: "dry-run requires active write credentials and effect",
          writeEffect: this.writeValve,
          credentialEffect: this.credentialValve,
        }),
      };
    }
    return this.executeThroughProviderChain("dryRun", context);
  }

  private executeThroughProviderChain(action: ConnectorAction, context: ConnectorOperationContext): ConnectorOperationResult {
    const ordered = this.providers.filter((entry) => entry.active);
    if (!ordered.length) {
      throw new ConnectorError("no active providers");
    }

    let lastFailure: Error | null = null;

    for (const provider of ordered) {
      if (!this.providerCanPerformAction(provider, action)) {
        continue;
      }
      try {
        const result = this.executeOnProvider(provider, action, context);
        provider.lastResult = "ok";
        return {
          ...result,
          diagnostics: {
            ...result.diagnostics,
            providerId: provider.providerId,
            providerType: provider.connectorType,
          },
        };
      } catch (error) {
        provider.lastResult = `failure:${error instanceof Error ? error.message : String(error)}`;
        lastFailure = error instanceof Error ? error : new Error(String(error));
        if (!isRetryableActionError(lastFailure)) {
          throw lastFailure;
        }
      }
    }

    throw lastFailure ?? new ConnectorError("no provider could satisfy action", { retryable: false });
  }

  private executeOnProvider(
    provider: ProductionConnectorProviderState,
    action: ConnectorAction,
    context: ConnectorOperationContext,
  ): ConnectorOperationResult {
    if (action === "discover") {
      return {
        status: "ok",
        records: this.providers.length,
        diagnostics: this.makeDiagnostics(action, { chosenProvider: provider.providerId }),
      };
    }
    if (action === "authorize") {
      return {
        status: "ok",
        diagnostics: this.makeDiagnostics(action, {
          chosenProvider: provider.providerId,
          credentialEffect: this.credentialValve,
        }),
      };
    }
    if (action === "health") {
      if (!provider.healthEnabled) {
        throw new ConnectorError(`${provider.providerId} health probe failed`, { retryable: true });
      }
      return {
        status: "ok",
        diagnostics: this.makeDiagnostics(action, {
          chosenProvider: provider.providerId,
          healthy: provider.healthEnabled,
        }),
      };
    }
    if (action === "pull") {
      if (!provider.supportsPull) {
        throw new ConnectorError(`${provider.providerId} does not support pull`, { retryable: false });
      }
      if (provider.pullOutagesRemaining > 0) {
        provider.pullOutagesRemaining -= 1;
        throw new ConnectorError(`${provider.providerId} temporary outage`, { retryable: true, code: "outage" });
      }
      const cursorPrefix = context.cursor ? context.cursor.value : "start";
      return {
        status: "ok",
        records: provider.pullRecordCount,
        cursor: {
          connectorId: this.manifest.connectorId,
          partitionId: context.partitionId || "default",
          key: "default",
          value: `${provider.providerId}:${cursorPrefix}`,
          observedAt: nowIso(),
        },
        diagnostics: this.makeDiagnostics(action, {
          chosenProvider: provider.providerId,
          pullRecordCount: provider.pullRecordCount,
        }),
      };
    }
    if (action === "push") {
      if (!provider.supportsPush) {
        throw new ConnectorError(`${provider.providerId} does not support push`, { retryable: false });
      }
      return {
        status: "ok",
        records: 1,
        diagnostics: this.makeDiagnostics(action, {
          chosenProvider: provider.providerId,
          writeEffect: this.writeValve,
          credentialEffect: this.credentialValve,
        }),
      };
    }
    if (action === "revoke") {
      provider.active = false;
      return {
        status: "ok",
        diagnostics: this.makeDiagnostics(action, {
          revokedProvider: provider.providerId,
        }),
      };
    }
    if (action === "dryRun") {
      return {
        status: "ok",
        records: 0,
        diagnostics: this.makeDiagnostics(action, {
          chosenProvider: provider.providerId,
          dryRun: true,
        }),
      };
    }
    throw new ConnectorError(`unsupported action ${action}`);
  }

  private providerCanPerformAction(provider: ProductionConnectorProviderState, action: ConnectorAction): boolean {
    if (!provider.active) {
      return false;
    }
    if (action === "pull") {
      return provider.supportsPull;
    }
    if (action === "push") {
      return provider.supportsPush;
    }
    return true;
  }

  private makeDiagnostics(action: ConnectorAction, diagnostics: Record<string, unknown>): Record<string, unknown> {
    return {
      action,
      connectorId: this.manifest.connectorId,
      version: MU03_CONNECTORS_VERSION,
      writeEffect: this.writeValve,
      credentialEffect: this.credentialValve,
      revoked: this.revoked,
      ...diagnostics,
    };
  }

  private requireNotRevoked(requestId?: string): void {
    if (!this.revoked) {
      return;
    }
    throw new ConnectorError(`connector ${this.manifest.connectorId} revoked`, {
      code: "revoked",
      retryable: false,
    });
  }
}

export function createMu03ProductionConnectorCatalog(
  options: {
    providersPerAdapter?: number;
  } = {},
): ProductionConnectorShellAdapter[] {
  const providerFallbackCount = options.providersPerAdapter ?? 2;
  return [
    new ProductionConnectorShellAdapter({
      connectorId: "connector-github-mu-03",
      connectorType: "provider-hub",
      name: "GitHub production shell",
      description: "Provider-neutral GitHub adapter shell with deterministic fixtures",
      providers: makeProviderChain("github", "GitHub", "github", providerFallbackCount, {
        includePrimaryPush: true,
        pullOutagesBeforeHealthy: 1,
      }),
    }),
    new ProductionConnectorShellAdapter({
      connectorId: "connector-google-mu-03",
      connectorType: "provider-hub",
      name: "Google production shell",
      description: "Provider-neutral Google adapter shell with deterministic fixtures",
      providers: makeProviderChain("google", "Google", "drive", providerFallbackCount, {
        includePrimaryPush: true,
      }),
    }),
    new ProductionConnectorShellAdapter({
      connectorId: "connector-slack-mu-03",
      connectorType: "provider-hub",
      name: "Slack production shell",
      description: "Provider-neutral Slack adapter shell with partial write scope by design",
      providers: makeProviderChain("slack", "Slack", "chat", providerFallbackCount, {
        includePrimaryPush: false,
        includeFallbackPush: true,
      }),
    }),
    new ProductionConnectorShellAdapter({
      connectorId: "connector-notion-mu-03",
      connectorType: "provider-hub",
      name: "Notion production shell",
      description: "Provider-neutral Notion adapter shell with deterministic fixtures",
      providers: makeProviderChain("notion", "Notion", "document", providerFallbackCount, {
        includePrimaryPush: true,
      }),
    }),
    new ProductionConnectorShellAdapter({
      connectorId: "connector-webhook-mu-03",
      connectorType: "provider-hub",
      name: "Webhook/file production shell",
      description: "Generic webhook/file adapter shell with deterministic fixtures",
      providers: makeProviderChain("webhook", "Webhook/File", "file", providerFallbackCount, {
        includePrimaryPush: false,
        includeFallbackPush: false,
      }),
    }),
  ];
}

interface ProviderChainOptions {
  includePrimaryPush: boolean;
  includeFallbackPush?: boolean;
  pullOutagesBeforeHealthy?: number;
}

function makeProviderChain(
  providerFamily: string,
  label: string,
  sourceDataClass: string,
  count: number,
  options: ProviderChainOptions,
): ProductionConnectorProviderSpec[] {
  const providers: ProductionConnectorProviderSpec[] = [];
  const safeCount = Math.max(1, Math.min(3, Math.floor(count)));

  providers.push({
    providerId: `${providerFamily}-primary`,
    connectorType: `${providerFamily}-primary`,
    providerName: `${label} Primary`,
    sourceDataClass,
    pullRecordCount: 2,
    supportsPush: options.includePrimaryPush,
    pullOutagesBeforeHealthy: options.pullOutagesBeforeHealthy ?? 0,
    healthEnabled: true,
  });

  if (safeCount > 1) {
    providers.push({
      providerId: `${providerFamily}-fallback`,
      connectorType: `${providerFamily}-fallback`,
      providerName: `${label} Fallback`,
      sourceDataClass,
      pullRecordCount: 1,
      supportsPush: options.includeFallbackPush ?? options.includePrimaryPush,
      pullOutagesBeforeHealthy: 0,
      healthEnabled: true,
    });
  }

  if (safeCount > 2) {
    providers.push({
      providerId: `${providerFamily}-tertiary`,
      connectorType: `${providerFamily}-tertiary`,
      providerName: `${label} Tertiary`,
      sourceDataClass,
      pullRecordCount: 1,
      supportsPush: options.includeFallbackPush ?? options.includePrimaryPush,
      pullOutagesBeforeHealthy: 0,
      healthEnabled: true,
    });
  }

  return providers;
}
