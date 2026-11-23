"""Add transaction-scoped tenant RLS for tenant-owned tables.

The migration discovers tenant columns from the target schema instead of
maintaining a fragile hand-written 389-table list.  Tables without a direct
tenant column are intentionally not treated as tenant-owned by this migration;
relationally scoped system tables are covered by the explicit map below.
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

revision = "u1v3x5z7b9d2"
down_revision = "s1a3g5k7m9q2"
branch_labels = None
depends_on = None

_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")
_POLICY = "acp_tenant_isolation"


# These tables have no direct company_id/branch_id but their foreign-key path
# establishes tenant ownership.  System/authentication tables are deliberately
# absent and remain shared.
_RELATIONAL_POLICIES: dict[str, str] = {
    "customer_billing_addresses": "EXISTS (SELECT 1 FROM customers parent WHERE parent.id = customer_billing_addresses.customer_id AND parent.company_id = acp_rls_company_id())",
    "customer_contacts": "EXISTS (SELECT 1 FROM customers parent WHERE parent.id = customer_contacts.customer_id AND parent.company_id = acp_rls_company_id())",
    "customer_notes": "EXISTS (SELECT 1 FROM customers parent WHERE parent.id = customer_notes.customer_id AND parent.company_id = acp_rls_company_id())",
    "service_locations": "EXISTS (SELECT 1 FROM customers parent WHERE parent.id = service_locations.customer_id AND parent.company_id = acp_rls_company_id())",
    "customer_migration_source_rows": "EXISTS (SELECT 1 FROM customer_migration_source_artifacts parent WHERE parent.id = customer_migration_source_rows.artifact_id AND parent.company_id = acp_rls_company_id())",
    "customer_migration_candidates": "EXISTS (SELECT 1 FROM customer_migration_source_rows parent JOIN customer_migration_source_artifacts artifact ON artifact.id = parent.artifact_id WHERE parent.id = customer_migration_candidates.source_row_id AND artifact.company_id = acp_rls_company_id())",
    "customer_migration_child_exceptions": "EXISTS (SELECT 1 FROM customer_migration_source_rows parent JOIN customer_migration_source_artifacts artifact ON artifact.id = parent.artifact_id WHERE parent.id = customer_migration_child_exceptions.source_row_id AND artifact.company_id = acp_rls_company_id())",
    "customer_migration_evidence": "EXISTS (SELECT 1 FROM customer_migration_source_rows parent JOIN customer_migration_source_artifacts artifact ON artifact.id = parent.artifact_id WHERE parent.id = customer_migration_evidence.source_row_id AND artifact.company_id = acp_rls_company_id())",
    "customer_migration_exceptions": "EXISTS (SELECT 1 FROM customer_migration_runs parent WHERE parent.id = customer_migration_exceptions.run_id AND parent.company_id = acp_rls_company_id())",
    "customer_migration_progress": "EXISTS (SELECT 1 FROM customer_migration_runs parent WHERE parent.id = customer_migration_progress.run_id AND parent.company_id = acp_rls_company_id())",
    "customer_migration_staging_runs": "EXISTS (SELECT 1 FROM customer_migration_runs run_parent JOIN customer_migration_source_artifacts artifact ON artifact.id = customer_migration_staging_runs.artifact_id WHERE run_parent.id = customer_migration_staging_runs.run_id AND run_parent.company_id = acp_rls_company_id() AND artifact.company_id = acp_rls_company_id())",
    "demo_environments": "active_company_id = acp_rls_company_id()",
    "factory_control_events": "tenant_company_id = acp_rls_company_id()",
    "factory_control_snapshots": "tenant_company_id = acp_rls_company_id()",
    "factory_lane_states": "EXISTS (SELECT 1 FROM factory_control_events parent WHERE parent.id = factory_lane_states.last_event_id AND parent.tenant_company_id = acp_rls_company_id())",
    "operational_migration_artifact_attempts": "EXISTS (SELECT 1 FROM operational_migration_artifacts parent WHERE parent.id = operational_migration_artifact_attempts.artifact_id AND parent.company_id = acp_rls_company_id())",
    "operational_migration_exceptions": "EXISTS (SELECT 1 FROM operational_migration_runs parent WHERE parent.id = operational_migration_exceptions.run_id AND parent.company_id = acp_rls_company_id())",
    "operational_migration_progress": "EXISTS (SELECT 1 FROM operational_migration_runs parent WHERE parent.id = operational_migration_progress.run_id AND parent.company_id = acp_rls_company_id())",
    "operational_migration_record_outcomes": "EXISTS (SELECT 1 FROM operational_migration_runs parent WHERE parent.id = operational_migration_record_outcomes.run_id AND parent.company_id = acp_rls_company_id())",
    "pending_email_changes": "initiating_company_id = acp_rls_company_id()",
    "role_permissions": "EXISTS (SELECT 1 FROM roles parent WHERE parent.id = role_permissions.role_id AND (parent.company_id IS NULL OR parent.company_id = acp_rls_company_id()))",
}


def _check_identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise RuntimeError(f"Unsafe database identifier discovered: {value!r}")
    return value


def _direct_tenant_tables(connection: sa.Connection) -> list[tuple[str, bool, bool]]:
    rows = connection.execute(
        sa.text(
            """
            SELECT table_name,
                   bool_or(column_name = 'company_id') AS has_company,
                   bool_or(column_name = 'branch_id') AS has_branch
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND column_name IN ('company_id', 'branch_id')
             GROUP BY table_name
             ORDER BY table_name
            """
        )
    )
    return [(str(row[0]), bool(row[1]), bool(row[2])) for row in rows]


def _policy_sql(table: str, has_company: bool, has_branch: bool) -> str:
    table = _check_identifier(table)
    predicates: list[str] = []
    if has_company:
        # A nullable company_id represents an intentionally global/system row
        # in several event and audit tables.  Tenant rows still require an
        # exact company match; a non-null value can never pass without context.
        predicates.append(
            f"({table}.company_id IS NULL OR {table}.company_id = acp_rls_company_id())"
        )
    if has_branch:
        predicates.append(
            f"({table}.branch_id IS NULL OR acp_rls_branch_allowed({table}.branch_id))"
        )
    return " AND ".join(predicates)


def _enable_policy(connection: sa.Connection, table: str, expression: str) -> None:
    table = _check_identifier(table)
    connection.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    connection.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    connection.execute(
        sa.text(f'DROP POLICY IF EXISTS "{_POLICY}" ON "{table}"')
    )
    connection.execute(
        sa.text(
            f'CREATE POLICY "{_POLICY}" ON "{table}" '
            f"USING ({expression}) WITH CHECK ({expression})"
        )
    )


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION acp_rls_company_id()
            RETURNS uuid
            LANGUAGE sql
            STABLE
            AS $$
              SELECT CASE
                WHEN current_setting('app.company_id', true) ~
                  '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
                THEN current_setting('app.company_id', true)::uuid
                ELSE NULL
              END
            $$
            """
        )
    )
    connection.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION acp_rls_branch_allowed(candidate uuid)
            RETURNS boolean
            LANGUAGE sql
            STABLE
            AS $$
              SELECT candidate IS NOT NULL
                 AND candidate::text = ANY(
                   string_to_array(NULLIF(current_setting('app.branch_ids', true), ''), ',')
                 )
            $$
            """
        )
    )

    for table, has_company, has_branch in _direct_tenant_tables(connection):
        _enable_policy(connection, table, _policy_sql(table, has_company, has_branch))

    for table, expression in _RELATIONAL_POLICIES.items():
        _enable_policy(connection, table, expression)


def downgrade() -> None:
    connection = op.get_bind()
    direct_tables = [row[0] for row in _direct_tenant_tables(connection)]
    tables = [*direct_tables, *_RELATIONAL_POLICIES]
    for table in tables:
        table = _check_identifier(table)
        connection.execute(
            sa.text(f'DROP POLICY IF EXISTS "{_POLICY}" ON "{table}"')
        )
        connection.execute(sa.text(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY'))
        connection.execute(sa.text(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY'))
    connection.execute(sa.text("DROP FUNCTION IF EXISTS acp_rls_branch_allowed(uuid)"))
    connection.execute(sa.text("DROP FUNCTION IF EXISTS acp_rls_company_id()"))
