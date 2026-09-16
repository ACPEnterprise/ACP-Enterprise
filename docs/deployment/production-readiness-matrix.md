# Twelve Hats Production readiness matrix

Evidence date: 2026-09-16. Protected authority at audit start:
`a65a104c21282fd8f94a2e9bac37ba576a91a75c`.

This packet treats All County Plumbing & Leak as the beta tenant and its records
as customer-owned business data. Permanent platform infrastructure, domains,
master secrets, artifacts, and observability must be provisioned for Twelve Hats
/ The 10:31 Project. Existing Preview infrastructure is evidence only and is not
a Production target.

`READY` means the requirement has direct evidence. Source configuration without
runtime evidence is `READY BUT UNPROVEN`.

| Area | Requirement | Classification | Current evidence / exact gate |
| --- | --- | --- | --- |
| Compute | Backend service | READY BUT UNPROVEN | Immutable-image Compose service, non-root capability boundary, read-only root, health check, restart policy, graceful stop, resource and PID limits; no Production runtime exists. |
| Compute | Frontend delivery | READY BUT UNPROVEN | Loopback-only Nginx service, SPA/API proxy, health check, read-only root, bounded tmpfs and resources; image has not run on Production infrastructure. |
| Compute | Startup ordering | READY BUT UNPROVEN | Migration must succeed before backend; backend readiness must pass before frontend. Compose rendering/runtime remain unproven on the selected host. |
| Compute | Identity delivery worker | BLOCKED | External identity delivery is intentionally disabled. The current admitted Postmark worker is Preview-only and is not a Production worker. |
| Database | Dedicated PostgreSQL 16 topology | EXTERNAL ACTION REQUIRED | Select/provision a private managed endpoint independent from application and Preview. |
| Database | Least-privilege users/connectivity | OWNER ACTION REQUIRED | Name migration and runtime operators; provision separate credentials and verify private/TLS controls. |
| Database | Migration procedure | READY BUT UNPROVEN | One-shot migration gate exists; zero-to-head rehearsal passed all 178 revisions to one `o1q9s27h4u0v` head. Exact Production endpoint is absent. |
| Database | Backup/PITR | MISSING | Provider PITR, approved RPO/retention, encrypted off-host logical backup, manifest, and alerting are not provisioned. |
| Database | Restore rehearsal | READY | PostgreSQL 16 disposable restore completed in 17 seconds; catalog, schema and representative counts were verified. Source dump lacked the Production sidecar manifest, so Production recovery-point readiness is not established. |
| Redis | Private TLS/ACL service | EXTERNAL ACTION REQUIRED | Provision dedicated `rediss` endpoint, ACL user, persistence/recovery policy and monitoring. |
| Redis | Restart/recovery proof | MISSING | No Production Redis service or failover/restart evidence exists. |
| Edge | Production DNS | EXTERNAL ACTION REQUIRED | Permanent hostname is `app.twelve-hats.com`; stable runtime address and exact DNS record are absent. |
| Edge | TLS lifecycle/HTTPS | EXTERNAL ACTION REQUIRED | Caddy template and HSTS policy exist; issuance, renewal, expiry alerting and HTTPS verification require the live edge. |
| Edge | Trusted hosts/CORS | READY BUT UNPROVEN | Repository contract binds to `https://app.twelve-hats.com`; runtime verification remains pending. |
| Edge | Internal isolation | READY BUT UNPROVEN | Backend is not host-published and frontend binds loopback only; host firewall/provider network evidence is absent. |
| Secrets | Inventory/injection | READY BUT UNPROVEN | Required keyrings and provider credentials are inventoried and file-mounted. Fail-closed preflight checks modes and placeholders. No Production values exist. |
| Secrets | Rotation/recovery | OWNER ACTION REQUIRED | Name secret custodian and recovery authority; generate independent Production values and rehearse rotation/recovery without logging material. |
| Evidence | Persistent evidence storage | EXTERNAL ACTION REQUIRED | Select encrypted Twelve Hats-owned storage, restricted mount, retention policy, access logging and independent backup. |
| Observability | Health endpoints | READY | Safe liveness/readiness covers application identity, database, schema and Redis. |
| Observability | Logs/metrics/uptime/capacity | READY BUT UNPROVEN | Bounded local logs and launch thresholds exist. External collection, uptime probes, DB/cache/disk telemetry, destinations and humans are absent. |
| Observability | Backup-failure visibility | MISSING | Cannot be proven before backup provider/job selection. |
| Release | Immutable revision/artifacts | READY BUT UNPROVEN | Preflight requires exact Git SHA and backend/frontend `@sha256` references; registry artifacts are absent. |
| Release | Preflight/migration/smoke gates | READY BUT UNPROVEN | Fail-closed preflight and documented gates exist; no Production execution evidence. |
| Release | Previous release/rollback | BLOCKED | First release has no prior Production artifact. Before traffic the rollback is traffic closed; after writes, schema rollback is not assumed safe. |
| DR | Application redeployment | READY BUT UNPROVEN | Immutable artifact procedure is documented but registry/runtime/redeployment rehearsal are absent. |
| DR | Database recovery | BLOCKED | Restore mechanics are proven; provider PITR, manifest-bearing Production backup and authorized restore rehearsal remain absent. |
| DR | Secrets recovery | OWNER ACTION REQUIRED | Requires independent escrow/recovery design and named authorized humans. |
| Cutover | Controlled runbook | READY BUT UNPROVEN | Preflight through rollback is ordered below; execution requires a separate go/no-go authorization. |

## Exact launch blockers

1. Provision Twelve Hats-owned Production runtime, private PostgreSQL 16, private
   TLS/ACL Redis, encrypted evidence storage, registry, and monitoring.
2. Create `app.twelve-hats.com` DNS only after the runtime address is stable;
   prove certificate issuance/renewal and external HTTPS monitoring.
3. Generate independent Production secrets on the Production boundary, establish
   mode-0600 custody, and name release, incident, security, backup, restore, and
   secret-recovery authorities.
4. Approve RPO, RTO, retention and failure-domain policy; enable PITR and produce
   a manifest-bearing encrypted off-host backup; rehearse restoring it.
5. Build/scan/publish immutable backend and frontend images from the selected
   protected SHA and retain the exact digests.
6. Run the fail-closed preflight, Compose rendering, migrations, health and
   authenticated smoke acceptance against the closed Production boundary.
7. Reconcile the final HCP delta and obtain owner/accountant dispositions defined
   by the existing migration authority before business cutover.
8. Record a separate owner go/no-go. This candidate does not authorize traffic.

## Owner and external actions

- Owner: approve provider spend, RPO/RTO/retention, geographic/storage policy,
  release window, and named operational authorities.
- Twelve Hats / The 10:31 Project: control platform accounts, domains, registry,
  master secrets, infrastructure and monitoring—not All County.
- DNS/TLS/cloud/database/cache/storage/monitoring providers: provision and return
  runtime evidence.
- All County: certify customer-data reconciliation and cutover business timing;
  it does not own permanent platform infrastructure.
