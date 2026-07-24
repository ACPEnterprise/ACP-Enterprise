# ADR 0003: Authenticated Worker Transport Transaction Ownership

- **Status:** Accepted
- **Date:** 2026-07-24
- **Decision owners:** Engineering leadership

## Context

Authenticated inbound worker messages coordinate protocol state owned by Worker
Transport with orchestration state owned by Worker Control. A heartbeat or
structured result must not be considered accepted unless its domain mutation,
monotonic sequence advancement, and durable receipt all succeed together.

Using separate transactions for these operations could leave a partially
accepted message after a process failure or database error. The transaction
boundary must preserve Worker Control's domain authority without allowing
Worker Transport to duplicate its business rules.

## Decision

Worker Transport owns the single database transaction for processing each
authenticated inbound worker message.

Worker Control exposes transaction-aware domain operations that participate in
the caller's existing `AsyncSession`. These operations:

- do not open nested transactions;
- do not commit;
- do not roll back the caller's transaction; and
- preserve Worker Control's ownership of business rules and validation.

The authenticated message transaction atomically performs:

1. transport session loading and locking;
2. session, identity, key-version, expiry, revocation, timestamp, sequence, and
   duplicate validation;
3. the Worker Control heartbeat or structured-result domain mutation;
4. sequence advancement;
5. durable receipt insertion; and
6. one final commit.

Any failure rolls back the Worker Control mutation, sequence advancement, and
receipt insertion together.

Existing standalone Worker Control service methods continue to own their
transactions. Each wrapper opens its normal transaction, invokes the same
transaction-aware domain operation, and commits once.

## Rationale

This boundary provides atomic guarantees for:

- duplicate detection;
- heartbeat or result mutation;
- sequence advancement; and
- durable receipt persistence.

It prevents partially accepted messages while avoiding duplication of Worker
Control rules inside Worker Transport.

## Consequences

### Positive

- Worker Control remains authoritative for worker orchestration and business
  rules.
- Worker Transport remains authoritative for authenticated protocol durability
  and message-processing orchestration.
- Identical committed duplicates return their prior receipt without repeating
  the domain effect.
- Altered duplicates fail closed.
- Existing standalone Worker Control callers retain their transaction-owning
  service interface.
- Future HTTP, WebSocket, gRPC, queue, or other transport adapters can reuse the
  same service boundary.

### Constraints and required practices

- All database-backed transport adapters must use the same `AsyncSession` for
  transport persistence and Worker Control mutation.
- Repositories flush when necessary but do not commit.
- Transaction-aware Worker Control operations must not start nested
  transactions or hide transaction ownership.
- Durable database locking and constraints remain necessary; in-process locking
  is not an adequate substitute.
- Live provider execution remains outside this decision.

## Alternatives considered

### Separate Worker Transport and Worker Control transactions

Rejected because sequence advancement or a Worker Control domain mutation could
commit without the corresponding durable receipt. The inverse ordering could
also persist a receipt before its domain effect succeeds.

### Allow Worker Control to open a nested transaction

Rejected because transaction ownership becomes ambiguous, and nested SQLAlchemy
transaction behavior does not provide the required single atomic boundary.

### Duplicate heartbeat or result rules in Worker Transport

Rejected because it would create competing domain authority and allow the two
implementations to drift.

### Use only in-process locking

Rejected because an in-process lock cannot coordinate multiple processes or
survive process restarts. Database-backed locking and uniqueness constraints
are required for durable concurrency control.
