# Customer Domain Foundation

- **Status:** Sprint 6 Milestone 3A implementation baseline
- **Domain owner:** Customer Operations
- **API version:** `/api/v1`
- **Last updated:** 2026-07-18

## Purpose

The Customer domain is ACP Enterprise's authoritative representation of the parties served by a Company, the people authorized to communicate for those parties, and the physical locations where service is delivered. Dispatch, estimates, jobs, assets, invoices, payments, agreements, communications, reporting, accounting, inventory, marketing, and AI workflows reference Customer and Service Location identifiers rather than creating competing identity records.

Customer is a long-lived enterprise aggregate. Application workflows change status or deactivate child records; they do not hard-delete operational history or reuse Customer Numbers.

## Aggregate model

```text
Company 1 ─── * Customer 1 ─── * Contact
                         └───── * Service Location
```

### Customer

Customer is Company-owned and includes:

- UUID `id`
- immutable Company-scoped `customer_number` in `CUS-000001` format
- status: `prospect`, `active`, or `inactive`
- type: `residential`, `commercial`, `municipal`, `hoa`, or `property_management`
- display and optional legal names
- optional primary Contact reference
- preferred contact method: `phone`, `sms`, or `email`
- optional marketing source
- tax-exempt indicator
- internal notes
- created and updated timestamps

Customer Number allocation uses a Company-owned PostgreSQL counter updated atomically in the Customer creation transaction. A committed number is unique within its Company and is never reassigned or accepted from API input. Different Companies maintain independent sequences.

### Contact

A Customer may have multiple Contacts. Contact stores first and last name, title, normalized email, normalized mobile and office phones, preferred and active indicators, notes, and timestamps. At most one active Contact may be preferred. The database partial unique index prevents duplicate preferred Contacts, while the service locks the Customer and clears the previous preference in the same transaction.

`Customer.primary_contact_id` points only to an active preferred Contact belonging to that same Customer. PostgreSQL validates this boundary through a trigger, and the Customer Service applies the corresponding lifecycle rule. Deactivating or unpreferring the primary Contact clears the Customer reference.

### Service Location

A Customer may have multiple Service Locations. Each location stores nickname, street address, optional second address line, city, state or region, postal code, ISO country code, optional GPS coordinates, billing-address-override indicator, gate code, property notes, active state, normalized address, and timestamps.

Future operational tables reference `service_locations.id`. A Service Location is deactivated rather than deleted when it is no longer available for new work.

## Tenant and authorization boundary

Every query and mutation receives a resolved Sprint 5 `AuthorizationContext`. Company ownership comes only from that context and is never accepted from request bodies. Repository lookups include `company_id`; a cross-Company identifier returns the same generic not-found response as an unknown identifier.

Customer endpoints require centralized catalog Permissions:

- `COMPANY_CUSTOMER_READ`
- `COMPANY_CUSTOMER_MANAGE`

Authentication establishes User identity. Authorization establishes active Company Membership and effective Permissions. Customer is Company-scoped rather than Branch-owned in Milestone 3A, so no Branch header is required. When a request supplies an active Branch through the platform context, emitted events retain that Branch identifier for operational traceability without changing Customer ownership.

## Service responsibilities

`CustomerService` is the only Customer mutation boundary. It owns:

- transactional Customer creation and numbering
- partial, idempotent Customer updates
- explicit status transitions
- tenant-scoped retrieval and listing
- Contact creation and update
- preferred and primary Contact enforcement
- Contact deactivation
- Service Location creation, update, and deactivation
- normalized search fields
- Business Event staging

Routers perform dependency composition, schema validation, response translation, and generic error mapping only.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/customers` | Company-scoped list/search with bounded pagination |
| `POST` | `/api/v1/customers` | Create and allocate the next Customer Number |
| `GET` | `/api/v1/customers/{customer_id}` | Retrieve Customer with Contacts and Service Locations |
| `PATCH` | `/api/v1/customers/{customer_id}` | Update mutable Customer profile fields |
| `PATCH` | `/api/v1/customers/{customer_id}/status` | Change Customer lifecycle status |
| `GET` | `/api/v1/customers/{customer_id}/contacts` | List Contacts |
| `POST` | `/api/v1/customers/{customer_id}/contacts` | Create a Contact |
| `PATCH` | `/api/v1/customers/{customer_id}/contacts/{contact_id}` | Update or deactivate a Contact |
| `GET` | `/api/v1/customers/{customer_id}/locations` | List Service Locations |
| `POST` | `/api/v1/customers/{customer_id}/locations` | Create a Service Location |
| `PATCH` | `/api/v1/customers/{customer_id}/locations/{location_id}` | Update or deactivate a Service Location |

Request schemas reject unknown fields. Company IDs, Customer Numbers, primary Contact IDs, audit fields, and normalized values are server-controlled.

## Business Events

State changes stage events through the existing `BusinessEventService` in the same transaction:

- `customer.created`
- `customer.updated`
- `customer.status_changed`
- `contact.created`
- `contact.updated`
- `contact.deactivated`
- `service_location.created`
- `service_location.updated`
- `service_location.deactivated`

Event payloads contain stable identifiers, status values, and changed-field names. They exclude Contact details, gate codes, notes, and other sensitive content.

## Forward migration policy

The original Customer Management revision `8f3c2d1a9b47` remains immutable. The Sprint 6 revision evolves the tables forward:

- legacy `individual` Customers map to `residential`
- legacy `business` Customers map to `commercial`
- legacy `do_not_service` status maps to `inactive`
- existing owned Customers receive deterministic Company-scoped numbers
- `customer_properties` is renamed to `service_locations` without changing record IDs
- legacy Contact and plumbing-location metadata remains available for future operational modules

The migration refuses to guess ownership. If any legacy Customer has a null `company_id`, migration stops with an explicit backfill requirement. Production rollout must first assign each such record to its correct Company through a reviewed forward-data migration or controlled backfill.

## Acceptance criteria

1. Authorized users can create, retrieve, search, and update Customers only in their active Company.
2. Customer Numbers are atomic, unique, sequential per Company, and not client-editable.
3. Concurrent Customer creation produces distinct numbers.
4. Invalid status and type values are rejected by API and database constraints.
5. Cross-Company Customer, Contact, and Service Location access fails closed.
6. At most one active preferred Contact exists and the primary Contact reference remains consistent.
7. Contacts and Service Locations can be deactivated without deleting history.
8. Unknown request fields are rejected.
9. Required Business Events commit atomically with domain changes.
10. Empty-database migration and schema-drift validation pass through the complete immutable revision chain.

## Deferred work

- Duplicate-customer matching, merge, survivorship, and householding
- Customer-level custom fields and segmentation
- Billing-account hierarchy and consolidated invoicing
- Location geocoding and address verification
- Customer portal and consent management
- Assets, jobs, estimates, invoices, agreements, and communications
- Frontend migration from the pre-identity Customer Management contract
