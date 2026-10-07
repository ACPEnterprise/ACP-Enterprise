# QBO Payroll history acquisition and Lianne packet

Authority reviewed: protected `643eb690e1efc1288debb5d3b9d690435a164018` on
2026-10-06. This is a read-only acquisition packet. It does not run Payroll,
issue checks, write QBO, post Accounting, or move money.

## Machine finding

The current Twelve Hats QBO adapter uses the QuickBooks Online Accounting scope.
It can acquire `Employee`, `TimeActivity`, `JournalEntry`, `TaxPayment`, and
`Account` evidence when those records exist. These records can support identity
candidates and accounting reconciliation, but they do not constitute detailed
Payroll history. The adapter has no Payroll-run, paycheck, employee-tax,
deduction, contribution, or employee-YTD entity contract.

The current worker runtime has no mounted protected QBO evidence root, verified
realm, or sanctioned Production token reference. Therefore no additional real
acquisition was attempted. The protected connection packet also remains
`OWNER_CONFIGURATION_REQUIRED`.

Intuit's current report catalog names the necessary Payroll reports, and Intuit
documents that Payroll Summary is based on paycheck dates rather than pay-period
dates. That means Payroll Summary alone cannot establish the bridge cutoff. Seal
both `Payroll Details` and `Paycheck List`, retaining their date filters and raw
exports. Sources:

- <https://quickbooks.intuit.com/learn-support/en-us/payroll-reports/modify-payroll-summary-report/00/370041>
- <https://quickbooks.intuit.com/learn-support/en-us/help-article/purchase-orders/reports-included-quickbooks-online-subscription/L0s4KrGgr_US_en_US>
- <https://quickbooks.intuit.com/learn-support/en-us/help-article/list-management/export-reports-lists-data-quickbooks-online/L1xleDrLp_US_en_US>

## Capability classification

| Evidence family | Classification | Accounting API evidence | Required stronger evidence |
| --- | --- | --- | --- |
| Employee identity | API_AVAILABLE; sealed population not mounted | `Employee` provider ID/version | Employee Details export plus owner-approved exact provider-ID crosswalk |
| Runs, periods, pay dates | EXTERNAL_EXPORT_REQUIRED | none | Payroll Details and Paycheck List |
| Paychecks/payment method/check number | EXTERNAL_EXPORT_REQUIRED | booked transactions are reconciliation-only | Payroll Details and Paycheck List |
| Hours, earnings, gross, net | EXTERNAL_EXPORT_REQUIRED | `TimeActivity` is not accepted Payroll time | Payroll Details; Payroll Summary by Employee |
| Employee/employer taxes | EXTERNAL_EXPORT_REQUIRED | aggregate journal/tax-payment evidence only | Payroll Details; Payroll Tax and Wage Summary |
| Deductions/contributions/reimbursements | EXTERNAL_EXPORT_REQUIRED | aggregate journal evidence only | Payroll Details; Payroll Deductions/Contributions |
| Liabilities/remittances | EXTERNAL_EXPORT_REQUIRED | Account, JournalEntry, TaxPayment reconciliation evidence | Payroll Tax Liability; Payroll Tax Payments; settlement confirmations |
| Employee YTD | EXTERNAL_EXPORT_REQUIRED | unavailable as Employee Payroll authority | Payroll Summary by Employee; Payroll Tax and Wage Summary; Payroll Deductions/Contributions |
| Voids/reversals/off-cycle | EXTERNAL_EXPORT_REQUIRED | booked effects may be partial | Payroll Details and Paycheck List, including voided/off-cycle rows |
| Post-QBO bridge/final checks | MANUAL_EVIDENCE_REQUIRED | outside QBO Payroll | physical Payroll/check/time/tax evidence |

## Exact packet Lianne should gather

Export the following from the exact All County QuickBooks company. Use the full
available historical range through the last completed QBO Payroll, and retain
the unmodified Excel/CSV/PDF files:

1. **Payroll Details** — all Employees; include every paycheck, void, reversal,
   and off-cycle run.
2. **Paycheck List** — all Employees and payment methods/check references.
3. **Payroll Summary by Employee** — full available history and current-year
   range separately.
4. **Payroll Deductions/Contributions** — full history and current YTD.
5. **Payroll Tax and Wage Summary** — current YTD and every relevant prior year.
6. **Payroll Tax Liability** — through the exact final QBO pay date.
7. **Payroll Tax Payments** — through the same cutoff.
8. **Employee Details** — identity support only; protected tax/bank values stay
   in restricted custody.

For every export, record the report name, exact filters/date range, realm/company,
export timestamp, row/page completeness, and original-file SHA-256. Do not edit
the original before sealing it.

Also gather physical evidence for the post-QBO period: pay stubs, check register,
accepted timecards, check images/numbers, tax worksheets, liability/remittance
confirmations, deductions/contributions, reimbursements, and corrections.

## Cutoff, crosswalk, bridge, and YTD

The last QBO Payroll cutoff is currently `UNAVAILABLE`. It becomes provable only
after Payroll Details and Paycheck List identify the same last completed run,
period start/end, pay date, and Employee population. The bridge cannot be dated
until then.

All nine identities remain unbound to QBO Payroll provider IDs in this runtime.
Malcolm Calci's active Helper status is owner-confirmed, but that permits binding
only after one unique authoritative QBO Employee ID and one unique ACP Employee
ID are proven. Names alone never bind.

Dareis Montgomery and Kamen Wilmington each have two unpopulated future
paper-check evidence slots. They remain historical/terminated, and their slots
cannot reactivate employment, User, Membership, Mobile, or Dispatch state.

For each Employee, final reconciliation remains:

`sealed QBO Employee YTD + certified bridge + recorded final checks = ACP YTD`

Source YTD, bridge entered, final checks entered, ACP YTD, difference, and
certification remain unavailable—not zero—until their evidence is admitted.

## Accountant handoff

Accountant Close requires exact Employee identity, approved runs, approved account
mappings, journal/GL lines, liabilities, settlements/remittances, opening/YTD,
cutoff, source lineage, and certification. The exports above establish source
evidence; they do not certify or post it.
