# Database-security release package v1

This package is qualified in disposable PostgreSQL/Redis environments only.
It does not authorize or perform a Beta change.

## Bound release identities

- Unified application candidate: `14f7171da8d77f36255c0019c89bc1c65a5da5c0`
- Database-security successor: `92e3c9d55de9664d26f121bfd60cfd54cece3dc9`
- Release-tooling candidate: `1fa6236193d8513ab8cfb16e22c279c2cabf13c9`
- Current deployed Beta application: `3d415c07f4438bbb0cdd93bbf7c6a78f3798457c`
- Current deployed Beta schema: `r4s6u8w0y2a4`
- Target migration head: `u1v3x5z7b9d2`

## Backup and restore qualification

A dedicated `acp_backup` login was qualified in isolation with:

- `NOSUPERUSER`
- `NOCREATEDB`
- `NOCREATEROLE`
- `NOREPLICATION`
- `BYPASSRLS` only for complete tenant-inclusive backup capture
- `pg_read_all_data`
- no application membership or runtime use

The source database contained 430 public tables, two forced-RLS probe rows,
and head `u1v3x5z7b9d2`. A custom-format dump produced by `acp_backup` had:

- 2,596,632 bytes
- 4,580 TOC entries
- the forced-RLS probe represented in the dump

Restore to a fresh isolated database produced:

- 430 public tables restored
- 2/2 probe rows restored
- head `u1v3x5z7b9d2`
- 412 RLS-enabled tables restored, including the probe

Source and restored counts matched. Restore was performed by the controlled
maintenance/database-owner identity, not by `acp_backup`.

The guarded `scripts/backup-preview-postgres.sh` procedure was also executed
against the disposable PostgreSQL container using the protected backup
password-file path. Its resulting dump SHA-256 was
`5508fc8dbc04a161aec9876c0976d5fe2c1e593a6601d3eec24569df72e02789`.

## Migration-role qualification

`acp_migrate` was tested as a non-superuser login with no `CREATEROLE`,
`CREATEDB`, `REPLICATION`, or `BYPASSRLS`. It entered a non-login
`acp_schema_owner` role by default. Public schema and application objects were
owned by that role, and the migration role executed both:

- `u1v3x5z7b9d2` -> `s1a3g5k7m9q2`
- `s1a3g5k7m9q2` -> `u1v3x5z7b9d2`

No application runtime superuser privilege was used for either operation.

## Application-role qualification

`acp_app` was tested with:

- no superuser, createdb, createrole, replication, or bypass-RLS flags
- schema usage and application DML grants only
- no schema-owner membership
- no DDL privilege
- no role-escalation privilege

With no tenant context, tenant queries returned zero rows. The application
started with this identity and reached healthy readiness with database,
schema, and Redis healthy.

## Rotation and failure injection

- New database credential accepted by a fresh network client: PASS
- Old credential rejected after rotation: PASS
- Fresh app container with rotated secret: HEALTHY
- Invalid credential container: blocked before healthy readiness
- Existing pool remained healthy until controlled restart
- Rollback to prior credential and fresh app container: HEALTHY
- Connection-limit exhaustion: detected and denied
- Invalid tenant context: denied/cleared
- RLS cross-tenant read/write: denied
- Migration downgrade/re-upgrade: PASS

## Application regression

The full backend suite covers customer/HCP, QuickBooks read-only, workforce,
dispatch, timeclock, Mission Control, and Sales Demo contracts:

- Backend: 3,890 passed, 7 skipped
- Frontend: 791 passed
- Mobile: 162 passed
- Ruff, MyPy, TypeScript, frontend build: PASS

These are isolated qualification results, not live Beta owner acceptance.

## Enterprise authorization request

Enterprise must approve one reversible Beta change set that:

1. creates the schema-owner, migration, and backup identities;
2. switches the backup procedure to the protected `acp_backup` path;
3. creates a fresh backup and isolated restore receipt;
4. applies `u1v3x5z7b9d2` using `acp_migrate`;
5. switches runtime credentials to `acp_app`;
6. restarts the application pool and verifies all health, authorization, and
   tenant-isolation gates;
7. retains the prior application credential and backup for rollback; and
8. performs no production, HCP, QuickBooks-write, payroll, banking, or money
   movement action.

No live change has been performed.
