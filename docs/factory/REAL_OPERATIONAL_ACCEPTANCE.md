# Real Operational Acceptance

The canonical machine-readable matrix is
`docs/factory/acp_full_system_roadmap.yaml#real_operational_acceptance`. Factory
Control renders that evidence under **Real Operational Acceptance**.

## Standard

A surface is `PASS` only after a normal Michael, Lianne, or employee workflow
uses authoritative All County data through the normal UI, performs the normal
operator action, persists the durable result, and successfully continues to the
next workflow step.

Page load, route existence, API success, deployment, fixture data, synthetic
tests, and engineering smoke are not Beta operability or owner acceptance.
History is append-only: later physical failures produce defect/reopen evidence;
they do not erase earlier engineering or deployment evidence.

## Current physical failures

| Surface | Result | Owning lane | Defect |
|---|---|---|---|
| Customers | Source reconciliation reports `SERVICE UNREACHABLE` | OM2-A / Customers | #432 |
| Service Agreements | No meaningful real agreement population is visible | OM2-A / Service Agreements | #479 |
| My Day | `YOUR ITINERARY IS UNAVAILABLE` | OM2-C / Workforce, Dispatch, Mobile | #480 |
| Scheduling | Operating graph is partial and authorized Job projections are missing | OM2-C / Scheduling and Dispatch | #439 |
| Payroll | Real inputs, native calculation, close, register, and paper-check workflow are unavailable | OM2-B / Payroll | #449 |

## All County recurring golden path

No record is designated merely because it exists in a database. The owner must
confirm the exact real record before it becomes acceptance authority.

| Required record | Current state |
|---|---|
| Real Customer | `HUMAN_CONFIRMATION_REQUIRED` after provider-ID reconciliation. Hammer Haag is authoritative source evidence but is not yet a native golden-path Customer. |
| Customer with Location | `HUMAN_CONFIRMATION_REQUIRED` after exact Customer/Location linkage is published. |
| Open Job | `HUMAN_CONFIRMATION_REQUIRED`; current completeness must be published first. |
| Scheduled Appointment | `HUMAN_CONFIRMATION_REQUIRED`; current operating graph is incomplete. |
| Technician | `HUMAN_CONFIRMATION_REQUIRED`; owner certification and eligibility remain authoritative. |
| Estimate | `HUMAN_CONFIRMATION_REQUIRED`; exact Customer/Location/catalog prerequisites apply. |
| Invoice | `HUMAN_CONFIRMATION_REQUIRED`; exact sold Job lineage is required. |
| Service Agreement | `HUMAN_CONFIRMATION_REQUIRED` only if authoritative source evidence exists. |
| Payroll Employee | `HUMAN_CONFIRMATION_REQUIRED`; identity, compensation, tax, policy, and accepted time must be certified. |

Once confirmed, identifiers belong in protected acceptance evidence, not in a
fixture or a synthetic seed. Releases touching a golden-path domain must prove
the same connected workflow still works.
