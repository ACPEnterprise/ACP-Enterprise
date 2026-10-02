# QuickBooks replacement pre-sprint parity matrix

Observed protected authority: `290ad8119951412237df640f6003ecc3f3d08ada`.

The complete machine-readable matrix is
[`qbo-presprint-parity-matrix.json`](./qbo-presprint-parity-matrix.json). It
contains the required fields: domain, capability, All County evidence, ACP
state, status, gap, dependencies, size, acceptance test, owner/accountant/
external actions, recommended day, and lane.

Counts are deliberately conservative:

| Status | Count | Meaning |
| --- | ---: | --- |
| GREEN | 0 | No physical/operator proof was available in this repository sweep. |
| YELLOW | 19 | Implemented or partially present, but incomplete or unaccepted. |
| RED | 6 | Missing or materially deficient for replacement. |
| N/A | 1 | Recurring transactions usage requires explicit owner classification. |

## Human-readable control view

| Domain | QuickBooks workflow | Evidence/state | Status | Blocking gap | Day / lane |
| --- | --- | --- | --- | --- | --- |
| Accounting | COA, GL, journals, periods, opening equity | Contracts, migrations, and cutover packets exist; real proof absent | YELLOW | Real exports, mappings, opening tie-out | 1–2 / LPTP1A |
| AR | Invoices, credits, receipts, applications, aging | Invoice/payment authority and reports exist | YELLOW | AR control and QBO open-item tie | 3–4 / LPTP1A/B |
| AP | Vendors, bills, credits, payments, aging | AP packet and Purchasing seams exist | YELLOW | Real vendor population and AP tie | 3–4 / LPTP1A |
| Banking | Feed, matching, categorization, transfers | Provider-neutral controls qualified; no accepted All County source | YELLOW | Connector/statement, operator workflow, matching policy | 1 / LPTP1A |
| Banking | Reconciliation and statement close | Sanitized zero-difference/review controls qualified; no real statement | YELLOW | Operator workflow, accountant policy, physical proof | 5 / LPTP1A |
| Cash | Deposits and undeposited funds | Payment/deposit contracts exist | RED | Clearing and settlement proof | 5 / LPTP1C |
| Inventory | Valuation and GL control | Operational inventory exists; valuation unaccepted | RED | Quantity, cost basis, control tie | 4 / LPTP1A |
| Payroll | Payroll posting and liabilities | Payroll authority exists; cutover proof absent | YELLOW | Period/liability/tax tie | 3 / LPTP1A |
| Jobs | Job costing/profitability | Luminary reports incomplete actual cost population | RED | Authoritative labor/material cost | 4 / LPTP1E |
| Fixed assets | Register/depreciation/disposal | Required by exit contract; runtime evidence absent | RED | Owner scope and asset register | 1 / LPTP1A |
| Tax | Sales tax, payroll tax, 1099 | Tax contracts exist; accounting parity unproven | RED | Jurisdiction and filing workpaper | 6 / LPTP1A |
| Audit | Source, evidence, attachments, lineage | Strong source envelope/review contracts | YELLOW | Real package and retention proof | 6 / LPTP1C |
| Reporting | P&L, Balance Sheet, TB, GL | Read-only routes exist; QBO basis issues remain | YELLOW | Real report tie-out and basis approval | 6 / LPTP1B |
| Reporting | Cash Flow | Provider-neutral tie/classification controls qualified; no accepted real source | YELLOW | Report route/UI, classifications, accountant tie-out | 6 / LPTP1B |
| Operations | Accountant review and close | Review-resolution workflow exists | YELLOW | Physical accountant closure | 7 / LPTP1C |
| QBO | Read-only acquisition/custody | Provider-neutral machinery exists | YELLOW | Real realm, credentials, sealed package | 1 / LPTP1A |
| QBO | Native application/review | Application ledger and quarantine exist | YELLOW | Real evidence and accountant queue closure | 4 / LPTP1C |
| Cutover | Freeze, reconcile, activate, retire QBO | Contract only; failed cutover remains open | RED | All parity and independent go/no-go | 7 / LPTP1E |

No row is GREEN. “Implemented” means only that a contract or bounded runtime
was found; it is not an assertion of All County parity.
