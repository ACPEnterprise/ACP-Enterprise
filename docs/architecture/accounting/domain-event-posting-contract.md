<!-- markdownlint-disable MD013 -->

# ACC.POST.CONTRACT.1 — Domain Event to Accounting Journal Contract

## 1. Authority and boundary

This contract freezes the Day-1 boundary by which authoritative operational
financial facts become journals in the internal Accounting Core. It is governed
by the [core ledger contract](core-ledger-contract.md), the
[Invoice/AR contract](accounts-receivable-invoice-contract.md), and the
[Accounting integration control](integration-control.md). It was reconciled
against Core runtime commit `ee87e572d0f0e53fbc826978ab4d3a8ff489120a`
and Invoice/AR runtime commit
`43018e22786341116f77a606ccf70a8fa1e3ae14`, plus AP contract commit
`3f1a72cac91059b22a9d1f6d7909d73da7aeb174` and Payment contract commit
`0915317370a75f7b529b2f4c9b39f8dd228c78e3`.

This is a contract milestone. It does not implement `ACC.POST.1`, change domain
events, create a migration, deploy, access real QuickBooks data, enter Preview
or Production, or perform cutover. The exact implementation packet is
[`acc-post-1.packet.json`](acc-post-1.packet.json) and is `NOT STARTABLE` until
its producer-contract and policy dependencies are accepted.

## 2. Ownership and posting boundary

Source domains own business state and atomically stage immutable Business Event
facts with the mutation that made them true. Accounting owns posting-rule
selection, account/control mapping, journal construction, posting receipts,
failure/reconciliation state, and the ledger. A consumer never reconstructs a
financial fact from mutable display records, directly writes a source
subledger, or lets a source domain write Accounting tables.

The accepted Core already owns balanced journals, posting-source idempotency,
period controls, control-account assignments, reversals/corrections, audit,
posting failures, and Accounting outbox events. `ACC.POST.1` orchestrates those
public seams; it may not weaken their invariants or implement a second ledger.

## 3. Canonical source-fact envelope

Every posting-eligible event must provide, either in the immutable event
envelope or its versioned payload:

- event schema name and positive schema version;
- immutable event ID and source-domain aggregate type/ID;
- source aggregate version and canonical payload digest;
- Company ID and authoritative Branch ID, or explicit Company-level scope;
- occurred timestamp, accounting effective date, functional currency, and
  correlation ID;
- canonical signed amount components needed by the selected rule;
- stable related identities needed for subledger/control reconciliation;
- correction, reversal, application, or predecessor links when applicable; and
- an immutable evidence reference containing no payment instrument, credential,
  payroll-person detail, or mutable display-only data.

Missing, null, ambiguous, conflicting, unknown-version, or unevidenced fields
are not treated as zero. They produce a deterministic non-posting failure and a
reconciliation-queue item. Events with no financial effect may be acknowledged
as `nonposting` only by an accepted versioned rule—not by absence of mapping.

The current `BusinessEvent` envelope authoritatively supplies event ID, event
type, entity type/ID, Company, optional Branch, actor, JSON payload, correlation
ID, occurred timestamp, and creation timestamp. Its generic storage is transport
evidence, not permission to accept arbitrary JSON as an Accounting fact.

## 4. Authoritative source-fact inventory

### 4.1 Invoice and Accounts Receivable

The following event names are authoritative in current Invoice runtime:

- `invoice.created`;
- `invoice.issued`;
- `invoice.voided`;
- `invoice.credit_memo_issued`;
- `invoice.write_off_recorded`;
- `invoice.payment_applied`;
- `invoice.payment_application_reversed`; and
- `invoice.correction_replacement_linked`.

Invoice runtime atomically stages Company, Branch, event/entity/invoice identity,
customer identity, currency, subtotal, discount, tax, total, open amount, source
version, calculation digest, correlation, actor, and occurrence evidence. It
also accepts an Accounting posting receipt keyed by source event, containing
journal identity/version, policy version, status, effective date, and posted
timestamp. Conflicting receipt replay fails closed.

These fields are accepted source facts. Their existence does not by itself
authorize a debit/credit mapping. Before implementation Start, the accepted
Invoice fact must add or prove the accounting effective date, immutable evidence
reference, and the revenue/tax/control allocation facts needed by each posting
rule. Current common event payloads do not prove line-level revenue account
allocation, tax jurisdiction/control mapping, receipt amount for each payment-
application event, write-off account policy, or whether `invoice.created` is an
explicit nonposting event. Those are `AUTHORITATIVE PRODUCER FACT OR FINANCE
MAPPING REQUIRED`.

Minimum rule outcomes once those inputs are accepted are:

| Source fact | Required Accounting outcome; account identities remain versioned mappings |
| --- | --- |
| Invoice issuance | Debit AR control; credit mapped revenue and sales-tax liability for exact accepted components |
| Credit memo | Debit mapped revenue contra/adjustment and tax liability reduction as applicable; credit AR control |
| Write-off | Debit Finance-approved write-off account; credit AR control; tax correction only when authoritative policy requires it |
| Void/correction | Controlled reversal of the posted source journal plus replacement posting when applicable; never rewrite history |
| Payment application | Reduce AR and link the authoritative receipt/payment clearing or cash posting without duplicating cash recognition |
| Application reversal | Reverse only the prior application effect through linked journal evidence |

`invoice.created` is not assumed to post. `invoice.issued` is not postable until
its revenue/tax mapping inputs are complete. A posting receipt is written only
after the Accounting transaction commits; its absence leaves Invoice
`accounting_status` pending or reconciliation-required, never falsely posted.

### 4.2 Payments

The [Payment/cash contract](payment-cash-settlement-contract.md) now requires
these future `PAY.1-3.ACCEL` event facts:

- `payment.intent_created` and `payment.authorization_recorded`;
- `payment.receipt_captured` and `payment.failed`;
- `payment.refund_requested`, `payment.refund_succeeded`, and
  `payment.refund_failed`;
- `payment.dispute_recorded`;
- `payment.deposit_submitted` and `payment.deposit_reversed`;
- `payment.settlement_received` and `payment.settlement_reconciled`; and
- `payment.reconciliation_exception_opened` and
  `payment.reconciliation_exception_resolved`.

Posting facts carry schema/event/source identity, Company, optional Branch,
Customer where applicable, sanitized provider/merchant references, effective
date, currency, signed components, canonical digest, correlation, and sanitized
evidence. They exclude instruments, tokens, secrets, raw webhooks, and
unrestricted provider descriptions. Verified capture is the only receipt fact.
Invoice application events remain Invoice authority. Capture, application,
refund, dispute, deposit, provider fee, settlement, and reconciliation remain
separate linked facts so retries cannot double debit cash or double credit AR.

These are accepted contract facts, but `PAY.1-3.ACCEL` runtime is not yet
authoritative. No payment payload or result may be treated as implemented until
slot 3 integrates. Finance mappings for undeposited funds, clearing, bank/cash,
fees, refunds, disputes, and variances remain required. Legacy generic event
names such as `payment.received` do not supersede the accepted versioned
contract merely because they remain in the event catalog.

### 4.3 Accounts Payable and vendors

The [AP/vendor contract](accounts-payable-vendor-contract.md) now authoritatively
requires these future `ACC.AP.1` events:

- `accounts_payable.vendor_created` and `accounts_payable.vendor_mapped`;
- `accounts_payable.bill_approved` and `accounts_payable.bill_reversed`;
- `accounts_payable.vendor_credit_issued` and
  `accounts_payable.vendor_credit_applied`;
- `accounts_payable.disbursement_recorded` and
  `accounts_payable.disbursement_reversed`; and
- `accounts_payable.reconciliation_required`.

Posting events must carry schema version, stable event/source identity, Company,
optional Branch, vendor and AP document identity, effective date, currency,
canonical amount components, account-mapping/posting-rule version, digest,
correlation, and evidence reference. Bill approval creates one AP obligation
fact; only Accounting establishes the GL liability. Disbursement is distinct
verified settlement evidence. Credits, applications, reversals, non-PO facts,
Purchasing receipts, Inventory movements, and liabilities remain distinct.

These are accepted contract facts, but `ACC.AP.1` runtime is not authoritative.
No AP event payload or persistence may be treated as implemented until that
runtime integrates in slot 4. Finance mappings for expense, asset, tax,
inventory, AP control, cash/clearing, tolerances, and disbursement remain
required and fail closed. `ACC.POST.1` must not invent additional AP names or
fields.

### 4.4 Tax

Invoice runtime authoritatively supplies an invoice-level tax amount and the
Invoice contract requires invoice tax to equal the tax-liability posting basis.
Jurisdiction/agency, tax-code, taxable basis, rate/effective policy, liability
control mapping, filing-period, credit/refund, and rounding-disposition facts are
not yet authoritative. Tax posting is blocked until those mapping/source facts
are accepted. A missing jurisdiction or mapping is never assigned to a default
tax account.

### 4.5 Inventory financial control

Current Inventory events describe locations, transfers, reservations, and
releases. They do not prove a financial valuation adjustment. No inventory
receipt, material issue, cost adjustment, count variance, valuation method,
cost-layer, or offset-account posting fact is authoritative for this contract.
Inventory financial posting is `SOURCE CONTRACT REQUIRED`; operational transfer
events must not be treated as financial adjustments merely because they exist.

### 4.6 Payroll summaries

No authoritative payroll-summary posting event exists. Payroll period, gross
wages, employer expense, taxes, deductions, cash/clearing, liabilities,
adjustments, provider summary identity, and evidence digest are `SOURCE CONTRACT
REQUIRED`. The eventual fact must contain aggregate financial controls only and
must exclude unnecessary employee/person detail. Payroll remains an external
processor boundary; Accounting records its accepted summary journal.

## 5. Posting-rule registry

A posting rule is immutable and versioned by `(company, source event schema,
source schema version, rule version)`. It records effective-from and optional
effective-through dates, accounting basis, functional currency, required fact
fields, deterministic account/control mapping version, effective-date policy,
line-construction algorithm, rounding policy, reversal rule, and approval
evidence. Rule versions never change in place.

Rule selection uses the event's Company, schema/version, and accounting
effective date—not consumer time. Exactly one approved rule must apply. Zero or
multiple matches fail closed. An event before a rule's effective range cannot
use a later rule. Backdated facts must target the period containing their
approved accounting effective date; a closed/closing period fails closed and
queues for controlled Finance disposition. No automatic shift into the current
period is allowed.

Account resolution uses effective-dated Company mappings and named Core control
roles. Branch-scoped facts produce lines for that same authorized Branch.
Company-level facts may omit Branch only when the producer contract says so.
Day-1 journals cannot span Branches.

## 6. Deterministic posting transaction

For each accepted source fact, `ACC.POST.1` must:

1. claim or lock the immutable event without crossing Company scope;
2. validate its envelope, producer schema, payload digest, related source
   identities, currency, and Company/Branch authority;
3. select exactly one effective rule and mapping version;
4. derive an exact-decimal journal candidate and canonical line digest;
5. validate at least two nonzero lines, one positive side per line, equal debit
   and credit totals, active Company accounts, permitted controls, and one
   eligible open/reopened period;
6. in one database transaction create/resolve the Core posting-source key,
   journal and lines, automated approval/post evidence, audit evidence,
   Accounting outbox event, and durable posting outcome/receipt evidence; and
7. after commit, deliver the idempotent source-domain receipt through its
   accepted contract. Delivery failure retries the receipt; it never reposts.

The idempotency key is the Core tuple `(company, source system, source type,
source identity, posting-rule version)` with the canonical source digest. Exact
replay returns the original journal/receipt with zero new lines. The same tuple
with a different digest is a conflict and posts nothing. Concurrent duplicates
serialize to one result. A new source version is not automatically a correction;
it needs an accepted replacement/reversal relation and rule.

Atomic posting never leaves orphaned lines, partial journals, a posted receipt
without a posted journal, or a posted journal without provenance. Source-domain
mutation and its event are atomic at the producer. Accounting consumption is a
separate idempotent transaction; the durable event and receipt bridge that
boundary without distributed-transaction assumptions.

## 7. Corrections, reversals, and replay

Posted journals and lines remain immutable. A full correction creates one
linked opposite balanced reversal journal and, when required, a separate
corrective/replacement journal under the rule effective for the approved
correction date. Partial corrections create an expressly mapped balanced
corrective journal. The original event/journal, reversal event/journal, reason,
actor/system principal, source versions, rule versions, and correlations remain
linked permanently.

One active full reversal is allowed per original journal. Exact reversal replay
returns the prior reversal. A duplicate, stale, cross-Company, circular, or
unlinked correction fails closed. Closed-period correction requires the Core's
governed reopen path or a Finance-approved current-period corrective treatment;
software does not choose between them.

## 8. Failure and reconciliation queue

A posting attempt ends as `posted`, `nonposting`, `retryable_failed`, or
`reconciliation_required`. Retryable means a classified transient technical
failure with unchanged fact/rule/mapping identity. All semantic, balance,
period, mapping, source-evidence, digest, Company/Branch, permission, and
conflicting-replay failures require reconciliation and cannot auto-post.

The durable queue records Company/Branch, source event identity/version/digest,
rule/mapping version if selected, deterministic error code, first/last attempt,
attempt count, correlation, evidence reference, owner, status, disposition,
resolution event, and resulting journal/receipt identity. It must not copy
credentials, payment instruments, sensitive payroll detail, or arbitrary source
payload values into logs/errors.

Failure recording occurs after rollback in its own durable transaction when the
posting transaction cannot commit. Claiming uses lease/lock semantics with
expiry and deterministic retry. A worker crash before commit leaves no posting;
a crash after commit observes the Core idempotency record and emits/delivers the
same receipt. Queue dismissal cannot manufacture a posted state or unexplained
zero variance. Finance dispositions are append-only and auditable.

Reconciliation reports tie every eligible event exactly once to posted,
accepted-nonposting, retryable, or reconciliation-required status; every posted
event to exactly one active journal outcome; AR/AP/tax/inventory/payroll source
controls to their Core controls; and all reversals to their originals.

## 9. Permissions and separation of duties

The runtime consumer uses a narrowly scoped Accounting system principal with
event-read, rule-read, mapped automated-post, audit/outbox, failure-queue-write,
and receipt-delivery authority only for its Company/Branch. It cannot administer
the COA, mappings, rules, periods, roles, or its own permissions.

Rule/mapping preparation, approval, posting reconciliation, period reopen, and
Production/cutover authority remain distinct governed operations. The Finance
Preparer and Independent Finance Approver are different identities. Source-
domain permissions cannot grant Accounting-post authority; Accounting operators
cannot mutate source invoices, payments, bills, inventory, or payroll facts.
The independent CPA has no development, repository, Codex, or Preview role.

## 10. Migration and readiness

Current authoritative Enterprise has exactly one Alembic head,
`w8m0i2k4n619`. Migration ownership remains serialized:

`ACC.CORE.1 → INVOICE.1-3.ACCEL → PAY.1-3.ACCEL → ACC.AP.1 → ACC.POST.1 → ACC.RPT.1 → ACC.MIG.1`.

This contract owns no migration. `ACC.POST.1` may create at most one revision
for posting-rule/outcome/queue persistence not already owned by Core. At final
integration it must descend from the then-current single authoritative head
after all prior slots. A revision is not required merely to consume existing
Core persistence. Sibling heads, force-push, silent re-parenting, and unjustified
merge revisions are prohibited.

`ACC.POST.1` is not startable today. Core and Invoice/AR runtime plus the Payment
and AP producer contracts are accepted, but Payment runtime, AP runtime, tax
mapping facts, inventory financial-adjustment facts, payroll-summary facts, and
the Finance-approved posting-rule/mapping package remain blockers. Isolated
implementation becomes
eligible only after the packet's required dependency evidence is authoritative
and Owner separately Starts it. Preview, Production, and cutover remain separate
gates.
