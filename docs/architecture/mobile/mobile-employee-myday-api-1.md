# MOBILE.EMPLOYEE.MYDAY.API.1 — Authenticated Employee My Day Projection

## Contract

`GET /api/v1/employee-operations/me/day` is a read-only, Company-scoped employee self-service projection. The optional `business_date` parameter is a strict local calendar date. When omitted, the server resolves the date from the active Branch timezone, falling back to the Company timezone. The response identifies both the resolved date and timezone.

The route requires `COMPANY_EMPLOYEE_OPERATIONS_OWN_DAY_READ`; it does not require broad Job, Scheduling, or Dispatch read permission. Authentication and authorization resolve the active Company/Membership. The service resolves the active, non-archived Employee using `(company_id, membership_id)`. A missing linkage returns HTTP 422 and cannot be mistaken for an empty day. Authentication remains HTTP 401, missing capability remains HTTP 403, and a legitimate no-work result is HTTP 200 with an empty `assignments` array.

## Assignment authority

The persistence query constrains Company, authorized Branch IDs, resolved Employee, scheduling window, and active assignment state before returning data. It includes an Employee who is either the primary assignee or an active crew member. Removed crew and released, replaced, or canceled Dispatch assignments are excluded. Reassignment therefore disappears on the next read.

The business-day placement and deterministic ordering use Appointment arrival-window timestamps with Appointment ID as the stable tie-breaker. Rescheduling moves work according to the updated Appointment window. A canceled Appointment is returned with explicit `appointment_status="cancelled"` only if its Dispatch assignment still has an accepted active state; normally accepted cancellation releases/cancels the assignment and therefore removes it.

No current/next designation is fabricated in v1. `designation` is null because Workday clock state is independent and current Dispatch persistence does not provide a sufficient universal current/next rule.

## Privacy and performance

The dedicated response exposes appointment/job identifiers and statuses, scheduling window, safe service category (`job_type_code`), assignment role/state, customer display name, and the service address needed to perform assigned work. It excludes Customer contacts/history, phone/email, financial fields, prices, estimates, invoices, balances, costs, margins, Payroll, compensation, and Business Economics data.

Free-text Customer notes, property notes, Job `internal_description`, and `customer_reported_problem` are omitted because current persistence does not carry an explicit field-employee visibility classification.

The query is one joined projection across Dispatch Assignment, Appointment, Customer, Service Location, and optional Job, with a correlated `EXISTS` for active crew membership. It does not load a Company schedule or issue one query per assignment. The endpoint performs no mutation and emits no Business Event.
