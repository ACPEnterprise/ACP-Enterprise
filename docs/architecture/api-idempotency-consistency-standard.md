# BANK.PLAT.008 API Idempotency Consistency Standard

## Boundary

ACP uses one Platform contract over existing domain-owned command receipts. It
does not introduce a shared mutation service or replace stronger aggregate,
append-only, provider, Accounting, Payments, AP, Purchasing, worker-transport,
or notification-outbox identities.

The versioned mutation coverage registry inventories all 233 current HTTP
operations expressed with `POST`, `PUT`, `PATCH`, or `DELETE`. Its fingerprint
is part of `PlatformContractManifest`; adding or changing a mutating route
without reconciling the registry fails the Platform meta-test.

| Classification | Current count | Meaning |
|---|---:|---|
| `IDEMPOTENCY_REQUIRED` | 92 | Existing domain request identity and durable receipt/replay contract |
| `NATURALLY_IDEMPOTENT` | 58 | Resource target state or optimistic aggregate version is stronger than a separate key |
| `IMMUTABLE_APPEND_ONLY` | 4 | Accepted deterministic evidence/receipt identity owns replay, with concrete test evidence recorded in the registry |
| `NON_MUTATING_READ_ONLY` | 5 | Query or qualification operation expressed as POST |
| `EXPLICIT_EXEMPTION` | 74 | Compatibility boundary lacking a proven cross-network receipt; no compliance is claimed |

An exemption is not evidence of idempotency. It prevents a legacy API from
being silently described as safe and identifies where a separately bounded
domain transition is required. PLAT.008 does not add breaking request fields or
redesign those services.

An append-only classification is accepted only when its registry record names
concrete replay evidence. The registry fails closed if that evidence is absent.
Customer note creation, Customer consent creation, and direct Business Event
publication are explicit exemptions: each creates a fresh append-only identity,
but none currently accepts a deterministic request identity that can recover an
earlier result after an uncertain network outcome. Their domain behavior is
unchanged; append-only storage alone is not described as replay safety.

## Canonical identity and digest

The default identity is `(Company, semantic operation, Idempotency-Key)`.
Branch remains immutable request and authorization context unless an accepted
domain aggregate explicitly defines Branch as part of its unique command
identity. Platform-global authentication, integration, and worker-transport
operations are identified explicitly rather than pretending to be Company
mutations.

Canonical request digests use sorted mapping keys and typed representations for
UUIDs, decimal amounts, dates, and timezone-aware timestamps. Sequence order is
preserved; a domain must normalize a genuinely unordered collection before
digesting it. Binary floating point and naive timestamps fail closed. Domains
exclude unstable transport metadata and server-authored omissions before using
the shared digest helper.

## Replay and recovery

Same tenant, operation, key, and digest returns the original authoritative
resource/result identity without another domain, Business Event, or successful
audit effect. A materially different digest conflicts deterministically.
Concurrent duplicates converge through each domain's durable unique constraint,
receipt, lock, or compare-and-set implementation—not an in-memory lock.

A client that loses the response retries the same identity to recover the
committed result. Replay is reauthorized against current Company/Branch access;
possession of a key is never permission. Sensitive one-time material is not
replayed merely because an ordinary response is recoverable.

Audit evidence distinguishes original execution, exact recovery, and a safe
contradictory-attempt classification where the domain records one. Exact replay
does not fabricate a second successful human action. Business Events remain
one logical consequence of the original mutation.

## Current domain inventory

The registry covers Customers and service locations, Jobs, Scheduling,
Dispatch, Timekeeping and Workforce, Inventory, Purchasing, Price Book,
Estimates, Invoices/AR, Payments, AP, Accounting, Platform communications and
notification boundaries, identity/authorization, and accepted Engineering
transport APIs. Payroll currently exposes no HTTP mutation router and therefore
has no endpoint record; its command contracts remain domain-owned.

PLAT.006 Company-scoped outbox uniqueness remains unchanged. No schema,
endpoint, authorization, Business Event, audit, or source-domain mutation is
introduced by this standard.

### Purchasing replenishment decisions

`POST /api/v1/purchasing/replenishment/decisions` is
`IDEMPOTENCY_REQUIRED`. Its accepted identity is Company plus the command's
`idempotency_key`; the durable decision stores a canonical digest of the full
command. Exact replay returns the existing decision before recomputing the
recommendation, so a lost response can be recovered without another Purchase
Order or Business Event. Reusing the key with a different command conflicts.
A new key carrying old recommendation evidence fails with
`STALE_REPLENISHMENT_RECOMMENDATION`, and Company plus recommendation-digest
uniqueness prevents a second disposition for the same evidence. Branch remains
explicit authorization and evidence context rather than a globally shared
identity. Possession of a key does not bypass current
`PurchasingPermission.APPROVE` authorization.

The qualified coverage fingerprint is
`332a6edbc0f97d9d37e0031b76fc058e52b2e91c2fdd1fc4af00c1277a9c9f8a`.

PLATFORM.RELIABILITY.IDEMPOTENCY.1 adds an optional transactional receipt path
for Customer and Job creation. Headerless calls remain explicit compatibility
exemptions; calls carrying `Idempotency-Key` receive durable replay, conflict,
tenant-isolation and single-authority concurrency guarantees. The registry also
tracks the authoritative Purchasing branch-policy command added after the
original PLAT.008 snapshot.
