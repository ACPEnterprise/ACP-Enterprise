# PLATFORM.RELIABILITY.IDEMPOTENCY.1

ACP's mutation path is authorization, tenant-scoped idempotency admission,
database serialization, domain mutation and Business Event staging in one
transaction, followed by authoritative result recovery. Possession of an
idempotency key is never authorization.

The shared receipt identity is `(Company, operation, Idempotency-Key)`. Branch
is recorded authorization context unless a domain's accepted aggregate identity
explicitly makes it part of the operation. Canonical SHA-256 request evidence
excludes transport metadata and rejects binary floating-point input. Reuse with
a different digest fails with the safe `idempotency_conflict` API class.

Customer and Job creation adopt the receipt transaction when clients supply
`Idempotency-Key`. Their existing headerless contract remains an explicit,
documented compatibility exemption rather than being mislabeled replay-safe.
This supports incremental client adoption without silently breaking existing
integrations. Exact retries reconstruct the authoritative aggregate and do not
repeat the domain mutation or Business Event.

Database advisory transaction locks serialize concurrent requests across
backend processes. The durable receipt and domain effect commit or roll back
together. A missing result behind a completed receipt becomes
`reconciliation_required`; it is never re-executed. Safe diagnostics contain
only receipt identity and outcome class, not request bodies or credentials.

Retention classes are `transport`, `operational`, and `financial_audit`.
`expires_at` is nullable and policy-supplied. ACP does not invent a universal
purge interval; absent an approved policy, evidence is retained. Domain-owned
financial, Payroll, Purchasing, Inventory, Invoice, Payment, Timekeeping,
Dispatch and Accounting receipts remain authoritative and are independently
qualified rather than copied into the Platform table.

The standard API error vocabulary covers unauthorized, forbidden, not found,
validation, stale version, idempotency conflict, concurrency conflict,
dependency conflict, reconciliation required, provider unavailable and internal
failure. Payloads are safe classifications and never expose SQL constraint
names, stack traces, filesystem paths, provider secrets or protected request
data.
