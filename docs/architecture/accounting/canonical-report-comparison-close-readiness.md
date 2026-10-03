# Canonical report comparison and close-readiness contract

This backend contract is read-only except for its bounded hardening of the
existing period-close command. It performs no posting, Payroll execution, QBO
write, Banking operation, or money movement.

## Operator routes

- `GET /api/v1/accounting/periods/{period_id}/report-comparisons`
- `GET /api/v1/accounting/accountant-review`
- `GET /api/v1/accounting/periods/{period_id}/close-readiness`

The comparison response always contains all eight families: Trial Balance,
Profit & Loss, Balance Sheet, General Ledger, AR Aging, AP Aging, Cash Flow, and
Job Costing. A difference is returned only for `COMPARABLE` evidence. Missing
or incompatible evidence returns `UNAVAILABLE` or `NOT_COMPARABLE` and a stable
reason; the client must not calculate a replacement difference.

The accountant-review projection preserves each source domain's lifecycle and
links to its governed workspace. It is not an approval authority.

Close readiness is server-derived from the selected period version, approved
opening/equity controls, all canonical comparisons, the governed review queue,
and the Payroll close-evidence provider. Its digest binds those inputs. The
existing close command now requires the current `readiness_digest`; it rejects
blocked or stale readiness and replaces browser control assertions/evidence
digests with the server-derived values before calling the existing close
service.

## LPTP1B rules

1. Display server values and non-comparable reasons; never subtract report
   totals in the browser.
2. Use line drill-down from each comparison response, preserving debit and
   credit orientation for Trial Balance.
3. Render accountant-review state as source-owned; do not add a shared approval
   action.
4. Fetch close readiness immediately before close and submit only its
   `evidence_digest` as `readiness_digest` with the current period version.
5. Disable close whenever `overall_readiness != READY`.

## Real-evidence gate

The default report and Payroll providers fail closed until canonical ACP and
sealed QBO report snapshots plus period-level Payroll control evidence are
admitted. Fixture comparability proves software behavior only. Accounting
cutover still requires real sealed source custody, identical cutoff/basis/
currency/scope, reconciled AR/AP and equity, approved Payroll posting and
settlement evidence, and accountant certification.
