# BANK.PLAT.008 API Idempotency Consistency Standard

## Boundary

ACP uses one Platform contract over existing domain-owned command receipts. It
does not introduce a shared mutation service or replace stronger aggregate,
append-only, provider, Accounting, Payments, AP, Purchasing, worker-transport,
or notification-outbox identities.

The versioned mutation coverage registry inventories all 231 current HTTP
operations expressed with `POST`, `PUT`, `PATCH`, or `DELETE`. Its fingerprint
is part of `PlatformContractManifest`; adding or changing a mutating route
without reconciling the registry fails the Platform meta-test.

| Classification | Current count | Meaning |
|---|---:|---|
| `IDEMPOTENCY_REQUIRED` | 90 | Existing domain request identity and durable receipt/replay contract |
| `NATURALLY_IDEMPOTENT` | 58 | Resource target state or optimistic aggregate version is stronger than a separate key |
| `IMMUTABLE_APPEND_ONLY` | 7 | Accepted deterministic evidence/receipt identity owns replay |
| `NON_MUTATING_READ_ONLY` | 5 | Query or qualification operation expressed as POST |
| `EXPLICIT_EXEMPTION` | 71 | Compatibility boundary lacking a proven cross-network receipt; no compliance is claimed |

An exemption is not evidence of idempotency. It prevents a legacy API from
being silently described as safe and identifies where a separately bounded
domain transition is required. PLAT.008 does not add breaking request fields or
redesign those services.

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
