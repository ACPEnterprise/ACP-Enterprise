-- Reference contract for an isolated rehearsal.  Do not run against Beta
-- without Enterprise release authorization and a verified rollback plan.
DO $$
BEGIN
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
ALTER ROLE acp_backup NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

-- Grants are intentionally table/schema-specific and must be generated from
-- the target schema during the isolated rehearsal.  No blanket PUBLIC or
-- database-owner grants belong in this contract.
