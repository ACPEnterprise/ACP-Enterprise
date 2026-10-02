# Pre-sprint owner and accountant queue

Only human/external actions are listed here; engineering tasks remain on the
day board.

| Priority | Required action | Why engineering cannot do it | Affected closure | Expected time |
| --- | --- | --- | --- | ---: |
| P0 | Authorize read-only QBO realm/company connection and sealed export | Requires owner/provider credentials and source authority | Source custody, all reconciliation | 30–60 min |
| P0 | Confirm All County QuickBooks workflows actually used, including recurring transactions, fixed assets, 1099, inventory valuation, and cash flow | Usage/policy cannot be inferred from code | Parity classification | 45 min |
| P0 | Accountant approves basis, cutoff date/timezone, COA mappings, opening equity, and period policy | Accounting policy and certification are human decisions | Opening state and reporting | 60–90 min |
| P0 | Accountant supplies/approves AR, AP, bank, payroll, inventory, tax, and liability control reports | Real accounting evidence is unavailable to engineering | Control reconciliation | 90 min |
| P0 | Owner/accountant perform physical operator workflows and independent go/no-go | GREEN requires real acceptance | Final replacement closure | 2–4 hr |

Engineering resumes immediately after each accepted input with deterministic
reconciliation, UI tie-outs, and exception closure.
