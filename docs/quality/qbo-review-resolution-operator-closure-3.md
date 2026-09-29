# QBO review resolution operator closure 3

## Operator contract

The Accounting QuickBooks migration workspace now records governed human decisions
against quarantined records. Decisions are append-only; replacement requires the
current decision identity and preserves the predecessor. Every accepted decision
creates audit and Business Event evidence. No action calls or writes QuickBooks.

| Action | Authority | Effect |
|---|---|---|
| Exact Customer/Vendor binding | OWNER + Accounting reconcile | Binds only the UUID explicitly selected in the same Company. |
| Account mapping/classification confirmation | ACCOUNTANT (`COMPANY_ACCOUNTING_FINANCE_APPROVE`) | Binds an explicit existing Company account; no classification is inferred. |
| Source-version confirmation | ACCOUNTANT | Clears only the source-version conflict; any remaining native-admission dependency stays quarantined. |
| Reject with reason | ACCOUNTANT | Creates a current `REJECTED_WITH_REASON` disposition. |
| Hold for accountant | ACCOUNTANT | Records the current governed hold without changing source truth. |
| Defer for external evidence | EXTERNAL EVIDENCE REQUIRED | Records the evidence dependency and leaves the queue item open. |
| Provider unavailable / unsupported | SYSTEM | Remain system-derived terminal dispositions, not human mutation buttons. |

Name-only/fuzzy matching, inferred account/tax semantics, bank reconciliation,
Payroll/tax fabrication, QBO writeback, and Accounting posting remain prohibited.

## Dependency replay

After a decision, the API filters the already sealed evidence packet to dependency
identities named by that review item and re-evaluates only those records. A matching
unchanged quarantine is an idempotent replay; a newly satisfied exact authority may
create a successor disposition. Failure to access sealed evidence does not undo the
decision and is reported as zero bounded records re-evaluated.

## Migration and release

- migration: `r8t0v2x4z6b8`
- parent at publication: `rg7c9e1f3i5k7`
- OM2E owns any final reline if Operations advances before integration.

Release must migrate first, deploy backend/frontend together, and verify the normal
Accounting workspace using sanctioned synthetic review records before Michael or an
accountant acts on the real Beta queue.
