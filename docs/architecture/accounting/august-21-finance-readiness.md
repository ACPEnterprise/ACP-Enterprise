<!-- markdownlint-disable MD013 -->

# CUTOVER.FINANCE.1 — August 21 Accounting Policy and Finance Readiness

## Purpose and authority

This launch-readiness record accompanies the deterministic [Day-1 Accounting policy packet](day-1-accounting-policy.packet.json). It applies the accepted [Day-1 control contract](day-1-control-contract.md), [Accounting Core contract](core-ledger-contract.md), [Invoice/AR contract](accounts-receivable-invoice-contract.md), [AP contract](accounts-payable-vendor-contract.md), [Payment contract](payment-cash-settlement-contract.md), [posting contract](domain-event-posting-contract.md), [Financial Reporting contract](day-1-financial-reporting-contract.md), and [QuickBooks exit data contract](quickbooks-exit-data-contract.md).

It records policy authority and exact unanswered questions. It does not approve an unanswered recommendation, access or extract QuickBooks, implement runtime, post or import transactions, modify a migration, deploy, or authorize the August 21 cutover.

## Classification summary

The packet accounts for all 16 required inputs exactly once:

| Classification | Count | Items |
| --- | ---: | --- |
| `RESOLVED_BY_AUTHORITY` | 3 | Company timezone; reporting freshness; exception ownership |
| `OWNER_DECISION_REQUIRED` | 1 | Comparative-period presentation |
| `FINANCE_DECISION_REQUIRED` | 6 | Statement mappings; retained/current earnings; AR buckets; AP buckets; display signs; export retention |
| `SOURCE_EVIDENCE_REQUIRED` | 6 | Functional currency; accounting basis; fiscal calendar; COA classifications; control workpapers; independent reviewer identity/evidence |
| `BLOCKED` | 0 | No policy analysis is blocked; downstream activation remains blocked by the listed evidence and decisions |

Repository values in sanitized synthetic fixtures are test data and are not Company facts. In particular, synthetic `USD` and `accrual` values do not resolve functional currency or accounting basis.

## Policies resolved by authority

1. **Company timezone:** `America/New_York`. The accepted cutover instant is `2026-08-21 00:00:00-04:00`; accounting-date boundaries use this timezone. QuickBooks export metadata must still record its source timezone to prove reconciliation.
2. **Reporting freshness:** cutoff-consistent on demand. A report is current only for its immutable ledger and relevant subledger cutoffs. A later posting/open-item fact makes the earlier result stale. A time-based SLA cannot make inconsistent cutoffs current.
3. **Exception ownership and SOD:** the Owner is `FINANCE_PREPARER`; the external accountant/CPA is `INDEPENDENT_FINANCE_APPROVER`; the Owner separately gives final cutover authorization. The preparer/reconciler and independent approver must be different people. A nonzero unexplained control variance blocks acceptance.

Other mechanical rules are also fixed: preserve the active QuickBooks basis and COA without redesign; use single functional currency; posted journals alone affect balances; corrections are append-only reversal/replacement evidence; Branch is a Company dimension; exact control reconciliation is not waived by materiality; and Business Economics is not ledger authority.

## Decisions and evidence required

### Immediate actions within 24 hours — by August 14, 2026

| Priority | Exact action/question | Recommended response | Consequence if delayed |
| --- | --- | --- | --- |
| 1 | Authorize a named Owner-controlled QuickBooks export operator and restricted evidence custodian. Who are they? | Owner may fill both preparer/custodian functions if access policy permits; neither can independently approve their own package. | No trustworthy source settings, COA, or control package; POST/RPT/MIG and cutover remain blocked. |
| 2 | Identify the external accountant/CPA who will act as independent reviewer, their secure exchange channel, signature/attestation format, and availability for rehearsal and August 20–21. | Use the existing CPA/accountant; signed attestation must name the manifest SHA-256 and decision. | No independent Finance gate; cutover cannot occur. |
| 3 | Produce controlled QuickBooks company-settings evidence for home currency, accounting basis, timezone/locale, fiscal-year start, current period/close settings, product/edition/version, and Company identity. | Export/screenshot the active company settings without changing them. | Core configuration, statement semantics, and opening package cannot be accepted. |
| 4 | Produce the active COA machine export and human control report with stable IDs, account types/subtypes, active state, parent, currency where applicable, and control roles. | Preserve it as-is for Day 1; defer redesign. | Posting mappings, statements, and opening journals remain blocked. |

### Owner decision

**Question:** Which comparative columns are mandatory on Day 1?

- Choice A: current reporting period only.
- Choice B: current period and immediately preceding period.
- Choice C: current period/prior period plus year-to-date/prior-year year-to-date.
- **Recommendation:** Choice C where the QuickBooks fiscal calendar and comparable prior-period controls are evidenced; otherwise launch with Choice B and retain deterministic export support for C.
- **Accounting consequence:** none to ledger balances; each comparison is an independent complete computation with its own range and cutoff.
- **Cutover consequence:** blocks acceptance of comparative presentation, not trial-balance or GL correctness.
- **Latest safe decision:** August 17, 2026, before ACC.RPT.1 presentation acceptance.

### Finance/CPA decisions

| Decision and exact question | Supported choices | Recommendation | Accounting and cutover consequence | Latest safe date |
| --- | --- | --- | --- | --- |
| Statement mapping: how does every active/nonzero COA account map to a BS or P&L section and ordered subtotal? | Preserve evidenced QuickBooks report grouping; or Finance-approved ACP grouping with a complete one-to-one crosswalk | Preserve QuickBooks grouping for Day 1; redesign later | Ambiguity fails statements; blocks RPT and cutover | Aug 15 |
| Retained/current earnings: which equity account receives evidenced opening retained earnings, and how is unclosed current earnings displayed? | Separate current earnings presentation; or evidenced QuickBooks-equivalent presentation | Separate current earnings in reporting; never create an inferred closing journal | Blocks balanced opening equity and BS acceptance | Aug 15 |
| AR bucket boundaries? | Preserve evidenced QuickBooks buckets; or another ordered exhaustive Finance-approved set | Preserve current QuickBooks buckets; if none are evidenced use `current`, `1–30`, `31–60`, `61–90`, `91+` only after explicit Finance approval | Presentation and migration aging controls cannot be accepted | Aug 15 |
| AP bucket boundaries? | Same choices independently from AR | Preserve current QuickBooks buckets; use the conventional set only with explicit approval | Presentation and migration aging controls cannot be accepted | Aug 15 |
| Statement display signs? | Natural-credit revenues/liabilities/equity displayed positive; or canonical debit-positive signs; expenses either positive or signed | Use conventional statements: assets/expenses positive by normal balance, liabilities/equity/revenue positive by normal balance; retain canonical debit-positive evidence in drillback | Does not alter ledger math but blocks Finance acceptance of statements | Aug 16 |
| Export retention duration and custody? | Existing Finance/legal schedule; or a newly approved duration/storage schedule | Apply existing policy; if none exists, seek Finance/legal approval for at least seven fiscal years in restricted immutable storage | Blocks accepted export/archive and cutover evidence; recommendation is not legal approval | Aug 15 |

### Source evidence, not discretionary decisions

- Functional currency: QuickBooks company settings plus same-basis trial balance/COA currency evidence.
- Accounting basis: QuickBooks basis setting and same-basis TB, balance sheet, and P&L.
- Fiscal calendar: fiscal-year start, period bounds, current close date/status, and Finance-confirmed 2026 schedule.
- COA classifications: active machine export plus control report and stable source identities.
- Control workpapers: every required subledger/control and statement-to-book reconciliation listed below.
- Reviewer: named external CPA/accountant, distinct identity, attestation method, secure channel, availability, and checksum-bound evidence.

## Exact QuickBooks source package

Do not commit real exports or private accounting data to Git. Store them in approved restricted storage and place only sanitized layouts/checksums in authorized engineering evidence.

### Policy and statement artifacts required now

1. Company-information/settings evidence: stable Company identity, QuickBooks product/edition/version, home currency, multicurrency status, accounting basis, timezone/locale, fiscal-year start, period/close settings, export operator/time, filters, and report definition/version.
2. Active Chart of Accounts: machine-readable export plus human control report, including stable account ID, number/name, active status, source type/subtype/classification, parent, and currency where applicable.
3. Trial balance at one common explicit cutoff: machine-readable detail plus signed/PDF control, debit/credit meaning, basis, currency, filters, and zero-net proof.
4. Balance sheet and P&L at that same cutoff/basis, including account grouping, retained earnings, current earnings, equity, and comparative settings actually used.
5. AR aging plus open customer invoice, credit, application, and unapplied-receipt detail at the same cutoff; include bucket settings and customer stable IDs.
6. AP aging plus open vendor bill, credit, application, and disbursement detail at the same cutoff; include bucket settings and vendor stable IDs.

### Opening-state and reconciliation artifacts required before rehearsal/cutover

- GL detail for the Finance-approved support period tied to the cutover trial balance.
- Undeposited-funds transaction listing tied to its GL control.
- Bank and cash account book balances, statements, last reconciliations, outstanding checks, deposits in transit, transfers, and every reconciling item.
- Payment clearing, processor settlement, fees, refunds, chargebacks, and destination-deposit controls.
- Sales-tax liability by jurisdiction, filing period, credits/payments, and GL control.
- Payroll provider summary, payroll liabilities/accruals, covered periods, due dates, and GL controls without unnecessary employee-sensitive detail.
- Inventory financial-control/valuation report and mapped GL control.
- Equity and retained-earnings reports with fiscal-year context.
- Credit cards, loans, fixed assets/accumulated depreciation, prepaids, and other accrual schedules when applicable; otherwise signed `not_applicable` disposition.
- Customer/vendor identity exports covering every open item.
- Native QuickBooks archive, export inventory, raw-byte SHA-256 checksums, storage/custodian/retention reference, restore/readability evidence, and final transaction-freeze evidence.

All artifacts must identify the same source Company, basis, currency, timezone, approved cutoff, filters, and report version or carry an independently approved difference. PDF is control evidence, not loader rows. Missing evidence is not zero or `not_applicable` without signed disposition.

## Consumer blocking map

| Consumer | Blocking inputs |
| --- | --- |
| `PAY.1-3.ACCEL` activation | Functional currency; bank destination and payment/clearing/settlement mappings; control workpapers; named exception actors |
| `ACC.AP.1` activation | Functional currency/basis; AP control and expense/asset/tax mappings; vendor/open-item evidence; AP aging policy for accepted reporting; SOD actors |
| `ACC.POST.1` activation | Functional currency; basis; fiscal periods; COA/control classifications; every source-to-account mapping; exact effective-date policies; control workpapers |
| `ACC.RPT.1` acceptance | Currency/basis/calendar; COA and statement mappings; retained/current earnings; AR/AP buckets; display/comparative policy; retention; complete controls; independent review |
| `ACC.MIG.1` | All source settings; final COA/TB/open items; Company/Branch mappings; every opening schedule/control; retention/custody; independent Finance evidence |
| August 21 cutover | All above plus zero unexplained variance, accepted rehearsal, backup/rollback, security, Preview/Production gates, independent Finance approval, and separate Owner go/no-go |

## Workpaper acceptance template

Every workpaper records Company, optional Branch, control name, source and GL account identities, functional currency, accounting basis, effective cutoff, source report/export definition, source amount, ACP/subledger amount, GL amount, exact variance, itemized explanation, source file SHA-256, preparer identity/time, independent reviewer identity/time/decision, and supersession link. `reconciled` requires exact zero unexplained variance. Materiality may prioritize investigation but never changes reconciliation truth.

## Readiness conclusion

Policy architecture is complete enough to collect decisions without further design. Three items are resolved, seven require Owner/Finance decisions, and six are classified as requiring authoritative QuickBooks/control evidence; the latter include the independent reviewer identity/evidence record. Some decision items also require source evidence first. No downstream activation or cutover is authorized by this packet. The critical immediate path is: name the export custodian and independent CPA, capture Company settings and the active COA, then obtain common-cutoff financial statements and open-item/control packages for Finance disposition.
