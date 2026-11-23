# Enterprise Release Qualification

`ENTERPRISE.RELEASE` uses `scripts/enterprise-release-qualify` as its canonical
runner for every cumulative candidate. The runner records all gates even when a
gate is blocked or belongs to a later environment. It never merges or deploys.

Qualification packet v3 keeps application provenance separate from release
tooling provenance. `--candidate-sha` identifies the application candidate;
`--tooling-sha` must equal the executing worktree HEAD; and
`--protected-baseline-sha` identifies the protected release baseline. An
application candidate may therefore be qualified from a later tooling
successor without falsely comparing the two SHAs.

Run it from the repository root with the repository's Python 3.12 environment.
`pytest.ini` supplies the `backend` import root, and the runner resolves paths
from its repository location, so neither repository-root nor outside-`backend`
invocations require a caller-managed `PYTHONPATH`.

The local profile's backend test gate uses `scripts/qualify-backend-tests`. The
wrapper starts the digest-pinned PostgreSQL 16 image with uniquely labeled,
disposable Docker resources, selects an unused loopback port and publishes it
on `127.0.0.1` only, verifies a pristine UTF-8
database, migrates it to the current single head, and supplies that internally
constructed URL to pytest. A caller-supplied `DATABASE_URL` is never used by
this gate. Test failure, interruption, invalid port binding, unsupported
PostgreSQL, migration failure, and cleanup failure all fail closed. The
container, database volume, dedicated network, and disposable credentials are
removed on exit. The wrapper never connects to Preview, Production, or a shared
developer database.

Signal exits remain nonzero after cleanup: HUP returns `129`, INT returns `130`,
and TERM returns `143`. If cleanup itself fails, the wrapper returns `70`
instead of concealing the cleanup failure or the interruption.

## Evidence profiles

Create a private evidence directory outside Git. Always pass the full candidate
SHA obtained after fetching current remote authority.

```bash
git fetch --prune origin
CANDIDATE_SHA=... # exact application candidate SHA
TOOLING_SHA=$(git rev-parse HEAD)
PROTECTED_BASELINE_SHA=... # exact protected baseline SHA
install -d -m 700 /var/tmp/enterprise-release-${CANDIDATE_SHA}

scripts/enterprise-release-qualify \
  --profile local --execute \
  --candidate-sha "$CANDIDATE_SHA" \
  --tooling-sha "$TOOLING_SHA" \
  --protected-baseline-sha "$PROTECTED_BASELINE_SHA" \
  --evidence-dir "/var/tmp/enterprise-release-${CANDIDATE_SHA}/local"
```

Run PostgreSQL rehearsal in the supported Docker environment:

```bash
scripts/enterprise-release-qualify \
  --profile database --execute \
  --candidate-sha "$CANDIDATE_SHA" \
  --evidence-dir "/var/tmp/enterprise-release-${CANDIDATE_SHA}/database"
```

The database profile uses only `docker-compose.release-qualification.yml`. Its
PostgreSQL 16 source and restore containers use distinct single-run volumes and
are reachable only over an internal Compose network. Passwords are generated in
a mode-0700 temporary directory and mounted as Compose secrets; Redis uses the
production ACL shape and file-backed credentials. Both PostgreSQL clusters are
explicitly initialized as UTF-8. Before Alembic runs, qualification fails if any
application table, sequence, view, or prior `alembic_version` exists. It then
requires one head, performs zero-to-head, proves current=head, checks drift,
creates and verifies a custom-format backup, proves the restore target is empty,
restores it, and requires application readiness against restored PostgreSQL and
authenticated Redis. Cleanup removes containers, networks, volumes, secrets,
and temporary evidence; a cleanup failure changes an otherwise successful run
into a failure.

The Compose file contains no PostgreSQL or Redis password and no credentialed
database URL. Disposable test-only signing constants remain confined to
`ENVIRONMENT=test`. `scripts/release-qualification-config-check.py` proves the
committed configuration remains single, isolated, secret-indirected, UTF-8, and
split across distinct source and restore volumes.

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

Skipped and failed test counts remain visible in each result. Runtime warnings
are recorded, and supported test-suite warning patterns fail closed. Output is
redacted before persistence; command, exit code, duration, status, and redacted
artifact digest remain in the packet. Infrastructure failures are `BLOCKED`,
never `PASS`.

## Expected artifacts

Each evidence directory is mode 0700 and contains:

- `qualification-packet.json` (mode 0600), validated against
  `docs/release/enterprise-release-qualification.schema.json` and binding the
  candidate SHA, observed HEAD, profile, schema digest, commands, outcomes,
  Preview revision, rollback receipt digests, and canonical packet digest;
- `evidence-seal.json` (mode 0600), binding the packet digest and the SHA-256 and
  byte length of every evidence artifact;
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

The mutation registry is qualified directly against live OpenAPI. Every `POST`,
`PUT`, `PATCH`, and `DELETE` operation must have exactly one matching current
operation ID, explicit mechanism, tenant scope, and closed classification.
Missing and stale entries fail the local profile.
