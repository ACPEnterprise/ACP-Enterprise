# 2026 federal Payroll tax reconciliation

## Candidate and method

- Protected base: `d52d117801d72d04e81afac157671c97a941efa0`.
- Provider candidate under test: PR #228 / `46c2976ec722ef44072419e3d6e5ccd24bbd019a`.
- Reconciliation version: `payroll.federal-tax-2026-reconciliation.v1`.
- Oracle: explicit expected values independently worked from IRS Publication
  15-T Worksheet 1A and annual percentage schedules, IRS Publication 15 FICA
  rules, and the SSA 2026 contribution base. Expected values are static test
  evidence; they are not computed by ACP provider code.

## Case ledger

| Case | Official source/version | Expected | ACP | Variance | Result |
| --- | --- | ---: | ---: | ---: | --- |
| Single / ordinary weekly | IRS Publication 15-T (2026) | 78.08 | 78.08 | 0.00 | PASS |
| Married filing jointly / weekly | IRS Publication 15-T (2026) | 96.15 | 96.15 | 0.00 | PASS |
| Head of household / weekly | IRS Publication 15-T (2026) | 93.46 | 93.46 | 0.00 | PASS |
| Step 2 off | IRS Publication 15-T (2026) | 78.08 | 78.08 | 0.00 | PASS |
| Step 2 on | IRS Publication 15-T (2026) | 135.10 | 135.10 | 0.00 | PASS |
| Step 3 annual credits 2,600 | IRS Publication 15-T (2026) | 28.08 | 28.08 | 0.00 | PASS |
| Step 4(a) other income 5,200 | IRS Publication 15-T (2026) | 90.08 | 90.08 | 0.00 | PASS |
| Step 4(b) deductions 5,200 | IRS Publication 15-T (2026) | 66.08 | 66.08 | 0.00 | PASS |
| Step 4(c) extra withholding 25 | IRS Publication 15-T (2026) | 103.08 | 103.08 | 0.00 | PASS |
| Low wages / zero FIT | IRS Publication 15-T (2026) | 0.00 | 0.00 | 0.00 | PASS |
| High wages / top bracket | IRS Publication 15-T (2026) | 6,438.47 | 6,438.47 | 0.00 | PASS |
| Social Security base crossing / employee | IRS Publication 15 (2026); SSA 2026 CBB | 31.00 on 500.00 | 31.00 on 500.00 | 0.00 | PASS |
| Social Security base crossing / employer | IRS Publication 15 (2026); SSA 2026 CBB | 31.00 on 500.00 | 31.00 on 500.00 | 0.00 | PASS |
| Medicare / employee | IRS Publication 15 (2026) | 14.50 | 14.50 | 0.00 | PASS |
| Medicare / employer | IRS Publication 15 (2026) | 14.50 | 14.50 | 0.00 | PASS |
| Additional Medicare threshold crossing | IRS Publication 15 (2026) | 6.75 on 750.00 | 6.75 on 750.00 | 0.00 | PASS |
| Prior Payroll exhausts Social Security base | IRS Publication 15 (2026); SSA 2026 CBB | 0.00 | 0.00 | 0.00 | PASS |
| Prior Payroll reaches Additional Medicare threshold | IRS Publication 15 (2026) | 9.00 | 9.00 | 0.00 | PASS |
| Pre-tax federal wage reduction | IRS Publication 15-T (2026) | 66.08 on 900.00 | 66.08 on 900.00 | 0.00 | PASS |
| Pre-tax FICA reduction / Social Security | IRS Publication 15 (2026) | 55.80 on 900.00 | 55.80 on 900.00 | 0.00 | PASS |
| Pre-tax FICA reduction / Medicare | IRS Publication 15 (2026) | 13.05 on 900.00 | 13.05 on 900.00 | 0.00 | PASS |
| Deterministic half-up minor-unit boundary | IRS Publication 15 (2026) | 62.01 | 62.01 | 0.00 | PASS |
| Florida explicit work/residence jurisdiction | Florida DOR FAQ ID 1466 | NOT_APPLICABLE | NOT_APPLICABLE | 0 | PASS |

The executable result records additionally preserve expected and actual taxable
bases and a digest per case. A deliberately altered expected value proves a
material variance produces `FAIL` rather than being normalized away.

## Real-Employee post-deploy readiness packet

Enterprise may run `build_lianne_readiness_packet()` only after PR #223 and PR
#228 deploy. The packet remains
`BLOCKED_PENDING_AUTHORIZED_REAL_INPUTS` until all of these are true:

1. protected-envelope encryption keys are configured;
2. Lianne is resolved in the authorized Company;
3. her effective 2026 W-4 election is entered and approved;
4. Social Security and Medicare YTD wages, prior-Payroll coverage, and any
   applicable pre-tax deductions are entered and approved;
5. work and residence jurisdiction are explicit and approved; and
6. compensation, accepted time, and the pay period are approved.

Then Enterprise should run the Company-scoped readiness evaluator, require
`READY_FOR_PAYROLL` with no blockers, create a non-transmitting calculation
candidate, reconcile each component to an independent calculation, and retain
source versions, evidence digests, exact variance, and owner review state.

No W-4 election, YTD value, jurisdiction, deduction, or prior-Payroll fact is
present in this packet. Missing information is never treated as zero.

## Remaining bounded readiness gap

Real calculation acceptance is an external deployment/input gate. The next
bounded engineering gap is wiring the provider constructor to PR #223's
protected setup projection after Enterprise integrates both candidates. That
must be reconciled against the exact integrated contract and must not be guessed
on this pre-integration branch.
