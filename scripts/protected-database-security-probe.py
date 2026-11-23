#!/usr/bin/env python3
"""Probe PostgreSQL through the actual backend application connection."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from urllib.parse import urlsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-role", required=True)
    parser.add_argument("--expected-application-table-count", type=int, required=True)
    parser.add_argument("--expected-forced-rls-count", type=int, required=True)
    return parser.parse_args()


async def probe(args: argparse.Namespace) -> dict[str, object]:
    raw_url = os.environ.get("DATABASE_URL")
    if not raw_url:
        raise SystemExit("DATABASE_URL is required; legacy runtime fallback is forbidden")
    username = urlsplit(raw_url).username
    if username != args.expected_role:
        raise SystemExit("backend DATABASE_URL does not use the expected application role")

    engine = create_async_engine(raw_url, pool_pre_ping=True)
    query = text(
        """
        WITH application_tables AS (
            SELECT
                c.oid,
                c.relrowsecurity,
                c.relforcerowsecurity,
                bool_or(a.attname IN ('company_id', 'branch_id'))
                    FILTER (WHERE a.attnum > 0 AND NOT a.attisdropped) AS has_tenant_column,
                EXISTS (
                    SELECT 1
                    FROM pg_policies p
                    WHERE p.schemaname = n.nspname
                      AND p.tablename = c.relname
                      AND p.policyname = 'acp_tenant_isolation'
                ) AS has_tenant_policy
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            LEFT JOIN pg_attribute a ON a.attrelid = c.oid
            WHERE n.nspname = 'public'
              AND c.relkind = 'r'
              -- Qualification-only tables are never part of the live count.
              AND c.relname NOT IN (
                  'backup_coverage_probe',
                  'database_security_probe',
                  'rls_rehearsal_probe'
              )
            GROUP BY c.oid, n.nspname, c.relname, c.relrowsecurity, c.relforcerowsecurity
        )
        SELECT current_user,
               current_database(),
               r.rolsuper,
               r.rolcreaterole,
               r.rolcreatedb,
               r.rolreplication,
               r.rolbypassrls,
               count(*)::int,
               count(*) FILTER (WHERE t.has_tenant_column OR t.has_tenant_policy)::int,
               count(*) FILTER (WHERE (t.has_tenant_column OR t.has_tenant_policy)
                                      AND NOT t.relrowsecurity)::int,
               count(*) FILTER (WHERE (t.has_tenant_column OR t.has_tenant_policy)
                                      AND NOT t.relforcerowsecurity)::int,
               count(*) FILTER (WHERE (t.has_tenant_column OR t.has_tenant_policy)
                                      AND t.relrowsecurity AND t.relforcerowsecurity)::int
        FROM pg_roles r
        CROSS JOIN application_tables t
        WHERE r.rolname = current_user
        GROUP BY current_user, current_database(), r.rolsuper,
                 r.rolcreaterole, r.rolcreatedb, r.rolreplication,
                 r.rolbypassrls
        """
    )
    try:
        async with engine.connect() as connection:
            row = (await connection.execute(query)).one()
    finally:
        await engine.dispose()

    (
        role,
        database,
        superuser,
        createrole,
        createdb,
        replication,
        bypassrls,
        table_count,
        tenant_table_count,
        without_rls,
        without_force,
        forced_count,
    ) = row
    if role != args.expected_role:
        raise SystemExit("active PostgreSQL connection identity mismatch")
    if any((superuser, createrole, createdb, replication, bypassrls)):
        raise SystemExit("application database identity has elevated privileges")
    if table_count != args.expected_application_table_count:
        raise SystemExit(
            f"application table inventory does not match the release contract "
            f"(observed={table_count}, expected={args.expected_application_table_count})"
        )
    if without_rls or without_force or forced_count != args.expected_forced_rls_count:
        raise SystemExit(
            "application database forced-RLS coverage does not match the release contract "
            f"(tenant={tenant_table_count}, forced={forced_count}, "
            f"without_rls={without_rls}, without_force={without_force})"
        )
    return {
        "database": database,
        "role": role,
        "application_table_count": table_count,
        "tenant_table_count": tenant_table_count,
        "forced_rls_count": forced_count,
        "tenant_tables_without_rls": without_rls,
        "tenant_tables_without_forced_rls": without_force,
    }


def main() -> int:
    args = parse_args()
    print(json.dumps(asyncio.run(probe(args)), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
