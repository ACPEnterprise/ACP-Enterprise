# Identity invitation activation redemption

## Authority and scope

- Protected authority inspected: `ef1f35f250b4e4f4ea2ee4ed04029c5744711882`
- Scope: first-time Employee invitation activation only
- Schema impact: none
- Production/Beta mutation: none

## Root cause

The activation page did not call an API during GET/render, so link scanners,
prefetch, refresh, and repeated passive visits did not consume invitations.
Invitation consumption was already staged in the same transaction as credential
creation and membership activation.

The physical failure message was caused by the error contract around that POST.
`PasswordPolicyError` escaped the onboarding router as an internal failure, and
the browser collapsed every rejected POST (validation, network, and server
failure included) into the same expired/already-used message. A valid pending
invitation could therefore look burned even though its row remained pending.

## Corrected lifecycle

1. Invitation issuance stores only the HMAC token digest; protected delivery
   retains the plaintext only in its encrypted delivery envelope.
2. Passive activation-page visits remain frontend-only and read-only.
3. Password-policy failure returns the safe `validation` / HTTP 422 contract.
   The invitation remains pending and can be retried.
4. Expired, superseded, consumed, revoked, or scope-invalid invitations retain
   the non-enumerating HTTP 409 response.
5. Credential creation, User/Membership activation, invitation consumption,
   protected-envelope destruction, Business Event, and audit evidence commit in
   one transaction. Any failure rolls the complete transaction back.
6. Successful replay fails closed; concurrent redemption has one winner.

## Qualification

- PostgreSQL zero-to-head: PASS
- Identity onboarding, access-log redaction, and URL-edge redaction: 29 passed
- Focused frontend activation: 4 passed
- Frontend ESLint: PASS
- Frontend TypeScript and production build: PASS
- Ruff: PASS
- MyPy for affected onboarding service/router: PASS
- Diff check: PASS

The broader authentication suite reached 35 passing tests and one environment
blocker: its Redis rate-limit integration case requires the unavailable `redis`
service hostname. The failure is fail-closed (`RateLimitUnavailableError`) and
is unrelated to invitation state.

Protected also currently carries a separate known Factory Control authentication
registry drift: four internal controller endpoints are absent from the explicit
non-bearer review list. That is owned by the existing OM1-A Release Security
candidate and is not duplicated in this P0 repair.

## OM1E acceptance

After protected integration and Beta deployment, use a new sanctioned synthetic
FIELD_TECH identity. Open the delivered link twice (or allow an email scanner to
visit it), submit an intentionally too-short password once, then submit a valid
password. Confirm activation succeeds, sign-in establishes the intended Company,
MAIN Branch Membership, and Employee context, and a later link replay fails.

No real password or invitation token belongs in the acceptance record.
