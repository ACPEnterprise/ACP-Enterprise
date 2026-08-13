<!-- markdownlint-disable MD013 -->

# Internal Accounting Cutover Critical Path

The target is Friday, 2026-08-21. The date never overrides the controlling
[ADR](../architecture/adr/0005-internal-accounting-system-of-record.md),
[Day-1 controls](../architecture/accounting/day-1-control-contract.md), Finance
approval, reconciliation, security, Preview, Production, or cutover gates.

## Ordered path

1. `ACC.CUTOVER.0` — accept authority, policy, packets, and exit controls.
2. In parallel: `ACC.CORE.CONTRACT.1`, `ACC.AR.CONTRACT.1`, and `ACC.DATA.1`.
3. `ACC.CORE.1` — internal ledger and control foundation.
4. `INVOICE.1-3.ACCEL` — invoices and AR.
5. `PAY.1-3.ACCEL` — payment/cash accounting.
6. `ACC.AP.1` — AP and vendor accounting.
7. `ACC.POST.1` — source facts to journals.
8. `ACC.RPT.1` — required statements and aging.
9. `ACC.MIG.1` — opening-state loader and reconciliation evidence.
10. `ACC.IC.1` — accepted, serialized Accounting candidate with one head.
11. `ACC.PREVIEW.1` — separately approved Preview validation.
12. `ACC.REHEARSAL.1` — real-export, non-Production cutover rehearsal.
13. `ACC.GO.1` — independent Finance verification and owner go/no-go.
14. `ACC.PROD.1` — separately approved Production release.
15. `ACC.CUTOVER.1` — separately approved freeze, import, reconcile, activate,
    and QuickBooks operational retirement.

## Capacity handoff

- `OM2-A`: `ACC.AR.CONTRACT.1` now; after acceptance,
  `INVOICE.1-3.ACCEL`, then `PAY.1-3.ACCEL`.
- `OM2-B`: `ACC.CORE.CONTRACT.1` now; after acceptance, `ACC.CORE.1`, then
  `ACC.AP.1`.
- `LAP-A`: this milestone, then serialized `ACC.IC.1` and release gates.
- `LAP-B`: after existing MMQ work, `ACC.DATA.1`, then rehearsal evidence.
- MIG/ECO receive no filler work. Any reassignment requires a clean independent
  repository/worktree and a separate Start.

## Calendar gates

| Date | Required outcome |
| --- | --- |
| Aug 13 | Contract accepted; contract/data packets started |
| Aug 14 | Runtime contracts accepted; implementation packets may start |
| Aug 15–17 | Core/subledgers/posting/reporting integrated serially |
| Aug 18 | Latest safe Preview candidate and backup/restore proof |
| Aug 19 | Latest safe first real-export rehearsal |
| Aug 20 noon | Repeatable reconciliation and immutable go/no-go package |
| Aug 21 | Only if approved: freeze, final export, deploy, import, reconcile, activate |

If a required gate fails, cutover moves; controls do not weaken.
