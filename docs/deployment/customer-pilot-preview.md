# Controlled Customer Pilot in Preview

This runbook is the repository-supported administrative path for an
owner-approved Customer pilot. It does not expose an HTTP endpoint. The command
accepts only a reviewed adapter-output contract and an immutable approval
specification; it never accepts raw CSV rows or mapping overrides.

## Authoritative execution path

```text
restricted reviewed-output JSON
  + immutable owner approval JSON
  + authenticated preview owner session
  → python -m app.customer_migration.pilot_command
  → CustomerPilotExecutionService
  → customer_import_facade.import_reviewed(...)
  → CustomerAdapterImportService
  → CustomerService.stage_migrated_customer(...)
```

The retired `HousecallProCustomerMigration.run` entry point is not imported by
the command and remains fail-closed.

Both JSON inputs must be regular UTF-8 files with mode `0600` in a restricted
directory outside Git. The reviewed-output file contains migration runtime data
and must never be copied into the repository or printed to logs. The access
token is delivered through the restricted
`ACP_CUSTOMER_PILOT_ACCESS_TOKEN` environment variable, never a command-line
argument.

## Preview administration authority

The authoritative repository mechanism is:

* `docker-compose.preview.yml`;
* `scripts/verify-preview.sh`;
* the manual deployment process in `preview-deployment.md`;
* host Caddy for reverse proxy and automatic TLS;
* the Compose `postgres`, `redis`, `backend`, and `frontend` services.

Preview topology was reconciled during PHONE.2F: Caddy is the active host
reverse proxy and Nginx is inactive. Caddy forwards the public HTTPS hostname
to the frontend loopback listener on port 8080. Caddy is host-managed rather
than a Compose service and must be validated separately.

Run these checks on the preview host from the clean, approved release checkout:

```bash
test -z "$(git status --short)"
git rev-parse HEAD
docker compose --env-file .env.preview -f docker-compose.preview.yml ps
docker compose --env-file .env.preview -f docker-compose.preview.yml exec -T \
  backend alembic current
systemctl is-active caddy
caddy validate --config /etc/caddy/Caddyfile
PREVIEW_URL=https://preview.allcountyhomeservices.com \
  sh scripts/verify-preview.sh .env.preview
```

Record the exact Git SHA and the single Alembic head in the approval
specification. The command independently compares both values. Provide the
deployed SHA to the backend command as `ACP_DEPLOYED_GIT_SHA`.

## Required backup

Before validation or import mode, create a restricted PostgreSQL custom-format backup:

```bash
install -d -m 0700 /opt/acp-enterprise/backups
backup=/opt/acp-enterprise/backups/customer-pilot-$(date -u +%Y%m%dT%H%M%SZ).dump
docker compose --env-file .env.preview -f docker-compose.preview.yml exec -T \
  postgres sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' > "$backup"
chmod 0600 "$backup"
sha256sum "$backup"
docker run --rm -v /opt/acp-enterprise/backups:/backups:ro postgres:16-alpine \
  pg_restore --list "/backups/$(basename "$backup")" >/dev/null
```

Record the path, byte size, SHA-256, and successful `pg_restore --list`
verification in the restricted execution log. Import mode also recomputes the
digest and verifies the `PGDMP` custom-format signature before invoking the
facade.

## Validate without writes

Validation mode reads operational counts and verifies every digest, ordered
identity, expected count, release, schema, tenant permission, and Alembic
boundary. It does not invoke the import facade.

```bash
docker compose --env-file .env.preview -f docker-compose.preview.yml run --rm -T \
  --no-deps \
  -v /opt/acp-enterprise/migration-runtime:/run/acp-migration:ro \
  -v /opt/acp-enterprise/backups:/run/acp-backups:ro \
  -e ACP_DEPLOYED_GIT_SHA=APPROVED_FULL_GIT_SHA \
  -e ACP_CUSTOMER_PILOT_ACCESS_TOKEN \
  backend python -m app.customer_migration.pilot_command \
  --target preview \
  --mode validate \
  --approval /run/acp-migration/customer-pilot-approval.json \
  --reviewed-output /run/acp-migration/customer-reviewed-output.json \
  --company-id APPROVED_COMPANY_UUID \
  --branch-id APPROVED_BRANCH_UUID \
  --backup /run/acp-backups/APPROVED_BACKUP.dump \
  --backup-sha256 APPROVED_BACKUP_SHA256
```

The approval and reviewed-output files must be mounted read-only into the
backend container at execution time. Do not bake them into an image.

## Import after separate owner authorization

Use the identical approval and reviewed-output files:

```bash
docker compose --env-file .env.preview -f docker-compose.preview.yml run --rm -T \
  --no-deps \
  -v /opt/acp-enterprise/migration-runtime:/run/acp-migration:ro \
  -v /opt/acp-enterprise/backups:/run/acp-backups:ro \
  -e ACP_DEPLOYED_GIT_SHA=APPROVED_FULL_GIT_SHA \
  -e ACP_CUSTOMER_PILOT_ACCESS_TOKEN \
  backend python -m app.customer_migration.pilot_command \
  --target preview \
  --mode import \
  --approval /run/acp-migration/customer-pilot-approval.json \
  --reviewed-output /run/acp-migration/customer-reviewed-output.json \
  --company-id APPROVED_COMPANY_UUID \
  --branch-id APPROVED_BRANCH_UUID \
  --backup /run/acp-backups/APPROVED_BACKUP.dump \
  --backup-sha256 APPROVED_BACKUP_SHA256
```

The command emits one compact JSON report containing only digests, run ID, and
aggregate counts. It does not emit Customer names, contacts, addresses, source
identities, or source rows.

## Post-import validation

Record post-import counts from the command, rerun `scripts/verify-preview.sh`,
confirm that Compose reports no unexpected restarts, and use an authenticated
preview account to validate:

* Customer list API and workspace;
* every imported Customer detail API;
* exact migration history, audit, and business-event totals;
* idempotent replay with no additional operational aggregates.

Never place authenticated API output in Git or unrestricted logs.

## Exact rollback

If pilot integrity cannot be established, stop application writes and preserve
migration evidence. Owner and database-administrator approval are required
before restoration.

```bash
docker compose --env-file .env.preview -f docker-compose.preview.yml stop \
  backend frontend
docker compose --env-file .env.preview -f docker-compose.preview.yml exec -T \
  postgres sh -c \
  'dropdb -U "$POSTGRES_USER" "$POSTGRES_DB" &&
   createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
docker compose --env-file .env.preview -f docker-compose.preview.yml exec -T \
  postgres sh -c \
  'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' \
  < /opt/acp-enterprise/backups/APPROVED_BACKUP.dump
docker compose --env-file .env.preview -f docker-compose.preview.yml up -d
PREVIEW_URL=https://preview.allcountyhomeservices.com \
  sh scripts/verify-preview.sh .env.preview
```

Before using this procedure, verify the backup SHA-256 again and test
`pg_restore --list`. Never run it against production, and never use
`docker compose down -v`.
