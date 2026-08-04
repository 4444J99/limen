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
