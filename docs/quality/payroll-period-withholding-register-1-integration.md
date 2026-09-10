# Payroll period, withholding, and operating register integration

## Authority and boundary

- Starting protected authority: `9ff11122c4591d8738c11164caff829ef72dc729`.
- Branch: `work/payroll-period-withholding-register-1`.
- This change projects existing Payroll policy, gross-pay, tax/deduction,
  pay-period, run, and reporting authority. It does not replace those engines.
- Qualification used synthetic identities and inputs only. No direct deposit,
  ACH, provider submission, tax filing/payment, Accounting posting, Preview
  deployment, Production action, or real Employee mutation occurred.

## Sequential milestone result

### PAYROLL.PERIOD.REVIEW.1

The operating register exposes the authoritative period start/end, processing
date, payday, admitted Employee population, accepted-time minutes, regular and
overtime minutes, compensation evidence identity, exceptions, run lifecycle,
and review state. Missing real inputs remain `BLOCKED_FOR_PAYROLL`; unavailable
values are not rendered as zero.

### PAYROLL.WITHHOLDING.CALCULATION.1

The existing effective-dated calculation authority remains canonical. The
register projects its versioned component evidence, including employee
withholdings/payroll taxes, deductions, employer taxes/contributions, gross,
net, money version, rule/calculation version, and immutable calculation digest.
Unchanged evidence/configuration retains the existing deterministic digest.

The repository supports component-neutral federal, Social Security, Medicare,
Additional Medicare, state/local, deduction, and employer-liability
instructions when approved effective-dated authority exists. It does not carry
current real Employee elections or an admitted production tax-rule provider;
those Employees must remain blocked with the exact missing authority key.

### PAYROLL.OPERATING.REGISTER.1

`GET /api/v1/payroll/operations/registers` is Company-scoped and protected by
`COMPANY_PAYROLL_REPORTING_READ`. The owner UI shows Employee, accepted and
regular/overtime time, compensation provenance, gross, aggregate employee tax,
deductions, net pay, employer liabilities, exact blockers, and review state.
It also provides period totals suitable for owner manual filing/payment.

Job labor allocation remains
`UNAVAILABLE_NO_AUTHORITATIVE_JOB_ALLOCATION`: paid-time authority is
intentionally separate from Job participation, and no unsupported allocation
was invented.

## Persistence

Migration `c2e4g6i8k0m2` adds non-null JSONB `blocker_codes` to
`payroll_run_members`, defaulting existing records to an empty list. New blocked
members persist the exact safe admission blocker codes already bound by the
admission evidence digest. No protected election values are exposed.

## Qualification

- Fresh PostgreSQL migration from base through `c2e4g6i8k0m2`: passed.
- Full Payroll backend suite: 106 passed.
- Focused period/calculation/register/reporting/API suite: 42 passed.
- Frontend Payroll route: 3 passed.
- Frontend production build and TypeScript: passed.
- ESLint, Ruff, MyPy, Python compilation, and `git diff --check`: passed.

## Real operating gates

- Confirm the real active Employee population and effective pay period.
- Admit approved effective-dated compensation/rate authority for every Employee.
- Admit accepted time evidence and resolve time exceptions.
- Securely admit each Employee's federal/state/local elections and applicability.
- Admit production tax tables/rules and version identity for the applicable date
  and jurisdictions.
- Admit configured Employee deductions and employer liabilities, or explicit
  approved `not_applicable` authority.
- Define authoritative Job labor allocation evidence if required.
- Complete owner review/approval. Filing and payment remain manual and outside
  ACP execution authority.

Enterprise should integrate against then-current protected authority, apply the
single migration, and rerun Payroll/backend/frontend intersections. No deployment
is authorized from this lane.
