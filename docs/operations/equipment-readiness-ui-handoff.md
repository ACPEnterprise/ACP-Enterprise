# Daily equipment readiness UI handoff

This contract is for the field/mobile and owner interfaces. The backend remains the
authority for custody, readiness, requirements, warnings, and attention. Clients
must never infer equipment requirements from Job text.

## Field clock-in

After a successful clock-in, request:

`GET /api/v1/equipment-readiness/employees/{employee_id}/daily-prompt?work_date=YYYY-MM-DD`

If `required` is false, continue without an equipment step. Otherwise show the
returned items as a single fast confirmation. Submit one idempotent request to
`POST /api/v1/equipment-readiness/daily-confirmations`. A missing or broken item
is a warning/report, not a failed clock-in.

An `incomplete_set` report must name configured missing components. A `transferred`
report must identify the receiving Employee or governed location. The response is
the durable receipt and may safely be recovered by replaying the same idempotency
key and payload.

## Midday change

Use `POST /api/v1/equipment-readiness/placements/{placement_id}/custody` with the
current placement version. A stale version returns 409. The action records an
append-only custody event and updates the current projection.

## Dispatch

Use the branch readiness endpoint for the equipment dimension and the job/employee
fit endpoint for a selected assignment. `AVAILABLE_EQUIPMENT_WARNING` is explicitly
a soft warning; `continuation_allowed` remains true. Existing Dispatch constraints
remain authoritative and separate.

## Manager home

Users with governed Owner, Company Administrator, or Field Service Manager role
authority may read `/attention`. The UI should show critical-before-job items first,
then needs-attention and information items. It must not use Employee names to infer
management authority.

## Intelligence boundary

`/intelligence-evidence` is read-only. Beacon and Luminary may explain or analyze
the evidence but have no custody, resolution, assignment, or pricing authority.
