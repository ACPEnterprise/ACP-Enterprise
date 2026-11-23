# Database security transition v1 — rehearsal evidence

This evidence is for isolated development qualification only. No live Beta
database roles, RLS policies, schema, data, or application containers were
changed by this candidate.

## Release identity

- Application baseline: `14f7171da8d77f36255c0019c89bc1c65a5da5c0`
- Release-tooling baseline: `1fa6236193d8513ab8cfb16e22c279c2cabf13c9`
- Database-security migration: `u1v3x5z7b9d2`
- Prior schema: `s1a3g5k7m9q2`
- Current Beta application observed: `3d415c07f4438bbb0cdd93bbf7c6a78f3798457c`
- Current Beta schema observed: `r4s6u8w0y2a4`

## Schema inventory

The current Beta schema was inspected read-only:

- 427 public tables
- 389 direct tenant-owned tables
  - 220 direct `company_id`
  - 167 direct `company_id` plus `branch_id`
  - 2 direct `branch_id`
- 21 relational tenant tables covered by the explicit verified parent map
- 17 shared/system tables intentionally left outside guessed tenant policies

The isolated candidate schema contains 429 public tables and 390 direct
tenant-scoped tables because it includes the later agreement tables. Its
metadata inventory is preserved separately as
`isolated-schema-inventory.json` in the external evidence bundle.

## Isolated database qualification

- Full zero-to-head Alembic migration: PASS
- Candidate head: `u1v3x5z7b9d2`
- Autogenerate drift check: PASS (`No new upgrade operations detected`)
- Isolated schema object digest: `082d2d672a9c37435b32734c1e402dde86b04bf1215a5099b524f4b77cd9bea5`
- RLS-enabled tenant/relational tables: 411
- Forced RLS tenant/relational tables: 411
- `acp_tenant_isolation` policies: 411
- Isolated `acp_app` role flags: `NOSUPERUSER`, `NOCREATEROLE`, `NOCREATEDB`,
  `NOREPLICATION`, `NOBYPASSRLS`
- Isolated role qualification also passed for `acp_migrate` as a non-superuser,
  non-BYPASSRLS maintenance login, and `acp_backup` as a non-superuser backup
  login with `pg_read_all_data` plus the narrowly scoped `BYPASSRLS` capability
  required for a complete forced-RLS backup.

The reusable security probe passed:

- `RLS_DEFAULT_DENY=PASS`
- `RLS_CROSS_TENANT_READ=PASS`
- `RLS_CROSS_TENANT_WRITE=PASS`
- `RLS_TRANSACTION_RESET=PASS`

The application started with the non-superuser `acp_app` rehearsal identity
and returned healthy readiness with database, schema, and Redis healthy. The
isolated Redis ACL required `user default off`; that fixture was corrected and
retested.

Rollback rehearsal on the disposable database passed:

- Downgrade: `u1v3x5z7b9d2` -> `s1a3g5k7m9q2`, resulting state
  `s1a3g5k7m9q2|0 RLS policies`
- Re-upgrade: `s1a3g5k7m9q2` -> `u1v3x5z7b9d2`, resulting state
  `u1v3x5z7b9d2|411 RLS-enabled tables`
- Existing backup digest: `c3976d2c6c828b8c873a5cba3df579ec55f800ee7b950c67e261168cd41ad57a`
- Existing isolated-restore receipt digest:
  `765fece02a253aa18afe0c6fbe02a20d3ef95688ed89010d4cb2e06724b3d0e0`

## Automated qualification

- Backend: 3,890 passed, 7 skipped, 46 warnings
- Platform/release focused backend regression: 431 passed
- Tenant-context regression: 3 passed
- Frontend: 791 tests passed across 171 files; ESLint, TypeScript, and build passed
- Mobile: 162 tests across 20 suites; typecheck and lint passed
- Ruff: PASS
- MyPy: PASS

Warnings are existing deprecations/SQLAlchemy transaction warnings; no test
failure was observed.

## Live Beta safety finding

The protected read-only Beta check remains intentionally blocked for the
transition:

- runtime DB identity: `acp_enterprise@acp_enterprise_preview`
- superuser: `true`
- direct tenant tables without RLS: 389
- direct tenant tables with RLS but without FORCE: 0

This is not a candidate failure. It is the required live-change gate: the
application role, migration role, backup role, protected runtime secrets,
RLS migration, and rollback plan must be approved and applied by Enterprise
as one reversible change set. No live transition was attempted.

The live backup script still uses the container owner for `pg_dump`; switching
it to the qualified protected backup path remains an explicit Enterprise
approval item. The rehearsal does not claim that live roles or secrets have
been changed.
