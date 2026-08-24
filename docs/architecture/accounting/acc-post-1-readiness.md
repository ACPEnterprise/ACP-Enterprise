<!-- markdownlint-disable MD013 -->

# ACC.POST.READY.1 — Day-1 Posting Runtime Readiness Closure

## Authority and boundary

This record reconciles `ACC.POST.1` readiness at Enterprise SHA
`5f6649527d793a3f40d1a60d41af5e5c5c943ea7`. It applies the accepted
[posting contract](domain-event-posting-contract.md),
[machine packet](acc-post-1.packet.json),
[Finance readiness packet](day-1-accounting-policy.packet.json), and
[integration control](integration-control.md).

It is control-plane documentation only. It does not Start or implement
`ACC.POST.1`, add events or adapters, create a migration, configure actual
accounts, access accounting data, deploy, enter Preview or Production, import,
or perform cutover. The August 21, 2026 target has passed as of this
reconciliation on August 24; no missed date weakens a gate.

## Dependency status

| Dependency | Classification | Authoritative evidence and consequence |
| --- | --- | --- |
| `ACC.CORE.1` | `COMPLETE_AND_AUTHORITATIVE` | Runtime commit `ee87e572d0f0e53fbc826978ab4d3a8ff489120a`; owns balanced journals, periods, controls, idempotency, reversals, failures, audit, and posting-source identity |
| `INVOICE.1-3.ACCEL` | `COMPLETE_AND_AUTHORITATIVE` | Runtime commit `43018e22786341116f77a606ccf70a8fa1e3ae14` plus authoritative identity fix `5f6649527d793a3f40d1a60d41af5e5c5c943ea7`; Invoice event/receipt seams exist |
| `PAY.1-3.ACCEL` | `BLOCKED` | `PAY.CONTRACT.1` and packet are accepted, but `backend/app/payments/**` and an authoritative runtime commit do not exist; packet is ready for separate Owner Start |
| `ACC.AP.1` | `BLOCKED` | `ACC.AP.CONTRACT.1` and packet are accepted, but `backend/app/accounts_payable/**` and an authoritative runtime commit do not exist; slot 4 remains downstream of Payment slot 3 |
| `ACC.POST.CONTRACT.1` | `COMPLETE_AND_AUTHORITATIVE` | Commit `4585dc8b3e5b2e6730ed980ba89a0b677d79d128`; exact contract and packet are on authoritative Enterprise |
| `CUTOVER.FINANCE.1` | `FINANCE_INPUT_REQUIRED` | Readiness commit `cdc0467`; policy inventory is closed, but packet status is `owner_finance_evidence_required`: 3 resolved, 1 Owner decision, 6 Finance decisions, and 6 source-evidence items |
| Inventory financial-adjustment facts | `SOURCE_EVIDENCE_REQUIRED` | Operational adjustment, cycle-count, material-issue, reversal, quantity and optional valuation records exist; emitted Inventory events do not carry an accepted financial value/mapping fact. `NOT_REQUIRED_FOR_INITIAL_RUNTIME`, required for Inventory financial activation if applicable |
| Payroll-summary facts | `SOURCE_EVIDENCE_REQUIRED` | Workforce capability data exists; no payroll runtime or accepted summary event exists. `NOT_REQUIRED_FOR_INITIAL_RUNTIME`, required for payroll-summary activation |
| Tax jurisdiction/control mapping | `FINANCE_INPUT_REQUIRED` | Invoice revisions/lines preserve taxable basis, tax amount, classification, operational tax-policy ID/version/rate; the common posting event omits jurisdiction/agency and liability mapping. Source enrichment and Finance control mapping are required for tax activation |

`IMPLEMENTING` is not assigned because no authoritative branch/commit evidence
proves Payment or AP implementation is active. Contract readiness is not runtime
implementation evidence.

## Day-1 posting-rule readiness matrix

Account names below are semantic roles, never actual COA numbers. Every rule is
Company-scoped, versioned, effective-dated, exact-decimal, balanced, and selected
against the source fact's approved accounting effective date. Every closed or
closing period fails closed; no rule silently shifts dates. Missing mappings
produce `reconciliation_required`, no journal, and no zero default.

| Source fact | Source domain and accepted identity | Debit role | Credit role | Control | Effective date and period | Reversal/correction | Idempotency | Finance state |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Invoice issuance / AR | Invoice; `invoice.issued` with source event/invoice/version/digest; runtime authoritative but posting payload enrichment remains required | `ACCOUNTS_RECEIVABLE_CONTROL` for gross obligation | Versioned `REVENUE_*` roles plus `SALES_TAX_PAYABLE` for exact accepted components | AR; tax when nonzero | Approved invoice accounting effective date; containing open/reopened Company period | Linked full reversal for void/replacement; corrective journal for approved partial correction; never rewrite issued evidence | `(company, invoice.issued, event_id, rule_version)` plus canonical source digest | Actual revenue/tax account mappings and basis/effective-date policy required to activate |
| Payment receipt/capture | Payments; accepted contract identity `payment.receipt_captured`; runtime absent | Finance-mapped `UNDEPOSITED_FUNDS` or `PAYMENT_CLEARING_RECEIVABLE` according to settlement model | Finance-mapped `UNAPPLIED_CUSTOMER_RECEIPT`/receipt-clearing role; never AR until application | Undeposited funds/payment clearing | Verified capture effective date; open/reopened period | Refund/dispute uses its own linked compensating fact; capture is never edited | `(company, payment.receipt_captured, event_id, rule_version)` plus evidence digest | Receipt-side roles and clearing model required to activate; not required to build generic engine |
| Payment application | Invoice authority; `invoice.payment_applied`; correlate accepted receipt identity, never duplicate a Payment event | `UNAPPLIED_CUSTOMER_RECEIPT` or selected receipt-clearing role | `ACCOUNTS_RECEIVABLE_CONTROL` | AR plus receipt/clearing tie | Accepted application effective date; open/reopened period | `invoice.payment_application_reversed` reverses only linked application journal | Source event tuple/digest; receipt/application identity unique | Clearing-to-AR mapping required to activate |
| Refund succeeded | Payments; accepted contract identity `payment.refund_succeeded`; runtime absent | Receipt liability/clearing role; if previously applied, linked Invoice unapplication restores AR under its own fact | Bank/cash/payment-clearing role | Cash/clearing, refund and AR tie where applied | Verified refund success effective date, not request date; open/reopened period | Later contradictory provider evidence queues; no mutation of prior journal | `(company, payment.refund_succeeded, event_id, rule_version)` plus provider evidence digest | Refund source/destination and applied-refund orchestration policy required to activate |
| Processor fee | Payments settlement component; contract requires separate fee component but exact event payload is runtime-dependent | `PROCESSOR_FEE_EXPENSE` | `PAYMENT_CLEARING` or mapped bank settlement role | Payment clearing/bank settlement | Verified settlement effective date; open/reopened period | Reversed only by linked provider adjustment/settlement correction | Settlement/component stable identity + rule version + digest | Expense and clearing mappings required; runtime fact schema required to implement producer adapter |
| Deposit / clearing | Payments; `payment.deposit_submitted`, `payment.deposit_reversed`, `payment.settlement_received`, `payment.settlement_reconciled`; runtime absent | Bank/cash or destination clearing role on accepted settlement | Undeposited-funds/payment-clearing role | Bank/cash, undeposited funds, payment clearing | Submitted is posting-eligible only if approved rule says so; otherwise settlement effective date controls; open/reopened period | Deposit reversal/settlement correction is linked compensating evidence | Deposit/settlement event identity + rule version + digest | Bank destination, undeposited, clearing, fee and variance mappings required to activate |
| AP bill approval | AP; accepted contract identity `accounts_payable.bill_approved`; runtime absent | Versioned line roles: expense, prepaid, fixed asset, inventory asset, recoverable tax only when accepted | `ACCOUNTS_PAYABLE_CONTROL` | AP plus applicable asset/tax controls | Approved bill accounting effective date; open/reopened period | `accounts_payable.bill_reversed` reverses linked obligation; replacement bill posts separately | `(company, accounts_payable.bill_approved, event_id, rule_version)` plus bill revision digest | AP control and every line classification/mapping required to activate |
| Vendor credit | AP; `accounts_payable.vendor_credit_issued` and application fact; runtime absent | `ACCOUNTS_PAYABLE_CONTROL` when credit recognizes reduction | Versioned original expense/asset/tax role; application itself cannot duplicate recognition | AP and applicable source control | Credit effective date; open/reopened period | Unapplication/correction is compensating evidence under accepted AP contract; no edit | Credit event/source/version + rule version + digest | Credit classification and tax/asset treatment required to activate |
| Disbursement evidence | AP; `accounts_payable.disbursement_recorded` / `disbursement_reversed`; only verified external evidence is eligible | `ACCOUNTS_PAYABLE_CONTROL` | Bank/cash/payment-clearing role | AP and bank/cash/clearing | Verified disbursement effective date; open/reopened period | Reverse only from verified void/return/stop/reversal evidence; unknown outcome queues | Disbursement event/provider identity + rule version + digest | Cash/clearing mapping and verification/approval policy required to activate |
| Sales-tax liability | Invoice line/revision tax facts plus enriched jurisdiction/agency posting component; current common event is incomplete | AR debit is part of invoice gross; credit memo/refund rules may debit liability | `SALES_TAX_PAYABLE` qualified by accepted jurisdiction/agency | Sales tax payable by jurisdiction | Invoice/credit approved effective date under effective tax policy; open/reopened period | Linked invoice credit/void/correction reverses exact original tax components | Invoice event + tax-policy version + jurisdiction component digest + posting rule | Jurisdiction/agency identity and liability-control mapping required to implement concrete tax rule and activate |
| Inventory financial adjustment | Inventory; smallest future fact `inventory.financial_adjustment_posted.v1`; current operational movements are insufficient | For positive value: `INVENTORY_ASSET`; for negative value: mapped variance/COGS role | Opposite mapped variance/COGS role for increase; `INVENTORY_ASSET` for decrease | Inventory asset/control | Authoritative financial effective date and valuation version; open/reopened period | Linked financial reversal referencing original movement/value fact | Company + financial event/movement identity + valuation/rule version + digest | `SOURCE_EVIDENCE_REQUIRED`; adapter is optional for initial engine but required before applicable Day-1 activation |
| Payroll summary | Payroll provider/summary owner; smallest future fact `payroll.summary_accepted.v1` | Versioned wage, employer-tax, benefit and other expense roles | Payroll liabilities, deductions, taxes, and cash/clearing roles | Payroll liability plus cash/clearing | Accepted pay-date/accrual effective date and covered period; open/reopened period | New linked corrected summary/reversal; never rewrite prior provider summary | Company + provider summary/version + rule version + evidence digest | `SOURCE_EVIDENCE_REQUIRED`; adapter is optional for initial engine but required before payroll Day-1 activation |

Events explicitly classified by an approved rule as nonfinancial—such as an
intent creation, authorization without capture, failed payment, vendor creation,
or Inventory transfer with no financial value change—receive a deterministic
`nonposting` outcome. An event is never nonposting merely because no rule exists.

## Finance seam

### Required to implement

No actual Company account number, QuickBooks value, or final mapping is required
to build the generic rule engine, registry, validator, queue, Core adapter, and
fail-closed behavior. Implementation does require the already accepted policy
shape:

- semantic account/control-role vocabulary and effective/versioned mapping API;
- single-functional-currency and configurable accounting-basis inputs;
- source-effective-date to Accounting-period selection with closed-period
  failure;
- immutable rule versions, canonical digests, reversal links, exact decimal
  balance, and Company/Branch boundaries;
- source schemas for each producer adapter actually included in the initial
  implementation; and
- no default account, suspense account, current-period shift, or inferred zero.

Payment and AP authoritative runtime event/receipt schemas are therefore
implementation prerequisites for their adapters. Actual Finance mapping values
are not prerequisites for the generic runtime if configuration absence is
tested to fail closed.

### Required to activate

- evidenced functional currency and accounting basis;
- accepted fiscal calendar, periods, close status, and timezone;
- active COA stable identities/classifications and effective account mappings;
- AR, AP, sales-tax, inventory, payroll, bank/cash, undeposited-funds, payment-
  clearing and opening control assignments as applicable;
- revenue/discount/write-off/refund/fee/variance, expense/asset/prepaid/fixed-
  asset, cash/clearing, tax jurisdiction and other source-role mappings;
- exact rule effective dates, rounding and correction treatment;
- Payment processor/merchant and settlement evidence configuration;
- named authorized system principal plus human preparer/reconciler/approver SOD;
  and
- zero unresolved configuration ambiguity for every event enabled at activation.

An adapter may remain disabled without blocking unrelated source domains. An
enabled adapter with a missing mapping blocks its event and activation; it does
not post to a default.

### Required only for cutover acceptance

- common-cutoff QuickBooks settings, COA, trial balance, GL/open-item and all
  applicable control workpapers;
- exact AR/AP, bank/cash, clearing, tax, inventory, payroll and opening-state
  zero-variance reconciliations;
- accepted immutable export/archive package, checksums, custody, retention,
  backup/restore and rollback evidence;
- repeatable rehearsal and complete posting/reconciliation queue disposition;
- named independent CPA, secure channel, checksum-bound approval, and distinct
  preparer/approver evidence;
- accepted financial statements and all required presentation decisions; and
- separate Preview, Production, import/cutover and final Owner go/no-go authority.

## Smallest missing source-fact contracts

### Inventory

Add one immutable public fact contract, not Inventory accounting logic:
`inventory.financial_adjustment_posted.v1`. It must carry event/source and
movement identity/version, Company/Branch, item/location, financial effective
date, signed quantity, evidenced unit cost and extended book value, currency,
valuation method/version, financial classification/mapping key, reason,
reversal-of link when applicable, canonical digest, correlation and evidence
reference. Transfer/reservation/location facts remain explicit nonposting facts.
Missing valuation is unknown, never zero.

### Payroll

Add `payroll.summary_accepted.v1` from the authoritative payroll-summary owner.
It must carry provider/company summary identity/version, ACP Company and approved
Branch allocation, covered period, pay/effective date, currency, exact aggregate
expense/liability/deduction/tax/cash components by semantic posting role,
balanced control totals, correction/reversal link, digest, correlation,
restricted evidence reference and approval evidence. It excludes employee-level
detail, credentials, bank accounts and raw payroll files.

### Tax

Enrich posting-eligible Invoice credit/issue/correction facts with immutable tax
components keyed by tax-policy ID/version and accepted jurisdiction/agency
identity: taxable basis, exact tax amount, currency, effective date, liability-
mapping qualifier, calculation digest and reversal/replacement link. The current
operational classification, rate and invoice tax amount are useful evidence but
do not identify the Accounting liability control by jurisdiction.

These contracts are not implemented here. Inventory/payroll adapters are
`NOT_REQUIRED_FOR_INITIAL_RUNTIME`; tax enrichment is required before enabling
Invoice tax posting, but the generic runtime can still be built fail closed.

## Migration and slot-5 parent condition

The current authoritative Enterprise Alembic head is `w8m0i2k4n619`. This
milestone creates no migration. Final order remains:

`Invoice slot 2 → Payment slot 3 → AP slot 4 → Posting slot 5`.

Before any slot-5 integration, fetch `origin/customer-management-v1`, prove
Payment and AP integrated in order or were explicitly migration-free, and
resolve exactly one current authoritative head. Any required ACC.POST.1 revision
must name that head as its parent and must contain only accepted posting-rule,
outcome/claim, or reconciliation-queue persistence not already owned by Core.
Implementation-time parent evidence is not integration authority. Sibling heads,
merge revisions, force-push, and silent semantic re-parenting are prohibited.
Mechanical re-parenting is allowed only before publication when DDL, data,
runtime and downgrade semantics are unchanged and full validation passes.

## Exact startability trigger

`ACC.POST.1` becomes startable—not activated—when all of these are true:

1. `PAY.1-3.ACCEL` and `ACC.AP.1` have authoritative accepted runtime commits;
2. their immutable event payload and posting-receipt contracts satisfy the
   canonical source envelope and are integrated after Invoice in slots 3 and 4;
3. authoritative Enterprise has exactly one Alembic head and no shared-seam
   collision;
4. the generic runtime may represent every unavailable actual account mapping
   as disabled/fail-closed configuration without guessing; and
5. Owner separately Starts the exact `ACC.POST.1` packet from a fresh fetched
   SHA/head.

Actual Finance account IDs, QuickBooks evidence, Inventory/payroll adapters and
activation-only mapping values do not need to delay generic runtime Start.
Their absence must block the affected rules/adapters and all Day-1 activation or
cutover claims. If Payment/AP runtime omits a contract-required source fact,
that omission is an implementation blocker and cannot be replaced by inference.
