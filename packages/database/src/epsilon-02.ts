import { createHash, randomUUID } from "node:crypto";
import {
  AuditEventRecord,
  DecisionRecord,
  OutboxEventRecord,
  OutboxStatus,
  PartitionRecord,
  PartitionClassification,
  JobRecord,
  JobStatus,
  SyntheticSeedRecord,
  PrincipalRecord,
  TaskRecord,
  TaskStatus,
} from "./schema";

function nowIso(): string {
  return new Date().toISOString();
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function stableStringify(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }

if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(",")}]`;
  }

  const sortedEntries = Object.entries(value as Record<string, unknown>)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, entryValue]) => `${JSON.stringify(key)}:${stableStringify(entryValue)}`)
    .join(",");

  return `{${sortedEntries}}`;
}

function hashCommandPayload(payload: unknown): string {
  return createHash("sha256").update(stableStringify(payload)).digest("hex");
}

function buildSummary(value: unknown): string {
  return hashCommandPayload(value);
}

function addMilliseconds(isoString: string, milliseconds: number): string {
  const date = new Date(isoString);
  return new Date(date.getTime() + milliseconds).toISOString();
}

function isDue(runAfter: string, now: string): boolean {
  return Date.parse(runAfter) <= Date.parse(now);
}

function isLeaseExpired(leaseExpiresAt: string | null, now: string): boolean {
  if (!leaseExpiresAt) {
    return true;
  }
  return Date.parse(leaseExpiresAt) <= Date.parse(now);
}

function deterministicRetryDelayMs(attempt: number): number {
  const safeAttempt = Math.max(1, attempt);
  const step = Math.min(6, safeAttempt);
  return 5_000 * 2 ** (step - 1);
}

export type OutboxStatusKind = OutboxStatus;

export interface CommandEnvelope<TPayload = Record<string, unknown>> {
  command: string;
  idempotencyKey: string;
  partitionId: string;
  actorId: string;
  correlationId: string;
  causationId: string;
  payload: TPayload;
}

export interface CommandReceipt {
  id: string;
  command: string;
  idempotency_key: string;
  partition_id: string;
  actor_id: string;
  correlation_id: string;
  causation_id: string;
  status: "accepted" | "replayed";
  request_hash: string;
  replay_of: string | null;
  result_summary: string;
  created_at: string;
}

export interface CommandExecutionResult<T> {
  status: "accepted" | "replayed";
  replay_of: string | null;
  receipt: CommandReceipt;
  output: T | null;
}

export type JobFailureReason =
  | "retryable"
  | "non_retryable"
  | "interrupted";

export interface WorkerLeaseOptions {
  leaseDurationMs?: number;
  maxAttempts?: number;
  retryBaseMs?: number;
  retryCeilingAttempts?: number;
}

export interface JobDraft {
  partitionId: string | null;
  idempotencyKey: string;
  jobType: string;
  payload: Record<string, unknown>;
  maxAttempts?: number;
  runAfter?: string;
  syntheticSeedTag?: string | null;
  custodyToken?: string | null;
  provenance?: Record<string, unknown>;
}

export interface SyntheticSeedDraft {
  partitionId: string;
  tag: string;
  custodyToken: string;
  createdBy: string;
}

export interface OutboxEventDraft {
  partition_id: string;
  event_type: string;
  aggregate_type: string;
  aggregate_id: string;
  payload: Record<string, unknown>;
  correlation_id: string;
  causation_id: string;
  signature?: string | null;
  status?: OutboxStatusKind;
  target_endpoint?: string | null;
  attempts?: number;
}

export interface AuditEventDraft {
  partition_id: string;
  actor_id: string;
  causation_id: string;
  correlation_id: string;
  action: string;
  resource_type: string;
  resource_id: string;
  outcome: Record<string, unknown>;
  redacted_payload: Record<string, unknown>;
}

export class JobLeaseConflictError extends Error {
  public readonly jobId: string;

  public constructor(message: string, jobId: string) {
    super(message);
    this.name = "JobLeaseConflictError";
    this.jobId = jobId;
  }
}

export class SyntheticSeedError extends Error {
  public constructor(message: string) {
    super(message);
    this.name = "SyntheticSeedError";
  }
}

export class IdempotentConflictError extends Error {
  public readonly existingReceipt: CommandReceipt;

  public constructor(message: string, existingReceipt: CommandReceipt) {
    super(message);
    this.name = "IdempotentConflictError";
    this.existingReceipt = existingReceipt;
  }
}

interface StoredIdempotency {
  requestHash: string;
  receipt: CommandReceipt;
}

class InMemoryTable<T extends { id: string }> {
  private readonly values = new Map<string, T>();

  public get(id: string): T | null {
    const row = this.values.get(id);
    if (!row) {
      return null;
    }
    return clone(row);
  }

  public set(row: T): T {
    const copied = clone(row);
    this.values.set(copied.id, copied);
    return clone(copied);
  }

  public all(): T[] {
    return [...this.values.values()].map((value) => clone(value));
  }

  public has(id: string): boolean {
    return this.values.has(id);
  }

  public clone(): InMemoryTable<T> {
    const cloned = new InMemoryTable<T>();
    for (const row of this.values.values()) {
      cloned.set(row);
    }
    return cloned;
  }
}

export interface PartitionCreateInput {
  partition_key: string;
  display_name: string;
  synthetic?: boolean;
  classification?: PartitionClassification;
  retention_days?: number;
  created_by?: string | null;
  provenance?: string;
}

export class PartitionRepository {
  public constructor(private readonly table: InMemoryTable<PartitionRecord>) {}

  public async list(): Promise<PartitionRecord[]> {
    return this.table.all();
  }

  public async getById(id: string): Promise<PartitionRecord | null> {
    return this.table.get(id);
  }

  public async getByKey(partitionKey: string): Promise<PartitionRecord | null> {
    return this.table
      .all()
      .find((row) => row.partition_key === partitionKey) || null;
  }

  public async create(input: PartitionCreateInput): Promise<PartitionRecord> {
    const createdAt = nowIso();
    const row: PartitionRecord = {
      id: randomUUID(),
      partition_key: input.partition_key,
      display_name: input.display_name,
      synthetic: Boolean(input.synthetic),
      classification: input.classification ?? "private",
      retention_days: input.retention_days ?? 365,
      created_by: input.created_by ?? null,
      provenance: input.provenance ?? "{}",
      is_deleted: false,
      record_version: 1,
      created_at: createdAt,
      updated_at: createdAt,
    };
    return this.table.set(row);
  }

  public async softDelete(id: string): Promise<void> {
    const row = await this.getById(id);
    if (!row) {
      return;
    }
    row.is_deleted = true;
    row.updated_at = nowIso();
    this.table.set(row);
  }
}

export interface PrincipalCreateInput {
  principal_type?: string;
  external_subject: string;
  principal_name: string;
  contact?: Record<string, unknown> | null;
  status?: string;
  created_by?: string | null;
}

export class PrincipalRepository {
  public constructor(private readonly table: InMemoryTable<PrincipalRecord>) {}

  public async list(): Promise<PrincipalRecord[]> {
    return this.table.all();
  }

  public async getById(id: string): Promise<PrincipalRecord | null> {
    return this.table.get(id);
  }

  public async getByExternalSubject(externalSubject: string): Promise<PrincipalRecord | null> {
    return this.table.all().find((row) => row.external_subject === externalSubject) || null;
  }

  public async create(input: PrincipalCreateInput): Promise<PrincipalRecord> {
    const createdAt = nowIso();
    const row: PrincipalRecord = {
      id: randomUUID(),
      principal_type: input.principal_type ?? "owner",
      external_subject: input.external_subject,
      principal_name: input.principal_name,
      contact: input.contact ?? null,
      status: input.status ?? "active",
      provenance: "{}",
      created_at: createdAt,
      updated_at: createdAt,
    };
    return this.table.set(row);
  }
}

export interface TaskCreateInput {
  partition_id: string;
  title: string;
  created_by: string;
  status?: TaskStatus;
  due_at?: string | null;
  provenance?: string;
}

export class TaskRepository {
  public constructor(private readonly table: InMemoryTable<TaskRecord>) {}

  public async getById(id: string): Promise<TaskRecord | null> {
    return this.table.get(id);
  }

  public async listByPartition(partitionId: string): Promise<TaskRecord[]> {
    return this.table
      .all()
      .filter((record) => record.partition_id === partitionId);
  }

  public async create(input: TaskCreateInput): Promise<TaskRecord> {
    const createdAt = nowIso();
    const row: TaskRecord = {
      id: randomUUID(),
      partition_id: input.partition_id,
      title: input.title,
      status: input.status ?? "draft",
      created_by: input.created_by,
      due_at: input.due_at ?? null,
      provenance: input.provenance ?? "{}",
      created_at: createdAt,
      updated_at: createdAt,
    };
    return this.table.set(row);
  }

  public async updateStatus(id: string, status: TaskStatus): Promise<TaskRecord> {
    const row = (await this.getById(id)) as TaskRecord | null;
    if (!row) {
      throw new Error(`task ${id} not found`);
    }
    row.status = status;
    row.updated_at = nowIso();
    return this.table.set(row);
  }
}

export interface DecisionCreateInput {
  partition_id: string;
  title: string;
  principal_id: string | null;
  status?: string;
  rationale: string;
}

export class DecisionRepository {
  public constructor(private readonly table: InMemoryTable<DecisionRecord>) {}

  public async create(input: DecisionCreateInput): Promise<DecisionRecord> {
    const createdAt = nowIso();
    const row: DecisionRecord = {
      id: randomUUID(),
      partition_id: input.partition_id,
      principal_id: input.principal_id,
      title: input.title,
      status: input.status ?? "draft",
      provenance: JSON.stringify({ rationale: input.rationale }),
      created_at: createdAt,
    };
    return this.table.set(row);
  }

  public async getById(id: string): Promise<DecisionRecord | null> {
    return this.table.get(id);
  }

  public async listByPartition(partitionId: string): Promise<DecisionRecord[]> {
    return this.table
      .all()
      .filter((record) => record.partition_id === partitionId);
  }
}

export class OutboxRepository {
  public constructor(private readonly table: InMemoryTable<OutboxEventRecord>) {}

  public async listByPartition(partitionId: string, status?: OutboxStatus): Promise<OutboxEventRecord[]> {
    const rows = this.table.all().filter((row) => row.partition_id === partitionId);
    if (status) {
      return rows.filter((row) => row.status === status);
    }
    return rows;
  }

  public async append(draft: OutboxEventDraft): Promise<OutboxEventRecord> {
    const createdAt = nowIso();
    const row: OutboxEventRecord = {
      id: randomUUID(),
      partition_id: draft.partition_id,
      correlation_id: draft.correlation_id,
      causation_id: draft.causation_id,
      event_type: draft.event_type,
      aggregate_type: draft.aggregate_type,
      aggregate_id: draft.aggregate_id,
      payload: draft.payload,
      signature: draft.signature ?? null,
      status: draft.status ?? "pending",
      attempts: draft.attempts ?? 0,
      target_endpoint: draft.target_endpoint ?? null,
      processed_at: null,
      provenance: {
        source: "in-memory-domain-uow",
      },
      created_at: createdAt,
      updated_at: createdAt,
    };
    return this.table.set(row);
  }
}

export class AuditRepository {
  public constructor(private readonly table: InMemoryTable<AuditEventRecord>) {}

  public async append(draft: AuditEventDraft): Promise<AuditEventRecord> {
    const createdAt = nowIso();
    const row: AuditEventRecord = {
      id: randomUUID(),
      partition_id: draft.partition_id,
      actor_id: draft.actor_id,
      causation_id: draft.causation_id,
      correlation_id: draft.correlation_id,
      action: draft.action,
      resource_type: draft.resource_type,
      resource_id: draft.resource_id,
      outcome: draft.outcome,
      redacted_payload: draft.redacted_payload,
      provenance: {
        source: "in-memory-domain-uow",
      },
      created_at: createdAt,
    };
    return this.table.set(row);
  }

  public async listByPartition(partitionId: string): Promise<AuditEventRecord[]> {
    return this.table.all().filter((row) => row.partition_id === partitionId);
  }
}

function hashCustodyToken(token: string): string {  // allow-secret
  return createHash("sha256").update(token).digest("hex");
}

export class JobRepository {
  private readonly leaseDurationMs: number;

  public constructor(
    private readonly table: InMemoryTable<JobRecord>,
    private readonly options?: {
      now?: () => string;
      leaseDurationMs?: number;
    },
  ) {
    this.leaseDurationMs = options?.leaseDurationMs ?? 30_000;
  }

  private now(): string {
    return (this.options?.now || nowIso)();
  }

  public async getById(id: string): Promise<JobRecord | null> {
    return this.table.get(id);
  }

  public async listByPartition(partitionId: string): Promise<JobRecord[]> {
    return this.table.all().filter((row) => row.partition_id === partitionId);
  }

  public async listDue(now: string = this.now(), status?: JobStatus): Promise<JobRecord[]> {
    return this.table
      .all()
      .filter((record) => isDue(record.run_after, now))
      .filter((record) => (status ? record.status === status : true))
      .sort((left, right) =>
        left.created_at.localeCompare(right.created_at) || left.id.localeCompare(right.id),
      );
  }

  public async listByStatus(status: JobStatus): Promise<JobRecord[]> {
    return this.table.all().filter((record) => record.status === status);
  }

  public async listByWorker(workerId: string): Promise<JobRecord[]> {
    return this.table.all().filter((record) => record.worker_id === workerId);
  }

  public async enqueue(draft: JobDraft): Promise<JobRecord> {
    const existing = this.table
      .all()
      .find((record) => record.idempotency_key === draft.idempotencyKey);
    if (existing) {
      return existing;
    }

    const createdAt = this.now();
    const maxAttempts = draft.maxAttempts ?? 3;
    const row: JobRecord = {
      id: randomUUID(),
      partition_id: draft.partitionId,
      idempotency_key: draft.idempotencyKey,
      job_type: draft.jobType,
      payload: draft.payload,
      status: "pending",
      worker_id: null,
      lease_expires_at: null,
      attempts: 0,
      max_attempts: maxAttempts,
      run_after: draft.runAfter ?? createdAt,
      error_message: null,
      synthetic_seed_tag: draft.syntheticSeedTag ?? null,
      custody_token: draft.custodyToken ? hashCustodyToken(draft.custodyToken) : null,
      provenance: draft.provenance ?? {},
      created_at: createdAt,
      updated_at: createdAt,
    };
    return this.table.set(row);
  }

  public async claimNext(workerId: string, options?: WorkerLeaseOptions): Promise<JobRecord | null> {
    const now = this.now();
    const due = await this.listDue(now, "pending");
    const next = due[0] || null;
    if (!next) {
      return null;
    }
    next.status = "claimed";
    next.worker_id = workerId;
    const leaseDuration = options?.leaseDurationMs ?? this.leaseDurationMs;
    next.lease_expires_at = addMilliseconds(now, leaseDuration);
    next.updated_at = now;
    return this.table.set(next);
  }

  public async heartbeat(
    jobId: string,
    workerId: string,
    now: string = this.now(),
    leaseDurationMs = this.leaseDurationMs,
  ): Promise<boolean> {
    const row = await this.getById(jobId);
    if (!row) {
      return false;
    }
    if (row.status !== "claimed" || row.worker_id !== workerId) {
      return false;
    }
    if (isLeaseExpired(row.lease_expires_at, now)) {
      return false;
    }
    row.lease_expires_at = addMilliseconds(now, leaseDurationMs);
    row.updated_at = now;
    this.table.set(row);
    return true;
  }

  public async complete(
    jobId: string,
    workerId: string,
    now: string = this.now(),
  ): Promise<JobRecord> {
    const row = await this.getById(jobId);
    if (!row) {
      throw new Error(`job ${jobId} not found`);
    }
    if (row.status !== "claimed" || row.worker_id !== workerId) {
      throw new JobLeaseConflictError(
        `job ${jobId} cannot be completed because worker ${workerId} does not own claim`,
        jobId,
      );
    }
    row.status = "completed";
    row.error_message = null;
    row.lease_expires_at = null;
    row.worker_id = workerId;
    row.updated_at = now;
    return this.table.set(row);
  }

  public async markFailed(
    jobId: string,
    workerId: string,
    options?: {
      reason?: string;
      failure?: JobFailureReason;
      now?: string;
      retryBackoffMs?: number;
    },
  ): Promise<JobRecord> {
    const row = await this.getById(jobId);
    if (!row) {
      throw new Error(`job ${jobId} not found`);
    }
    if (row.status !== "claimed" || row.worker_id !== workerId) {
      throw new JobLeaseConflictError(
        `job ${jobId} cannot be failed because worker ${workerId} does not own claim`,
        jobId,
      );
    }
    const now = options?.now ?? this.now();
    const failure = options?.failure ?? "retryable";
    row.attempts += 1;
    row.error_message = options?.reason ?? "execution failed";
    row.updated_at = now;

    if (failure === "non_retryable" || row.attempts >= row.max_attempts) {
      row.status = "dead_lettered";
      row.lease_expires_at = null;
      row.worker_id = null;
      row.run_after = now;
      return this.table.set(row);
    }

    const delayMs = options?.retryBackoffMs ?? deterministicRetryDelayMs(row.attempts);
    row.status = "pending";
    row.worker_id = null;
    row.lease_expires_at = null;
    row.run_after = addMilliseconds(now, delayMs);
    return this.table.set(row);
  }

  public async interrupt(
    jobId: string,
    workerId: string,
    options?: {
      reason?: string;
      now?: string;
      reclaimDelayMs?: number;
      retryable?: boolean;
    },
  ): Promise<JobRecord> {
    const row = await this.getById(jobId);
    if (!row) {
      throw new Error(`job ${jobId} not found`);
    }
    if (row.status !== "claimed" || row.worker_id !== workerId) {
      throw new JobLeaseConflictError(
        `job ${jobId} cannot be interrupted because worker ${workerId} does not own claim`,
        jobId,
      );
    }

    const now = options?.now ?? this.now();
    const retryable = options?.retryable ?? true;
    row.updated_at = now;
    row.error_message = options?.reason ?? "interrupted";
    row.attempts += 1;
    if (!retryable || row.attempts >= row.max_attempts) {
      row.status = "dead_lettered";
      row.run_after = now;
    } else {
      row.status = "pending";
      row.run_after = addMilliseconds(now, options?.reclaimDelayMs ?? deterministicRetryDelayMs(row.attempts));
    }
    row.worker_id = null;
    row.lease_expires_at = null;
    return this.table.set(row);
  }

  public async recoverExpiredLeases(now: string = this.now()): Promise<JobRecord[]> {
    const recovered: JobRecord[] = [];
    for (const row of this.table.all()) {
      if (row.status !== "claimed") {
        continue;
      }
      if (!isLeaseExpired(row.lease_expires_at, now)) {
        continue;
      }
      row.attempts += 1;
      if (row.attempts >= row.max_attempts) {
        row.status = "dead_lettered";
        row.run_after = now;
        row.error_message = "lease expired";
        row.worker_id = null;
        row.lease_expires_at = null;
        recovered.push(this.table.set(row));
        continue;
      }
      row.status = "pending";
      row.error_message = "lease expired";
      row.run_after = addMilliseconds(now, deterministicRetryDelayMs(row.attempts));
      row.worker_id = null;
      row.lease_expires_at = null;
      row.updated_at = now;
      recovered.push(this.table.set(row));
    }
    return recovered;
  }
}

export class SyntheticSeedRepository {
  public constructor(
    private readonly table: InMemoryTable<SyntheticSeedRecord>,
    private readonly partitions: InMemoryTable<PartitionRecord>,
    private readonly options?: {
      now?: () => string;
    },
  ) {}

  private now(): string {
    return (this.options?.now || nowIso)();
  }

  private assertSyntheticPartition(partitionId: string): PartitionRecord {
    const partition = this.partitions.get(partitionId);
    if (!partition || !partition.synthetic) {
      throw new SyntheticSeedError(`partition ${partitionId} is not synthetic`);
    }
    return partition;
  }

  public async listByPartition(partitionId: string): Promise<SyntheticSeedRecord[]> {
    return this.table.all().filter((row) => row.partition_id === partitionId);
  }

  public async getByTag(partitionId: string, tag: string): Promise<SyntheticSeedRecord | null> {
    const rows = await this.listByPartition(partitionId);
    return rows.find((row) => row.tag === tag && !row.is_deleted) || null;
  }

  public async seed(draft: SyntheticSeedDraft): Promise<SyntheticSeedRecord> {
    const partition = this.assertSyntheticPartition(draft.partitionId);
    const existing = await this.getByTag(draft.partitionId, draft.tag);
    const tokenHash = hashCustodyToken(draft.custodyToken);

    if (existing) {
      if (existing.custody_token_hash !== tokenHash) {
        throw new SyntheticSeedError(
          `custody mismatch while reseeding partition ${partition.partition_key} tag ${draft.tag}`,
        );
      }
      return existing;
    }

    const createdAt = this.now();
    const row: SyntheticSeedRecord = {
      id: randomUUID(),
      partition_id: partition.id,
      tag: draft.tag,
      seed_version: 1,
      seeded_at: createdAt,
      reset_count: 0,
      custody_token_hash: tokenHash,
      status: "active",
      last_reset_at: null,
      completed_at: null,
      created_by: draft.createdBy,
      is_deleted: false,
      created_at: createdAt,
      updated_at: createdAt,
    };
    return this.table.set(row);
  }

  public async reset(
    partitionId: string,
    tag: string,
    custodyToken: string,
    now: string = this.now(),
  ): Promise<SyntheticSeedRecord> {
    const partition = this.assertSyntheticPartition(partitionId);
    const row = await this.getByTag(partition.id, tag);
    if (!row) {
      throw new SyntheticSeedError(
        `synthetic seed for partition ${partition.partition_key} tag ${tag} not found`,
      );
    }
    if (row.custody_token_hash !== hashCustodyToken(custodyToken)) {
      throw new SyntheticSeedError(`custody mismatch for partition ${partition.partition_key} tag ${tag}`);
    }
    row.seed_version += 1;
    row.reset_count += 1;
    row.status = "active";
    row.last_reset_at = now;
    row.seeded_at = now;
    row.updated_at = now;
    return this.table.set(row);
  }

  public async seal(partitionId: string, tag: string, custodyToken: string): Promise<SyntheticSeedRecord> {
    const partition = this.assertSyntheticPartition(partitionId);
    const row = await this.getByTag(partition.id, tag);
    if (!row) {
      throw new SyntheticSeedError(
        `synthetic seed for partition ${partition.partition_key} tag ${tag} not found`,
      );
    }
    if (row.custody_token_hash !== hashCustodyToken(custodyToken)) {
      throw new SyntheticSeedError(`custody mismatch for partition ${partition.partition_key} tag ${tag}`);
    }
    const now = this.now();
    row.status = "sealed";
    row.updated_at = now;
    row.completed_at = now;
    return this.table.set(row);
  }
}

export class MutableRepositories {
  public readonly partitions: PartitionRepository;
  public readonly principals: PrincipalRepository;
  public readonly tasks: TaskRepository;
  public readonly decisions: DecisionRepository;
  public readonly outbox: OutboxRepository;
  public readonly audit: AuditRepository;
  public readonly jobs: JobRepository;
  public readonly syntheticSeeds: SyntheticSeedRepository;

  public constructor(snapshot: DatabaseSnapshot) {
    this.partitions = new PartitionRepository(snapshot.partitions);
    this.principals = new PrincipalRepository(snapshot.principals);
    this.tasks = new TaskRepository(snapshot.tasks);
    this.decisions = new DecisionRepository(snapshot.decisions);
    this.outbox = new OutboxRepository(snapshot.outbox);
    this.audit = new AuditRepository(snapshot.audit);
    this.jobs = new JobRepository(snapshot.jobs);
    this.syntheticSeeds = new SyntheticSeedRepository(snapshot.syntheticSeeds, snapshot.partitions);
  }
}

class DatabaseSnapshot {
  public readonly partitions: InMemoryTable<PartitionRecord>;
  public readonly principals: InMemoryTable<PrincipalRecord>;
  public readonly tasks: InMemoryTable<TaskRecord>;
  public readonly decisions: InMemoryTable<DecisionRecord>;
  public readonly outbox: InMemoryTable<OutboxEventRecord>;
  public readonly audit: InMemoryTable<AuditEventRecord>;
  public readonly jobs: InMemoryTable<JobRecord>;
  public readonly syntheticSeeds: InMemoryTable<SyntheticSeedRecord>;
  public idempotency: Map<string, StoredIdempotency>;

  public constructor(existing?: DatabaseSnapshot) {
    this.partitions = existing ? existing.partitions.clone() : new InMemoryTable<PartitionRecord>();
    this.principals = existing ? existing.principals.clone() : new InMemoryTable<PrincipalRecord>();
    this.tasks = existing ? existing.tasks.clone() : new InMemoryTable<TaskRecord>();
    this.decisions = existing ? existing.decisions.clone() : new InMemoryTable<DecisionRecord>();
    this.outbox = existing ? existing.outbox.clone() : new InMemoryTable<OutboxEventRecord>();
    this.audit = existing ? existing.audit.clone() : new InMemoryTable<AuditEventRecord>();
    this.jobs = existing ? existing.jobs.clone() : new InMemoryTable<JobRecord>();
    this.syntheticSeeds = existing ? existing.syntheticSeeds.clone() : new InMemoryTable<SyntheticSeedRecord>();
    this.idempotency = existing
      ? new Map(existing.idempotency)
      : new Map<string, StoredIdempotency>();
  }

  public createRepositories(): MutableRepositories {
    return new MutableRepositories(this);
  }
}

export class RepositoryStore {
  private activeState: DatabaseSnapshot;

  public constructor() {
    this.activeState = new DatabaseSnapshot();
  }

  public beginUnitOfWork<T>(
    command: CommandEnvelope,
    mutate: (scope: MutableRepositories) => Promise<T>,
    options?: {
      idempotentSummary?: (value: T) => Record<string, unknown>;
    },
  ): Promise<CommandExecutionResult<T>> {
    return this.execute(command, mutate, options);
  }

  public async execute<T>(
    command: CommandEnvelope,
    mutate: (scope: MutableRepositories) => Promise<T>,
    options?: {
      idempotentSummary?: (value: T) => Record<string, unknown>;
    },
  ): Promise<CommandExecutionResult<T>> {
    if (!command.idempotencyKey) {
      throw new Error("command.idempotencyKey is required for epsilon-02 unit-of-work execution");
    }

    const requestHash = hashCommandPayload({
      command: command.command,
      partitionId: command.partitionId,
      actorId: command.actorId,
      correlationId: command.correlationId,
      causationId: command.causationId,
      payload: command.payload,
    });

    const existing = this.activeState.idempotency.get(command.idempotencyKey);
    if (existing) {
      if (existing.requestHash === requestHash) {
        return {
          status: "replayed",
          replay_of: existing.receipt.id,
          receipt: clone(existing.receipt),
          output: null,
        };
      }
      throw new IdempotentConflictError(
        `idempotency conflict for ${command.idempotencyKey}`,
        clone(existing.receipt),
      );
    }

    const workingState = new DatabaseSnapshot(this.activeState);
    const scope = workingState.createRepositories();

    let output: T;
    try {
      output = await mutate(scope);
    } catch (error) {
      throw error;
    }

    const requestSummary = options?.idempotentSummary
      ? options.idempotentSummary(output)
      : { command: command.command, changedRows: 0 };

    const receipt: CommandReceipt = {
      id: randomUUID(),
      command: command.command,
      idempotency_key: command.idempotencyKey,
      partition_id: command.partitionId,
      actor_id: command.actorId,
      correlation_id: command.correlationId,
      causation_id: command.causationId,
      status: "accepted",
      request_hash: requestHash,
      replay_of: null,
      result_summary: buildSummary(requestSummary),
      created_at: nowIso(),
    };

    workingState.idempotency.set(command.idempotencyKey, {
      requestHash,
      receipt,
    });

    this.activeState = workingState;

    return {
      status: "accepted",
      replay_of: null,
      receipt,
      output,
    };
  }

  public snapshot(): {
    partitions: PartitionRecord[];
    principals: PrincipalRecord[];
    tasks: TaskRecord[];
    decisions: DecisionRecord[];
    outbox: OutboxEventRecord[];
    audit: AuditEventRecord[];
    jobs: JobRecord[];
    syntheticSeeds: SyntheticSeedRecord[];
  } {
    return {
      partitions: this.activeState.partitions.all(),
      principals: this.activeState.principals.all(),
      tasks: this.activeState.tasks.all(),
      decisions: this.activeState.decisions.all(),
      outbox: this.activeState.outbox.all(),
      audit: this.activeState.audit.all(),
      jobs: this.activeState.jobs.all(),
      syntheticSeeds: this.activeState.syntheticSeeds.all(),
    };
  }
}

export default RepositoryStore;
