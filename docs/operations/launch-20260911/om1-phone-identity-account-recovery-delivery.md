# OM1 Phone — Identity Account Recovery Delivery

Date: 2026-09-12

## Candidate

- Branch: `work/om1-phone-identity-account-recovery-delivery-1`
- Protected authority reconciled: `origin/customer-management-v1`
- Dependency: PR #227 (`work/om1-phone-team-status-ux-1`), merged as a parent without amendment
- Scope: Preview-capable identity delivery only; no Production, Customer communication, Payroll execution, money movement, Apple signing, or TestFlight

## Behavior

- Eligible active employees can request password recovery through the public login surface.
- Authorized Company administrators can use Employee → Account Access → Send Password Reset.
- One active reset token maps to one Company-scoped outbox identity. Repeated requests reuse it.
- Reset material is AES-GCM encrypted at rest and decrypted only by the existing identity Postmark worker.
- Outbox payloads, API responses, audit details, UI state, and provider evidence never contain the raw token.
- Provider acceptance and confirmed delivery remain distinct states.
- Terminal failure or expiry permits an audited reissue while preserving the prior token/outbox history.
- Reset completion retains the existing password policy, forced-reset clearing, replay rejection, and all-session revocation contract.

## Operator states

`RESET_NOT_REQUESTED`, `RESET_PENDING_DELIVERY`, `RESET_ACCEPTED_BY_PROVIDER`,
`RESET_DELIVERED`, `RESET_FAILED`, `RESET_UNCERTAIN`, `RESET_EXPIRED`, and
`RESET_CONSUMED`.

## Enterprise acceptance

1. Apply the migration and confirm a single Alembic head.
2. In Preview, open an active Employee with active User, Membership, Employee, and authorized Branch linkage.
3. Select **Send Password Reset** and confirm the status initially reports pending/provider accepted—not delivered—until provider delivery evidence arrives.
4. Confirm the employee receives the identity-only message and the URL targets the configured Preview activation origin at `/reset-password`.
5. Establish a compliant new password and verify the token cannot be replayed.
6. Verify pre-reset sessions are rejected and fresh login succeeds with unchanged Company, Branch, role, and permission authority.
7. Exercise a provider rejection and confirm retry/reissue preserves failed-attempt history without creating a duplicate active token.

No mailbox receipt or deployed Preview behavior is claimed by this engineering packet.
