# Identity Administration Persistence

## Purpose and scope

This document defines the persistence foundation for future ACP Enterprise
identity-administration services. It covers pending verified email changes,
forced-password-reset state, and the repository boundary that owns identity
mutation persistence. It does not make the related workflows operational.

Future API and service work must retain the platform flow:

```text
API
→ authentication and authorization dependencies
→ IdentityAdministrationService
→ identity repositories and existing security services
→ PostgreSQL
```

`AuthenticationService` remains responsible for authentication, credential
verification, session validity, refresh rotation, and session revocation.
`AuthorizationService` remains responsible for company, membership, role,
permission, and branch decisions. `RecoveryService` remains responsible for
password-reset tokens and password recovery. Identity repositories neither
authorize requests nor publish events.

## Pending verified email changes

`PendingEmailChange` is a first-class immutable-history record with a controlled
lifecycle: `pending`, `confirmed`, `revoked`, `superseded`, or `expired`. It
stores the proposed normalized email, an optional display form, a deterministic
verification-token hash, origin metadata, and lifecycle timestamps. It never
stores a plaintext token.

Only a `pending` row is consumable. Confirmation locks the row and permits one
transition to `confirmed`; all terminal transitions are timestamped. A later
service must validate expiration and state, recheck global email uniqueness,
apply the verified email, and publish the required business, security, and audit
records in one transaction.

The model supports self-service and future company or platform administration.
Company-originated requests retain the initiating company for audit context, but
that field does not grant tenant authority. Authorization remains outside the
repository.

## Email reservation and concurrency

PostgreSQL provides three complementary safeguards:

1. `users.normalized_email` remains globally unique and is the final authority.
2. Partial unique indexes allow only one `pending` request per user and one
   `pending` reservation per normalized email.
3. The identity repository acquires a transaction-scoped PostgreSQL advisory
   lock derived from the normalized email before availability checks or final
   mutation.

The advisory lock serializes reservations and confirmations for the same email,
including the otherwise unavoidable race between checking `users` and inserting
or updating a row. The partial indexes remain defensive database constraints if
a caller violates repository ordering. Expired rows are transitioned to
`expired` before their address is reused; revoked and superseded rows do not
reserve an address. A user row lock serializes competing requests for one user.

All callers must supply a trimmed, lowercase normalized email. The repository
rejects noncanonical input rather than silently applying a second normalization
policy. Future services own user-facing parsing and normalization before calling
the repository.

## Forced-password-reset state

Forced-reset state is stored on `UserCredential`:

- `password_change_required`
- `password_change_required_at`
- `password_change_required_reason_code`
- `password_change_required_by_user_id`
- `password_change_required_company_id`
- `password_change_required_cleared_at`

This location was selected because the state governs credential usability and
must remain one-to-one with the credential. It also lets future authentication
logic load the policy with the credential row it already locks. Database checks
require complete origin metadata while active and preserve the prior requirement
and clearing timestamps after it is cleared.

A dedicated credential-security-state table was considered. It would add a
second one-to-one lifecycle and more joins without providing independent history
in the approved scope. Storing the flag on `User` was rejected because global
identity and credential security have different ownership and lifecycle rules.
Credential-version increments alone were rejected because they invalidate stale
sessions but cannot represent an outstanding password-change obligation.

This milestone does not change login behavior. A future service must set or clear
the state transactionally, coordinate credential-version and session invalidation
through `AuthenticationService`, and emit events. Unrelated credential updates
must not clear the state.

## Repository ownership

`UserIdentityRepository` owns:

- locking users and credentials for identity mutation;
- canonical email lookup and availability queries;
- normalized-email advisory locking;
- pending-change creation, expiration, supersession, revocation, and locked
  retrieval;
- the persisted confirmation transition and verified email mutation;
- forced-password-reset set and clear transitions.

Methods accept an existing `AsyncSession`, flush when an assigned identifier or
constraint result is required, and never commit independently. The future
`IdentityAdministrationService` owns the outer transaction and coordinates the
repository with authentication, recovery, event, and audit services. Ordinary
user retrieval, memberships, authorization evaluation, session mutation, token
generation, password hashing, and delivery do not belong in this repository.

## Delivery and outbox direction

Email delivery is deliberately absent. The approved future flow is:

```text
database transaction
→ durable outbox or delivery record
→ background worker
→ email provider
```

The service will persist the pending change and durable delivery intent in the
same database transaction. Network delivery will occur after commit so database
locks are never held across provider calls. Delivery records can then support
retry, deduplication, observability, and controlled failure handling without
changing the pending-change lifecycle.

## Sessions and history

Current `AuthenticationSession` records represent active and terminal security
state used by `AuthenticationService`. They are not redesigned here. Future
session-history presentation may read retained session and security-event data or
introduce a purpose-built historical projection. Only `AuthenticationService`
may perform session-security mutations and revocation semantics.

## Security invariants

- Plaintext verification tokens, passwords, refresh tokens, and credential
  hashes are excluded from pending email-change records and repository errors.
- Restrictive foreign keys preserve identity and administrative history.
- Global user identity remains separate from tenant membership and company
  authorization.
- Repositories do not infer company access from initiating-company metadata.
- Confirmation is single-consumption and protected by row and advisory locks.
- Global normalized-email uniqueness is rechecked during final mutation and is
  enforced by PostgreSQL.
- Forced-reset state is changed only through credential-row locking and cannot be
  cleared by ordinary credential updates.

## Future milestones

Later reviewed milestones may add `IdentityAdministrationService`, self-service
and company-administration APIs, event orchestration, login enforcement for
forced reset, durable delivery/outbox processing, and frontend experiences. MFA,
passkeys, SSO, SCIM, and directory synchronization remain separate future work.
None of those capabilities is operational merely because this persistence schema
exists.
