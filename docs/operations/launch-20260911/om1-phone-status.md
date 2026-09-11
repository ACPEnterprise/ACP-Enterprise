# OM1 Phone launch status

Updated: 2026-09-10 America/New_York

## Authority

- Protected base: `42a4f68087d76247269bd4c8388f556dd62a8b5c`
- Mission: `origin/work/launch-20260911-mission`
- Mission commit: `0c08f1e3634f38a7fb82970932dea5de7a4cf24f`
- Mission file SHA-256: `03b74b5f065694b487268bdee531d8d50620f2816f30c91d8b665f9d5b3e9dfc`

## Lianne delivery coordination

OM1 Phone performed a read-only Preview reconciliation using the mission-pinned
invitation and outbox identities. No recipient address or activation material is
recorded here.

The existing onboarding request is `invited`; its invitation is `pending`,
unconsumed, and valid until `2026-09-12T00:32:52.574990+00:00`. The existing
User, invited Membership, active Employee, Company binding, MAIN Branch binding,
owner-selected role, and exact recorded recipient are preserved. The protected
envelope remains recoverable.

The outbox row is terminal `failed` after a definitive Postmark HTTP 422 / code
412 rejection. It has no provider reference and no surviving submitted marker,
so there is no ambiguous provider submission to reconcile before one approved
retry. Preview's identity delivery worker is running.

The owner reports Postmark approved. Enterprise owns the one live Preview retry
and must coordinate the consumer. Current protected authority does not expose an
audited operation that reopens this terminal failed row: the existing recovery
routine applies only to legacy `ambiguous` rows with the exact old safe error code.
Do not directly edit the outbox row, recreate the employee, reissue while the
invitation remains valid, or run a competing consumer. Enterprise should either:

1. use an existing audited operational retry interface not visible in this source
   tree; or
2. integrate and deploy the smallest authorized retry operation that locks this
   exact row, verifies terminal definitive rejection/no provider reference/current
   invitation validity, appends recovery evidence, and schedules the original
   outbox identity once.

OM1 Phone has now prepared option 2 on this branch. The candidate adds a
Preview-only, onboarding-admin endpoint that reopens only the original
`identity.onboarding_invitation` outbox identity after a definitive Postmark 4xx.
It verifies current invited/pending/unexpired state, Company/Branch access, exact
recorded recipient, recoverable envelope, terminal failure, and absence of provider
submission/reference. It appends actor-bound recovery evidence and an audit record.
A durable recovery marker permanently prevents a second administrative retry for
the same outbox identity. It cannot retry ambiguous, accepted, delivered, expired,
consumed, superseded, cross-tenant, cross-Branch, recipient-mismatched, or Production
delivery.

Enterprise action after protected integration and Preview deployment:

1. pause or otherwise coordinate the single identity consumer;
2. invoke `POST /api/v1/identity-onboarding/{request_id}/delivery/retry-definitive-rejection`
   as an authenticated administrator with `IDENTITY_ONBOARDING_MANAGE` and current
   MAIN access;
3. let the existing worker claim the original outbox identity exactly once;
4. record provider MessageID/accepted response separately from webhook delivery and
   human receipt;
5. do not invoke reissue unless the invitation expires before this operation.

After Enterprise executes, record separately: outbox claim, provider submission,
Postmark MessageID/accepted response, webhook delivery if available, human receipt,
activation, and login. Provider acceptance is not human receipt or activation.

## OM1 Phone next work

- Continue isolated fixture qualification for activation expiry/replay/revocation,
  password establishment/login, role refresh, and Mobile required permissions.
- After human activation evidence, verify active Membership and assign/verify
  `ACP_EMPLOYEE_MOBILE` through the sanctioned Administration path while preserving
  the owner's selected role and MAIN Branch.
- Hand Laptop1 Phone the Preview client contract without credentials or activation
  secrets. Physical-device ownership remains Laptop1 Phone.

## Qualification checkpoint

- Postmark `/server`: authenticated HTTP 200; `DeliveryType=Live`. The server
  response does not expose a separate approval flag, so the owner's approval report
  plus the next actual provider response is the accepted verification boundary.
- Preview health and `/activate` page: HTTP 200.
- Frontend activation and Identity Onboarding: 2 suites, 6 tests passed.
- Postmark adapter: 3 tests passed.
- ACP Employee Mobile: 14 suites, 118 tests passed; TypeScript, ESLint, and Preview
  configuration validation passed. Production remains inactive.
- Database-backed onboarding/outbox tests could not run on OM1 because the existing
  test configuration resolves PostgreSQL only inside the container network. They
  were not run against Preview because destructive test fixtures are prohibited.
  A separate provider-only test run passed; the earlier mixed run's database errors
  are environment failures, not asserted product failures.
- Retry candidate: focused Ruff passed, MyPy passed for four changed source files,
  API mutation/idempotency registry 10/10 passed, and 38 database-backed onboarding
  and outbox tests collect successfully. The new database execution test covers
  scheduling, lifecycle constraint state, actor/reason evidence, audit details, and
  second-retry rejection; execution remains an Enterprise isolated-PostgreSQL gate.

Current live role readiness is intentionally not mutated: the owner-selected
`OFFICE_MANAGER` assignment remains, `ACP_EMPLOYEE_MOBILE` exists and contains
exactly the required five permissions, but it is not assigned to the invited
Membership. One of the five permissions is currently effective through the existing
role; My Day, Job execution, and own-Timekeeping permissions remain pending the
post-activation sanctioned role assignment.

## Laptop1 Phone handoff

- Client: existing ACP Employee development client owned by Laptop1 Phone.
- Runtime: Preview, `https://preview.allcountyhomeservices.com`; Production inactive.
- Login identity: Lianne's exact unique onboarding email, delivered privately by the
  owner; never place it or her password in Git/task logs.
- Human sequence: open the single-use invitation, establish her own password, then
  sign in through the ACP Employee login screen. Human receipt, activation, and
  successful login require direct evidence and are currently pending.
- Before My Day/Jobs/Timekeeping acceptance, an authorized administrator must add
  `ACP_EMPLOYEE_MOBILE` to the newly active Membership while preserving
  `OFFICE_MANAGER` and MAIN. Verify all five effective permissions after the
  authorization refresh.
- Physical acceptance remains on Laptop1 Phone. OM1 Phone must not request or move
  the iPhone, alter Laptop1's runtime, or claim a physical pass from automated tests.

No Production, Apple signing/TestFlight, Customer communication, shared password,
or real employee mutation was performed by OM1 Phone in this checkpoint.
