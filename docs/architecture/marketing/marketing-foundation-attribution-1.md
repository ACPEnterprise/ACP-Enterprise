# MARKETING.1 — Marketing Foundation & Attribution

Status: `ARCHITECTURE_DEFINED`

## Purpose

Establish one evidence-backed acquisition and contribution chain without
creating a competing Lead, Customer, Job, Invoice, Payment, or Accounting
authority.

`acquisition source -> Lead -> Customer -> Estimate -> Job -> Invoice -> Payment -> gross profit -> marketing contribution`

## Authority boundaries

- Pipeline owns Lead lifecycle, source attribution attached to a Lead, CSR ownership, and next action.
- Customer owns canonical Customer identity and prospect-to-Customer binding.
- Estimates, Jobs, Scheduling, Invoices, Payments, Accounting, and Economics remain their source authorities.
- Marketing owns campaign identity, attribution evidence, source-specific reporting, and contribution projections.
- A fuzzy match may propose a candidate but never establishes identity or attribution.

## Source and campaign identity

Every admitted acquisition event must carry a stable source event identity,
source type, campaign identity when supplied, observed timestamp, landing or
tracking context, and an evidence digest. Supported source classes are
organic, paid search, paid social, referral, partner, website, phone/tracking
number, direct, and unknown. Unknown is explicit; it is never silently mapped
to direct.

Tracking numbers are campaign/source evidence only. They do not determine
Customer identity or Lead status. Duplicate inbound events require a stable
provider/event key and idempotent disposition.

## External boundaries

- Google Ads: provider-neutral click/conversion evidence only; no spend or conversion claim without admitted provider evidence.
- Search Console/SEO: impressions, queries, and landing evidence; not a Customer or revenue authority.
- GBP/local: profile/call/website referral evidence; no implied booking or attribution without a matching admitted event.
- Yelp/Angi: provider lead IDs and disposition evidence; no fuzzy Customer binding.
- Website/landing pages: UTM/campaign/referrer capture and consent-aware event intake; no direct mutation of Pipeline.

## Marketing economics

Marketing may report spend, attributed opportunities, conversion, revenue,
collected cash, gross profit, and contribution only when each measure has its
own authoritative evidence and attribution confidence. It must distinguish
observed, derived, projected, incomplete, unavailable, and conflicting states.
No spend, revenue, payment, margin, or campaign ROI is inferred from counts.

## Permissions, events, and approvals

Marketing read and manage permissions are Company/Branch scoped. Source event
intake is append-only and auditable. Business Events must record admitted
source events, attribution decisions, disposition changes, identity-binding
decisions, and contribution recalculations without persisting secrets or raw
provider payloads unnecessarily.

Owner approval is required for campaign naming conventions, paid-spend
admission, attribution-window policy, cost allocation, contribution formula,
and any marketing action that changes external campaigns or budgets.

## Acceptance criteria

1. A sanctioned inbound event creates or attaches one Lead idempotently.
2. Source/campaign identity and evidence digest survive Lead-to-Customer and downstream lineage.
3. Prospect identity remains unresolved until authoritative Customer binding.
4. Estimate, Job, Invoice, Payment, and gross-profit links are source-backed.
5. Branch/company isolation and permission denial are tested.
6. Missing or conflicting attribution is visible, not converted to zero or certainty.
7. Owner can inspect source, campaign, confidence, evidence, and contribution limitations.
8. No provider credential, external campaign mutation, or autonomous budget action is required for the foundation.
