# Business Event Delivery and Replay Hardening

## Existing architecture and guarantee

ACP domain services stage `BusinessEvent` rows inside the same database transaction as the authoritative domain mutation. A rollback removes both; a commit durably retains both. Existing consumers are Company-scoped pull projections rather than asynchronous mutation consumers:

| Consumer | Classification | Repository evidence |
|---|---|---|
| Customer timeline | Read-model/pull; replay-safe | `app.customers.timeline` |
| Operational analytics | Read-model/pull; replay-safe | `app.analytics.service` |
| Beacon event evidence | Read-model/pull; no event-driven mutation | `app.beacon.repository` |
| Communications source lookup | Read-model/pull; Company/Branch-bound | `app.communications.repository` |

There was no general push-delivery boundary before BANK.PLAT.005. The new foundation does not manufacture one for these pull consumers. It supplies a single durable delivery ledger for a future explicitly registered push/external consumer. The guarantee is **at least once physical acquisition with effectively-once logical application through an immutable consumer receipt**. It does not claim exactly-once transport or global ordering.

## Delivery identity and lifecycle

One delivery identity is the immutable pair `(event_id, consumer_name)`. It preserves event version, Company/Branch scope, attempt count, replay count, claim identity and expiry, safe failure classification, and terminal timestamps. Its explicit states are `pending`, `claimed`, `retryable`, `delivered`, and `terminal`. Append-only delivery evidence records every claim, expired-claim recovery, acknowledgement, retryable/terminal failure, and authorized replay request. Thus committed registered work is always pending, acknowledged, retryable, terminally visible, or explicitly outside delivery because its real consumer is pull-based.

## Retry, terminal failure, and recovery

Workers acquire ready work with PostgreSQL row locks and `SKIP LOCKED`; no in-memory lock is authoritative. A transient failure requires an explicit future eligibility time and caller-supplied maximum attempt boundary. BANK.PLAT.005 deliberately invents no backoff constants. Exhaustion, unsafe classification, or a terminal error produces visible terminal evidence; nothing is discarded.

Claims have explicit expiry. A worker may recover an expired claim and append recovery evidence. If a consumer effect committed but acknowledgement was interrupted, the immutable `(event_id, consumer_name)` receipt makes the repeated call return the same logical result without repeating the effect. Claim tokens prevent stale workers from acknowledging or failing newer work.

## Replay and ordering

Replay is an authorized redelivery of the original event, never a new business fact. The request retains actor and request identity, increments replay evidence, preserves tenant/subject/version identity, and fails closed for corrupt or unsupported versions. Read authority does not imply replay authority; no replay API or new role is added here.

No global ordering is promised. A registered order-sensitive consumer must provide positive `aggregate_sequence` evidence. Its Company/consumer/aggregate cursor rejects a stale or duplicate sequence. Order-independent consumers use the immutable receipt without unnecessary sequencing.

## Isolation, audit, and versioning

Claims and all state transitions require the delivery's exact Company and Branch scope. Cross-tenant work is neither visible nor bindable. Delivery evidence is additive and contains identities, safe codes, digests, actors, timestamps, and lineage—not copied event payloads, credentials, payment material, or secrets. It complements domain audit evidence and does not replace it.

Consumers declare supported event schema versions. Missing versions retain the legacy `1.0` interpretation already used by accepted events; malformed or unsupported versions fail closed. An incompatible historical payload requires an explicit versioned transformation contract.

## Registration and exclusions

Future consumers must register a stable name, classification, supported versions, and repository evidence. Side-effect consumers must perform their mutation and immutable receipt in one transaction, then acknowledge delivery. Active Enterprise worker/factory, ECO, HCP Migration, Accounting, Beacon, Purchasing, CRM, and Inventory runtime were not changed. No external endpoint, scheduler, autonomous remediation, Preview delivery, or Production operation is introduced.
