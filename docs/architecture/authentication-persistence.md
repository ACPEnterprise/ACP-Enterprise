# Authentication Persistence

This document defines the persistence boundary introduced by Sprint 5 Milestone 2D. It does not define authentication APIs, cryptographic implementations, or authorization evaluation.

## Session lifecycle

An `AuthenticationSession` belongs to one global User. Its UUID primary key is also its opaque public session identifier. A session records the credential and authorization versions observed when it was created, its authentication method, device metadata, absolute expiration, and optional idle expiration.

Future session validation must reject a session when any of these conditions is true:

- Its status is not active.
- Its absolute expiration has passed.
- Its idle expiration is present and has passed.
- Its recorded credential version differs from the current `UserCredential.credential_version`.
- Its recorded authorization version differs from `User.authorization_version`.

Revocation must set the session status and `revoked_at` transactionally. Revoking or compromising a session invalidates every future refresh operation for that session.

## Access and refresh tokens

Access tokens will be short-lived bearer credentials. ACP Enterprise will not store plaintext access tokens.

Refresh tokens are rotating credentials. Persistence stores only a cryptographic token hash, never the plaintext token. Each token belongs to one session and one family and carries a monotonically assigned sequence number. A successful future rotation will:

1. Lock and validate the presented token and session.
2. Mark the presented token used.
3. Create the next family token with a new hash and sequence number.
4. Link parent and replacement records in the same transaction.

Presentation of an already used token is reuse. Future services must mark `reuse_detected_at`, revoke the token family, mark the associated session compromised, and emit an operational security event. Database constraints prevent duplicate family sequence numbers and self-referential parent or replacement links.

## Password reset

Password-reset requests create historical, expiring token records containing only hashes. A token can be consumed or revoked, but not both. Future services must invalidate all outstanding reset tokens transactionally after a successful reset, increment the credential version, and invalidate older sessions.

## Email verification

Email-verification tokens contain only hashes and are bound to the normalized email captured at issuance. Future services must compare that value with the User's current normalized email before consuming the token. A changed email invalidates the token. A verification token can be consumed or revoked, but not both.

## Authentication and authorization

Authentication proves global User identity; it does not grant Membership, Role, Permission, Company, or Branch access. An authenticated User without an active Membership has no company access.

Session identity and authorization are evaluated separately. Authorization must continue to require both the applicable role-derived Permission and Branch or resource scope.

## Operational security events

`AuthenticationSecurityEvent` records focused security operations such as login failures, account lockouts, token reuse, password-reset activity, verification activity, and session revocation. It may exist without a resolved User for failed identity lookups. It stores no passwords or token material.

This table is not the enterprise Audit platform. It does not record general administrative or business activity, field-level changes, policy decisions, or compliance history. Later Audit integration may reference or project authentication events without replacing their operational security purpose.

## Secret-storage prohibition

ACP Enterprise must never persist plaintext access tokens, refresh tokens, password-reset tokens, email-verification tokens, or passwords. Token hashes and password hashes must use purpose-appropriate cryptographic algorithms selected by the future authentication service. Logs, events, analytics, and error messages must not contain plaintext credential material.

## Authentication service security profile

Passwords use Argon2id through `argon2-cffi`; ACP Enterprise does not implement cryptographic primitives. The initial policy accepts passwords from 12 through 256 characters and rejects blank or whitespace-only values. It intentionally avoids brittle composition requirements. Argon2 parameters are configuration values so encoded hashes can be detected and upgraded after successful verification.

Security tokens contain 32 random bytes generated with Python's `secrets` module and are URL-safe encoded. Database lookup values are deterministic HMAC-SHA-256 hashes produced with a dedicated secret. HMAC key rotation requires a controlled transition strategy—such as multiple verification keys or revocation of outstanding tokens—because existing hashes cannot be located with a replaced key.

Access tokens are short-lived HS256 JWTs with an explicit server-side algorithm allowlist. Required claims are issuer, audience, User subject, Session identifier, issuance, expiration, unique token identifier, credential version, and authorization version. Permission lists, Membership claims, personal profile data, and company-access claims are excluded.

Required signing and HMAC keys must be supplied outside test mode and must contain at least 32 characters. Production secrets belong in the deployment secret manager, must not be committed, and require documented rotation procedures. Local Docker values are development-only and are not production credentials.

## Lockout and rate limiting

The initial credential lockout policy applies a 15-minute temporary lock after five consecutive incorrect passwords. Successful authentication resets the counter. Threshold and duration are configurable.

Authentication endpoints use focused Redis counters for login, refresh, password-reset, and email-verification abuse controls. Redis failure causes authentication safeguards to fail closed with a service-unavailable response. This is not a general API gateway or distributed policy engine.

## Transaction and locking strategy

Credential mutation, login counters and Session creation, refresh rotation, token-reuse compromise handling, logout, password reset, and email verification execute in explicit transactions. Mutable credential, Session, and token rows use PostgreSQL `FOR UPDATE` locking. The refresh token row lock ensures concurrent rotation attempts cannot both succeed; a later attempt observes consumption and triggers family compromise handling.

Security events are staged in the same transaction as their corresponding authentication outcome whenever practical. Failure reasons are controlled identifiers and never arbitrary exceptions or supplied secret material.

## Delivery and browser boundary

No production email provider exists yet. Password-reset and verification services return plaintext tokens once through a development/test delivery boundary. Public recovery responses remain generic regardless of account existence.

For backend development, refresh credentials are returned in JSON response bodies. Production browser integration must move refresh tokens to cookies configured with `Secure`, `HttpOnly`, an appropriate `SameSite` policy, narrow path and domain scope, and CSRF protections. Access and refresh tokens must never appear in URLs.
