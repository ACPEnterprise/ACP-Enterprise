# Price Book Product Contract

- **Status:** Approved Version 1.0 product contract
- **Owner:** Price Book domain within Sales
- **Depends on:** Foundation, Platform identity and policy

Architecture authority: [Sales Domain Architecture Brief](../../architecture/sales/domain-architecture-brief.md)
and [Operational Financial Boundary](../../architecture/financial/operational-financial-boundary.md).

## Product outcome

ACP Enterprise provides an authoritative Company- and Branch-aware catalog of
flat-rate service items that can be quoted consistently. A service item may
contain optional labor and material components and may participate in a
customer-selectable option group. The Price Book supplies controlled commercial
inputs; it does not own Estimates, Jobs, stock, purchasing, invoicing, payments,
or accounting.

## Ownership and scope

The Price Book domain owns categories, service items, option-group definitions,
price versions, tax classifications, effective dates, and lifecycle policy. A
Company owns every Price Book record. A service item or price version may be
Company-wide or restricted to one Branch. A Branch restriction must reference a
Branch in the same Company.

Other domains consume immutable Price Book projections through an application
interface. They must not read or write Price Book tables directly. Sales owns
the Estimate and copies an immutable commercial snapshot when a Price Book item
is selected. Later changes to the Price Book never rewrite that snapshot.

Version 1.0 includes:

- nested or flat categories with stable Company-scoped codes;
- flat-rate service items with customer-facing and internal descriptions;
- optional labor and material components used for explanation and job costing;
- option groups whose choices can be presented together on an Estimate;
- versioned prices, deterministic effective dates, and tax classification;
- `draft`, `active`, `inactive`, `superseded`, and `archived` lifecycles;
- immutable commercial snapshots when a price is used on an Estimate.

Version 1.0 excludes stock quantities, reservations, warehouse and vehicle
inventory, replenishment, purchasing, accounts payable, and general-ledger
postings. A material component is a costing and description input, not evidence
that an item is in stock or was consumed.

## Aggregate and lifecycle

`ServiceItem` is the aggregate root. It has a stable identity and code,
Company ownership, optional Branch restriction, category, lifecycle, display
content, and current-version projection. A `PriceVersion` has its own immutable
identity, currency, unit price, tax classification, effective interval,
components, and creation attribution.

Lifecycle meanings are:

- `draft`: editable and unavailable for new commercial selection;
- `active`: eligible for selection during its effective interval;
- `inactive`: temporarily unavailable for new selection but retained;
- `superseded`: replaced by another version and unavailable for new selection;
- `archived`: permanently unavailable for new selection and retained for audit.

Only a draft version may be edited. Activation validates ownership, currency,
components, effective dates, and absence of an overlapping active version for
the same item and Branch scope. Activating a replacement supersedes the prior
version transactionally. Inactivation and archival do not alter existing
Estimate, Job-scope, or Invoice snapshots.

Effective intervals use timezone-aware instants and a half-open
`[effective_at, expires_at)` convention. Missing `expires_at` means no scheduled
end. A caller supplies the business-effective instant; selection never guesses
from client-local time.

## Categories, options, and components

Categories organize discovery but do not determine authorization or tax.
Archiving a category does not delete its items or historical snapshots.

An option group is a presentation contract, such as good/better/best. It orders
compatible service choices but does not combine their prices or imply that the
customer approved all choices. Estimate approval identifies exactly which
option and lines were accepted.

Labor and material components have stable snapshot labels, decimal quantities,
unit cost inputs when authorized, and controlled component types. Component
costs are internal and must not appear in customer payloads unless an explicit
presentation policy permits them. Material components do not mutate physical
inventory.

## Price selection and snapshot

Selection requires Company, Branch, service-item identity, business-effective
instant, requested quantity, and currency. The domain returns one eligible
active version or a controlled failure. Branch-specific versions take
precedence over Company-wide versions only under an explicit deterministic
policy; ambiguous matches fail closed.

The Estimate snapshot records at least:

- service-item and price-version identities;
- Company and applicable Branch identities;
- stable item code and customer-facing description;
- quantity, unit price, currency, extended amount, and rounding policy;
- tax-classification code and relevant component snapshots;
- selected option-group and option identities when applicable;
- effective instant and snapshot creation attribution.

Snapshots are immutable. Correction requires an Estimate line revision, not a
Price Book mutation. Activating, superseding, inactivating, or archiving a price
never triggers historical recalculation.

## Authorization proposal

These proposed codes are not added to the live catalog in this milestone:

| Permission | Purpose |
| --- | --- |
| `COMPANY_PRICE_BOOK_READ` | Read eligible Price Book projections and historical references |
| `COMPANY_PRICE_BOOK_MANAGE` | Create and change categories, items, options, components, and drafts |
| `COMPANY_PRICE_BOOK_ACTIVATE` | Activate, supersede, inactivate, or archive price versions |

Every command also requires Company and Branch access. Read permission does not
grant access to internal cost components unless later policy explicitly permits
it.

## Proposed events

`price_book.price_version_activated` is the launch-critical event. Its safe
payload contains Company ID, optional Branch ID, service-item ID, price-version
ID, stable code, currency, effective interval, tax-classification code, and
actor ID. It excludes internal cost, free-form notes, customer data, credentials,
and full commercial snapshots.

Possible later lifecycle events use the same bounded payload convention. The
live Business Event catalog remains unchanged until integrated by its owner.

## Acceptance criteria

1. An authorized user can create a flat-rate service draft with optional labor
   and material components and activate a valid price version.
2. Company-wide and Branch-restricted selection is deterministic and tenant-safe.
3. Overlapping or ambiguous active versions fail without partial mutation.
4. An Estimate receives an immutable snapshot of the selected version.
5. Later Price Book changes do not change existing Estimate or Invoice totals.
6. Taxable and non-taxable classifications can coexist on one Estimate.
7. Customer options retain explicit ordering and independent approval identity.
8. No workflow asserts or mutates physical stock.

## Deferred work

Inventory balances, availability, reservations, vendors, purchase orders,
receipts, accounts payable, dynamic pricing, external tax integration, and
multi-currency conversion are deferred.
