# Enterprise Release Qualification

`ENTERPRISE.RELEASE` uses `scripts/enterprise-release-qualify` for every cumulative
candidate. The runner records all gates even when a gate is blocked or belongs to
a later environment. It never merges or deploys.

## Evidence profiles

Create a private evidence directory outside Git. Always pass the full candidate
SHA obtained after fetching current remote authority.

```bash
git fetch --prune origin
CANDIDATE_SHA=$(git rev-parse HEAD)
install -d -m 700 /var/tmp/enterprise-release-${CANDIDATE_SHA}

scripts/enterprise-release-qualify \
  --profile local --execute \
  --candidate-sha "$CANDIDATE_SHA" \
  --evidence-dir "/var/tmp/enterprise-release-${CANDIDATE_SHA}/local"
```

Run PostgreSQL rehearsal in the supported Docker environment:

```bash
scripts/enterprise-release-qualify \
  --profile database --execute \
  --candidate-sha "$CANDIDATE_SHA" \
  --evidence-dir "/var/tmp/enterprise-release-${CANDIDATE_SHA}/database"
```

Preview preflight requires the protected mode-0600 environment file and immutable
backup plus isolated-restore receipts. It validates configuration; it does not
start, migrate, or deploy services.

```bash
scripts/enterprise-release-qualify \
  --profile preview --execute \
  --candidate-sha "$CANDIDATE_SHA" \
  --preview-revision "$APPROVED_PREVIEW_REVISION" \
  --backup-receipt /protected/release/backup-receipt.json \
  --restore-receipt /protected/release/restore-receipt.json \
  --expected-backup-receipt-sha256 "$BACKUP_RECEIPT_SHA256" \
  --expected-restore-receipt-sha256 "$RESTORE_RECEIPT_SHA256" \
  --evidence-dir "/var/tmp/enterprise-release-${CANDIDATE_SHA}/preview"
```

After Enterprise deploys, run the post-deployment profile from the protected
execution environment. API, authentication, RBAC, PostgreSQL, Redis, workers,
revision, and routes remain `BLOCKED` until protected smoke credentials and the
sanctioned deployed environment are available. Critical CRUD uses a separate
`commissioning` profile and requires explicit authority for a disposable
non-production tenant.

## Classification

- `PASS`: command or supplied immutable evidence satisfied the expected result.
- `FAIL`: an executed check disproved release readiness.
- `BLOCKED`: required infrastructure, credentials, receipt, or supported runtime
  was unavailable.
- `NOT APPLICABLE`: the release contract explicitly excludes the capability.
- `NOT YET EXECUTED`: the gate belongs to another profile or execution was not
  requested.

Skipped tests remain visible in each command log and the packet's
`skipped_count`. Infrastructure failures are `BLOCKED`, never `PASS`.

## Expected artifacts

Each evidence directory is mode 0700 and contains:

- `qualification-packet.json` (mode 0600), binding candidate SHA, observed HEAD,
  profile, Preview revision, result classifications, rollback receipt digests,
  and packet digest;
- one `.log` per executed command, including complete test output and skips;
- externally supplied backup and restore receipts remain in their protected
  source location and are referenced by SHA-256.

Release approval requires all required profiles to have no `FAIL`, `BLOCKED`, or
`NOT YET EXECUTED` gates. The packet always records
`deployment_authorized=false`; owner-approved deployment remains a separate
Enterprise action.

## Rollback and post-deployment procedure

Before deployment, prove a fresh backup, digest, isolated restore, current schema
head, prior immutable application image/revision, and documented rollback trigger.
Rollback restores the prior application revision first; database restoration is
used only under the approved migration-specific recovery procedure. Never run
`docker compose down -v`.

After deployment, run `scripts/verify-preview.sh`, verify the deployed revision
equals the approved SHA, then execute the post-deployment profile. Confirm health,
authentication rejection/acceptance, tenant and Branch denial, critical read
routes, worker heartbeat, PostgreSQL, Redis, migration head, and SPA routes. A
CRUD commissioning pass must use an approved disposable tenant and idempotent
cleanup; it must never use All County business records.
