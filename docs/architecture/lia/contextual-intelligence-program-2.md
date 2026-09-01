# LIA contextual intelligence program 2

## Authority boundary

`LIA.CONTEXT.v1` is the common request-time binding for contextual intelligence.
The browser supplies only a domain and opaque entity identity. The owning domain
resolves Company and Branch scope from the current `AuthorizationContext` before
retrieval. A returned reference binds the source contract version, Company,
authorized Branch set, authorization version, evidence digest, observation time,
freshness, and explicit limitations. A stale browser context or foreign UUID does
not reveal whether a protected entity exists.

The contract is minimum-necessary and read-only. It neither provides unrestricted
ORM access nor grants mutation authority. Every request revalidates Membership,
permission, Company, Branch, and source-domain predicates on the server.

## Context sources

- `CUSTOMER.LIA_CONTEXT.v1` includes the Customer display label and lifecycle,
  bounded authorized Locations and Jobs, and permission-gated Estimate, Invoice,
  and Service Agreement state counts. It excludes contacts, payment instruments,
  raw notes, attachments, and unrestricted history.
- `JOB.LIA_CONTEXT.v1` includes Job lifecycle, priority and version; optionally
  Customer and Location labels; up to 10 linked appointments; and permission-gated
  Dispatch, Estimate-origin, Invoice, and Payment-receipt states. It excludes raw
  Customer/Job text, technician details, amounts, provider data, and source-domain
  mutation controls.
- Scheduling, Estimate, revenue-cycle, Purchasing, Inventory, Economics, Luminary,
  Beacon, Migration, Payroll readiness, and system-readiness summaries continue to
  use their accepted bounded adapters. Counts are evidence, not inferred urgency,
  settlement, revenue, valuation, or causality.
- Asset/Fleet remains `SOURCE_REQUIRED` until its owning lane publishes an accepted
  read projection. Workforce expansion remains owned by its active domain lane.

Payroll own-statement retrieval already performs server-side active
Membership-to-Employee resolution and never accepts an Employee identity from the
client/model. Its older foundation registry declaration remains conservatively
blocked until that separately qualified contract is versioned; administrative
Payroll metadata remains separately permission-gated and protected amounts are not
projected.

## Truth and safety

Missing evidence remains unavailable or incomplete. Conflicting evidence is not
collapsed. Transaction, service, posting, and settlement dates remain distinct in
their owning sources. LIA does no financial recomputation and does not infer that a
does not infer that a Payment receipt settles an Invoice.

All source text is untrusted data. It cannot change system policy, permissions,
scope, tools, or action authority. High-impact requests remain unavailable unless
an exact separately accepted action contract exists. Provider state remains
`AI_PROVIDER_NOT_CONFIGURED`; deterministic answers continue without a provider.
No transcript retention policy is invented and hidden reasoning is never persisted.

## Performance and navigation

Context retrieval uses bounded grouped queries: at most 10 Customer Locations, 10
Customer Jobs, and 10 Job Appointments. It does not load whole histories. Safe
navigation returns to the owning ACP route and never exposes database or filesystem
locators.
