# Estimates Product Contract

- **Status:** Approved Version 1.0 product contract
- **Owner:** Sales
- **Depends on:** Foundation, Platform, CRM, Price Book, Jobs references

Architecture authority: [Sales Domain Architecture Brief](../../architecture/sales/domain-architecture-brief.md)
and [Operational Financial Boundary](../../architecture/financial/operational-financial-boundary.md).

## Product outcome and ownership

Sales owns the commercial proposal presented to a customer. An Estimate records
one or more controlled alternatives, immutable Price Book snapshots, explicit
discount and tax decisions, presentation history, expiration, and approval
evidence. Approval establishes a versioned commercial agreement for a Job; it
does not transfer ownership of the operational Job to Sales.

Sales alone writes Estimate state. Price Book supplies immutable inputs, CRM
supplies customer and service-location references, and Jobs validates the target
Job. No domain writes another domain's tables.

## Lifecycle

- `draft`: editable proposal not ready for presentation;
- `ready`: internally complete and pricing-valid but not yet presented;
- `presented`: delivered to the customer with a recorded presentation version;
- `approved`: one exact presentation and option selection was authorized;
- `declined`: customer declined the presented proposal;
- `expired`: its controlled expiration elapsed without approval;
- `superseded`: replaced by a later Estimate or revision;
- `cancelled`: withdrawn with actor, reason, and time.

Only `draft` is freely editable. Moving to `ready` calculates and freezes a
revision. Presentation creates immutable presentation evidence. A presented
Estimate may return to draft only through a new revision that preserves the
prior presentation. Approval, decline, expiration, supersession, and
cancellation are terminal for that revision. A correction creates a new
Estimate revision or successor rather than rewriting evidence.

Expiration is an explicit timezone-aware instant. A controlled process may
record `expired` after that instant, while approval validation must reject an
already expired presentation even if the status projection has not yet caught
up.

Every mutating command carries an expected concurrency version. Stale commands
fail without mutation or event publication.

## Alternatives and customer options

An Estimate can contain multiple labeled alternatives. Each alternative has an
ordered set of lines and independently calculated totals. Presentation makes
the available alternatives explicit. Approval identifies the presentation
revision, chosen alternative, included lines, quantities, totals, and any
customer selections. Unselected alternatives remain historical evidence and do
not become Job scope.

Estimate lines hold immutable Price Book snapshots or explicitly attributed
custom lines. A custom line requires authorization and a reason. Approval never
rewrites the source Price Book item, price version, or any other Estimate.

## Discounts and tax

Discount policies are configured facts, never hard-coded percentage or dollar
limits. A line- or Estimate-level discount records type, input value, calculated
amount, reason, requesting actor, applicable authority threshold, and approval
when required. A discount outside the requester's authority cannot move to
`ready` or `presented` until an authorized approver records an explicit decision.

Tax is calculated deterministically from the approved Company/Branch tax
configuration and each line's snapshot tax classification. The Estimate stores
the configuration/rule identity and calculated results needed to reproduce the
decision. A future tax-provider interface may supply the same normalized tax
decision without changing the Estimate aggregate.

## Approval evidence

Approval is append-only and must identify the exact presentation and selected
alternative. Supported evidence kinds are:

- authenticated digital approval;
- signature with protected artifact reference and integrity metadata;
- recorded verbal authorization with recording or call reference;
- administrator-recorded approval with customer attribution, administrator,
  reason, source, and timestamp.

Events and ordinary API projections contain evidence type and stable references,
not signature images, recordings, credentials, or sensitive free text. Evidence
storage and retention follow the enterprise security policy.

## Conversion to Job commercial scope

Approval requests creation of a Job-owned commercial-scope version through a
defined Jobs application interface. Sales supplies the approved Estimate,
revision, alternative, line snapshots, totals, tax decision, discounts, approval
evidence references, and correlation/idempotency identity. Jobs validates
Company, Branch, customer, service location, Job state, and duplicate conversion.

The transaction boundary must not permit an approved Estimate to appear
converted when Job scope was not established. Implementations may use one local
transaction through a stable interface or an outbox-driven handshake with an
explicit pending projection and retry; they may not perform untracked dual
writes.

## Authorization proposal

| Permission | Purpose |
| --- | --- |
| `COMPANY_ESTIMATE_READ` | Read authorized Estimate projections |
| `COMPANY_ESTIMATE_CREATE` | Create an Estimate and draft alternatives |
| `COMPANY_ESTIMATE_EDIT` | Revise eligible drafts and custom lines |
| `COMPANY_ESTIMATE_PRESENT` | Mark a validated revision presented and record delivery |
| `COMPANY_ESTIMATE_APPROVAL_RECORD` | Record customer approval evidence or decline |
| `COMPANY_DISCOUNT_APPROVE` | Approve discounts within configured authority |
| `COMPANY_ESTIMATE_CANCEL` | Cancel or supersede an eligible Estimate |

Approval recording does not grant discount approval. All commands retain Company
and Branch enforcement. These codes are proposals only.

## Proposed events

| Event | Safe payload core |
| --- | --- |
| `estimate.created` | Estimate ID, Company/Branch IDs, customer, location, Job, revision, actor |
| `estimate.presented` | Estimate ID, revision, presentation ID, expiration, delivery kind, actor |
| `estimate.approved` | Estimate ID, revision, presentation and alternative IDs, Job ID, total, currency, evidence kind/reference, actor |
| `estimate.declined` | Estimate ID, revision, presentation ID, actor and controlled reason code |
| `estimate.expired` | Estimate ID, revision, presentation ID and expiration instant |

Payloads omit contact details, signature/recording contents, internal notes, raw
provider responses, credentials, and unrestricted reasons. Existing event names
are reused where already reserved; live definitions are not changed here.

## Acceptance scenarios

1. A flat-rate service snapshot becomes a single-option Estimate and approves
   without modifying its Price Book version.
2. Good/better/best alternatives are presented and exactly one approved option
   becomes Job scope.
3. A discount over the requester's configured authority remains blocked until a
   distinct authorized approval is attributed.
4. Taxable and non-taxable lines produce a reproducible basis, tax, and total.
5. An expired presentation rejects approval and can be superseded by a new revision.
6. Concurrent edits fail through optimistic concurrency.
7. Every supported approval method links evidence to the exact presentation.
8. Duplicate approval or conversion requests are idempotent.

## Deferred work

Financing, external tax calls, electronic-signature vendor selection, dynamic
pricing, autonomous discounting, and inventory reservation are deferred.
