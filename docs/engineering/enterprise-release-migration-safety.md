# ENTERPRISE.RELEASE migration safety

This runbook is for non-Production qualification. It never authorizes a domain
migration, a protected merge, or a Production deployment.

## Mandatory preflight

From repository root:

```bash
scripts/migration-lineage --require-single-head --output migration-lineage.json
cd backend
alembic heads
alembic branches
alembic history --verbose
```

Any duplicate revision, missing `down_revision`, cycle, unexpected root, or
head count other than one stops integration. A release engineer must not choose
between domain heads. The owning lanes must provide a reviewed successor or an
explicit Alembic merge revision.

## Backup before migration

Use the existing fail-closed utility against the approved non-Production target:

```bash
scripts/platform-resilience backup \
  --environment preview-isolated \
  --database-url "$QUALIFICATION_DATABASE_URL" \
  --database-identity "$APPROVED_DATABASE_IDENTITY" \
  --authority-sha "$RELEASE_SHA" \
  --schema-head "$EXPECTED_HEAD" \
  --output "$RESTRICTED_BACKUP_PATH"
scripts/platform-resilience verify --backup "$RESTRICTED_BACKUP_PATH"
```

Retain the generated checksum manifest with release evidence. Never print the
database URL or copy a backup into the repository.

## Disposable PostgreSQL rehearsal

Only after preflight reports one head:

1. Start `docker-compose.migration-rehearsal.yml` with a dedicated secret.
2. Point `DATABASE_URL` at the isolated database on `127.0.0.1:55432`.
3. Capture `alembic current` before changes.
4. Run `alembic upgrade head` from an empty database.
5. Capture `alembic current`, `alembic heads`, and a schema-only `pg_dump`.
6. Run `alembic upgrade head` again; it must perform no revision transition.
7. Restore the pre-migration backup into a second isolated database.
8. Run `alembic upgrade head` against that existing-state restore.
9. Run `alembic check`; any model/schema drift stops release.
10. Exercise downgrade only for the reviewed candidate revisions whose
   downgrade functions are explicitly supported, then upgrade to head again.

## Failed migration recovery

Stop application writers. Record the database identity, current Alembic
revision, backend SHA, failing command, and database logs. Do not stamp past a
failed migration. If the migration transaction rolled back, correct the
candidate and rehearse again. If non-transactional DDL escaped rollback, restore
the verified backup into a new isolated database, verify its manifest and
revision, and repeat the upgrade. Escalate ambiguous state to the migration
owner and ENTERPRISE.RELEASE.

## Restore rehearsal

The restore target must be isolated and follow the naming guard enforced by
`scripts/platform-resilience`:

```bash
scripts/platform-resilience restore \
  --environment test \
  --database-url "$ISOLATED_RESTORE_DATABASE_URL" \
  --target-identity "isolated-release-rehearsal" \
  --expected-source-identity "$APPROVED_DATABASE_IDENTITY" \
  --backup "$RESTRICTED_BACKUP_PATH"
```

## Post-deployment verification

Capture backend SHA, `alembic current`, expected head, actual head, schema-only
digest, application health, and migration logs. Run `platform-resilience
release-check` with exact backend/frontend/Mission Control SHAs and one expected
schema head. A mismatch is `NOT_READY`; never repair it by stamping blindly.
