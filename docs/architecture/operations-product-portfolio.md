# OM2-B operations product portfolio

This portfolio composes accepted Enterprise authorities; it does not create new
domain truth.

## Program disposition

| Program | Disposition | Evidence |
| --- | --- | --- |
| Asset and Fleet | AUTHORITY_GATE | No accepted native asset mutation authority or maintenance policy exists. |
| Mission Control | ACTIVE_OWNED | Enterprise owns runtime and protected integration. |
| Administration | ACTIVE_OWNED | Identity/authorization and readiness surfaces are concurrently owned. |
| Audit/Event experience | COMPLETED_SAFE_BOUNDARY | Existing immutable Audit API gains scoped server filters and visible UI. Business Events remain separate. |
| Notification Center | AUTHORITY_GATE | Notification outbox is delivery evidence, not an accepted user-notification inbox lifecycle. |
| Task/work queues | COMPOSED_EXISTING | Domain queues remain in their existing workspaces; no universal task engine is invented. |
| Document Center | AUTHORITY_GATE | Artifact access is domain-specific; a universal permission would violate ownership boundaries. |
| Enterprise Search | ARCHITECTURE_GATE | Cross-domain indexing and authorization-safe result existence need a separately accepted design. |
| Report Center | COMPLETED_SAFE_BOUNDARY | Visible navigation composes existing authoritative report projections. |
| Operator guidance | COMPLETED_SAFE_BOUNDARY | Recovery vocabulary is explained deterministically without AI. |
| Accessibility/responsive | COMPLETED_TOUCHED_SURFACES | New routes use responsive cards, semantic navigation, labels, status text, and focus styles. |
| Error/recovery consistency | COMPLETED_SAFE_BOUNDARY | Shared authoritative recovery classes receive operator-facing explanations. |
| Synthetic office day | STATIC_QUALIFIED | Navigation covers operational, sales, finance, supply-chain, workforce, audit, and recovery seams. |

## Audit history boundary

Audit filtering is server-side and always retains Company and authorized Branch
scope. Supported filters are actor, resource type, action, outcome, correlation,
Branch, and an exclusive occurred-before cursor. Responses retain only the
existing safe audit schema; IP address, user agent, credentials, secrets, and raw
domain payloads are not added.

## Integrated qualification

PostgreSQL-backed pagination, tenant isolation, and query-plan qualification are
`PENDING_INTEGRATED_DB_QUALIFICATION` when the isolated workstation cannot resolve
the configured `postgres` host. Static, unit, frontend, lint, type, and build
qualification remain locally executable.
