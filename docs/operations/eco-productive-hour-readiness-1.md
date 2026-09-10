# ECO.PRODUCTIVE.HOUR.READINESS.1 integration packet

Protected authority: `origin/customer-management-v1` at
`9ff11122c4591d8738c11164caff829ef72dc729`. The authoritative
`workforce.time-economics-readiness.v1` contract is integrated through protected
commit `b4cbc4a0`; this milestone extends it and does not recreate it.

`economics.productive-hour-readiness.v1` projects deterministic readiness at
Company, Branch, Employee, and Job/Appointment scope. It preserves separate
paid, scheduled, actual-worked, jobsite, productive-Job, travel,
nonproductive-operational, and unclassified-paid measurements. Every measure is
classified `AVAILABLE`, `PARTIAL`, `ABSENT`, or `CONFLICTING`, with minutes
withheld whenever incomplete or conflicting evidence would create false
precision.

Scheduled duration never supplies actual worked duration. Employee paid time
remains Timekeeping-owned and acquires Job context only as an explicitly named
interval overlap, never as a Payroll allocation. Multi-technician Jobs retain
separate Employee/Job/Appointment scopes. Supplemental travel and
nonproductive evidence must match an authoritative labor relationship when
Job-scoped and must carry source provenance when available.

The downstream break-even and labor-cost contract identifies the factual inputs
needed by future models. Labor burden method, break-even method, overhead
allocation, and the owner definition of productive time remain
`POLICY_REQUIRED`. No rate, price, ranking, recommendation, Payroll execution,
Price Book activation, or employment action is produced.

Accepted HCP operational evidence remains Migration-owned. Missing travel,
arrival/jobsite, work timestamps, pause/resume, timezone, or Employee crosswalk
evidence remains absent or partial until a successor-aware, digest-bound source
is admitted.

Qualification used a fresh isolated PostgreSQL 16 cluster. Zero-to-head reached
`a1c3e5g7i9k1`; `alembic current` equaled head and `alembic check` reported no
drift. All 957 affected Operational Measurement, Timekeeping, Jobs, Scheduling,
Dispatch, Workforce, Payroll, Business Economics, HCP Migration, and Luminary
tests passed.
