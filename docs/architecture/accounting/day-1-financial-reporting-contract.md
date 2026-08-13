<!-- markdownlint-disable MD013 -->

# Day-1 Internal Accounting Financial Reporting Contract

- **Milestone:** `ACC.RPT.CONTRACT.1`
- **Status:** Accepted implementation contract when this commit is authoritative
- **Runtime successor:** `ACC.RPT.1`
- **Cutover target:** August 21, only after the separately governed cutover gates
- **Ledger authority:** ACP Internal Accounting Core after accepted cutover

## Authority and boundary

This contract specializes the [Internal Accounting Day-1 Control Contract](day-1-control-contract.md), the [Internal Accounting Core Contract](core-ledger-contract.md), and [ADR 0005](../adr/0005-internal-accounting-system-of-record.md). It freezes the minimum reports required to operate, review, and reconcile ACP's books after QuickBooks retirement. It does not authorize runtime implementation, schema changes, data import, Preview, Production, or cutover.

Internal Accounting Core is the sole ledger authority. Financial Reporting is a read-only interpretation and presentation layer over immutable posted journals, the accepted Chart of Accounts, accounting periods, control reconciliations, and authoritative AR/AP open-item facts. A report, cache, export, Business Economics measurement, or operational record cannot create or alter an accounting balance. Business Economics may consume accepted reporting outputs later but is never an accounting authority or a source for Day-1 statements.

QuickBooks remains accounting authority until the separately approved cutover. After cutover it is an immutable archive and opening-state evidence source, not a runtime dependency. Report comparisons to QuickBooks are reconciliation evidence; they do not permit QuickBooks behavior, account classification, or amounts to be guessed.

## Common report contract

Every report request and result carries:

- Company identity, required and authorization-scoped;
- optional Branch identity belonging to that Company;
- accepted functional currency and accounting/book basis;
- report definition and version;
- effective-date range or as-of effective date, as applicable;
- accepted Company business timezone used to resolve date boundaries;
- optional accounting-period identity where the request is period-based;
- immutable ledger cutoff identifying the complete set of posted journals observed;
- generation timestamp and requesting principal;
- source/subledger cutoffs needed for control ties;
- reconciliation, completeness, and freshness state; and
- deterministic provenance and export checksum information.

Money uses fixed-precision decimal arithmetic in the Company's single Day-1 functional currency. No floating-point arithmetic, foreign-exchange translation, implicit rounding, or currency netting is permitted. Unknown, missing, stale, contradictory, or unreconciled evidence is explicit and never represented as zero.

For identical authorized inputs, ledger and subledger cutoffs, definition version, and ordering rules, computation produces identical rows, totals, provenance ordering, and canonical digest. A later posting, correction, period transition, mapping change, or subledger event creates a different cutoff or definition version; it never rewrites a previously exported result.

### Scope semantics

ACP has one Company-owned general ledger. Branch is a Company-scoped accounting dimension, not a second ledger or security tenant.

- A Company report includes all posted lines for the Company, including Company-level lines without a Branch.
- A Branch report includes only posted lines carrying that Branch. It does not invent an allocation of Company-level lines.
- A requested Branch must belong to the requested Company and be visible to the principal. A mismatch is indistinguishable from not found.
- A Branch statement may not be described as a complete legal-entity statement when Company-level balances are excluded. Its scope label and unassigned-Company amount disclosure are mandatory.
- Cross-Company aggregation and netting are prohibited on Day 1. A portfolio view, if later approved, remains a presentation of separately complete Company reports.

## Day-1 report definitions

### Trial balance

The trial balance derives exclusively from posted journal lines whose effective accounting date is on or before the requested as-of date and whose journal is included in the immutable ledger cutoff. It groups by Company and account, and by Branch only when Branch scope is requested.

For each account it presents account identity/code/name, classification, normal balance, beginning balance before an optional activity range, range debits, range credits, and ending balance. The canonical debit-positive signed balance is `sum(debit) - sum(credit)`; normal-balance presentation may change display sign but not the canonical amount. Archived accounts with activity or nonzero balances remain visible.

Invariants:

- total debit activity equals total credit activity exactly;
- total canonical ending balance is zero exactly;
- beginning balance plus range debits minus range credits equals ending balance per account;
- only `posted` journals affect any amount;
- every included line appears exactly once; and
- a missing account classification, period, currency, or ledger provenance fails the report closed.

### Balance sheet

The balance sheet is an as-of report over cumulative posted activity through the requested effective date. It presents asset, liability, and equity accounts using the accepted COA classification and normal-balance policy. It includes current earnings derived from revenue and expense activity not yet closed to retained earnings so that reporting does not depend on an inferred closing entry.

The invariant is `Assets = Liabilities + Equity`, including current earnings, exactly in functional-currency minor units. The report must disclose the retained-earnings/current-earnings mapping and definition version. Missing or ambiguous classification or mapping fails closed. Comparative columns are separate complete as-of computations with their own cutoffs; no prior result is mutated.

### Income statement / profit and loss

The income statement reports posted revenue and expense activity whose effective accounting date falls inclusively within the requested range or accounting period. Account classification and approved statement grouping come from versioned Accounting reporting mappings. The invariant is `Net income = Revenue - Expenses`, using the accepted display-sign policy and exact decimal totals.

Original, reversal, and corrective journals are all included according to their own effective dates. A correction effective in a later open period changes that later period and comparative cumulative results; it does not rewrite a closed-period export. Cash, accrual, or other book-basis behavior is determined by accepted posting policy, not by report-time reinterpretation of invoices or payments.

### General-ledger detail

General-ledger detail presents every included posted journal line without aggregation loss. It supports Company, optional Branch, account, effective-date/period, and source filters. Stable ordering is effective date, posting timestamp, journal identity, line ordinal, then line identity.

Each row exposes account, debit or credit, running canonical balance, effective date, period, journal type/status/description, line description, Branch, preparer/poster identities permitted for the viewer, source tuple, posting-rule/mapping version, canonical source digest reference, correlation identity, and original/reversal/corrective links. Beginning and ending balances reconcile exactly to the trial balance for the same scope and cutoff. Filters may narrow display but must state their scope and may not label filtered totals as the full trial balance.

### Accounts-receivable aging

AR aging is a read-only projection of authoritative invoice/open-item evidence as of the requested instant. Each item retains Company, Branch, Customer, invoice/open-item identity, issue and due dates, currency, original amount, credits/write-offs/applications through the cutoff, and open amount. Aging uses contractual due date and the accepted Company business timezone.

The versioned bucket policy is a Finance input. Until approved, no bucket boundaries may be assumed. The implementation must support the accepted ordered, nonoverlapping, exhaustive bucket definition and identify its version. Unapplied receipts are disclosed separately and are never aged as invoices. Customer credits, voids, write-offs, application reversals, and corrections remain visible through drillback. There is no cross-Customer, cross-Company, cross-Branch, or cross-currency netting.

For the same scope and cutoff, `sum(open AR items) = AR subledger balance = posted GL AR control balance`. Any missing posting receipt, duplicate or contradictory application, stale cutoff, or nonzero variance makes the report unreconciled; it never changes the difference to zero.

### Accounts-payable aging

AP aging is the corresponding read-only projection of authoritative vendor bill/open-item evidence. Each item retains Company, Branch where authoritative, Vendor, bill/open-item identity, bill and due dates, currency, original amount, credits/disbursement applications through the cutoff, and open amount. It uses the same accepted timezone and a separately versioned Finance-approved AP bucket policy.

Unapplied disbursements or vendor credits are disclosed separately and not silently netted. Bill corrections, credits, voids, disbursement reversals, and replacements remain visible through drillback. There is no cross-Vendor, cross-Company, cross-Branch, or cross-currency netting.

For the same scope and cutoff, `sum(open AP items) = AP subledger balance = posted GL AP control balance`. Missing authoritative AP evidence makes the report incomplete or unavailable, not zero. `ACC.RPT.1` cannot synthesize an AP subledger from GL descriptions.

## Effective dates, periods, and cutoffs

The journal effective accounting date determines statement inclusion. Occurrence, source receipt, preparation, approval, posting, and report-generation timestamps are provenance and never substitute for effective date. The as-of instant is resolved in the accepted Company business timezone; API transport remains timezone-aware.

A report cutoff is a durable high-water mark over committed posted journals plus the relevant AR/AP evidence marks. It prevents a multi-query report from mixing states while posting occurs. A period report validates that the requested date range equals the accepted period boundaries. An ad hoc date range is permitted but is labeled as such.

Period status is reported, not inferred from elapsed time. `open`, `closing`, `closed`, and `reopened` remain distinguishable. A closed-period report is not automatically Finance-approved. A reopened period retains transition history and invalidates the freshness of prior close exports until a new reconciliation and review package is accepted. Late evidence posts only through normal open/reopened-period controls.

## Provenance and drillback

Every displayed total and detail row must support deterministic drillback:

```text
report result and cutoff
  → statement section / account / aging bucket
  → contributing journal line or open-item entry
  → posted journal and reversal/correction chain
  → Accounting posting receipt and posting-rule/mapping version
  → immutable source tuple, source digest, and Business Event/correlation evidence
  → source-domain record authorized for that viewer
```

The report stores identities and evidence references, not mutable copies as authority. Drillback enforces the target domain's permissions and sensitive-data rules; report permission does not grant unrestricted source-record access. If source detail is unavailable, the financial line and immutable reference remain visible with an explicit unavailable-detail state.

A canonical report manifest includes definition version, normalized request, ledger/subledger cutoffs, ordered contributing identities and digests, row count, control totals, reconciliation state, generated timestamp, and SHA-256 digest. The digest proves the exported package, not the truth of absent source evidence.

## Corrections and reversals

Posted records are append-only. Reporting includes an original journal, its opposite reversal, and any replacement/corrective journal as separate evidence according to their effective dates. It presents chain identity, reason, actor evidence subject to permission, period, and net effect. A display option may collapse a chain for readability only when the uncollapsed chain and its exact reconciliation remain available.

An AR/AP correction likewise preserves the original item and compensating entries. No report filter may silently hide reversals, voids, credits, write-offs, or replacement links while presenting a result as complete. A prior export remains immutable and is marked superseded/stale by a later accepted cutoff rather than overwritten.

## Reconciliation, completeness, and freshness

Each report carries independent states rather than one ambiguous success flag:

- **completeness:** `complete` or `incomplete`, with every missing required source/control identified;
- **freshness:** `current` or `stale`, relative to the report cutoff and versioned source-specific policy;
- **reconciliation:** `reconciled`, `unreconciled`, or `not_applicable`, with exact variance and evidence;
- **integrity:** `passed` or `failed`, based on mathematical and isolation invariants; and
- **review:** `unreviewed`, `prepared`, `finance_approved`, or `rejected`, with immutable actor/time/evidence.

`finance_approved` requires an independently authorized Finance actor and never follows automatically from reconciliation. A report with failed integrity cannot be exported as accepted. An incomplete, stale, or unreconciled report may be rendered only as a conspicuously exception-marked workpaper; it cannot satisfy close, migration, cutover, or owner-review evidence.

AR/AP/control variances use exact minor-unit reconciliation. Finance reporting materiality may prioritize review but may not convert a nonzero control variance to reconciled. No unexplained residual is acceptable for Day-1 cutover.

## Authorization and separation of duties

All access uses the centralized permission catalog and Company/Branch scope.

| Action | Minimum Accounting authority | Separation rule |
| --- | --- | --- |
| Read reports and exports | `COMPANY_ACCOUNTING_REPORT_READ` | Scope filtering always applies |
| Drill into posted ledger evidence | `COMPANY_ACCOUNTING_READ` plus report read | Source-domain detail requires its own permission |
| Prepare reconciliation/review package | `COMPANY_ACCOUNTING_RECONCILE` plus report read | Preparer cannot independently approve the same package |
| Approve governed report/reconciliation evidence | `COMPANY_ACCOUNTING_FINANCE_APPROVE` | Must differ from preparer/reconciler |
| Manage period or request reopen | `COMPANY_ACCOUNTING_PERIOD_MANAGE` | Finance approver must be distinct |

Report endpoints are read-only. They expose no journal posting, reversal, source correction, period transition, or approval shortcut. Review/approval is an Accounting governance command referencing an immutable report package, not a mutation of report rows. Sensitive payroll, bank, payment-instrument, Customer, Vendor, and free-text evidence is minimized and separately authorized.

## Export and owner/Finance review

Day 1 requires deterministic machine-readable CSV exports for every report and a stable human-readable rendering suitable for signed review. Each export is generated from one immutable report result and includes or accompanies its canonical manifest and SHA-256 checksum. Spreadsheet formulas, locale-dependent numbers, mutable external links, credentials, and hidden rows are prohibited as authoritative evidence.

The Owner/Finance package includes report name/version/scope, as-of or range, accounting basis, currency, timezone, period status/history, ledger and subledger cutoffs, reconciliation/completeness/freshness/integrity states, exact control variances, correction/reversal disclosure, exception register, checksum, preparer, and independent Finance decision. Export does not equal approval. The Owner remains final cutover authority; the external accountant/CPA may approve through signed/checksummed evidence without ACP application access.

## Exact `ACC.RPT.1` implementation packet

### Start dependencies

`ACC.RPT.1` may start only after owner authorization and authoritative integration evidence for:

1. `ACC.CORE.1`: accepted COA, immutable posted journals/lines, periods, reversals, permissions, and reconciliation interfaces;
2. `INVOICE.1-3.ACCEL`: authoritative AR open-item, credit, write-off, application, reversal, and posting-receipt evidence;
3. `PAY.1-3.ACCEL`: receipt/application, refund, clearing, deposit, unapplied receipt, and settlement evidence;
4. `ACC.AP.1`: the accepted [Accounts Payable and Vendor Contract](accounts-payable-vendor-contract.md), including authoritative AP open-item, credit, disbursement, correction, and posting-receipt evidence;
5. `ACC.POST.1`: accepted source-to-journal mappings, posting receipts, failures, and replay behavior; and
6. accepted Finance inputs listed below.

Dependency completion is proved by the [Accounting integration control](integration-control.md) and its durable ledger, not branch names or planned sequence. `ACC.MIG.1` follows `ACC.RPT.1`; reporting must work with synthetic fixtures before opening-state import.

### Allowed implementation boundary

- new `backend/app/financial_reporting/**` and `backend/tests/financial_reporting/**`;
- narrowly required read-only interfaces in Accounting, Invoicing/AR, Payments, and AP, with their focused tests;
- matching read-only frontend reporting routes/components/tests under the established frontend structure;
- centralized registration and the exact permission seams required by this contract; and
- documentation limited to implementation evidence and accepted API/report schemas.

The packet prohibits writes to operational-domain or Accounting ledger tables, Business Economics changes, provider/QuickBooks transport, import behavior, deployment configuration, credentials, Production data, and unrelated shared files.

### Required deliverables

1. Immutable typed request/result contracts for all six reports, scope, period/effective date, cutoff, definition version, quality states, provenance, and export manifest.
2. Read-only ports for posted ledger/account/period/reversal/reconciliation facts and authoritative AR/AP open-item facts.
3. Deterministic services implementing the equations, scope rules, stable ordering, exact decimal arithmetic, drillback graph, and fail-closed behavior in this contract.
4. Read-only authenticated APIs for report generation/read, GL drillback, provenance, reconciliation state, and checksum-bound export.
5. Day-1 operator presentation for each required report, explicit scope/cutoff/status banners, exceptions, correction chains, drillback, and controlled export. No dashboard or KPI substitution satisfies a report.
6. Accounting-governed package preparation and independent Finance review references without combining preparer and approver authority.
7. Rebuild/freshness evidence proving any optimization is disposable and exactly reproducible from authoritative facts.

### Persistence and migration

No reporting persistence or Alembic migration is required or authorized by this contract. `ACC.RPT.1` must begin with deterministic read models over authoritative sources. If measured performance demonstrates a durable projection is necessary, implementation must stop and obtain separate approval for its schema, rebuild/checkpoint semantics, retention, and serialized migration slot 6. A cache never becomes ledger or subledger authority.

### Required validation

- exact trial-balance equality and zero-net property across empty, single-period, multi-period, reversal, correction, reopened-period, Company, and Branch fixtures;
- balance-sheet equation and income-statement/net-income equations with versioned mappings;
- GL-detail beginning/activity/ending ties and deterministic ordering/provenance;
- AR and AP item-to-subledger-to-control-account equality, bucket boundaries, credits, unapplied amounts, and missing-evidence failures;
- effective-date versus posting-time, timezone boundary, period, cutoff consistency, late evidence, and comparative replay tests;
- Company isolation, Branch scope/unassigned disclosure, permission denial, sensitive-data minimization, and SOD tests;
- deterministic rebuild, identical replay/digest, stale detection, correction/reversal visibility, and export checksum tests;
- Ruff, MyPy, focused and affected backend regressions; frontend tests, ESLint, typecheck, and production build when frontend changes exist;
- Alembic current-head, fresh upgrade, populated upgrade, downgrade/re-upgrade, and drift checks proving no unintended schema change;
- `git diff --check`, documentation-link validation, and focused credential/private-key scan; and
- independent Finance acceptance against signed, sanitized controls before any Preview, Production, migration, or cutover gate.

### Completion and stop conditions

Completion requires all deliverables and validation evidence, exact control ties, Finance review, clean repository state, and separately authorized integration. Stop for ambiguous COA/report mappings, accounting basis, functional currency, aging buckets, unexplained variance, ownership conflict, schema need outside an approved migration, sensitive-data exposure, semantic Git conflict, or any Preview/Production/cutover operation.

## Dependencies and unresolved Finance inputs

The following are inputs, not choices for Financial Reporting to invent:

- accepted Company functional currency, book basis, business timezone, fiscal calendar, and period boundaries;
- active COA classifications, normal balances, statement grouping/order, retained/current-earnings presentation, and control-account assignments;
- separately versioned AR and AP aging bucket boundaries;
- accepted AR/AP, cash/bank, undeposited funds, clearing, tax, inventory, payroll, opening-state, and other required reconciliation workpapers;
- policy for display signs, zero-account visibility, comparative periods, and controlled export retention;
- source-specific freshness requirements and Finance/Owner exception ownership; and
- external accountant/CPA identity and approved evidence mechanism for independent review.

These inputs block acceptance or activation of affected reports. They do not authorize default assumptions. Runtime dependencies remain ordered:

`ACC.CORE.1 → INVOICE.1-3.ACCEL → PAY.1-3.ACCEL → ACC.AP.1 → ACC.POST.1 → ACC.RPT.1 → ACC.MIG.1`.

## Contract acceptance

Acceptance of this document makes `ACC.RPT.1` eligible only when its dependencies and owner Start gate are satisfied. It does not start implementation, reserve a migration, approve Finance policy, retire QuickBooks, modify Preview or Production, or authorize the August 21 cutover.
