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
