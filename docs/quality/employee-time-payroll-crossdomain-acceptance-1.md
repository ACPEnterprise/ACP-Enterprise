# Employee Time and Payroll Cross-Domain Acceptance 1

## Authority and boundary

This packet extends the existing Enterprise operational acceptance factory with the
bounded `employee_time_payroll_crossdomain` scenario. It does not create a second
acceptance harness and does not exercise Payroll payment execution, payment release,
Accounting posting, Preview mutation, or Production.

Starting protected authority: `9ff11122c4591d8738c11164caff829ef72dc729`.
The authority was fetched again at the productive checkpoint and remained unchanged.

## Accepted deterministic chain

The selected authoritative proofs compose:

Employee → User → active Membership → authorized Branch → assigned Job/Appointment →
employee-owned clock-in → active interval → clock-out → Job labor evidence → approved
daily timecard → immutable Payroll Time Input for a pay period → gross calculation →
employee withholding → Payroll reporting/register evidence.

The scenario proves:

- authenticated rejection and Company/Branch isolation;
- authorization-version invalidation and explicit Job management permission;
- own-time identity derivation, no client-selected Employee identity, and no
  self-approval;
- exact punch replay after response loss, contradictory idempotency-key rejection,
  duplicate clock-in rejection, and missing/invalid clock-out rejection;
- overlap rejection, missing worked-time classification without schedule inference,
  and separate Job/Appointment labor provenance;
- immutable correction lineage, approval audit/event evidence, a changed Payroll Time
  Input digest after accepted correction, and preserved predecessor evidence;
- gross-result supersession rather than destructive recalculation, distinct employee
  withholding, and a deterministic active-source Payroll report/register;
- safe API projection for validation, authorization, conflict, and unexpected server
  errors.

## Qualification evidence

- Current Alembic graph upgraded from an empty PostgreSQL database to the single head
  `a1c3e5g7i9k1`.
- Focused factory scenario: 17 passed.
- Bounded related suites (Timekeeping, Payroll, operational measurement, factory,
  Jobs API, authorization): 238 passed.
- Ruff: passed for changed Python files.
- MyPy: passed for changed Python files.
- Python compilation: passed for changed Python files.
- `git diff --check`: passed.

An earlier broad invocation against the already-used focused-test database produced
236 passes and two fixture setup collisions on deterministic synthetic Company codes.
That invocation is not classified as a product failure. The clean-database rerun above
is the qualifying result.

## External operational gate

Repository evidence does not provide this lane a current, sanctioned real Employee
credential plus admitted real worked-time/assignment evidence. The authenticated
operational rerun is therefore `SOURCE_REQUIRED`: execute the same bounded scenario
when OM1 Phone / OM2-A / Laptop1-A publish those facts and Enterprise grants the
appropriate non-production access. Synthetic deterministic preparation is complete.

No product defect was found in the accepted deterministic chain. No migration or
runtime product change was required.

## Protected integration

Integrate the commit from branch
`work/om2c-employee-time-payroll-crossdomain-acceptance-1` onto the then-current
`customer-management-v1` after confirming the branch remains mechanically current.
Enterprise owns any Preview execution or deployment.
