# LIA owner intelligence read-only v1

`LIA.OWNER.INTELLIGENCE.READONLY.1` extends the existing governed LIA boundary; it does not create a parallel assistant or domain model.

## Read-only evidence flow

The deterministic question planner selects explicit registered domains. Request-time `AuthorizationContext` restricts those domains before retrieval, and each adapter applies Company and Branch predicates before reading evidence. Customer and Job entity questions continue through their source-owned minimum-necessary projections. Service Location evidence remains part of the Customer projection because a Location does not independently establish tenant ownership.

Responses bind an authority classification, Company and Branch scope, subject, source systems, evidence digests, as-of time, missing evidence, limitations, and a safe navigation or refresh action. `SOURCE_BACKED` evidence is never promoted to `ACP_AUTHORITATIVE`. Missing, conflicting, stale, or unavailable evidence remains explicit.

Follow-up context carries the authorization version and prior evidence digest. Changed authorization fails before retrieval. Changed evidence returns `STALE` with refreshed evidence instead of silently continuing from the earlier answer.

## Supported owner evidence families

The current bounded registry covers Customer/Location, Job, Scheduling, Dispatch, Estimates, Invoices, Payments, Workforce, Timekeeping, Payroll readiness, Accounting period readiness, Price Book readiness, Data Quality, Audit, launch readiness, Beacon, Economics, Luminary, and Migration/source evidence. Cross-domain questions compose evidence references but do not claim an unproved relationship or causality.

Accounting access is readiness-only here. LIA does not invoke financial-report generation because that workflow can record posting failures; it therefore cannot violate this milestone's strict no-mutation boundary. QBO evidence remains behind Migration authority and is labeled source-backed.

## Safety and remaining boundaries

The LIA runtime has no persistence, domain command, provider call, or executable tool path. It cannot schedule, dispatch, post, pay, change Payroll, activate pricing, alter permissions, or mutate a source record. Protected Payroll, banking, credentials, cross-Company, and unauthorized Branch requests fail closed.

Exact financial statements, detailed source acquisition completeness manifests, and free-form generative answers remain unavailable until their owning source contracts or a separately approved provider admission exist. Conversation retention remains policy-required; current follow-up continuity is request-bound and non-durable.
