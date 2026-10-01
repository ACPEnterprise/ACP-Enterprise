# LIA CSR/Dispatch Copilot Contract v1

This is a transient, server-owned composition contract. It guides a CSR and
does not create Customers, reserve ghost slots, assign Employees, or mutate
Appointments.

## Speech interpretation

Each critical field is represented by:

`state` (`CONFIDENT`, `CONFIRM_RECOMMENDED`, or `UNCERTAIN`), `heard_text`,
optional `evidence_digest`, `possible_meaning`, `suggested_confirmation`,
`source_language`, optional `interpreted_language`, `translation_state` and
`translation_provenance`, `as_of`, `confirmed`, `owning_fact_type`, and bounded
`context`.

Only a `CONFIDENT` interpretation explicitly confirmed by the CSR/customer may
be admitted to the owning domain. Phone must render non-confident fields as
clarification/translation guidance and must not infer a route or persist a
business fact locally.

## Customer branch

`customer_branch.state` is `EXISTING`, `NEW_CUSTOMER_INTAKE_REQUIRED`, or
`AMBIGUOUS`. An `EXISTING` branch includes canonical Customer and Location IDs.
The new/ambiguous branches include missing fields and next questions. Identity
is supplied by the Customer authority; fuzzy similarity is never identity.

## Dispatch guidance

The contract carries the current server-composed primary ghost slot,
alternates, constrained options, limitations, expiration context, and shared
`NavigationSuggestion` action metadata. Recommendations are current only when
canonical Customer/Location context and confirmed critical speech facts permit
it; otherwise they remain provisional.

Scheduling/Dispatch remains authoritative for eligibility, capacity, conflicts,
Appointments, assignments, and mutations. A recommendation is non-mutating,
non-capacity-reserving, and expiring/supersedable.
