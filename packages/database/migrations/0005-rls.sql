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
