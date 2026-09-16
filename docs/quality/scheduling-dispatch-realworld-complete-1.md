# Scheduling / Dispatch real-world completion packet

Authority evaluated: `90af57abf5f4e2dbda75ed2680d4d420eb60410c`.

Candidate branch: `work/om2c-realworld-scheduling-activation-1`.

## Machine-qualified behavior

- Dispatch consumes Workforce technician eligibility. It does not create profiles or grant technician capability.
- Eligibility requires an active Employee and Workforce profile, authorized Branch, `technician` capability, applicable readiness and availability, and no conflicting assignment.
- Job and Appointment views project the authoritative Dispatch assignment. An unavailable assignment read is reported as unknown, never as unassigned.
- Scheduling ranges, calendar grouping, timeline placement, and edit controls use the selected Branch timezone.
- Day, Week, Work Week, Month, Month overflow, Needs Scheduling, technician, Branch, date, status, and text-filter behavior have focused automated coverage.
- Needs Scheduling creates the Appointment through Scheduling, then requires technician assignment through appointment-specific Dispatch eligibility. It does not preselect a technician from the general Workforce directory.
- Assignment/reassignment uses the existing versioned, idempotent Dispatch service and preserves assignment history and Business Events.

## Real-data gate

Real Preview counts, roster names, and record identities are deliberately not reported as zero. Protected Preview routes require sanctioned authentication, and no authorized acceptance session or attestation is present in this worktree. Preview is also deployed behind protected authority. No real record was mutated.

Enterprise must provide an authenticated owner/CSR session and deploy this candidate before operator acceptance. OM2-B must ensure each intended real field technician has an active native Employee, valid Workforce profile, MAIN Branch scope, explicit `technician` capability, and current availability/readiness. Lianne Hernandez and Alex Donahue must remain excluded from the technician selector unless Workforce separately grants technician capability.

## Owner acceptance script

1. Confirm the displayed release matches the integrated candidate and select MAIN Branch.
2. Open Scheduling for today and tomorrow; record Job, Appointment, unassigned, and Needs Scheduling counts.
3. Check Day, Week, Work Week, and Month; expand every `+N more` group used in the sample.
4. Open a real Appointment and navigate to its Job, Customer, and Service Location.
5. Confirm the selector contains only currently eligible real field technicians.
6. With explicit sanction for that real record, assign one eligible technician; save and refresh.
7. Confirm Appointment detail, Job detail, and Dispatch show the same technician.
8. With explicit sanction, reassign a safe Appointment; refresh and confirm the prior assignment remains in audit history.
9. Open Needs Scheduling. With explicit sanction, choose a real unscheduled Job and create its date/window.
10. Assign through Dispatch only after appointment-specific eligibility is available; refresh and verify calendar placement.
11. Exercise technician, date, status, Branch, window, and Needs Scheduling filters and record any source-only or readiness gaps.

Real-world closure requires the entire script against current All County records. Automated qualification alone is not operator acceptance.
