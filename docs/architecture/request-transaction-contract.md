# ACP Enterprise Request Transaction Contract

## Purpose

This document defines the canonical database-session and transaction contract for
request-driven ACP Enterprise operations. It applies uniformly to every domain,
including Customers, Identity, Scheduling, Jobs, Estimates, Dispatch, Inventory,
and Accounting.

## Request lifecycle

```text
FastAPI request
  -> request-scoped security session
     -> authenticate
     -> resolve Company, Membership, Branch, Role, and Permission context
  -> request-scoped application session
     -> mutating service transaction
        -> repositories
        -> domain mutation
        -> Business Event staging
        -> commit or rollback
  -> dependency cleanup closes both sessions
```

FastAPI creates each session through dependency injection and keeps it alive for
the request. Authentication and authorization share the security session. Routers
and application services share a separate application session. Dependency cleanup
closes both sessions, including rolling back any uncommitted implicit read
transaction.

Authorization resolution converts mapped User, Company, Membership, Branch, Role,
and Permission records into frozen scalar value objects before returning an
`AuthorizationContext`. Domain services receive no live ORM identity, lazy-loading
capability, or security-session attachment. These values retain the established
attribute-level context API but cannot be used for persistence.

## Ownership

### Session ownership

The database session module owns `AsyncSession` construction and configuration.
FastAPI dependencies own request lifetime and disposal:

- `get_security_database_session` supplies the isolated security session.
- `get_database_session` supplies the application session used by routers and
  services.

Callers must not retain either session beyond the request.

### Transaction ownership

The public mutating service method owns exactly one transaction with
`async with session.begin()`. That boundary commits on success and rolls back on
any exception. A router must invoke a mutating service with an application session
that has not already performed database work.

Repositories never begin, commit, or roll back transactions. Read-only services
may execute queries without opening an explicit transaction; SQLAlchemy's implicit
read transaction is discarded when the request session closes.

Authentication services retain ownership of their own security mutations, such as
session validation and last-seen maintenance, within the isolated security
session. Authorization resolves tenant context from that same security session and
does not mutate domain state.

## Why security reads are isolated

SQLAlchemy begins a transaction when authentication or authorization first reads
from PostgreSQL. Reusing that session for a domain service that subsequently calls
`session.begin()` can raise `InvalidRequestError`. Isolating security resolution
keeps authorization centralized while guaranteeing that the application session
arrives at a mutating service without an active transaction.

Moving transaction ownership to routers or middleware was rejected because it
would make atomic service behavior dependent on HTTP delivery and would weaken
service reuse. Nested transactions were rejected because savepoints do not define
the request's commit owner and could accidentally commit caller-owned work.

## Business Events and rollback

Business services stage Business Events on the application session inside the
same transaction as domain mutations. Event staging does not commit. If repository
work, validation, event staging, or flushing fails, the service transaction rolls
back all domain records, sequence changes, reservations, audit records, outbox
records, and Business Events participating in that transaction.

## Responsibilities

- Routers validate transport data, obtain authenticated and authorized context,
  and invoke services. They do not begin transactions.
- Authentication verifies credentials and sessions using the security session.
- Authorization resolves and validates Company, Membership, Branch, Role, and
  Permission context using the security session, then returns an immutable,
  detached value snapshot.
- Mutating services own validation, orchestration, the application transaction,
  and transactional event staging.
- Repositories own SQL, persistence, locking, and tenant-scoped queries but never
  transaction completion.

New request-driven mutation paths must follow this contract without domain-specific
session or transaction exceptions.
