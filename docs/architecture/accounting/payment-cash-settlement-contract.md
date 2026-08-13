<!-- markdownlint-disable MD013 -->

# Day-1 Payment, Cash, Refund, Deposit, and Settlement Contract

- **Milestone:** `PAY.CONTRACT.1`
- **Status:** Accepted implementation contract when this commit is authoritative
- **Runtime successor:** `PAY.1-3.ACCEL`
- **Cutover target:** 2026-08-21, subject to the separate cutover gates

## Authority and operating boundary

This contract specializes the [Day-1 control contract](day-1-control-contract.md),
the [AR/Invoice contract](accounts-receivable-invoice-contract.md), and the
[Core ledger contract](core-ledger-contract.md). ACP retains the existing external payment processor
for authorization, tokenization, capture, refund
execution, and money movement. The processor is not an accounting system of
record.

Payments owns ACP payment intent and receipt identity, provider references,
verified provider evidence, failures, refunds, unapplied receipt balances,
deposits, clearing, and settlement reconciliation. Invoicing owns AR obligation
and application/unapplication evidence. Accounting owns accounts, periods,
posting rules, journals, controls, and financial statements. No module writes
another domain's tables.

The selected existing processor adapter and merchant-account mapping are
deployment configuration requiring owner evidence. Runtime is provider-neutral
and fail-closed until that configuration, webhook credentials, and Finance
mappings are present. This contract does not choose or replace the processor.

## Security and payment-instrument boundary

ACP never stores PAN, CVV, magnetic-stripe data, raw bank credentials, provider
API secrets, signing secrets, or unredacted provider payloads. Browser or
provider-hosted tokenization sends payment instruments directly to the existing
processor. ACP may retain only an opaque provider token/reference, provider and
merchant-account identifiers, brand/type, expiration display metadata where
permitted, and a non-secret fingerprint suitable for duplicate detection.

Secrets live in the approved runtime secret facility, are never returned by an
API, logged, embedded in events, committed, or persisted as business evidence.
Every outbound processor call uses an ACP operation identity as the provider
idempotency key. Logs and audit evidence contain stable references and digests,
not instruments or credentials.

Webhook endpoints authenticate the raw request before parsing business data.
They verify the configured provider, merchant account, signature over the exact
raw bytes, timestamp tolerance, and endpoint/secret version. Unknown provider,
invalid or missing signature, stale timestamp, wrong merchant account, malformed
payload, unsupported event, or unavailable verification configuration is
rejected and causes no financial mutation. Secret rotation may accept explicitly
configured current and previous versions for a bounded overlap; verification
records which version succeeded without recording the secret.

## Identity and aggregates

All identities below are immutable UUIDs scoped by Company. Provider identities
are unique by `(Company, provider, merchant account, provider identity)`:

- **Payment intent:** one requested attempt to collect a positive amount in one
  currency for one Customer and optional Invoice. It owns the client
  idempotency identity, provider idempotency identity, amount, status, actor,
  authorization/capture references, and version.
- **Payment attempt:** append-only request/result evidence for authorization or
  capture. A decline or transport ambiguity is evidence, never a receipt.
- **Receipt:** immutable evidence of confirmed captured money. It owns original,
  applied, refunded, disputed, and available amounts as projections rebuildable
  from append-only receipt events.
- **Application:** Invoice-owned evidence linking a verified receipt amount to
  one invoice. Payments retains the command/correlation receipt, not a second AR
  application ledger.
- **Refund:** one requested processor refund and its append-only lifecycle. A
  provider acknowledgement is not completion; only verified succeeded evidence
  reduces the receipt's refundable amount and triggers AR/accounting handling.
- **Deposit:** a Company/Branch grouping of captured receipt evidence moving
  from undeposited funds toward a bank/clearing destination. It never fabricates
  processor settlement.
- **Settlement:** immutable provider payout/batch evidence containing gross,
  refunds, disputes, fees, adjustments, and net components plus constituent
  transaction references and evidence digest.
- **Reconciliation exception:** explicit unresolved missing, duplicate,
  contradictory, unmatched, late, or amount/currency variance evidence.

Human references are display values and never replace stable identities.
Provider payload retention uses a canonical allowlist plus SHA-256 digest of
the verified raw evidence; unknown sensitive fields are not copied.

## Lifecycle contracts

Payment intent states are `created`, `requires_action`, `authorized`,
`captured`, `declined`, `failed`, `cancelled`, and `expired`. The only success
that creates a receipt is verified capture. An ambiguous timeout remains
`requires_reconciliation`; it must be resolved by provider lookup/webhook before
retry. Runtime never assumes a failed response means no charge.

Receipt state is derived from capture, application, refund, dispute, and
settlement evidence: `unapplied`, `partially_applied`, `fully_applied`,
`partially_refunded`, `refunded`, `disputed`, or `reconciliation_required`.
Amounts satisfy, in one currency:

`captured = available + applied + refunded + disputed_or_reversed`

No component may be negative. Missing evidence is unknown, never zero.

Refund states are `requested`, `submitted`, `pending`, `succeeded`, `failed`,
`cancelled`, and `reconciliation_required`. A terminal state never moves to a
different terminal state. Late contradictory evidence opens an exception and
does not silently rewrite history. Deposit states are `open`, `submitted`,
`settled`, `reconciled`, `reversed`, and `reconciliation_required`.

Every mutable aggregate uses an expected version and row lock or equivalent
serialization. Stale, contradictory, scope-mismatched, or ambiguous commands
fail closed.

## Idempotency and duplicate-charge prevention

Every command has a Company-scoped idempotency key and canonical request digest.
Exact replay returns the original identity and outcome; reuse with different
canonical input is a conflict. Database uniqueness is the final barrier.

A collection request reserves its idempotency identity before any outbound
processor call and persists the stable provider idempotency key. Concurrent
requests for the same key have one winner. A retry reuses that provider key and
first reconciles any ambiguous prior attempt. It never creates a fresh charge
because a client timed out. Provider event identity and canonical evidence
digest are also unique; exact webhook replay is a no-op, while the same identity
with different evidence is a security/reconciliation exception.

Optional Invoice identity participates in duplicate-risk checks, but equal
amounts on the same Invoice are not automatically duplicates. Only an explicit
new operation identity can authorize another attempt. Runtime blocks capture
beyond the requested intent amount and does not auto-charge an open balance.

## Receipt application, partial payment, and overpayment

`INVOICE.1-3.ACCEL` exposes the accepted seam: Payments registers an immutable
verified `PaymentReceiptFact` with Invoicing.
Invoicing locks the receipt availability and Invoice, validates Company, Branch,
Customer, currency and open amount, then owns the application or compensating
unapplication. Payments calls only the accepted Invoice application command and
records its returned application/event identity. It never edits Invoice balance
or AR entries.

Partial applications are explicit and cannot exceed available receipt or open
Invoice amount. A receipt may be applied across multiple invoices for the same
Company, Customer, Branch policy, and currency through separate commands. Day 1
does not implicitly transfer money between Customers, Companies, currencies, or
unauthorized Branches.

Overpayment stays as an unapplied receipt balance. It is excluded from AR aging
and remains a cash/undeposited-funds plus customer-liability or accepted
Accounting-mapping fact until explicitly applied, refunded, or converted to a
customer credit by a separately authorized contract. Automatic netting,
automatic credit creation, and treating overpayment as revenue are prohibited.

## Refunds, failures, declines, and disputes

A refund requires a verified captured receipt, positive amount not exceeding
the unrefunded refundable balance, one currency, reason, actor, permission,
idempotency key, and provider operation identity. If applied money is refunded,
the relevant Invoice application must be compensated through Invoicing; the
refund cannot silently leave AR paid. The order is transactionally orchestrated
with recoverable state: reserve refund, obtain verified provider result, record
immutable result, request exact unapplication where required, emit facts, and
surface any partial failure as reconciliation-required. No evidence is deleted.

Declines and failed attempts record sanitized provider code/category, provider
identity when supplied, time, requested amount/currency, intent, correlation,
and digest. They create no receipt, AR application, or successful cash posting.
Transport ambiguity, late success, chargeback/dispute, and refund mismatch are
not classified as ordinary declines; each is explicitly reconciled.

Day 1 records dispute/chargeback evidence and reverses applications only through
compensating evidence. Automated representment, collections, and cross-currency
refunds are outside scope.

## Undeposited funds, deposits, clearing, and settlement

Verified capture creates a receipt and an undeposited-funds/processor-clearing
source fact according to the accepted Finance mapping. Creating an operational
deposit groups each eligible receipt exactly once and preserves constituent
identity. It does not claim bank settlement.

Verified settlement evidence is scoped to Company, provider, merchant account,
currency, payout/batch identity, and settlement date. Its invariant is:

`gross captures - refunds - disputes - fees +/- adjustments = net settlement`

Every component is fixed decimal and traces to verified provider evidence.
Each constituent is matched at most once. Net settlement must tie to the
provider payout and accepted bank/clearing control. Fees are separate components,
not reductions to customer receipts or AR. Unknown/missing constituents,
duplicate membership, currency mismatch, or nonzero variance creates an
exception and prevents `reconciled` status.

Manual deposits and statement/CSV settlement evidence require an authorized
actor, immutable source artifact digest, preparer evidence, and independent
reconciliation approval where the Accounting control contract requires it.
They cannot manufacture a capture or overwrite provider evidence.

## Accounting handoff

Payments publishes immutable, versioned source facts; `ACC.POST.1` alone maps
them to balanced journals. Required facts cover receipt captured, application
observed, application reversed, refund succeeded/failed, payment failed,
deposit submitted/reversed, settlement received/reconciled, dispute recorded,
and reconciliation exception opened/resolved. Each carries schema version,
event/source identity, Company, optional Branch, Customer where applicable,
provider/merchant references, effective date, currency, signed components,
canonical digest, correlation, and sanitized evidence reference.

Events contain no token, instrument, secret, raw webhook, or unrestricted
provider description. Accounting responds with its standard unique posting
receipt. Payments may project `pending`, `posted`, `reversed`, or
`reconciliation_required`, but cannot claim posted without that receipt.
Invoice application events remain Invoice authority; Payments correlates rather
than republishes them as a competing AR fact.

Control reconciliation proves receipt/application totals to AR, undeposited
funds and clearing to their control accounts, and settled net to bank/cash.
Provider fees, refunds, disputes, and variances each retain their own mapping.
Missing posting receipts or control evidence remain explicit exceptions.

## Isolation, permissions, and separation of duties

Storage, uniqueness, APIs, processor configuration, events, joins, application,
refund, deposit, settlement, and reconciliation are Company-scoped. Branch is
fixed where operational ownership supplies one and must be authorized. Wrong
Company, merchant account, Customer, Invoice, Branch, currency, or provider
reference is indistinguishable from not found.

The minimum centralized permission vocabulary is:

- `COMPANY_PAYMENT_READ` — read sanitized payment and reconciliation evidence;
- `COMPANY_PAYMENT_COLLECT` — create intent and submit authorization/capture;
- `COMPANY_PAYMENT_APPLY` — request Invoice application/unapplication;
- `COMPANY_PAYMENT_REFUND` — request an eligible refund;
- `COMPANY_PAYMENT_DEPOSIT_MANAGE` — prepare deposits and settlement matches;
- `COMPANY_PAYMENT_RECONCILE` — resolve reconciliation exceptions; and
- `COMPANY_PAYMENT_FINANCE_APPROVE` — independently approve governed refund,
  deposit, or reconciliation actions required by configured policy.

Refund requester and governed approver must differ when policy/threshold says
approval is required. Deposit/reconciliation preparer cannot independently
approve the same record. Accounting posting permission does not grant payment
collection/refund authority, and payment permission does not grant journal or
period authority. Platform authentication and audit remain authoritative.

## Day-1 exclusions and gates

Day 1 excludes processor replacement, card vaulting, PCI-sensitive storage,
automatic customer-credit conversion, cross-customer transfer, convenience
fees, recurring billing/subscriptions, payment plans, multi-currency conversion,
automated dispute representment, automated bank feeds, Accounts Payable,
payroll, and cutover/import execution.

The exact runtime boundary is
[`pay-1-3-accel.packet.json`](pay-1-3-accel.packet.json). Preview, Production,
processor credential activation, real transaction execution, data import, and
cutover each remain separately authorized gates.

Before Production activation the owner/Finance must evidence: existing processor
and merchant accounts; supported payment methods and capture mode; refund approval
threshold; webhook timestamp tolerance and secret-rotation procedure; provider
fee/refund/dispute/clearing/deposit mappings; undeposited-funds policy; settlement
timezone/cutoff; bank destination mapping; current QuickBooks basis; and named
preparer/approver identities. Missing inputs do not block fail-closed runtime
implementation, but they block real processor activation and cutover.
