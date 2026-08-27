# ECO.MEASUREMENT.ADAPTERS.1 — Accepted domain-fact adapters

The first measurement adapters target contracts that exist and carry defensible
authority at this repository state. Accepted ACP `JobDetail` supplies explicit Job
identity/lifecycle context and, only when present, its exact `job_type_code` service
classification. Accepted immutable Accounting `PostingFact` supplies posting and
reconciliation evidence without reclassifying its components as revenue or cost.

Provider-neutral public operational assertions may enter the measurement boundary,
but their existing contract does not assert economic acceptance or carry a measured
value. The adapter therefore retains them as unaccepted `PARTIAL`/`UNKNOWN` evidence.
QBO assertions remain `quickbooks_online_source_reported`, unaccepted, and value-less
for measurement even when the source envelope reports an amount.

Every adapter requires an explicit Company, Branch, subject, and reconciliation
context and immutable package digest. Scope or identity mismatch fails closed. No
adapter discovers relationships from descriptions, timestamps, customer names,
provider IDs, or proximity.

Invoice/revenue acceptance, payment acceptance/application, measured workforce cost,
Job-linked material cost, other direct cost, and overhead adapters remain deferred.
Current public contracts do not establish their required economic acceptance,
costing policy, or authoritative Job linkage. Raw Migration evidence is never read.

Adapters emit normalized inputs compatible with the deterministic measurement gate.
They do not calculate contribution, profit, margin, leakage, allocation, forecasts,
rankings, or recommendations.
