# QuickBooks Controlled Handoff

- **Status:** Approved Version 1.0 architecture contract
- **Initial transport:** Controlled export and reconciliation
- **Deferred:** Direct QuickBooks API integration

Financial calculation and aggregate authority is defined by the
[Operational Financial Boundary](operational-financial-boundary.md).

## Authority boundary

ACP Enterprise owns operational Customers, Jobs, commercial scope, Invoices,
Payments, Refunds, Credits, and Adjustments. QuickBooks owns accounting books,
accounting classifications, journal consequences, bank reconciliation, close,
and financial statements. Export success does not transfer operational authority
to QuickBooks, and QuickBooks reconciliation does not rewrite ACP source facts.

The handoff translates immutable operational projections into an approved export
schema. It does not create internal journal entries or simulate QuickBooks
accounting behavior.

## Export aggregate

`QuickBooksExportBatch` is a Financial integration aggregate with Company,
optional Branch selection, batch ID, schema version, cutoff/window, creation
actor, creation time, source-record manifest, artifact digest, lifecycle,
attempts, and reconciliation summary.

Recommended lifecycle:

- `draft`: selection can be validated but no immutable artifact exists;
- `prepared`: manifest and immutable artifact were produced;
- `delivered`: artifact delivery was attributed;
- `partially_reconciled`: some records are matched and exceptions remain;
- `reconciled`: every required record has an accepted result;
- `failed`: preparation, delivery, or reconciliation failed with classification;
- `superseded`: a controlled replacement batch covers the intended correction.

Preparing a batch snapshots only eligible source versions. The artifact includes
stable ACP record ID, record type, record version, Company/Branch, document
number, dates, currency, controlled amounts, customer/job references, prior
mapping when known, and operation kind. Sensitive customer data is minimized to
the approved QuickBooks import requirement.

## Identity mapping and duplicate prevention

`AccountingRecordIdentity` maps Company, ACP entity type and ID/version to the
external system code (`quickbooks`), external realm/company reference, external
record type and ID, first/last batch, and reconciliation state. Mappings are
append-only or versioned; changing an external identity requires an attributed
correction, not overwrite.

A source record version can appear as an original operation in at most one
prepared batch. Retry reuses the same batch identity and artifact digest. A new
batch may contain a compensating correction but cannot masquerade as a retry.
Import tooling must use stable ACP identity/version fields to detect duplicates.

## Reconciliation

Every manifest entry has one of:

- `pending`;
- `matched`;
- `accepted_with_warning`;
- `rejected`;
- `conflict`;
- `missing_external`;
- `duplicate_external`;
- `correction_required`.

A reconciliation result records the batch and entry, external identity when
known, source evidence/artifact, result time, actor, controlled classification,
safe detail, and whether retry is allowed. Batch completion derives from entries;
it is not asserted independently.

Owner-visible exceptions show operational record/document number, failure class,
safe explanation, retryability, responsible owner, age, and proposed action.
They never expose credentials, tokens, raw provider payloads, or unnecessary
customer information.

## Retry and correction behavior

- Preparation failure commits no `prepared` batch or export-success event.
- Delivery retry uses the same immutable artifact and idempotency identity.
- Reconciliation can resume without resetting accepted entries.
- Retryable technical failures remain distinct from data rejection and policy conflict.
- Source correction occurs through the owning ACP domain's append-only command.
- An issued Invoice or Payment is never edited to make export pass.
- Corrections export as explicit void, credit, refund, reversal, adjustment, or
  replacement operations linked to the prior source and mapping.
- A superseding batch preserves every earlier artifact and result.

No automatic retry may cause duplicate external creation. When the external
outcome is unknown, the entry becomes `conflict` and requires lookup or owner
review before another create attempt.

## Authorization proposal

`COMPANY_FINANCIAL_RECONCILE` permits review and controlled reconciliation
decisions. `COMPANY_QUICKBOOKS_HANDOFF_ADMIN` permits preparing, delivering,
retrying, and superseding export batches. Neither grants Invoice, Payment,
Refund, or accounting authority. These are proposed permissions only.

## Proposed events

| Event | Safe payload core |
| --- | --- |
| `quickbooks.export_prepared` | Company/Branch, batch ID, schema version, cutoff, entry counts, digest, actor |
| `quickbooks.reconciliation_completed` | Batch ID, completion time, matched/warning counts, actor |
| `quickbooks.reconciliation_failed` | Batch ID, stage, controlled failure class, retryable flag, exception count |

Individual customer data, line descriptions, credentials, file-system paths,
raw QuickBooks responses, and unrestricted error text are excluded. Catalog
integration is deferred to the designated owner.

## Future direct API seam

Transport is behind a provider-neutral `AccountingHandoffPort` that accepts a
versioned prepared manifest and returns normalized delivery and reconciliation
evidence. The initial implementation writes and controls export artifacts. A
future QuickBooks API adapter may implement the port without changing operational
aggregates, calculation rules, identities, idempotency, or exception semantics.

Credential storage, OAuth, webhooks, rate limits, and vendor-specific recovery
belong to that future adapter and enterprise integration-security review.

## Acceptance scenarios

1. An eligible Invoice and external Payment record produce one immutable batch.
2. Re-preparing with the same idempotency input returns the same batch and digest.
3. Delivery failure exposes an owner-visible retryable exception.
4. Retry cannot create a second logical export operation.
5. A partial reconciliation resumes without duplicating accepted records.
6. An unknown external outcome blocks blind retry.
7. A source correction exports a linked compensating operation.
8. A migrated historical Invoice exports only when provenance and eligibility
   policy permit it; absent issuance evidence is never invented.

## Explicit exclusions

This boundary implements no direct API, OAuth flow, journal entry, chart of
accounts, accounts payable, bank feed, bank reconciliation, close, tax filing,
payroll, or financial statement.
