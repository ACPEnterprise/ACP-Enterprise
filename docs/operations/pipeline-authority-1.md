# Pipeline authority v1

## Repository audit

ACP already owns authoritative Customers and contacts, Jobs, Appointments and
Scheduling, Estimates, communications, Business Events, permissions, and HCP
source-lineage evidence. Customer `marketing_source` and HCP `lead_source`
preserve attribution, but neither was an opportunity lifecycle. The Estimates
workspace is an Estimate artifact list, not a Pipeline. No protected model or
API represented a prospect before Customer creation or required the next CSR
action.

Pipeline reuses those authorities by identity. It does not duplicate Customer,
Job, Appointment, Estimate, assignment, or communication state. Existing
Customer read/manage permissions govern this first CRM increment, preserving
the established CSR and owner/admin role boundary without a parallel grant
system.

## Canonical contract

`pipeline_leads` is the single opportunity authority. A Lead can reference an
existing Customer or retain a prospect/contact name before Customer creation.
Lead source is attribution and never determines whether the opportunity is a
Lead. Active lifecycle stages retain owner, last action, next action, due time,
and contact attempts. Every mutation emits append-only Lead history; lifecycle
changes also emit Business Event and audit evidence.

The lifecycle is:

`new -> contacted -> qualified -> appointment_needed -> scheduled ->
estimate_follow_up -> won`, with bounded alternate transitions to `lost` and
`nurture`. The transition contract validates optimistic version, Company,
Branch, assignee membership, and linked Appointment/Job/Estimate authority.

## Projections

The CSR queue derives New, Needs Attention, Scheduled, Estimate Follow-Up,
Won, Lost, and Nurture views from the canonical rows. Needs Attention explains
new/uncontacted, due/overdue, qualified-not-scheduled, Estimate follow-up,
missing-next-action, and stale conditions.

The Command Center contract returns `moving_forward` and `needs_attention`
buckets. Each bucket includes an exact count and a canonical `/pipeline?view=`
drill-down. Monetary value is null unless every member has admitted value
authority in the same currency; zero is never substituted for unknown value.

## HCP and call implications

No migration admission behavior changes here. HCP opportunities may be
admitted later using `source_system`, `source_provider_id`, source version,
observed timestamp, and the existing SOURCE.4 evidence lineage. Acquired,
unavailable, unsupported, missing, and ambiguous history remain Migration
classifications; this model does not infer historical stages.

Incoming phone, SMS, web, referral, existing-customer, advertising, and manual
opportunities can all create Leads. Repeated contact is recorded against the
same Lead with idempotent contact activity. Automatic classification of a
communication as a legitimate service opportunity remains a Communications
source contract gap: administrative/spam/vendor calls must be dispositioned
before Lead creation, and no fuzzy phone-number deduplication is permitted.

## Follow-on gaps

- Connect sanctioned Communications dispositions to create-or-attach Lead
  commands using stable provider/contact identity.
- Add Customer-to-Lead conversion that binds a prospect Lead to a newly created
  Customer without fabricating Customer identity.
- Compose accepted Estimate decision evidence into an explicit
  approved-not-scheduled queue classification.
- Add assigned-CSR display names and a bounded assignee picker from Workforce.
- Add durable follow-up notifications/tasks after their owning authority
  exposes an accepted contract.
