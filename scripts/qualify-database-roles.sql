-- Reference contract for an isolated rehearsal.  Do not run against Beta
-- without Enterprise release authorization and a verified rollback plan.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'acp_schema_owner') THEN
    CREATE ROLE acp_schema_owner NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'acp_app') THEN
    CREATE ROLE acp_app LOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'acp_migrate') THEN
    CREATE ROLE acp_migrate LOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'acp_backup') THEN
    CREATE ROLE acp_backup LOGIN;
  END IF;
END
$$;

ALTER ROLE acp_app NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE acp_migrate NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE acp_schema_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
GRANT acp_schema_owner TO acp_migrate;
ALTER ROLE acp_migrate SET ROLE acp_schema_owner;

-- Ownership is transferred only by the separately authorized maintenance
-- operator.  The loop is deterministic and covers current tables/sequences;
-- default privileges below cover objects created by future migrations.
ALTER SCHEMA public OWNER TO acp_schema_owner;
DO $$
DECLARE
  object_record record;
BEGIN
  FOR object_record IN
    SELECT schemaname, tablename
    FROM pg_tables
    WHERE schemaname = 'public'
  LOOP
    EXECUTE format(
      'ALTER TABLE %I.%I OWNER TO acp_schema_owner',
      object_record.schemaname,
      object_record.tablename
    );
  END LOOP;
  FOR object_record IN
    SELECT sequence_schema, sequence_name
    FROM information_schema.sequences
    WHERE sequence_schema = 'public'
  LOOP
    EXECUTE format(
      'ALTER SEQUENCE %I.%I OWNER TO acp_schema_owner',
      object_record.sequence_schema,
      object_record.sequence_name
    );
  END LOOP;
END
$$;
-- A complete backup must capture every tenant despite FORCE RLS.  BYPASSRLS
-- is therefore limited to this separately controlled backup principal; it is
-- never granted to the application or migration runtime.
ALTER ROLE acp_backup NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS;
GRANT pg_read_all_data TO acp_backup;

-- The migration owner owns schema objects.  Runtime grants are explicit and
-- are applied to the target schema during the isolated rehearsal; no PUBLIC
-- or database-owner fallback is allowed.
GRANT USAGE ON SCHEMA public TO acp_app, acp_migrate, acp_backup;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO acp_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO acp_app;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO acp_schema_owner;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO acp_schema_owner;

ALTER DEFAULT PRIVILEGES FOR ROLE acp_schema_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO acp_app;
ALTER DEFAULT PRIVILEGES FOR ROLE acp_schema_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO acp_app;
