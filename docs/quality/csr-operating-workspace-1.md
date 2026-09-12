# CSR operating workspace 1

## Authority and boundary

- Protected base: `4514b5df6be66e50ee172085c622ae613e172086`.
- Reconciled protected authority: `d52d117801d72d04e81afac157671c97a941efa0`.
- Immutable stacked dependency: `f2dbe1099ef0ceb18418d5aa5550a0c436bbd9c6`.
- Customer, Job, Appointment, Scheduling, and Dispatch remain owned by their
  existing domain services. This candidate adds no backend, schema, Customer
  model, booking engine, or Dispatch mutation authority.

## Office workflow

The existing flow remains Customer search → Customer → authorized Service
Location → create/open Job → schedule Appointment → Schedule/Month/Week/Work
Week → Dispatch assignment. Arrival-window start/end remain distinct from
expected work duration, and booking, assignment, and rescheduling remain
explicit authorized human actions.

The Scheduling workspace now serializes its operating scope into the URL:
local service date, view, Schedule/Dispatch perspective, Branch, technician,
status, bounded search, and selected Appointment. Direct links restore that
scope. Opening an Appointment, Job, or Customer carries a validated internal
Scheduling return path so normal back navigation no longer resets the CSR's
calendar or filters. Foreign or malformed return targets fail closed to
`/scheduling`.

Job detail now offers permission-gated Customer navigation and preserves the
Scheduling return path when opening its Customer or linked Appointment. This
is navigation composition only and does not modify Customer implementation.

## Partial and failure states

An Appointment/Dispatch projection failure offers an explicit bounded retry.
A failed Job-context projection is reported separately: authoritative
Appointment timing remains usable, while Customer, Location, Job status, and
related navigation are identified as incomplete until retry succeeds. Empty,
loading, authorization, stale-version, and conflict behavior remain governed
by the existing qualified contracts.

## Acceptance

Sanctioned frontend fixtures prove direct-link restoration, Month selection,
Appointment/Job/Customer round trips, hostile return-path rejection, filters,
local date context, separate arrival windows and work duration, retry behavior,
and permission-gated Customer navigation. Existing suites continue to cover
crowded Month expansion, phone-wrapping controls, keyboard-sized actions,
explicit booking/reschedule confirmation, assignment, Unassigned / Needs
Scheduling, stale conflicts, and Schedule/Dispatch consistency.

Real SOURCE.4 and deployed acceptance remain Enterprise/Migration gates. The
deployed rerun should select a real admitted Appointment from a filtered Month,
open Appointment → Job → Customer, return to the identical calendar scope,
then verify a human-confirmed assignment/reschedule survives refresh across
Schedule and Dispatch.

No Production, customer communication, autonomous Dispatch, HCP mutation,
Payroll, payment, or Accounting action is included.
