# Password reset redemption release handoff

## Scope

`IDENTITY.PASSWORD.RESET.REDEMPTION.1` repairs the owner-observed password-reset
failure presentation and hardens redemption eligibility. It does not deploy or
mutate Beta or Production data.

## Root cause and evidence boundary

The reset page treated every confirmation failure as an expired, used, or
unavailable token. The API already returns password-policy failures as HTTP 422,
terminal token failures as HTTP 400, and unexpected failures separately. The UI
discarded that distinction, so the physical message does not prove the real token
was expired or consumed. Establishing that token's persisted state requires
sanctioned Beta evidence; no token value is needed or recorded here.

Passive link visits are read-only: rendering or reloading the reset route issues
no reset-confirmation request. Token consumption occurs only in the credential
update transaction after password validation succeeds.

## Corrected lifecycle

- HTTP 422 gives actionable password-policy guidance and explicitly preserves
  same-link retry.
- HTTP 400 retains the terminal expired/used/unavailable response.
- transport, server, and other failures no longer claim the token was consumed.
- redemption locks and validates the token and active User, updates the
  credential and credential version, consumes the token, revokes other reset
  tokens and prior sessions/refresh tokens, and stages the security event in one
  transaction.
- an inactive or archived User cannot redeem a token issued before the status
  change; rejection does not consume the token.

## Qualification

- Fresh PostgreSQL zero-to-head migration: PASS.
- Focused backend auth, API-boundary, delivery, access-log-minimization, and URL
  redaction suites: 19 passed.
- Backend Ruff: PASS.
- Backend MyPy for the changed authentication service: PASS.
- Backend authentication module compilation: PASS.
- Password reset frontend tests: 5 passed.
- Frontend ESLint, TypeScript, and production build: PASS.
- Frontend dependency install audit: 0 vulnerabilities.

Coverage includes valid redemption, invalid-password retry with the same token,
two passive/scanner-style visits before redemption, expiration, supersession,
consumed-token replay, concurrent redemption with exactly one winner, inactive
User rejection, old-session/refresh-token revocation, new-password login, and
old-password rejection.

## Beta acceptance

After protected integration and Beta deployment, repeat the physical flow with
an isolated test identity: request reset, visit the link, submit an intentionally
noncompliant password, verify actionable guidance, submit a compliant password
using the same link, sign in with the new password, verify the old password and
old session fail, then verify link replay fails.

No password or reset token may be captured in the acceptance evidence.
