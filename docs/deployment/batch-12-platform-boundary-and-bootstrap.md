# Batch 12: platform boundary and closed-traffic bootstrap

Evidence date: 2026-09-16. Frozen candidate:
`d5148f60ba842f9b4e7c9e83f16d1d3301372491`. This is a preparation packet,
not deployment authority. All County is the beta tenant and owns its business
data. Twelve Hats / The 10:31 Project controls the permanent platform.

## Ownership and control matrix

Repository or account names are not evidence of legal ownership. `UNKNOWN`
therefore remains a release blocker until documentary or provider-console
evidence is attached to the release record.

| Asset / authority | Current classification | Required launch disposition |
| --- | --- | --- |
| Legal entity | UNKNOWN | Identify the contracting/platform entity; MUST MOVE BEFORE PRODUCTION if currently personal or All County controlled. |
| Software and product IP | PLATFORM CONTROLLED (owner direction) | Record assignment/custody evidence in the release record. |
| GitHub organization/repository | UNKNOWN | Platform-controlled organization, administrators, recovery and protected-branch evidence required before Production. |
| Cloud provider and billing | UNKNOWN | PLATFORM CONTROLLED; owner approves provider/spend. MUST MOVE BEFORE PRODUCTION. |
| Registrar | UNKNOWN | Platform-controlled permanent domain custody required; current DNS delegation alone proves no ownership. |
| DNS | TEMPORARY DEVELOPMENT CONTROL | Current GoDaddy delegation may remain; platform-authorized DNS operator required before record change. |
| Container registry | UNKNOWN / not provisioned | PLATFORM CONTROLLED and required before closed traffic. |
| PostgreSQL, Redis, object/evidence storage | UNKNOWN / not provisioned | PLATFORM CONTROLLED, tenant-isolated, private, encrypted; required before closed traffic. |
| Backup destination | UNKNOWN / not provisioned | PLATFORM CONTROLLED and separated from primary failure domain. |
| Monitoring and alert delivery | UNKNOWN / not provisioned | PLATFORM CONTROLLED; named human destination required before closed traffic. |
| Apple Developer distribution | UNKNOWN | MAY MOVE AFTER LAUNCH; not used by this web Production release. |
| Production secrets and encryption/master keys | UNKNOWN / not generated | PLATFORM CONTROLLED; generate only inside approved Production boundary. |
| TLS certificates | UNKNOWN / not issued | PLATFORM CONTROLLED lifecycle at Production edge. |
| Incident, security, release, backup, restore, secret-recovery authorities | UNKNOWN | Name individual principals and alternates before closed traffic. |

All existing Preview/development controls are `TEMPORARY DEVELOPMENT CONTROL`.
They are not evidence that the corresponding Production control is ready.

## Minimum topology

Use one modest, hardened application runtime rather than Kubernetes. The public
edge terminates TLS and proxies the frontend; `/api` reaches the backend only
through the internal application network. The backend alone reaches private
PostgreSQL 16, private TLS/ACL Redis 7, and encrypted evidence storage. Managed
state services survive runtime replacement. Backend and frontend images are
pulled from a platform-controlled registry by immutable digest. Logs, metrics,
uptime probes, backup/PITR, and alerts are external to the runtime failure
domain.

## Minimum provider bill of materials

| Resource | Purpose / exposure | Durability, encryption and backup | Initial sizing basis / scale trigger | Timing / ownership |
| --- | --- | --- | --- | --- |
| Application runtime | Reverse proxy, frontend, backend and one-shot migration; only 443 public | Replaceable; encrypted boot volume; no authoritative state | 2 backend workers, 2 vCPU/2 GiB backend envelope; scale on sustained CPU, latency, memory or queue pressure | Closed traffic; platform-controlled |
| Private PostgreSQL 16 | Authoritative relational state; never public | Encrypted in transit/at rest, automated backups and PITR | Provider minimum HA-capable tier; scale on storage, connections, IOPS and latency | Closed traffic; platform-controlled |
| Private Redis 7 | Sessions/rate limiting/coordination; never public | TLS/ACL; persistence/recovery selected according to admitted usage | Small managed tier; scale on memory, eviction, connections and latency | Closed traffic; platform-controlled |
| Object/evidence storage | Durable source/evidence objects; private | Versioning, encryption, access logs, lifecycle and independent recovery | Usage based; scale on bytes/request rate | Closed traffic; platform-controlled |
| Container registry | Immutable backend/frontend artifacts | Retention, scan metadata and digest immutability | Two images plus retained rollback generations | Closed traffic; platform-controlled |
| Backup/PITR system | Database recovery points and off-host logical copies | Encrypted; separate account/region as approved; monitored | Driven by owner-approved RPO/retention | Closed traffic; platform-controlled |
| Monitoring/logging | Health, errors, DB/cache/capacity, certificate, deploy and backup signals | Restrict business/secret data; retention selected | Scale on ingestion and retention | Closed traffic; platform-controlled |
| Alert delivery | Deliver actionable incidents | At least primary and alternate humans; tested receipt | Scale by on-call model | Closed traffic; platform-controlled |
| DNS/TLS | `app.twelve-hats.com` and HTTPS | Automated renewal; expiry monitoring | One hostname initially | Public cutover; platform-controlled |

Required spend/credentials: cloud account and billing; runtime; PostgreSQL;
Redis; object storage; registry; backup/PITR; monitoring/alert provider; and DNS
operator access. Nothing in this candidate purchases or provisions them.

## Production secret model

Generate inside the approved boundary: database migration/runtime credentials,
Redis ACL/password, access-token keyring, security-token HMAC key, identity
delivery keyring, protected payroll-input keyring, object-storage credentials,
registry pull credential, monitoring ingestion credential, backup credential,
and any later admitted provider credentials. Production values must be distinct
from Preview.

Use versioned names (`service/purpose/version`), least-privilege service
consumers, audit-logged custody and two-authority recovery for master/keyring
material. Rotate service credentials and signing keys on schedule and incident;
retain only the overlap needed to validate unexpired tokens. Emergency
revocation disables the affected integration first, records an incident, rotates
the credential, verifies consumers, and never prints secret material. Recovery
authority and escrow location must be named before bootstrap.

## Backup and PITR model

Enable provider PostgreSQL PITR plus encrypted, manifest-bearing logical backups
to an off-host failure domain. Record candidate SHA, schema head, timestamp,
checksums, source instance and encryption-key reference. Monitor every job and
freshness against the approved RPO. Restore into a clean isolated target and run
schema, row-count/checksum and application-start verification periodically.
Owner approval remains required for RPO, RTO, retention, region and geographic
separation; proposed values are planning inputs only and are not defaults.

## Monitoring model

Implement the existing
`production-monitoring-alert-contract.v1.json`, adding provider telemetry for
frontend HTTPS, backend health/error rate, PostgreSQL availability/storage/
connections, Redis availability/memory/eviction, runtime disk/capacity,
certificate expiry, migration/deploy failure, backup success/freshness and
restore rehearsal. Alert routing is blocked until the owner names destinations
and escalation principals. Alerts must contain neither secrets nor customer
data.

## DNS and TLS runbook

1. Provision and verify the stable edge target first.
2. Because `twelve-hats.com` is delegated to GoDaddy (`ns67` and `ns68`), create
   the record in the authoritative GoDaddy zone: `CNAME app -> provider name`
   when the provider supplies a hostname, otherwise `A/AAAA app -> stable IP`.
3. Lower only the `app` record TTL to 300 seconds at least one prior TTL before
   cutover; do not alter apex or nameservers.
4. Prove the target while traffic is restricted, then authorize ACME/certificate
   issuance. Validate chain, hostname, renewal and expiry alert before use.
5. Enforce HTTPS and HSTS only after HTTPS works; keep preload disabled.
6. Validate authoritative DNS, multiple recursive resolvers, external HTTPS,
   CORS/trusted-host behavior and health.
7. Roll back by closing application access and restoring the previous `app`
   record if one exists; a first launch has no safe previous Production target.
   Retain the failed environment and evidence for diagnosis.

DNS mutation requires explicit owner authorization and is not performed here.

## Closed-traffic bootstrap

1. Attach ownership evidence and name release/security/incident/backup/restore/
   secret-recovery authorities.
2. Verify protected candidate SHA and release manifest.
3. Build, scan and publish immutable images; record digests.
4. Verify private network, runtime and managed-service health.
5. Generate Production-only secrets inside the boundary.
6. Capture and verify an encrypted baseline database recovery point.
7. Run the database release preflight and migrate to the manifest head.
8. Start backend; require readiness.
9. Start frontend behind the restricted edge.
10. Verify internal and edge health.
11. Verify Production authentication without Preview credentials.
12. Verify Company/Branch RBAC and denial paths.
13. Perform bounded representative transaction smoke using dedicated acceptance
    records; remove/retain them according to the approved evidence procedure.
14. Verify all monitoring signals.
15. Trigger a safe synthetic alert and prove human receipt.
16. Trigger/verify backup and checksum evidence.
17. Require a successful clean-target restore artifact before go-live.
18. Capture SHA, image digests, schema head, configuration fingerprint, checks,
    actors and timestamps in the release record.
19. Hold a separate owner/Release go/no-go; keep normal traffic closed.
20. On failure close traffic, stop mutations, preserve evidence, restore the
    previous application artifact where schema-compatible, and use PITR/restore
    only under restore authority. Never assume automatic schema downgrade.

Run the repository preflight with both the mode-0600 environment file and a
completed copy of `production-platform-manifest.example.json`. The example is
intentionally blocked until resources, authorities and decisions are real.

## Minimum disaster recovery

| Event | First safe response | Recovery authority/path |
| --- | --- | --- |
| Runtime loss | Keep edge closed; replace runtime from recorded digests | Release authority; reconnect private services and re-run health/smoke |
| Database loss | Stop writes; preserve incident evidence | Restore authority selects PITR point, restores clean target, verifies manifest/schema/data/application before endpoint switch |
| Redis loss | Block auth/rate-limit/coordination-sensitive mutations | Recreate managed service, rotate credential if needed, verify session behavior |
| Object/evidence issue | Freeze acquisition/processing that would overwrite truth | Recover versioned objects from independent copy; reconcile checksums |
| Credential compromise | Disable affected integration and close affected traffic | Security authority revokes/rotates, verifies consumers and records incident |
| Bad deploy | Close traffic; retain failing artifact/logs | Release authority returns to prior digest only when schema compatible |
| Bad migration | Stop application writes; do not improvise downgrade | Database release/restore authority uses documented forward fix or verified recovery point |
| DNS failure | Validate authoritative zone; close traffic | Authorized DNS operator restores prior record/TTL and revalidates TLS |

The residual backend CVE runtime prototype is not started in this batch: no
OM1-A admitted replacement exists, and changing the frozen runtime would require
separate Enterprise admission.

## Current classification

- Platform engineering: **READY BUT UNPROVEN**. Contracts and gates are
  implementation-ready, but no platform-owned resources exist to prove them.
- Closed-traffic bootstrap: **NOT READY**. All required runtime/state/registry/
  backup/monitoring resources, Production secrets, authorities and owner
  operational decisions remain absent.
