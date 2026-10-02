# QuickBooks replacement: prepared seven-working-day board

The seven-day clock has not started. This board is dependency-ready planning,
not a cutover authorization.

| Day | Parallel work | Required exit evidence |
| --- | --- | --- |
| 1 | LPTP1A source custody/COA/company settings; LPTP1B owner usage interview and workflow confirmation; LPTP1C manifest/replay controls | Sealed source package, capability use decisions, no unresolved schema/identity ambiguity |
| 2 | LPTP1A opening/period/equity and GL controls; LPTP1B AR/AP mapping; LPTP1C double-entry/control validators | Accepted mappings, balanced opening proposal, AR/AP control test plan |
| 3 | AR/AP real-data reconciliation; Payroll posting evidence; reporting basis decision | AR/AP ties or explicit quarantines; payroll/accountant disposition; basis fixed |
| 4 | QBO application/review queue; inventory/material/job-cost evidence; report drilldowns | Every unresolved item has disposition, owner, source, and next action |
| 5 | Bank/deposit/reconciliation workflow; period close/reopen; replay and audit | Bank and clearing controls proven or explicit provider/human gate |
| 6 | P&L, Balance Sheet, Cash Flow, TB, GL, aging, job-cost parity; accountant review | Report pack ties to accepted source evidence and is operator-usable |
| 7 | Independent Finance review, owner/Lianne physical workflows, final freeze/reconcile/activate decision | All required rows GREEN, or signed exception/deferral; QuickBooks retirement go/no-go |

## Execution rules

- No real posting, bank reconciliation, money movement, payroll mutation, or
  QBO writeback occurs from this preparation branch.
- A failed control creates a quarantined exception; it is never rounded away or
  converted to zero.
- Independent lanes continue while a provider or owner gate is pending.
- A row cannot be GREEN from code or tests alone.
