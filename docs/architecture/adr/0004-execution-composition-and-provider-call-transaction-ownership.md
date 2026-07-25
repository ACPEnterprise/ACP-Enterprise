# ADR 0004: Execution Composition and Provider Call Transaction Ownership

- **Status:** Accepted
- **Date:** 2026-07-25
- **Decision owners:** Engineering leadership

## Context

An approved Engineering Execution must be durably bound to one Company, worker,
lease, provider, capability intersection, repository expectation, and evidence
set before any future provider call is permitted. Provider calls are external
operations and cannot participate safely in a PostgreSQL transaction.

Holding database locks across provider communication would increase contention
without making the external operation atomic. Calling a provider before durable
composition would permit work without durable acceptance evidence.

## Decision

`ExecutionCompositionService` owns the database transaction that creates an
immutable `ExecutionComposition`, its immutable `CompositionReceipt`, Enterprise
Audit evidence, and Business Events. It commits exactly once after all
eligibility and exact-evidence checks succeed.

The composition transaction never invokes an execution provider. A future live
client may call a provider only after it receives an authenticated, unexpired
composition and receipt through Worker Control and Worker Transport.

A future provider call:

- occurs outside any database transaction and without holding database locks;
- uses a stable attempt and idempotency identifier prepared in an earlier
  service-owned transaction;
- returns only provider-neutral structured progress or result contracts; and
- records each authenticated progress message or normalized result in a new,
  bounded transaction using compare-and-swap and quarantine rules.

Late, invalid, cancelled, or expired results remain durable quarantined evidence
and cannot complete the approved execution.

## Rationale

This boundary ensures that:

- no provider work can precede durable composition acceptance;
- composition, receipt, audit, and events cannot partially commit;
- database locks are never held during unbounded network communication;
- retries use durable idempotency evidence;
- provider failure cannot corrupt approval or composition state; and
- provider-specific behavior remains outside Engineering Control, Engineering
  Execution persistence, and Worker Control.

## Consequences

### Positive

- Engineering Control remains the sole owner of human approval and
  cancellation.
- Engineering Execution owns durable intent, composition, attempts, and
  normalized outcomes.
- Worker Control remains the owner of orchestration eligibility and leases.
- Worker Transport remains the owner of authenticated delivery, sequencing,
  replay protection, and transport receipts.
- Future providers can implement the same provider-neutral contracts without
  changing business policy.

### Constraints and required practices

- Repositories do not commit, roll back, or invoke providers.
- Composition creation and receipt creation use the same `AsyncSession`.
- Provider credentials, raw logs, internal paths, and provider-specific types
  are not persisted in composition records.
- `repository_mutated` is always false and is enforced by domain validation and
  a database constraint.
- A future live-client supervisor must not interpret provider success as commit,
  push, merge, or deployment authority.

## Alternatives considered

### Invoke the provider inside the composition transaction

Rejected because an external call cannot be atomically committed with
PostgreSQL and would hold locks for an unbounded duration.

### Invoke the provider before composition persistence

Rejected because work could begin without durable approval evidence, receipt,
lease binding, or audit.

### Let the provider update Engineering Control directly

Rejected because it would bypass owner approval authority and leak
provider-specific behavior into the approval domain.

### Treat a late result as successful completion

Rejected because approval, composition, or lease authority may have expired
before the result arrived. Such evidence must be quarantined for review.
