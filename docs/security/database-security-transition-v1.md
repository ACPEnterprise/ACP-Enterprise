# Database security transition v1

This candidate is an isolated rehearsal only.  It does not change Beta roles,
RLS, or data.

## Scope inventory

The current Beta schema inventory contains 427 public tables:

- 389 direct tenant-owned tables: 220 with `company_id`, 167 with both
  `company_id` and `branch_id`, and 2 branch-owned tables with `branch_id`.
- 21 relational tenant tables whose ownership is proven through a foreign-key
  path to a tenant-owned parent.  These are explicitly enumerated in the
  `u1v3x5z7b9d2` migration.
- 17 shared/system tables: companies, users, credentials, sessions, tokens,
  permission catalogs, migration/control sequence tables, and other global
  security or platform records.  They are not given a guessed company policy.

The read-only inventory command is `scripts/database-security-inventory.py`.
It records the table columns and foreign-key paths without reading business
rows.  The migration discovers direct tenant columns from the target schema so
new direct tenant tables fail closed into the migration review rather than
silently remaining unprotected.

## RLS contract

`u1v3x5z7b9d2_add_tenant_rls_security.py`:

- enables and forces RLS on every direct tenant table;
- adds default-deny behavior when `app.company_id` is absent or malformed;
- limits branch rows to the verified request branch set in
  `app.branch_ids`;
- adds relationship policies only for enumerated, verified parent paths;
- leaves shared/system tables unchanged.

The application projects authorization into `SET LOCAL` settings at transaction
start.  `SET LOCAL` is reset by PostgreSQL on commit or rollback, preventing a
pooled connection from carrying a previous request's tenant.  The request
header is only a pre-authentication bound; the authorization service must first
prove membership and branch access, then replaces it with the complete verified
branch set.  The database policy is defense in depth and does not replace
application authorization.

## Database roles

The live role transition must be performed by the Enterprise maintenance
authority, not by an application migration:

| Role | Login | Purpose | Prohibited capabilities |
|---|---:|---|---|
| `acp_app` | yes | API/runtime queries and business mutations | `SUPERUSER`, `CREATEROLE`, `CREATEDB`, `REPLICATION`, `BYPASSRLS` |
| `acp_migrate` | controlled | Alembic and schema maintenance | application/API use; shared with runtime |
| `acp_backup` | controlled | backup custody | `SUPERUSER`, `CREATEROLE`, `CREATEDB`, `REPLICATION`; application/API use |

The application must never own the migration or backup role.  Rotation is a
credential-provider operation with a rollback credential retained until the
transition is accepted.

The isolated rehearsal qualifies `acp_backup` as a separately controlled,
non-superuser backup principal with `pg_read_all_data` and `BYPASSRLS`.  The
RLS bypass is required only because a complete backup must capture every
tenant after `FORCE ROW LEVEL SECURITY`; it is not granted to `acp_app` or
`acp_migrate`, and `acp_backup` is never used by the API.  Restore is performed
by the controlled maintenance/database-owner procedure, not by the backup
principal.  The live backup script must be switched to this protected path as
part of the approved transition.

The Redis ACL used by the runtime must disable the default user (`user default
off`) and grant only the named runtime/health principals.  An ACL that leaves
the default user enabled can make protected-mode health checks fail or create an
unexpected unauthenticated path; the isolated rehearsal caught and corrected
that fixture defect.

## Staged Beta transition

1. Enterprise verifies a fresh backup and isolated restore.
2. Enterprise creates/rotates the three roles and records flags and grants.
3. Enterprise applies the candidate migration with `acp_migrate`.
4. Enterprise configures the API with `acp_app`, starts a fresh deployment, and
   proves tenant, worker, dispatch, timeclock, accounting-read-only, and demo
   isolation.
5. Enterprise observes health and audit telemetry, then revokes the legacy
   elevated runtime credential.
6. Rollback uses the retained application credential and database backup only
   after the failure criteria in the release runbook are met.  No downgrade is
   assumed safe without a separately qualified reverse migration.

Live approval required: Enterprise release authority must authorize role
creation/rotation, the RLS migration, and the runtime secret switch as one
reversible change set.  This rehearsal deliberately does not perform those
actions.
