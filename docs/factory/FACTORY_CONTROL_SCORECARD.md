# Factory Control scorecard contract

Factory Control reports equal-weight milestone progress from the canonical
`acp_full_system_roadmap.yaml` roadmap plus immutable, authorized Factory events.
Every represented canonical milestone has weight `1`. A canonical milestone named
in another canonical milestone's `supersedes` list is excluded from both numerator
and denominator; references to historical PR or checklist identifiers do not add
roadmap weight.

## Headline measures

- **Engineering Completion**: engineering status is `ENGINEERING_READY`,
  `INTEGRATED`, `DEPLOYED_BETA`, or `CLOSED`, or an authorized
  `engineering_complete` event is current.
- **Beta Operability**: an authorized `beta_complete` event is current, or the
  milestone is strictly `CLOSED`. `DEPLOYED_BETA` alone does not prove an operator
  workflow works and is not counted.
- **Owner Accepted**: owner acceptance status is `ACCEPTED` or `CLOSED`, or an
  authorized `owner_accepted` event is current.
- **Full-System CLOSED**: lifecycle status is `CLOSED`, or an authorized `closed`
  event is current. A close implies the preceding engineering, Beta, and owner
  stages. Reopen events remove the affected current stage without deleting history.

Each percentage is `100 * current stage weight / represented milestone weight`,
rounded to two decimal places. The UI also displays the exact numerator and
denominator.

## Event-only measures

Defect transitions, gates, handoff/pickup latency, release latency, lane
utilization, eligible-idle time, queue depth, and 1/3/7-day velocity require
durable controller events. When no authorized events or lane projections exist,
the API and UI report `NOT_YET_MEASURED`; they never render an empty history as
zero activity.

The existing `/api/v1/platform/factory-control/internal/sync` connection projects
Development Factory worker and queue truth into the same event and lane tables.
It requires an exact active worker identity plus an explicit
`PLATFORM_FACTORY_CONTROL_INGEST` assignment. No tenant role implies that global
platform authority.

## Acceptance movement test

The sanctioned scorecard movement test uses a synthetic in-memory roadmap. It
asserts that an `engineering_complete` event changes only Engineering Completion
and cannot change Beta Operability, Owner Accepted, or Full-System CLOSED. It does
not write Beta metadata or alter a real milestone.
