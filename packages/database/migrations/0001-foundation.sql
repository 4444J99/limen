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

