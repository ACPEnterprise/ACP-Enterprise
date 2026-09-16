# Controlled Production infrastructure readiness

This runbook prepares, but does not authorize or execute, ACP Production. Preview
is never renamed or reused as Production. Production business traffic remains
closed until the owner records a separate go/no-go decision.

## Immutable release candidate

The release candidate is the exact protected SHA selected after this packet is
integrated, with Alembic head `n0p8q16g3t9u`. Backend and frontend images must be
built from that SHA, scanned, and published as immutable registry references with
`@sha256:` digests. Mutable `latest` tags are not admissible Production artifacts.

## Required topology

| Component | Required Production boundary | Current gate |
| --- | --- | --- |
| Application runtime | Dedicated host/runtime; only the reverse proxy is public | Owner must provision or approve recurring cost |
| PostgreSQL 16 | Private endpoint, dedicated database/user, encryption, automated backups and PITR | Owner/provider action required |
| Redis 7 | Private endpoint, TLS/ACL credentials, Production-only namespace | Owner/provider action required |
| Evidence storage | Encrypted Production-only mount/bucket; HCP/QBO evidence read-only to the app | Owner must select storage and retention |
| Reverse proxy | Caddy or equivalent on the Production runtime, loopback proxy to frontend | Template prepared; host absent |
| DNS/TLS | One owner-approved Production FQDN and provider-issued certificate | Exact record waits for hostname and runtime address |
| Secrets | Production-only secret manager or mode-0600 protected files | Inventory prepared; values must be generated on the Production boundary |
| Backups | PITR plus encrypted off-host logical backup in a separate failure domain | Provider/storage selection required |
| Monitoring | External checks and host/database/cache/application telemetry | Rules prepared; destination and humans required |
| Release source | Protected Git SHA plus immutable backend/frontend image digests | Registry/provider required |
| Rollback source | Retained immutable application artifact and verified recovery point | First launch has no prior Production application release |

The application-only runtime is defined by `docker-compose.production.yml`.
PostgreSQL and Redis are deliberately not defined as local Compose services: the
Production runtime must not turn one host failure into simultaneous application,
database, cache, and backup loss.

## Secrets and keyrings

| Secret/configuration | State before provisioning | Requirement |
| --- | --- | --- |
| Access-token signing keyring | `MUST_GENERATE` | Independent Production keys and active key ID |
| Security-token HMAC key | `MUST_GENERATE` | Independent Production value, at least 32 characters |
| PostgreSQL credentials | `PROVIDER_REQUIRED` | Dedicated least-privilege user and private endpoint |
| Redis ACL credentials | `PROVIDER_REQUIRED` | Application and health identities; TLS/private endpoint |
| Protected-field keyring | `MUST_GENERATE` | Production-only key identity; never copied from Preview |
| Identity delivery keyring | `MUST_GENERATE` | Production-only invitation protection |
| QBO source evidence | `READY_FOR_READONLY_COPY` | Copy sealed evidence; do not copy OAuth runtime tokens into ACP Production |
| Email/invitations | `OWNER_REQUIRED` | Initial launch may remain owner-mediated with external delivery disabled |
| Evidence/object storage | `PROVIDER_REQUIRED` | Encrypted storage, access log, lifecycle/retention, separate backup |
| Monitoring/alert credentials | `PROVIDER_REQUIRED` | External destination; no secrets or customer data in alerts |
| OCR, push, payment, ACH | `NOT_REQUIRED_AT_INITIAL_LAUNCH` | Remain disabled |

The mode-0600 `.env.production` file may contain injected secret values only on
the Production host. It must never be committed, copied from Preview, included in
backups, printed, or passed in command arguments recorded by an external system.

## DNS and TLS gate

The owner must select the Production FQDN and provision a stable runtime address.
Only then may the DNS operator create the exact provider-supported `A`, `AAAA`, or
`CNAME` record. No record value is guessed by this packet. Validate resolution,
certificate chain, hostname, expiry, HSTS, CORS, and callback origins before
opening traffic. `production-caddyfile.example` is a template, not an applied
configuration.

## Backup and PITR contract

Production readiness requires both:

1. provider-managed PostgreSQL PITR with an owner-approved RPO/retention; and
2. encrypted logical backups copied to a separate account/region or equivalent
   independent failure domain.

Each logical backup receives a checksum manifest binding environment, database
identity, protected SHA, schema head, size, time, and encryption/storage object
identity. Access is restricted to the Production backup operator and restore
authority. A local dump alone never satisfies this gate. The owner must approve
RPO, RTO, retention, storage provider, geographic separation, and named operators.

## Restore and migration rehearsal

Before Production traffic:

1. restore a final-schema backup into an isolated non-Production PostgreSQL 16
   target;
2. validate the backup catalog and checksum;
3. verify `alembic current`, one head, and drift;
4. start the exact backend image against the restored target without public ports;
5. verify health, authentication fail-closed behavior, and representative
   Customer/Job/Appointment counts;
6. record duration and dispose only the rehearsal target;
7. separately create an empty Production-shaped PostgreSQL 16 target, run all
   migrations zero-to-head, verify compatibility, and record duration.

Schema downgrade is never the default rollback. After authoritative Production
writes, destructive downgrade or database replacement requires explicit restore
authority and reconciliation; otherwise recovery is a forward fix.

### 2026-09-16 isolated rehearsal evidence

The protected `a109743968fc764fc1885ecf8fbd4abeb87846d7` backend image was
qualified on the Preview host without publishing a port or touching a Preview
volume. A mode-0600, 70,162,355-byte pre-Batch-8 dump with SHA-256
`e3896a4f5033cefaf5ba247ff549409eb1ff90bfc47df9c09b14617170995035`
restored into PostgreSQL 16 on disposable tmpfs in 17 seconds. The restored
catalog contained 357 public tables at `n0p8q16g3t9u`; representative reads
returned 2,143 Customers, 342 Jobs, and 291 Appointments. The exact backend
image reached healthy Database/Schema/Redis readiness, and unauthenticated
Customer access failed closed with HTTP 401. Total rehearsal time was 34
seconds. The source dump does not have the versioned sidecar manifest required
for a Production recovery point, so it proves restore mechanics, not off-host
Production backup readiness.

An independent empty PostgreSQL 16 tmpfs target upgraded through all 174
revisions to the single `n0p8q16g3t9u` head in 17 seconds and produced 357
public tables. `alembic check` reported no new upgrade operations. Static review
found no destructive table/column operation in any upgrade body. Because no
Production database exists, the exact existing-state Production upgrade path
remains unexercisable; the initial Production database path is zero-to-head.

## Monitoring and alert routing

`production-monitoring-alert-contract.v1.json` defines launch thresholds. The
owner must name the incident authority, release operator, security contact, and
external destination. Alert delivery must be tested before traffic. Container
logs remain bounded, but local logs alone are not Production monitoring.

## Rollback authority and triggers

Before business traffic, the named Release Operator may abort deployment and
remove the Production route for any migration, release-identity, health, login,
or smoke-test failure. No database restore is permitted.

After traffic opens, either the Owner Incident Authority or Security Contact may
order mutation shutdown for:

- backend/frontend readiness failure lasting two checks;
- owner/admin login failure;
- Customer, Job, Appointment, or assignment integrity discrepancy;
- migration/schema mismatch;
- suspected data corruption;
- Company/Branch or authorization isolation defect;
- repeated ambiguous mutation outcomes; or
- a confirmed security incident.

For the first Production release there is no prior Production application
artifact. The rollback target is therefore **traffic closed**, not Preview and
not a database downgrade. Once a second compatible Production release exists,
application rollback may use its retained immutable predecessor after schema
compatibility is proven. Database restoration always requires the named Owner
Incident Authority and Production Restore Operator. Once authoritative writes
cannot be safely represented by the older schema/application, recovery becomes
forward-fix only.

## HCP final delta and coexistence

The owner authorizes the following as a separate cutover operation, not through
this packet:

1. record the exact HCP read-only acquisition window and proposed freeze time;
2. execute the sanctioned GET-only acquisition with immutable request/page
   manifests and no HCP mutation;
3. compare against the accepted SOURCE.4 authority by provider identity only;
4. classify every delta as create, reuse, update, hold, unresolved, or
   source-backed-only;
5. reconcile Customers, Locations, open Jobs, current/future Appointments,
   Estimates, Invoices, Payments, Employees, and attachment gaps;
6. run the legacy and provider completeness manifests, preserving unavailable
   counts as unavailable rather than zero;
7. obtain owner disposition for held/unresolved operational records and
   accountant disposition for financial overlap;
8. record the final cutover timestamp and immutable digests;
9. place HCP into the owner-approved coexistence policy: no new operational
   writes after cutover, retained read-only/reference access for the approved
   period, and no destructive deletion; and
10. monitor post-cutover discrepancies and preserve HCP as evidence until the
    separate retirement decision.

No fuzzy identity matching, destructive replacement, automatic attachment
assumption, HCP write, or silent HCP/QBO aggregation is permitted.

## Pre-traffic command sequence

The Release Operator uses the exact release directory and mode-0600 environment
file:

```bash
docker compose --env-file .env.production -f docker-compose.production.yml config
docker compose --env-file .env.production -f docker-compose.production.yml run --rm migrate
docker compose --env-file .env.production -f docker-compose.production.yml up -d backend frontend
```

Traffic remains closed until SHA/schema checks, health, owner login, Customer and
Job reads, Scheduling/Dispatch reads, bounded Invoice behavior, source-backed
financial reporting, monitoring, backup, and rollback evidence all pass.
