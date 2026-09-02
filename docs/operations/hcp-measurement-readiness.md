# HCP operational measurement readiness

This capability consumes only Migration-admitted, digest-bound projections. It
does not inspect protected acquisition files, decide admission, repair source
truth, create Employees, or mutate native operational evidence.

## Source/native semantics

- HCP schedule start/end may become an ACP Appointment window only when both
  timestamps are timezone-aware, ordered, parent-bound, and source-digest bound.
- A missing window remains missing. Broad windows remain partial and policy
  required; cross-midnight windows remain explicit rather than being split.
- HCP Job status may become historical lifecycle evidence only through the
  registered Migration mapping. Missing intermediate transitions are not
  fabricated.
- Source technician IDs require an explicit crosswalk disposition. Inactive
  historical Employees remain valid historical attribution; unmapped and
  multiple-technician cases remain visible.
- Started/completed timestamps without complete pause evidence are elapsed-work
  evidence, not pause-corrected active duration.

## Current field audit

SOURCE.4 exposes Job schedule, appointment windows, assigned/dispatched source
technician IDs, Job and appointment state, `on_my_way`, work start/completion,
Job type, and Business Unit. Current downstream transformation retains the
window, scheduled duration, lifecycle, source technician IDs, work start and
completion. It does not yet retain category, Business Unit/Branch provenance,
`on_my_way`, or provider timezone as admitted downstream fields. Pause/resume
evidence and an authoritative priority mapping are absent.

## August 28 acceptance

`reconcile_date` consumes a bounded admitted projection and assigns every input
source identity exactly one disposition: admitted, held, unmapped technician,
incomplete window, canceled/historical, or another explicit disposition. The
report binds source identities/digests, timezone, date, counts, and a replay
digest. It never hard-codes screenshot-derived names or counts.

## Downstream behavior

Scheduling can render authoritative dated windows without waiting for
technician mapping or measured duration. Dispatch Intelligence admits valid
window/duration evidence while keeping travel, Fleet, capability,
certification, and mapping gaps explicit. Economics may consume work period,
category, and entity linkage readiness, but operational history never implies
revenue, cash, labor cost, materials, or profitability. Luminary explains these
limitations without causal claims.
