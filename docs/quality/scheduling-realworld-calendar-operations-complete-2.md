# Scheduling real-world calendar operations complete 2

Starting protected authority: `bae55401586e48e4b606604c3aac1eeef4832a27`.

Reconciled protected authority: `626eb9316d85e6fca52302b845d3fddf0aa17ce8`.

Branch: `work/om2c-scheduling-calendar-operations-complete-2`.

## Product boundary

This candidate changes Scheduling calendar, queue, detail, discovery, completeness,
refresh, responsive presentation, and operator error projection only. It does not
change Dispatch assignment, Dispatch API/hooks, Workforce readiness, technician
eligibility, or Employee onboarding.

Enterprise must integrate this candidate after or beside the reconciled OM2-B PR
#299 plus OM2-C `69bb0193ab3486871c0c9a7ba1ce145f316477d9` stack. There is no
path overlap with the OM2-B candidate. The existing OM2-C candidate and this branch
both touch `SchedulingRoute.tsx`, `AppointmentDetailRoute.tsx`, and the Appointment
detail test. Preserve the existing candidate's Branch-timezone conversion and
assignment projection while retaining this candidate's calendar-readiness,
conflict, refresh, detail-history, and queue behavior.

## Operator result

- Day rows are deterministically ordered and retain Customer, Location, Job,
  technician, window, and lifecycle presentation.
- Week and Monday-Friday Work Week render every returned Appointment; partial API
  results remain explicitly unsafe for operational completeness.
- Month displays per-day counts, the first three summaries, `+N more`, full expansion,
  and Day drill-down. Every returned Appointment remains reachable on narrow layouts.
- Needs Scheduling exposes Job, Customer, Location, age, priority/status, attention
  reason, readiness, Branch, service category, window, duration, and technician truth.
- Search composes the existing Job/Customer/Location projection. Service category,
  technician/unassigned, status, Branch, date, and queue filters remain bounded.
- Workspace conditions expose invalid/missing windows, missing Job/Location context,
  and same-technician overlaps without changing Workforce readiness.
- Appointment detail adds explicit Scheduling version/reschedule history, refresh,
  Customer/Location links, and truthful unavailable-source language.
- Explicit refresh refetches Scheduling, current-graph, Job context, and authorized
  Dispatch projections. No realtime behavior is implied.
- The calendar completeness card compares the admitted
  `hcp-source4-realworld-acceptance-snapshot/v1` baseline (11 Customers, 11 Locations,
  15 Jobs, 18 total Appointments, 14 in the bounded current/future query) with native
  authorized projections. Partial pagination or unavailable context never becomes a
  missing/zero conclusion.

## Owner acceptance script

1. Verify the deployed protected SHA and select MAIN Branch.
2. Open Scheduling for today; confirm chronological windows and open one Appointment.
3. Follow Appointment → Job → Customer → Location, then return to the same calendar scope.
4. Review Week and Work Week; confirm dense-day rows are all reachable.
5. Open Month; compare each day count, expand a crowded day, open its final row, and drill into Day.
6. Open Needs Scheduling; filter by priority, status, service category, and queue state.
7. Search by a real Job number, Customer, and Location fragment.
8. Review the current operating graph card; do not proceed as complete on PARTIAL or INCOMPLETE.
9. Review every conflict warning and correct missing parent/window evidence through its owning domain.
10. On an explicitly sanctioned real Appointment, review and confirm a reschedule; refresh and verify persistence.
11. Repeat Day and Month navigation at phone width.
12. After Enterprise's reconciled Dispatch deployment, separately run real-technician assignment acceptance.

No synthetic record, Preview record, source system, or Production state was mutated.
