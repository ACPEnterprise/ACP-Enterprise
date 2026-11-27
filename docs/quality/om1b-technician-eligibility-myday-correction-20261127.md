# OM1-B Technician eligibility and My Day correction — 2026-11-27

## Authority and isolation

- Corrective branch: `work/om1b-technician-eligibility-myday-correction`.
- Exact baseline: published CSR handoff
  `fd253be703fe16987e8a5278fa774a9f1c23bb76`.
- Isolated database: local PostgreSQL database
  `om1b_csr_dispatch_20261127`; all qualification identities and business
  records are synthetic and disposable.
- No protected record, provider, deployment, Docker environment, or external
  system was read or mutated.

## Reproduced defect

The bounded field-readiness command created the Workforce profile, canonical
`technician` capability, and availability window, but it did not persist a
`WorkforceBranchEligibility` relationship. It also accepted incomplete
Employee identity state without proving the active login, Membership, effective
`TECHNICIAN` role, or Membership Branch grant that Dispatch and authenticated
My Day consume.

This allowed field-readiness evidence to diverge from the complete
onboarding-to-Dispatch relationship. The prior CSR regression concealed the
gap by manually seeding the Technician, profile, branch eligibility, and
availability instead of exercising managed onboarding and field readiness.

## Correction

`prepare_field_readiness` now performs one atomic transaction that:

1. locks the Company Employee and requires an active Employee, User, and
   Membership;
2. requires an effective, unrevoked active `TECHNICIAN` role at the readiness
   window start;
3. requires all-Branch access, the requested default Branch, or an explicit
   Membership Branch grant;
4. creates or verifies the active Workforce profile and canonical qualified
   `technician` capability;
5. creates or verifies explicit active Workforce Branch eligibility;
6. creates or verifies the exact bounded availability window; and
7. audits the Branch eligibility and availability evidence without returning
   protected credential material.

Missing role or Branch authority fails before any profile, capability, Branch
eligibility, or availability evidence is committed. The response now includes
the durable `branch_eligibility_id`.

The existing authenticated CSR regression now creates the Technician through
the public managed-onboarding API, provisions field readiness through the
public API, verifies Dispatch eligibility, assigns the Technician, reconstructs
the application, and verifies authenticated My Day. It no longer manually
pre-seeds Technician readiness.

## Qualification results

- Focused onboarding → field readiness → eligibility → assignment → My Day:
  **PASS**.
- Fail-closed missing Technician role with no partial profile: **PASS**.
- Fail-closed missing Membership Branch grant with no partial profile:
  **PASS**.
- Relevant backend Customer, Jobs, Scheduling, Dispatch, Employee Operations,
  Workforce, onboarding, and operational suite: **464 passed** in 86.93
  seconds.
- Backend warnings: seven pre-existing SQLAlchemy outer-transaction cleanup
  warnings; no failures.
- Focused frontend Customer, Job, Scheduling, Dispatch, and Technician suite:
  **14 files / 98 tests passed** in 8.32 seconds.
- Ruff, JavaScript syntax, and whitespace checks: **PASS**.
- Live local runtime, authenticated Technician session 1: login **200** and
  current-date itinerary **200**, returning `APT-000001`, `JOB-000001`, and the
  assigned synthetic Customer.
- Backend process stop/start followed by independent authenticated Technician
  session 2: login **200** and the same persisted itinerary **200**.

## Browser qualification boundary

The secret-free browser harness is
`frontend/tests/technician-my-day-real-browser.mjs`. It creates a fresh Chrome
profile, authenticates through the rendered login form, opens `/technician`,
rejects the empty state, verifies the Technician, Customer, Appointment, and
Job, and records a screenshot digest without writing credentials to evidence.

The Codex-launched installed Chrome 158 process aborted with exit status 134
before opening its DevTools endpoint. No browser request reached the
application. Therefore real-browser acceptance is **not passed in this
session**, and the successful authenticated HTTP/runtime proof is not
represented as browser proof.

Laptop Reviewer can run the harness from a normal host Terminal against the
isolated runtime using a mode-0600 synthetic credential file and a secret-free
receipt file:

```text
OM1B_SERVING_SHA=<candidate-sha> node frontend/tests/technician-my-day-real-browser.mjs <frontend-url> <credential-file> <receipt-file> <output-json> initial
```

Restart the backend process, then repeat with phase `after-restart` and a new
debugging port. Mandatory independent browser qualification remains open until
both outputs pass.

## Acceptance boundary

This is synthetic isolated qualification, not protected All County acceptance.
It does not close Owner Acceptance Finding 001 and does not authorize
production claims, deployment, provider writes, or protected business-record
mutation.
