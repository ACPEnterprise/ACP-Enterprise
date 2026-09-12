# CSR.NEEDS_SCHEDULING.OPERATIONS.1 qualification

## Authority and boundary

- Protected starting authority: `ee882429987feb73078fe229dbd57c60a366ce75`.
- Required immutable predecessors: `f2dbe1099ef0ceb18418d5aa5550a0c436bbd9c6` and `27435a99d8649912ed19f6e89d504ce165e53fe5`.
- The queue composes the existing Job, Appointment, and Dispatch projections. It does not create scheduling, assignment, or migration authority.
- Assignment remains an explicit authorized operator action in the existing appointment workflow.

## Delivered acceptance contract

The Unassigned view and the compact Schedule-side queue use one operator queue. It identifies:

- a native Job without an Appointment as `NEEDS_SCHEDULING`;
- a scheduled Appointment without an active Dispatch assignment as `SCHEDULED_UNASSIGNED`;
- a scheduled Appointment with an active assignment as `ASSIGNED`;
- an Appointment whose Customer/Job/Dispatch join is incomplete as `PARTIAL`, without weakening authoritative Appointment timing.

The queue displays available Customer, Service Location, Job, Job status, explicit priority/emergency state, Branch, created date, arrival window, expected duration, and assignment evidence. Missing values are rendered as unavailable or not established, never inferred.

Operator controls include URL-persisted queue state, Job status, priority, ordering, Branch, technician, date, and Customer/Job search. Ordering is explicit and reversible: oldest, newest, or authoritative Job priority followed by oldest. No hidden prioritization policy is introduced.

Every record provides bounded navigation to the authoritative Appointment, Job, Customer, and Service Location surfaces. The Scheduling return URL preserves the complete queue/filter state. Selecting an Appointment uses the existing human-confirmed assignment workflow.

## Current source-contract limitations

Current projections do not expose enough evidence to classify these states authoritatively:

- stale versus current projection evidence;
- Migration `HELD` or `SOURCE_ONLY` evidence;
- a requested service window distinct from an admitted Appointment arrival window;
- a durable source-observed timestamp or source projection digest.

The owning backend/source contract needed to close those gaps is a permission-scoped projection status with an authoritative state (`NATIVE`, `PARTIAL`, `STALE`, `HELD`, or `SOURCE_ONLY`), observed timestamp, stable evidence digest, and optional requested service window. Until that exists, the UI does not invent those classifications.

## SOURCE.4 rerun

When real SOURCE.4 records are admitted, rerun with at least: multiple unassigned Jobs, scheduled-unassigned and assigned Appointments, an emergency Job, a Job without a date, mapped/unmapped technicians, missing optional Customer/Location context, multiple Branches, and partial historical records. Verify the same authoritative Appointment identity, arrival window, status, and assignment across Unassigned, Schedule, Month, Day, Week, Work Week, and Dispatch; verify no `HELD` or `SOURCE_ONLY` record is presented as native actionable work.

## Safety

No schema, backend mutation, Migration admission, autonomous Dispatch action, communication, Preview deployment, or Production operation is part of this boundary.
