# Scheduling / CSR launch acceptance 2

## Authority and boundary

- Owner mission: `0c08f1e3634f38a7fb82970932dea5de7a4cf24f`
- Protected base: `b22297c65165280a761860198dc05441df4a4312`
- Reuses the protected Scheduling operator UX integrated by PR #204.
- No Scheduling engine, Customer workflow, Dispatch recommendation, or source
  admission behavior is duplicated.

## Repaired operator defects

Crowded Month days now expand in place when an operator activates `+N more`.
All appointments become directly keyboard/touch selectable without losing the
Month context or active filters. The day-number control remains the explicit
Month-to-Day drill-down. The control exposes expanded state to assistive
technology and can collapse the day again.

Selected appointment detail now reconciles after the authoritative appointment
query refreshes. Reschedule success can no longer leave the former time and
duration in the open detail form. Mutation remains human-confirmed and uses the
existing versioned Scheduling service.

Successful CSR booking now provides direct Appointment, Job, and Dispatch
navigation. Assignment remains a separate authorized, human-confirmed Dispatch
operation.

## Deterministic acceptance

The focused suite proves crowded-day expansion, selection of an originally
hidden appointment, Customer/Job/Appointment navigation, explicit Day
drill-down, filter continuity, local-time conversion, selected-detail refresh,
human confirmation, Customer/Location booking, persistence response links,
cross-view projection, Unassigned, and review-only Dispatch intelligence.

Real SOURCE.4 rerun remains a deployed-data acceptance gate. When admitted,
Enterprise should verify a mapped and unmapped technician, unassigned and
canceled work, arrival windows across local-day boundaries, and the same source
appointment across Month, Day, Week, Work Week, Schedule, Dispatch, and
Unassigned. The UI continues to label partial query populations and missing
Customer/Location/assignment evidence rather than manufacturing context.

No Production, HCP mutation, autonomous Dispatch, source mutation, customer
communication, Payroll, payment, or Accounting action is included.
