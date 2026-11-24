#!/usr/bin/env python3
"""Run the isolated PostgreSQL RLS/role rehearsal.

This script is deliberately fail-closed against live-looking database names.
It creates and removes only a temporary probe table and a no-login role.
"""

from __future__ import annotations

import argparse
import os

import psycopg

SQL = r"""
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'acp_rls_rehearsal') THEN
    EXECUTE 'DROP OWNED BY acp_rls_rehearsal';
    EXECUTE 'DROP ROLE acp_rls_rehearsal';
  END IF;
  EXECUTE 'CREATE ROLE acp_rls_rehearsal NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS';
END
$$;
CREATE TEMP TABLE rls_rehearsal_probe (
  id integer PRIMARY KEY,
  company_id uuid NOT NULL,
  branch_id uuid,
  value text NOT NULL
);
INSERT INTO rls_rehearsal_probe VALUES
  (1, '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000011', 'tenant-a'),
  (2, '00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000022', 'tenant-b');
ALTER TABLE rls_rehearsal_probe ENABLE ROW LEVEL SECURITY;
ALTER TABLE rls_rehearsal_probe FORCE ROW LEVEL SECURITY;
CREATE POLICY acp_tenant_isolation ON rls_rehearsal_probe
  USING (company_id = acp_rls_company_id()
    AND (branch_id IS NULL OR acp_rls_branch_allowed(branch_id)))
  WITH CHECK (company_id = acp_rls_company_id()
    AND (branch_id IS NULL OR acp_rls_branch_allowed(branch_id)));
GRANT SELECT, INSERT ON rls_rehearsal_probe TO acp_rls_rehearsal;

SET ROLE acp_rls_rehearsal;
BEGIN;
DO $$
BEGIN
  IF (SELECT count(*) FROM rls_rehearsal_probe) <> 0 THEN
    RAISE EXCEPTION 'default-deny failed without context';
  END IF;
  PERFORM set_config('app.company_id', '00000000-0000-0000-0000-000000000001', true);
  PERFORM set_config('app.branch_ids', '00000000-0000-0000-0000-000000000011', true);
  IF (SELECT count(*) FROM rls_rehearsal_probe) <> 1 THEN
    RAISE EXCEPTION 'tenant A visibility failed';
  END IF;
  IF (SELECT count(*) FROM rls_rehearsal_probe WHERE company_id = '00000000-0000-0000-0000-000000000002') <> 0 THEN
    RAISE EXCEPTION 'cross-tenant visibility failed';
  END IF;
END
$$;
COMMIT;
BEGIN;
DO $$
BEGIN
  IF (SELECT count(*) FROM rls_rehearsal_probe) <> 0 THEN
    RAISE EXCEPTION 'SET LOCAL context leaked across pooled transaction';
  END IF;
END
$$;
ROLLBACK;
BEGIN;
DO $$
BEGIN
  PERFORM set_config('app.company_id', '00000000-0000-0000-0000-000000000001', true);
  PERFORM set_config('app.branch_ids', '00000000-0000-0000-0000-000000000011', true);
  BEGIN
    INSERT INTO rls_rehearsal_probe VALUES
      (3, '00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000022', 'forbidden');
    RAISE EXCEPTION 'cross-tenant write was accepted';
  EXCEPTION WHEN insufficient_privilege THEN
    NULL;
  END;
END
$$;
ROLLBACK;
RESET ROLE;
DROP TABLE rls_rehearsal_probe;
DROP ROLE acp_rls_rehearsal;
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--allow-rehearsal-database", action="store_true")
    args = parser.parse_args()
    if not args.allow_rehearsal_database:
        raise SystemExit("refusing to run without --allow-rehearsal-database")
    database_name = os.environ.get("PGDATABASE", args.dsn.rsplit("/", 1)[-1])
    if not any(
        token in database_name.lower() for token in ("rehearsal", "qualification")
    ):
        raise SystemExit("refusing to run against a non-rehearsal database name")
    try:
        with psycopg.connect(args.dsn, autocommit=True) as connection:
            connection.execute(SQL)
    except psycopg.Error as error:
        raise SystemExit(
            f"database security rehearsal failed: {type(error).__name__}: {error}"
        ) from error
    print("RLS_DEFAULT_DENY=PASS")
    print("RLS_CROSS_TENANT_READ=PASS")
    print("RLS_CROSS_TENANT_WRITE=PASS")
    print("RLS_TRANSACTION_RESET=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
