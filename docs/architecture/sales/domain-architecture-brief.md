# Sales Domain Architecture Brief

- **Status:** Approved for implementation planning
- **Release:** Version 1.0 commercial workflow

Product contracts: [Price Book](../../product/modules/price-book.md),
[Estimates](../../product/modules/estimates.md), and
[Invoicing and Payments](../../product/modules/invoicing-and-payments.md).

## Decision

Sales is a distinct bounded context that owns Price Book and Estimates. It turns
controlled catalog inputs into an explicit customer-approved commercial proposal.
It does not own the operational Job, Invoice, Payment, inventory, or accounting.

```text
Price Book ──immutable selection snapshot──► Estimate
Estimate approval ──approved agreement──► Jobs commercial scope
Jobs commercial scope ──invoiceable snapshot──► Financial
Financial export ──controlled handoff──► QuickBooks
```

Each arrow is an application contract or durable event, never a cross-domain
table write. The modular-monolith deployment does not relax aggregate ownership.

## Aggregate boundaries

Price Book owns `ServiceItem`, `PriceVersion`, category, option group, component,
and tax-classification references. Estimate owns proposal revisions,
alternatives, line snapshots, discounts, tax decisions, presentations,
expiration, and approval evidence.

Jobs owns `JobCommercialScope`, described below, after accepting an approved
Estimate. Sales retains provenance and approval evidence; it does not update the
Job table or scope tables directly. Financial consumes scope projections and
does not read Sales tables to calculate an Invoice.

## Job commercial scope contract

The Jobs domain owns a versioned commercial agreement attached to a Job. Each
scope version contains:

- immutable identity, Company/Branch/Job/customer/location scope, and version;
- source Estimate, revision, presentation, alternative, and approval references;
- ordered commercial line snapshots and optional internal component snapshots;
- currency, subtotal, discounts, taxable basis, tax, total, and rounding policy;
- customer-approval evidence references and establishment attribution;
- effective time, superseded-version reference, and concurrency version.

The first accepted approval establishes version one. It is immutable. The Job's
current-scope pointer may advance only after a controlled change order is
approved. Historical versions remain addressable for audit, Invoice provenance,
and dispute resolution.

Jobs continues to own operational status, appointments, assignments, notes,
work execution, and completion. Commercial scope does not turn Estimate status
into Job status or allow Sales to perform operational transitions.

## Change orders

A change order is a proposed successor commercial-scope version. It references
the prior scope, identifies additions/removals/quantity or price changes, records
recalculated totals, and requires customer approval evidence under the same
standards as an Estimate. Work policy may permit emergency performance before
approval only if separately approved; no such exception is granted here.

Approval creates the successor atomically and supersedes the current projection.
Existing Invoices retain their source scope version. The Financial domain decides
whether later approved changes require a new Invoice, supplemental Invoice, or
authorized adjustment; it never rewrites an issued Invoice.

## Materials used

Jobs owns actual materials-used capture because consumption is an execution fact.
Each append-only entry identifies Job, scope/version when applicable, material
code or snapshot description, decimal quantity, unit-of-measure code, unit-cost
snapshot when authorized, occurrence time, actor, and correction relationship.

Materials used support job costing and Luminary projections. They do not assert
warehouse or vehicle availability, decrement stock, create purchase demand, or
post accounting entries. Future Inventory consumes these facts through events or
an application interface.

## Money value contract

All domains use the rules in
[Operational Financial Boundary](../financial/operational-financial-boundary.md).
A boundary message carries normalized decimal strings or typed decimal values,
never binary floating-point values. Producers include currency, scale, rounding
policy, source versions, and invariant-checked totals. Consumers reject
contradictory messages rather than repairing them silently.

## Transaction and integration policy

Within the modular monolith, one orchestrated database transaction may call
public application interfaces owned by multiple domains when transaction
ownership is explicit. Repositories remain private. Where asynchronous handoff
is used, the source commits state and an outbox event atomically; consumers are
idempotent and expose pending/failure state. No workflow treats event publication
alone as proof that downstream state exists.

## Authorization and events

The product contracts propose granular Price Book, Estimate, discount, Invoice,
Payment, and reconciliation permissions. Platform remains authoritative for
permission resolution and Branch access. Sales never infers authority from job
title, role name, UI visibility, or prior behavior.

Proposed Sales events are `price_book.price_version_activated`,
`estimate.created`, `estimate.presented`, `estimate.approved`,
`estimate.declined`, and `estimate.expired`. Jobs proposes
`job.commercial_scope_established` and `job.change_order_approved`. Catalog
integration is reserved for the Original Office Machine authority.

## Implementation slices

1. Price Book persistence and APIs.
2. Price Book frontend administration and selection.
3. Estimates operational aggregate and APIs.
4. Estimate frontend presentation and approval.
5. Jobs-owned commercial-scope integration and change orders.
6. Operational Invoice lifecycle.
7. Provider-neutral Payment lifecycle.
8. QuickBooks controlled export and reconciliation.
9. Materials-used costing without inventory balances.
10. Business Economics and Luminary projections.

Each persistence slice owns one migration at integration time. Shared event,
permission, application-router, frontend-router, and navigation changes are
integrated sequentially by their designated owners.

The known collision surfaces are `backend/alembic/versions/`,
`backend/app/platform/permissions/codes.py`,
`backend/app/platform/permissions/catalog.py`,
`backend/app/events/types.py`, `backend/app/main.py`,
`frontend/src/layout/navigation.ts`, `frontend/src/routing/router.tsx`, and
`frontend/src/routing/routeMetadata.ts`. Estimate, Invoice, Payment, Beacon, and
migration work also currently converge on `backend/app/financials/` and
`backend/app/operational_migration/`. Domain branches must not edit a shared
surface merely for convenience. The Original Office Machine authority sequences
permission and Business Event catalog integration; a designated migration owner
rebases each new revision onto the then-current single Alembic head.

Price Book must stabilize before operational Estimates consume it. Estimate
approval and Job commercial scope must stabilize before Invoice implementation.
Payment and QuickBooks handoff follow immutable Invoice issuance. Materials-used
capture may be implemented alongside the later Financial slices after its Jobs
ownership and unit-of-measure contract are approved. Luminary follows validated
operational sources and must never convert missing facts into zero values.

## Cross-domain acceptance scenarios

1. **Flat-rate service Estimate:** an active Branch-eligible price version is
   snapshotted, presented, approved, and converted to one Job scope without later
   Price Book changes altering it.
2. **Multiple customer options:** good/better/best alternatives remain distinct;
   approval identifies one exact option and only its lines establish Job scope.
3. **Discount requiring approval:** a discount beyond the requester's configured
   threshold cannot be presented until an authorized approver is attributed.
4. **Mixed tax:** taxable and non-taxable lines retain classifications and
   reproduce subtotal, taxable basis, tax, and total using one recorded policy.
5. **Estimate approval:** authenticated, signature, verbal, or administrator-
   recorded evidence binds to the exact presentation and is safely referenced.
6. **Estimate expiration:** approval after the expiration instant fails even if
   an asynchronous status projection has not yet changed to `expired`.
7. **Change order:** an approved successor scope preserves the prior scope and
   does not rewrite an Invoice already issued from it.
8. **Partial Invoice payment:** one eligible Payment reduces balance and projects
   `partially_paid` while preserving issued totals.
9. **Multiple Payments:** distinct idempotency and external identities permit
   several Payments to satisfy one Invoice without duplication.
10. **Recorded external Payment:** attributed external evidence creates one
    provider-neutral Payment without storing sensitive payment credentials.
11. **Refund:** an append-only partial or full refund cannot exceed remaining
    eligible settled value and does not mutate the original Payment amount.
12. **Invoice void:** an authorized void retains issuance, number, amounts,
    reason, actor, and replacement relationship while removing collectible state.
13. **QuickBooks failure and retry:** a failed export exposes a classified
    owner-visible exception; retry reuses the same batch and immutable artifact.
14. **Migrated historical Invoice:** source state and confidence are visible,
    missing issuance/payment evidence is not invented, and the record remains
    read-only unless explicitly adopted under a later reviewed policy.
15. **Materials used without inventory:** a Job records actual material quantity
    and cost snapshot for profitability without asserting or changing stock.

These scenarios require tenant, Branch, authorization, concurrency, atomicity,
idempotency, and audit assertions in later runtime test suites.

## Acceptance boundary

The domain is ready for downstream implementation when Price Book selection is
deterministic, Estimate calculations reproduce, approval identifies one exact
presentation, Job scope conversion is idempotent, and no mutation crosses a
repository ownership boundary.
