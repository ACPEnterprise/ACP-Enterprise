# Scheduling multiview and HCP acceptance

`SCHEDULING.MULTIVIEW.HCP.ACCEPTANCE.1` keeps one Scheduling and Dispatch
authority and adds operator projections over the same bounded appointment, Job,
assignment, and Workforce evidence.

## Operator projections

- **Schedule / Day:** technicians are columns and time is vertical.
- **Dispatch / Day:** technicians are rows and time is horizontal.
- **Week / Work Week / Month:** planning projections use the same appointment
  query and selection/detail workflow.
- **Unassigned:** the existing operational Job query remains the source for work
  needing scheduling. It is not a second queue authority.

Open visual space means only that no appointment is projected there. It does not
claim Employee availability. Assignment, reassignment, and rescheduling continue
to use the existing versioned Dispatch and Scheduling commands. Dispatch
Intelligence remains a deterministic, non-mutating proposal; its proposed window
is a ghost-slot seam and requires human approval through an owning command.

## SOURCE.4 comparison

`hcp-acp-schedule-comparison.v1` compares Migration-admitted SOURCE.4 appointment
evidence with a minimum ACP native schedule projection. Each source appointment
receives exactly one `MATCHED`, `PARTIAL`, or `CONFLICTING` row. The comparison
binds source/native evidence digests and checks:

- Company and Branch;
- appointment status;
- arrival-window start and end;
- explicitly crosswalked Employee identities;
- missing and duplicate native source lineage.

Unmapped technicians remain partial and visible. Missing native records remain
partial. Contradictory status, window, scope, technician, or duplicate lineage
fails closed as conflicting. Input ordering does not affect the report digest.
The comparison reads bounded projections only: it neither opens sealed HCP data
nor admits, repairs, creates, schedules, or dispatches anything.

## Preview acceptance boundary

After `MIGRATION.HCP.PREVIEW.SUCCESSOR.RECONCILIATION.1` admits real SOURCE.4
records, Enterprise can generate the comparison for the same Company, Branch,
date, and source package shown in HCP, then verify the Calendar projections and
comparison counts together. Acceptance must retain unmapped technicians,
canceled/historical work, unknown duration, missing optional metadata, and held
records as explicit states rather than fabricated native truth.
