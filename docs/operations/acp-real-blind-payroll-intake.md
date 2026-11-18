# ACP real blind payroll intake

This packet is for one calculation-only historical replay involving exactly three
employees. It must not contain the selected payroll's calculated gross, taxes,
deduction results, net pay, employer taxes, or payroll journal. Those outputs remain
sealed until the TwelveHats result is frozen.

## Period and employee selection

Choose a completed, recent payroll whose inputs can be reconstructed without opening
its paycheck results. Prefer a period in the same tax year as the supported tax table,
with approved timecards and beginning YTD evidence ending immediately before the
period. Avoid off-cycle, amended, voided, corrected, or partial-period payrolls for the
first replay.

Select one hourly technician with overtime or commission, one helper/hourly field
employee, and one salaried manager or office employee. Each must have effective pay,
W-4, jurisdiction, deduction, and opening-YTD evidence.

## Source routing

### A. Auto-collect from TwelveHats or retained source data

| Input | Expected location |
| --- | --- |
| Company and employee IDs; display label; status | TwelveHats Company and Workforce employee records |
| Compensation type, rate, effective start/end | Approved TwelveHats Payroll compensation authority; otherwise retained signed compensation record |
| Regular, overtime, and other paid hours | Sealed TwelveHats timekeeping payroll-input snapshot; otherwise approved historical timecard |
| Commission, bonus, other earnings, reimbursement | Approved TwelveHats earning evidence; otherwise retained commission/expense approval |
| Work and residence state; locality | TwelveHats employee/work-location records; otherwise retained protected employee record |
| Pay-period dates and frequency | TwelveHats pay-period schedule; otherwise retained payroll calendar |
| Evidence digests and source IDs | Generated from each collected source artifact; never owner-entered |

### B. Read from QuickBooks input/configuration without opening the selected paycheck

| Input | Read-only QuickBooks location |
| --- | --- |
| Current/base pay and employment history | **All apps > Team > Employees > employee > Personal > Personal info > View History**; confirm the rate effective during the selected period from retained history |
| W-4 filing status, Steps 2, 3, 4a, 4b, 4c, and withholding exemptions | **All apps > Team > Employees > employee > Job & pay > Tax withholdings > Edit**; view only |
| FICA applicability and state/local withholding configuration | The same employee **Tax withholdings** view and applicable state/local setup; view only |
| Pay types | **All apps > Payroll > Employees > Edit payroll items > Pay types** |
| Deduction/benefit code, amount or percentage, limit, tax treatment, and employer contribution | **All apps > Payroll > Employees > Edit payroll items > Deductions & contributions**, then select the item and employee; or **employee > Job & pay > Deductions & contributions** |
| FUTA/SUTA configuration, state unemployment rate and wage base | Payroll tax setup and the effective agency rate notice retained for the selected period |
| Beginning YTD wage bases and withholding through the immediately preceding paycheck | A read-only **Payroll Details** export ending on the prior pay date, with the selected payroll excluded; alternatively prior pay stubs/payroll reports with YTD amounts |

W-4 elections can therefore be viewed without opening the selected paycheck. Beginning
YTD bases can also be obtained without it by running the Payroll Details report only
through the immediately preceding pay date. The resulting export is an opening-state
input artifact, not the selected payroll answer key.

### C. Owner-supplied only if neither source contains it

No owner typing is planned. If automated collection finds a gap, request only the
specific missing effective-period fact and a source artifact—normally the signed W-4,
approved timecard, signed compensation change, benefit election, commission approval,
expense approval, or state unemployment rate notice. Do not ask the owner to
re-key a report.

## Smallest QuickBooks input-only evidence set

1. Read-only screenshots or protected PDF capture of each selected employee's
   **Job & pay > Tax withholdings** configuration.
2. Export from **Edit payroll items > Pay types** and **Deductions & contributions**
   for only the three employees, including tax treatment and employer contribution.
3. **Payroll Details** export with an end date equal to the paycheck immediately before
   the selected payroll. It supplies opening YTD bases only; exclude the selected pay
   date.
4. Effective-period state unemployment rate/wage-base notice only when the configured
   value is not already retained in TwelveHats evidence.

Do not export or view the selected paycheck detail, Payroll Summary including the
selected pay date, Paycheck History result, Payroll Tax and Wage Summary including the
selected pay date, Total Payroll Cost for the selected payroll, or its accounting
journal until the frozen snapshot exists.

## Import packet

The protected JSON instance must conform to
[`payroll.blind-replay-input.v1`](../../backend/app/payroll/blind_replay.py), contain
exactly three employee objects, and include these sections:

```text
company_id
period_start, period_end, pay_date, pay_frequency
packet_provenance {source_id, effective_date, evidence_digest, authority_classification}
employees[3]
  identity/status
  effective compensation
  hours and variable earnings
  W-4/FICA/jurisdiction configuration
  deductions[] with tax treatment, contribution, and provenance
  opening_ytd with federal/FICA/unemployment/state-local bases and provenance
  FUTA/SUTA rates and bases
  compensation/time/tax/jurisdiction provenance
```

Every applicable zero must be explicit. Missing values are rejected rather than
converted to zero. `authority_classification` must be `VERIFIED` or `SUPPORTED`, and
every evidence digest must be a SHA-256 hex digest. The readiness collector emits only
field presence and exact missing-field names; it does not expose protected values.
