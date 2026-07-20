# Customer Search and Timeline

## Purpose

Customer Search provides tenant-scoped discovery across the Customer aggregate. The Customer Timeline provides the canonical, read-only chronological view of activity associated with a Customer. Both capabilities build on the Sprint 6 Customer domain and the existing Platform security and Business Event foundations.

## Search architecture

`CustomerSearchService` accepts validated search criteria and delegates query construction to `CustomerRepository`. Every query includes the active Company identifier from `AuthorizationContext` and excludes archived Customers. Routers require `COMPANY_CUSTOMER_READ`; they do not evaluate permissions or tenant rules themselves.

Search covers Customer number, display and legal names, Contact names, normalized Contact email and phone values, and Service Location address, city, and postal code. Matching is case-insensitive and partial. Phone input is reduced to digits before matching normalized phone columns. Email input is lowercased before matching normalized email.

Contact and Service Location matching uses correlated `EXISTS` clauses. This avoids duplicate Customer rows and eliminates relationship loading for the result list. Boolean filters use the same pattern for preferred Contacts and active Service Locations. Count and page queries share the same predicates.

Sorting is limited to an explicit allowlist: Customer number, display name, creation time, update time, and status. Customer ID is a deterministic secondary sort key. Pagination returns `items`, `page`, `page_size`, `total_count`, and `total_pages`.

PostgreSQL `pg_trgm` GIN indexes support partial text search. Existing ownership, status, and normalized-value indexes remain useful for tenant filtering and exact matching. Search never falls back to an unscoped query.

## Timeline architecture

`CustomerTimelineService` reads directly from `business_events`; it does not create or duplicate timeline storage. An event belongs on a Customer timeline when it has the active Company ID and either:

- identifies the Customer as its entity; or
- carries the Customer ID in the standard `payload.customer_id` correlation field.

This convention allows new event types to appear without Timeline code changes. Events emitted by future authentication or access workflows will appear when they use the same Customer correlation field. Enterprise Audit records remain separate and are not copied into Business Events.

The repository query loads Business Events and optional actor Users in one operation, orders by occurrence time and event ID newest first, and paginates at the database. Composite indexes support direct Customer-entity events and payload-correlated events.

## Presentation and data safety

Timeline entries expose event time and type, actor identity when available, entity and resource identifiers, Company and optional Branch ownership, a human-readable summary, safe metadata, and correlation ID. Known event types receive concise operational summaries. Unknown future event types receive a deterministic humanized summary.

Metadata uses an explicit allowlist. Token values, credentials, gate codes, Contact details, arbitrary notes, and other unreviewed payload fields are never returned. Adding a metadata field requires an explicit safety review.

## Security invariants

- Authentication establishes the User; `AuthorizationContext` establishes the active tenant scope.
- `COMPANY_CUSTOMER_READ` is required for both search and timeline access.
- Customer ownership is verified before timeline events are queried.
- Company ID is mandatory in both Customer and Business Event predicates.
- Cross-company Customer existence is represented as an empty search result or generic not-found response.
- Branch metadata is descriptive; it does not broaden the caller's authorization scope.

## Extension contract

Business modules that create Customer-related activity should publish through `BusinessEventService`, retain their own entity type and resource ID, include the owning Company ID, and include `customer_id` in the payload when the Customer is not the primary entity. Payloads must remain free of secrets and should contain only the minimum information required for downstream consumers.
