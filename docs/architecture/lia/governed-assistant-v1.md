# Governed LIA assistant v1

LIA is ACP's interaction layer, not a second business system. Product LIA is
separate from the Development Factory's historical “Leadership Intelligence
Assistant” supervisory tooling.

## Authority order

Every request follows this order:

1. authenticate and resolve current Company, Branch and authorization version;
2. classify the requested capability and reject unsafe/exfiltration requests;
3. select only adapters whose domain read permission is present;
4. query those authoritative ACP boundaries inside the resolved tenant scope;
5. compose a structured answer with evidence, limitations and safe navigation;
6. emit safe audit metadata without prompt, answer or protected payload text.

Filtering after broad retrieval is prohibited. Conversation IDs convey continuity
only; each request re-resolves authorization. No transcript is durably retained
until the owner selects a retention policy.

## Truth and intelligence boundaries

Responses explicitly classify truth as `KNOWN`, `DERIVED`, `INCOMPLETE`,
`STALE`, `CONFLICTING`, `UNAVAILABLE`, `UNAUTHORIZED`, `POLICY_REQUIRED`, or
`EXTERNAL_GATE`. Deterministic ACP code owns arithmetic, filtering, source
selection, scope, provenance and action eligibility. A future model provider may
explain a bounded evidence package, but its text never becomes authoritative.

Business Economics remains authoritative for admitted profitability. Beacon
owns attention lifecycle. Luminary owns higher-order findings when its stable
adapter becomes available. LIA explains those products; it does not recompute or
mutate them.

## Action boundary

LIA can create a short-lived, deterministic, non-executing review proposal.
Purchase approval, payment, journal posting, payroll, scheduling and every other
business mutation remain in their domain service with its permission,
confirmation, separation-of-duties and idempotency contract.

## Provider and operations

The default provider state is `AI_PROVIDER_NOT_CONFIGURED`. Authorized
deterministic retrieval, evidence summaries, refusal and navigation remain
available. Provider secrets are backend-only. Configure or rotate them through
protected runtime configuration, never Git, frontend configuration or logs.

Ordinary telemetry contains request/correlation identity, actor/scope IDs,
classification, source-domain names, latency and evidence digest. It excludes
question/answer text, retrieved payloads, credentials and personal data.
