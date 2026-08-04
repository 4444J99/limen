/**
 * Database schema and migration contract for EPSILON-01.
 *
 * The SQL here is PostgreSQL-first and intentionally normalized by partition boundary:
 * every mutable business record carries partition_id, provenance, and immutable lineage.
 */

export type PartitionClassification = "private" | "confidential" | "restricted";
export type LifecycleStatus = "draft" | "active" | "waiting" | "in_progress" | "done" | "cancelled";
export type OutboxStatus = "pending" | "claimed" | "done" | "failed" | "dead_lettered";

export interface PartitionRecord {
  id: string;
  partition_key: string;
  display_name: string;
  synthetic: boolean;
  classification: PartitionClassification;
  retention_days: number;
  created_by: string | null;
  provenance: string;
  is_deleted: boolean;
  record_version: number;
  created_at: string;
  updated_at: string;
}

export interface PrincipalRecord {
  id: string;
  principal_type: string;
  external_subject: string | null;
  principal_name: string | null;
  contact: Record<string, unknown> | null;
  status: string;
  provenance: string;
  created_at: string;
  updated_at: string;
}

export type TaskStatus = LifecycleStatus | "open";

export type JobStatus = "pending" | "claimed" | "completed" | "failed" | "dead_lettered";

export type SyntheticSeedStatus = "active" | "resetting" | "sealed";

export interface TaskRecord {
  id: string;
  partition_id: string;
  title: string;
  status: TaskStatus;
  created_by: string;
  due_at: string | null;
  provenance: string;
  created_at: string;
  updated_at: string;
}

export interface DecisionRecord {
  id: string;
  partition_id: string;
  principal_id: string | null;
  title: string;
  status: string;
  provenance: string;
  created_at: string;
}

export interface JobRecord {
  id: string;
  partition_id: string | null;
  idempotency_key: string;
  job_type: string;
  payload: Record<string, unknown>;
  status: JobStatus;
  worker_id: string | null;
  lease_expires_at: string | null;
  attempts: number;
  max_attempts: number;
  run_after: string;
  error_message: string | null;
  synthetic_seed_tag: string | null;
  custody_token: string | null;
  provenance: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface SyntheticSeedRecord {
  id: string;
  partition_id: string;
  tag: string;
  seed_version: number;
  seeded_at: string | null;
  reset_count: number;
  custody_token_hash: string;
  status: SyntheticSeedStatus;
  last_reset_at: string | null;
  completed_at: string | null;
  created_by: string;
  is_deleted: boolean;
  created_at: string;
  updated_at: string;
}

export interface OutboxEventRecord {
  id: string;
  partition_id: string;
  correlation_id: string;
  causation_id: string;
  event_type: string;
  aggregate_type: string;
  aggregate_id: string;
  payload: Record<string, unknown>;
  signature: string | null;
  status: OutboxStatus;
  attempts: number;
  target_endpoint: string | null;
  processed_at: string | null;
  provenance: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AuditEventRecord {
  id: string;
  partition_id: string;
  actor_id: string;
  causation_id: string;
  correlation_id: string;
  action: string;
  resource_type: string;
  resource_id: string;
  outcome: Record<string, unknown>;
  redacted_payload: Record<string, unknown>;
  provenance: Record<string, unknown>;
  created_at: string;
}

export interface MigrationManifestEntry {
  id: string;
  filename: string;
  description: string;
  scope: string;
  dependsOn?: string[];
  sql: string;
}

const MIGRATION_0001_SQL = `
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  checksum TEXT NOT NULL,
  description TEXT NOT NULL,
  scope TEXT NOT NULL,
  depends_on TEXT[],
  applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  executed_by TEXT NOT NULL DEFAULT CURRENT_USER
);

CREATE TABLE IF NOT EXISTS partitions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_key TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  synthetic BOOLEAN NOT NULL DEFAULT FALSE,
  classification TEXT NOT NULL DEFAULT 'private',
  retention_days INTEGER NOT NULL DEFAULT 365,
  created_by UUID,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
  deleted_at TIMESTAMPTZ,
  record_version INTEGER NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (classification IN ('private', 'confidential', 'restricted')),
  CHECK (retention_days > 0)
);

CREATE TABLE IF NOT EXISTS principals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  principal_type TEXT NOT NULL DEFAULT 'owner',
  external_subject TEXT NOT NULL UNIQUE,
  principal_name TEXT NOT NULL,
  contact JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'active',
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
  deleted_at TIMESTAMPTZ,
  record_version INTEGER NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (principal_type IN ('owner', 'service', 'agent', 'collaborator'))
);

CREATE TABLE IF NOT EXISTS memberships (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  principal_id UUID NOT NULL REFERENCES principals(id) ON DELETE RESTRICT,
  role_name TEXT NOT NULL,
  granted_by UUID NOT NULL REFERENCES principals(id) ON DELETE RESTRICT,
  grant_reason TEXT NOT NULL DEFAULT 'init',
  grant_receipt_id UUID,
  start_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  end_at TIMESTAMPTZ,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (role_name IN ('owner', 'admin', 'editor', 'viewer', 'auditor')),
  CHECK (end_at IS NULL OR end_at > start_at),
  UNIQUE (partition_id, principal_id, role_name)
);

CREATE TABLE IF NOT EXISTS capability_grants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  principal_id UUID NOT NULL REFERENCES principals(id) ON DELETE RESTRICT,
  resource TEXT NOT NULL,
  action TEXT NOT NULL,
  effect TEXT NOT NULL DEFAULT 'allow',
  constraints JSONB NOT NULL DEFAULT '{}'::jsonb,
  issued_by UUID NOT NULL REFERENCES principals(id) ON DELETE RESTRICT,
  issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMPTZ,
  revocation_reason TEXT,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (partition_id, principal_id, resource, action),
  CHECK (effect IN ('allow', 'deny'))
);

CREATE TABLE IF NOT EXISTS policy_decisions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  actor_id UUID NOT NULL REFERENCES principals(id) ON DELETE RESTRICT,
  action TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id UUID,
  allowed BOOLEAN NOT NULL,
  reason_code TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  request_id UUID NOT NULL,
  causation_id UUID NOT NULL,
  correlation_id UUID NOT NULL,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_partitions_partition_key ON partitions (partition_key);
CREATE INDEX IF NOT EXISTS idx_memberships_partition_id ON memberships (partition_id);
CREATE INDEX IF NOT EXISTS idx_memberships_principal_id ON memberships (principal_id);
CREATE INDEX IF NOT EXISTS idx_capability_grants_partition_id ON capability_grants (partition_id);
CREATE INDEX IF NOT EXISTS idx_policy_decisions_partition_id ON policy_decisions (partition_id);
`;

const MIGRATION_0002_SQL = `
CREATE TABLE IF NOT EXISTS persons (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  display_name TEXT NOT NULL,
  email TEXT,
  phone TEXT,
  notes TEXT,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
  deleted_at TIMESTAMPTZ,
  created_by UUID NOT NULL REFERENCES principals(id),
  record_version INTEGER NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (partition_id, display_name, email)
);

CREATE TABLE IF NOT EXISTS organizations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  legal_name TEXT NOT NULL,
  preferred_name TEXT,
  website TEXT,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by UUID NOT NULL REFERENCES principals(id),
  is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
  deleted_at TIMESTAMPTZ,
  record_version INTEGER NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (partition_id, legal_name)
);

CREATE TABLE IF NOT EXISTS relationships (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  subject_person_id UUID NOT NULL REFERENCES persons(id) ON DELETE RESTRICT,
  object_entity_type TEXT NOT NULL,
  object_entity_id UUID NOT NULL,
  relation_type TEXT NOT NULL,
  notes TEXT,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by UUID NOT NULL REFERENCES principals(id),
  status TEXT NOT NULL DEFAULT 'active',
  record_version INTEGER NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (object_entity_type IN ('person', 'organization')),
  CHECK (status IN ('active', 'stale', 'closed'))
);

CREATE TABLE IF NOT EXISTS engagements (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  name TEXT NOT NULL,
  organization_id UUID REFERENCES organizations(id),
  lifecycle TEXT NOT NULL DEFAULT 'active',
  objective TEXT,
  confidence INTEGER NOT NULL DEFAULT 100,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by UUID NOT NULL REFERENCES principals(id),
  is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
  deleted_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (lifecycle IN ('active', 'paused', 'closed', 'deferred'))
);

CREATE TABLE IF NOT EXISTS projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  engagement_id UUID REFERENCES engagements(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  scope JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'active',
  due_at TIMESTAMPTZ,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by UUID NOT NULL REFERENCES principals(id),
  is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
  deleted_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (status IN ('active', 'suspended', 'completed', 'cancelled'))
);

CREATE TABLE IF NOT EXISTS matters (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  title TEXT NOT NULL,
  description TEXT,
  owner_principal_id UUID NOT NULL REFERENCES principals(id),
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by UUID NOT NULL REFERENCES principals(id),
  is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
  deleted_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS interactions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  engagement_id UUID NOT NULL REFERENCES engagements(id) ON DELETE RESTRICT,
  interaction_type TEXT NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  actor_id UUID NOT NULL REFERENCES principals(id),
  details JSONB NOT NULL DEFAULT '{}'::jsonb,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (interaction_type IN ('call', 'email', 'note', 'event', 'meeting'))
);

CREATE TABLE IF NOT EXISTS meetings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  title TEXT NOT NULL,
  planned_for TIMESTAMPTZ NOT NULL,
  outcome TEXT,
  summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by UUID NOT NULL REFERENCES principals(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS message_references (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  source_id UUID NOT NULL,
  source_system TEXT NOT NULL,
  source_created_at TIMESTAMPTZ,
  meeting_id UUID REFERENCES meetings(id) ON DELETE SET NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS notes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  author_id UUID NOT NULL REFERENCES principals(id),
  engagement_id UUID REFERENCES engagements(id),
  project_id UUID REFERENCES projects(id),
  matter_id UUID REFERENCES matters(id),
  body TEXT NOT NULL,
  classification TEXT NOT NULL DEFAULT 'private',
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by UUID NOT NULL REFERENCES principals(id),
  is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
  deleted_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (classification IN ('private', 'confidential', 'restricted'))
);

CREATE TABLE IF NOT EXISTS artifacts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  owner_type TEXT NOT NULL,
  owner_id UUID NOT NULL,
  title TEXT NOT NULL,
  storage_key TEXT NOT NULL,
  digest_algorithm TEXT NOT NULL DEFAULT 'sha256',
  digest_value TEXT NOT NULL,
  mime_type TEXT,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by UUID NOT NULL REFERENCES principals(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (partition_id, storage_key)
);

CREATE TABLE IF NOT EXISTS transcript_references (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE RESTRICT,
  transcript_artifact_id UUID NOT NULL REFERENCES artifacts(id),
  checksum_algorithm TEXT NOT NULL DEFAULT 'sha256',
  checksum_value TEXT NOT NULL,
  is_raw BOOLEAN NOT NULL DEFAULT TRUE,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS decisions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  engagement_id UUID REFERENCES engagements(id),
  title TEXT NOT NULL,
  rationale TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft',
  decided_by UUID REFERENCES principals(id),
  due_date TIMESTAMPTZ,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by UUID NOT NULL REFERENCES principals(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (status IN ('draft', 'active', 'superseded', 'closed'))
);

CREATE TABLE IF NOT EXISTS commitments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  decision_id UUID REFERENCES decisions(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  assignee_id UUID,
  status TEXT NOT NULL DEFAULT 'open',
  due_at TIMESTAMPTZ,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by UUID NOT NULL REFERENCES principals(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (status IN ('open', 'in_progress', 'waiting', 'done', 'cancelled'))
);

CREATE TABLE IF NOT EXISTS tasks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  engagement_id UUID REFERENCES engagements(id),
  commitment_id UUID REFERENCES commitments(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  description TEXT,
  status TEXT NOT NULL DEFAULT 'draft',
  assignee_id UUID REFERENCES principals(id),
  priority INTEGER NOT NULL DEFAULT 3,
  due_at TIMESTAMPTZ,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by UUID NOT NULL REFERENCES principals(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (status IN ('draft', 'open', 'in_progress', 'waiting', 'done', 'cancelled')),
  CHECK (priority BETWEEN 1 AND 5)
);

CREATE TABLE IF NOT EXISTS milestones (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  name TEXT NOT NULL,
  due_at TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'planned',
  completion_artifact_id UUID REFERENCES artifacts(id),
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by UUID NOT NULL REFERENCES principals(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (status IN ('planned', 'active', 'complete', 'deferred', 'abandoned'))
);

CREATE TABLE IF NOT EXISTS risks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  matter_id UUID NOT NULL REFERENCES matters(id) ON DELETE RESTRICT,
  title TEXT NOT NULL,
  likelihood INTEGER NOT NULL DEFAULT 3,
  impact INTEGER NOT NULL DEFAULT 3,
  mitigation TEXT,
  status TEXT NOT NULL DEFAULT 'open',
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by UUID NOT NULL REFERENCES principals(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (likelihood BETWEEN 1 AND 5),
  CHECK (impact BETWEEN 1 AND 5),
  CHECK (status IN ('open', 'accepted', 'mitigated', 'closed'))
);

CREATE TABLE IF NOT EXISTS tags (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  label TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'general',
  created_by UUID NOT NULL REFERENCES principals(id),
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (partition_id, label, category)
);

CREATE TABLE IF NOT EXISTS links (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  source_id UUID NOT NULL,
  source_type TEXT NOT NULL,
  target_id UUID NOT NULL,
  target_type TEXT NOT NULL,
  link_strength INTEGER NOT NULL DEFAULT 1,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by UUID NOT NULL REFERENCES principals(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (link_strength BETWEEN 1 AND 5),
  CHECK (source_type IN ('person', 'organization', 'engagement', 'project', 'matter', 'note', 'task', 'artifact')),
  CHECK (target_type IN ('person', 'organization', 'engagement', 'project', 'matter', 'note', 'task', 'artifact', 'decision'))
);

CREATE INDEX IF NOT EXISTS idx_persons_partition_id ON persons (partition_id);
CREATE INDEX IF NOT EXISTS idx_organizations_partition_id ON organizations (partition_id);
CREATE INDEX IF NOT EXISTS idx_relationships_partition_id ON relationships (partition_id);
CREATE INDEX IF NOT EXISTS idx_engagements_partition_id ON engagements (partition_id);
CREATE INDEX IF NOT EXISTS idx_projects_partition_id ON projects (partition_id);
CREATE INDEX IF NOT EXISTS idx_matters_partition_id ON matters (partition_id);
CREATE INDEX IF NOT EXISTS idx_interactions_partition_id ON interactions (partition_id);
CREATE INDEX IF NOT EXISTS idx_tasks_partition_id ON tasks (partition_id);
CREATE INDEX IF NOT EXISTS idx_commitments_partition_id ON commitments (partition_id);
CREATE INDEX IF NOT EXISTS idx_milestones_partition_id ON milestones (partition_id);
CREATE INDEX IF NOT EXISTS idx_risks_partition_id ON risks (partition_id);
`;

const MIGRATION_0003_SQL = `
CREATE TABLE IF NOT EXISTS sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  source_key TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_config JSONB NOT NULL DEFAULT '{}'::jsonb,
  lifecycle TEXT NOT NULL DEFAULT 'enabled',
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by UUID NOT NULL REFERENCES principals(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (partition_id, source_key),
  CHECK (source_type IN ('email', 'chat', 'doc', 'calendar', 'manual')),
  CHECK (lifecycle IN ('enabled', 'disabled', 'revoked'))
);

CREATE TABLE IF NOT EXISTS source_cursors (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id UUID NOT NULL REFERENCES sources(id) ON DELETE RESTRICT,
  cursor_key TEXT NOT NULL,
  cursor_value JSONB NOT NULL DEFAULT '{}'::jsonb,
  cursor_scope TEXT NOT NULL DEFAULT 'global',
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (source_id, cursor_key, cursor_scope)
);

CREATE TABLE IF NOT EXISTS source_envelopes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  source_id UUID NOT NULL REFERENCES sources(id) ON DELETE RESTRICT,
  external_id TEXT NOT NULL,
  envelope_type TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  payload_size INTEGER NOT NULL DEFAULT 0,
  checksum TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'raw',
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (source_id, external_id, revision),
  CHECK (status IN ('raw', 'normalized', 'rejected', 'quarantined'))
);

CREATE TABLE IF NOT EXISTS import_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  source_id UUID NOT NULL REFERENCES sources(id) ON DELETE RESTRICT,
  requested_by UUID NOT NULL REFERENCES principals(id),
  status TEXT NOT NULL DEFAULT 'running',
  import_reason TEXT NOT NULL DEFAULT 'initial',
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  finished_at TIMESTAMPTZ,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  CHECK (status IN ('running', 'completed', 'failed', 'cancelled'))
);

CREATE TABLE IF NOT EXISTS normalization_receipts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  source_envelope_id UUID NOT NULL REFERENCES source_envelopes(id) ON DELETE RESTRICT,
  normalization_pass INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'accepted',
  summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (status IN ('accepted', 'rejected', 'duplicate'))
);

CREATE TABLE IF NOT EXISTS outbox_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  correlation_id UUID NOT NULL,
  causation_id UUID NOT NULL,
  event_type TEXT NOT NULL,
  aggregate_type TEXT NOT NULL,
  aggregate_id UUID NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  signature TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  target_endpoint TEXT,
  processed_at TIMESTAMPTZ,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (status IN ('pending', 'claimed', 'done', 'failed', 'dead_lettered'))
);

CREATE TABLE IF NOT EXISTS jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID REFERENCES partitions(id) ON DELETE SET NULL,
  idempotency_key TEXT NOT NULL UNIQUE,
  job_type TEXT NOT NULL,
  payload JSONB NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  worker_id TEXT,
  lease_expires_at TIMESTAMPTZ,
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  run_after TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  error_message TEXT,
  synthetic_seed_tag TEXT,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (status IN ('pending', 'claimed', 'completed', 'failed', 'dead_lettered'))
);

CREATE TABLE IF NOT EXISTS notifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  principal_id UUID NOT NULL REFERENCES principals(id),
  channel TEXT NOT NULL DEFAULT 'inbox',
  template_key TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  sent BOOLEAN NOT NULL DEFAULT FALSE,
  seen BOOLEAN NOT NULL DEFAULT FALSE,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (channel IN ('inbox', 'email', 'webhook'))
);

CREATE TABLE IF NOT EXISTS saved_views (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  principal_id UUID NOT NULL REFERENCES principals(id),
  name TEXT NOT NULL,
  resource_scope TEXT NOT NULL,
  definition JSONB NOT NULL DEFAULT '{}'::jsonb,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (partition_id, principal_id, name)
);

CREATE TABLE IF NOT EXISTS search_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  source_type TEXT NOT NULL,
  source_id UUID NOT NULL,
  searchable_text TEXT,
  search_vector TSVECTOR,
  rank_boost INTEGER NOT NULL DEFAULT 0,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (partition_id, source_type, source_id)
);

CREATE TABLE IF NOT EXISTS search_sync_receipts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  search_document_id UUID NOT NULL REFERENCES search_documents(id) ON DELETE RESTRICT,
  status TEXT NOT NULL DEFAULT 'requested',
  request_id UUID NOT NULL,
  worker_id TEXT,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (status IN ('requested', 'synced', 'failed'))
);

CREATE TABLE IF NOT EXISTS automation_rules (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  name TEXT NOT NULL,
  trigger_event TEXT NOT NULL,
  condition_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  action_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by UUID NOT NULL REFERENCES principals(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS automation_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  rule_id UUID NOT NULL REFERENCES automation_rules(id) ON DELETE RESTRICT,
  trigger_event_id UUID NOT NULL,
  status TEXT NOT NULL DEFAULT 'approved',
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ended_at TIMESTAMPTZ,
  requested_by UUID NOT NULL REFERENCES principals(id),
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  CHECK (status IN ('approved', 'denied', 'running', 'succeeded', 'failed'))
);

CREATE TABLE IF NOT EXISTS audit_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  actor_id UUID NOT NULL REFERENCES principals(id),
  causation_id UUID NOT NULL,
  correlation_id UUID NOT NULL,
  action TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id UUID NOT NULL,
  outcome JSONB NOT NULL DEFAULT '{}'::jsonb,
  redacted_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS retention_rules (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  resource_type TEXT NOT NULL,
  keep_days INTEGER NOT NULL CHECK (keep_days >= 30),
  legal_hold_override BOOLEAN NOT NULL DEFAULT FALSE,
  created_by UUID NOT NULL REFERENCES principals(id),
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS legal_holds (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  reason TEXT NOT NULL,
  resource_selector JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'active',
  created_by UUID NOT NULL REFERENCES principals(id),
  expires_at TIMESTAMPTZ,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (status IN ('active', 'released'))
);

CREATE TABLE IF NOT EXISTS export_bundles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  requested_by UUID NOT NULL REFERENCES principals(id),
  bundle_path TEXT NOT NULL,
  checksum_algorithm TEXT NOT NULL DEFAULT 'sha256',
  checksum_value TEXT NOT NULL,
  manifest JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'created',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  CHECK (status IN ('created', 'sealed', 'validated', 'corrupted', 'deleted'))
);

CREATE TABLE IF NOT EXISTS restore_receipts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partition_id UUID NOT NULL REFERENCES partitions(id) ON DELETE RESTRICT,
  export_bundle_id UUID NOT NULL REFERENCES export_bundles(id),
  restore_scope JSONB NOT NULL DEFAULT '{}'::jsonb,
  restore_plan JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'pending',
  requested_by UUID NOT NULL REFERENCES principals(id),
  approved_by UUID,
  restored_at TIMESTAMPTZ,
  checksum_algorithm TEXT NOT NULL DEFAULT 'sha256',
  checksum_value TEXT NOT NULL,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'rolled_back'))
);

CREATE INDEX IF NOT EXISTS idx_outbox_events_partition_id ON outbox_events (partition_id);
CREATE INDEX IF NOT EXISTS idx_jobs_partition_id ON jobs (partition_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status);
CREATE INDEX IF NOT EXISTS idx_source_cursors_partition_id ON source_cursors (source_id);
CREATE INDEX IF NOT EXISTS idx_source_envelopes_partition_id ON source_envelopes (partition_id);
CREATE INDEX IF NOT EXISTS idx_source_envelopes_source_id ON source_envelopes (source_id);
CREATE INDEX IF NOT EXISTS idx_search_documents_partition_id ON search_documents (partition_id);
CREATE INDEX IF NOT EXISTS idx_automation_rules_partition_id ON automation_rules (partition_id);
CREATE INDEX IF NOT EXISTS idx_automation_runs_partition_id ON automation_runs (partition_id);
`;

const MIGRATION_0004_SQL = `
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cop_owner') THEN
    CREATE ROLE cop_owner NOLOGIN;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cop_migrator') THEN
    CREATE ROLE cop_migrator NOLOGIN;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cop_runtime') THEN
    CREATE ROLE cop_runtime NOLOGIN;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cop_worker') THEN
    CREATE ROLE cop_worker NOLOGIN;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cop_readonly') THEN
    CREATE ROLE cop_readonly NOLOGIN;
  END IF;

  GRANT ALL ON SCHEMA public TO cop_owner;
  GRANT USAGE, CREATE ON SCHEMA public TO cop_migrator, cop_runtime, cop_worker;
  GRANT USAGE ON SCHEMA public TO cop_readonly;
  GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO cop_owner;
  GRANT CONNECT ON DATABASE current_database() TO cop_migrator, cop_runtime, cop_worker, cop_readonly;
  GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO cop_migrator;
  GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO cop_runtime;
  GRANT SELECT ON ALL TABLES IN SCHEMA public TO cop_readonly;
  GRANT SELECT, UPDATE, DELETE ON jobs TO cop_worker;
  GRANT SELECT, INSERT, UPDATE ON outbox_events TO cop_worker;
  GRANT SELECT, INSERT, UPDATE ON automation_runs TO cop_worker;
  GRANT SELECT, INSERT, UPDATE ON jobs TO cop_runtime;
  GRANT USAGE ON SCHEMA public TO cop_migrator;
  ALTER ROLE cop_runtime SET row_security = on;
  ALTER ROLE cop_readonly SET row_security = on;
  REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
END $$;
`;

const MIGRATION_0005_SQL = `
CREATE OR REPLACE FUNCTION cop.current_partition_uuid()
RETURNS UUID
LANGUAGE sql
STABLE
AS $$
  SELECT nullif(current_setting('cop.current_partition_id', true), '')::uuid;
$$;

DO $$
DECLARE
  partitioned_tables TEXT[] := ARRAY[
    'memberships',
    'capability_grants',
    'policy_decisions',
    'persons',
    'organizations',
    'relationships',
    'engagements',
    'projects',
    'matters',
    'interactions',
    'meetings',
    'message_references',
    'notes',
    'artifacts',
    'transcript_references',
    'decisions',
    'commitments',
    'tasks',
    'milestones',
    'risks',
    'tags',
    'links',
    'sources',
    'source_envelopes',
    'import_runs',
    'normalization_receipts',
    'jobs',
    'outbox_events',
    'notifications',
    'saved_views',
    'search_documents',
    'search_sync_receipts',
    'automation_rules',
    'automation_runs',
    'audit_events',
    'retention_rules',
    'legal_holds',
    'export_bundles',
    'restore_receipts'
  ];
  target_table TEXT;
BEGIN
  FOREACH target_table IN ARRAY partitioned_tables
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', target_table);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', target_table);

    EXECUTE format(
      'DROP POLICY IF EXISTS cop_partition_force_deny_%I ON %I',
      target_table,
      target_table
    );
    EXECUTE format(
      'CREATE POLICY cop_partition_force_deny_%I ON %I
         FOR ALL TO PUBLIC
         USING (false)',
      target_table,
      target_table
    );

    EXECUTE format(
      'DROP POLICY IF EXISTS cop_runtime_access_%I_select ON %I',
      target_table,
      target_table
    );
    EXECUTE format(
      'CREATE POLICY cop_runtime_access_%I_select ON %I
         FOR SELECT TO cop_runtime, cop_worker, cop_readonly
         USING (partition_id = cop.current_partition_uuid())',
      target_table,
      target_table
    );

    EXECUTE format(
      'DROP POLICY IF EXISTS cop_runtime_access_%I_modify ON %I',
      target_table,
      target_table
    );
    EXECUTE format(
      'CREATE POLICY cop_runtime_access_%I_modify ON %I
         FOR INSERT, UPDATE, DELETE TO cop_runtime, cop_worker
         USING (partition_id = cop.current_partition_uuid())
         WITH CHECK (partition_id = cop.current_partition_uuid())',
      target_table,
      target_table
    );
  END LOOP;
END $$;

CREATE POLICY cop_owner_bypass_partitions ON partitions
  FOR ALL TO cop_owner
  USING (true)
  WITH CHECK (true);
`;

export const MIGRATIONS: readonly MigrationManifestEntry[] = [
  {
    id: "0001",
    filename: "0001-foundation.sql",
    description: "Create partition, principal, membership, capability, and policy decision foundations.",
    scope: "base",
    sql: MIGRATION_0001_SQL,
  },
  {
    id: "0002",
    filename: "0002-domain-core.sql",
    description: "Create canonical relationship, work, and decision-tracking entities.",
    scope: "domain",
    dependsOn: ["0001"],
    sql: MIGRATION_0002_SQL,
  },
  {
    id: "0003",
    filename: "0003-operability.sql",
    description: "Add source/inbox, jobs, outbox, search, automation, and custody artifacts.",
    scope: "operations",
    dependsOn: ["0002"],
    sql: MIGRATION_0003_SQL,
  },
  {
    id: "0004",
    filename: "0004-roles-and-privileges.sql",
    description: "Create least-privilege Postgres roles and explicit grant boundaries.",
    scope: "security",
    dependsOn: ["0003"],
    sql: MIGRATION_0004_SQL,
  },
  {
    id: "0005",
    filename: "0005-rls.sql",
    description: "Enable forced row-level security on partition tables and deny-by-default policies.",
    scope: "security",
    dependsOn: ["0004"],
    sql: MIGRATION_0005_SQL,
  },
];

export const CREATE_TABLES_SQL = `${MIGRATION_0001_SQL}\n${MIGRATION_0002_SQL}\n${MIGRATION_0003_SQL}`;

export const MIGRATION_MANIFEST = MIGRATIONS.map((migration) => ({
  id: migration.id,
  filename: migration.filename,
  description: migration.description,
  scope: migration.scope,
  dependsOn: migration.dependsOn,
}));

export const CURRENT_SCHEMA_VERSION = MIGRATIONS[MIGRATIONS.length - 1].id;
