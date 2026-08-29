# Payroll Policy and Compensation Authority

`PAYROLL.POLICY.AUTHORITY.1` separates approved paid-time evidence from the
Company rules and Employee compensation authority that a later Payroll engine
will use. It does not classify time into dollar earnings, calculate Payroll,
approve a Payroll run, settle funds, or post Accounting entries.

## Authority boundaries

- `payroll.time-input.v1` remains the immutable Workday Time evidence contract.
- `payroll.company-policy.v1` is an effective-dated Company authority describing
  pay schedule identity, regular/overtime/double-time dimensions, break and
  leave references, hourly/salaried admission rules, rounding configuration,
  corrections, cutoff, and approval requirements.
- `payroll.compensation-authority.v1` is a separately permissioned,
  effective-dated Employee authority for either hourly or salaried
  compensation. Missing authority is a blocker and is never a zero or default.
- `payroll.calculation-admission.v1` answers whether one Employee/pay-period is
  ready for a future calculation. It performs no wage calculation.

HCP and QBO evidence cannot create compensation authority. Compensation is not
exposed through Timekeeping, general Workforce, Economics, or employee
self-service contracts. A future, separately authorized Payroll-to-Economics
evidence contract may expose approved aggregate cost evidence without granting
general access to compensation authority.

## Lifecycle and replay

Policies and compensation authorities move from draft to explicitly approved,
then may be superseded or retired. The drafter cannot approve the same record.
Approved content has a deterministic authority digest and is not edited in
place. A successor is appended with lineage to its predecessor. Effective-date
resolution is Company-scoped, rejects overlap, and retains prior versions for
historical replay.

The policy points to the versioned Company pay-period schedule already owned by
Timekeeping. No Company schedule is a product default. Synthetic qualification
proves a weekly period from August 29 through September 4, 2026 can reference a
September 10 processing target and September 11 payday without activating any
live configuration.

## Corrections and retroactivity

- Before finalization, corrected approved time requires a newly sealed Time
  Input snapshot before calculation admission.
- After finalization, policy requires a new retroactive-adjustment record in a
  future Payroll result; the finalized evidence is not rewritten.
- After payment, policy requires a new post-payment adjustment in a future
  Payroll lifecycle; neither payment nor historical evidence is rewritten.

Leave, PTO, and holiday entries require their own approved evidence. Policy
references do not manufacture entitlement, balances, or paid leave.

## Admission

Admission is deterministic and fail-closed with these outcomes:

- `READY_FOR_CALCULATION`
- `BLOCKED_IDENTITY`
- `BLOCKED_TIME`
- `BLOCKED_COMPENSATION`
- `BLOCKED_POLICY`
- `BLOCKED_APPROVAL`
- `CONFLICTING`

The eight intended All County workforce identities remain unresolved until an
owner-authorized native Workforce/Identity reconciliation. No names, Employee
records, login links, compensation values, or Production configuration are
created by this milestone.
