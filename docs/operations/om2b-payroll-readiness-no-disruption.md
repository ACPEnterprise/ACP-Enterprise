# Payroll readiness without current-week disruption

Date: 2026-11-27  
Scope: isolated synthetic qualification only

This week's Payroll remains in Lianne's existing spreadsheet process. This work does
not submit Payroll, move funds, post Accounting, call a provider, or change protected
Employee compensation.

## Finding disposition

- **Missing pay period:** configuration gap. Create the period through Payroll
  Administration before assembling a run; no period is inferred.
- **Zero projection items:** corrected. Expected `GROSS_PAY_NOT_CALCULATED` and
  `WITHHOLDING_NOT_CALCULATED` states no longer prevent assembling the Employee
  population into the pending-calculation projection. Setup, employment, policy, and
  accepted-time exceptions still fail closed.
- **Approval conflict:** corrected. The user who accepted the Payroll review cannot
  approve that run, even if accidentally granted approval permission. A different
  user with `COMPANY_PAYROLL_RUN_APPROVE` is required and a conflict is returned
  explicitly.
- **Close/seal 422:** the UI now has regression evidence that Close supplies a fresh,
  non-empty idempotency identity. The API continues to reject a missing identity.
- **Separate approver:** enforced in the service, not merely described in the UI.

## Concise setup checklist for next week

1. Create the intended current pay period (start, end, processing date, pay date, and
   weekly schedule) in Payroll Administration.
2. Confirm the approved Company Payroll policy covers that period.
3. For every included Employee, approve effective compensation and authorized
   commission/additional-earning types; enter W-4, Florida work/residence jurisdiction,
   deductions or explicit N/A, and opening/YTD wage and withholding evidence.
4. Submit and supervisor-approve all current timecards and resolve corrections.
5. Assign two distinct authorized people: one Payroll reviewer and one Payroll
   approver. The accepted reviewer cannot approve the same run.
6. Assemble, calculate, review, accept review, approve, and close. Keep payment,
   filing, Accounting posting, and provider execution disabled until separately
   authorized.

## Synthetic qualification evidence

- Payroll calculation/finalization suite: 43 passed. Covered regular/overtime gross,
  authorized additional earnings/commissions, withholding, employee/employer taxes,
  fixed and percentage deductions with caps and priorities, gross-to-net totals,
  2026 federal withholding, Social Security wage-base crossing, Additional Medicare
  threshold, negative-YTD rejection, immutable run review, separate approval, and safe
  downstream handoff.
- Frontend Payroll route: 13 passed. Covered pay-period setup, non-empty pending
  projection, review/accept/approve controls, and idempotent Close invocation.

These results are synthetic qualification, not actual All County operational or
protected Payroll acceptance. Real readiness remains blocked until the checklist's
protected configuration is entered and reconciled against an independently accepted
reference Payroll.
