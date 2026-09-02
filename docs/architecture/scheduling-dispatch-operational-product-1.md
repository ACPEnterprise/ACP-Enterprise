# Scheduling and Dispatch operational product 1

The accepted Scheduling and Dispatch services remain authoritative. This product boundary replaces the list-first Scheduling presentation with a calendar-first office workspace.

## Product contract

- Day view renders appointments on a 7:00–19:00 time axis in technician lanes, including an explicit Unassigned lane.
- Week view provides bounded planning across seven days with previous, today, next, and direct-date navigation.
- The needs-scheduling queue is derived from authorized nonterminal Jobs whose accepted projection has no earliest Appointment.
- Customer, Service Location, Job, priority, timing, assignment, arrival, and field lifecycle labels come from existing Scheduling, Dispatch, and Job projections.
- Rescheduling calls the existing versioned Scheduling endpoint. It retains Branch, conflict, capacity, concurrency, Business Event, audit, and idempotency authority.
- Assignment and reassignment use the existing Dispatch assignment panel and eligibility service.
- Empty, partial, unknown-duration, unmapped-technician, and missing optional evidence states remain visible and non-fatal.
- Unbooked calendar space is explicitly not called technician availability unless Workforce authority establishes it.

## HCP operational acceptance packet

For protected Preview acceptance, use migrated synthetic-safe or approved HCP-derived records and verify:

1. Customer and Service Location labels resolve through native projections.
2. Appointments appear on their authoritative service date and time without duplicates.
3. Mapped technicians occupy their lane; unmapped assignments appear Unassigned or reconciliation-required.
4. Legacy/canceled/open states remain explicit and do not become newer ACP lifecycle facts merely from source text.
5. Unknown duration receives a bounded visual fallback while remaining labeled as unknown in detail.
6. Partial records do not crash the calendar, queue, details, or filters.
7. A version-conflicting reschedule fails visibly and does not overwrite concurrent authority.

Preview execution and deployment remain Enterprise-owned. Production is excluded.
