# OM1 Phone launch status

Updated: 2026-09-12 America/New_York

## Authority

- Protected base: `4514b5df6be66e50ee172085c622ae613e172086`
- Mission: `origin/work/launch-20260911-mission`
- Mission commit: `0c08f1e3634f38a7fb82970932dea5de7a4cf24f`
- Mission file SHA-256: `03b74b5f065694b487268bdee531d8d50620f2816f30c91d8b665f9d5b3e9dfc`

## Lianne identity and delivery result

The original onboarding, invitation, protected envelope, and outbox identities
were preserved. The audited retry was accepted by Postmark with a provider
reference, while the earlier definitive code-412 rejection and recovery evidence
remain in the delivery history. Provider acceptance is not represented as webhook
delivery or mailbox receipt.

Human login is now owner-reported and corroborated by read-only Preview state: the
invitation is consumed, the onboarding request is activated, a credential exists,
and active sessions exist. The User, Membership, and Employee remain active and
canonically linked. Company and explicit/default Branch authority remain bound to
All County Plumbing & Leak / MAIN. No invitation retry or reissue is now valid.

The active Membership has `ACP_EMPLOYEE_MOBILE` and `OFFICE_MANAGER`. All five
Mobile permissions resolve effectively:

- `COMPANY_TIMEKEEPING_OWN_READ`
- `COMPANY_TIMEKEEPING_OWN_PUNCH`
- `COMPANY_EMPLOYEE_OPERATIONS_OWN_DAY_READ`
- `COMPANY_JOB_READ`
- `COMPANY_JOB_EXECUTE`

No recipient address, activation material, credential, provider reference, or
session token is recorded in this packet.

## Team/Employees bounded repair

The current Add Employee route already presents the ordinary office sequence:
name, email, standard role, Branch, and Send Invite. Custom Company roles remain
assignable through Administration without changing the audited authorization
model.

The Team/Employees detail previously omitted the exact login email, invitation
state, delivery state, and a clear access state. It also calculated Mobile
readiness from three built-in role codes, causing a correctly permissioned custom
`ACP_EMPLOYEE_MOBILE` role to be reported as blocked. This candidate:

- shows email, human-readable role and Branch, invitation, delivery, account,
  employee access, and active/disabled state;
- resolves Branch names instead of displaying Branch UUIDs in the access view;
- keeps provider-accepted distinct from delivered and uncertain;
- computes Mobile readiness from the exact five effective permissions plus active
  User/Membership/Employee and Branch authority.

## Qualification

- Fresh isolated PostgreSQL database migrated from zero to current head.
- Identity onboarding, authentication, and workforce suites: 49/49 passed with
  isolated local PostgreSQL and Redis runtimes.
- Focused workforce projection: 6/6 passed.
- Frontend Team/Employees: 3/3 passed; TypeScript and ESLint passed.
- ACP Employee Mobile: 15 suites / 129 tests passed; TypeScript, ESLint, and
  Preview configuration validation passed.
- Ruff, MyPy, `git diff --check`, and focused secret review passed.
- Mobile remains Expo 57 (`~57.0.19`); no dependency or native-project change.

## Laptop1 Phone handoff

- Client/runtime: existing Laptop1 ACP Employee client against
  `https://preview.allcountyhomeservices.com`; Production remains inactive.
- Identity: Lianne Hernandez using the same unique owner-entered onboarding email;
  do not copy the address or password into Git or operations logs.
- Authority: active `ACP_EMPLOYEE_MOBILE` plus `OFFICE_MANAGER`, MAIN only; all
  five required Mobile permissions are effective.
- Ready contracts: My Day read, Job read/execute, and own Timekeeping read/punch.
  Actual Job visibility still depends on a sanctioned MAIN assignment.
- Remaining physical evidence on Laptop1: confirm My Day loads, confirm an assigned
  Preview Job is visible/executable, and confirm own Timekeeping loads and accepts
  only an explicitly sanctioned Preview punch. Keep these as separate owner-guided
  physical actions.

OM1 Phone did not move or mutate the physical device, alter Laptop1's runtime,
send Customer communication, use Production, sign/upload an Apple build, create a
shared password, execute Payroll, or move money.
