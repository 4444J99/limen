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
