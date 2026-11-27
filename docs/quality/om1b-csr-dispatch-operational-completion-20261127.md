# OM1-B CSR and Dispatch operational completion — 2026-11-27

## Authority and isolation

- Consolidated authority observed: `handoff/friday-consolidated-20261127` at
  `7de500f67451ca760d0c9767f8674fbf353d1a95`.
- Application baseline: `integration/friday-consolidated-20261127` at
  `8b6cb1e9e90b2890271cc76601275ebbb29566b2`, a direct successor of that
  authority.
- Candidate branch: `work/om1b-csr-dispatch-operational-completion`.
- Qualification database: local PostgreSQL database
  `om1b_csr_dispatch_20261127`, created solely for this assignment and migrated
  from zero to the candidate schema head.
- All created Company, Branch, Customer, Location, Employee, Appointment, Job,
  and Dispatch records use unique synthetic qualification identities. No
  protected, Preview, provider, HCP, or production record was read or mutated.
- The existing OM1-B supervisor process was not restarted, reconfigured, or
  otherwise altered.

## Operational result

The current integrated product implementation completes the bounded CSR and
Dispatch workflow without an application-source correction:

1. A CSR authenticated session creates an active Customer and primary Service
   Location through the public application APIs.
2. The same session creates a current-business-date Appointment, creates and
   activates its linked Job, and assigns an eligible canonical Technician.
3. A second CSR token, backed by a distinct authentication-session identity,
   searches and reopens the Customer and reads the correct name, Location, Job,
   Appointment, current-date Dispatch item, and persisted assignment.
4. A separately authenticated Technician session reads the same Appointment,
   Job, Customer name, and service address through My Day.
5. A further fresh HTTP client reads the durable Customer, Job detail, linked
   Appointment, and Dispatch assignment without using any mutation response or
   in-memory aggregate.

Customer search is the normal source-neutral search path. Its existing
PostgreSQL trigram indexes and the multi-field search matrix cover Customer
number and name, Contact name/email/phone, and Location address/city/postal
code. The qualification does not claim a production latency SLA; it establishes
correct indexed behavior in the isolated application database.

The added regression is
`backend/tests/operations/test_csr_dispatch_authenticated_flow.py`. It preserves
the real authentication, authorization, branch-access, scheduling-capacity,
workforce-eligibility, Dispatch, and My Day dependencies. The only dependency
overrides provide independent sessions against the isolated database.

## Qualification

- Zero-to-head Alembic migration in the isolated database: **PASS**.
- Focused authenticated CSR → current-date Scheduling → Job → Dispatch → My Day
  persistence flow: **1 passed**.
- Backend Customer, Jobs, Scheduling, Dispatch, My Day, and operational
  regression suite: **236 passed** in 101.71 seconds.
- The backend suite emitted four pre-existing SQLAlchemy transaction-cleanup
  warnings in Dispatch service tests; no tests failed and the new operational
  test emitted no warning.
- Focused frontend Customer, Job, Scheduling, Dispatch, and Technician suite:
  **13 files / 98 tests passed** in 5.99 seconds.
- Ruff for the new operational regression: **PASS**.

## Acceptance boundary and handoff

This is verified synthetic operational qualification, not actual protected All
County acceptance. It does not establish HCP source completeness, protected
Customer-history acceptance, production performance, or a successful deployed
browser run. Owner Acceptance Finding 001 therefore remains outside this
candidate and is not represented as closed.

Laptop Master can integrate the candidate as a single regression/evidence
commit. No schema migration or application runtime source change is required.
After integration, mandatory independent qualification should repeat the
authenticated test against a fresh isolated database and may add a deployed
browser run with separately authorized test identities. No protected Customer
or employee mutation is required for that review.
