# Identity / Mobile integration wave preflight

Refreshed: 2026-09-12 (America/New_York)

## Protected authority and candidate disposition

Protected authority inspected: `origin/customer-management-v1` at
`d4eee6f6b0bc178d58654f26f3ef2b9429332ab3`.

| Candidate | Exact head | Classification | Mechanical disposition |
| --- | --- | --- | --- |
| PR #227 — Team / Employees status UX | `735852684550ff9cf3737cc6dc520f80cf0bf993` | `SUPERSEDED` | Not in protected, but its exact commit is already a parent of PR #244. Do not merge it separately; close it after #244 integrates. |
| PR #230 — Employee operations/navigation | `f48a1233299232c7a4fe508cfa8541f9650fa547` | `RECONCILE_REQUIRED` | Its navigation corrections remain useful, but the branch is behind protected and conflicts in `PayrollRoute.tsx` with protected Employee Setup (#235). Reapply only its seven-file navigation patch after #244, preserving `PayrollEmployeeSetup`. |
| PR #244 — audited password recovery delivery | `8e1f4445b7d57115ec3f8849213b0d640f99f9f4` | `READY_TO_INTEGRATE` | Clean against current protected, contains #227, and is caught up through `d4eee6f6`. Integrate once; do not merge #227 first. |

Protected successors already present and retained: simplified onboarding and Postmark
identity delivery (#189–#202), humanized Membership role selection (#213), authoritative
timekeeping recovery (#216), and Employee Payroll Setup (#235). None supersedes #244.
Employee Payroll Setup partially supersedes #230's original Payroll presentation and is
the reason #230 must be reduced to navigation-only reconciliation.

## Required order

1. Integrate PR #244. This lands Team/Employee status truth (#227) and password-reset
   delivery together without duplicating #227.
2. From the resulting protected head, create a bounded #230 successor containing only:
   `/administration/identity-onboarding` → `/employees`, selected Employee preservation,
   `/employees?...#timecard-...`, and `/payroll?employee=...#payroll-employee-...`.
   Keep the protected `PayrollEmployeeSetup` projection and tests.
3. Deploy that integrated wave to Preview under Enterprise change control.
4. Run sanctioned synthetic password-reset acceptance.
5. Run forced-password-reset compatibility, then login/session acceptance.
6. Requalify Mobile authorization, My Day, own Timekeeping, and assigned Job access.
7. Return physical-device confirmation to Laptop1 Phone; OM1 does not take the device.

No later candidate uses a stale auth contract: Mobile still calls
`POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`, and the current authorization
context. Credential and authorization versions reject stale sessions server-side. PR #244
extends recovery without changing login/refresh response schemas or the five base Mobile
permission codes.

## Exact qualification commands

Run in a fresh integration worktree with admitted local test PostgreSQL/Redis and existing
locked dependency targets. Supply secrets through protected environment/file injection;
never place them on the command line or in captured output.

```bash
git fetch origin customer-management-v1
git merge-base --is-ancestor origin/customer-management-v1 HEAD
git diff --check origin/customer-management-v1...HEAD

cd backend
alembic upgrade head
pytest -q tests/platform/test_password_reset_delivery.py \
  tests/platform/test_api_idempotency_standard.py \
  tests/platform/test_authentication_services.py \
  tests/platform/test_identity_administration_service.py \
  tests/platform/test_identity_onboarding.py \
  tests/platform/test_notification_outbox.py \
  tests/communications/test_transactional_delivery.py \
  tests/communications/test_postmark_identity_provider.py \
  tests/workforce/test_operations_projection.py
ruff check app/platform/auth/recovery_delivery.py app/communications/identity_worker.py \
  app/platform/users/identity_router.py tests/platform/test_password_reset_delivery.py
mypy app/platform/auth/recovery_delivery.py app/communications/identity_worker.py \
  app/platform/users/identity_router.py app/workforce/employee_administration.py

cd ../frontend
npm test -- --run
npx tsc --noEmit
npm run lint
npm run build

cd ../mobile
npm test -- --runInBand
npm run typecheck
npm run lint
EXPO_PUBLIC_APP_ENV=preview \
EXPO_PUBLIC_API_BASE_URL=https://preview.allcountyhomeservices.com \
  npm run config:validate
```

Preflight evidence on protected authority: Mobile 15 suites / 131 tests passed;
TypeScript, ESLint, and Preview configuration passed. Production remained inactive.
Laptop1 branch `work/laptop1-phone-20260912` changes distribution/Apple artifacts only;
it does not replace identity or field-operation contracts.

## Preview reset acceptance — sanctioned identity only

Use one dedicated non-Production Employee whose User, active Membership, active Employee,
MAIN Branch grant, unique login email, and test-only ownership are pre-recorded. It must
not be Lianne and must not reuse an owner identity. Required operator permission is
`COMPANY_ADMINISTER`.

Before email authorization, Enterprise may deploy and verify the eligible operator action,
one outbox row, encrypted envelope persistence, audit metadata, and absence of plaintext.
Stop before the identity worker submits the message. After the owner explicitly approves
the sanctioned recipient, complete this sequence:

1. Establish a session for the sanctioned Employee and record only its opaque session ID.
2. Employee detail → Account Access must show **Send Password Reset** only while User,
   Membership, Employee, Company, home Branch, and Branch access are active.
3. Send once. Assert one `identity.password_reset` outbox row and one protected envelope.
   Repeat before terminal state and assert the same token ID/outbox ID; do not decrypt or
   display the token.
4. Assert outbox payload contains only `password_reset_token_id` and
   `protected_envelope`; audit details contain Employee/outbox IDs only; logs contain no
   URL query token, token hash, ciphertext, password, or provider credential.
5. Assert `RESET_PENDING_DELIVERY` before submission. Provider acceptance must become
   `RESET_ACCEPTED_BY_PROVIDER`, never `RESET_DELIVERED`, until authenticated provider
   delivery evidence produces `sent`.
6. For a definitive provider rejection, preserve failed evidence and reissue once through
   the same recovery action. Assert the failed outbox remains and exactly one new active
   token/outbox exists. Do not retry an ambiguous submission.
7. In an isolated synthetic case, expire the token and assert reset confirmation rejects
   it. Consume a fresh token once and assert replay rejects it.
8. For forced-reset compatibility, set the existing audited forced-password-reset state,
   confirm the old session is rejected, deliver through the same reset path, and assert the
   forced state clears only after a policy-compliant password is committed.
9. Assert all sessions that predate successful reset are revoked. Fresh login with the new
   employee-owned password succeeds; Company, MAIN Branch, roles, and permissions are
   unchanged.

Safe read-only evidence columns: outbox ID/type/status/retry count/timestamps,
`provider_reference IS NOT NULL`, token ID/issued/expiry/consumed/revoked timestamps,
envelope status and `octet_length(ciphertext)`, and audit action/resource IDs. Never select
recipient, ciphertext bytes, token hash, provider reference value, or message bodies into
operator evidence.

## Lianne preservation

Treat the previously corroborated Lianne state as protected acceptance truth: active
User/Membership/Employee, MAIN Branch, existing roles and effective Mobile permissions,
consumed invitation, and working login. This preflight performs no Preview mutation and
does not independently reassert live database state. Do not create an identity, invitation,
reset request, or password for Lianne. Any Lianne reset requires a new explicit owner choice.

## Mobile acceptance handoff

After synthetic reset acceptance, verify without changing the Laptop1 release candidate:

- login succeeds and disabled User/Membership login or authorization is rejected;
- expired access uses refresh-token rotation; credential/authorization version changes
  force refresh or reauthentication;
- `COMPANY_EMPLOYEE_OPERATIONS_OWN_DAY_READ` exposes My Day;
- `COMPANY_TIMEKEEPING_OWN_READ` and `COMPANY_TIMEKEEPING_OWN_PUNCH` expose only the
  Employee's timecard and punch operations;
- `COMPANY_JOB_READ` and `COMPANY_JOB_EXECUTE` expose assigned Job read/execution under
  current Branch/assignment authority;
- reset is performed in the secure web route; Mobile holds no reset token or alternate
  communications path, and fresh credentials work in the unchanged Mobile login client.

Laptop1 retains physical-device ownership. Remaining human evidence: Enterprise merge and
Preview deployment authorization, sanctioned reset-recipient approval, actual provider and
mailbox delivery, employee-owned password entry, fresh login, and Laptop1 physical checks.
No Production, general Customer mail, Payroll execution, money movement, Apple signing, or
TestFlight is authorized by this packet.
