# ACP Platform resilience and recovery runbook

This runbook separates safe diagnosis and isolated rehearsal from destructive
authoritative recovery. It does not authorize a Preview or Production restore.

## Owner outage guide

| What staff observe | Business continuity | Owner action |
| --- | --- | --- |
| Information is marked stale | `STALE_READ_ONLY`; do not rely on it for a new mutation | Pause the affected mutation and contact the administrator. |
| Employees cannot sign in | `MUTATION_BLOCKED` for employee workflows | Do not weaken authentication. Ask the administrator to inspect backend, database, Redis, and authorization-version readiness. |
| Jobs are visible but updates fail | `READ_ONLY_SAFE` only when the UI explicitly says so | Stop Job, Dispatch, and Timekeeping mutations; retain temporary operational notes outside ACP until recovery. |
| Office reads work but creation fails | `READ_ONLY_SAFE` for explicitly successful reads | Stop Customer, Job, Estimate, Invoice, and Payment mutations. Do not repeatedly submit an ambiguous mutation. |
| Messages are not sending | Core operations may remain `AVAILABLE`; Communications is `MUTATION_BLOCKED` | Do not claim delivery. Review outbox and provider readiness after recovery. |
| ACP is unavailable | `UNAVAILABLE` | Stop ACP mutations, contact the administrator, and invoke the incident procedure. |
| Deployment failed or is incomplete | `UNAVAILABLE` or `READ_ONLY_SAFE` only if readiness explicitly permits | Do not continue deployment. Preserve both release SHAs and schema head; select retry or rollback using the gate below. |
| Backup is stale or unverified | Runtime may be `AVAILABLE`, recovery assurance is `ACTION_REQUIRED` | Block schema-changing deployment until a fresh backup and isolated restore proof exist. |

After a client loses a response, staff must search for the committed result or
retry only with the same idempotency key. A different key can create a second
business request.

## Technical incident sequence

1. Record environment, time, intended release SHA, observed backend/frontend
   SHA, schema head, and correlation identity. Never copy secret values.
2. Inspect `/health/live` and `/health/ready`. A running process is not proof of
   readiness.
3. Classify affected operations as `AVAILABLE`, `READ_ONLY_SAFE`,
   `STALE_READ_ONLY`, `MUTATION_BLOCKED`, `UNAVAILABLE`, or
   `MANUAL_RECOVERY_REQUIRED`.
4. Isolate failing mutation paths. Never bypass authentication, tenant scope,
   immutable history, or database constraints.
5. Recover the least authoritative component first. Redis and application
   processes may restart; the database must not be replaced without explicit
   restore authorization.
6. Verify SHA, single schema head, PostgreSQL, Redis, frontend, workers, outbox,
   authentication, Company/Branch isolation, and a synthetic smoke mutation.
7. Reopen mutations only after readiness is healthy and ambiguous operations
   have been reconciled.

## Rollback decision contract

- `RETRY`: artifact and schema identities agree; failure is transient and no
  migration partially committed.
- `ROLLBACK_APPLICATION`: previous SHA is known-good and explicitly compatible
  with the current schema. Preserve rollback evidence.
- `RESTORE_DATABASE`: only when durable authority is lost or corrupt, with
  explicit owner/operator authorization and a verified backup identity.
- `OPERATOR_INTERVENTION`: schema compatibility is unknown, migration heads are
  multiple, protected configuration is missing, or a mutation result is
  ambiguous.

Never silently downgrade a schema. Migrations that drop/rename columns, narrow
types, or irreversibly transform evidence require a declared rollback boundary.

## Safe Preview restore procedure

This procedure restores into a disposable target, never over Preview:

1. Record source environment identity, authority SHA, schema head, database
   identity, timestamp, and expected checksum.
2. Create a restricted temporary directory outside the repository.
3. Run `scripts/platform-resilience backup` with environment `preview-isolated`
   against an explicitly approved non-Production source.
4. Run `scripts/platform-resilience verify`; reject checksum, format, or
   permission failures.
5. Provision a new empty database with an `isolated-` target identity.
6. Run `scripts/platform-resilience restore`, supplying the exact approved
   source identity. The target URL must identify only the disposable database.
7. Run Alembic current/head/drift checks and application-level invariant tests.
8. Destroy the disposable target only after safe evidence is recorded. Keep or
   remove backup material according to the approved retention policy.

## Production restore procedure (not authorized by this runbook)

Production recovery additionally requires explicit owner authorization, an
approved incident identity, verified target/environment identity, service
isolation, a qualified backup, schema compatibility review, controlled restore,
security and data-integrity validation, controlled reopen, and immutable audit
evidence. The repository tool intentionally refuses `production`.

## Component recovery

- **PostgreSQL unavailable:** all authoritative mutations stop. Restore service
  first; restore data only after loss is established and authorized.
- **Redis unavailable:** durable truth remains in PostgreSQL. Authentication,
  rate limiting, coordination, and any security-sensitive cached authority fail
  closed. Rebuild cache from durable authority; do not restore stale sessions.
- **Worker stopped:** restart it, release expired leases using existing
  authority, and reconcile uncertain work before retry. Outbox idempotency must
  prevent duplicate logical delivery.
- **Frontend unavailable:** backend readiness may remain healthy, but the web
  product is unavailable. Restore the exact frontend artifact matching the
  backend release contract.
- **TLS/proxy failure:** validate Caddy configuration and certificate status;
  do not bypass TLS or alter DNS as an incident shortcut.
- **Disk nearly full:** stop growth-heavy operations and create capacity. Never
  delete database, audit, sealed evidence, or the only rollback/backup copy.
- **Host loss:** provision a new isolated host, restore runtime configuration
  references, recover persistent volumes from approved backups, validate
  DNS/TLS without mutating them from this lane, and run the complete post-deploy
  gate.

## Secret-loss recovery

Secret values must come from the authorized secret store, not backup manifests,
Git, logs, or audit rows. A lost/revoked QBO credential, Communications
credential, invitation key, signing key, or application secret requires its
own owner/provider rotation procedure. Rotation is not authorized here. After
reprovisioning, invalidate affected sessions/tokens where required and verify
only presence, permissions, key identity, and readiness—not secret content.

## Monitoring and alert contract

Monitor public availability, backend readiness, schema head, PostgreSQL, Redis,
disk, TLS expiry, worker heartbeat, outbox age/backlog, backup age, last checksum
verification, and last isolated restore proof. Safe evidence contains state,
time, release/schema identity, and correlation identity only.

- `INFO`: healthy observation or planned recovery rehearsal.
- `WARNING`: degradable dependency or capacity/freshness trend; no correctness
  failure yet.
- `ACTION_REQUIRED`: backup stale/unverified, worker/outbox delay, certificate
  approaching expiry, or incomplete deployment evidence.
- `CRITICAL`: authoritative DB unavailable/corrupt, required schema mismatch,
  authentication safety failure, disk exhaustion, or public outage.

Business thresholds for backup age, disk reserve, certificate warning window,
RPO, and RTO remain configurable owner decisions.

## Launch-day non-Production checklist

- Current backup checksum is valid and backup permissions are restrictive.
- A representative isolated restore proof is current.
- Previous known-good application SHA and schema compatibility are recorded.
- Alembic has exactly one head and database current equals head.
- Backend, frontend, PostgreSQL, Redis, required workers, and HTTPS are ready.
- Disk headroom, log rotation, release retention, and backup retention are known.
- QBO/Migration protected state is present with expected permissions; contents
  are not printed.
- Communications provider readiness and Mobile/backend compatibility are known.
- Rollback operator and destructive-restore owner are identified.

## Owner decisions still required

Choose RPO/RTO and retention per system class. Recommended options to decide
among, rather than defaults implemented here:

| Class | RPO choices | RTO choices | Consequence |
| --- | --- | --- | --- |
| PostgreSQL authority | 5 min / 1 hr / 24 hr | 1 hr / 4 hr / next business day | Lower targets require WAL/PITR automation, off-host copies, monitoring, and rehearsals. |
| Protected evidence/documents | 1 hr / 24 hr | 4 hr / next business day | Must preserve encryption, ACLs, immutable digests, and environment separation. |
| Redis/cache | Reconstructible / snapshot | 15 min / 1 hr | Snapshotting stale authorization state can be less safe than rebuilding it. |
| Application releases/config references | Every release | 30 min / 2 hr | Requires retained immutable artifacts and separately recoverable secret references. |

Also decide backup retention generations, off-host/storage provider, geographic
separation, restore-proof cadence, log retention, release count, and who may
authorize Production restore.
