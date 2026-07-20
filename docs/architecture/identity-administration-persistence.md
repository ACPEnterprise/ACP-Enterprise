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

## Identity administration service layer

`IdentityAdministrationService` is the transaction owner for identity mutation
workflows. It accepts a resolved `AuthorizationContext`, calls the centralized
`AuthorizationService` for administrative permission evaluation, validates that
an administrative target has an active Membership in the context Company, and
coordinates `UserIdentityRepository` with existing token, authentication,
business-event, and audit services.

The service supports administrative email-change requests, authenticated
confirmation, revocation, expiration, forced-password-reset state, clearing that
state after a successful password change, availability validation, and a typed
identity-state projection for future APIs. No router or API contract is introduced
by this layer.

### Transaction lifecycle

Each mutation follows this sequence:

1. Validate centralized permission and canonical input before mutation.
2. Begin one service-owned database transaction.
3. Resolve and lock identity records through `UserIdentityRepository`.
4. Apply uniqueness, lifecycle, and company-membership persistence checks.
5. Coordinate credential-version changes and session revocation through the
   existing authentication boundary where the mutation invalidates identity
   security state.
6. Stage Business Event and Audit records in the same transaction.
7. Commit once, making the identity mutation and its event records visible
   together; any exception rolls all of them back.

“After successful transaction completion” therefore means staged records are not
observable or publishable until PostgreSQL commits successfully. The repository
never emits events and cannot leave an event behind after rollback.

### Service and repository boundaries

The service owns workflow decisions, authorization-service coordination,
user-facing normalization, secure token generation, event selection, and the
outer transaction. The repository owns SQL, row/advisory locks, availability
queries, active-membership persistence facts, and state transitions. An active
Membership lookup is a persistence fact used after centralized permission
evaluation; it does not grant authorization or calculate permissions.

The generated email-change token is returned once to the immediate caller and
only its HMAC hash is passed to persistence. Repeating an identical active request
is rejected because plaintext token recovery is intentionally impossible. Future
delivery retry will use durable delivery state rather than returning stored token
material.

### Session and credential coordination

A confirmed login-email change increments credential version and revokes active
sessions in the same transaction. Requiring a password reset does the same only
when the requirement represents a real state change; an identical repeat is a
no-op. Clearing the requirement is permitted only after the credential records a
password change later than the requirement timestamp.

`AuthenticationService` now enforces `password_change_required` after successful
credential verification and before session issuance. Successful password changes
and recovery resets call back into the identity service to validate and clear the
requirement within the caller-owned transaction. The existing authentication
boundary remains the owner of credential hashing, credential-version increments,
and session-security mutation semantics.

### Durable delivery extension

No network delivery occurs in an identity transaction. Email-change requests now
persist a `NotificationOutbox` intent alongside the pending change through the
dedicated repository, then commit both atomically. The intent contains resource
identifiers and normalized destination metadata but never the plaintext
verification token. A future worker and reviewed secret-safe token handoff will
perform provider delivery and retries after commit. See
`notification-outbox.md`; persistence does not make email delivery operational.

## Identity administration API boundary

The versioned HTTP foundation exposes the service layer through two route groups:

- `/api/v1/identity` contains authenticated self-service operations. Routers pass
  only the authenticated context User identifier, and service-owned ownership
  checks prevent a token or path from selecting another identity.
- `/api/v1/identity-admin` contains company-administration operations protected by
  the centralized `COMPANY_ADMINISTER` dependency before router execution.

Routers validate strict Pydantic schemas, obtain `AuthorizationContext`, call one
service operation, translate controlled service exceptions, and serialize API
responses. They do not query persistence, calculate authorization, generate
tokens, revoke sessions, publish events, or enforce lifecycle rules.

### Request lifecycle

```text
Bearer authentication
→ tenant AuthorizationContext resolution
→ centralized permission dependency when administrative
→ strict request validation
→ IdentityAdministrationService transaction
→ response serialization
```

Self-service confirmation uses a dedicated service entry point that requires the
pending request to belong to `context.user`. Administrative identity state and
mutations retain company-origin and active-Membership concealment in the service
and repository boundaries.

### HTTP errors

Authentication dependencies return `401`; centralized authorization dependencies
return generic `403`; concealed or absent identity resources map to `404`;
duplicate, expired, revoked, already-processed, and invalid lifecycle states map
to generic `409`; malformed schema input maps to FastAPI `422`; and otherwise
controlled identity failures map to `400`. Responses never expose repository,
database, token-hash, session, or exception internals.

The development/test response may return the newly generated plaintext email
verification token once, matching the existing authentication delivery boundary.
Preview and production responses always omit it. Durable outbox delivery remains
future work and no API claims that email delivery is currently operational.
