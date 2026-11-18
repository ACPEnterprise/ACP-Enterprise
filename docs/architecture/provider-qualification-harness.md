# Provider qualification harness

## Certification rule

Provider support is always domain-specific. Authentication proves only that a
connection exists. A domain advances through `NOT_IMPLEMENTED`,
`IMPLEMENTED_UNQUALIFIED`, `QUALIFIED_SYNTHETIC`, `QUALIFIED_LIVE`, `PARTIAL`,
`BLOCKED_PROVIDER`, `UNAVAILABLE`, and finally `CERTIFIED`.

The common harness executes discovery, company identity and scope capture, paged
full acquisition, cursor resume, idempotent replay, count reconciliation,
quarantine accounting, immutable raw retention, normalization, crosswalk binding,
delta-control inspection, and digest-bound certification. Certifications are
append-only PostgreSQL evidence. A provider count must equal received plus
quarantined records; otherwise certification fails.

## First-wave mapping packets

ServiceTitan maps CRM customers/contacts, locations, settings employees and
technicians, JPM jobs/appointments, dispatch, estimates, pricebook,
invoices, and payments. The adapter uses client-credentials authentication,
provider page metadata/checkpoints, bounded retry for documented transient
responses, and polling/backfill drift detection until usable webhooks are
verified. Live qualification requires a registered app key, All County tenant ID,
tenant-approved environment-specific client ID/secret, and approved read scopes
for each mapped resource.

Jobber maps clients, properties, users, jobs, visits, quotes, invoices, payments,
products/services, and time sheets. Acquisition uses OAuth authorization code
with state and PKCE S256, rotating refresh tokens, an explicit dated GraphQL
version, cursor pagination, bounded retry, and webhook plus backfill drift checks.
Live qualification requires a Developer Center app, callback URL, exact read
scopes, a dedicated test account, and an authorized account connection. More than
five paying connected accounts requires Jobber approval.

Synthetic fixtures exercise two pages, interruption/resume, a malformed
quarantined row, exact provider counts, normalization, crosswalks, and certificate
generation for every mapped ServiceTitan and Jobber domain. They do not assert
that a provider endpoint is live.

Housecall Pro retained All County evidence is live source-acquisition evidence.
The protected vault is outside Git; the committed qualification projection uses
only the sealed, published counts and classifications. It does not reopen or
rewrite raw evidence.

QuickBooks Accounting remains implemented but unqualified live in this worktree:
the Accounting OAuth grant exists, but no complete retained API acquisition with
page/count proof is available here. Payroll is independently blocked by scope and
partner approval. Neither state is promoted from connection status.

Xero discovery covers organisation, contacts, accounts, invoices, payments, bank
transactions, journals/reports, and region-specific payroll fallback. Sage
discovery covers business, contacts, ledger accounts, sales/purchase documents,
payments, banking, journals/reports, and product/region-specific payroll fallback.
Neither adapter makes speculative live calls.

## MASTER contract

The customer projection exposes only migration ID, connected systems, simple
domain labels and progress, actionable exception count, next action, and cutover
readiness. It never exposes scopes, cursors, provider counts, digests, or
crosswalks.

The staff projection exposes company/run/provider, per-domain certification and
counts, quarantine/reconciliation state, errors, conflicts, retries, customer
actions, and certification readiness. Normal migration diagnosis therefore does
not require repository or terminal access.

## 200 migrations/month

The initial capacity envelope is 200 starts over 20 operating days: 10 average
starts/day and 30 peak starts/day. Provider/domain work items use tenant-fair
queues, per-tenant serialization where identity state can conflict, and four
workers per provider pool as the starting deployment value. Provider token buckets
are configured only from verified limits; no rate limit is invented.

Transient failures use bounded exponential backoff with jitter. Permanent or
exhausted failures retain their checkpoint and enter the staff exception queue.
Calls, bytes, latency, throttles, retries, and provider cost are metered by tenant,
provider, and migration run. A provisional 10% exception reserve is a staffing
assumption, not provider fact, and must be replaced by rolling production data.
