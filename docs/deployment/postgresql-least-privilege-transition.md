# PostgreSQL Least-Privilege Transition

The release gate treats this as a hard security prerequisite. The current Beta
runtime observation is retained as evidence; no live role or credential is
changed by the release tooling.

## Required roles

- `acp_app`: application runtime only; `LOGIN`, no `SUPERUSER`, `CREATEROLE`,
  `CREATEDB`, `REPLICATION`, or `BYPASSRLS`.
- `acp_migrate`: protected maintenance identity used only by the governed
  migration step; never mounted into ordinary application containers.
- `acp_backup`: backup/restore operator identity held by the protected backup
  procedure; no application login or API exposure.

The actual role names and credentials are provider-controlled deployment
configuration, not committed secrets. Rotation must create and validate the
successor before revoking the predecessor, with a tested rollback target.

## Database requirements

Tenant-owned tables with `company_id` or `branch_id` require forced PostgreSQL
row-level security. Policies must bind the request tenant context to the
authenticated application context; the application query filter remains a
second defense. A role or policy change is not accepted from a live mutation
without a verified backup and isolated restore rehearsal.

## Qualification

`scripts/protected-runtime-check.py --service database-security` verifies the
authenticated runtime identity, all five elevated-role flags, and tenant-table
RLS/forced-RLS counts. It fails closed on unavailable evidence, an elevated
role, or any tenant table without forced RLS. The check is read-only.

The required transition rehearsal is:

1. Restore the protected Beta backup into an isolated PostgreSQL 16 target.
2. Create the three roles and grants there only.
3. Enable and force tenant policies using the canonical application tenant
   context contract.
4. Run migrations through `acp_migrate`.
5. Run representative customer, dispatch, accounting-read, and Demo-isolation
   requests through `acp_app`.
6. Prove denied cross-tenant reads and denied DDL/role-management operations.
7. Run backup and restore through `acp_backup`.
8. Record a rollback receipt before requesting any protected Beta role change.

Until this rehearsal and separate protected authorization are complete, the
database-security gate remains BLOCKED and Release GO is not available.
