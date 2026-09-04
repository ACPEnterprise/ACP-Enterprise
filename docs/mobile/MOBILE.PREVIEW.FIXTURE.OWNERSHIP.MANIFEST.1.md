# Mobile Preview fixture ownership manifest

Authority base: `d90ba8b8f0615f57dea4774b81df3ba66c250f92`.

The tenant-scoped `preview_fixture_resources` manifest binds each synthetic logical
resource key to exactly one Company, fixture, resource identity, and authoritative
owning-domain creation reference/digest. Exact registration replays; contradictory
logical keys or attempts to claim an entity already owned by another fixture fail at
the service and database boundaries.

Release is unavailable unless the caller has explicit Preview fixture authorization
and supplies a complete, non-duplicated plan whose keys all resolve under the current
Company and exact `acp-employee-beta-v1` fixture. Non-audit resources require an
owning-domain release callback. The manifest records release only after that callback
succeeds. Callbacks must use the existing idempotent/lifecycle service operations:
Dispatch release, Appointment cancellation, Job cancellation, or Service Location
deactivation. The manifest is ownership proof; it is not permission to delete domain
history.

Timekeeping and Field evidence are append-only audit facts. Their manifest entries
reject deletion callbacks and transition to `audit_retained` with
`active_projection=false`. The released assignment, cancelled Appointment/Job, and
revoked Employee Membership remove those facts from active Mobile operating context;
the evidence remains available for audit and correction/successor history.

Service Location creation now participates in the shared durable mutation-receipt
contract, closing its retry duplication gap. Customer and Job already use that
contract; Scheduling uses a deterministic idempotency UUID; Dispatch and Timekeeping
persist request-digest/idempotency evidence. A future internal orchestration command
may compose these services and register their returned authority. No public/live
transport is introduced here.

No Preview data, real Employee/Customer data, communication provider, Apple service,
Production system, payroll execution, or money movement was touched.
