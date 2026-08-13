<!-- markdownlint-disable MD013 -->

# Accounts Payable and Vendor Accounting Contract

- **Milestone:** `ACC.AP.CONTRACT.1`
- **Runtime successor:** `ACC.AP.1`
- **Accounting authority:** ACP after separately approved cutover

## Authority and Day-1 boundary

This contract specializes the [Day-1 control contract](day-1-control-contract.md)
and [Accounting Core contract](core-ledger-contract.md). Accounts Payable (AP)
owns accounting vendor/payee identity, vendor bills and credits, AP open items,
applications, aging inputs, disbursement records, posting receipts, and control
reconciliation. Accounting Core owns the COA, accounting basis, functional
currency, periods, control accounts, journals, and posting invariants.

Purchasing owns operational Vendor, purchase order (PO), receipt, discrepancy,
and procurement lifecycle evidence. Inventory owns physical receipt movements
and operational valuation evidence. Payments owns any approved bank/processor
money-movement execution and settlement evidence. AP references those facts
through immutable public contracts; no domain reads or writes another domain's
private tables. A PO or receipt does not create an AP liability automatically,
and a bill does not prove receipt or move stock.

Day 1 includes vendor identity, bills, credits, AP subledger and aging,
duplicate prevention, controlled disbursement recording, expense/asset/control
mapping, corrections, Accounting handoff, authorization, and audit. Automated
procurement, vendor portal, electronic bill ingestion, bank payment initiation,
advanced three-way matching, landed cost, and real QuickBooks import are out of
scope.

## Vendor accounting identity

An `AccountingVendor` is Company-owned and has an immutable UUID, unique stable
Company code, legal and display names, active/archived state, payment terms
snapshot defaults, version, timestamps, and provenance. QuickBooks source
company/vendor identity and checksum are immutable mappings, never display-name
matches. Codes and identities are never reused; archiving never changes prior
bills or entries.

An optional mapping relates one AP vendor to one same-Company Purchasing Vendor
for an effective range. Purchasing identity remains authoritative for POs and
receipts; AP identity remains authoritative for liabilities, credits, aging,
and disbursements. Ambiguous, cross-Company, or contradictory mappings fail
closed. Vendor banking, tax identifiers, credentials, and unrestricted source
documents are restricted data and are excluded from general Business Events.
ACC.AP.1 records no bank credentials and initiates no payment.

## Vendor bills

A bill has immutable UUID; gap-tolerant, never-reused Company number; Company;
vendor; optional Branch allocation; vendor document number; bill and received
dates; due date; terms snapshot; functional currency; lifecycle; version; source
identity/digest; totals; and evidence references. Ordered lines snapshot
description, quantity/unit where applicable, net amount, tax/ancillary amount,
expense or asset account mapping, optional PO/receipt/version references, Branch
dimension, and mapping version.

Lifecycle is `draft → submitted → approved → posted`, with `rejected` or
`cancelled` allowed before posting and derived `partially_paid`, `paid`,
`credited`, or `reversed` states after posting. Draft content may be replaced
under optimistic concurrency. Approved/posted bill evidence and AP subledger
entries are append-only. Due date cannot precede bill date. Currency must equal
the Company's Accounting Core functional currency. Missing amount, vendor,
account mapping, evidence, or posting receipt is an error, never zero.

Bill approval atomically freezes the bill revision and creates exactly one AP
obligation fact. Only Accounting posting establishes the GL liability. AP
`accounting_status` is derived as `pending`, `posted`, `reversed`, or
`reconciliation_required`; it cannot become `posted` without an Accounting
posting receipt.

## Duplicate-bill prevention

Before approval, AP normalizes vendor document number without discarding the
original and checks at least `(Company, vendor, normalized vendor document
number)`. It also detects same vendor, bill date, currency, and total as a
possible duplicate when document identity is absent or changed. Exact stable
source identity and import identity are unique independently.

An exact idempotent replay returns the prior result. Reuse with a different
canonical digest is a conflict. A hard duplicate cannot be approved. A possible
duplicate requires a distinct authorized reviewer, nonblank reason, linked
evidence, and immutable override record; the preparer cannot approve their own
override. Blank or fabricated vendor invoice numbers cannot bypass checks.

## Vendor credits, applications, corrections, and reversal

A vendor credit is immutable vendor-level AP evidence with stable number/source,
date, currency, amount, reason, lines/account mapping, optional original bill or
Purchasing reference, and posting receipt. Issuance and application are separate
idempotent actions. Applications lock the credit and bill open items, remain
within available/open amounts, use the same Company/vendor/currency, and never
silently net across vendors or Branches. Unapplication is compensating evidence.

Posted bills and credits are never edited, deleted, or backdated into a closed
period. Correction uses a full reversal or balanced credit plus a replacement
bill linked to the original. A reversal is a new AP subledger entry and later a
new Accounting journal through the normal Core contract. Reversal of a bill
with applications requires controlled application reversal first. Tax,
inventory, and landed-cost consequences are not inferred.

## AP subledger, aging, and control

The AP subledger is an append-only stream of bill obligations, debit
adjustments, vendor credits, applications/unapplications, disbursement
applications/reversals, and corrections. Each entry carries Company, optional
Branch, vendor, currency, source type/identity/version, effective date,
idempotency key, signed amount, actor, correlation, evidence digest, and
Accounting posting status/receipt.

For every Company, currency, and as-of instant:

- open bills less unapplied vendor credits equal the AP subledger balance;
- the AP subledger balance equals the Accounting AP control balance;
- each aging row traces to one immutable obligation and all applications;
- aging uses due date and the accepted Company business timezone;
- unposted or failed handoffs remain explicit reconciliation exceptions;
- negative open bills and cross-vendor/Company/currency netting are prohibited;
  and
- missing evidence or reconciliation is never reported as zero.

Financial Reporting owns aging bucket presentation. AP supplies vendor, bill,
bill/due dates, original/open amounts, currency, Company/Branch, status, and
as-of inputs. Projections are rebuildable from subledger entries and never
become financial authority.

## Purchasing ownership seam

Purchasing may submit immutable PO and receipt facts containing Company/Branch,
Purchasing Vendor identity/version, PO/version/line, receipt/version/line,
currency, ordered/accepted/rejected quantities and units, agreed and received
cost evidence, discrepancy codes, occurrence time, digest, and correlation.
AP independently maps the vendor, classifies each bill line, validates bill
evidence, and decides whether a liability may be approved.

Day-1 matching is evidence-assisted and fail-closed, not an automatic
three-way-match policy. A bill may be non-PO only with explicit source kind,
reason, evidence, and authority. A PO-linked bill must not exceed or contradict
the immutable PO/receipt facts without an attributed exception and independent
approval. Tolerances, over-receipt, substitutions, freight, sales/use tax,
discount, rebate, landed-cost allocation, and capitalization policy require
Finance configuration; absent policy blocks the affected approval.

AP returns a stable handoff receipt with AP vendor, bill, credit/application,
status, source digest, and reconciliation exception identity. It never changes
the PO, receipt, Inventory movement, or procurement Vendor. `PUR.1` is not a
runtime dependency for AP's generic and non-PO foundations; Purchasing adapters
remain contract-only until separately authorized.

## Expense, asset, and control-account mapping

Every bill/credit line selects an active same-Company Accounting Core account
through an effective, versioned mapping with source and Finance approval. AP
control is selected by the Core control assignment; AP cannot post arbitrary
manual lines to it. Expense, prepaid, fixed-asset, inventory-asset, tax, freight,
discount, and other classifications must be explicit. Missing or ambiguous
mapping blocks approval.

Inventory receipt evidence does not authorize inventory-asset or landed-cost
posting without accepted policy. Capitalization, depreciation, recoverable tax,
1099/tax reporting, and sales/use-tax policy are not inferred. A mapping change
affects only later effective facts; historical bills retain their mapping and
posting-rule version.

## Disbursement recording

AP records an immutable disbursement fact only after receiving verified
authorization or settlement evidence from the approved money-movement owner.
It contains Company, vendor/payee, amount, currency, effective date, method
category, non-sensitive external reference, source identity/digest, actor,
approval, application allocation, and Accounting receipt. ACC.AP.1 does not
hold bank credentials, print/transmit checks, initiate ACH, or call a processor.

A disbursement application cannot exceed either verified available amount or
bill open amount. Partial payment is allowed and derived. Unapplied amounts are
explicit; they are not silently allocated. Void, return, stop, or reversal
creates compensating evidence and deterministically reopens affected items.
Unknown external outcome prohibits blind retry and becomes reconciliation
required.

## Accounting Core and GL handoff

AP writes its aggregate, subledger evidence, audit entry, and Business Event
outbox fact atomically. `ACC.POST.1` consumes the event idempotently and owns the
balanced journal. Events required from ACC.AP.1 are:

- `accounts_payable.vendor_created` and `accounts_payable.vendor_mapped`;
- `accounts_payable.bill_approved` and `accounts_payable.bill_reversed`;
- `accounts_payable.vendor_credit_issued` and
  `accounts_payable.vendor_credit_applied`;
- `accounts_payable.disbursement_recorded` and
  `accounts_payable.disbursement_reversed`; and
- `accounts_payable.reconciliation_required`.

Posting events carry schema version, stable event/source identity, Company,
optional Branch, vendor and AP document identity, effective date, currency,
canonical amount components, account-mapping/posting-rule version, digest,
correlation, and evidence reference. Accounting returns the Core posting receipt
containing source event, journal/version, status, mapping/rule version,
effective/posted dates, and failure state. Missing, duplicate, or contradictory
receipts are explicit exceptions.

Bill/credit approval and disbursement effective date must fall in an Accounting
Core period that accepts posting. Closed periods reject new or corrected facts.
Corrections use an open period; AP never reopens a period or bypasses Core SOD.

## Authorization, separation of duties, concurrency, and audit

ACC.AP.1 extends ACP's existing Company/Branch authorization. Exact permissions
are:

- `COMPANY_ACCOUNTS_PAYABLE_READ`;
- `COMPANY_ACCOUNTS_PAYABLE_VENDOR_MANAGE`;
- `COMPANY_ACCOUNTS_PAYABLE_BILL_PREPARE`;
- `COMPANY_ACCOUNTS_PAYABLE_BILL_APPROVE`;
- `COMPANY_ACCOUNTS_PAYABLE_CREDIT_MANAGE`;
- `COMPANY_ACCOUNTS_PAYABLE_DISBURSEMENT_RECORD`;
- `COMPANY_ACCOUNTS_PAYABLE_RECONCILE`; and
- `COMPANY_ACCOUNTS_PAYABLE_REPORT_READ`.

Bill/credit preparer and approver must be distinct. Duplicate override requester
and approver must be distinct. Disbursement preparer/source recorder cannot
approve the same disbursement. A reconciler cannot approve their own variance
disposition. Finance posting, period, and final approval permissions remain
Accounting-owned; holding multiple permissions never bypasses record-level SOD.

Every monetary mutation uses expected version and row locks for vendor/open
items, credits, applications, and duplicate identities. Database uniqueness is
the final replay/duplicate barrier. All reads, writes, joins, events, and
references are Company-scoped; Branch references must be authorized and in the
same Company. Scope mismatch is returned as not found.

Every mutation records actor, Company/Branch, before/after lifecycle, reason,
source and mapping versions, idempotency/correlation identity, timestamps, and
evidence digest in platform audit plus owned append-only evidence. Posted bills,
credits, applications, disbursements, subledger entries, events, and posting
receipts cannot be hard-deleted.

## Dependencies, gates, and Finance inputs

Accounting Core and Invoice/AR establish the accepted money, period, posting
receipt, subledger, aging, correction, isolation, and audit patterns. AP runtime
requires `ACC.CORE.1` and this accepted contract. `PUR.1` is optional for the
generic AP runtime; only a future Purchasing adapter depends on its accepted
public facts.

Before AP activation, Finance must supply current QuickBooks evidence for
functional currency/book basis, vendor identities, AP control, expense/asset/tax
and cash/clearing mappings, terms, duplicate normalization/override policy,
approval limits, matching/tolerance and non-PO policy, disbursement methods,
aging buckets, and authorized human identities. Unknown values remain
fail-closed configuration and do not authorize guessed defaults.

ACC.AP.1 is migration slot 4. It may be implemented only after owner Start and
may integrate only after slots 1–3 (`ACC.CORE.1`, `INVOICE.1-3.ACCEL`, and
`PAY.1-3.ACCEL`) are integrated or explicitly proven migration-free. Its one
revision must descend from the actual single authoritative head fetched at
implementation/integration time. Preview, Production, real-data import,
rehearsal, and cutover remain separate gates.

The exact execution boundary is
[`acc-ap-1.packet.json`](acc-ap-1.packet.json).
