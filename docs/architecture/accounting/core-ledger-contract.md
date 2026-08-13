<!-- markdownlint-disable MD013 -->

# Internal Accounting Core Contract

## Authority and scope

This is the normative Day-1 ledger contract beneath the
[Internal Accounting Day-1 Control Contract](day-1-control-contract.md) and
[ADR 0005](../adr/0005-internal-accounting-system-of-record.md). It freezes the
interfaces for `ACC.CORE.1`; it does not authorize runtime, migration, import,
Preview, Production, or cutover work.

ACP has one Company-owned general ledger. Branch is a Company-scoped accounting
dimension, never a second ledger or security tenant. The Company's functional
currency and accounting/book basis must equal the active QuickBooks company at
cutover. The source values require Finance evidence; this contract does not
guess them. Day 1 is single-functional-currency, with ISO 4217 currency codes,
fixed-precision decimal money, and no foreign-exchange accounting.

## Chart of Accounts and account identity

The Day-1 Chart of Accounts (COA) is the active QuickBooks COA without redesign.
Each account has an immutable ACP identifier and Company identifier; a unique
Company-scoped code; display name; top-level classification (`asset`,
`liability`, `equity`, `revenue`, or `expense`); normal balance; active/archive
state; effective dates; and optional control role. QuickBooks source company,
account identifier, code, type, subtype, and import checksum are retained as
immutable source identity. Renaming or archiving never reuses identity or code
and never changes historical lines.

A versioned COA snapshot records approval and effective time. Source identities
are unique within `(company, source system, source company, source account)`.
Account classifications drive debit/credit presentation; QuickBooks types and
subtypes remain evidence and are not silently normalized. An account and every
referencing object must belong to the same Company.

Control roles are orthogonal to account classification. At most one active
assignment exists for a Company, role, and effective instant. Day-1 roles are:

- accounts receivable control;
- accounts payable control;
- bank/cash by represented bank or cash account;
- undeposited funds;
- payment clearing by processor where required;
- sales-tax payable by required jurisdiction grouping;
- inventory asset/control;
- payroll liabilities by required liability grouping; and
- explicitly approved opening-balance controls.

Direct manual posting to a control account fails closed. An opening entry or
approved reconciliation correction may use one only with explicit authority,
reason, evidence, and independent approval. Control balances must reconcile to
their authoritative subledger or workpaper; an unexplained variance blocks
close and cutover.

## Journal and line model

A journal has immutable identity, Company, type, effective accounting date,
period, functional currency, source identity and digest, posting-rule version,
description, lifecycle, preparer, approver/poster, timestamps, and optional
reversal links. A line has immutable identity, journal, ordinal, account,
optional Branch dimension, debit, credit, description, and permitted source
dimensions. Lines cannot exist without their journal.

Each line has exactly one positive debit or credit and the other is zero. Every
journal has at least two non-zero lines; sums are calculated in currency minor
units using decimal arithmetic; total debits equal total credits and are
non-zero. A journal posts with all lines, provenance, audit evidence, and its
outbox event in one database transaction. An unbalanced, orphaned, partially
posted, cross-Company, invalid-account, wrong-currency, or closed-period journal
cannot post.

Branch is required when the authoritative source fact is Branch-scoped and must
belong to the journal Company. Company-level facts may use no Branch. Day-1
manual journals cannot span Branches. Automated cross-Branch posting fails
closed until an independently approved inter-Branch balancing policy exists;
no such policy is assumed here.

## Posting lifecycle, dates, and periods

The lifecycle is `draft → prepared → approved → posted`. A pre-posting journal
may instead be rejected or cancelled. Automated posting may perform authorized
transitions atomically; it remains subject to the same validation and durable
system-principal provenance. Only `posted` journals affect balances.

The effective accounting date selects exactly one non-overlapping Company
period. Occurrence, receipt, preparation, approval, and posting timestamps are
separate provenance and never substitute for the effective date. Period states
are `open`, `closing`, `closed`, and `reopened`. Posting is allowed only to
`open` or explicitly `reopened` periods. Entering `closing` blocks new posting;
the close operation serializes with in-flight posting, confirms balanced trial
balance and required control reconciliations, then closes atomically.

Reopening requires period-management authority, independent Finance approval,
a reason, and immutable audit evidence. Closed periods fail closed; neither an
administrator nor a posting retry may bypass the transition contract.

## Immutability, reversal, and correction

Posted journals and lines are append-only: no update or delete operation is
exposed. A reversal is a new balanced posted journal with equal opposite lines,
the same Company and dimensions, a stable link to the original, an authorized
reason, and its own provenance. A corrected result is another new journal.
Reversals use an open accounting period; they do not rewrite a closed period.
One active full reversal is allowed for an original journal. Partial correction
requires an explicitly balanced corrective journal and evidence, never line
editing.

## Source provenance, idempotency, and failure behavior

Every posting carries `(company, source system, source type, source identity,
posting-rule version)` plus a canonical source-payload digest. That tuple is
unique. Exact replay returns the prior result. Reuse with a different digest is
a conflict and posts nothing. Manual journals require a Company-scoped client
idempotency key. Source identity is durable even after a producer record is
archived.

Validation, account mapping, idempotency reservation, period check, approval,
journal and line insertion, platform audit staging, and Business Event outbox
staging share one transaction. Any failure rolls it all back, so there is no
partial financial state. A bounded failure record may be written only after
rollback and contains source identity/digest, deterministic error code, time,
and correlation identity—not journal lines or a false zero amount. Missing
mapping, amount, evidence, or control totals is an explicit failure and is never
interpreted as zero.

Database uniqueness is the final duplicate barrier. Period state and relevant
mapping versions are locked or equivalently serialized while posting. Close and
post races have one deterministic winner; retries observe the committed result.

## Trial balance and control invariants

The trial balance derives only from posted lines, grouped by Company, account,
effective date/period, and requested Branch dimension. Its debit and credit
totals must match and its net must be zero. No projection is financial
authority. Reporting may cache results only if it proves rebuildability and
freshness against posted journal identity.

At every close and cutover, AR, AP, cash/bank, undeposited funds, clearing, tax,
inventory, payroll, and opening controls each tie to their authoritative
subledger or signed workpaper. Absence of required evidence is a failure, not a
zero balance.

## Opening-state contract

`ACC.MIG.1` may submit deterministic `opening` journals only after its own
authorization. Each journal or deterministic batch is balanced and records the
QuickBooks source company/account identities, source-package and record
checksums, source close timestamp, ACP cutover timestamp, functional currency,
accounting basis evidence, accepted/rejected/dispositioned status, control
totals, import-run identity, and approval evidence. Rejected records cannot
post. Every disposition is explicit.

Replay uses the normal source tuple and digest contract. Exact replay is a
no-op; changed evidence conflicts. Aggregate opening control accounts must equal
accepted open items and workpapers with zero unexplained variance. Activation
requires distinct Finance Preparer and Independent Finance Approver identities
plus separate final owner authorization. The external accountant/CPA needs no
ACP application, Codex, repository, Mission Control, Preview, or development
access; their signed/checksummed approval artifact and identity are retained as
evidence.

## Authorization and separation of duties

`ACC.CORE.1` extends the existing ACP permission catalog; it must not create a
parallel role or authentication system. The exact minimum vocabulary is:

| Permission | Authority |
| --- | --- |
| `COMPANY_ACCOUNTING_READ` | Read Company accounts and posted ledger evidence |
| `COMPANY_ACCOUNTING_JOURNAL_PREPARE` | Create and prepare manual journals |
| `COMPANY_ACCOUNTING_JOURNAL_POST` | Approve/post an eligible prepared journal |
| `COMPANY_ACCOUNTING_PERIOD_MANAGE` | Begin close, close, or request reopen |
| `COMPANY_ACCOUNTING_JOURNAL_REVERSE` | Prepare reversal/corrective journals |
| `COMPANY_ACCOUNTING_RECONCILE` | Prepare control-account reconciliations |
| `COMPANY_ACCOUNTING_FINANCE_APPROVE` | Independently approve governed actions |
| `COMPANY_ACCOUNTING_OPENING_STATE_APPROVE` | Approve opening-state package evidence |
| `COMPANY_ACCOUNTING_REPORT_READ` | Read trial-balance/statement inputs and outputs |

All checks are Company-scoped and Branch-scoped where the operation carries a
Branch. Preparing and approving/posting the same manual, reversal, or opening
journal requires distinct human identities. A reconciler cannot independently
approve the same reconciliation. Period reopen requester/manager and Finance
approver are distinct. Permission possession does not waive these record-level
rules. `FINANCE_PREPARER` is the Owner; `INDEPENDENT_FINANCE_APPROVER` is the
Owner's external accountant/CPA; final cutover authority is the Owner. The two
Finance identities must differ at the final Finance gate. Post-cutover rollback
requires the owner plus independent Finance authority defined by the cutover
contract.

## API and Business Event boundary

Core application commands cover COA read/administration, manual journal
draft/prepare/post, reversal/correction, period read/close/reopen, and internal
trial-balance/control validation. They are authenticated Company APIs and use
the permission vocabulary above. No public Accounting API or external CPA login
is required. `ACC.CORE.1` owns no frontend; a later separately approved packet
may add an operator UI without changing these commands.

Domain producers never write Accounting tables. `ACC.POST.1` receives an
immutable source fact carrying Company, optional Branch, source tuple, canonical
digest, effective date, currency, monetary components, and correlation identity;
Accounting selects a versioned posting rule and mapping. Accounting publishes
outbox-backed facts for journal posted/reversed, period closed/reopened, and
posting failed. Event payloads contain stable identifiers, totals and outcome,
not secrets, bank credentials, or unrestricted descriptions. Platform audit and
Business Events are complementary evidence, not a second ledger.

## Downstream handoffs and close hooks

- `INVOICE.1-3.ACCEL` supplies finalization, credit/void/correction, revenue,
  tax, Branch, and AR-control facts with deterministic totals.
- `PAY.1-3.ACCEL` supplies payment application, refund, failure, deposit,
  clearing, undeposited-funds, processor, and settlement facts.
- `ACC.AP.1` supplies vendor bill, credit, expense/asset, AP-control, and
  disbursement facts.
- `ACC.POST.1` owns event-to-rule mapping, balanced posting orchestration,
  retry/failure handling, and producer adapters against this core.
- `ACC.RPT.1` reads immutable posted accounts, lines, periods, reversal links,
  and reconciliation status for GL detail, trial balance, statements, and aging
  ties. Core exposes close readiness as explicit pass/fail checks with missing
  evidence and unexplained variances, never default zeros.
- `ACC.MIG.1` uses the opening-state command and evidence contract above; it
  cannot bypass posting, permissions, idempotency, or balance invariants.

QuickBooks is not a runtime dependency after successful cutover.

## Execution and gates

The exact `ACC.CORE.1` boundary and validation contract is
[`acc-core-1-execution-boundary.json`](acc-core-1-execution-boundary.json).
Accounting owns its schema and repositories. Other domains interact only through
application commands or immutable facts. The first Accounting runtime migration
must descend from the fetched, single authoritative Enterprise head at its own
integration time. No sibling head, collision, merge revision, or silent
re-parenting is allowed.

Preview, Production, Finance, and cutover are separate gates. Core completion
does not authorize any of them. Preview requires separate owner authorization;
Production requires a separate Production authorization; the Finance gate
requires distinct preparer/independent-approver evidence; cutover requires all
controls reconciled with zero unexplained variance and separate final owner
authorization.

The still-required external inputs are evidence of the current QuickBooks book
basis and functional currency, the active COA/source identities, and named
Finance identities. They are data/Finance-gate inputs, not permission to invent
values and not blockers to implementing the generic core contract.
