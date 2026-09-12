# CSR booking operator acceptance 1

## Authority and composition

- Protected base: `68cdc38976fcfb2d5a20e7ce52fc78306bde91ce`
- Stacked visual dependency: `34655c8c2d062740023c8ba57b2fc6498952cd36`
- Customer navigation is consumed from the protected Customer detail contract;
  this candidate does not change Customer implementation.
- Job scheduling, atomic Job/Appointment booking, Scheduling projections,
  Dispatch assignment, conflict/version handling, and query invalidation remain
  owned by their existing services.

## Operator workflow

The qualified path is Customer → authorized Service Location → existing or new
Job → Appointment → Schedule/Dispatch. Existing Jobs use the protected #217
schedule panel, including a human-readable technician selector or explicit
Unassigned / Needs Scheduling. Protected #218 ensures an unassigned appointment
does not claim technician capacity.

New customer-work booking remains an explicitly confirmed atomic service
request. The CSR now enters a customer-facing arrival-window start and end
separately from expected work duration. An absent or inverted window disables
review and explains the correction; no request is sent. Successful persistence
links to the authoritative Appointment and Job and then to human-confirmed
Dispatch assignment.

The stacked calendar acceptance proves the same appointment is usable through
Month, Day, Week, Work Week, Unassigned, Schedule, and Dispatch; crowded Month
days expand without losing filters, hidden appointments are selectable, and
reschedule requires explicit confirmation. Dispatch recommendations and ghost
slots remain review-only.

## Acceptance evidence

Sanctioned fixtures cover Customer search, Location selection, Branch, arrival
window, duration, Job/Appointment result identities, assigned and unassigned
paths, refresh invalidation, stale/conflict-safe errors, local-day projection,
crowded Month interaction, record navigation, permission gates, keyboard-sized
controls, and phone control wrapping. They do not mutate Preview records and do
not constitute real SOURCE.4 acceptance.

After protected integration and deployment, Enterprise should rerun with an
authorized segregated fixture: book or schedule, record the returned identities,
refresh, verify the local date/window in Month and Day, compare Week/Work Week
and Dispatch, then assign/reassign through explicit Dispatch confirmation and
verify the refreshed authoritative state. Real SOURCE.4 adds mapped, unmapped,
canceled, partial-lineage, and legacy-status cases when Migration admits them.

Qualification passed 115 frontend test files / 414 tests, including focused CSR
booking, existing-Job scheduling, Month/cross-view, Dispatch presentation, API,
authorization, and stale/conflict coverage. ESLint, TypeScript/Vite production
build, `git diff --check`, and credential/private-key scanning passed. No schema
or backend source changes are included.

No autonomous Dispatch, Customer communication, Production, HCP/source
mutation, Payroll, payment, or Accounting action is included.
