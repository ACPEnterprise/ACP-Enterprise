# Platform resilience contract

## Persistence inventory

| State | Classification | Recovery contract |
| --- | --- | --- |
| PostgreSQL, Business Events, outboxes, audit | `AUTHORITATIVE_PERSISTENT` | Consistent database backup plus isolated application-level restore proof. |
| Redis session/coordination/cache | `CACHE_ONLY` unless a feature explicitly proves otherwise | Reconstruct from durable authority; never restore stale authorization as truth. |
| QBO runtime credentials and expected-company binding | `PROTECTED_SECRET` | Authorized secret backup/reprovisioning; presence and permissions only in ordinary evidence. |
| Sealed QBO/HCP Migration generations | `AUTHORITATIVE_PERSISTENT` protected evidence | Preserve immutable digests, ACLs, generation identity, and separate storage; never put contents in Git/logs. |
| Protected documents/artifacts | `AUTHORITATIVE_PERSISTENT` | Storage-specific encrypted backup and restore validation with owning-domain authorization intact. |
| Application images/static assets/release manifests | `RECONSTRUCTIBLE` when immutable artifact storage exists | Identify by Git SHA/build digest; retain known-good compatible release. |
| Environment configuration references | `RECONSTRUCTIBLE`; values may be `PROTECTED_SECRET` | Version non-secret schema; reprovision secret values from authorized store. |

## Health semantics

`HEALTHY` means every hard dependency and release/schema identity agrees.
`DEGRADED` permits only explicitly classified degradable functions.
`NOT_READY` blocks traffic/mutation because correctness cannot be established.
`UNAVAILABLE` means the product cannot safely serve the operation. Process
liveness alone never promotes readiness.

The release gate compares exact backend SHA, primary frontend build SHA,
Mission Control artifact SHA-256, and a single Alembic head. Any mismatch is
`NOT_READY`. It detects incomplete deployment but does not automatically roll
back or restore data.

## Backup and restore evidence

The versioned manifest records environment class, timestamp, source database
identity, authority SHA, schema head, format, byte size, and SHA-256. Backup and
manifest are mode `0600`; their directory is `0700`. The manifest contains no
URL, credential, host path secret, or payload.

Restore is accepted only after checksum and `pg_restore --list` validation,
exact source-identity agreement, a distinctly identified isolated target,
single-transaction restore, schema checks, application connectivity, and
representative invariants. File existence is not restore proof.

## Capacity and retention

Measure database size/growth, filesystem free bytes/percent, log bytes/age,
protected-evidence bytes, document bytes, release count/bytes, and verified
backup count/bytes/age. Logs must be rotated independently of immutable audit
and Business Events. Deletion thresholds and Production retention require owner
policy; no automatic deletion is authorized by this contract.

## Clock safety

Tokens, Timekeeping, effective dating, leases, idempotency windows, outbox
scheduling, and evidence timestamps depend on UTC clock correctness. Runtime
monitoring must compare host time to an approved time source and make material
skew `NOT_READY` for security- or ordering-sensitive mutation. No repair may
rewrite accepted timestamps.

## Recovery acceptance

Every rehearsal records detection, fail-safe behavior, remaining availability,
mutation boundary, potentially stale evidence, operator action, required owner
authority, verification, and history preservation. Post-recovery security must
prove authentication, authorization versioning, Company/Branch isolation,
secret reference permissions, safe logging, and no resurrection of revoked
cached authority.

## Launch-critical failure acceptance

| Failure | Detection and safe behavior | Recovery and verification |
| --- | --- | --- |
| Backend crash, including after commit | Backend readiness fails; mutations are unavailable. An ambiguous client response is reconciled by resource lookup or same-key replay. | Restart exact release; verify DB/schema, receipt/idempotency and event/outbox evidence. |
| PostgreSQL unavailable or storage lost | Database/schema readiness is `NOT_READY`; all authoritative mutation stops. | Restore service, or explicitly authorize an isolated-proven backup restore; verify invariants before reopen. |
| Redis unavailable or lost | Redis component fails. Required security/coordination paths fail closed; durable DB truth is unchanged. | Start empty Redis and reconstruct permissible state; prove revoked authority is not resurrected. |
| Worker/outbox/Communications worker stopped | Heartbeat and backlog age expose failure; domain commits remain durable and delivery is delayed/uncertain. | Restart, expire leases through accepted authority, reconcile provider uncertainty, and resume idempotently. |
| Frontend unavailable | Frontend health fails while backend may remain healthy; web workflows are unavailable. | Restore the matching immutable artifact and verify direct routes without requiring cache clearing. |
| Partial deployment or migration failure | Backend/frontend SHA or schema mismatch makes release gate `NOT_READY`; transactional migration failure retains prior head. | Complete the release or roll back compatible application artifact; never silently downgrade schema. |
| Disk capacity, stale/missing/corrupt backup | Capacity/freshness/checksum probes raise `ACTION_REQUIRED`; corrupt backup is rejected before restore. | Add capacity without deleting authority; create and restore-verify a new backup. |
| Missing protected configuration | Startup/readiness fails closed without displaying values. | Authorized reprovisioning/rotation, then presence, permission, identity, and security verification. |
| TLS/proxy failure | HTTPS/proxy probe fails independently of backend health. | Validate config/certificate, restore proxy service, verify HTTPS; no DNS/TLS bypass. |
| Mobile/browser 502/503 or response loss | Client treats mutation outcome as ambiguous, not failed-and-safe-to-repeat. | Recover service, reconcile or same-key replay, refresh authorization and state. |
| Complete host loss | Availability and all local heartbeats fail. | Rebuild from immutable release/runtime definitions, restore approved persistence and secret references, then run post-deploy gate. |

## Business continuity by component outage

| Outage | Customer/Job/Scheduling/Dispatch | Technician/Timekeeping | Estimate/Invoice/Payment | Communications | Employee Admin/Owner Ops |
| --- | --- | --- | --- | --- | --- |
| Backend or database | `UNAVAILABLE` / `MUTATION_BLOCKED` | `MUTATION_BLOCKED` | `MUTATION_BLOCKED` | `MUTATION_BLOCKED` | `UNAVAILABLE` |
| Required Redis | Reads may be `READ_ONLY_SAFE` only when authenticated authority remains verifiable; otherwise `UNAVAILABLE` | `MUTATION_BLOCKED` | `MUTATION_BLOCKED` | queued durable work may wait | `UNAVAILABLE` |
| Worker only | `AVAILABLE` except worker-owned projections/actions | interactive paths remain as independently healthy | interactive paths remain; async results may be stale | `STALE_READ_ONLY` status and delayed delivery | `AVAILABLE` with explicit stale worker evidence |
| Frontend only | Web `UNAVAILABLE`; authorized APIs may remain available to supported clients | Mobile may remain `AVAILABLE` if backend is healthy | Web `UNAVAILABLE` | Web `UNAVAILABLE` | Web `UNAVAILABLE` |
| Communications provider/worker | `AVAILABLE` | `AVAILABLE` | `AVAILABLE` | `MUTATION_BLOCKED` or `STALE_READ_ONLY` for status | `AVAILABLE` with truthful provider gate |
| Incomplete release/schema mismatch | `UNAVAILABLE` | `MUTATION_BLOCKED` | `MUTATION_BLOCKED` | `MUTATION_BLOCKED` | `UNAVAILABLE` |

ACP has no general offline mutation authority. Staff may retain temporary notes
outside ACP during an outage, but those notes require later controlled entry
and reconciliation; they are not treated as committed ACP records.
